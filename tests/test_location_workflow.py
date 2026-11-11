from __future__ import annotations

import pytest

from google_ads_agent.errors import (
    PlanInputMismatchError,
    TargetingConflictError,
)
from google_ads_agent.models import (
    BudgetCondition,
    CampaignSelector,
    CtaCondition,
    ExecutionControl,
    LocationCriterion,
    LocationInput,
    ResultStatus,
    TextCondition,
)
from google_ads_agent.service import GoogleAdsAgent
from tests.fakes import FakeAdsGateway


def selector() -> CampaignSelector:
    return CampaignSelector(
        name=TextCondition(value="Campaign X"),
        budget=BudgetCondition(
            period="DAILY",
            amount="100.00",
            currency_code="USD",
        ),
        cta=CtaCondition(values=["LEARN_MORE"]),
    )


def locations() -> list[LocationInput]:
    return [LocationInput(name="Austin", country_code="US", target_type="City")]


def test_plan_then_execute_location_exclusion(
    agent: GoogleAdsAgent,
    gateway: FakeAdsGateway,
) -> None:
    plan = agent.exclude_locations_from_matching_campaigns(
        customer_id="123-456-7890",
        selector=selector(),
        locations=locations(),
        control=ExecutionControl(
            mode="PLAN",
            idempotency_key="test-command-0001",
        ),
    )

    assert plan.status == ResultStatus.AWAITING_APPROVAL
    assert len(plan.actions) == 1
    assert gateway.mutation_calls == [
        {
            "validate_only": True,
            "partial_failure": False,
            "action_ids": [plan.actions[0].action_id],
        }
    ]

    result = agent.exclude_locations_from_matching_campaigns(
        customer_id="1234567890",
        selector=selector(),
        locations=locations(),
        control=ExecutionControl(
            mode="EXECUTE",
            plan_id=plan.plan_id,
            confirmation="APPROVE",
        ),
    )

    assert result.status == ResultStatus.EXECUTED
    assert result.verification_passed is True
    assert len(result.executed_actions) == 1
    assert gateway.mutation_calls[-1]["validate_only"] is False

    repeated = agent.exclude_locations_from_matching_campaigns(
        customer_id="1234567890",
        selector=selector(),
        locations=locations(),
        control=ExecutionControl(
            mode="EXECUTE",
            plan_id=plan.plan_id,
            confirmation="APPROVE",
        ),
    )
    assert repeated == result
    assert len(gateway.mutation_calls) == 2


def test_plan_is_noop_when_location_is_already_excluded(
    agent: GoogleAdsAgent,
    gateway: FakeAdsGateway,
) -> None:
    gateway.criteria.append(
        LocationCriterion(
            resource_name="customers/1234567890/campaignCriteria/111~1",
            campaign_id="111",
            criterion_type="LOCATION",
            negative=True,
            geo_target_constant="geoTargetConstants/1026201",
        )
    )

    result = agent.exclude_locations_from_matching_campaigns(
        customer_id="1234567890",
        selector=selector(),
        locations=locations(),
        control=ExecutionControl(mode="PLAN"),
    )

    assert result.status == ResultStatus.NOOP
    assert result.skipped[0]["reason"] == "location is already excluded"
    assert gateway.mutation_calls == []


def test_positive_target_conflict_blocks_plan(
    agent: GoogleAdsAgent,
    gateway: FakeAdsGateway,
) -> None:
    gateway.criteria.append(
        LocationCriterion(
            resource_name="customers/1234567890/campaignCriteria/111~1",
            campaign_id="111",
            criterion_type="LOCATION",
            negative=False,
            geo_target_constant="geoTargetConstants/1026201",
        )
    )

    with pytest.raises(TargetingConflictError):
        agent.exclude_locations_from_matching_campaigns(
            customer_id="1234567890",
            selector=selector(),
            locations=locations(),
            control=ExecutionControl(mode="PLAN"),
        )
    assert gateway.mutation_calls == []


def test_execution_rejects_changed_inputs_before_claim(
    agent: GoogleAdsAgent,
) -> None:
    plan = agent.exclude_locations_from_matching_campaigns(
        customer_id="1234567890",
        selector=selector(),
        locations=locations(),
        control=ExecutionControl(mode="PLAN"),
    )

    changed_selector = selector().model_copy(
        update={"name": TextCondition(value="Different campaign")}
    )
    with pytest.raises(PlanInputMismatchError):
        agent.exclude_locations_from_matching_campaigns(
            customer_id="1234567890",
            selector=changed_selector,
            locations=locations(),
            control=ExecutionControl(
                mode="EXECUTE",
                plan_id=plan.plan_id,
                confirmation="APPROVE",
            ),
        )


def test_execution_blocks_stale_plan(
    agent: GoogleAdsAgent,
    gateway: FakeAdsGateway,
) -> None:
    plan = agent.exclude_locations_from_matching_campaigns(
        customer_id="1234567890",
        selector=selector(),
        locations=locations(),
        control=ExecutionControl(mode="PLAN"),
    )
    gateway.campaigns[0] = gateway.campaigns[0].model_copy(
        update={"status": "PAUSED"}
    )

    result = agent.exclude_locations_from_matching_campaigns(
        customer_id="1234567890",
        selector=selector(),
        locations=locations(),
        control=ExecutionControl(
            mode="EXECUTE",
            plan_id=plan.plan_id,
            confirmation="APPROVE",
        ),
    )

    assert result.status == ResultStatus.STALE_PLAN
    assert len(gateway.mutation_calls) == 1
