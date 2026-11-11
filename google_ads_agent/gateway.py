"""Mockable boundary around the official Google Ads client."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

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
    MutationReceipt,
    PlannedAction,
)


class AdsGateway(Protocol):
    """Operations required by the first high-level tools."""

    api_version: str

    def get_account_context(self, customer_id: str) -> AccountContext: ...

    def list_conversion_actions(
        self,
        customer_id: str,
    ) -> list[ConversionActionRecord]: ...

    def list_customer_conversion_goals(
        self,
        customer_id: str,
    ) -> list[CustomerConversionGoalRecord]: ...

    def list_campaign_conversion_goals(
        self,
        customer_id: str,
    ) -> list[CampaignConversionGoalRecord]: ...

    def list_campaign_health(
        self,
        customer_id: str,
    ) -> list[CampaignHealthRecord]: ...

    def list_campaign_performance(
        self,
        customer_id: str,
        window: DateWindow,
    ) -> list[CampaignPerformanceRecord]: ...

    def list_city_performance(
        self,
        customer_id: str,
        campaign_ids: Sequence[str],
        window: DateWindow,
        *,
        only_targeted_locations: bool,
    ) -> list[CityPerformanceRecord]: ...

    def list_campaigns(
        self,
        customer_id: str,
        *,
        include_removed: bool,
    ) -> list[CampaignRecord]: ...

    def get_campaign_ctas(
        self,
        customer_id: str,
        campaign_ids: Sequence[str],
        *,
        scope: CtaMatchScope,
    ) -> list[CampaignCtaSummary]: ...

    def suggest_geo_targets(
        self,
        customer_id: str,
        location: LocationInput,
    ) -> list[GeoCandidate]: ...

    def list_location_criteria(
        self,
        customer_id: str,
        campaign_ids: Sequence[str],
    ) -> list[LocationCriterion]: ...

    def mutate_location_exclusions(
        self,
        customer_id: str,
        actions: Sequence[PlannedAction],
        *,
        validate_only: bool,
        partial_failure: bool,
    ) -> MutationReceipt: ...
