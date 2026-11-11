from __future__ import annotations

from google_ads_agent.service import GoogleAdsAgent
from google_ads_agent.tools import get_agent_tool_schemas, invoke_agent_tool


def test_tool_schemas_expose_only_high_level_functions() -> None:
    schemas = get_agent_tool_schemas()
    names = {schema["function"]["name"] for schema in schemas}

    assert names == {
        "audit_measurement_and_goals",
        "daily_account_brief",
        "get_location_performance_report",
        "get_account_context",
        "find_campaigns",
        "resolve_geo_targets",
        "exclude_locations_from_matching_campaigns",
    }
    assert "execute_gaql" not in names
    assert "execute_mutate_operations" not in names


def test_dispatcher_validates_and_invokes_read_tool(agent: GoogleAdsAgent) -> None:
    result = invoke_agent_tool(
        agent,
        "find_campaigns",
        {
            "customer_id": "123-456-7890",
            "selector": {"campaign_ids": ["111"]},
        },
    )

    assert result["matched"][0]["campaign"]["id"] == "111"


def test_dispatcher_invokes_measurement_audit(agent: GoogleAdsAgent) -> None:
    result = invoke_agent_tool(
        agent,
        "audit_measurement_and_goals",
        {"customer_id": "123-456-7890"},
    )

    assert result["readiness"] == "BLOCKED"
