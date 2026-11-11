"""Stateful fake gateway used by unit and workflow tests."""

from __future__ import annotations

from collections.abc import Sequence

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
    CustomerConversionGoalRecord,
    DateWindow,
    GeoCandidate,
    LocationCriterion,
    LocationInput,
    MutationError,
    MutationReceipt,
    PlannedAction,
)


class FakeAdsGateway:
    api_version = "v25"

    def __init__(self) -> None:
        self.account = AccountContext(
            customer_id="1234567890",
            descriptive_name="Test account",
            currency_code="USD",
            time_zone="America/New_York",
            status="ENABLED",
            test_account=True,
            api_version="v25",
        )
        self.campaigns: list[CampaignRecord] = []
        self.ctas: dict[str, CampaignCtaSummary] = {}
        self.geo_candidates: dict[tuple[str, str], list[GeoCandidate]] = {}
        self.criteria: list[LocationCriterion] = []
        self.conversion_actions: list[ConversionActionRecord] = []
        self.customer_conversion_goals: list[CustomerConversionGoalRecord] = []
        self.campaign_conversion_goals: list[CampaignConversionGoalRecord] = []
        self.campaign_health: list[CampaignHealthRecord] = []
        self.campaign_performance: dict[
            tuple[str, str],
            list[CampaignPerformanceRecord],
        ] = {}
        self.city_performance: list[CityPerformanceRecord] = []
        self.validation_errors: list[MutationError] = []
        self.execution_errors: list[MutationError] = []
        self.mutation_calls: list[dict[str, object]] = []

    def get_account_context(self, customer_id: str) -> AccountContext:
        assert customer_id == self.account.customer_id
        return self.account.model_copy(deep=True)

    def list_conversion_actions(
        self,
        customer_id: str,
    ) -> list[ConversionActionRecord]:
        assert customer_id == self.account.customer_id
        return [record.model_copy(deep=True) for record in self.conversion_actions]

    def list_customer_conversion_goals(
        self,
        customer_id: str,
    ) -> list[CustomerConversionGoalRecord]:
        assert customer_id == self.account.customer_id
        return [
            record.model_copy(deep=True)
            for record in self.customer_conversion_goals
        ]

    def list_campaign_conversion_goals(
        self,
        customer_id: str,
    ) -> list[CampaignConversionGoalRecord]:
        assert customer_id == self.account.customer_id
        return [
            record.model_copy(deep=True)
            for record in self.campaign_conversion_goals
        ]

    def list_campaign_health(
        self,
        customer_id: str,
    ) -> list[CampaignHealthRecord]:
        assert customer_id == self.account.customer_id
        return [record.model_copy(deep=True) for record in self.campaign_health]

    def list_campaign_performance(
        self,
        customer_id: str,
        window: DateWindow,
    ) -> list[CampaignPerformanceRecord]:
        assert customer_id == self.account.customer_id
        key = (window.start_date.isoformat(), window.end_date.isoformat())
        return [
            record.model_copy(deep=True)
            for record in self.campaign_performance.get(key, [])
        ]

    def list_city_performance(
        self,
        customer_id: str,
        campaign_ids: Sequence[str],
        window: DateWindow,
        *,
        only_targeted_locations: bool,
    ) -> list[CityPerformanceRecord]:
        assert customer_id == self.account.customer_id
        del window
        wanted = set(campaign_ids)
        return [
            record.model_copy(deep=True)
            for record in self.city_performance
            if record.campaign_id in wanted
            and (record.targeted_location or not only_targeted_locations)
        ]

    def list_campaigns(
        self,
        customer_id: str,
        *,
        include_removed: bool,
    ) -> list[CampaignRecord]:
        assert customer_id == self.account.customer_id
        return [
            campaign.model_copy(deep=True)
            for campaign in self.campaigns
            if include_removed or campaign.status != "REMOVED"
        ]

    def get_campaign_ctas(
        self,
        customer_id: str,
        campaign_ids: Sequence[str],
        *,
        scope: CtaMatchScope,
    ) -> list[CampaignCtaSummary]:
        assert customer_id == self.account.customer_id
        del scope
        return [
            self.ctas[campaign_id].model_copy(deep=True)
            for campaign_id in campaign_ids
            if campaign_id in self.ctas
        ]

    def suggest_geo_targets(
        self,
        customer_id: str,
        location: LocationInput,
    ) -> list[GeoCandidate]:
        assert customer_id == self.account.customer_id
        return [
            candidate.model_copy(deep=True)
            for candidate in self.geo_candidates.get(
                (location.name.casefold(), location.country_code),
                [],
            )
        ]

    def list_location_criteria(
        self,
        customer_id: str,
        campaign_ids: Sequence[str],
    ) -> list[LocationCriterion]:
        assert customer_id == self.account.customer_id
        wanted = set(campaign_ids)
        return [
            criterion.model_copy(deep=True)
            for criterion in self.criteria
            if criterion.campaign_id in wanted
        ]

    def mutate_location_exclusions(
        self,
        customer_id: str,
        actions: Sequence[PlannedAction],
        *,
        validate_only: bool,
        partial_failure: bool,
    ) -> MutationReceipt:
        assert customer_id == self.account.customer_id
        self.mutation_calls.append(
            {
                "validate_only": validate_only,
                "partial_failure": partial_failure,
                "action_ids": [action.action_id for action in actions],
            }
        )
        errors = self.validation_errors if validate_only else self.execution_errors
        if errors:
            return MutationReceipt(
                validated_only=validate_only,
                request_ids=["fake-error-request-id"],
                errors=errors,
            )

        resource_names: list[str] = []
        if not validate_only:
            for index, action in enumerate(actions, start=1):
                resource_name = (
                    f"customers/{customer_id}/campaignCriteria/"
                    f"{action.campaign_id}~{1000 + index}"
                )
                resource_names.append(resource_name)
                self.criteria.append(
                    LocationCriterion(
                        resource_name=resource_name,
                        campaign_id=action.campaign_id,
                        criterion_type="LOCATION",
                        negative=True,
                        geo_target_constant=action.geo_target_constant,
                    )
                )
        return MutationReceipt(
            validated_only=validate_only,
            resource_names=resource_names,
            request_ids=["fake-request-id"],
        )


