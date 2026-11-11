"""Deterministic campaign selection and match explanations."""

from __future__ import annotations

import re
from decimal import Decimal

from google_ads_agent.errors import (
    AmbiguousSelectorError,
    UnsupportedSelectorError,
)
from google_ads_agent.gateway import AdsGateway
from google_ads_agent.models import (
    AccountContext,
    CampaignMatch,
    CampaignMatchResult,
    CampaignRecord,
    CampaignSelector,
    ComparisonOperator,
    CtaMatchScope,
    CtaStatus,
    TextCondition,
    TextOperator,
)
from google_ads_agent.utils import amount_to_micros


def _matches_text(actual: str, condition: TextCondition) -> bool:
    candidate = actual if condition.case_sensitive else actual.casefold()
    expected = condition.value if condition.case_sensitive else condition.value.casefold()
    if condition.operator == TextOperator.EXACT:
        return candidate == expected
    if condition.operator == TextOperator.CONTAINS:
        return expected in candidate
    if condition.operator == TextOperator.STARTS_WITH:
        return candidate.startswith(expected)
    flags = 0 if condition.case_sensitive else re.IGNORECASE
    return re.search(condition.value, actual, flags=flags) is not None


def _compare(actual: int, expected: int, tolerance: int, operator: ComparisonOperator) -> bool:
    if operator == ComparisonOperator.EQUALS:
        return abs(actual - expected) <= tolerance
    if operator == ComparisonOperator.GREATER_THAN:
        return actual > expected
    if operator == ComparisonOperator.GREATER_THAN_OR_EQUAL:
        return actual >= expected
    if operator == ComparisonOperator.LESS_THAN:
        return actual < expected
    return actual <= expected


def _is_experiment(campaign: CampaignRecord) -> bool:
    experiment_type = (campaign.experiment_type or "").upper()
    return bool(campaign.base_campaign) or experiment_type not in {"", "BASE", "UNSPECIFIED"}


def _campaign_matches(
    campaign: CampaignRecord,
    selector: CampaignSelector,
    account: AccountContext,
) -> tuple[bool, list[str], str | None]:
    reasons: list[str] = []

    if campaign.status == "REMOVED" and not selector.include_removed:
        return False, reasons, "removed campaigns are excluded"
    if _is_experiment(campaign) and not selector.include_experiments:
        return False, reasons, "experiment campaigns are excluded"

    if selector.campaign_ids is not None:
        if campaign.id not in selector.campaign_ids:
            return False, reasons, "campaign ID did not match"
        reasons.append(f"campaign ID matched {campaign.id}")

    if selector.name is not None:
        if not _matches_text(campaign.name, selector.name):
            return False, reasons, "campaign name did not match"
        reasons.append(
            f"campaign name matched {selector.name.operator.value} {selector.name.value!r}"
        )

    if selector.statuses is not None:
        if campaign.status.upper() not in selector.statuses:
            return False, reasons, "campaign status did not match"
        reasons.append(f"campaign status matched {campaign.status}")

    if selector.channel_types is not None:
        if campaign.channel_type.upper() not in selector.channel_types:
            return False, reasons, "advertising channel type did not match"
        reasons.append(f"channel type matched {campaign.channel_type}")

    if selector.channel_subtypes is not None:
        if (campaign.channel_subtype or "").upper() not in selector.channel_subtypes:
            return False, reasons, "advertising channel subtype did not match"
        reasons.append(f"channel subtype matched {campaign.channel_subtype}")

    if selector.bidding_strategy_types is not None:
        if (campaign.bidding_strategy_type or "").upper() not in selector.bidding_strategy_types:
            return False, reasons, "bidding strategy type did not match"
        reasons.append(f"bidding strategy matched {campaign.bidding_strategy_type}")

    if selector.labels is not None:
        actual_labels = {value.casefold() for value in campaign.labels}
        expected_labels = {value.casefold() for value in selector.labels}
        if not expected_labels.issubset(actual_labels):
            return False, reasons, "required labels were not all present"
        reasons.append(f"labels matched {', '.join(selector.labels)}")

    if selector.budget is not None:
        condition = selector.budget
        if condition.currency_code != account.currency_code.upper():
            return False, reasons, (
                f"budget currency {condition.currency_code} does not match account "
                f"currency {account.currency_code}"
            )
        if campaign.budget_period != condition.period.value:
            return False, reasons, "budget period did not match"
        if campaign.budget_amount_micros is None:
            return False, reasons, "campaign has no comparable budget amount"
        expected = amount_to_micros(condition.amount)
        tolerance = amount_to_micros(Decimal(condition.tolerance))
        if not _compare(
            campaign.budget_amount_micros,
            expected,
            tolerance,
            condition.operator,
        ):
            return False, reasons, "budget amount did not match"
        reasons.append(
            f"{condition.period.value} budget matched "
            f"{condition.operator.value} {condition.amount} {condition.currency_code}"
        )

    if selector.cta is not None:
        if selector.cta.match_scope in {
            CtaMatchScope.ANY_ACTIVE_AD,
            CtaMatchScope.ALL_ACTIVE_ADS,
        }:
            raise UnsupportedSelectorError(
                "ad-level CTA scopes are not implemented in the first release",
                details={
                    "supported_scopes": [
                        CtaMatchScope.ANY_EXPLICIT_SOURCE.value,
                        CtaMatchScope.CAMPAIGN_ASSET_ONLY.value,
                    ]
                },
            )
        summary = campaign.cta
        if summary is None or summary.status not in {CtaStatus.EXPLICIT, CtaStatus.MULTIPLE}:
            return False, reasons, "no supported explicit CTA was found"
        expected_ctas = set(selector.cta.values)
        actual_ctas = set(summary.values)
        if not expected_ctas.intersection(actual_ctas):
            return False, reasons, "CTA did not match"
        reasons.append(
            "CTA matched " + ", ".join(sorted(expected_ctas.intersection(actual_ctas)))
        )

    return True, reasons, None


def find_campaigns(
    gateway: AdsGateway,
    account: AccountContext,
    selector: CampaignSelector,
) -> CampaignMatchResult:
    campaigns = gateway.list_campaigns(
        account.customer_id,
        include_removed=selector.include_removed,
    )

    if selector.cta is not None and campaigns:
        cta_summaries = gateway.get_campaign_ctas(
            account.customer_id,
            [campaign.id for campaign in campaigns],
            scope=selector.cta.match_scope,
        )
        by_campaign = {summary.campaign_id: summary for summary in cta_summaries}
        campaigns = [
            campaign.model_copy(update={"cta": by_campaign.get(campaign.id)})
            for campaign in campaigns
        ]

    matched: list[CampaignMatch] = []
    skipped: list[dict[str, str]] = []
    for campaign in campaigns:
        is_match, reasons, skip_reason = _campaign_matches(campaign, selector, account)
        if is_match:
            matched.append(CampaignMatch(campaign=campaign, reasons=reasons))
        else:
            skipped.append(
                {
                    "campaign_id": campaign.id,
                    "campaign_name": campaign.name,
                    "reason": skip_reason or "selector did not match",
                }
            )

    if len(matched) > 1 and not selector.allow_multiple:
        raise AmbiguousSelectorError(
            "selector matched more than one campaign; use campaign_ids or set allow_multiple=true",
            details={
                "matches": [
                    {"campaign_id": item.campaign.id, "campaign_name": item.campaign.name}
                    for item in matched
                ]
            },
        )

    return CampaignMatchResult(
        customer_id=account.customer_id,
        matched=matched,
        skipped=skipped,
    )
