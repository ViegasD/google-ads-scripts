# Google Ads API: campaign location, zone, and radius exclusions

Verified against Google Ads API **v25** on **2026-07-26**.

## Short answer

Yes, a campaign can exclude a Google-supported geographic location through the API. Create a campaign `LocationInfo` criterion and set `CampaignCriterion.negative` to `true`.

There are important limits:

| Requirement | Supported? | API representation |
|---|---:|---|
| Exclude a country, state/region, city, postal area, or another Google-defined geographic area | Yes | Negative `CampaignCriterion` containing `LocationInfo` |
| Target a radius around an address or latitude/longitude | Yes | Positive `CampaignCriterion` containing `ProximityInfo` |
| Exclude a radius around an address or latitude/longitude | **No** | Google explicitly does not allow negative `ProximityInfo` |
| Exclude a custom polygon, GeoJSON shape, drawn zone, or arbitrary boundary | **No direct API support** | No polygon/geofence campaign criterion exists |
| Exclude a location group | No | `LocationGroupInfo` is positive-only |
| Change an existing exclusion in place | No | Its location and `negative` flag are immutable; remove and recreate it |
| Apply one location exclusion account-wide | No | Location criteria are not supported by `CustomerNegativeCriterionService` |

“Zone” is therefore supported only when the zone exists in Google's geo-target catalog as a `GeoTargetConstant`. For a custom zone, the closest available approach is to exclude the supported cities, postal areas, regions, or other catalog locations that cover it. That approximation will not produce an exact custom boundary.

## All relevant API methods

The names below are the canonical gRPC/client-library method names. Most REST equivalents use HTTP `POST`; result-listing and long-running-operation reads use `GET`.

| API method | REST v25 endpoint | Purpose |
|---|---|---|
| `GeoTargetConstantService.SuggestGeoTargetConstants` | `/v25/geoTargetConstants:suggest` | Resolve human-readable location names to `geoTargetConstants/{id}` resources. It accepts either location names or existing geo-target resource names. |
| `GoogleAdsService.Search` | `/v25/customers/{customerId}/googleAds:search` | Read geo constants, campaign criteria, and campaign geo settings with paginated GAQL results. |
| `GoogleAdsService.SearchStream` | `/v25/customers/{customerId}/googleAds:searchStream` | Read the same data as `Search`, but stream the complete result set. Usually the better choice for bulk reads. |
| `CampaignCriterionService.MutateCampaignCriteria` | `/v25/customers/{customerId}/campaignCriteria:mutate` | Create a positive location, create a negative location exclusion, create a positive proximity/radius, or remove criteria. This is the main write method. |
| `CampaignService.MutateCampaigns` | `/v25/customers/{customerId}/campaigns:mutate` | Update `Campaign.geo_target_type_setting`, which controls whether presence and/or interest is used when matching users to locations. |
| `GoogleAdsService.Mutate` | `/v25/customers/{customerId}/googleAds:mutate` | Optional atomic wrapper for operations involving multiple resource types. It can carry campaign and campaign-criterion operations together. |
| `BatchJobService.MutateBatchJob` | `POST /v25/customers/{customerId}/batchJobs:mutate` | Optional: create an asynchronous job for a very large set of mutations by using its `create` operation. |
| `BatchJobService.AddBatchJobOperations` | `POST /v25/customers/{customerId}/batchJobs/{batchJobId}:addOperations` | Optional: add campaign-criterion mutations to a batch job. |
| `BatchJobService.RunBatchJob` | `POST /v25/customers/{customerId}/batchJobs/{batchJobId}:run` | Optional: start the batch job. |
| `Operations.GetOperation` | `GET /v25/{operationName}` | Optional: poll the long-running operation returned by `RunBatchJob`. |
| `BatchJobService.ListBatchJobResults` | `GET /v25/customers/{customerId}/batchJobs/{batchJobId}:listResults` | Optional: retrieve per-operation results after the job finishes. |