def campaign(
    *,
    campaign_id: str = "111",
    name: str = "Campaign X",
    amount_micros: int = 100_000_000,
) -> CampaignRecord:
    return CampaignRecord(
        id=campaign_id,
        resource_name=f"customers/1234567890/campaigns/{campaign_id}",
        name=name,
        status="ENABLED",
        channel_type="SEARCH",
        channel_subtype="SEARCH_STANDARD",
        experiment_type="BASE",
        bidding_strategy_type="MAXIMIZE_CONVERSIONS",
        budget_id=f"9{campaign_id}",
        budget_resource_name=f"customers/1234567890/campaignBudgets/9{campaign_id}",
        budget_period="DAILY",
        budget_amount_micros=amount_micros,
        budget_explicitly_shared=False,
        budget_reference_count=1,
    )


def cta(campaign_id: str = "111", value: str = "LEARN_MORE") -> CampaignCtaSummary:
    return CampaignCtaSummary(
        campaign_id=campaign_id,
        status="EXPLICIT",
        values=[value],
        sources=[],
    )


def geo(
    *,
    criterion_id: str = "1026201",
    name: str = "Austin",
    canonical_name: str = "Austin, Texas, United States",
    country_code: str = "US",
    target_type: str = "City",
) -> GeoCandidate:
    return GeoCandidate(
        resource_name=f"geoTargetConstants/{criterion_id}",
        criterion_id=criterion_id,
        name=name,
        canonical_name=canonical_name,
        country_code=country_code,
        target_type=target_type,
        status="ENABLED",
        reach=1_000_000,
    )
