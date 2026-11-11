from __future__ import annotations

from typing import Any

from google.ads.googleads.client import GoogleAdsClient
from google.auth.credentials import AnonymousCredentials

from google_ads_agent.google_gateway import GoogleAdsApiGateway
from google_ads_agent.models import PlannedAction


class CapturingCampaignCriterionService:
    def __init__(self, real_client: GoogleAdsClient) -> None:
        self.real_client = real_client
        self.request: Any = None

    def mutate_campaign_criteria(self, *, request: Any) -> Any:
        self.request = request
        return self.real_client.get_type(
            "MutateCampaignCriteriaResponse",
            version="v25",
        )


class CapturingClient:
    def __init__(self) -> None:
        self.real_client = GoogleAdsClient(
            AnonymousCredentials(),
            developer_token="test",
            version="v25",
            use_proto_plus=True,
        )
        self.enums = self.real_client.enums
        self.service = CapturingCampaignCriterionService(self.real_client)

    def get_type(self, name: str, version: str) -> Any:
        return self.real_client.get_type(name, version=version)

    def get_service(self, name: str, version: str) -> Any:
        assert name == "CampaignCriterionService"
        assert version == "v25"
        return self.service


def test_live_gateway_builds_v25_negative_location_operation() -> None:
    client = CapturingClient()
    gateway = GoogleAdsApiGateway(client, api_version="v25")
    action = PlannedAction(
        action_id="action_123",
        action_type="CREATE_LOCATION_EXCLUSION",
        campaign_id="111",
        campaign_name="Campaign X",
        campaign_resource_name="customers/1234567890/campaigns/111",
        geo_target_constant="geoTargetConstants/1026201",
        location_name="Austin, Texas, United States",
        before="not excluded",
        after="excluded",
        reason="test",
    )

    receipt = gateway.mutate_location_exclusions(
        "1234567890",
        [action],
        validate_only=True,
        partial_failure=False,
    )

    request = client.service.request
    assert request.customer_id == "1234567890"
    assert request.validate_only is True
    assert request.partial_failure is False
    assert len(request.operations) == 1
    assert request.operations[0].create.campaign == action.campaign_resource_name
    assert request.operations[0].create.negative is True
    assert (
        request.operations[0].create.location.geo_target_constant
        == action.geo_target_constant
    )
    assert receipt.validated_only is True
    assert receipt.errors == []
