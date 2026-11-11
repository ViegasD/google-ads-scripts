"""Typed request, domain, plan, and result models."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=False)


class TextOperator(StrEnum):
    EXACT = "EXACT"
    CONTAINS = "CONTAINS"
    STARTS_WITH = "STARTS_WITH"
    REGEX = "REGEX"


class ComparisonOperator(StrEnum):
    EQUALS = "EQUALS"
    GREATER_THAN = "GREATER_THAN"
    GREATER_THAN_OR_EQUAL = "GREATER_THAN_OR_EQUAL"
    LESS_THAN = "LESS_THAN"
    LESS_THAN_OR_EQUAL = "LESS_THAN_OR_EQUAL"


class BudgetPeriod(StrEnum):
    DAILY = "DAILY"
    CUSTOM_PERIOD = "CUSTOM_PERIOD"


class CtaMatchScope(StrEnum):
    ANY_EXPLICIT_SOURCE = "ANY_EXPLICIT_SOURCE"
    CAMPAIGN_ASSET_ONLY = "CAMPAIGN_ASSET_ONLY"
    ANY_ACTIVE_AD = "ANY_ACTIVE_AD"
    ALL_ACTIVE_ADS = "ALL_ACTIVE_ADS"


class CtaStatus(StrEnum):
    EXPLICIT = "EXPLICIT"
    AUTO = "AUTO"
    MULTIPLE = "MULTIPLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"


class ExecutionMode(StrEnum):
    PLAN = "PLAN"
    EXECUTE = "EXECUTE"


class ResultStatus(StrEnum):
    NOOP = "NOOP"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    EXECUTED = "EXECUTED"
    PARTIAL = "PARTIAL"
    STALE_PLAN = "STALE_PLAN"
    FAILED = "FAILED"


class StoredPlanStatus(StrEnum):
    VALIDATED = "VALIDATED"
    EXECUTING = "EXECUTING"
    EXECUTED = "EXECUTED"
    PARTIAL = "PARTIAL"
    STALE = "STALE"
    FAILED = "FAILED"


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class IssueSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class MeasurementReadiness(StrEnum):
    READY = "READY"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"


class PerformanceObjective(StrEnum):
    CPA = "CPA"
    ROAS = "ROAS"


class LocationAssessmentStatus(StrEnum):
    EXCLUSION_CANDIDATE = "EXCLUSION_CANDIDATE"
    HEALTHY = "HEALTHY"
    WATCH = "WATCH"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    PROTECTED = "PROTECTED"


class TextCondition(StrictModel):
    operator: TextOperator = TextOperator.EXACT
    value: str = Field(min_length=1, max_length=255)
    case_sensitive: bool = False

    @field_validator("value")
    @classmethod
    def validate_regex(cls, value: str, info: Any) -> str:
        if info.data.get("operator") == TextOperator.REGEX:
            try:
                re.compile(value)
            except re.error as exc:
                raise ValueError(f"invalid regular expression: {exc}") from exc
        return value


class BudgetCondition(StrictModel):
    period: BudgetPeriod
    amount: Decimal = Field(gt=0)
    currency_code: str = Field(min_length=3, max_length=3)
    operator: ComparisonOperator = ComparisonOperator.EQUALS
    tolerance: Decimal = Field(default=Decimal("0.00"), ge=0)

    @field_validator("currency_code")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        if not value.isalpha():
            raise ValueError("currency_code must contain three letters")
        return value.upper()


class CtaCondition(StrictModel):
    values: list[str] = Field(min_length=1)
    match_scope: CtaMatchScope = CtaMatchScope.ANY_EXPLICIT_SOURCE

    @field_validator("values")
    @classmethod
    def normalize_values(cls, values: list[str]) -> list[str]:
        normalized = sorted({value.strip().upper() for value in values if value.strip()})
        if not normalized:
            raise ValueError("at least one non-empty CTA value is required")
        return normalized


class CampaignSelector(StrictModel):
    campaign_ids: list[str] | None = None
    name: TextCondition | None = None
    statuses: list[str] | None = None
    channel_types: list[str] | None = None
    channel_subtypes: list[str] | None = None
    labels: list[str] | None = None
    budget: BudgetCondition | None = None
    cta: CtaCondition | None = None
    bidding_strategy_types: list[str] | None = None
    include_experiments: bool = False
    include_removed: bool = False
    allow_multiple: bool = False

    @field_validator("campaign_ids")
    @classmethod
    def normalize_campaign_ids(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        normalized = []
        for value in values:
            campaign_id = value.replace("-", "").strip()
            if not campaign_id.isdigit():
                raise ValueError(f"invalid campaign ID: {value!r}")
            normalized.append(campaign_id)
        return sorted(set(normalized))

    @field_validator(
        "statuses",
        "channel_types",
        "channel_subtypes",
        "labels",
        "bidding_strategy_types",
    )
    @classmethod
    def normalize_string_lists(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        normalized = sorted({value.strip().upper() for value in values if value.strip()})
        return normalized or None

    @model_validator(mode="after")
    def require_a_filter(self) -> CampaignSelector:
        fields = (
            self.campaign_ids,
            self.name,
            self.statuses,
            self.channel_types,
            self.channel_subtypes,
            self.labels,
            self.budget,
            self.cta,
            self.bidding_strategy_types,
        )
        if not any(value is not None for value in fields):
            raise ValueError("at least one campaign filter is required")
        return self


class ExecutionControl(StrictModel):
    mode: ExecutionMode
    plan_id: str | None = None
    confirmation: Literal["APPROVE"] | None = None
    max_campaigns: int = Field(default=10, ge=1, le=1_000)
    max_operations: int = Field(default=100, ge=1, le=10_000)
    partial_failure: bool = False
    plan_ttl_seconds: int = Field(default=900, ge=60, le=86_400)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=255)

    @model_validator(mode="after")
    def validate_mode_fields(self) -> ExecutionControl:
        if self.mode == ExecutionMode.EXECUTE:
            if not self.plan_id or self.confirmation != "APPROVE":
                raise ValueError("EXECUTE requires plan_id and confirmation='APPROVE'")
        elif self.plan_id is not None or self.confirmation is not None:
            raise ValueError("PLAN must not include plan_id or confirmation")
        return self


class LocationInput(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    country_code: str = Field(min_length=2, max_length=2)
    target_type: str | None = None
    locale: str = Field(default="en", min_length=2, max_length=10)

    @field_validator("country_code")
    @classmethod
    def normalize_country_code(cls, value: str) -> str:
        if not value.isalpha():
            raise ValueError("country_code must contain two letters")
        return value.upper()

    @field_validator("target_type")
    @classmethod
    def normalize_target_type(cls, value: str | None) -> str | None:
        return value.strip().casefold() if value else None


class AccountContext(StrictModel):
    customer_id: str
    descriptive_name: str | None = None
    currency_code: str
    time_zone: str
    status: str
    test_account: bool = False
    manager: bool = False
    api_version: str


class CtaSource(StrictModel):
    resource_name: str
    level: Literal["CAMPAIGN", "AD_GROUP", "AD"]
    value: str
    status: str
    primary_status: str | None = None


class CampaignCtaSummary(StrictModel):
    campaign_id: str
    status: CtaStatus
    values: list[str] = Field(default_factory=list)
    sources: list[CtaSource] = Field(default_factory=list)


class CampaignRecord(StrictModel):
    id: str
    resource_name: str
    name: str
    status: str
    channel_type: str
    channel_subtype: str | None = None
    experiment_type: str | None = None
    base_campaign: str | None = None
    labels: list[str] = Field(default_factory=list)
    bidding_strategy_type: str | None = None
    budget_id: str | None = None
    budget_resource_name: str | None = None
    budget_period: str | None = None
    budget_amount_micros: int | None = None
    budget_explicitly_shared: bool | None = None
    budget_reference_count: int | None = None
    cta: CampaignCtaSummary | None = None


class CampaignMatch(StrictModel):
    campaign: CampaignRecord
    reasons: list[str]


class CampaignMatchResult(StrictModel):
    customer_id: str
    matched: list[CampaignMatch]
    skipped: list[dict[str, Any]] = Field(default_factory=list)


class GeoCandidate(StrictModel):
    resource_name: str
    criterion_id: str
    name: str
    canonical_name: str
    country_code: str
    target_type: str
    status: str
    reach: int | None = None


class ResolvedLocation(StrictModel):
    requested: LocationInput
    target: GeoCandidate


class LocationCriterion(StrictModel):
    resource_name: str
    campaign_id: str
    criterion_type: Literal["LOCATION", "PROXIMITY"]
    negative: bool
    geo_target_constant: str | None = None


class DateWindow(StrictModel):
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def validate_order(self) -> DateWindow:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if (self.end_date - self.start_date).days > 366:
            raise ValueError("date window cannot exceed 367 days")
        return self


class PerformanceMetrics(StrictModel):
    impressions: int = Field(default=0, ge=0)
    clicks: int = Field(default=0, ge=0)
    cost_micros: int = Field(default=0, ge=0)
    conversions: float = Field(default=0, ge=0)
    conversion_value: float = Field(default=0, ge=0)


class ConversionActionRecord(StrictModel):
    resource_name: str
    id: str
    name: str
    status: str
    type: str
    category: str
    origin: str
    primary_for_goal: bool


class CustomerConversionGoalRecord(StrictModel):
    resource_name: str
    category: str
    origin: str
    biddable: bool


class CampaignConversionGoalRecord(StrictModel):
    resource_name: str
    campaign_id: str
    campaign_name: str
    category: str
    origin: str
    biddable: bool
    goal_config_level: str
    custom_conversion_goal: str | None = None


class MeasurementIssue(StrictModel):
    severity: IssueSeverity
    code: str
    scope: Literal["ACCOUNT", "CAMPAIGN", "CONVERSION_ACTION"]
    resource_name: str | None = None
    campaign_id: str | None = None
    message: str
    recommendation: str


class MeasurementAuditResult(StrictModel):
    customer_id: str
    readiness: MeasurementReadiness
    conversion_actions: list[ConversionActionRecord]
    customer_goals: list[CustomerConversionGoalRecord]
    campaign_goals: list[CampaignConversionGoalRecord]
    issues: list[MeasurementIssue]
    summary: dict[str, int]
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CampaignHealthRecord(StrictModel):
    campaign_id: str
    campaign_name: str
    status: str
    primary_status: str
    primary_status_reasons: list[str] = Field(default_factory=list)
    bidding_strategy_type: str | None = None
    bidding_strategy_system_status: str | None = None
    budget_resource_name: str | None = None
    budget_period: str | None = None
    budget_amount_micros: int | None = None
    budget_explicitly_shared: bool = False
    budget_reference_count: int = 0
    has_recommended_budget: bool = False
    recommended_budget_amount_micros: int | None = None


class CampaignPerformanceRecord(StrictModel):
    campaign_id: str
    campaign_name: str
    metrics: PerformanceMetrics


class DailyBriefPolicy(StrictModel):
    as_of_date: date | None = None
    lookback_days: int = Field(default=7, ge=1, le=90)
    exclude_recent_days: int = Field(default=3, ge=0, le=30)
    spend_change_alert_percent: Decimal = Field(default=Decimal("50"), gt=0)
    conversion_drop_alert_percent: Decimal = Field(default=Decimal("50"), gt=0, le=100)
    minimum_previous_cost: Decimal = Field(default=Decimal("25"), ge=0)
    minimum_previous_conversions: float = Field(default=3, ge=0)
    zero_conversion_cost_threshold: Decimal | None = Field(default=None, gt=0)
    max_items: int = Field(default=100, ge=1, le=1_000)


class DailyBriefItem(StrictModel):
    severity: IssueSeverity
    category: Literal["MEASUREMENT", "SERVING", "BUDGET", "PERFORMANCE"]
    code: str
    campaign_id: str | None = None
    campaign_name: str | None = None
    title: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    recommendation: str


class DailyAccountBrief(StrictModel):
    customer_id: str
    currency_code: str
    time_zone: str
    analysis_window: DateWindow
    comparison_window: DateWindow
    measurement_readiness: MeasurementReadiness
    items: list[DailyBriefItem]
    summary: dict[str, int | float | str]
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LocationPerformancePolicy(StrictModel):
    objective: PerformanceObjective
    target_cpa: Decimal | None = Field(default=None, gt=0)
    target_roas: Decimal | None = Field(default=None, gt=0)
    as_of_date: date | None = None
    lookback_days: int = Field(default=60, ge=7, le=365)
    exclude_recent_days: int = Field(default=3, ge=0, le=30)
    minimum_clicks: int = Field(default=20, ge=0)
    minimum_cost: Decimal = Field(default=Decimal("0"), ge=0)
    minimum_conversions_for_relative_rule: float = Field(default=3, ge=0)
    zero_conversion_target_multiplier: Decimal = Field(default=Decimal("2.5"), gt=0)
    cpa_target_multiplier: Decimal = Field(default=Decimal("1.5"), gt=1)
    roas_target_multiplier: Decimal = Field(default=Decimal("0.70"), gt=0, lt=1)
    protected_geo_target_constants: list[str] = Field(default_factory=list)
    protected_location_names: list[str] = Field(default_factory=list)
    only_targeted_locations: bool = True
    max_candidates: int = Field(default=20, ge=1, le=500)

    @model_validator(mode="after")
    def validate_objective_target(self) -> LocationPerformancePolicy:
        if self.objective == PerformanceObjective.CPA and self.target_cpa is None:
            raise ValueError("target_cpa is required when objective=CPA")
        if self.objective == PerformanceObjective.ROAS and self.target_roas is None:
            raise ValueError("target_roas is required when objective=ROAS")
        self.protected_geo_target_constants = sorted(
            set(self.protected_geo_target_constants)
        )
        self.protected_location_names = sorted(
            {name.strip().casefold() for name in self.protected_location_names if name.strip()}
        )
        return self


class CityPerformanceRecord(StrictModel):
    campaign_id: str
    campaign_name: str
    geo_target_constant: str
    location_name: str
    canonical_name: str
    country_code: str
    targeted_location: bool
    metrics: PerformanceMetrics


class CityPerformanceAssessment(StrictModel):
    campaign_id: str
    campaign_name: str
    geo_target_constant: str
    location_name: str
    canonical_name: str
    country_code: str
    targeted_location: bool
    metrics: PerformanceMetrics
    cost: Decimal
    cpa: Decimal | None = None
    roas: Decimal | None = None
    campaign_baseline_cpa: Decimal | None = None
    campaign_baseline_roas: Decimal | None = None
    status: LocationAssessmentStatus
    reasons: list[str]


class LocationPerformanceReport(StrictModel):
    customer_id: str
    currency_code: str
    time_zone: str
    data_source: Literal["USER_PHYSICAL_LOCATION"] = "USER_PHYSICAL_LOCATION"
    window: DateWindow
    objective: PerformanceObjective
    assessments: list[CityPerformanceAssessment]
    candidates: list[CityPerformanceAssessment]
    summary: dict[str, int | float | str]
    warnings: list[str]
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PlannedAction(StrictModel):
    action_id: str
    action_type: Literal["CREATE_LOCATION_EXCLUSION"]
    campaign_id: str
    campaign_name: str
    campaign_resource_name: str
    geo_target_constant: str
    location_name: str
    before: str
    after: str
    reason: str


class MutationError(StrictModel):
    operation_index: int | None = None
    code: str
    message: str
    field_path: str | None = None


class MutationReceipt(StrictModel):
    validated_only: bool
    resource_names: list[str] = Field(default_factory=list)
    request_ids: list[str] = Field(default_factory=list)
    errors: list[MutationError] = Field(default_factory=list)


class ActionPlan(StrictModel):
    status: Literal[ResultStatus.AWAITING_APPROVAL] = ResultStatus.AWAITING_APPROVAL
    plan_id: str
    tool_name: str
    tool_version: str
    customer_id: str
    currency_code: str
    time_zone: str
    normalized_request: dict[str, Any]
    matched_campaigns: list[CampaignMatch]
    actions: list[PlannedAction]
    skipped: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    risk_level: RiskLevel
    validation: MutationReceipt
    source_state_hashes: dict[str, str]
    request_fingerprint: str
    plan_hash: str
    created_at: datetime
    expires_at: datetime
    approval_required: bool = True

    @field_validator("created_at", "expires_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(UTC)


class ActionResult(StrictModel):
    status: ResultStatus
    plan_id: str | None = None
    executed_actions: list[PlannedAction] = Field(default_factory=list)
    skipped: list[dict[str, Any]] = Field(default_factory=list)
    request_ids: list[str] = Field(default_factory=list)
    errors: list[MutationError] = Field(default_factory=list)
    verification_passed: bool = False
    audit_journal_id: str | None = None
    message: str
    rollback_available: bool = False
    completed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
