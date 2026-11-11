# Google Ads API v25: campaigns and budgets function map

Verified against the live Google Ads API v25 discovery document and official documentation on **2026-07-27**.

## Scope

This map includes:

- Live campaign and campaign-budget management.
- Resources attached directly to campaigns: criteria, assets, bid modifiers, goals, labels, shared sets, customizers, groups, and drafts.
- Campaign experiments, Smart Campaign helpers, Performance Max campaign structure, budget recommendations, bidding controls, planning, forecasting, and billing/account budgets.
- Universal read, mutation, batch, validation, and long-running-operation methods used with those resources.

It does not list every ad-group, ad, audience, conversion-upload, or reporting method merely because its data eventually belongs to a campaign. Those are separate API domains. Supporting methods needed to create campaign-linked resources are included in their own section.

## The most important API design rule

Google Ads does not provide REST functions named `getCampaign`, `listCampaigns`, `createCampaign`, `updateCampaign`, or `deleteCampaign`.

- Read resources with `GoogleAdsService.Search` or `SearchStream` and Google Ads Query Language (GAQL).
- Create, update, or remove resources through a service's `Mutate...` method.
- A mutate request contains operations such as `create`, `update` plus an `update_mask`, or `remove`.
- Removed Google Ads resources normally become `REMOVED`; this is not necessarily a physical database deletion.

Base REST URL:

```text
https://googleads.googleapis.com
```

All methods below use API version `v25`.

Common authentication requirements:

```http
Authorization: Bearer ACCESS_TOKEN
developer-token: DEVELOPER_TOKEN
login-customer-id: MANAGER_CUSTOMER_ID
Content-Type: application/json
```

The OAuth scope is `https://www.googleapis.com/auth/adwords`. Omit `login-customer-id` when no manager login is involved.

## 1. Universal functions used by campaigns and budgets

| Canonical method | REST endpoint | Purpose |
|---|---|---|
| `GoogleAdsService.Search` | `POST /v25/customers/{customerId}/googleAds:search` | Run a paginated GAQL query. Use it to read campaigns, budgets, metrics, recommendations, simulations, billing resources, and related objects. |
| `GoogleAdsService.SearchStream` | `POST /v25/customers/{customerId}/googleAds:searchStream` | Run the same GAQL queries and stream all results. Best for larger reads. |
| `GoogleAdsService.Mutate` | `POST /v25/customers/{customerId}/googleAds:mutate` | Execute different resource-operation types atomically, with temporary resource names. Useful for creating a budget and campaign together. |
| `BatchJobService.MutateBatchJob` | `POST /v25/customers/{customerId}/batchJobs:mutate` | Create an asynchronous batch job. |
| `BatchJobService.AddBatchJobOperations` | `POST /v25/{batchJobResourceName}:addOperations` | Add `MutateOperation` objects to a batch job. |
| `BatchJobService.RunBatchJob` | `POST /v25/{batchJobResourceName}:run` | Start the batch job and return a long-running operation. |
| `google.longrunning.Operations.GetOperation` | Long-running-operation endpoint/client helper | Poll a draft promotion, experiment action, or batch job until completion. |
| `BatchJobService.ListBatchJobResults` | `GET /v25/{batchJobResourceName}:listResults` | Read the result or error for every operation in a completed batch job. |

Use `validate_only: true` on supported mutate requests to validate without writing. Use `partial_failure: true` when valid operations should succeed even if another operation fails.

## 2. Core campaign and directly attached resource functions

### Campaign lifecycle

| Canonical method | REST endpoint | Supported actions | Purpose |
|---|---|---|---|
| `CampaignService.MutateCampaigns` | `POST /v25/customers/{customerId}/campaigns:mutate` | Create, update, remove | Create campaigns; change status, dates, name, budget association, bidding, networks, geo settings, URL settings, and campaign-type settings; remove campaigns. |
| `CampaignService.EnablePMaxBrandGuidelines` | `POST /v25/customers/{customerId}/campaigns:enablePMaxBrandGuidelines` | Custom action | Enable Brand Guidelines for Performance Max campaigns. |
| `CampaignGroupService.MutateCampaignGroups` | `POST /v25/customers/{customerId}/campaignGroups:mutate` | Create, update, remove | Create and manage reporting/organizational campaign groups. |
| `CampaignLabelService.MutateCampaignLabels` | `POST /v25/customers/{customerId}/campaignLabels:mutate` | Create, remove | Attach or detach labels from campaigns. |

