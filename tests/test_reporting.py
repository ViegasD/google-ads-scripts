from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from google_ads_agent.models import (
    CampaignHealthRecord,
    CampaignPerformanceRecord,
    CampaignSelector,
    CityPerformanceRecord,
    ConversionActionRecord,
    CustomerConversionGoalRecord,
    DailyBriefPolicy,
    LocationAssessmentStatus,
    LocationPerformancePolicy,
    MeasurementReadiness,
    PerformanceMetrics,
)
from google_ads_agent.service import GoogleAdsAgent
from tests.fakes import FakeAdsGateway


def configure_valid_measurement(gateway: FakeAdsGateway) -> None:
    gateway.conversion_actions = [
        ConversionActionRecord(
            resource_name="customers/1234567890/conversionActions/1",
            id="1",
            name="Qualified lead",
            status="ENABLED",
            type="WEBPAGE",
            category="SUBMIT_LEAD_FORM",
            origin="WEBSITE",
            primary_for_goal=True,
        )
    ]
    gateway.customer_conversion_goals = [
        CustomerConversionGoalRecord(
            resource_name=(
                "customers/1234567890/customerConversionGoals/"
                "SUBMIT_LEAD_FORM~WEBSITE"
            ),
            category="SUBMIT_LEAD_FORM",
            origin="WEBSITE",
            biddable=True,
        )
    ]


def test_measurement_audit_ready_with_primary_biddable_goal(
    agent: GoogleAdsAgent,
    gateway: FakeAdsGateway,
) -> None:
    configure_valid_measurement(gateway)

    result = agent.audit_measurement_and_goals("123-456-7890")

    assert result.readiness == MeasurementReadiness.READY
    assert result.issues == []
    assert result.summary["active_primary_actions"] == 1


def test_measurement_audit_blocks_performance_automation_without_primary_action(
    agent: GoogleAdsAgent,
    gateway: FakeAdsGateway,
) -> None:
    gateway.conversion_actions = [
        ConversionActionRecord(
            resource_name="customers/1234567890/conversionActions/1",
            id="1",
            name="Page view",
            status="ENABLED",
            type="WEBPAGE",
            category="PAGE_VIEW",
            origin="WEBSITE",
            primary_for_goal=False,
        )
    ]

    result = agent.audit_measurement_and_goals("1234567890")

    assert result.readiness == MeasurementReadiness.BLOCKED
    assert result.issues[0].code == "NO_PRIMARY_CONVERSION_ACTIONS"


def test_daily_brief_detects_serving_and_performance_anomalies(
    agent: GoogleAdsAgent,
    gateway: FakeAdsGateway,
) -> None:
    configure_valid_measurement(gateway)
    gateway.campaign_health = [
        CampaignHealthRecord(
            campaign_id="111",
            campaign_name="Campaign X",
            status="ENABLED",
            primary_status="LIMITED",
            primary_status_reasons=["BUDGET_CONSTRAINED"],
            bidding_strategy_type="MAXIMIZE_CONVERSIONS",
            bidding_strategy_system_status="LIMITED",
            budget_amount_micros=100_000_000,
        )
    ]
    gateway.campaign_performance = {
        ("2026-07-11", "2026-07-17"): [
            CampaignPerformanceRecord(
                campaign_id="111",
                campaign_name="Campaign X",
                metrics=PerformanceMetrics(
                    impressions=2_000,
                    clicks=100,
                    cost_micros=200_000_000,
                    conversions=2,
                    conversion_value=300,
                ),
            )
        ],
        ("2026-07-04", "2026-07-10"): [
            CampaignPerformanceRecord(
                campaign_id="111",
                campaign_name="Campaign X",
                metrics=PerformanceMetrics(
                    impressions=1_500,
                    clicks=80,
                    cost_micros=100_000_000,
                    conversions=10,
                    conversion_value=1_000,
                ),
            )
        ],
    }

    brief = agent.daily_account_brief(
        "1234567890",
        DailyBriefPolicy(
            as_of_date=date(2026, 7, 20),
            lookback_days=7,
            exclude_recent_days=3,
            spend_change_alert_percent=50,
            conversion_drop_alert_percent=50,
            minimum_previous_cost=25,
            minimum_previous_conversions=3,
        ),
    )

    assert brief.measurement_readiness == MeasurementReadiness.READY
    assert brief.analysis_window.start_date == date(2026, 7, 11)
    assert {item.code for item in brief.items} == {
        "BUDGET_CONSTRAINED",
        "SPEND_INCREASED",
        "CONVERSIONS_DROPPED",
    }
    assert brief.summary["cost"] == "200"


