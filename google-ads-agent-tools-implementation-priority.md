# Google Ads autonomous agent: Python function implementation priorities

Research and design proposal for Google Ads API **v25**, prepared **2026-07-27**.

## Implementation checklist

Last reviewed: **2026-07-27**.

Checkbox meaning:

- `[x]` is implemented in the current package.
- `[ ]` is not complete. A line marked **Partial** describes the implemented
  subset and the remaining work.

### Package and shared contracts

- [x] Installable Python package targeting Google Ads API v25.
- [x] Environment and `google-ads.yaml` credential loading.
- [x] Typed Pydantic request, selector, policy, plan, and result models.
- [x] Provider-neutral JSON Schema generation for agent function calling.
- [x] Registered-function dispatcher that does not expose raw GAQL or mutate
  operations.
- [x] Account currency, timezone, status, test-account, and manager context.
- [x] Windows IANA timezone data support for account-local reporting windows.

### Priority 0: read, resolve, and select

- [x] `get_account_context`
- [x] `find_campaigns`
  - [x] Campaign ID and name conditions.
  - [x] Status, channel, subtype, label, and bidding-strategy conditions.
  - [x] Daily and custom-period budget conditions with currency validation.
  - [x] CTA conditions with explicit match scope.
  - [x] Experiment exclusion by default.
  - [x] Machine-readable match and skip reasons.
- [ ] `get_campaign_snapshot`
- [x] `resolve_geo_targets`
  - [x] Country and target-type constraints.
  - [x] Enabled-target validation.
  - [x] Ambiguous-result rejection.
- [ ] `get_campaign_ctas` as a separately registered agent function —
  **Partial:** campaign and ad-group CTA assets are already read internally;
  complete ad-level coverage for every supported format remains pending.
- [ ] `get_change_history`

### Measurement and decision support

- [x] `audit_measurement_and_goals`
  - [x] Conversion-action inventory.
  - [x] Primary conversion-action validation.
  - [x] Customer conversion-goal biddability checks.
  - [x] Campaign goal-override detection.
  - [x] `READY`, `WARNING`, and `BLOCKED` readiness result.
- [x] `daily_account_brief`
  - [x] Measurement issues.
  - [x] Campaign serving and primary-status reasons.
  - [x] Available campaign-budget recommendations.
  - [x] Spend-change alerts.
  - [x] Conversion-drop alerts.
  - [x] Optional spend-without-conversions alerts.
  - [x] Account-local date windows and recent-day exclusion.
- [x] `get_location_performance_report`
  - [x] Physical user-city performance from `user_location_view`.
  - [x] CPA and ROAS objectives.
  - [x] Target and campaign-baseline comparisons.
  - [x] Minimum click, cost, and conversion thresholds.
  - [x] Protected locations.
  - [x] Conversion-lag exclusion window.
  - [x] Candidate ranking and maximum-candidate limit.
  - [x] Measurement-readiness warning.
- [ ] `get_budget_pacing_report`
- [ ] `campaign_health_check` as a standalone function —
  **Partial:** health checks are included in `daily_account_brief`.
- [ ] `explain_campaign_selection` as a standalone function —
  **Partial:** `find_campaigns` already returns match and skip reasons.

### Planning, approval, and safety engine

- [x] SQLite `PlanStore`.
- [x] Immutable plans with hashes and expiration.
- [x] Two-call `PLAN` then approved `EXECUTE` protocol.
- [x] Google Ads `validate_only=true` before returning a plan.
- [x] Campaign and operation safety limits.
- [x] Idempotency-key support.
- [x] Single-use execution claims.
- [x] Source-state hashes and stale-plan rejection.
- [x] Partial-failure result handling.
- [x] Read-after-write verification.
- [x] Audit events and Google request IDs.
- [x] No-op detection.
- [ ] PostgreSQL plan storage for multiple workers.

### Priority 1: approval-gated account actions

- [x] `exclude_locations_from_matching_campaigns`
  - [x] City, region, and country geo target constants.
  - [x] Existing-target and existing-exclusion conflict checks.
  - [x] Exact proposed action list.
  - [x] Validated plan, explicit approval, execution, and verification.
  - [x] Negative-radius rejection because Google Ads does not support negative
    proximity criteria.
- [ ] Create an exact-constant bridge from reviewed
  `get_location_performance_report` candidates to an immutable exclusion plan.
- [ ] `include_locations_in_matching_campaigns`
- [ ] `remove_location_exclusions_from_matching_campaigns`
- [ ] `set_campaign_geo_match_mode`
- [ ] `set_campaign_budget_amount`
- [ ] `assign_campaign_budget`
- [ ] `set_campaign_status`
- [ ] `set_campaign_dates`
- [ ] `apply_campaign_labels`
- [ ] `set_campaign_schedule`

### Priority 2: bounded optimization