### Campaign targeting and bid adjustments

| Canonical method | REST endpoint | Supported actions | Purpose |
|---|---|---|---|
| `CampaignCriterionService.MutateCampaignCriteria` | `POST /v25/customers/{customerId}/campaignCriteria:mutate` | Create, update, remove | Manage campaign-level locations, location exclusions, proximity targets, languages, devices, schedules, audiences, negative keywords, topics, placements, and other criterion types. Support varies by criterion and campaign type. |
| `CampaignBidModifierService.MutateCampaignBidModifiers` | `POST /v25/customers/{customerId}/campaignBidModifiers:mutate` | Create, update, remove | Manage campaign-level bid modifiers for supported criterion types. |

See [google-ads-location-exclusions-api.md](./google-ads-location-exclusions-api.md) for the detailed location, zone, and radius map.

### Campaign assets and sets

| Canonical method | REST endpoint | Supported actions | Purpose |
|---|---|---|---|
| `CampaignAssetService.MutateCampaignAssets` | `POST /v25/customers/{customerId}/campaignAssets:mutate` | Create, update, remove | Link assets to a campaign, change mutable link fields, or unlink assets. |
| `CampaignAssetSetService.MutateCampaignAssetSets` | `POST /v25/customers/{customerId}/campaignAssetSets:mutate` | Create, remove | Link or unlink an asset set at campaign level. |
| `AutomaticallyCreatedAssetRemovalService.RemoveCampaignAutomaticallyCreatedAsset` | `POST /v25/customers/{customerId}:removeCampaignAutomaticallyCreatedAsset` | Custom removal action | Remove specified automatically created assets from a campaign. |

### Campaign goals and conversions

| Canonical method | REST endpoint | Supported actions | Purpose |
|---|---|---|---|
| `CampaignConversionGoalService.MutateCampaignConversionGoals` | `POST /v25/customers/{customerId}/campaignConversionGoals:mutate` | Update only | Override whether a conversion category/origin combination is biddable for a campaign. |
| `ConversionGoalCampaignConfigService.MutateConversionGoalCampaignConfigs` | `POST /v25/customers/{customerId}/conversionGoalCampaignConfigs:mutate` | Update only | Configure whether a campaign uses customer-level or campaign-level conversion goals. |
| `CampaignGoalConfigService.MutateCampaignGoalConfigs` | `POST /v25/customers/{customerId}/CampaignGoalConfigs:mutate` | Create, update, remove | Link a v25 `Goal` to a campaign and configure goal-specific optimization settings, including acquisition and retention settings. |

The capitalized `CampaignGoalConfigs` REST path above is intentionally copied from the live v25 discovery document.

In v25, the legacy `CampaignLifecycleGoalService` and `CustomerLifecycleGoalService` were removed. Use `GoalService`, `CampaignGoalConfigService`, and the unified v25 goal schema.

### Campaign customizers and shared sets

| Canonical method | REST endpoint | Supported actions | Purpose |
|---|---|---|---|
| `CampaignCustomizerService.MutateCampaignCustomizers` | `POST /v25/customers/{customerId}/campaignCustomizers:mutate` | Create, remove | Set or remove a campaign-level value for a `CustomizerAttribute`. |
| `CampaignSharedSetService.MutateCampaignSharedSets` | `POST /v25/customers/{customerId}/campaignSharedSets:mutate` | Create, remove | Attach or detach a supported shared set from a campaign. |

## 3. Campaign drafts