Adjacent method: `AdGroupCriterionService.MutateAdGroupCriteria` manages supported ad-group-level criteria. It is not needed for a campaign-level exclusion and should not be confused with `CampaignCriterionService`.

There is no separate `excludeLocation`, `excludeRadius`, or `deleteLocation` function. Exclusion is a `create` operation with `negative: true`; deletion is a `remove` operation inside `MutateCampaignCriteria`.

## Common headers

```http
Content-Type: application/json
Authorization: Bearer ACCESS_TOKEN
developer-token: DEVELOPER_TOKEN
login-customer-id: MANAGER_CUSTOMER_ID
```

`login-customer-id` is needed when authenticating through a manager account. IDs in headers and resource names must not contain dashes. The OAuth scope is:

```text
https://www.googleapis.com/auth/adwords
```

## 1. Find the Google location ID

Use `GeoTargetConstantService.SuggestGeoTargetConstants`:

```http
POST https://googleads.googleapis.com/v25/geoTargetConstants:suggest
```

```json
{
  "locale": "pt",
  "countryCode": "BR",
  "locationNames": {
    "names": ["Araguaína", "Palmas"]
  }
}
```

Inspect each returned suggestion:

- `geoTargetConstant.resourceName`
- `geoTargetConstant.name`
- `geoTargetConstant.canonicalName`
- `geoTargetConstant.countryCode`
- `geoTargetConstant.targetType`
- `geoTargetConstant.status`

Only use the intended result and normally require `status == ENABLED`. Google can mark old locations as `REMOVAL_PLANNED`.

The complete downloadable catalog is also available from Google's [geo-target reference data](https://developers.google.com/google-ads/api/reference/data/geotargets).

## 2. List the current campaign location and radius criteria

Use `GoogleAdsService.Search` or `SearchStream` with this GAQL query:

```sql
SELECT
  campaign_criterion.resource_name,
  campaign_criterion.campaign,
  campaign_criterion.criterion_id,
  campaign_criterion.type,
  campaign_criterion.status,
  campaign_criterion.negative,
  campaign_criterion.location.geo_target_constant,
  campaign_criterion.proximity.geo_point.latitude_in_micro_degrees,
  campaign_criterion.proximity.geo_point.longitude_in_micro_degrees,
  campaign_criterion.proximity.radius,
  campaign_criterion.proximity.radius_units
FROM campaign_criterion
WHERE campaign_criterion.campaign =
  'customers/CUSTOMER_ID/campaigns/CAMPAIGN_ID'
  AND campaign_criterion.type IN ('LOCATION', 'PROXIMITY')
```

REST:

```http
POST https://googleads.googleapis.com/v25/customers/CUSTOMER_ID/googleAds:searchStream
```

```json
{
  "query": "SELECT campaign_criterion.resource_name, campaign_criterion.campaign, campaign_criterion.criterion_id, campaign_criterion.type, campaign_criterion.status, campaign_criterion.negative, campaign_criterion.location.geo_target_constant, campaign_criterion.proximity.geo_point.latitude_in_micro_degrees, campaign_criterion.proximity.geo_point.longitude_in_micro_degrees, campaign_criterion.proximity.radius, campaign_criterion.proximity.radius_units FROM campaign_criterion WHERE campaign_criterion.campaign = 'customers/CUSTOMER_ID/campaigns/CAMPAIGN_ID' AND campaign_criterion.type IN ('LOCATION', 'PROXIMITY')"
}
```

## 3. Exclude a supported location

Use `CampaignCriterionService.MutateCampaignCriteria`:

```http
POST https://googleads.googleapis.com/v25/customers/CUSTOMER_ID/campaignCriteria:mutate
```

```json
{
  "operations": [
    {
      "create": {
        "campaign": "customers/CUSTOMER_ID/campaigns/CAMPAIGN_ID",
        "negative": true,
        "location": {
          "geoTargetConstant": "geoTargetConstants/GEO_TARGET_CONSTANT_ID"
        }
      }
    }
  ],
  "partialFailure": false,
  "validateOnly": false,
  "responseContentType": "MUTABLE_RESOURCE"
}
```