- [ ] `rebalance_campaign_budgets`
- [ ] `exclude_underperforming_locations`
- [ ] `manage_campaign_negative_keywords`
- [ ] `suggest_negative_keywords_from_search_terms`
- [ ] `set_campaign_bidding_targets`
- [ ] `apply_budget_recommendations`
- [ ] `pause_campaigns_by_performance_rule`
- [ ] `run_campaign_policy`
- [ ] Policy-level cooldowns, rolling action limits, and rollback rules.
- [ ] Scheduled dry runs and alert-only mode.

### Testing and release readiness

- [x] Unit tests using a stateful fake Google Ads gateway.
- [x] Campaign selector and geo-resolution tests.
- [x] Plan-store and location workflow tests.
- [x] Measurement, daily brief, and city-performance policy tests.
- [x] Google Ads v25 negative-location operation construction test.
- [x] Ruff, package compilation, dependency, and wheel-build checks.
- [ ] GAQL contract tests against a Google Ads test account.
- [ ] Integration tests for the complete live `PLAN`/`EXECUTE` workflow.
- [ ] Production credential-separation and least-privilege review.
- [ ] Operational metrics, alerts, retention, and audit export.
- [ ] Staged rollout: test account, internal account, limited production, then
  broader production.

### Immediate next implementation order

- [ ] 1. Convert reviewed city candidates into an exact, approval-gated
  exclusion plan without re-resolving location names.
- [ ] 2. Add `get_campaign_snapshot` for a complete pre-change view.
- [ ] 3. Add `get_budget_pacing_report`.
- [ ] 4. Complete CTA coverage and expose `get_campaign_ctas`.
- [ ] 5. Add include/remove location-targeting actions.
- [ ] 6. Add budget mutation with shared-budget impact analysis.
- [ ] 7. Run live GAQL contract tests on a Google Ads test account.

## Objective

Build a Python library that exposes high-level functions to an AI agent. The agent should only:

1. Select the appropriate function.
2. Convert the user's instruction into typed parameters.
3. Show the function's proposed action list to the user.
4. Call the same function again with the approved plan.

The Python function—not the agent—must:

- Retrieve all required Google Ads data.
- Resolve campaign names, budgets, CTAs, locations, labels, and other conditions.
- Apply deterministic filters.
- Detect ambiguity and unsupported cases.
- Calculate the exact before/after diff.
- Check safety rules and limits.
- Call the Google Ads API with `validate_only=true`.
- Return an approval-ready action plan.
- Recheck for state changes after approval.
- Execute the approved operations.
- Verify the resulting state.
- Store an audit record and Google request IDs.

## Recommended first release

| Order | Layer | Functions/components |
|---:|---|---|
| 1 | Account and selection | `get_account_context`, `find_campaigns`, `get_campaign_snapshot` |
| 2 | Condition resolution | `resolve_geo_targets`, `get_campaign_ctas`, `get_change_history` |
| 3 | Safe execution | `PlanStore`, `plan_validate_execute`, shared selectors and result models |
| 4 | Location actions | `exclude_locations_from_matching_campaigns`, `include_locations_in_matching_campaigns`, `remove_location_exclusions_from_matching_campaigns`, `set_campaign_geo_match_mode` |
| 5 | Budget and state actions | `set_campaign_budget_amount`, `assign_campaign_budget`, `set_campaign_status`, `set_campaign_dates` |
| 6 | Organization and schedule | `apply_campaign_labels`, `set_campaign_schedule` |
| 7 | Decision support | `get_budget_pacing_report`, `get_location_performance_report`, `campaign_health_check`, `explain_campaign_selection` |

Do not begin with autonomous optimization. First make campaign matching, immutable planning, approval, execution, verification, and audit reliable; then build policy-driven optimizers on top.

## Recommended autonomy level

Start at **Level 1: planned changes with human confirmation**.

| Level | Behavior | Initial support? |
|---|---|---:|
| 0 — Read only | Inspect, report, and diagnose. | Yes |
| 1 — Confirmed actions | Build and validate a plan, require user approval, then execute. | **Yes—initial target** |
| 2 — Bounded automation | Execute pre-approved policies within limits, schedules, and cooldowns. | Later |
| 3 — Open autonomy | Agent decides and changes the account without a bounded policy. | No |

The code should be architected for Level 2, but production writes should begin at Level 1.

## Critical design: the two-call approval protocol

A synchronous Python function cannot stop halfway, wait for a person to answer, and then resume its stack safely. Use the same high-level function twice.

### First call: plan

```python
exclude_locations_from_matching_campaigns(
    customer_id="1234567890",
    campaign_selector={
        "name": {"operator": "EXACT", "value": "Campaign X"},
        "budget": {
            "period": "DAILY",
            "amount": 100.00,
            "currency_code": "USD",
            "operator": "EQUALS"
        },
        "cta": {
            "values": ["LEARN_MORE"],
            "match_scope": "ANY_ACTIVE_AD"
        }
    },
    locations=[
        {"name": "City A", "country_code": "US"},
        {"name": "City B", "country_code": "US"}
    ],
    control={
        "mode": "PLAN",
        "max_campaigns": 10,
        "max_operations": 50
    }
)
```