| Canonical method | REST endpoint | Purpose |
|---|---|---|
| `CampaignDraftService.MutateCampaignDrafts` | `POST /v25/customers/{customerId}/campaignDrafts:mutate` | Create, update, or remove campaign drafts. |
| `CampaignDraftService.PromoteCampaignDraft` | `POST /v25/{campaignDraftResourceName}:promote` | Promote draft changes into the base campaign. Returns a long-running operation. |
| `CampaignDraftService.ListCampaignDraftAsyncErrors` | `GET /v25/{campaignDraftResourceName}:listAsyncErrors` | List asynchronous errors produced by draft promotion. |

## 4. Campaign experiments

| Canonical method | REST endpoint | Purpose |
|---|---|---|
| `ExperimentService.MutateExperiments` | `POST /v25/customers/{customerId}/experiments:mutate` | Create, update, or remove experiment definitions. |
| `ExperimentArmService.MutateExperimentArms` | `POST /v25/customers/{customerId}/experimentArms:mutate` | Create, update, or remove control/treatment arms and their campaign allocations. |
| `ExperimentService.ScheduleExperiment` | `POST /v25/{experimentResourceName}:scheduleExperiment` | Schedule an experiment and create its experiment campaigns. Returns a long-running operation. |
| `ExperimentService.EndExperiment` | `POST /v25/{experimentResourceName}:endExperiment` | End a running experiment immediately. |
| `ExperimentService.GraduateExperiment` | `POST /v25/{experimentResourceName}:graduateExperiment` | Graduate an experiment and manage budget allocation according to the request. |
| `ExperimentService.PromoteExperiment` | `POST /v25/{experimentResourceName}:promoteExperiment` | Apply the experiment campaign's changes to its base campaign. |
| `ExperimentService.ListExperimentAsyncErrors` | `GET /v25/{experimentResourceName}:listExperimentAsyncErrors` | Read errors from asynchronous experiment actions. |

## 5. Campaign budgets

### Main function

| Canonical method | REST endpoint | Supported actions | Purpose |
|---|---|---|---|
| `CampaignBudgetService.MutateCampaignBudgets` | `POST /v25/customers/{customerId}/campaignBudgets:mutate` | Create, update, remove | Manage campaign delivery budgets. |

`CampaignBudgetService.MutateCampaignBudgets` handles both:

- Average daily budgets: `period = DAILY`, set `amount_micros`.
- Campaign total budgets: `period = CUSTOM_PERIOD`, set `total_amount_micros`.

Important budget fields:

| Field | Meaning |
|---|---|
| `amount_micros` | Average daily amount. `1,000,000` micros equals one account-currency unit. |
| `total_amount_micros` | Total amount across the campaign duration for a custom-period budget. Mutually exclusive with `amount_micros`. |
| `period` | `DAILY` or `CUSTOM_PERIOD`; immutable after creation. |
| `explicitly_shared` | Whether multiple campaigns may share the budget. Average daily budgets default to shared if omitted. |
| `delivery_method` | Delivery pacing; normally `STANDARD`. |
| `aligned_bidding_strategy_id` | Portfolio bidding strategy aligned to the same campaigns as the shared budget. |
| `recommended_budget_amount_micros` | Read-only recommended amount, if available. |
| `reference_count` | Read-only number of campaigns actively using the budget. |

Assigning or changing a campaign's budget is **not** a campaign-budget mutation. Update `Campaign.campaign_budget` through `CampaignService.MutateCampaigns`.

### Budget operation examples

Create an average daily budget:

```json
{
  "operations": [
    {
      "create": {
        "name": "Search daily budget",
        "amountMicros": "50000000",
        "deliveryMethod": "STANDARD",
        "explicitlyShared": false
      }
    }
  ],
  "validateOnly": false
}
```

Update the amount:

```json
{
  "operations": [
    {
      "update": {
        "resourceName": "customers/CUSTOMER_ID/campaignBudgets/BUDGET_ID",
        "amountMicros": "75000000"
      },
      "updateMask": "amount_micros"
    }
  ]
}
```

Assign that budget to a campaign with `CampaignService.MutateCampaigns`:

