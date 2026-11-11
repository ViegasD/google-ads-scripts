"""Read-only measurement, health, and performance decision reports."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from google_ads_agent.gateway import AdsGateway
from google_ads_agent.models import (
    AccountContext,
    CampaignHealthRecord,
    CampaignMatchResult,
    CampaignPerformanceRecord,
    CityPerformanceAssessment,
    DailyAccountBrief,
    DailyBriefItem,
    DailyBriefPolicy,
    DateWindow,
    IssueSeverity,
    LocationAssessmentStatus,
    LocationPerformancePolicy,
    LocationPerformanceReport,
    MeasurementAuditResult,
    MeasurementIssue,
    MeasurementReadiness,
    PerformanceMetrics,
    PerformanceObjective,
)
from google_ads_agent.utils import MICROS_PER_UNIT

_SEVERITY_ORDER = {
    IssueSeverity.CRITICAL: 0,
    IssueSeverity.WARNING: 1,
    IssueSeverity.INFO: 2,
}

_CRITICAL_CAMPAIGN_REASONS = {
    "BIDDING_STRATEGY_MISCONFIGURED",
    "BUDGET_MISCONFIGURED",
    "HAS_ADS_DISAPPROVED",
    "HAS_ASSET_GROUPS_DISAPPROVED",
    "MISSING_LOCATION_TARGETING",
    "NO_AD_GROUPS",
    "NO_AD_GROUP_ADS",
    "NO_ASSET_GROUPS",
    "NO_KEYWORDS",
}

_WARNING_CAMPAIGN_REASONS = {
    "BIDDING_STRATEGY_CONSTRAINED",
    "BIDDING_STRATEGY_LIMITED",
    "BUDGET_CONSTRAINED",
    "HAS_ADS_LIMITED_BY_POLICY",
    "HAS_ASSET_GROUPS_LIMITED_BY_POLICY",
    "SEARCH_VOLUME_LIMITED",
}

_EXPECTED_NON_SERVING_REASONS = {
    "CAMPAIGN_DRAFT",
    "CAMPAIGN_ENDED",
    "CAMPAIGN_PAUSED",
    "CAMPAIGN_PENDING",
    "CAMPAIGN_REMOVED",
}


def _account_local_today(account: AccountContext) -> date:
    try:
        zone = ZoneInfo(account.time_zone)
    except ZoneInfoNotFoundError:
        return datetime.now(UTC).date()
    return datetime.now(zone).date()


def reporting_window(
    account: AccountContext,
    *,
    as_of_date: date | None,
    lookback_days: int,
    exclude_recent_days: int,
) -> DateWindow:
    reference = as_of_date or _account_local_today(account)
    end_date = reference - timedelta(days=exclude_recent_days)
    start_date = end_date - timedelta(days=lookback_days - 1)
    return DateWindow(start_date=start_date, end_date=end_date)


def audit_measurement_and_goals(
    gateway: AdsGateway,
    account: AccountContext,
) -> MeasurementAuditResult:
    actions = gateway.list_conversion_actions(account.customer_id)
    customer_goals = gateway.list_customer_conversion_goals(account.customer_id)
    campaign_goals = gateway.list_campaign_conversion_goals(account.customer_id)
    issues: list[MeasurementIssue] = []

    active_actions = [action for action in actions if action.status != "REMOVED"]
    active_primary = [action for action in active_actions if action.primary_for_goal]
    if not active_actions:
        issues.append(
            MeasurementIssue(
                severity=IssueSeverity.CRITICAL,
                code="NO_ACTIVE_CONVERSION_ACTIONS",
                scope="ACCOUNT",
                message="The account has no active conversion actions.",
                recommendation="Configure and verify at least one business conversion action.",
            )
        )
    elif not active_primary:
        issues.append(
            MeasurementIssue(
                severity=IssueSeverity.CRITICAL,
                code="NO_PRIMARY_CONVERSION_ACTIONS",
                scope="ACCOUNT",
                message="No active conversion action is marked primary for goal optimization.",
                recommendation=(
                    "Choose the conversion actions that represent real business outcomes "
                    "and mark them primary."
                ),
            )
        )

    active_primary_keys = {
        (action.category, action.origin)
        for action in active_primary
    }
    customer_goal_map = {
        (goal.category, goal.origin): goal
        for goal in customer_goals
    }
    for action in active_primary:
        goal = customer_goal_map.get((action.category, action.origin))
        if goal is None:
            issues.append(
                MeasurementIssue(
                    severity=IssueSeverity.WARNING,
                    code="PRIMARY_ACTION_WITHOUT_CUSTOMER_GOAL",
                    scope="CONVERSION_ACTION",
                    resource_name=action.resource_name,
                    message=(
                        f"Primary action {action.name!r} has no matching customer goal "
                        f"for {action.category}/{action.origin}."
                    ),
                    recommendation="Review the effective conversion account and goal setup.",
                )
            )
        elif not goal.biddable:
            issues.append(
                MeasurementIssue(
                    severity=IssueSeverity.WARNING,
                    code="PRIMARY_ACTION_ACCOUNT_GOAL_NOT_BIDDABLE",
                    scope="CONVERSION_ACTION",
                    resource_name=action.resource_name,
                    message=(
                        f"Primary action {action.name!r} belongs to an account goal "
                        "that is not biddable."
                    ),
                    recommendation=(
                        "Confirm whether campaigns should optimize for this goal or whether "
                        "campaign-specific goal overrides are intentional."
                    ),
                )
            )

    for goal in customer_goals:
        if goal.biddable and (goal.category, goal.origin) not in active_primary_keys:
            issues.append(
                MeasurementIssue(
                    severity=IssueSeverity.WARNING,
                    code="BIDDABLE_GOAL_WITHOUT_ACTIVE_PRIMARY_ACTION",
                    scope="ACCOUNT",
                    resource_name=goal.resource_name,
                    message=(
                        f"Biddable customer goal {goal.category}/{goal.origin} has no "
                        "active primary conversion action."
                    ),
                    recommendation="Review removed, secondary, or incorrectly classified actions.",
                )
            )

    customer_biddable = {
        (goal.category, goal.origin): goal.biddable
        for goal in customer_goals
    }
    campaigns_with_overrides: set[str] = set()
    for goal in campaign_goals:
        if goal.goal_config_level == "CAMPAIGN":
            campaigns_with_overrides.add(goal.campaign_id)
        account_value = customer_biddable.get((goal.category, goal.origin))
        if (
            goal.goal_config_level == "CAMPAIGN"
            and account_value is not None
            and account_value != goal.biddable
        ):
            issues.append(
                MeasurementIssue(
                    severity=IssueSeverity.INFO,
                    code="CAMPAIGN_GOAL_OVERRIDES_ACCOUNT",
                    scope="CAMPAIGN",
                    resource_name=goal.resource_name,
                    campaign_id=goal.campaign_id,
                    message=(
                        f"Campaign {goal.campaign_name!r} overrides "
                        f"{goal.category}/{goal.origin} from {account_value} "
                        f"to {goal.biddable}."
                    ),
                    recommendation="Confirm this campaign-specific goal difference is intentional.",
                )
            )

    critical_count = sum(
        issue.severity == IssueSeverity.CRITICAL
        for issue in issues
    )
    warning_count = sum(
        issue.severity == IssueSeverity.WARNING
        for issue in issues
    )
    readiness = (
        MeasurementReadiness.BLOCKED
        if critical_count
        else MeasurementReadiness.WARNING
        if warning_count
        else MeasurementReadiness.READY
    )
    issues.sort(
        key=lambda issue: (
            _SEVERITY_ORDER[issue.severity],
            issue.campaign_id or "",
            issue.code,
        )
    )
    return MeasurementAuditResult(
        customer_id=account.customer_id,
        readiness=readiness,
        conversion_actions=actions,
        customer_goals=customer_goals,
        campaign_goals=campaign_goals,
        issues=issues,
        summary={
            "conversion_actions": len(actions),
            "active_primary_actions": len(active_primary),
            "customer_goals": len(customer_goals),
            "campaigns_with_goal_overrides": len(campaigns_with_overrides),
            "critical_issues": critical_count,
            "warning_issues": warning_count,
        },
    )


def _health_items(records: list[CampaignHealthRecord]) -> list[DailyBriefItem]:
    items: list[DailyBriefItem] = []
    for campaign in records:
        if campaign.status == "REMOVED":
            continue
        for reason in sorted(set(campaign.primary_status_reasons)):
            if reason in _EXPECTED_NON_SERVING_REASONS:
                continue
            if reason in _CRITICAL_CAMPAIGN_REASONS:
                severity = IssueSeverity.CRITICAL
            elif reason in _WARNING_CAMPAIGN_REASONS:
                severity = IssueSeverity.WARNING
            else:
                continue
            items.append(
                DailyBriefItem(
                    severity=severity,
                    category="SERVING",
                    code=reason,
                    campaign_id=campaign.campaign_id,
                    campaign_name=campaign.campaign_name,
                    title=f"{campaign.campaign_name}: {reason.replace('_', ' ').title()}",
                    evidence={
                        "campaign_status": campaign.status,
                        "primary_status": campaign.primary_status,
                        "bidding_strategy_system_status": (
                            campaign.bidding_strategy_system_status
                        ),
                    },
                    recommendation="Inspect and resolve this campaign serving limitation.",
                )
            )
        if campaign.has_recommended_budget:
            items.append(
                DailyBriefItem(
                    severity=IssueSeverity.INFO,
                    category="BUDGET",
                    code="RECOMMENDED_BUDGET_AVAILABLE",
                    campaign_id=campaign.campaign_id,
                    campaign_name=campaign.campaign_name,
                    title=f"{campaign.campaign_name}: budget recommendation available",
                    evidence={
                        "current_budget_micros": campaign.budget_amount_micros,
                        "recommended_budget_micros": (
                            campaign.recommended_budget_amount_micros
                        ),
                        "shared_budget": campaign.budget_explicitly_shared,
                        "budget_reference_count": campaign.budget_reference_count,
                    },
                    recommendation=(
                        "Review expected impact and every campaign using the budget "
                        "before changing it."
                    ),
                )
            )
    return items


def _performance_map(
    records: list[CampaignPerformanceRecord],
) -> dict[str, CampaignPerformanceRecord]:
    return {record.campaign_id: record for record in records}


def _money(micros: int) -> Decimal:
    return Decimal(micros) / MICROS_PER_UNIT


def _percent_change(current: Decimal | float, previous: Decimal | float) -> Decimal | None:
    previous_value = Decimal(str(previous))
    if previous_value == 0:
        return None
    current_value = Decimal(str(current))
    return ((current_value - previous_value) / previous_value) * Decimal("100")


def daily_account_brief(
    gateway: AdsGateway,
    account: AccountContext,
    policy: DailyBriefPolicy,
) -> DailyAccountBrief:
    window = reporting_window(
        account,
        as_of_date=policy.as_of_date,
        lookback_days=policy.lookback_days,
        exclude_recent_days=policy.exclude_recent_days,
    )
    comparison_end = window.start_date - timedelta(days=1)
    comparison = DateWindow(
        start_date=comparison_end - timedelta(days=policy.lookback_days - 1),
        end_date=comparison_end,
    )
    measurement = audit_measurement_and_goals(gateway, account)
    items = [
        DailyBriefItem(
            severity=issue.severity,
            category="MEASUREMENT",
            code=issue.code,
            campaign_id=issue.campaign_id,
            title=issue.message,
            evidence={"resource_name": issue.resource_name},
            recommendation=issue.recommendation,
        )
        for issue in measurement.issues
    ]
    items.extend(_health_items(gateway.list_campaign_health(account.customer_id)))

    current_records = gateway.list_campaign_performance(account.customer_id, window)
    previous_records = gateway.list_campaign_performance(account.customer_id, comparison)
    current_map = _performance_map(current_records)
    previous_map = _performance_map(previous_records)
    minimum_previous_cost = policy.minimum_previous_cost

    for campaign_id in sorted(set(current_map).union(previous_map)):
        current = current_map.get(campaign_id)
        previous = previous_map.get(campaign_id)
        if current is None or previous is None:
            continue
        current_cost = _money(current.metrics.cost_micros)
        previous_cost = _money(previous.metrics.cost_micros)
        if previous_cost >= minimum_previous_cost:
            spend_change = _percent_change(current_cost, previous_cost)
            if (
                spend_change is not None
                and abs(spend_change) >= policy.spend_change_alert_percent
            ):
                direction = "increased" if spend_change > 0 else "decreased"
                items.append(
                    DailyBriefItem(
                        severity=IssueSeverity.WARNING,
                        category="PERFORMANCE",
                        code=f"SPEND_{direction.upper()}",
                        campaign_id=campaign_id,
                        campaign_name=current.campaign_name,
                        title=(
                            f"{current.campaign_name}: spend {direction} "
                            f"{abs(spend_change):.1f}%"
                        ),
                        evidence={
                            "current_cost": str(current_cost),
                            "previous_cost": str(previous_cost),
                            "change_percent": str(spend_change),
                        },
                        recommendation=(
                            "Check budget, bidding, eligibility, demand, and recent changes."
                        ),
                    )
                )

        if previous.metrics.conversions >= policy.minimum_previous_conversions:
            conversion_change = _percent_change(
                current.metrics.conversions,
                previous.metrics.conversions,
            )
            if (
                conversion_change is not None
                and conversion_change <= -policy.conversion_drop_alert_percent
            ):
                items.append(
                    DailyBriefItem(
                        severity=IssueSeverity.CRITICAL,
                        category="PERFORMANCE",
                        code="CONVERSIONS_DROPPED",
                        campaign_id=campaign_id,
                        campaign_name=current.campaign_name,
                        title=(
                            f"{current.campaign_name}: conversions dropped "
                            f"{abs(conversion_change):.1f}%"
                        ),
                        evidence={
                            "current_conversions": current.metrics.conversions,
                            "previous_conversions": previous.metrics.conversions,
                            "change_percent": str(conversion_change),
                        },
                        recommendation=(
                            "Verify measurement first, then inspect spend, traffic, "
                            "search terms, geography, and landing pages."
                        ),
                    )
                )

        threshold = policy.zero_conversion_cost_threshold
        if (
            threshold is not None
            and current.metrics.conversions == 0
            and current_cost >= threshold
        ):
            items.append(
                DailyBriefItem(
                    severity=IssueSeverity.WARNING,
                    category="PERFORMANCE",
                    code="SPEND_WITHOUT_CONVERSIONS",
                    campaign_id=campaign_id,
                    campaign_name=current.campaign_name,
                    title=(
                        f"{current.campaign_name}: {current_cost} spent with "
                        "no conversions"
                    ),
                    evidence={
                        "cost": str(current_cost),
                        "clicks": current.metrics.clicks,
                    },
                    recommendation=(
                        "Review conversion tracking and traffic quality before pausing."
                    ),
                )
            )

    items.sort(
        key=lambda item: (
            _SEVERITY_ORDER[item.severity],
            item.category,
            item.campaign_name or "",
            item.code,
        )
    )
    items = items[: policy.max_items]
    current_totals = _sum_metrics(record.metrics for record in current_records)
    return DailyAccountBrief(
        customer_id=account.customer_id,
        currency_code=account.currency_code,
        time_zone=account.time_zone,
        analysis_window=window,
        comparison_window=comparison,
        measurement_readiness=measurement.readiness,
        items=items,
        summary={
            "critical_items": sum(
                item.severity == IssueSeverity.CRITICAL for item in items
            ),
            "warning_items": sum(
                item.severity == IssueSeverity.WARNING for item in items
            ),
            "informational_items": sum(
                item.severity == IssueSeverity.INFO for item in items
            ),
            "campaigns_with_metrics": len(current_records),
            "cost": str(_money(current_totals.cost_micros)),
            "conversions": current_totals.conversions,
            "conversion_value": current_totals.conversion_value,
        },
    )


def _sum_metrics(metrics: Iterable[PerformanceMetrics]) -> PerformanceMetrics:
    total = PerformanceMetrics()
    for value in metrics:
        total.impressions += value.impressions
        total.clicks += value.clicks
        total.cost_micros += value.cost_micros
        total.conversions += value.conversions
        total.conversion_value += value.conversion_value
    return total


def _metric_ratios(metrics: PerformanceMetrics) -> tuple[Decimal | None, Decimal | None]:
    cost = _money(metrics.cost_micros)
    conversions = Decimal(str(metrics.conversions))
    conversion_value = Decimal(str(metrics.conversion_value))
    cpa = cost / conversions if conversions > 0 else None
    roas = conversion_value / cost if cost > 0 else None
    return cpa, roas


def location_performance_report(
    gateway: AdsGateway,
    account: AccountContext,
    matches: CampaignMatchResult,
    policy: LocationPerformancePolicy,
) -> LocationPerformanceReport:
    window = reporting_window(
        account,
        as_of_date=policy.as_of_date,
        lookback_days=policy.lookback_days,
        exclude_recent_days=policy.exclude_recent_days,
    )
    campaign_ids = [match.campaign.id for match in matches.matched]
    rows = gateway.list_city_performance(
        account.customer_id,
        campaign_ids,
        window,
        only_targeted_locations=policy.only_targeted_locations,
    )
    totals: dict[str, PerformanceMetrics] = defaultdict(PerformanceMetrics)
    for row in rows:
        total = totals[row.campaign_id]
        total.impressions += row.metrics.impressions
        total.clicks += row.metrics.clicks
        total.cost_micros += row.metrics.cost_micros
        total.conversions += row.metrics.conversions
        total.conversion_value += row.metrics.conversion_value

    protected_resources = set(policy.protected_geo_target_constants)
    protected_names = set(policy.protected_location_names)
    assessments: list[CityPerformanceAssessment] = []
    for row in rows:
        cost = _money(row.metrics.cost_micros)
        cpa, roas = _metric_ratios(row.metrics)
        baseline_cpa, baseline_roas = _metric_ratios(totals[row.campaign_id])
        reasons: list[str] = []
        protected = (
            row.geo_target_constant in protected_resources
            or row.location_name.casefold() in protected_names
            or row.canonical_name.casefold() in protected_names
        )
        if protected:
            status = LocationAssessmentStatus.PROTECTED
            reasons.append("location is protected by policy")
        elif (
            row.metrics.clicks < policy.minimum_clicks
            or cost < policy.minimum_cost
        ):
            status = LocationAssessmentStatus.INSUFFICIENT_DATA
            reasons.append(
                "minimum click or cost threshold has not been reached"
            )
        else:
            status, reasons = _assess_location(
                row.metrics,
                cost,
                cpa,
                roas,
                baseline_cpa,
                baseline_roas,
                policy,
            )
        assessments.append(
            CityPerformanceAssessment(
                campaign_id=row.campaign_id,
                campaign_name=row.campaign_name,
                geo_target_constant=row.geo_target_constant,
                location_name=row.location_name,
                canonical_name=row.canonical_name,
                country_code=row.country_code,
                targeted_location=row.targeted_location,
                metrics=row.metrics,
                cost=cost,
                cpa=cpa,
                roas=roas,
                campaign_baseline_cpa=baseline_cpa,
                campaign_baseline_roas=baseline_roas,
                status=status,
                reasons=reasons,
            )
        )

    candidates_all = [
        item
        for item in assessments
        if item.status == LocationAssessmentStatus.EXCLUSION_CANDIDATE
    ]
    candidates_all.sort(
        key=lambda item: (
            -item.cost,
            item.campaign_name,
            item.canonical_name,
        )
    )
    candidates = candidates_all[: policy.max_candidates]
    assessments.sort(
        key=lambda item: (
            0
            if item.status == LocationAssessmentStatus.EXCLUSION_CANDIDATE
            else 1,
            -item.cost,
            item.campaign_name,
            item.canonical_name,
        )
    )
    return LocationPerformanceReport(
        customer_id=account.customer_id,
        currency_code=account.currency_code,
        time_zone=account.time_zone,
        window=window,
        objective=policy.objective,
        assessments=assessments,
        candidates=candidates,
        summary={
            "matched_campaigns": len(matches.matched),
            "cities_analyzed": len(assessments),
            "candidate_cities": len(candidates_all),
            "candidates_returned": len(candidates),
            "protected_cities": sum(
                item.status == LocationAssessmentStatus.PROTECTED
                for item in assessments
            ),
            "insufficient_data_cities": sum(
                item.status == LocationAssessmentStatus.INSUFFICIENT_DATA
                for item in assessments
            ),
        },
        warnings=[
            (
                "This report uses modeled physical user-location data. Treat candidates "
                "as recommendations and review business serviceability before exclusion."
            ),
            (
                f"The most recent {policy.exclude_recent_days} day(s) were excluded "
                "to reduce conversion-lag bias."
            ),
        ],
    )


def _assess_location(
    metrics: PerformanceMetrics,
    cost: Decimal,
    cpa: Decimal | None,
    roas: Decimal | None,
    baseline_cpa: Decimal | None,
    baseline_roas: Decimal | None,
    policy: LocationPerformancePolicy,
) -> tuple[LocationAssessmentStatus, list[str]]:
    if policy.objective == PerformanceObjective.CPA:
        assert policy.target_cpa is not None
        if (
            metrics.conversions == 0
            and cost >= policy.target_cpa * policy.zero_conversion_target_multiplier
        ):
            return (
                LocationAssessmentStatus.EXCLUSION_CANDIDATE,
                [
                    (
                        f"zero conversions after spending {cost}, at least "
                        f"{policy.zero_conversion_target_multiplier}x target CPA"
                    )
                ],
            )
        if (
            cpa is not None
            and baseline_cpa is not None
            and metrics.conversions >= policy.minimum_conversions_for_relative_rule
            and cpa > policy.target_cpa * policy.cpa_target_multiplier
            and cpa > baseline_cpa * policy.cpa_target_multiplier
        ):
            return (
                LocationAssessmentStatus.EXCLUSION_CANDIDATE,
                [
                    (
                        f"CPA {cpa} exceeds both target and campaign city baseline "
                        f"by the configured {policy.cpa_target_multiplier}x multiplier"
                    )
                ],
            )
        if cpa is not None and cpa > policy.target_cpa:
            return (
                LocationAssessmentStatus.WATCH,
                [f"CPA {cpa} is above target CPA {policy.target_cpa}"],
            )
        return LocationAssessmentStatus.HEALTHY, ["CPA is within policy thresholds"]

    assert policy.target_roas is not None
    if metrics.conversion_value == 0:
        return (
            LocationAssessmentStatus.EXCLUSION_CANDIDATE,
            ["no conversion value after reaching minimum click and cost thresholds"],
        )
    if (
        roas is not None
        and baseline_roas is not None
        and roas < policy.target_roas * policy.roas_target_multiplier
        and roas < baseline_roas * policy.roas_target_multiplier
    ):
        return (
            LocationAssessmentStatus.EXCLUSION_CANDIDATE,
            [
                (
                    f"ROAS {roas} is below both target and campaign city baseline "
                    f"at the configured {policy.roas_target_multiplier} multiplier"
                )
            ],
        )
    if roas is not None and roas < policy.target_roas:
        return (
            LocationAssessmentStatus.WATCH,
            [f"ROAS {roas} is below target ROAS {policy.target_roas}"],
        )
    return LocationAssessmentStatus.HEALTHY, ["ROAS is within policy thresholds"]