The function returns a saved, immutable plan:

```json
{
  "status": "AWAITING_APPROVAL",
  "plan_id": "plan_01J...",
  "expires_at": "2026-07-27T15:00:00Z",
  "matched_campaigns": 1,
  "actions": [
    {
      "campaign_id": "111",
      "campaign_name": "Campaign X",
      "action": "CREATE_LOCATION_EXCLUSION",
      "location": "City A, State, United States",
      "geo_target_constant": "geoTargetConstants/1234",
      "before": "not excluded",
      "after": "excluded",
      "reason": "campaign matched name, daily budget, and explicit CTA"
    }
  ],
  "skipped": [],
  "warnings": [],
  "validation": {
    "validate_only_passed": true
  },
  "approval_required": true
}
```

### Second call: execute

After the user approves:

```python
exclude_locations_from_matching_campaigns(
    customer_id="1234567890",
    campaign_selector={...},
    locations=[...],
    control={
        "mode": "EXECUTE",
        "plan_id": "plan_01J...",
        "confirmation": "APPROVE"
    }
)
```

Before writing, the function must load the saved plan, verify its hash and expiration, re-read affected resources, and fail with `STALE_PLAN` if campaign, budget, CTA, location, or targeting state changed.

Do not let the agent submit arbitrary prebuilt mutate operations during the execution call. Execution must use the immutable operations saved by the planning call.

## Important semantic issue: CTA is not a universal campaign field

Google Ads does not expose one normalized `campaign.cta` field.

An explicit CTA may come from:

- A `CallToActionAsset`.
- An ad-level reference to a call-to-action asset.
- A campaign/ad-group asset link with `CALL_TO_ACTION` or `CALL_TO_ACTION_SELECTION`.
- An ad-type-specific CTA representation.
- A business message asset.
- An automatically selected CTA, in which case no single fixed explicit value may exist.

The first CTA implementation should return a normalized status for every campaign:

```text
EXPLICIT       A supported explicit CTA was found.
AUTO           Google selects the CTA automatically.
MULTIPLE       Multiple explicit CTA values are active.
NOT_APPLICABLE Campaign/ad type does not use a supported CTA.
UNKNOWN        The current implementation cannot determine it safely.
```

CTA conditions must also define their scope:

```text
ANY_ACTIVE_AD
ALL_ACTIVE_ADS
CAMPAIGN_ASSET_ONLY
ANY_EXPLICIT_SOURCE
```

For the initial version, skip unsupported or ambiguous CTA sources instead of treating them as a match.

## Shared typed models to implement first

Every public tool should reuse the same typed selector, plan, and execution models. Pydantic models are recommended because their JSON schemas can be exposed directly to an agent.

### `CampaignSelector`

```python
class CampaignSelector(BaseModel):
    campaign_ids: list[str] | None = None
    name: TextCondition | None = None
    statuses: list[CampaignStatus] | None = None
    channel_types: list[AdvertisingChannelType] | None = None
    channel_subtypes: list[AdvertisingChannelSubType] | None = None
    labels: list[str] | None = None
    budget: BudgetCondition | None = None
    cta: CtaCondition | None = None
    bidding_strategy_types: list[BiddingStrategyType] | None = None
    date_condition: DateCondition | None = None
    metric_conditions: list[MetricCondition] | None = None
    metric_date_range: DateRange | None = None
    include_experiments: bool = False
    include_removed: bool = False
    allow_multiple: bool = False
```

Selector requirements:

- Exact campaign ID is preferred over name.
- Campaign names are not safe identifiers; duplicates must cause `AMBIGUOUS_SELECTOR` unless `allow_multiple=true`.
- Budget comparisons must include `DAILY` versus `CUSTOM_PERIOD`.
- Human currency amounts must be converted to micros using the customer's currency.
- Decimal equality should support an explicit tolerance.
- Metric conditions must require a date range.
- Experiment and draft campaigns should be excluded by default.

### `ExecutionControl`

```python
class ExecutionControl(BaseModel):
    mode: Literal["PLAN", "EXECUTE"]
    plan_id: str | None = None
    confirmation: Literal["APPROVE"] | None = None
    max_campaigns: int = 10
    max_operations: int = 100
    partial_failure: bool = False
    plan_ttl_seconds: int = 900
    idempotency_key: str | None = None
```

### `ActionPlan`

Required fields:

- `plan_id`
- `tool_name` and tool version
- `customer_id`, currency, and timezone
- normalized input parameters
- selector result and why each campaign matched
- skipped campaigns and exact skip reason
- before/after action list
- affected shared resources and all downstream campaigns
- validation result
- warnings and risk level
- plan hash and source-state hashes
- creation and expiration timestamps
- approval state

### `ActionResult`

Required fields:

- `status`: `NOOP`, `AWAITING_APPROVAL`, `EXECUTED`, `PARTIAL`, `STALE_PLAN`, or `FAILED`
- executed and skipped actions
- Google Ads request IDs
- granular Google Ads errors by operation
- read-after-write verification result
- audit-journal ID
- rollback availability and limitations

