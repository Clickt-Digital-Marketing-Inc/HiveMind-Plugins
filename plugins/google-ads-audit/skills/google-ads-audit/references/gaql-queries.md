# GAQL Query Recipes — Google Ads MCP

How to pull each audit area through the `google-ads-mcp` server. Three tools:

- `customers_list_accessible_customers` → returns customer IDs the login can reach.
- `metadata_get_resource_metadata` → returns selectable/filterable fields for a
  resource. **Call this to verify a field before querying — never guess field
  names.** Cache the result; the schema rarely changes.
- `search_search` → runs the query. Parameters:
  - `customer_id` (string, digits only, no dashes)
  - `resource` (e.g. `"campaign"`)
  - `fields` (list, e.g. `["campaign.name","metrics.cost_micros"]`)
  - `conditions` (list of strings, AND-combined, e.g. `["campaign.status = 'ENABLED'"]`)
  - `orderings` (list, e.g. `["metrics.cost_micros DESC"]`)
  - `limit` (int, optional)

## Global conversion rules (apply to every pull)

- **Micros:** `*_micros` fields are millionths. Divide by 1,000,000 for currency
  (cost_micros 6,100,000 → $6.10).
- **Impression share & rates:** `metrics.*_impression_share`, `metrics.ctr`,
  `conversions_from_interactions_rate` are fractions 0–1. Multiply by 100 for %.
- **Date filters:** add `"segments.date DURING LAST_30_DAYS"` or
  `"segments.date BETWEEN '2026-05-25' AND '2026-06-24'"` to a condition list.
- **Status:** analyze `ENABLED` entities only unless a check is about paused/removed clutter.

## Step 0 — Account resolution

1. `customers_list_accessible_customers` → pick / confirm the `customer_id`.
2. Account meta — `resource: "customer"`, fields:
   `customer.id, customer.descriptive_name, customer.currency_code,
   customer.time_zone, customer.auto_tagging_enabled,
   customer.conversion_tracking_setting.conversion_tracking_status,
   customer.conversion_tracking_setting.enhanced_conversions_for_leads_enabled`

## Step 1 — Account structure → tab 03

- Campaigns: `resource: "campaign"`, fields:
  `campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type,
  campaign.advertising_channel_sub_type, campaign.bidding_strategy_type,
  campaign_budget.amount_micros`. Condition: `campaign.status != 'REMOVED'`.
- Ad groups: `resource: "ad_group"`, fields:
  `ad_group.id, ad_group.name, ad_group.status, ad_group.type, campaign.name`.
- Use names to judge naming convention, type/objective tagging, brand vs non-brand
  split, and segmentation.

## Step 2 — Performance review → tab 04

- Per-campaign KPIs: `resource: "campaign"`, fields:
  `campaign.name, campaign.advertising_channel_type,
  campaign.bidding_strategy_type, metrics.impressions,
  metrics.clicks, metrics.ctr,
  metrics.average_cpc, metrics.cost_micros, metrics.conversions,
  metrics.conversions_value, metrics.cost_per_conversion,
  metrics.search_impression_share, metrics.search_budget_lost_impression_share,
  metrics.search_rank_lost_impression_share, metrics.search_top_impression_share`.
  Conditions: `["campaign.status = 'ENABLED'", "segments.date DURING LAST_90_DAYS"]`.
  Order: `["metrics.cost_micros DESC"]`.
  **Save this result verbatim as `campaigns.json`** (with the Step-3 keyword and
  search-terms pulls as `keywords.json` / `search_terms.json`) — the Concentration
  report parses these files directly; `campaign.advertising_channel_type` is what
  enables its campaign-types dimension, and `campaign.bidding_strategy_type`
  powers the deterministic pre-scorer (BB-02 / KW-03).
- Trend: add `segments.date` and `time`-bucket in app layer, or query
  `LAST_30_DAYS` vs the prior 30 separately to compare.
- **Lost IS (Budget)** high → budget-constrained; **Lost IS (Rank)** high → bid/Quality Score problem.

## Step 3 — Keyword strategy → tab 05

- Keywords + Quality Score: `resource: "keyword_view"`, fields:
  `ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type,
  campaign.name, ad_group_criterion.status,
  ad_group_criterion.quality_info.quality_score,
  ad_group_criterion.quality_info.creative_quality_score,
  ad_group_criterion.quality_info.post_click_quality_score,
  ad_group_criterion.quality_info.search_predicted_ctr,
  metrics.cost_micros, metrics.conversions, ad_group.id`.
- Search terms (wasted spend): `resource: "search_term_view"`, fields:
  `search_term_view.search_term, search_term_view.status,
  segments.search_term_match_type, metrics.cost_micros, metrics.conversions,
  metrics.clicks, campaign.name`.
  Condition: `["segments.date DURING LAST_30_DAYS"]`.
  **Gotchas:** `search_term_view` rejects `LAST_90_DAYS`; it cannot be filtered on
  `campaign.status`/`ad_group.status` — filter those in the app layer.
- Negative keywords (campaign-level): `resource: "campaign_criterion"`, fields:
  `campaign_criterion.keyword.text, campaign_criterion.keyword.match_type,
  campaign_criterion.negative, campaign.name`. Condition: `campaign_criterion.negative = true`.