This works for catalog locations such as countries, regions, cities, and postal areas, subject to location availability and campaign-type restrictions.

Multiple exclusions can be sent in the same `operations` array. Set `partialFailure` to `true` if valid operations should still be applied when another operation fails.

## 4. Create a positive radius target

A proximity is an inclusion, not an exclusion:

```json
{
  "operations": [
    {
      "create": {
        "campaign": "customers/CUSTOMER_ID/campaigns/CAMPAIGN_ID",
        "proximity": {
          "geoPoint": {
            "latitudeInMicroDegrees": -10760000,
            "longitudeInMicroDegrees": -48260000
          },
          "radius": 10,
          "radiusUnits": "KILOMETERS"
        }
      }
    }
  ]
}
```

Coordinates are integers in microdegrees:

```text
microdegrees = decimal degrees × 1,000,000
```

Allowed unit enum values are `KILOMETERS` and `MILES`; the default is kilometers. Google requires a radius of at least 1 km. A very small target may not serve because of privacy and audience-size thresholds.

Instead of `geoPoint`, a proximity may be created from an address:

```json
{
  "proximity": {
    "address": {
      "streetAddress": "ADDRESS",
      "cityName": "CITY",
      "provinceCode": "STATE_OR_PROVINCE_CODE",
      "postalCode": "POSTAL_CODE",
      "countryCode": "BR"
    },
    "radius": 10,
    "radiusUnits": "KILOMETERS"
  }
}
```

Google geocodes the address. When both an address and coordinates are involved, the geo point and radius determine serving; the stored address is descriptive.

Do **not** add `"negative": true` to a proximity operation. Google documents that `LocationInfo` can be excluded but `ProximityInfo` cannot.

## 5. Remove an exclusion, location target, or radius

First read its `campaign_criterion.resource_name`, then send a `remove` operation:

```json
{
  "operations": [
    {
      "remove": "customers/CUSTOMER_ID/campaignCriteria/CAMPAIGN_ID~CRITERION_ID"
    }
  ]
}
```

The resource-name format is:

```text
customers/{customer_id}/campaignCriteria/{campaign_id}~{criterion_id}
```

## 6. Replace or change geographic criteria

The criterion kind (`location` or `proximity`), its location/radius data, the owning campaign, and `negative` are immutable. Negative criteria cannot be updated.

To change any of those values:

1. Read current criteria.
2. Compare them with the desired set.
3. Send `remove` operations for obsolete criteria.
4. Send `create` operations for missing criteria.

Both remove and create operations can be included in one `MutateCampaignCriteria` request. With `partialFailure: false`, the request is transactional.

Although `CampaignCriterionOperation` has a generic `update` branch, it does not turn an immutable positive location into an exclusion or edit an exclusion's geography. Use remove-and-create.

## 7. Read and update advanced location matching

Read the settings with GAQL:

```sql
SELECT
  campaign.resource_name,
  campaign.geo_target_type_setting.positive_geo_target_type,
  campaign.geo_target_type_setting.negative_geo_target_type
FROM campaign
WHERE campaign.id = CAMPAIGN_ID
```

Update them with `CampaignService.MutateCampaigns`:

```http
POST https://googleads.googleapis.com/v25/customers/CUSTOMER_ID/campaigns:mutate
```

```json
{
  "operations": [
    {
      "update": {
        "resourceName": "customers/CUSTOMER_ID/campaigns/CAMPAIGN_ID",
        "geoTargetTypeSetting": {
          "positiveGeoTargetType": "PRESENCE",
          "negativeGeoTargetType": "PRESENCE"
        }
      },
      "updateMask": "geo_target_type_setting.positive_geo_target_type,geo_target_type_setting.negative_geo_target_type"
    }
  ]
}
```

Relevant enum behavior:

- Positive `PRESENCE`: people in or regularly in the included locations.
- Positive `PRESENCE_OR_INTEREST`: people present in or interested in the included locations.
- Negative `PRESENCE`: exclude people in the excluded locations.
- Negative `PRESENCE_OR_INTEREST`: defined in the enum, but generally unsupported for negative targeting in most campaign types. Prefer `PRESENCE`.
- Positive `SEARCH_INTEREST`: restricted to certain Search and standard Shopping campaigns and is deprecated/not settable for most campaign types.

These settings change how users are matched; they do not create geographic criteria.

## 8. Validate without changing the account

For either campaign or campaign-criterion mutate requests, set:

```json
{
  "validateOnly": true
}
```

The API validates the request and returns errors without applying operations. This is useful before a bulk exclusion change.

## Practical limits and campaign caveats

- Location targeting is best-effort, based on signals such as IP address, device information, settings, and behavior. It is not a guaranteed GPS geofence.
- If a campaign has no positive location or location-group criterion, it can default to targeting all regions. Always inspect the full positive and negative set.
- A campaign cannot target and exclude the exact same criterion.
- Smart campaigns cannot mix location and proximity targets, and have additional limits on proximity criteria.
- Hotel Ads campaigns do not support radius targeting and have stricter geographic-target rules.
- Available target types differ by country.
- An invalid or ungeocodable proximity address returns a criterion error.
- Common relevant errors include `INVALID_PROXIMITY_ADDRESS`, `INVALID_PROXIMITY_RADIUS`, `INVALID_PROXIMITY_RADIUS_UNITS`, `INVALID_LATITUDE`, `INVALID_LONGITUDE`, `CANNOT_TARGET_AND_EXCLUDE`, and `CANNOT_UPDATE_NEGATIVE_CRITERION`.

## Recommended workflow

1. Resolve each requested place with `SuggestGeoTargetConstants`.
2. Reject ambiguous, non-`ENABLED`, or wrong-country suggestions.
3. Read existing `LOCATION` and `PROXIMITY` campaign criteria.
4. Compute the desired create/remove operations.
5. Call `MutateCampaignCriteria` with `validateOnly: true`.
6. If validation succeeds, repeat with `validateOnly: false`.
7. Read the criteria again and verify the resulting set.
8. Set `negative_geo_target_type` to `PRESENCE` when physical-presence exclusion is required.

## Official references

- [Location targeting guide](https://developers.google.com/google-ads/api/docs/targeting/location-targeting)
- [CampaignCriterion resource](https://developers.google.com/google-ads/api/reference/rpc/v25/CampaignCriterion)
- [CampaignCriterionService](https://developers.google.com/google-ads/api/reference/rpc/v25/CampaignCriterionService)
- [GeoTargetConstantService.SuggestGeoTargetConstants](https://developers.google.com/google-ads/api/reference/rpc/v25/GeoTargetConstantService/SuggestGeoTargetConstants)
- [ProximityInfo](https://developers.google.com/google-ads/api/reference/rpc/v25/ProximityInfo)
- [Campaign.GeoTargetTypeSetting](https://developers.google.com/google-ads/api/reference/rpc/v25/Campaign.GeoTargetTypeSetting)
- [GoogleAdsService.Search](https://developers.google.com/google-ads/api/reference/rpc/v25/GoogleAdsService/Search)
- [GoogleAdsService.SearchStream](https://developers.google.com/google-ads/api/reference/rpc/v25/GoogleAdsService/SearchStream)
- [REST Search and SearchStream](https://developers.google.com/google-ads/api/rest/common/search)
- [REST mutate operations](https://developers.google.com/google-ads/api/rest/common/mutate)
- [Criteria support matrix](https://developers.google.com/google-ads/api/docs/targeting/criteria)
- [Geo-target reference data](https://developers.google.com/google-ads/api/reference/data/geotargets)
- [Google Ads API v25 release notes](https://developers.google.com/google-ads/api/docs/release-notes)
- [Google Ads Help: target geographic locations](https://support.google.com/google-ads/answer/1722043)
