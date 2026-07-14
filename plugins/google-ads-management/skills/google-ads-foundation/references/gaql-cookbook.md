# GAQL Cookbook (Google Ads MCP)

Ready-to-run queries expressed as `mcp__google-ads-mcp__search_search` arguments. All field names
below were verified against `metadata_get_resource_metadata`. If a query errors, re-check fields
with metadata for that resource — the API version may have changed.

Reminder: `conditions` are AND-ed; money fields are micros (÷1,000,000) — including
`metrics.average_cpc` / `average_cpm` / `average_cost`, which are micros despite the name; any
query selecting `metrics.*` needs a `segments.date ...` condition.

---

## Account identification

```
resource: "customer"
fields: ["customer.id","customer.descriptive_name","customer.manager",
         "customer.currency_code","customer.time_zone"]
```
Run once per accessible customer_id. Skip rows where `customer.manager = true`.

---

## Campaigns — structure, bidding, budget, AI Max

```
resource: "campaign"
fields: ["campaign.id","campaign.name","campaign.status",
         "campaign.advertising_channel_type","campaign.advertising_channel_sub_type",
         "campaign.bidding_strategy_type","campaign.bidding_strategy_system_status",
         "campaign.ai_max_setting.enable_ai_max",
         "campaign_budget.amount_micros","campaign_budget.explicitly_shared"]
conditions: ["campaign.status = 'ENABLED'"]
```
`campaign_budget.*` is selectable from the `campaign` resource (joined). Daily budget =
`campaign_budget.amount_micros / 1e6`.

## Campaign performance + impression share (budget/competitive/reporting)

```
resource: "campaign"
fields: ["campaign.id","campaign.name","campaign.advertising_channel_type",
         "metrics.impressions","metrics.clicks","metrics.ctr","metrics.average_cpc",
         "metrics.cost_micros","metrics.conversions","metrics.conversions_value",
         "metrics.cost_per_conversion","metrics.search_impression_share",
         "metrics.search_budget_lost_impression_share",
         "metrics.search_rank_lost_impression_share",
         "metrics.search_top_impression_share","metrics.search_absolute_top_impression_share"]
conditions: ["campaign.status = 'ENABLED'","segments.date DURING LAST_30_DAYS"]
orderings: ["metrics.cost_micros DESC"]
```
Impression-share metrics are fractions 0–1 (0.62 = 62%). They are only populated for Search; for
PMax/Display they return null. ROAS = `conversions_value / (cost_micros/1e6)`.

To trend a metric for the 5 early-warning signals, run the same query twice with different date
conditions (e.g. `LAST_7_DAYS` vs a `BETWEEN` window for the prior 7 days) and compare.

---

## Ad groups — sprawl, structure

```
resource: "ad_group"
fields: ["ad_group.id","ad_group.name","ad_group.status","campaign.id","campaign.name"]
conditions: ["campaign.status = 'ENABLED'","ad_group.status = 'ENABLED'"]
```

## Keyword count per ad group (red flag: 20+ keywords)
Pull keywords (below) and group/count by `ad_group.id` in code, deduping by
`(ad_group.id, keyword.text, keyword.match_type)`.

---

## Keywords — text, match type, Quality Score (no metrics on this resource)

```
resource: "ad_group_criterion"
fields: ["ad_group.id","ad_group.name","campaign.id","campaign.name",
         "ad_group_criterion.criterion_id","ad_group_criterion.keyword.text",
         "ad_group_criterion.keyword.match_type","ad_group_criterion.status",
         "ad_group_criterion.negative",
         "ad_group_criterion.quality_info.quality_score",
         "ad_group_criterion.quality_info.creative_quality_score",
         "ad_group_criterion.quality_info.post_click_quality_score",
         "ad_group_criterion.quality_info.search_predicted_ctr"]
conditions: ["ad_group_criterion.type = 'KEYWORD'",
             "ad_group_criterion.negative = false",
             "campaign.status = 'ENABLED'","ad_group.status = 'ENABLED'"]
```
`quality_info.*` is the QS triad: `creative_quality_score` (Ad relevance),
`post_click_quality_score` (Landing page exp.), `search_predicted_ctr` (Expected CTR) — values
`ABOVE_AVERAGE` / `AVERAGE` / `BELOW_AVERAGE`. `quality_score` is the 1–10 number. **`quality_score`
of `0` (or null) means the keyword is unscored (too little data / not eligible), NOT a literal
zero — exclude unscored keywords from QS averages and treat them separately.**

## Keyword performance + QS together (use the keyword_view resource for metrics)

```
resource: "keyword_view"
fields: ["ad_group.id","ad_group.name","campaign.id","campaign.name",
         "ad_group_criterion.keyword.text","ad_group_criterion.keyword.match_type",
         "ad_group_criterion.quality_info.quality_score",
         "metrics.impressions","metrics.clicks","metrics.ctr","metrics.average_cpc",
         "metrics.cost_micros","metrics.conversions","metrics.conversions_value"]
conditions: ["campaign.status = 'ENABLED'","segments.date DURING LAST_30_DAYS"]
orderings: ["metrics.cost_micros DESC"]
```