```json
{
  "operations": [
    {
      "update": {
        "resourceName": "customers/CUSTOMER_ID/campaigns/CAMPAIGN_ID",
        "campaignBudget": "customers/CUSTOMER_ID/campaignBudgets/BUDGET_ID"
      },
      "updateMask": "campaign_budget"
    }
  ]
}
```

### Budget restrictions that affect API design

- A budget actively used by a campaign cannot simply be removed.
- A non-shared budget may be converted to shared, but a shared budget cannot be converted back to non-shared.
- A campaign total budget cannot be shared.
- `period` cannot be changed after budget creation.
- Campaign total budgets require supported campaign/bidding types and fixed campaign dates.
- An average daily budget is not a strict per-day charge cap. Monthly charging behavior uses the average daily budget and Google's serving rules.

## 6. Account budgets, billing, payments, and invoices

Campaign budgets control ad delivery. Account budgets control billing/spend authorization for invoiced accounts. They are different resource families.

| Canonical method | REST endpoint | Purpose |
|---|---|---|
| `AccountBudgetProposalService.MutateAccountBudgetProposal` | `POST /v25/customers/{customerId}/accountBudgetProposals:mutate` | Propose creating, changing, ending, or removing an account-level billing budget; or cancel a pending proposal. |
| `BillingSetupService.MutateBillingSetup` | `POST /v25/customers/{customerId}/billingSetups:mutate` | Create a billing setup or cancel a pending setup. |
| `PaymentsAccountService.ListPaymentsAccounts` | `GET /v25/customers/{customerId}/paymentsAccounts` | List payments accounts usable by the customer. |
| `InvoiceService.ListInvoices` | `GET /v25/customers/{customerId}/invoices` | List invoices for a billing setup and month. |

`AccountBudget` itself is read through GAQL and cannot be mutated directly. To modify it, create an `AccountBudgetProposal` whose `proposal_type` is `UPDATE`, `END`, or `REMOVE`. The proposal operation itself supports `create` and `remove`; it does not have a normal `update` branch.

## 7. Smart Campaign functions

| Canonical method | REST endpoint | Purpose |
|---|---|---|
| `SmartCampaignSuggestService.SuggestSmartCampaignBudgetOptions` | `POST /v25/customers/{customerId}:suggestSmartCampaignBudgetOptions` | Return suggested low, recommended, and high budget options with estimated metrics when available. |
| `SmartCampaignSuggestService.SuggestSmartCampaignAd` | `POST /v25/customers/{customerId}:suggestSmartCampaignAd` | Suggest Smart Campaign ad text. |
| `SmartCampaignSuggestService.SuggestKeywordThemes` | `POST /v25/customers/{customerId}:suggestKeywordThemes` | Suggest keyword themes from business context. |
| `SmartCampaignSuggestService.GenerateAdGroupThemes` | `POST /v25/customers/{customerId}:generateAdGroupThemes` | Generate Smart Campaign ad-group themes. |
| `SmartCampaignSettingService.MutateSmartCampaignSettings` | `POST /v25/customers/{customerId}/smartCampaignSettings:mutate` | Update Smart Campaign business, landing-page, phone, and location-source settings. |
| `SmartCampaignSettingService.GetSmartCampaignStatus` | `GET /v25/{smartCampaignSettingResourceName}:getSmartCampaignStatus` | Return the detailed serving/eligibility status of a Smart Campaign. |

Suggested budgets are advisory. Create the real budget with `CampaignBudgetService.MutateCampaignBudgets`.

## 8. Budget and campaign recommendations

| Canonical method | REST endpoint | Purpose |
|---|---|---|
| `RecommendationService.GenerateRecommendations` | `POST /v25/customers/{customerId}/recommendations:generate` | Generate supported recommendation types from supplied campaign, bidding, budget, and seed information. |
| `RecommendationService.ApplyRecommendation` | `POST /v25/customers/{customerId}/recommendations:apply` | Apply retrieved or generated recommendations. |
| `RecommendationService.DismissRecommendation` | `POST /v25/customers/{customerId}/recommendations:dismiss` | Dismiss recommendations. |
| `RecommendationSubscriptionService.MutateRecommendationSubscription` | `POST /v25/customers/{customerId}/recommendationSubscriptions:mutateRecommendationSubscription` | Subscribe or unsubscribe from supported automatically applied recommendation types. |