## Priority 0: foundation functions

These must exist before any agent-accessible write function.

### 1. `get_account_context`

```python
get_account_context(customer_id: str) -> AccountContext
```

Retrieves and caches:

- Customer ID and descriptive name.
- Currency code and timezone.
- Manager/login relationship.
- Account status and test-account flag.
- Enabled API capabilities relevant to the tool set.
- Current API version.

Why first: all date, currency, budget, scheduling, and safety logic depends on this context.

### 2. `find_campaigns`

```python
find_campaigns(
    customer_id: str,
    selector: CampaignSelector,
    fields: CampaignFieldSet = "SUMMARY"
) -> CampaignMatchResult
```

Responsibilities:

- Build safe GAQL internally; do not accept raw GAQL from the agent.
- Retrieve campaign, campaign budget, labels, dates, bidding, channel, experiment state, and requested metrics.
- Resolve normalized CTAs through additional asset/ad queries when requested.
- Return every match with a machine-readable explanation.
- Return non-matches only when diagnostic detail is requested.
- Enforce maximum rows and pagination/streaming.

This is the common selection engine used by every action function.

### 3. `get_campaign_snapshot`

```python
get_campaign_snapshot(
    customer_id: str,
    campaign_ids: list[str],
    include: set[SnapshotSection]
) -> list[CampaignSnapshot]
```

Snapshot sections:

- `CAMPAIGN`
- `BUDGET`
- `BIDDING`
- `TARGETING`
- `LOCATIONS`
- `ASSETS`
- `CTAS`
- `GOALS`
- `SCHEDULE`
- `METRICS`
- `RECOMMENDATIONS`

The snapshot becomes the source for plan diffs, state hashes, verification, and rollback records.

### 4. `resolve_geo_targets`

```python
resolve_geo_targets(
    customer_id: str,
    locations: list[LocationInput],
    ambiguity_policy: Literal["ERROR", "RETURN_CANDIDATES"] = "ERROR"
) -> GeoResolutionResult
```

Responsibilities:

- Call `GeoTargetConstantService.SuggestGeoTargetConstants`.
- Require country codes where names are ambiguous.
- Verify `ENABLED` status and target type.
- Return canonical names, IDs, parents, and reach where available.
- Never silently select the first name match.

### 5. `get_campaign_ctas`

```python
get_campaign_ctas(
    customer_id: str,
    campaign_ids: list[str],
    active_ads_only: bool = True
) -> list[CampaignCtaSummary]
```

Responsibilities:

- Read explicit CTA assets and ad references supported by the current implementation.
- Normalize CTA enums.
- Report the source resource and serving status.
- Distinguish `AUTO`, `MULTIPLE`, `NOT_APPLICABLE`, and `UNKNOWN`.
- Never infer a CTA from ad copy text.

### 6. `get_change_history`

```python
get_change_history(
    customer_id: str,
    resource_types: list[str],
    since: datetime,
    campaign_ids: list[str] | None = None
) -> ChangeHistoryResult
```

Use `change_event` for field-level history and `change_status` for synchronization:

- `change_event` queries must use a finite window within the past 30 days and a `LIMIT` of at most 10,000. Continue from the final timestamp when more rows exist.
- `change_status` queries must use a date within the past 90 days and a `LIMIT` of at most 10,000.
- Either source can take up to about three minutes to reflect a new change, and neither is a substitute for the application's own audit log.

This function is for audit and drift detection, not as the sole rollback mechanism.

### 7. Internal `PlanStore`

Not exposed directly to the agent.

Recommended initial implementation:

- SQLite for local development; PostgreSQL for multi-worker production.
- Canonical JSON for normalized input and actions.
- SHA-256 plan and source-state hashes.
- Short plan expiration.
- Single-use execution token.
- Unique application-level idempotency key.
- Status transition lock: `CREATED → VALIDATED → APPROVED → EXECUTING → EXECUTED`.

### 8. Internal `plan_validate_execute` engine

Every write function should delegate to the same engine:

```python
plan_validate_execute(
    tool_name,
    customer_id,
    normalized_request,
    selector_fn,
    planner_fn,
    validator_fn,
    executor_fn,
    verifier_fn,
    control
) -> ActionPlan | ActionResult
```

Required behavior:

1. Validate local schema and policy.
2. Select campaigns.
3. Fetch complete current state.
4. Build an idempotent diff.
5. Enforce action limits and shared-resource expansion.
6. Call the relevant mutate request with `validate_only=true`.
7. Save and return the plan.
8. On execution, lock and reload the plan.
9. Recheck current state and plan hash.
10. Execute.
11. Parse partial failures if enabled.
12. Read after write.
13. Journal the result and request IDs.

## Priority 1: first user-facing action functions

These provide broad value while keeping the mutation surface understandable.

### 1. `exclude_locations_from_matching_campaigns`