## Existing campaign-level negative keywords (red flag: none present)

```
resource: "campaign_criterion"
fields: ["campaign.id","campaign.name","campaign_criterion.keyword.text",
         "campaign_criterion.keyword.match_type","campaign_criterion.type",
         "campaign_criterion.negative"]
conditions: ["campaign_criterion.type = 'KEYWORD'","campaign_criterion.negative = true"]
```
A campaign with zero rows here has no campaign-level negatives.

---

## Search terms — the search query report (keywords/QS skills)

```
resource: "search_term_view"
fields: ["search_term_view.search_term","search_term_view.status",
         "segments.keyword.info.text","segments.keyword.info.match_type",
         "campaign.id","campaign.name","ad_group.id","ad_group.name",
         "metrics.impressions","metrics.clicks","metrics.ctr","metrics.average_cpc",
         "metrics.cost_micros","metrics.conversions","metrics.conversions_value"]
conditions: ["campaign.status = 'ENABLED'","segments.date DURING LAST_30_DAYS"]
orderings: ["metrics.cost_micros DESC"]
```
Segment buckets (apply in code): conversions ≥ 3 → add as exact; clicks ≥ 10 AND conversions = 0 →
negative; starts with how/what/why/etc → informational, evaluate intent; competitor/junk → shared
negative list.

---

## Ads — RSA assets, Ad Strength, approvals/disapprovals

```
resource: "ad_group_ad"
fields: ["campaign.id","campaign.name","ad_group.id","ad_group.name",
         "ad_group_ad.ad.id","ad_group_ad.ad.type","ad_group_ad.status",
         "ad_group_ad.ad_strength",
         "ad_group_ad.policy_summary.approval_status",
         "ad_group_ad.policy_summary.review_status",
         "ad_group_ad.ad.responsive_search_ad.headlines",
         "ad_group_ad.ad.responsive_search_ad.descriptions"]
conditions: ["campaign.status = 'ENABLED'","ad_group.status = 'ENABLED'"]
```
Disapprovals: `policy_summary.approval_status IN ('DISAPPROVED','AREA_OF_INTEREST_ONLY')`.
`ad_strength` of `POOR`/`AVERAGE` flags weak RSAs. The headlines/descriptions arrays let you build
the keyword↔headline matrix for the Quality Score skill (count assets too: < 8–10 headlines is
under-built).

## Ad performance (for A/B winner selection)

```
resource: "ad_group_ad"
fields: ["ad_group.id","ad_group_ad.ad.id","metrics.impressions","metrics.clicks",
         "metrics.ctr","metrics.conversions","metrics.cost_micros","metrics.conversions_value"]
conditions: ["campaign.status = 'ENABLED'","segments.date DURING LAST_30_DAYS"]
```

---

## Conversion actions — tracking health

```
resource: "conversion_action"
fields: ["conversion_action.id","conversion_action.name","conversion_action.status",
         "conversion_action.type","conversion_action.category",
         "conversion_action.primary_for_goal",
         "conversion_action.counting_type",
         "conversion_action.attribution_model_settings.attribution_model",
         "conversion_action.value_settings.default_value"]
conditions: ["conversion_action.status = 'ENABLED'"]
```
Zero rows, or no `primary_for_goal = true` action, means tracking is broken/misconfigured —
automation cannot work. Enhanced Conversions status is **not** exposed here; mark it manual.

## Device / time segmentation (Quality Score step 2, dayparting)

Add one breakdown segment to any metrics query, e.g. `segments.device` or
`segments.day_of_week` / `segments.hour` (add to `fields`; no special arg). Example device split:
```
resource: "keyword_view"
fields: ["ad_group_criterion.keyword.text","segments.device","metrics.impressions",
         "metrics.clicks","metrics.ctr","metrics.cost_micros","metrics.conversions"]
conditions: ["campaign.status = 'ENABLED'","segments.date DURING LAST_30_DAYS"]
```

---

## Audiences — applied to ad groups (audience-targeting skill)

```
resource: "ad_group_criterion"
fields: ["campaign.name","ad_group.name","ad_group_criterion.type",
         "ad_group_criterion.user_list.user_list","ad_group_criterion.bid_modifier",
         "ad_group_criterion.status"]
conditions: ["ad_group_criterion.type = 'USER_LIST'"]
```
Remarketing list sizes/membership durations and PMax brand-exclusion lists are **not** fully
exposed; verify those in the UI. Customer Match / Enhanced Conversions setup is manual.

---

## What the MCP cannot return (always mark manual)
- Auction Insights competitor domains/overlap (only your own impression-share metrics are exposed).
- Landing-page Core Web Vitals / page speed (use Search Console / PageSpeed — separate from this MCP).
- Enhanced Conversions / Consent Mode / Customer Match upload status.
- Any write/change — produce an artifact instead.