Read account-generated recommendations with GAQL from `recommendation`.

Budget-specific recommendation types include:

- `CAMPAIGN_BUDGET`
- `MOVE_UNUSED_BUDGET`
- `MARGINAL_ROI_CAMPAIGN_BUDGET`
- `FORECASTING_CAMPAIGN_BUDGET`

Applying a recommendation can change live spend. Inspect its impact and proposed amounts before calling `ApplyRecommendation`.

## 9. Campaign bidding and temporary bidding controls

| Canonical method | REST endpoint | Purpose |
|---|---|---|
| `BiddingStrategyService.MutateBiddingStrategies` | `POST /v25/customers/{customerId}/biddingStrategies:mutate` | Create, update, or remove portfolio bidding strategies used by campaigns. |
| `BiddingDataExclusionService.MutateBiddingDataExclusions` | `POST /v25/customers/{customerId}/biddingDataExclusions:mutate` | Exclude anomalous conversion data from Smart Bidding for selected campaigns/channels and dates. |
| `BiddingSeasonalityAdjustmentService.MutateBiddingSeasonalityAdjustments` | `POST /v25/customers/{customerId}/biddingSeasonalityAdjustments:mutate` | Apply expected conversion-rate adjustments to selected campaigns/channels and dates. |

Standard bidding strategies are configured directly on a `Campaign` with `CampaignService.MutateCampaigns`. Portfolio strategies are separate `BiddingStrategy` resources and are assigned through the campaign.

## 10. Performance Max campaign structure

Performance Max campaigns require asset-group resources in addition to the campaign.

| Canonical method | REST endpoint | Supported actions | Purpose |
|---|---|---|---|
| `AssetGroupService.MutateAssetGroups` | `POST /v25/customers/{customerId}/assetGroups:mutate` | Create, update, remove | Manage Performance Max asset groups belonging to a campaign. |
| `AssetGroupAssetService.MutateAssetGroupAssets` | `POST /v25/customers/{customerId}/assetGroupAssets:mutate` | Create, update, remove | Link/unlink assets and manage mutable asset-group link fields. |
| `AssetGroupSignalService.MutateAssetGroupSignals` | `POST /v25/customers/{customerId}/assetGroupSignals:mutate` | Create, remove | Add or remove audience/search-theme signals. |
| `AssetGroupListingGroupFilterService.MutateAssetGroupListingGroupFilters` | `POST /v25/customers/{customerId}/assetGroupListingGroupFilters:mutate` | Create, update, remove | Build and manage the product/listing filter tree. |
| `CampaignService.EnablePMaxBrandGuidelines` | `POST /v25/customers/{customerId}/campaigns:enablePMaxBrandGuidelines` | Custom action | Enable PMax Brand Guidelines. |

## 11. Supporting-resource functions commonly required by campaign operations

These methods do not mutate the campaign itself, but they create resources later linked through the campaign methods above.

