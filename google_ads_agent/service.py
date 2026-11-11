"""High-level functions intended to be exposed as agent tools."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from google_ads_agent.config import AgentConfig
from google_ads_agent.errors import (
    GoogleAdsRequestError,
    PlanInputMismatchError,
    SafetyLimitError,
    TargetingConflictError,
)
from google_ads_agent.gateway import AdsGateway
from google_ads_agent.geo import resolve_geo_targets
from google_ads_agent.models import (
    AccountContext,
    ActionPlan,
    ActionResult,
    CampaignMatchResult,
    CampaignSelector,
    DailyAccountBrief,
    DailyBriefPolicy,
    ExecutionControl,
    ExecutionMode,
    LocationCriterion,
    LocationInput,
    LocationPerformancePolicy,
    LocationPerformanceReport,
    MeasurementAuditResult,
    MeasurementReadiness,
    MutationError,
    PlannedAction,
    ResolvedLocation,
    ResultStatus,
    RiskLevel,
    StoredPlanStatus,
)
from google_ads_agent.plan_store import PlanStore
from google_ads_agent.reporting import (
    audit_measurement_and_goals,
    daily_account_brief,
    location_performance_report,
)
from google_ads_agent.selectors import find_campaigns
from google_ads_agent.utils import (
    action_plan_hash_payload,
    normalize_customer_id,
    stable_hash,
    utc_now,
)
from google_ads_agent.version import __version__

TOOL_EXCLUDE_LOCATIONS = "exclude_locations_from_matching_campaigns"


class GoogleAdsAgent:
    """Facade containing deterministic, approval-gated Google Ads tools."""

    def __init__(
        self,
        gateway: AdsGateway,
        *,
        config: AgentConfig | None = None,
        plan_store: PlanStore | None = None,
    ) -> None:
        self.config = config or AgentConfig()
        self.gateway = gateway
        self.plan_store = plan_store or PlanStore(self.config.plan_database_path)

    @classmethod
    def from_config(cls, config: AgentConfig | None = None) -> GoogleAdsAgent:
        settings = config or AgentConfig.from_env()
        from google_ads_agent.google_gateway import GoogleAdsApiGateway

        gateway = GoogleAdsApiGateway.from_config(settings)
        return cls(gateway, config=settings)

    def get_account_context(self, customer_id: str) -> AccountContext:
        return self.gateway.get_account_context(normalize_customer_id(customer_id))

    def find_campaigns(
        self,
        customer_id: str,
        selector: CampaignSelector,
    ) -> CampaignMatchResult:
        account = self.get_account_context(customer_id)
        return find_campaigns(self.gateway, account, selector)

    def audit_measurement_and_goals(
        self,
        customer_id: str,
    ) -> MeasurementAuditResult:
        account = self.get_account_context(customer_id)
        return audit_measurement_and_goals(self.gateway, account)

    def daily_account_brief(
        self,
        customer_id: str,
        policy: DailyBriefPolicy | None = None,
    ) -> DailyAccountBrief:
        account = self.get_account_context(customer_id)
        return daily_account_brief(
            self.gateway,
            account,
            policy or DailyBriefPolicy(),
        )

    def get_location_performance_report(
        self,
        customer_id: str,
        selector: CampaignSelector,
        policy: LocationPerformancePolicy,
    ) -> LocationPerformanceReport:
        account = self.get_account_context(customer_id)
        matches = find_campaigns(self.gateway, account, selector)
        report = location_performance_report(
            self.gateway,
            account,
            matches,
            policy,
        )
        measurement = audit_measurement_and_goals(self.gateway, account)
        if measurement.readiness != MeasurementReadiness.READY:
            report = report.model_copy(
                update={
                    "warnings": [
                        (
                            f"Measurement readiness is {measurement.readiness.value}; "
                            "resolve goal-audit issues before acting on city candidates."
                        ),
                        *report.warnings,
                    ]
                }
            )
        return report

    def resolve_geo_targets(
        self,
        customer_id: str,
        locations: list[LocationInput],
    ) -> list[ResolvedLocation]:
        normalized_id = normalize_customer_id(customer_id)
        if not locations:
            raise ValueError("at least one location is required")
        return resolve_geo_targets(self.gateway, normalized_id, locations)

    def exclude_locations_from_matching_campaigns(
        self,
        *,
        customer_id: str,
        selector: CampaignSelector,
        locations: list[LocationInput],
        control: ExecutionControl,
    ) -> ActionPlan | ActionResult:
        normalized_id = normalize_customer_id(customer_id)
        if not locations:
            raise ValueError("at least one location is required")
        self._enforce_control_limits(control)

        request_payload = {
            "customer_id": normalized_id,
            "selector": selector.model_dump(mode="json"),
            "locations": [
                location.model_dump(mode="json")
                for location in sorted(
                    locations,
                    key=lambda item: (
                        item.country_code,
                        item.name.casefold(),
                        item.target_type or "",
                    ),
                )
            ],
        }
        request_fingerprint = stable_hash(request_payload)

        if control.mode == ExecutionMode.PLAN:
            return self._plan_location_exclusions(
                customer_id=normalized_id,
                selector=selector,
                locations=locations,
                control=control,
                request_payload=request_payload,
                request_fingerprint=request_fingerprint,
            )
        return self._execute_location_exclusions(
            customer_id=normalized_id,
            selector=selector,
            locations=locations,
            control=control,
            request_fingerprint=request_fingerprint,
        )

    def _enforce_control_limits(self, control: ExecutionControl) -> None:
        if control.max_campaigns > self.config.max_campaigns_hard_limit:
            raise SafetyLimitError(
                "max_campaigns exceeds the application hard limit",
                details={
                    "requested": control.max_campaigns,
                    "hard_limit": self.config.max_campaigns_hard_limit,
                },
            )
        if control.max_operations > self.config.max_operations_hard_limit:
            raise SafetyLimitError(
                "max_operations exceeds the application hard limit",
                details={
                    "requested": control.max_operations,
                    "hard_limit": self.config.max_operations_hard_limit,
                },
            )

    def _read_source_state(
        self,
        customer_id: str,
        selector: CampaignSelector,
        locations: list[LocationInput],
    ) -> tuple[
        AccountContext,
        CampaignMatchResult,
        list[ResolvedLocation],
        list[LocationCriterion],
        dict[str, str],
    ]:
        account = self.gateway.get_account_context(customer_id)
        matches = find_campaigns(self.gateway, account, selector)
        resolved = resolve_geo_targets(self.gateway, customer_id, locations)
        campaign_ids = [match.campaign.id for match in matches.matched]
        criteria = self.gateway.list_location_criteria(customer_id, campaign_ids)

        source_hashes: dict[str, str] = {
            "account": stable_hash(
                {
                    "customer_id": account.customer_id,
                    "currency_code": account.currency_code,
                    "time_zone": account.time_zone,
                    "status": account.status,
                }
            ),
            "resolved_locations": stable_hash(
                [
                    item.model_dump(mode="json")
                    for item in sorted(
                        resolved,
                        key=lambda item: item.target.resource_name,
                    )
                ]
            ),
            "matched_campaign_ids": stable_hash(sorted(campaign_ids)),
        }
        for match in matches.matched:
            source_hashes[f"campaign:{match.campaign.id}"] = stable_hash(
                match.campaign.model_dump(mode="json")
            )
            campaign_criteria = sorted(
                (
                    criterion.model_dump(mode="json")
                    for criterion in criteria
                    if criterion.campaign_id == match.campaign.id
                ),
                key=lambda value: value["resource_name"],
            )
            source_hashes[f"location_criteria:{match.campaign.id}"] = stable_hash(
                campaign_criteria
            )
        return account, matches, resolved, criteria, source_hashes

    def _build_location_actions(
        self,
        matches: CampaignMatchResult,
        resolved: list[ResolvedLocation],
        criteria: list[LocationCriterion],
    ) -> tuple[list[PlannedAction], list[dict[str, Any]]]:
        actions: list[PlannedAction] = []
        skipped: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []

        criterion_index = {
            (
                criterion.campaign_id,
                criterion.geo_target_constant,
                criterion.negative,
            ): criterion
            for criterion in criteria
            if criterion.criterion_type == "LOCATION"
        }

        for match in matches.matched:
            campaign = match.campaign
            for location in resolved:
                key = (campaign.id, location.target.resource_name)
                if (*key, False) in criterion_index:
                    conflicts.append(
                        {
                            "campaign_id": campaign.id,
                            "campaign_name": campaign.name,
                            "location": location.target.canonical_name,
                            "reason": "location is currently a positive target",
                        }
                    )
                    continue
                if (*key, True) in criterion_index:
                    skipped.append(
                        {
                            "campaign_id": campaign.id,
                            "campaign_name": campaign.name,
                            "location": location.target.canonical_name,
                            "reason": "location is already excluded",
                        }
                    )
                    continue

                action_seed = {
                    "campaign": campaign.resource_name,
                    "geo_target": location.target.resource_name,
                    "action": "CREATE_LOCATION_EXCLUSION",
                }
                actions.append(
                    PlannedAction(
                        action_id=f"action_{stable_hash(action_seed)[:16]}",
                        action_type="CREATE_LOCATION_EXCLUSION",
                        campaign_id=campaign.id,
                        campaign_name=campaign.name,
                        campaign_resource_name=campaign.resource_name,
                        geo_target_constant=location.target.resource_name,
                        location_name=location.target.canonical_name,
                        before="not excluded",
                        after="excluded",
                        reason="; ".join(match.reasons),
                    )
                )

        if conflicts:
            raise TargetingConflictError(
                "one or more requested exclusions are currently positive location targets",
                details={"conflicts": conflicts},
            )
        return actions, skipped

    def _plan_location_exclusions(
        self,
        *,
        customer_id: str,
        selector: CampaignSelector,
        locations: list[LocationInput],
        control: ExecutionControl,
        request_payload: dict[str, Any],
        request_fingerprint: str,
    ) -> ActionPlan | ActionResult:
        account, matches, resolved, criteria, source_hashes = self._read_source_state(
            customer_id,
            selector,
            locations,
        )
        if len(matches.matched) > control.max_campaigns:
            raise SafetyLimitError(
                "selector matched more campaigns than max_campaigns",
                details={
                    "matched_campaigns": len(matches.matched),
                    "max_campaigns": control.max_campaigns,
                },
            )

        actions, skipped = self._build_location_actions(matches, resolved, criteria)
        if len(actions) > control.max_operations:
            raise SafetyLimitError(
                "planned changes exceed max_operations",
                details={
                    "planned_operations": len(actions),
                    "max_operations": control.max_operations,
                },
            )
        if not actions:
            return ActionResult(
                status=ResultStatus.NOOP,
                skipped=skipped,
                verification_passed=True,
                message=(
                    "No matching campaigns were found."
                    if not matches.matched
                    else "All requested locations are already excluded."
                ),
            )

        validation = self.gateway.mutate_location_exclusions(
            customer_id,
            actions,
            validate_only=True,
            partial_failure=control.partial_failure,
        )
        if validation.errors:
            raise GoogleAdsRequestError(
                "Google Ads rejected the planned location exclusions",
                details={
                    "request_ids": validation.request_ids,
                    "errors": [
                        error.model_dump(mode="json") for error in validation.errors
                    ],
                },
            )

        created_at = utc_now()
        plan_id = f"plan_{uuid.uuid4().hex}"
        normalized_request = {
            "request": request_payload,
            "execution_policy": {
                "partial_failure": control.partial_failure,
                "max_campaigns": control.max_campaigns,
                "max_operations": control.max_operations,
            },
        }
        plan = ActionPlan(
            plan_id=plan_id,
            tool_name=TOOL_EXCLUDE_LOCATIONS,
            tool_version=__version__,
            customer_id=customer_id,
            currency_code=account.currency_code,
            time_zone=account.time_zone,
            normalized_request=normalized_request,
            matched_campaigns=matches.matched,
            actions=actions,
            skipped=skipped,
            warnings=[
                (
                    "This creates negative LocationInfo criteria. Google Ads does not "
                    "support negative proximity/radius criteria."
                )
            ],
            risk_level=RiskLevel.MEDIUM,
            validation=validation,
            source_state_hashes=source_hashes,
            request_fingerprint=request_fingerprint,
            plan_hash="",
            created_at=created_at,
            expires_at=created_at + timedelta(seconds=control.plan_ttl_seconds),
        )
        plan_hash = stable_hash(
            action_plan_hash_payload(plan.model_dump(mode="json"))
        )
        plan = plan.model_copy(update={"plan_hash": plan_hash})
        return self.plan_store.save_plan(
            plan,
            idempotency_key=control.idempotency_key,
        )

    def _execute_location_exclusions(
        self,
        *,
        customer_id: str,
        selector: CampaignSelector,
        locations: list[LocationInput],
        control: ExecutionControl,
        request_fingerprint: str,
    ) -> ActionResult:
        assert control.plan_id is not None  # Enforced by ExecutionControl.
        preview = self.plan_store.get_plan(control.plan_id)
        if preview.tool_name != TOOL_EXCLUDE_LOCATIONS:
            raise PlanInputMismatchError(
                "plan belongs to a different tool",
                details={"plan_tool": preview.tool_name},
            )
        if preview.customer_id != customer_id:
            raise PlanInputMismatchError(
                "customer_id does not match the approved plan",
                details={"plan_customer_id": preview.customer_id},
            )
        if preview.request_fingerprint != request_fingerprint:
            raise PlanInputMismatchError(
                "selector or locations do not match the approved plan",
                details={"plan_id": preview.plan_id},
            )

        plan, existing_result = self.plan_store.claim_execution(control.plan_id)
        if existing_result is not None:
            return existing_result

        try:
            _, _, _, _, current_hashes = self._read_source_state(
                customer_id,
                selector,
                locations,
            )
            if current_hashes != plan.source_state_hashes:
                changed_keys = sorted(
                    key
                    for key in set(current_hashes).union(plan.source_state_hashes)
                    if current_hashes.get(key) != plan.source_state_hashes.get(key)
                )
                result = ActionResult(
                    status=ResultStatus.STALE_PLAN,
                    plan_id=plan.plan_id,
                    message="Account state changed after planning; no operations executed.",
                    errors=[
                        MutationError(
                            code="STALE_PLAN",
                            message="source state changed",
                            field_path=", ".join(changed_keys),
                        )
                    ],
                )
                journal_id = self.plan_store.add_audit_event(
                    plan.plan_id,
                    "STALE_PLAN_DETECTED",
                    {"changed_state_keys": changed_keys},
                )
                result = result.model_copy(update={"audit_journal_id": journal_id})
                self.plan_store.finish_execution(
                    plan.plan_id,
                    result,
                    status=StoredPlanStatus.STALE,
                )
                return result

            partial_failure = bool(
                plan.normalized_request["execution_policy"]["partial_failure"]
            )
            receipt = self.gateway.mutate_location_exclusions(
                customer_id,
                plan.actions,
                validate_only=False,
                partial_failure=partial_failure,
            )
            failed_indexes = {
                error.operation_index
                for error in receipt.errors
                if error.operation_index is not None
            }
            if receipt.errors and not partial_failure:
                successful_actions: list[PlannedAction] = []
            elif any(error.operation_index is None for error in receipt.errors):
                successful_actions = []
            else:
                successful_actions = [
                    action
                    for index, action in enumerate(plan.actions)
                    if index not in failed_indexes
                ]

            verification_passed = self._verify_location_exclusions(
                customer_id,
                successful_actions,
            )
            if receipt.errors:
                result_status = (
                    ResultStatus.PARTIAL if successful_actions else ResultStatus.FAILED
                )
                stored_status = (
                    StoredPlanStatus.PARTIAL
                    if successful_actions
                    else StoredPlanStatus.FAILED
                )
            elif verification_passed:
                result_status = ResultStatus.EXECUTED
                stored_status = StoredPlanStatus.EXECUTED
            else:
                result_status = ResultStatus.FAILED
                stored_status = StoredPlanStatus.FAILED

            result = ActionResult(
                status=result_status,
                plan_id=plan.plan_id,
                executed_actions=successful_actions,
                request_ids=receipt.request_ids,
                errors=receipt.errors,
                verification_passed=verification_passed,
                message=(
                    "Approved location exclusions executed and verified."
                    if result_status == ResultStatus.EXECUTED
                    else "Execution did not fully complete; inspect errors and verification."
                ),
                rollback_available=bool(successful_actions),
            )
            journal_id = self.plan_store.add_audit_event(
                plan.plan_id,
                "EXECUTION_RESULT",
                result.model_dump(mode="json"),
            )
            result = result.model_copy(update={"audit_journal_id": journal_id})
            self.plan_store.finish_execution(
                plan.plan_id,
                result,
                status=stored_status,
            )
            return result
        except Exception as exc:
            result = ActionResult(
                status=ResultStatus.FAILED,
                plan_id=plan.plan_id,
                message="Execution failed before verification completed.",
                errors=[
                    MutationError(
                        code=getattr(exc, "code", type(exc).__name__),
                        message=str(exc),
                    )
                ],
            )
            journal_id = self.plan_store.add_audit_event(
                plan.plan_id,
                "EXECUTION_EXCEPTION",
                {"error": str(exc), "error_type": type(exc).__name__},
            )
            result = result.model_copy(update={"audit_journal_id": journal_id})
            self.plan_store.finish_execution(
                plan.plan_id,
                result,
                status=StoredPlanStatus.FAILED,
            )
            return result

    def _verify_location_exclusions(
        self,
        customer_id: str,
        actions: list[PlannedAction],
    ) -> bool:
        if not actions:
            return False
        campaign_ids = sorted({action.campaign_id for action in actions})
        criteria = self.gateway.list_location_criteria(customer_id, campaign_ids)
        actual = {
            (criterion.campaign_id, criterion.geo_target_constant)
            for criterion in criteria
            if criterion.criterion_type == "LOCATION" and criterion.negative
        }
        expected = {
            (action.campaign_id, action.geo_target_constant)
            for action in actions
        }
        return expected.issubset(actual)