```python
exclude_locations_from_matching_campaigns(
    customer_id: str,
    campaign_selector: CampaignSelector,
    locations: list[LocationInput],
    control: ExecutionControl,
    negative_match_type: Literal["PRESENCE"] = "PRESENCE"
) -> ActionPlan | ActionResult
```

Internal workflow:

1. Resolve location names.
2. Find campaigns matching name/ID, budget, CTA, channel, labels, or metrics.
3. Read current `LOCATION` and `PROXIMITY` criteria.
4. Skip already excluded locations.
5. Reject target/exclude conflicts.
6. Reject radius exclusions because negative `ProximityInfo` is unsupported.
7. Build negative `LocationInfo` criteria.
8. Validate, plan, approve, execute, and verify.

This directly implements the example from the product requirement.

### 2. `include_locations_in_matching_campaigns`

```python
include_locations_in_matching_campaigns(
    customer_id: str,
    campaign_selector: CampaignSelector,
    locations: list[LocationInput],
    replace_existing: bool,
    control: ExecutionControl
) -> ActionPlan | ActionResult
```

Default `replace_existing=false`. Replacing all positive locations is higher risk and should require a separate warning plus a lower operation cap.

### 3. `remove_location_exclusions_from_matching_campaigns`

```python
remove_location_exclusions_from_matching_campaigns(
    customer_id: str,
    campaign_selector: CampaignSelector,
    locations: list[LocationInput],
    control: ExecutionControl
) -> ActionPlan | ActionResult
```

Negative criteria are immutable, so removal uses their exact campaign-criterion resource names.

### 4. `set_campaign_budget_amount`

```python
set_campaign_budget_amount(
    customer_id: str,
    campaign_selector: CampaignSelector,
    change: BudgetChange,
    control: ExecutionControl
) -> ActionPlan | ActionResult
```

`BudgetChange` should support:

```text
SET_AMOUNT
INCREASE_AMOUNT
DECREASE_AMOUNT
INCREASE_PERCENT
DECREASE_PERCENT
```

Mandatory controls:

- Expected currency.
- Daily versus campaign-total budget.
- Minimum and maximum resulting amount.
- Maximum percentage change.
- Shared-budget policy: `ERROR`, `EXPAND_AND_SHOW_ALL`, or `ALLOW`.
- Experiment-budget policy.
- Cooldown since the last automated budget change.

If a budget is shared, the plan must show every campaign affected—even campaigns that did not match the original selector.

### 5. `assign_campaign_budget`

```python
assign_campaign_budget(
    customer_id: str,
    campaign_selector: CampaignSelector,
    destination: ExistingBudget | NewBudget,
    control: ExecutionControl
) -> ActionPlan | ActionResult
```

Use `GoogleAdsService.Mutate` with temporary resource names when creating and assigning a new budget atomically. Otherwise, a failed assignment can leave an orphaned budget.

### 6. `set_campaign_status`

```python
set_campaign_status(
    customer_id: str,
    campaign_selector: CampaignSelector,
    status: Literal["ENABLED", "PAUSED"],
    control: ExecutionControl
) -> ActionPlan | ActionResult
```

Initial implementation should not expose `REMOVED`. Enabling is higher risk than pausing and must verify that required ads, targeting, budget, dates, and policy status are ready.

### 7. `set_campaign_dates`

```python
set_campaign_dates(
    customer_id: str,
    campaign_selector: CampaignSelector,
    start_at: datetime | None,
    end_at: datetime | None,
    control: ExecutionControl
) -> ActionPlan | ActionResult
```

Convert user dates in the customer account's timezone. Detect immutable/past-date constraints and interactions with campaign-total budgets.

### 8. `set_campaign_geo_match_mode`

```python
set_campaign_geo_match_mode(
    customer_id: str,
    campaign_selector: CampaignSelector,
    positive: Literal["PRESENCE", "PRESENCE_OR_INTEREST"],
    negative: Literal["PRESENCE"],
    control: ExecutionControl
) -> ActionPlan | ActionResult
```

This manages `Campaign.geo_target_type_setting`. Do not offer negative `PRESENCE_OR_INTEREST` initially because it is generally unsupported for most campaign types.

### 9. `apply_campaign_labels`

```python
apply_campaign_labels(
    customer_id: str,
    campaign_selector: CampaignSelector,
    add: list[str] | None = None,
    remove: list[str] | None = None,
    create_missing: bool = False,
    control: ExecutionControl = ...
) -> ActionPlan | ActionResult
```

Labels provide a low-risk mechanism for marking campaigns as managed, exempt, under review, or assigned to a policy.

Recommended system labels:

```text
agent:managed
agent:manual-only
agent:budget-auto
agent:geo-auto
agent:review-required
```

### 10. `set_campaign_schedule`

```python
set_campaign_schedule(
    customer_id: str,
    campaign_selector: CampaignSelector,
    schedule: WeeklySchedule,
    replace_existing: bool,
    control: ExecutionControl
) -> ActionPlan | ActionResult
```

The function must calculate criterion create/remove operations, validate supported intervals, use account timezone, and show the complete resulting weekly schedule.