| Canonical method | REST endpoint | Why it is campaign-related |
|---|---|---|
| `AssetService.MutateAssets` | `POST /v25/customers/{customerId}/assets:mutate` | Create/remove assets before linking them with `CampaignAsset` or `AssetGroupAsset`. |
| `AssetSetService.MutateAssetSets` | `POST /v25/customers/{customerId}/assetSets:mutate` | Create/remove asset sets. |
| `AssetSetAssetService.MutateAssetSetAssets` | `POST /v25/customers/{customerId}/assetSetAssets:mutate` | Add/remove assets in an asset set. |
| `SharedSetService.MutateSharedSets` | `POST /v25/customers/{customerId}/sharedSets:mutate` | Create/remove shared sets before campaign attachment. |
| `SharedCriterionService.MutateSharedCriteria` | `POST /v25/customers/{customerId}/sharedCriteria:mutate` | Populate supported shared sets with criteria. |
| `LabelService.MutateLabels` | `POST /v25/customers/{customerId}/labels:mutate` | Create/remove labels before linking them to campaigns. |
| `CustomizerAttributeService.MutateCustomizerAttributes` | `POST /v25/customers/{customerId}/customizerAttributes:mutate` | Define customizer attributes used by campaign customizers. |
| `GoalService.MutateGoals` | `POST /v25/customers/{customerId}/Goals:mutate` | Create or update v25 unified goals before linking them through `CampaignGoalConfig`. |
| `ConversionActionService.MutateConversionActions` | `POST /v25/customers/{customerId}/conversionActions:mutate` | Manage conversion actions that feed campaign conversion goals. |
| `ConversionValueRuleService.MutateConversionValueRules` | `POST /v25/customers/{customerId}/conversionValueRules:mutate` | Manage individual conversion value rules. |
| `ConversionValueRuleSetService.MutateConversionValueRuleSets` | `POST /v25/customers/{customerId}/conversionValueRuleSets:mutate` | Manage rule sets that may be scoped to campaigns. |
| `GeoTargetConstantService.SuggestGeoTargetConstants` | `POST /v25/geoTargetConstants:suggest` | Resolve names to geographic IDs used by campaign location criteria. |
| `KeywordThemeConstantService.SuggestKeywordThemeConstants` | `POST /v25/keywordThemeConstants:suggest` | Resolve Smart Campaign keyword-theme constants. |
| `BrandSuggestionService.SuggestBrands` | `POST /v25/customers/{customerId}:suggestBrands` | Find brand resources for supported brand criteria. |
| `AssetGenerationService.GenerateText` | `POST /v25/customers/{customerId}/assetGenerations:generateText` | Closed beta: generate text assets for supported campaign/ad contexts. |
| `AssetGenerationService.GenerateImages` | `POST /v25/customers/{customerId}/assetGenerations:generateImages` | Closed beta: generate image assets for supported campaign/ad contexts. |
| `TravelAssetSuggestionService.SuggestTravelAssets` | `POST /v25/customers/{customerId}:suggestTravelAssets` | Suggest supported travel assets for hotel/travel campaign construction. |

The capitalized `Goals` path is also copied from the live v25 discovery document.

## 12. Planning, forecasts, reservations, and previews

These methods model or prepare campaigns; they do not directly update a normal live campaign unless another mutate/action method is called afterward.

### Keyword planning

| Canonical method | REST endpoint | Purpose |
|---|---|---|
| `KeywordPlanService.MutateKeywordPlans` | `POST /v25/customers/{customerId}/keywordPlans:mutate` | Create/update/remove keyword plans. |
| `KeywordPlanCampaignService.MutateKeywordPlanCampaigns` | `POST /v25/customers/{customerId}/keywordPlanCampaigns:mutate` | Manage planned campaigns inside a keyword plan. |
| `KeywordPlanCampaignKeywordService.MutateKeywordPlanCampaignKeywords` | `POST /v25/customers/{customerId}/keywordPlanCampaignKeywords:mutate` | Manage plan-level negative campaign keywords. |
| `KeywordPlanAdGroupService.MutateKeywordPlanAdGroups` | `POST /v25/customers/{customerId}/keywordPlanAdGroups:mutate` | Manage planned ad groups. |
| `KeywordPlanAdGroupKeywordService.MutateKeywordPlanAdGroupKeywords` | `POST /v25/customers/{customerId}/keywordPlanAdGroupKeywords:mutate` | Manage planned keywords. |
| `KeywordPlanIdeaService.GenerateKeywordIdeas` | `POST /v25/customers/{customerId}:generateKeywordIdeas` | Generate keyword ideas. |
| `KeywordPlanIdeaService.GenerateKeywordHistoricalMetrics` | `POST /v25/customers/{customerId}:generateKeywordHistoricalMetrics` | Return historical keyword metrics. |
| `KeywordPlanIdeaService.GenerateKeywordForecastMetrics` | `POST /v25/customers/{customerId}:generateKeywordForecastMetrics` | Forecast a keyword campaign or keyword plan. |

