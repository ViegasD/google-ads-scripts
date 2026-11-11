from __future__ import annotations

import pytest

from google_ads_agent.errors import GeoResolutionError
from google_ads_agent.geo import resolve_geo_targets
from google_ads_agent.models import LocationInput
from tests.fakes import FakeAdsGateway, geo


def test_geo_resolution_requires_one_exact_candidate(gateway: FakeAdsGateway) -> None:
    result = resolve_geo_targets(
        gateway,
        gateway.account.customer_id,
        [LocationInput(name="Austin", country_code="US", target_type="City")],
    )

    assert result[0].target.resource_name == "geoTargetConstants/1026201"


def test_geo_resolution_rejects_ambiguity(gateway: FakeAdsGateway) -> None:
    gateway.geo_candidates[("austin", "US")] = [
        geo(criterion_id="1"),
        geo(criterion_id="2"),
    ]

    with pytest.raises(GeoResolutionError, match="resolved to 2"):
        resolve_geo_targets(
            gateway,
            gateway.account.customer_id,
            [LocationInput(name="Austin", country_code="US")],
        )