def test_city_report_ranks_candidates_and_respects_guards(
    agent: GoogleAdsAgent,
    gateway: FakeAdsGateway,
) -> None:
    configure_valid_measurement(gateway)
    gateway.city_performance = [
        CityPerformanceRecord(
            campaign_id="111",
            campaign_name="Campaign X",
            geo_target_constant="geoTargetConstants/1",
            location_name="Austin",
            canonical_name="Austin, Texas, United States",
            country_code="US",
            targeted_location=True,
            metrics=PerformanceMetrics(
                clicks=30,
                cost_micros=150_000_000,
                conversions=0,
            ),
        ),
        CityPerformanceRecord(
            campaign_id="111",
            campaign_name="Campaign X",
            geo_target_constant="geoTargetConstants/2",
            location_name="Dallas",
            canonical_name="Dallas, Texas, United States",
            country_code="US",
            targeted_location=True,
            metrics=PerformanceMetrics(
                clicks=40,
                cost_micros=100_000_000,
                conversions=4,
                conversion_value=600,
            ),
        ),
        CityPerformanceRecord(
            campaign_id="111",
            campaign_name="Campaign X",
            geo_target_constant="geoTargetConstants/3",
            location_name="Waco",
            canonical_name="Waco, Texas, United States",
            country_code="US",
            targeted_location=True,
            metrics=PerformanceMetrics(
                clicks=35,
                cost_micros=140_000_000,
                conversions=0,
            ),
        ),
        CityPerformanceRecord(
            campaign_id="111",
            campaign_name="Campaign X",
            geo_target_constant="geoTargetConstants/4",
            location_name="El Paso",
            canonical_name="El Paso, Texas, United States",
            country_code="US",
            targeted_location=True,
            metrics=PerformanceMetrics(
                clicks=3,
                cost_micros=10_000_000,
                conversions=0,
            ),
        ),
    ]

    report = agent.get_location_performance_report(
        "1234567890",
        CampaignSelector(campaign_ids=["111"]),
        LocationPerformancePolicy(
            objective="CPA",
            target_cpa=Decimal("50"),
            as_of_date=date(2026, 7, 20),
            minimum_clicks=20,
            minimum_cost=Decimal("25"),
            protected_location_names=["Waco"],
        ),
    )

    assert [candidate.location_name for candidate in report.candidates] == ["Austin"]
    status_by_city = {
        assessment.location_name: assessment.status
        for assessment in report.assessments
    }
    assert status_by_city == {
        "Austin": LocationAssessmentStatus.EXCLUSION_CANDIDATE,
        "Dallas": LocationAssessmentStatus.HEALTHY,
        "Waco": LocationAssessmentStatus.PROTECTED,
        "El Paso": LocationAssessmentStatus.INSUFFICIENT_DATA,
    }
    assert report.summary["candidate_cities"] == 1
    assert all("Measurement readiness" not in warning for warning in report.warnings)


def test_city_report_warns_when_measurement_is_not_ready(
    agent: GoogleAdsAgent,
    gateway: FakeAdsGateway,
) -> None:
    report = agent.get_location_performance_report(
        "1234567890",
        CampaignSelector(campaign_ids=["111"]),
        LocationPerformancePolicy(objective="CPA", target_cpa=Decimal("50")),
    )

    assert report.warnings[0].startswith("Measurement readiness is BLOCKED")


def test_location_policy_requires_the_objective_target() -> None:
    with pytest.raises(ValidationError, match="target_roas is required"):
        LocationPerformancePolicy(objective="ROAS")