`KeywordPlanCampaign` is not a live `Campaign`.

### Reach planning

| Canonical method | REST endpoint | Purpose |
|---|---|---|
| `ReachPlanService.ListPlannableLocations` | `POST /v25:listPlannableLocations` | List locations supported by Reach Planner. |
| `ReachPlanService.ListPlannableProducts` | `POST /v25:listPlannableProducts` | List plannable ad products. |
| `ReachPlanService.ListPlannableUserInterests` | `POST /v25:listPlannableUserInterests` | List plannable interest audiences. |
| `ReachPlanService.ListPlannableUserLists` | `POST /v25:listPlannableUserLists` | List eligible user lists for planning. |
| `ReachPlanService.GenerateReachForecast` | `POST /v25/customers/{customerId}:generateReachForecast` | Forecast reach, frequency, impressions, and cost for a proposed media plan/campaign mix. |
| `ReachPlanService.GenerateConversionRates` | `POST /v25:generateConversionRates` | Generate conversion-rate suggestions for supported plannable products. |

### Reservations and previews

| Canonical method | REST endpoint | Purpose |
|---|---|---|
| `ReservationService.QuoteCampaigns` | `POST /v25/customers/{customerId}/reservations:quoteCampaigns` | Quote supported reservation campaigns. This service is not publicly available. |
| `ReservationService.BookCampaigns` | `POST /v25/customers/{customerId}/reservations:bookCampaigns` | Book/manage supported reservation campaigns. This service is not publicly available. |
| `ShareablePreviewService.GenerateShareablePreviews` | `POST /v25/customers/{customerId}:generateShareablePreviews` | Generate supported Performance Max asset-group or video/audio ad previews. |

## 13. Reading campaigns, budgets, spend, and forecasts

There are no separate read functions for each resource. Use `Search` or `SearchStream`.

Main GAQL `FROM` resources:

| Resource | Typical use |
|---|---|
| `campaign` | Configuration, status, dates, bidding, linked budget, optimization score, serving status, and metrics. |
| `campaign_budget` | Daily/total amount, sharing, recommendations, reference count, and status. |
| `campaign_asset`, `campaign_asset_set` | Campaign asset links. |
| `campaign_bid_modifier` | Campaign bid adjustments. |
| `campaign_conversion_goal`, `conversion_goal_campaign_config`, `campaign_goal_config` | Campaign goal configuration. |
| `campaign_criterion` | Campaign targeting and exclusions. |
| `campaign_customizer` | Campaign customizer values. |
| `campaign_draft` | Draft state and base/draft campaign links. |
| `campaign_group`, `campaign_label`, `campaign_shared_set` | Organization and attached shared resources. |
| `campaign_simulation` | Read-only bid or budget simulation points for supported campaign/strategy combinations. |
| `experiment`, `experiment_arm` | Experiment state and traffic split. |
| `recommendation` | Account-generated campaign, bidding, and budget recommendations. |
| `account_budget`, `account_budget_proposal`, `billing_setup` | Invoiced-account budget and billing state. |
| `batch_job` | Batch progress and metadata. |

Example campaign and budget query:

```sql
SELECT
  campaign.id,
  campaign.name,
  campaign.status,
  campaign.advertising_channel_type,
  campaign.bidding_strategy_type,
  campaign.campaign_budget,
  campaign.start_date,
  campaign.end_date,
  campaign_budget.id,
  campaign_budget.name,
  campaign_budget.amount_micros,
  campaign_budget.total_amount_micros,
  campaign_budget.period,
  campaign_budget.explicitly_shared,
  campaign_budget.reference_count,
  metrics.impressions,
  metrics.clicks,
  metrics.cost_micros,
  metrics.conversions,
  metrics.conversions_value
FROM campaign
WHERE segments.date BETWEEN '2026-07-01' AND '2026-07-27'
  AND campaign.status != 'REMOVED'
```