## Priority 1: first read-only decision functions

These should be implemented alongside the action functions because they provide the evidence users need before approving changes.

### `get_budget_pacing_report`

```python
get_budget_pacing_report(
    customer_id: str,
    campaign_selector: CampaignSelector,
    date_range: DateRange,
    projection_end: date | None = None
) -> BudgetPacingReport
```

Return:

- Budget period and current amount.
- Spend so far.
- Expected spend at current pace.
- Pacing percentage.
- Remaining days and projected overspend/underspend.
- Shared-budget allocation warning.
- Conversion, CPA, ROAS, and impression-share context when requested.

Do not call daily budget a strict daily spend cap.

### `get_location_performance_report`

```python
get_location_performance_report(
    customer_id: str,
    campaign_selector: CampaignSelector,
    date_range: DateRange,
    location_level: Literal["COUNTRY", "REGION", "CITY", "POSTAL_CODE"]
) -> LocationPerformanceReport
```

Keep user physical location and location of interest distinct. A report should never label inferred geographic performance as exact GPS data.

### `campaign_health_check`

```python
campaign_health_check(
    customer_id: str,
    campaign_selector: CampaignSelector,
    date_range: DateRange
) -> CampaignHealthReport
```

Initial checks:

- Campaign serving/primary status and reasons.
- Budget constrained or missing.
- No enabled ads/ad groups.
- No positive locations or unintended worldwide targeting.
- Conflicting/obsolete location criteria.
- Disapproved or non-serving assets.
- Invalid/past dates.
- Missing conversion configuration.
- Shared budget and experiment risks.
- Recent unexpected external changes.

### `explain_campaign_selection`

```python
explain_campaign_selection(
    customer_id: str,
    selector: CampaignSelector
) -> CampaignMatchResult
```

This exposes the exact selector engine output so the user can verify why a natural-language instruction matched or skipped each campaign before any action planning.

## Priority 2: optimization functions after Priority 1 is stable

These functions turn performance data into changes and need stronger statistical and policy safeguards.

### `rebalance_campaign_budgets`

Moves budget among a bounded set of campaigns according to a declared strategy.

Required parameters:

- Total portfolio budget cap.
- Date range and attribution-lag exclusion.
- Objective: conversions, conversion value, CPA, ROAS, clicks, or impression share.
- Minimum data thresholds.
- Per-campaign minimum/maximum.
- Maximum change per run.
- Shared-budget handling.
- Cooldown and change frequency.

The function should produce recommendations first and never optimize from tiny samples.

### `exclude_underperforming_locations`

Uses a location-performance report and a rule such as:

```text
cost >= 100
conversions = 0
clicks >= 30
observation_days >= 14
```

It must:

- Require minimum volume and a date window.
- Distinguish physical-location reporting from interest reporting.
- Resolve the report row to a targetable `GeoTargetConstant`.
- Avoid excluding a parent location when only a child row underperformed.
- Enforce a maximum excluded share of spend/reach.

### `manage_campaign_negative_keywords`

Add or remove campaign negative keywords using explicit match types.

Do not initially mix search-term recommendation logic into this write function. Let another read-only function propose candidates.

### `suggest_negative_keywords_from_search_terms`

Read-only first. Return terms with costs and conversion evidence, suggested match type, conflicts, and estimated scope. Human approval then feeds exact candidates into `manage_campaign_negative_keywords`.

### `set_campaign_bidding_targets`

Manage supported tCPA/tROAS or other campaign bidding targets with:

- Current strategy compatibility checks.
- Portfolio versus standard strategy detection.
- Minimum conversion data.
- Maximum percentage change.
- Cooldown.
- Budget-constrained warning.
- Experiment exclusion.

### `apply_budget_recommendations`

Retrieve and optionally apply only these types:

```text
CAMPAIGN_BUDGET
MOVE_UNUSED_BUDGET
MARGINAL_ROI_CAMPAIGN_BUDGET
FORECASTING_CAMPAIGN_BUDGET
```

The plan must include Google's predicted impact, current amount, proposed amount, and all affected campaigns.

### `pause_campaigns_by_performance_rule`

This is riskier than it appears. Require:

- Minimum impressions/clicks/cost.
- A conversion-lag buffer.
- Date range.
- Comparison baseline.
- Maximum number/percentage of campaigns paused.
- Explicit handling for new campaigns.
- Cooldown.

### `run_campaign_policy`

Implement only after the individual actions are reliable.

```python
run_campaign_policy(
    customer_id: str,
    policy_id: str,
    mode: Literal["PLAN", "EXECUTE"]
) -> PolicyRunResult
```

A stored policy should contain:

- Campaign selector.
- Trigger conditions.
- Action type and parameters.
- Schedule.
- Observation window.
- Cooldown.
- Maximum actions and financial impact.
- Approval mode.
- Exempt labels.
- Start/end validity.

The rules engine should call the same specific high-level functions; it should not create raw API operations itself.

