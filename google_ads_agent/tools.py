"""JSON-schema registry and dispatcher for AI-agent integrations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import Field

from google_ads_agent.models import (
    CampaignSelector,
    DailyBriefPolicy,
    ExecutionControl,
    LocationInput,
    LocationPerformancePolicy,
    StrictModel,
)
from google_ads_agent.service import GoogleAdsAgent


class AccountContextRequest(StrictModel):
    customer_id: str = Field(description="Ten-digit Google Ads customer ID; dashes are allowed.")


class FindCampaignsRequest(StrictModel):
    customer_id: str
    selector: CampaignSelector


class ResolveGeoTargetsRequest(StrictModel):
    customer_id: str
    locations: list[LocationInput] = Field(min_length=1)


class ExcludeLocationsRequest(StrictModel):
    customer_id: str
    selector: CampaignSelector
    locations: list[LocationInput] = Field(min_length=1)
    control: ExecutionControl


class MeasurementAuditRequest(StrictModel):
    customer_id: str


class DailyAccountBriefRequest(StrictModel):
    customer_id: str
    policy: DailyBriefPolicy = Field(default_factory=DailyBriefPolicy)


class LocationPerformanceReportRequest(StrictModel):
    customer_id: str
    selector: CampaignSelector
    policy: LocationPerformancePolicy


ToolHandler = Callable[[GoogleAdsAgent, StrictModel], Any]


def _account_context(agent: GoogleAdsAgent, request: StrictModel) -> Any:
    typed = AccountContextRequest.model_validate(request)
    return agent.get_account_context(typed.customer_id)


def _find_campaigns(agent: GoogleAdsAgent, request: StrictModel) -> Any:
    typed = FindCampaignsRequest.model_validate(request)
    return agent.find_campaigns(typed.customer_id, typed.selector)


def _resolve_geo_targets(agent: GoogleAdsAgent, request: StrictModel) -> Any:
    typed = ResolveGeoTargetsRequest.model_validate(request)
    return agent.resolve_geo_targets(typed.customer_id, typed.locations)


def _exclude_locations(agent: GoogleAdsAgent, request: StrictModel) -> Any:
    typed = ExcludeLocationsRequest.model_validate(request)
    return agent.exclude_locations_from_matching_campaigns(
        customer_id=typed.customer_id,
        selector=typed.selector,
        locations=typed.locations,
        control=typed.control,
    )


def _measurement_audit(agent: GoogleAdsAgent, request: StrictModel) -> Any:
    typed = MeasurementAuditRequest.model_validate(request)
    return agent.audit_measurement_and_goals(typed.customer_id)


def _daily_account_brief(agent: GoogleAdsAgent, request: StrictModel) -> Any:
    typed = DailyAccountBriefRequest.model_validate(request)
    return agent.daily_account_brief(typed.customer_id, typed.policy)


def _location_performance_report(
    agent: GoogleAdsAgent,
    request: StrictModel,
) -> Any:
    typed = LocationPerformanceReportRequest.model_validate(request)
    return agent.get_location_performance_report(
        typed.customer_id,
        typed.selector,
        typed.policy,
    )


_TOOL_REGISTRY: dict[str, tuple[type[StrictModel], str, ToolHandler]] = {
    "get_account_context": (
        AccountContextRequest,
        "Get account currency, timezone, status, test-account flag, and API version.",
        _account_context,
    ),
    "find_campaigns": (
        FindCampaignsRequest,
        "Find campaigns using deterministic typed conditions and explain each match.",
        _find_campaigns,
    ),
    "resolve_geo_targets": (
        ResolveGeoTargetsRequest,
        "Resolve location names to exact enabled Google geo target constants.",
        _resolve_geo_targets,
    ),
    "audit_measurement_and_goals": (
        MeasurementAuditRequest,
        (
            "Audit conversion actions and effective account/campaign conversion goals "
            "before making performance decisions."
        ),
        _measurement_audit,
    ),
    "daily_account_brief": (
        DailyAccountBriefRequest,
        (
            "Summarize measurement, serving, budget, spend, and conversion anomalies "
            "for the account without changing it."
        ),
        _daily_account_brief,
    ),
    "get_location_performance_report": (
        LocationPerformanceReportRequest,
        (
            "Assess physical user-city performance for selected campaigns and return "
            "reviewable exclusion candidates without changing targeting."
        ),
        _location_performance_report,
    ),
    "exclude_locations_from_matching_campaigns": (
        ExcludeLocationsRequest,
        (
            "Plan or execute approved city/region/country exclusions for campaigns "
            "matching the supplied conditions."
        ),
        _exclude_locations,
    ),
}


def get_agent_tool_schemas() -> list[dict[str, Any]]:
    """Return provider-neutral function definitions with JSON Schema parameters."""

    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": request_model.model_json_schema(),
            },
        }
        for name, (request_model, description, _) in _TOOL_REGISTRY.items()
    ]


def invoke_agent_tool(
    agent: GoogleAdsAgent,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any] | list[dict[str, Any]]:
    """Validate JSON arguments and invoke only a registered high-level tool."""

    try:
        request_model, _, handler = _TOOL_REGISTRY[tool_name]
    except KeyError as exc:
        raise ValueError(f"unknown agent tool: {tool_name}") from exc
    request = request_model.model_validate(arguments)
    result = handler(agent, request)
    if isinstance(result, list):
        return [item.model_dump(mode="json") for item in result]
    return result.model_dump(mode="json")
