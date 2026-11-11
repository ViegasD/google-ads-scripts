"""Strict geographic-target resolution."""

from __future__ import annotations

from google_ads_agent.errors import GeoResolutionError
from google_ads_agent.gateway import AdsGateway
from google_ads_agent.models import LocationInput, ResolvedLocation


def resolve_geo_targets(
    gateway: AdsGateway,
    customer_id: str,
    locations: list[LocationInput],
) -> list[ResolvedLocation]:
    resolved: list[ResolvedLocation] = []
    seen_resource_names: set[str] = set()

    for location in locations:
        candidates = gateway.suggest_geo_targets(customer_id, location)
        eligible = [
            candidate
            for candidate in candidates
            if candidate.status == "ENABLED"
            and candidate.country_code.upper() == location.country_code
            and candidate.name.casefold() == location.name.casefold()
            and (
                location.target_type is None
                or candidate.target_type.casefold() == location.target_type
            )
        ]
        if len(eligible) != 1:
            raise GeoResolutionError(
                (
                    f"location {location.name!r} resolved to {len(eligible)} exact enabled "
                    "targets; provide a more specific name or target_type"
                ),
                details={
                    "location": location.model_dump(mode="json"),
                    "eligible_candidates": [
                        candidate.model_dump(mode="json") for candidate in eligible
                    ],
                    "all_candidates": [
                        candidate.model_dump(mode="json") for candidate in candidates
                    ],
                },
            )
        candidate = eligible[0]
        if candidate.resource_name in seen_resource_names:
            continue
        seen_resource_names.add(candidate.resource_name)
        resolved.append(ResolvedLocation(requested=location, target=candidate))

    return resolved