## Priority 3: defer until the management layer is mature

### Full campaign creation

Implement separate functions by campaign type:

```text
create_search_campaign
create_performance_max_campaign
create_demand_gen_campaign
create_smart_campaign
```

Do not build one universal `create_campaign` function. Required resources and constraints differ substantially by campaign type.

### Campaign cloning

`clone_campaign` must deeply copy compatible budgets, targeting, ad groups, ads, assets, URLs, goals, and type-specific resources. This is not a simple Campaign mutation.

### Permanent removal

Do not initially expose `remove_campaign` or broad remove functions to the agent. Prefer pause, label, and human review.

### Arbitrary GAQL or raw mutate tools

Keep these developer/admin-only:

```text
execute_gaql
execute_mutate_operations
```

Giving an agent unrestricted GAQL is acceptable only for read-only expert mode with query validation and row limits. Giving an agent unrestricted mutate operations bypasses the selector, approval, and safety architecture.

## Cross-cutting safety requirements

### Scope and ambiguity

- Require one `customer_id`; never mutate multiple accounts in one tool call.
- Remove dashes from normalized customer IDs.
- Default `allow_multiple=false`.
- Require explicit country codes for ambiguous geographic names.
- Require campaign budget period and currency for amount conditions.
- Return `NOOP` when desired state already exists.

### Financial guardrails

- Default maximum budget change: configurable, initially no more than 20% per execution.
- Require absolute minimum and maximum budget values.
- Detect every shared-budget consumer.
- Block total portfolio budget increases beyond a provided cap.
- Never apply a Google recommendation solely because it exists.
- Record human-readable amounts and micros.

### Targeting guardrails

- Block target/exclude conflicts.
- Never approximate an unsupported radius exclusion silently.
- Never create custom polygon assumptions.
- Set a maximum number of criteria changed per campaign.
- Show the final positive and negative location set, not only the diff.

### Performance-rule guardrails

- Require date range and minimum sample size.
- Support an attribution-lag exclusion window.
- Use account timezone.
- Treat conversions and conversion value according to the account's configured goals.
- Apply cooldowns to prevent oscillation.
- Compare with previous automated actions before recommending the opposite change.

### Mutation behavior

- Use sparse updates and exact field masks.
- Use `validate_only=true` before every planned mutation when supported.
- Default `partial_failure=false`.
- Enable partial failure only when operations are independent and the response parser maps each error back to its action.
- Use `GoogleAdsService.Mutate` for atomic cross-resource creation.
- Do not assume batch jobs are atomic; Google may split them into sub-batches.
- Respect the API's 10,000 mutate-operation request limit, but set much lower agent-facing limits.
- Billing and account-budget mutate requests allow only one operation per request.

### Retry and idempotency

- Retry only transient server failures with exponential backoff and jitter.
- Do not blindly retry validation, authorization, not-found, or failed-precondition errors.
- Implement application-level idempotency using a request fingerprint, plan journal, state diff, and read-after-write verification.
- On retry, re-read state and omit actions already applied.

### Audit and observability

Log:

- Tool name and version.
- Agent/user request correlation ID.
- Customer ID.
- Normalized parameters.
- Selected campaigns and selection reasons.
- Before/after values.
- Google API method and operation index.
- Google `request-id`.
- Latency, retry count, and detailed failure.
- Approval actor and timestamp.
- Verification outcome.

Redact OAuth credentials, refresh tokens, developer tokens, and personally identifiable data.

## Proposed Python package structure

```text
google_ads_agent/
├── __init__.py
├── config.py
├── client.py
├── errors.py
├── models/
│   ├── selectors.py
│   ├── plans.py
│   ├── results.py
│   ├── budgets.py
│   ├── locations.py
│   └── policies.py
├── readers/
│   ├── accounts.py
│   ├── campaigns.py
│   ├── budgets.py
│   ├── targeting.py
│   ├── assets.py
│   ├── ctas.py
│   ├── metrics.py
│   └── changes.py
├── selectors/
│   ├── campaign_selector.py
│   └── predicates.py
├── planning/
│   ├── diff.py
│   ├── safety.py
│   ├── validation.py
│   └── engine.py
├── execution/
│   ├── mutations.py
│   ├── retries.py
│   ├── verification.py
│   └── batch.py
├── tools/
│   ├── campaign_search.py
│   ├── locations.py
│   ├── budgets.py
│   ├── statuses.py
│   ├── dates.py
│   ├── labels.py
│   ├── schedules.py
│   └── reports.py
├── policies/
│   ├── engine.py
│   └── scheduler.py
└── audit/
    ├── models.py
    ├── plan_store.py
    └── journal.py
```

## Recommended implementation order

### Milestone 1 — read and select

1. Google Ads client/authentication and logging.
2. Shared Pydantic models.
3. `get_account_context`.
4. `find_campaigns`.
5. `get_campaign_snapshot`.
6. `get_campaign_ctas`.
7. `resolve_geo_targets`.
8. Selector tests against a Google Ads test account.

