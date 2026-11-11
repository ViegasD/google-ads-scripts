# Google Ads agent tools

Python tools that let an AI agent select campaigns, create an immutable action
plan, request human approval, and execute the approved Google Ads changes.

The initial implementation focuses on campaign discovery, measurement and
performance diagnostics, and approval-gated location exclusions. It
deliberately does not expose raw GAQL or arbitrary mutate operations to an
agent.

## Status

This is an initial implementation. Use it against a Google Ads test account
before enabling production writes.

Implemented:

- Typed campaign, budget, CTA, location, and execution parameters.
- Account context retrieval.
- Campaign selection with machine-readable match reasons.
- Explicit CTA lookup from campaign and ad-group CTA asset links.
- Conversion-action and effective conversion-goal audit.
- Daily measurement, serving, budget, spend, and conversion anomaly brief.
- Physical user-city performance report with CPA or ROAS policies, conversion
  lag, minimum-data, campaign-baseline, and protected-location safeguards.
- Strict geographic target resolution.
- SQLite-backed immutable plans and audit events.
- Location-exclusion `PLAN` and approved `EXECUTE` workflow.
- `validate_only` before returning a plan.
- Expiration, single-use execution, stale-state detection, operation limits,
  idempotency keys, read-after-write verification, and no-op handling.

Not implemented yet:

- Ad-level CTA extraction for every campaign/ad format.
- Metrics-based selectors.
- Budget mutation functions.
- Campaign status, labels, dates, and schedules.
- Multi-worker PostgreSQL plan storage.

## Install

Python 3.11 or newer is required.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## Google Ads credentials

Use the official Google Ads client configuration. Either set the
`GOOGLE_ADS_*` environment variables or keep credentials in a `google-ads.yaml`
file outside source control.

```powershell
$env:GOOGLE_ADS_CONFIGURATION_FILE_PATH = "C:\secure\google-ads.yaml"
```

The expected API client dependency is `google-ads>=31.2.0,<32`, configured for
API version `v25`. Version 31.2.0 is the first Python client release supporting
Google Ads API v25.

## Example

```python
from google_ads_agent import (
    AgentConfig,
    BudgetCondition,
    CampaignSelector,
    CtaCondition,
    ExecutionControl,
    GoogleAdsAgent,
    LocationInput,
    TextCondition,
)

agent = GoogleAdsAgent.from_config(AgentConfig.from_env())

selector = CampaignSelector(
    name=TextCondition(operator="EXACT", value="Campaign X"),
    budget=BudgetCondition(
        period="DAILY",
        amount="100.00",
        currency_code="USD",
        operator="EQUALS",
    ),
    cta=CtaCondition(
        values=["LEARN_MORE"],
        match_scope="ANY_EXPLICIT_SOURCE",
    ),
)

plan = agent.exclude_locations_from_matching_campaigns(
    customer_id="123-456-7890",
    selector=selector,
    locations=[
        LocationInput(name="Austin", country_code="US", target_type="City"),
    ],
    control=ExecutionControl(
        mode="PLAN",
        max_campaigns=10,
        max_operations=50,
        idempotency_key="conversation-42-command-1",
    ),
)

print(plan.model_dump_json(indent=2))

# Only after the user explicitly approves the displayed plan:
result = agent.exclude_locations_from_matching_campaigns(
    customer_id="123-456-7890",
    selector=selector,
    locations=[
        LocationInput(name="Austin", country_code="US", target_type="City"),
    ],
    control=ExecutionControl(
        mode="EXECUTE",
        plan_id=plan.plan_id,
        confirmation="APPROVE",
    ),
)

print(result.model_dump_json(indent=2))
```

The execution call verifies that its customer, selector, and locations are
identical to the planned request. It then re-reads campaign and location state;
any drift returns `STALE_PLAN` without applying the saved operations.

## Performance review example

The performance report is read-only. It returns city exclusion candidates for
review but never changes campaign targeting.

```python
from google_ads_agent import (
    CampaignSelector,
    LocationPerformancePolicy,
)

report = agent.get_location_performance_report(
    customer_id="123-456-7890",
    selector=CampaignSelector(
        campaign_ids=["111"],
    ),
    policy=LocationPerformancePolicy(
        objective="CPA",
        target_cpa="50.00",
        lookback_days=60,
        exclude_recent_days=3,
        minimum_clicks=20,
        minimum_cost="50.00",
        protected_location_names=["Company headquarters city"],
    ),
)

print(report.model_dump_json(indent=2))
```

The report uses `user_location_view` segmented by physical user city. It does
not treat an explicitly targeted location as proof that every user was
physically located there. Resolve measurement-audit warnings before acting on
the recommendations.

## Agent tool schemas

Integrations that use JSON function calling can load the seven registered,
high-level schemas:

```python
from google_ads_agent import get_agent_tool_schemas, invoke_agent_tool

schemas = get_agent_tool_schemas()
result = invoke_agent_tool(
    agent,
    "find_campaigns",
    {
        "customer_id": "123-456-7890",
        "selector": {"campaign_ids": ["111"]},
    },
)
```

`invoke_agent_tool` accepts only registered functions. It does not expose raw
GAQL or raw mutate operations.

## Test

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
```

The unit tests use an in-memory fake Google Ads gateway. Live credentials are
not required.

## Design documents

- [Implementation priorities](google-ads-agent-tools-implementation-priority.md)
- [Campaign and budget API map](google-ads-campaigns-budgets-api-map.md)
- [Location exclusion API map](google-ads-location-exclusions-api.md)