Budget utilization is calculated from metrics such as `metrics.cost_micros`; it is not returned by a dedicated “get spend” function.

## 14. Common end-to-end workflows

### Create a standard campaign

1. `CampaignBudgetService.MutateCampaignBudgets`
2. `CampaignService.MutateCampaigns`
3. `CampaignCriterionService.MutateCampaignCriteria`
4. Supporting asset/ad-group/ad methods as required by the campaign type
5. `GoogleAdsService.Search` to verify the created structure

Use `GoogleAdsService.Mutate` with temporary resource names when steps 1–3 should be atomic.

### Change a campaign's budget amount

1. Read `campaign.campaign_budget`.
2. Update the linked `CampaignBudget.amount_micros` or `total_amount_micros` with `MutateCampaignBudgets`.
3. Re-query the campaign and budget.

If the budget is shared, changing it affects every linked campaign.

### Move a campaign to another budget

1. Create or identify the destination budget.
2. Update `Campaign.campaign_budget` using `CampaignService.MutateCampaigns`.
3. Remove the old budget only if it has no active references and removal is supported.

### Apply a budget recommendation

1. Query `recommendation` and inspect the proposed amount/impact.
2. Call `RecommendationService.ApplyRecommendation`, or update the budget directly with `MutateCampaignBudgets`.
3. Re-query the campaign, budget, and recommendation.

### Large multi-campaign update

1. Create a batch job with `MutateBatchJob`.
2. Add campaign/budget operations with `AddBatchJobOperations`.
3. Run it with `RunBatchJob`.
4. Poll the long-running operation.
5. Read `ListBatchJobResults`.

Batch jobs can split submitted operations into sub-batches, so they do not provide the same all-or-nothing semantics as a single atomic `GoogleAdsService.Mutate`.

## 15. Request controls and safety

Common mutate controls:

| Field | Behavior |
|---|---|
| `validate_only` / REST `validateOnly` | Validate without applying changes. |
| `partial_failure` / REST `partialFailure` | Apply valid operations and return per-operation errors for invalid ones. |
| `response_content_type` / REST `responseContentType` | Request resource names only or mutable resources in results where supported. |
| `update_mask` / REST `updateMask` | Exact mutable fields to change in an update operation. |

Recommended production sequence:

1. Search current state.
2. Build the smallest required operations and update masks.
3. Validate with `validateOnly: true`.
4. Execute with an intentional `partialFailure` choice.
5. Store the request ID and per-operation results.
6. Search again to verify state.

## Official references

- [Google Ads API v25 reference](https://developers.google.com/google-ads/api/reference/rpc/v25/overview)
- [Google Ads API discovery document](https://googleads.googleapis.com/$discovery/rest?version=v25)
- [Campaigns overview](https://developers.google.com/google-ads/api/docs/campaigns/overview)
- [Campaign budgets overview](https://developers.google.com/google-ads/api/docs/campaigns/budgets/overview)
- [Create campaign budgets](https://developers.google.com/google-ads/api/docs/campaigns/budgets/create-budgets)
- [Account budgets](https://developers.google.com/google-ads/api/docs/billing/account-budgets)
- [Mutating resources](https://developers.google.com/google-ads/api/docs/mutating/overview)
- [REST mutate operations](https://developers.google.com/google-ads/api/rest/common/mutate)
- [Search and SearchStream](https://developers.google.com/google-ads/api/rest/common/search)
- [Batch processing flow](https://developers.google.com/google-ads/api/docs/batch-processing/flow)
- [Experiments](https://developers.google.com/google-ads/api/docs/experiments/overview)
- [Smart Campaign suggestions](https://developers.google.com/google-ads/api/docs/smart-campaigns/get-suggestions)
- [Recommendations](https://developers.google.com/google-ads/api/docs/recommendations/overview)
- [Bidding strategy types](https://developers.google.com/google-ads/api/docs/campaigns/bidding/strategy-types)
- [Google Ads API v25 release notes](https://developers.google.com/google-ads/api/docs/release-notes)