- Shared negative lists: `resource: "shared_set"` (`shared_set.name, shared_set.type`)
  + `resource: "shared_criterion"` for members + `campaign_shared_set` for attachment.
  **Count shared lists alongside campaign-level negatives** before judging coverage.

### Keyword accuracy rules
- Dedupe by `(ad_group.id, keyword.text, keyword.match_type)`.
- Only flag wasted spend on terms with material spend (> $10) AND 0 conversions.
- BROAD + Manual CPC = legacy BMM, not intentional broad — don't flag as modern broad.
- Count keywords with impressions > 0 when judging ad-group theme coherence.

## Step 4 — Ad creatives & assets → tab 06

- Ads: `resource: "ad_group_ad"`, fields:
  `ad_group_ad.ad.id, ad_group_ad.ad.type, ad_group_ad.ad_strength,
  ad_group_ad.status, ad_group_ad.policy_summary.approval_status,
  ad_group_ad.policy_summary.review_status, ad_group_ad.ad.final_urls,
  ad_group.name`.
  - `ad.type = EXPANDED_TEXT_AD` → deprecated, flag for RSA migration.
  - `ad_strength` below `GOOD` → flag.
  - `approval_status = DISAPPROVED` → critical.
- Assets/extensions: `resource: "campaign_asset"`, fields:
  `campaign_asset.field_type, asset.type, campaign.name` (and `ad_group_asset` for
  ad-group level). Check sitelinks, callouts, structured snippets present.

## Step 5 — Landing pages → tab 07

- Final URLs: from `ad_group_ad.ad.final_urls` (step 4) or
  `resource: "landing_page_view"`, fields:
  `landing_page_view.unexpanded_final_url, metrics.clicks, metrics.conversions`.
- **GAQL exposes URLs only.** 404 checks, mobile/speed, and message-match are
  **manual** — mark those checks `N/A` with an "observed: manual review" note, or
  crawl the URLs outside the MCP.

## Step 6 — Budget & bidding → tab 08

- Budgets: `resource: "campaign_budget"`, fields:
  `campaign_budget.name, campaign_budget.amount_micros,
  campaign_budget.explicitly_shared`.
- Bidding: from `campaign.bidding_strategy_type` plus targets:
  `campaign.maximize_conversions.target_cpa_micros,
  campaign.target_cpa.target_cpa_micros, campaign.target_roas.target_roas,
  campaign.maximize_conversion_value.target_roas`. Portfolio strategies:
  `resource: "bidding_strategy"`, fields `bidding_strategy.type, bidding_strategy.name`.
  - Flag `ENHANCED_CPC` (eCPC) as deprecated.
  - Lead gen → expect tCPA / Max Conversions; ecommerce → tROAS / Max Conversion Value.

## Step 7 — Tracking & measurement → tab 09

- Conversion actions: `resource: "conversion_action"`, fields:
  `conversion_action.name, conversion_action.type, conversion_action.category,
  conversion_action.status, conversion_action.counting_type,
  conversion_action.primary_for_goal`.
  - No `ENABLED` primary action → critical.
  - Duplicate counting (multiple primary actions for the same event) → flag.
- Enhanced Conversions / Consent: read
  `customer.conversion_tracking_setting.enhanced_conversions_for_leads_enabled`
  and `...accepted_customer_data_terms`. Consent Mode v2 and GTM/tag firing are
  **partly manual** (verify in the tag) — mark `N/A` if not serving EU or if unverifiable.

## Step 8 — Audiences → tab 10

- Audience attachment: `resource: "ad_group_audience_view"` /
  `campaign_audience_view` for performance by audience; criteria via
  `ad_group_criterion.user_list.user_list, ad_group_criterion.type`.
- Lists: `resource: "user_list"`, fields:
  `user_list.name, user_list.membership_status, user_list.size_for_search,
  user_list.size_for_display, user_list.eligible_for_search,
  user_list.eligible_for_display`.
  - Small/expired lists or low membership → flag.
  - Check exclusions don't block high-value audiences.

## Step 9 — Scripts, recommendations & automation → tab 11

- Recommendations: `resource: "recommendation"`, fields:
  `recommendation.type, recommendation.dismissed, campaign.name`.
  - Triage, don't auto-apply. Treat optimization-score "apply more budget /
    broad match" recos with caution.
- **Account-level Scripts are not exposed via the API/GAQL.** Mark script checks
  `N/A` with "manual review" — only `recommendation` is queryable here.

## PMax deep checks (distribute into tabs 03/06/09)

- `resource: "campaign"` with `campaign.advertising_channel_type = 'PERFORMANCE_MAX'`.
- Asset groups: `resource: "asset_group"`, fields:
  `asset_group.name, asset_group.status, asset_group.ad_strength, campaign.name`.
- Signals/listing: `asset_group_signal`, `asset_group_listing_group_filter`.
- Brand cannibalization: compare PMax brand-term conversions vs Search brand campaign
  (use search terms / brand list). Recommend PMax brand exclusions if > ~15% from brand.
