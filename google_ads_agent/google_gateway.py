"""Production gateway implemented with Google's official Python client."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Any

from google_ads_agent.config import AgentConfig
from google_ads_agent.errors import (
    GoogleAdsDependencyError,
    GoogleAdsRequestError,
    UnsupportedSelectorError,
)
from google_ads_agent.models import (
    AccountContext,
    CampaignConversionGoalRecord,
    CampaignCtaSummary,
    CampaignHealthRecord,
    CampaignPerformanceRecord,
    CampaignRecord,
    CityPerformanceRecord,
    ConversionActionRecord,
    CtaMatchScope,
    CtaSource,
    CtaStatus,
    CustomerConversionGoalRecord,
    DateWindow,
    GeoCandidate,
    LocationCriterion,
    LocationInput,
    MutationError,
    MutationReceipt,
    PerformanceMetrics,
    PlannedAction,
)


def _enum_name(enum_type: Any, value: Any) -> str:
    if hasattr(value, "name"):
        return str(value.name)
    try:
        return str(enum_type(value).name)
    except (TypeError, ValueError):
        return str(value)


class GoogleAdsApiGateway:
    """Thin translation layer; business rules live outside this class."""

    def __init__(self, client: Any, *, api_version: str = "v25") -> None:
        self.client = client
        self.api_version = api_version

    @classmethod
    def from_config(cls, config: AgentConfig) -> GoogleAdsApiGateway:
        try:
            from google.ads.googleads.client import GoogleAdsClient
        except ImportError as exc:
            raise GoogleAdsDependencyError(
                "install the project dependencies to use the live Google Ads gateway"
            ) from exc

        if config.google_ads_yaml_path is not None:
            client = GoogleAdsClient.load_from_storage(
                str(config.google_ads_yaml_path),
                version=config.api_version,
            )
        else:
            client = GoogleAdsClient.load_from_env(version=config.api_version)
        return cls(client, api_version=config.api_version)

    def _search(self, customer_id: str, query: str) -> Iterable[Any]:
        service = self.client.get_service(
            "GoogleAdsService",
            version=self.api_version,
        )
        try:
            response = service.search_stream(customer_id=customer_id, query=query)
            for batch in response:
                yield from batch.results
        except Exception as exc:
            self._raise_request_error(exc)

    def _raise_request_error(self, exc: Exception) -> None:
        request_id = getattr(exc, "request_id", None)
        failure = getattr(exc, "failure", None)
        errors = self._parse_failure(failure) if failure is not None else []
        raise GoogleAdsRequestError(
            str(exc),
            details={
                "request_id": request_id,
                "errors": [error.model_dump(mode="json") for error in errors],
            },
        ) from exc

    def _parse_failure(self, failure: Any) -> list[MutationError]:
        parsed: list[MutationError] = []
        for error in getattr(failure, "errors", []):
            operation_index: int | None = None
            path_parts: list[str] = []
            for element in getattr(getattr(error, "location", None), "field_path_elements", []):
                field_name = getattr(element, "field_name", "")
                index = getattr(element, "index", None)
                if field_name:
                    path_parts.append(
                        f"{field_name}[{index}]" if index is not None else field_name
                    )
                if field_name == "operations" and index is not None:
                    operation_index = int(index)

            error_code = getattr(error, "error_code", None)
            code = "GOOGLE_ADS_ERROR"
            if error_code is not None:
                underlying = getattr(error_code, "_pb", None)
                if underlying is not None:
                    selected = underlying.WhichOneof("error_code")
                    if selected:
                        code_value = getattr(error_code, selected)
                        code = f"{selected}.{getattr(code_value, 'name', code_value)}"

            parsed.append(
                MutationError(
                    operation_index=operation_index,
                    code=code,
                    message=getattr(error, "message", str(error)),
                    field_path=".".join(path_parts) or None,
                )
            )
        return parsed

    def _parse_partial_failure(self, status: Any) -> list[MutationError]:
        if not status or getattr(status, "code", 0) == 0:
            return []
        try:
            failure_type = self.client.get_type(
                "GoogleAdsFailure",
                version=self.api_version,
            )
            errors: list[MutationError] = []
            for detail in status.details:
                failure = failure_type.deserialize(detail.value)
                errors.extend(self._parse_failure(failure))
            return errors
        except Exception:
            return [
                MutationError(
                    code=f"RPC_STATUS_{getattr(status, 'code', 'UNKNOWN')}",
                    message=getattr(status, "message", "partial failure"),
                )
            ]

    def get_account_context(self, customer_id: str) -> AccountContext:
        query = """
            SELECT
              customer.id,
              customer.descriptive_name,
              customer.currency_code,
              customer.time_zone,
              customer.status,
              customer.test_account,
              customer.manager
            FROM customer
            LIMIT 1
        """
        rows = list(self._search(customer_id, query))
        if not rows:
            raise GoogleAdsRequestError("customer query returned no rows")
        customer = rows[0].customer
        return AccountContext(
            customer_id=str(customer.id),
            descriptive_name=customer.descriptive_name or None,
            currency_code=customer.currency_code,
            time_zone=customer.time_zone,
            status=_enum_name(self.client.enums.CustomerStatusEnum, customer.status),
            test_account=customer.test_account,
            manager=customer.manager,
            api_version=self.api_version,
        )

    def list_conversion_actions(
        self,
        customer_id: str,
    ) -> list[ConversionActionRecord]:
        query = """
            SELECT
              conversion_action.resource_name,
              conversion_action.id,
              conversion_action.name,
              conversion_action.status,
              conversion_action.type,
              conversion_action.category,
              conversion_action.origin,
              conversion_action.primary_for_goal
            FROM conversion_action
        """
        records: list[ConversionActionRecord] = []
        for row in self._search(customer_id, query):
            action = row.conversion_action
            records.append(
                ConversionActionRecord(
                    resource_name=action.resource_name,
                    id=str(action.id),
                    name=action.name,
                    status=_enum_name(
                        self.client.enums.ConversionActionStatusEnum,
                        action.status,
                    ),
                    type=_enum_name(
                        self.client.enums.ConversionActionTypeEnum,
                        action.type_,
                    ),
                    category=_enum_name(
                        self.client.enums.ConversionActionCategoryEnum,
                        action.category,
                    ),
                    origin=_enum_name(
                        self.client.enums.ConversionOriginEnum,
                        action.origin,
                    ),
                    primary_for_goal=action.primary_for_goal,
                )
            )
        return records

    def list_customer_conversion_goals(
        self,
        customer_id: str,
    ) -> list[CustomerConversionGoalRecord]:
        query = """
            SELECT
              customer_conversion_goal.resource_name,
              customer_conversion_goal.category,
              customer_conversion_goal.origin,
              customer_conversion_goal.biddable
            FROM customer_conversion_goal
        """
        records: list[CustomerConversionGoalRecord] = []
        for row in self._search(customer_id, query):
            goal = row.customer_conversion_goal
            records.append(
                CustomerConversionGoalRecord(
                    resource_name=goal.resource_name,
                    category=_enum_name(
                        self.client.enums.ConversionActionCategoryEnum,
                        goal.category,
                    ),
                    origin=_enum_name(
                        self.client.enums.ConversionOriginEnum,
                        goal.origin,
                    ),
                    biddable=goal.biddable,
                )
            )
        return records

    def list_campaign_conversion_goals(
        self,
        customer_id: str,
    ) -> list[CampaignConversionGoalRecord]:
        config_query = """
            SELECT
              conversion_goal_campaign_config.campaign,
              conversion_goal_campaign_config.custom_conversion_goal,
              conversion_goal_campaign_config.goal_config_level,
              campaign.id
            FROM conversion_goal_campaign_config
        """
        configs: dict[str, tuple[str, str | None]] = {}
        for row in self._search(customer_id, config_query):
            config = row.conversion_goal_campaign_config
            configs[str(row.campaign.id)] = (
                _enum_name(
                    self.client.enums.GoalConfigLevelEnum,
                    config.goal_config_level,
                ),
                config.custom_conversion_goal or None,
            )

        goal_query = """
            SELECT
              campaign_conversion_goal.resource_name,
              campaign_conversion_goal.campaign,
              campaign_conversion_goal.category,
              campaign_conversion_goal.origin,
              campaign_conversion_goal.biddable,
              campaign.id,
              campaign.name
            FROM campaign_conversion_goal
            WHERE campaign.status != REMOVED
        """
        records: list[CampaignConversionGoalRecord] = []
        for row in self._search(customer_id, goal_query):
            goal = row.campaign_conversion_goal
            campaign_id = str(row.campaign.id)
            config_level, custom_goal = configs.get(
                campaign_id,
                ("CUSTOMER", None),
            )
            records.append(
                CampaignConversionGoalRecord(
                    resource_name=goal.resource_name,
                    campaign_id=campaign_id,
                    campaign_name=row.campaign.name,
                    category=_enum_name(
                        self.client.enums.ConversionActionCategoryEnum,
                        goal.category,
                    ),
                    origin=_enum_name(
                        self.client.enums.ConversionOriginEnum,
                        goal.origin,
                    ),
                    biddable=goal.biddable,
                    goal_config_level=config_level,
                    custom_conversion_goal=custom_goal,
                )
            )
        return records

    def list_campaign_health(
        self,
        customer_id: str,
    ) -> list[CampaignHealthRecord]:
        query = """
            SELECT
              campaign.id,
              campaign.name,
              campaign.status,
              campaign.primary_status,
              campaign.primary_status_reasons,
              campaign.bidding_strategy_type,
              campaign.bidding_strategy_system_status,
              campaign_budget.resource_name,
              campaign_budget.period,
              campaign_budget.amount_micros,
              campaign_budget.total_amount_micros,
              campaign_budget.explicitly_shared,
              campaign_budget.reference_count,
              campaign_budget.has_recommended_budget,
              campaign_budget.recommended_budget_amount_micros
            FROM campaign
            WHERE campaign.status != REMOVED
        """
        records: list[CampaignHealthRecord] = []
        for row in self._search(customer_id, query):
            campaign = row.campaign
            budget = row.campaign_budget
            period = _enum_name(self.client.enums.BudgetPeriodEnum, budget.period)
            amount = (
                budget.total_amount_micros
                if period == "CUSTOM_PERIOD"
                else budget.amount_micros
            )
            records.append(
                CampaignHealthRecord(
                    campaign_id=str(campaign.id),
                    campaign_name=campaign.name,
                    status=_enum_name(
                        self.client.enums.CampaignStatusEnum,
                        campaign.status,
                    ),
                    primary_status=_enum_name(
                        self.client.enums.CampaignPrimaryStatusEnum,
                        campaign.primary_status,
                    ),
                    primary_status_reasons=[
                        _enum_name(
                            self.client.enums.CampaignPrimaryStatusReasonEnum,
                            reason,
                        )
                        for reason in campaign.primary_status_reasons
                    ],
                    bidding_strategy_type=_enum_name(
                        self.client.enums.BiddingStrategyTypeEnum,
                        campaign.bidding_strategy_type,
                    ),
                    bidding_strategy_system_status=_enum_name(
                        self.client.enums.BiddingStrategySystemStatusEnum,
                        campaign.bidding_strategy_system_status,
                    ),
                    budget_resource_name=budget.resource_name or None,
                    budget_period=period,
                    budget_amount_micros=int(amount) if amount else 0,
                    budget_explicitly_shared=budget.explicitly_shared,
                    budget_reference_count=int(budget.reference_count),
                    has_recommended_budget=budget.has_recommended_budget,
                    recommended_budget_amount_micros=(
                        int(budget.recommended_budget_amount_micros)
                        if budget.has_recommended_budget
                        else None
                    ),
                )
            )
        return records

    @staticmethod
    def _performance_metrics(metrics: Any) -> PerformanceMetrics:
        return PerformanceMetrics(
            impressions=int(metrics.impressions),
            clicks=int(metrics.clicks),
            cost_micros=int(metrics.cost_micros),
            conversions=float(metrics.conversions),
            conversion_value=float(metrics.conversions_value),
        )

    def list_campaign_performance(
        self,
        customer_id: str,
        window: DateWindow,
    ) -> list[CampaignPerformanceRecord]:
        query = f"""
            SELECT
              campaign.id,
              campaign.name,
              metrics.impressions,
              metrics.clicks,
              metrics.cost_micros,
              metrics.conversions,
              metrics.conversions_value
            FROM campaign
            WHERE segments.date BETWEEN '{window.start_date.isoformat()}'
              AND '{window.end_date.isoformat()}'
              AND campaign.status != REMOVED
        """
        return [
            CampaignPerformanceRecord(
                campaign_id=str(row.campaign.id),
                campaign_name=row.campaign.name,
                metrics=self._performance_metrics(row.metrics),
            )
            for row in self._search(customer_id, query)
        ]

    def _geo_target_details(
        self,
        customer_id: str,
        resource_names: set[str],
    ) -> dict[str, Any]:
        safe_names = sorted(
            name
            for name in resource_names
            if re.fullmatch(r"geoTargetConstants/\d+", name)
        )
        details: dict[str, Any] = {}
        for offset in range(0, len(safe_names), 500):
            batch = safe_names[offset : offset + 500]
            if not batch:
                continue
            quoted = ", ".join(f"'{name}'" for name in batch)
            query = f"""
                SELECT
                  geo_target_constant.resource_name,
                  geo_target_constant.name,
                  geo_target_constant.canonical_name,
                  geo_target_constant.country_code,
                  geo_target_constant.target_type,
                  geo_target_constant.status
                FROM geo_target_constant
                WHERE geo_target_constant.resource_name IN ({quoted})
            """
            for row in self._search(customer_id, query):
                target = row.geo_target_constant
                details[target.resource_name] = target
        return details

    def list_city_performance(
        self,
        customer_id: str,
        campaign_ids: Sequence[str],
        window: DateWindow,
        *,
        only_targeted_locations: bool,
    ) -> list[CityPerformanceRecord]:
        if not campaign_ids:
            return []
        safe_ids = sorted({str(campaign_id) for campaign_id in campaign_ids})
        if any(not re.fullmatch(r"\d+", campaign_id) for campaign_id in safe_ids):
            raise ValueError("campaign IDs must contain digits only")
        ids = ", ".join(safe_ids)
        targeted_filter = (
            "AND user_location_view.targeting_location = TRUE"
            if only_targeted_locations
            else ""
        )
        query = f"""
            SELECT
              campaign.id,
              campaign.name,
              segments.geo_target_city,
              user_location_view.targeting_location,
              metrics.impressions,
              metrics.clicks,
              metrics.cost_micros,
              metrics.conversions,
              metrics.conversions_value
            FROM user_location_view
            WHERE segments.date BETWEEN '{window.start_date.isoformat()}'
              AND '{window.end_date.isoformat()}'
              AND campaign.id IN ({ids})
              {targeted_filter}
        """
        aggregates: dict[tuple[str, str, bool], CityPerformanceRecord] = {}
        raw_rows = list(self._search(customer_id, query))
        resource_names = {
            row.segments.geo_target_city
            for row in raw_rows
            if row.segments.geo_target_city
        }
        details = self._geo_target_details(customer_id, resource_names)
        for row in raw_rows:
            resource_name = row.segments.geo_target_city
            if not resource_name:
                continue
            target = details.get(resource_name)
            targeted = bool(row.user_location_view.targeting_location)
            key = (str(row.campaign.id), resource_name, targeted)
            metrics = self._performance_metrics(row.metrics)
            if key in aggregates:
                current = aggregates[key].metrics
                current.impressions += metrics.impressions
                current.clicks += metrics.clicks
                current.cost_micros += metrics.cost_micros
                current.conversions += metrics.conversions
                current.conversion_value += metrics.conversion_value
                continue
            aggregates[key] = CityPerformanceRecord(
                campaign_id=str(row.campaign.id),
                campaign_name=row.campaign.name,
                geo_target_constant=resource_name,
                location_name=target.name if target else resource_name,
                canonical_name=(
                    target.canonical_name if target else resource_name
                ),
                country_code=target.country_code if target else "",
                targeted_location=targeted,
                metrics=metrics,
            )
        return list(aggregates.values())

    def _label_names(self, customer_id: str) -> dict[str, str]:
        query = """
            SELECT
              label.resource_name,
              label.name
            FROM label
        """
        return {row.label.resource_name: row.label.name for row in self._search(customer_id, query)}

    def list_campaigns(
        self,
        customer_id: str,
        *,
        include_removed: bool,
    ) -> list[CampaignRecord]:
        where = "" if include_removed else "WHERE campaign.status != REMOVED"
        query = f"""
            SELECT
              campaign.id,
              campaign.resource_name,
              campaign.name,
              campaign.status,
              campaign.advertising_channel_type,
              campaign.advertising_channel_sub_type,
              campaign.experiment_type,
              campaign.base_campaign,
              campaign.labels,
              campaign.bidding_strategy_type,
              campaign_budget.id,
              campaign_budget.resource_name,
              campaign_budget.period,
              campaign_budget.amount_micros,
              campaign_budget.total_amount_micros,
              campaign_budget.explicitly_shared,
              campaign_budget.reference_count
            FROM campaign
            {where}
        """
        rows = list(self._search(customer_id, query))
        label_names = (
            self._label_names(customer_id)
            if any(row.campaign.labels for row in rows)
            else {}
        )
        campaigns: list[CampaignRecord] = []
        for row in rows:
            campaign = row.campaign
            budget = row.campaign_budget
            period = _enum_name(self.client.enums.BudgetPeriodEnum, budget.period)
            amount = (
                budget.total_amount_micros
                if period == "CUSTOM_PERIOD"
                else budget.amount_micros
            )
            campaigns.append(
                CampaignRecord(
                    id=str(campaign.id),
                    resource_name=campaign.resource_name,
                    name=campaign.name,
                    status=_enum_name(
                        self.client.enums.CampaignStatusEnum,
                        campaign.status,
                    ),
                    channel_type=_enum_name(
                        self.client.enums.AdvertisingChannelTypeEnum,
                        campaign.advertising_channel_type,
                    ),
                    channel_subtype=_enum_name(
                        self.client.enums.AdvertisingChannelSubTypeEnum,
                        campaign.advertising_channel_sub_type,
                    ),
                    experiment_type=_enum_name(
                        self.client.enums.CampaignExperimentTypeEnum,
                        campaign.experiment_type,
                    ),
                    base_campaign=campaign.base_campaign or None,
                    labels=sorted(
                        label_names.get(resource_name, resource_name)
                        for resource_name in campaign.labels
                    ),
                    bidding_strategy_type=_enum_name(
                        self.client.enums.BiddingStrategyTypeEnum,
                        campaign.bidding_strategy_type,
                    ),
                    budget_id=str(budget.id) if budget.id else None,
                    budget_resource_name=budget.resource_name or None,
                    budget_period=period,
                    budget_amount_micros=int(amount) if amount else 0,
                    budget_explicitly_shared=budget.explicitly_shared,
                    budget_reference_count=int(budget.reference_count),
                )
            )
        return campaigns

    def _cta_query_rows(
        self,
        customer_id: str,
        campaign_ids: Sequence[str],
        *,
        level: str,
    ) -> Iterable[Any]:
        ids = ", ".join(campaign_ids)
        if level == "CAMPAIGN":
            query = f"""
                SELECT
                  campaign.id,
                  campaign_asset.resource_name,
                  campaign_asset.status,
                  campaign_asset.primary_status,
                  asset.call_to_action_asset.call_to_action
                FROM campaign_asset
                WHERE campaign.id IN ({ids})
                  AND campaign_asset.field_type = CALL_TO_ACTION
                  AND campaign_asset.status = ENABLED
            """
        else:
            query = f"""
                SELECT
                  campaign.id,
                  ad_group_asset.resource_name,
                  ad_group_asset.status,
                  ad_group_asset.primary_status,
                  asset.call_to_action_asset.call_to_action
                FROM ad_group_asset
                WHERE campaign.id IN ({ids})
                  AND ad_group_asset.field_type = CALL_TO_ACTION
                  AND ad_group_asset.status = ENABLED
            """
        return self._search(customer_id, query)

    def get_campaign_ctas(
        self,
        customer_id: str,
        campaign_ids: Sequence[str],
        *,
        scope: CtaMatchScope,
    ) -> list[CampaignCtaSummary]:
        if scope in {CtaMatchScope.ANY_ACTIVE_AD, CtaMatchScope.ALL_ACTIVE_ADS}:
            raise UnsupportedSelectorError(
                "ad-level CTA scopes are not implemented",
                details={
                    "supported_scopes": [
                        CtaMatchScope.ANY_EXPLICIT_SOURCE.value,
                        CtaMatchScope.CAMPAIGN_ASSET_ONLY.value,
                    ]
                },
            )
        if not campaign_ids:
            return []

        sources_by_campaign: dict[str, list[CtaSource]] = defaultdict(list)
        levels = ["CAMPAIGN"]
        if scope == CtaMatchScope.ANY_EXPLICIT_SOURCE:
            levels.append("AD_GROUP")

        for level in levels:
            for row in self._cta_query_rows(customer_id, campaign_ids, level=level):
                link = row.campaign_asset if level == "CAMPAIGN" else row.ad_group_asset
                call_to_action = row.asset.call_to_action_asset.call_to_action
                value = _enum_name(
                    self.client.enums.CallToActionTypeEnum,
                    call_to_action,
                )
                if value in {"UNSPECIFIED", "UNKNOWN"}:
                    continue
                sources_by_campaign[str(row.campaign.id)].append(
                    CtaSource(
                        resource_name=link.resource_name,
                        level=level,
                        value=value,
                        status=_enum_name(
                            self.client.enums.AssetLinkStatusEnum,
                            link.status,
                        ),
                        primary_status=_enum_name(
                            self.client.enums.AssetLinkPrimaryStatusEnum,
                            link.primary_status,
                        ),
                    )
                )

        summaries: list[CampaignCtaSummary] = []
        for campaign_id in campaign_ids:
            sources = sources_by_campaign.get(str(campaign_id), [])
            values = sorted({source.value for source in sources})
            status = (
                CtaStatus.UNKNOWN
                if not values
                else CtaStatus.EXPLICIT
                if len(values) == 1
                else CtaStatus.MULTIPLE
            )
            summaries.append(
                CampaignCtaSummary(
                    campaign_id=str(campaign_id),
                    status=status,
                    values=values,
                    sources=sources,
                )
            )
        return summaries

    def suggest_geo_targets(
        self,
        customer_id: str,
        location: LocationInput,
    ) -> list[GeoCandidate]:
        del customer_id  # Geo target constants are global; kept for a uniform boundary.
        service = self.client.get_service(
            "GeoTargetConstantService",
            version=self.api_version,
        )
        request = self.client.get_type(
            "SuggestGeoTargetConstantsRequest",
            version=self.api_version,
        )
        request.locale = location.locale
        request.country_code = location.country_code
        request.location_names.names.append(location.name)
        try:
            response = service.suggest_geo_target_constants(request=request)
        except Exception as exc:
            self._raise_request_error(exc)

        candidates: list[GeoCandidate] = []
        for suggestion in response.geo_target_constant_suggestions:
            target = suggestion.geo_target_constant
            candidates.append(
                GeoCandidate(
                    resource_name=target.resource_name,
                    criterion_id=str(target.id),
                    name=target.name,
                    canonical_name=target.canonical_name,
                    country_code=target.country_code,
                    target_type=target.target_type,
                    status=_enum_name(
                        self.client.enums.GeoTargetConstantStatusEnum,
                        target.status,
                    ),
                    reach=int(suggestion.reach) if suggestion.reach else None,
                )
            )
        return candidates

    def list_location_criteria(
        self,
        customer_id: str,
        campaign_ids: Sequence[str],
    ) -> list[LocationCriterion]:
        if not campaign_ids:
            return []
        ids = ", ".join(campaign_ids)
        query = f"""
            SELECT
              campaign.id,
              campaign_criterion.resource_name,
              campaign_criterion.type,
              campaign_criterion.negative,
              campaign_criterion.location.geo_target_constant
            FROM campaign_criterion
            WHERE campaign.id IN ({ids})
              AND campaign_criterion.type IN (LOCATION, PROXIMITY)
              AND campaign_criterion.status != REMOVED
        """
        criteria: list[LocationCriterion] = []
        for row in self._search(customer_id, query):
            criterion = row.campaign_criterion
            criterion_type = _enum_name(
                self.client.enums.CriterionTypeEnum,
                criterion.type_,
            )
            criteria.append(
                LocationCriterion(
                    resource_name=criterion.resource_name,
                    campaign_id=str(row.campaign.id),
                    criterion_type=criterion_type,
                    negative=criterion.negative,
                    geo_target_constant=(
                        criterion.location.geo_target_constant
                        if criterion_type == "LOCATION"
                        else None
                    ),
                )
            )
        return criteria

    def mutate_location_exclusions(
        self,
        customer_id: str,
        actions: Sequence[PlannedAction],
        *,
        validate_only: bool,
        partial_failure: bool,
    ) -> MutationReceipt:
        service = self.client.get_service(
            "CampaignCriterionService",
            version=self.api_version,
        )
        request = self.client.get_type(
            "MutateCampaignCriteriaRequest",
            version=self.api_version,
        )
        request.customer_id = customer_id
        request.validate_only = validate_only
        request.partial_failure = partial_failure

        for action in actions:
            operation = self.client.get_type(
                "CampaignCriterionOperation",
                version=self.api_version,
            )
            operation.create.campaign = action.campaign_resource_name
            operation.create.negative = True
            operation.create.location.geo_target_constant = action.geo_target_constant
            request.operations.append(operation)

        try:
            response = service.mutate_campaign_criteria(request=request)
        except Exception as exc:
            request_id = getattr(exc, "request_id", None)
            failure = getattr(exc, "failure", None)
            errors = self._parse_failure(failure) if failure is not None else [
                MutationError(code="GOOGLE_ADS_REQUEST_FAILED", message=str(exc))
            ]
            return MutationReceipt(
                validated_only=validate_only,
                request_ids=[request_id] if request_id else [],
                errors=errors,
            )

        errors = self._parse_partial_failure(response.partial_failure_error)
        return MutationReceipt(
            validated_only=validate_only,
            resource_names=[
                result.resource_name
                for result in response.results
                if result.resource_name
            ],
            errors=errors,
        )
