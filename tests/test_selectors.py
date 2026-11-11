from __future__ import annotations

import pytest

from google_ads_agent.errors import AmbiguousSelectorError, UnsupportedSelectorError
from google_ads_agent.models import (
    BudgetCondition,
    CampaignSelector,
    CtaCondition,
    TextCondition,
)
from google_ads_agent.selectors import find_campaigns
from tests.fakes import FakeAdsGateway, campaign, cta


def test_selector_matches_name_budget_and_cta(gateway: FakeAdsGateway) -> None:
    selector = CampaignSelector(
        name=TextCondition(operator="EXACT", value="Campaign X"),
        budget=BudgetCondition(
            period="DAILY",
            amount="100",
            currency_code="usd",
        ),
        cta=CtaCondition(values=["learn_more"]),
    )

    result = find_campaigns(gateway, gateway.account, selector)

    assert [match.campaign.id for match in result.matched] == ["111"]
    assert any("budget matched" in reason for reason in result.matched[0].reasons)
    assert any("CTA matched LEARN_MORE" in reason for reason in result.matched[0].reasons)


def test_selector_rejects_multiple_matches_by_default(gateway: FakeAdsGateway) -> None:
    gateway.campaigns.append(campaign(campaign_id="222", name="Campaign X"))
    selector = CampaignSelector(name=TextCondition(value="Campaign X"))

    with pytest.raises(AmbiguousSelectorError):
        find_campaigns(gateway, gateway.account, selector)


def test_selector_allows_explicit_multiple_matches(gateway: FakeAdsGateway) -> None:
    gateway.campaigns.append(campaign(campaign_id="222", name="Campaign X"))
    selector = CampaignSelector(
        name=TextCondition(value="Campaign X"),
        allow_multiple=True,
    )

    result = find_campaigns(gateway, gateway.account, selector)

    assert {match.campaign.id for match in result.matched} == {"111", "222"}


def test_ad_level_cta_scope_is_rejected(gateway: FakeAdsGateway) -> None:
    gateway.ctas = {"111": cta()}
    selector = CampaignSelector(
        campaign_ids=["111"],
        cta=CtaCondition(values=["LEARN_MORE"], match_scope="ANY_ACTIVE_AD"),
    )

    with pytest.raises(UnsupportedSelectorError):
        find_campaigns(gateway, gateway.account, selector)