Exit criterion: a user instruction can be converted into a selector and the system explains exactly which campaigns match and why.

### Milestone 2 — plan and approve

1. `PlanStore`.
2. Diff engine.
3. Safety policies and operation caps.
4. `validate_only` integration.
5. Immutable plan hashing and expiration.
6. Approval and stale-plan checks.
7. Audit journal.

Exit criterion: the system returns a validated action list but cannot yet execute production changes.

### Milestone 3 — first writes

Implement in this order:

1. `apply_campaign_labels`
2. `set_campaign_status` with `PAUSED` first
3. `exclude_locations_from_matching_campaigns`
4. `remove_location_exclusions_from_matching_campaigns`
5. `set_campaign_geo_match_mode`
6. `set_campaign_budget_amount`
7. `assign_campaign_budget`
8. `set_campaign_dates`
9. `set_campaign_schedule`

Exit criterion: every action supports plan, API validation, approval, execution, verification, idempotent re-run, and detailed audit.

### Milestone 4 — reporting and recommendations

1. `get_budget_pacing_report`
2. `get_location_performance_report`
3. `campaign_health_check`
4. `suggest_negative_keywords_from_search_terms`
5. `apply_budget_recommendations`

### Milestone 5 — bounded automation

1. Stored policies.
2. Cooldowns and attribution-lag handling.
3. Scheduled read-only policy evaluation.
4. Scheduled plan generation.
5. Human-approved execution.
6. Only then, opt-in auto-execution for narrowly bounded policies.

## Testing strategy

### Unit tests

- Selector predicates.
- Currency-to-micros conversion.
- Budget equality and tolerance.
- CTA normalization.
- Geo ambiguity.
- Before/after diff.
- Shared-budget expansion.
- State hashing.
- Plan expiration.
- Operation-to-error mapping.
- Retry classification.

### Contract tests

- Validate Pydantic-generated tool schemas.
- Record sanitized Google Ads responses.
- Verify GAQL field compatibility.
- Verify every mutate request supports the fields the tool sends.

### Integration tests

Use Google Ads test accounts that are not accessible by production credentials.

Test:

- No-op re-execution.
- Ambiguous campaign name.
- Duplicate location.
- Already excluded location.
- Target/exclude conflict.
- Unsupported radius exclusion.
- Shared budget affecting unmatched campaigns.
- Stale plan after manual UI change.
- Partial failure mapping.
- API timeout after a successful server-side mutation.
- Read-after-write mismatch.

### Production rollout

1. Read-only on production.
2. Plan-only on production.
3. Writes restricted to labeled test campaigns.
4. Low operation and budget limits.
5. Expand campaign types gradually.

## Definition of done for every public action function

A function is not complete until it:

- Uses typed, agent-friendly parameters.
- Rejects ambiguous selectors.
- Explains every match and skip.
- Produces an idempotent diff.
- Detects shared-resource side effects.
- Enforces local safety policies.
- Calls Google Ads `validate_only` when available.
- Requires a valid saved approval plan.
- Detects stale plans.
- Executes with intentional transaction/partial-failure semantics.
- Maps every operation to a result.
- Verifies state after execution.
- Stores request IDs and an audit record.
- Has unit, contract, and test-account integration tests.
- Documents campaign-type limitations.

## Official references

- [Google Ads API v25 reference](https://developers.google.com/google-ads/api/reference/rpc/v25/overview)
- [Mutating resources](https://developers.google.com/google-ads/api/docs/mutating/overview)
- [Mutate best practices and temporary resource names](https://developers.google.com/google-ads/api/docs/mutating/best-practices)
- [Partial failure](https://developers.google.com/google-ads/api/docs/best-practices/partial-failures)
- [Testing and `validate_only`](https://developers.google.com/google-ads/api/docs/best-practices/testing)
- [API limits and quotas](https://developers.google.com/google-ads/api/docs/best-practices/quotas)
- [Error handling and request IDs](https://developers.google.com/google-ads/api/docs/best-practices/understand-api-errors)
- [Production logging](https://developers.google.com/google-ads/api/docs/productionize/logging)
- [Campaign budgets overview](https://developers.google.com/google-ads/api/docs/campaigns/budgets/overview)
- [Campaign budget assignment](https://developers.google.com/google-ads/api/docs/campaigns/budgets/assign-budgets)
- [Campaign budget restrictions](https://developers.google.com/google-ads/api/docs/campaigns/budgets/restrictions-errors)
- [Location targeting](https://developers.google.com/google-ads/api/docs/targeting/location-targeting)
- [Assets and CTA asset types](https://developers.google.com/google-ads/api/docs/assets/overview)
- [Change Event](https://developers.google.com/google-ads/api/docs/change-event)
- [Change Status](https://developers.google.com/google-ads/api/docs/change-status)
- [Search and SearchStream](https://developers.google.com/google-ads/api/rest/common/search)
- [Search campaign creation requirements](https://developers.google.com/google-ads/api/docs/campaigns/search-campaigns/getting-started)
