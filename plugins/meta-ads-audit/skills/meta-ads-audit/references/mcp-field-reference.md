# Meta Ads MCP — Verified Field Reference

This file records what the Meta Ads MCP (`mcp__…__ads_*`) can and cannot return, verified via
`ads_get_field_context`. **Never pass a field that is not listed as AVAILABLE below** — the entity
tool rejects unknown fields. When in doubt, call `ads_get_field_context` again at runtime; the
catalog can change.

> Conventions: levels = `account` / `campaign` / `adset` / `ad`. "metric" = requires a time range
> (`date_preset` or `time_range`). "attribute" = static, no time range needed.

---

## 1. The workhorse: `ads_get_ad_entities`

Pulls entities at one `level` with chosen `fields`, optional `filtering`, `sort`, `breakdowns`,
and a time window. Hard rules learned from the schema:

- **Always include `id` and `name`** in `fields`. Entity display name comes from `name` — there is
  **no** `campaign_name` / `adset_name` / `ad_name` queryable field (they resolve as *unknown*).
- **Metrics require a time range.** Without `date_preset` or `time_range` you get attributes only.
  Never pass both `date_preset` and `time_range` together.
- **One breakdown per call.** Extra breakdowns are ignored. If a breakdown returns empty, **retry
  without the breakdown**.
- **Result set is capped.** To get both top and bottom of a metric, call twice with opposite `sort`
  direction. Do not loop the same params.
- `date_preset` values: `today, yesterday, this_month, last_month, this_quarter, last_3d, last_7d,
  last_14d, last_30d, last_90d, last_week_sun_sat, last_quarter, last_year, this_week_sun_today,
  this_year, maximum`.
- `time_range` = `'{"since":"YYYY-MM-DD","until":"YYYY-MM-DD"}'`.
- `time_increment`: `1`–`90`, `monthly`, or `all_days` — use for trend/fatigue pulls.

### AVAILABLE fields (verified)

| Field | Type | Levels | Metric? | Filter/Sort | Notes |
|---|---|---|---|---|---|
| `amount_spent` (alias `spend`) | currency | all | yes | yes/yes | Primary spend field. Alias `spend` accepted. |
| `impressions` | int | all | yes | yes/yes | |
| `reach` | int | all | yes | yes/yes | Unique "Meta Accounts". |
| `frequency` | float | all | yes | yes/yes | impressions ÷ reach. |
| `clicks` | int | all | yes | yes/yes | **All** clicks (not link clicks). |
| `ctr` | float | all | yes | yes/yes | **All-click** CTR, not link CTR. |
| `cpc` | currency | all | yes | yes/yes | Cost per all-click. |
| `cpm` | currency | all | yes | yes/yes | Cost per 1,000 impressions. |
| `results` | int | all | yes | **yes/yes** | Objective-based outcome count. **Use this as the "optimization events" count** for fragmentation/learning checks. |
| `cost_per_result` | currency | campaign/adset/ad | yes | yes/yes | Effective CPA per objective. |
| `conversions` | int | campaign | yes | no/yes | Specific conversion list; prefer `results` for the generic outcome count. |
| `cost_per_conversion` | currency | all | yes | no/yes | |
| `purchase_roas` | float | all | yes | yes/yes | ROAS from connected tools (in-platform). |
| `cost_per_action_type` | currency (map) | all | yes | no/no | Map keyed by action_type. **Derive link clicks / landing-page views from here** (see §4). |
| `video_thruplay_watched_actions` | int | all | yes | no/no | **ThruPlays** = played ≥15s or to completion. The closest "hold" metric. |
| `video_p25_watched_actions` | int | all | yes | no/no | 25% retention. |
| `video_p50_watched_actions` | int | all | yes | no/no | 50% retention. |
| `video_p75_watched_actions` | int | all | yes | no/no | 75% retention. |
| `video_p100_watched_actions` | int | all | yes | no/no | 100% retention. |
| `daily_budget` | currency | campaign/adset | no | yes/no | Presence ⇒ daily pacing. |
| `lifetime_budget` | currency | campaign/adset | no | yes/yes | Presence ⇒ lifetime pacing. |
| `bid_strategy` | enum | campaign/adset | no | no/no | lowest cost / cost cap / bid cap / target cost / min ROAS. |
| `optimization_goal` | enum | **adset** | no | yes/no | e.g. `OFFSITE_CONVERSIONS, VALUE, LEAD_GENERATION, QUALITY_LEAD, LINK_CLICKS, LANDING_PAGE_VIEWS, THRUPLAY, REACH`. |
| `objective` | enum | campaign/ad | no | yes/yes | e.g. `OUTCOME_SALES, OUTCOME_LEADS, OUTCOME_AWARENESS, OUTCOME_ENGAGEMENT, OUTCOME_TRAFFIC`. |
| `attribution_setting` | enum | **adset** | (treat as attribute) | yes/no | `1d_click, 7d_click, 1d_view_1d_click, 1d_view_7d_click, skan, incrementality`. **Core of the Attribution lever.** |
| `effective_status` | enum | all | no | yes/yes | Real delivery state: `ACTIVE, WITH_ISSUES, DISAPPROVED, PENDING_REVIEW, …`. |
| `status` | enum | all | no | yes/yes | Advertiser-set: `ACTIVE, PAUSED, ARCHIVED, DELETED`. |
| `buying_type` | enum | campaign | no | yes/yes | `AUCTION` / `RESERVED`. |
| `created_time` | datetime | all | no | yes/yes | **Creative recency / refresh-cadence proxy.** |
| `start_time` / `stop_time` | datetime | campaign/adset | no | yes/yes | Flight dates. |

### NOT available (confirmed *unknown* — do not request)

- Link/outbound clicks: `inline_link_clicks`, `inline_link_click_ctr`, `outbound_clicks`,
  `outbound_clicks_ctr`, `unique_outbound_clicks`, `unique_clicks`, `unique_ctr`,
  `cost_per_unique_click`.
- Short video views: `video_3_sec_watched_actions`, `video_play_actions`,
  `video_15_sec_watched_actions`, `video_30_sec_watched_actions`, `thruplays` (use
  `video_thruplay_watched_actions` instead).
- Relevance diagnostics: `quality_ranking`, `engagement_rate_ranking`,
  `conversion_rate_ranking`.
- Misc: `website_purchase_roas` (use `purchase_roas`), `account_currency`, standalone `actions` /
  `action_values` (the schema explicitly forbids requesting these standalone).

---

## 2. Useful breakdowns (one per call)

- `publisher_platform` — Facebook vs Instagram vs Audience Network vs Messenger.
- `platform_position` — Feed / Stories / Reels placement.
- `age`, `gender`, `country`, `region` — audience composition.
- `frequency_value` — distribution of frequency (saturation).
- `action_type` — action mix (purchase, add_to_cart, link_click, landing_page_view…).
- `impression_device`, `device_platform` — device split.

---

## 3. Other audit tools (verified)

| Tool | Returns | Audit lever |
|---|---|---|
| `ads_get_ad_accounts` | accounts + `is_ads_mcp_enabled`, `is_queryable`, `not_queryable_reason`, owning business | Scope gate |
| `ads_insights_advertiser_context` | business context / funnel / objective | Business model |
| `ads_insights_performance_trend` | time-series CPC/CPM/CPR/ROAS/CTR/CVR | Budget trend, fatigue |
| `ads_insights_industry_benchmark` | ad-set vs peer benchmarks (spend tier, optimization goal) | Benchmark reality-check |
| `ads_get_datasets` | pixels/datasets list (id, status) | Data infra |
| `ads_get_dataset_quality` | **EMQ**, per-match-key coverage, freshness (by channel: web/offline/crm) | Data infra (signal) |
| `ads_get_dataset_stats` | event volume, `aggregation=event`, `event_source=WEB_ONLY`/`SERVER_ONLY` | CAPI presence + dedup signal; ≥25/wk |
| `ads_get_ad_account_custom_audiences` | custom audiences + subtype (WEBSITE/LOOKALIKE/ENGAGEMENT/…), size, status | Prospecting/retargeting split, exclusions |
| `ads_get_creatives` | creative body/title/CTA/format/object_type (pass `creative_ids` or `fields` for full detail) | Creative format mix |
| `ads_get_creative_ads` | which ads use a creative | Concept consolidation |
| `ads_library_search` | competitor public ads (needs `search_terms` / `page_ids` / `countries`) | Competitive |
| `ads_get_opportunity_score` | account opportunity score 0–100 + recommendations | Future-proofing |
| `ads_catalog_get_dynamic_ads_health` | catalog/feed health | Future-proofing (ecom) |
| `ads_insights_anomaly_signal` | anomaly detection | Future-proofing |

> `ads_get_dataset_stats` lookback is **max 28 days**; timestamps are **Unix seconds** (not ISO).

---

## 4. Metric formulas (computed by the skill, not returned directly)

Let `S=amount_spent`, `I=impressions`, `R=reach`, `TP=video_thruplay_watched_actions`,
`P25/P50/P75/P100=video_pXX_watched_actions`, `CPA_t=cost_per_action_type[t]`.

- **Link clicks (derived)** `= S ÷ CPA_link_click` when `link_click` present in
  `cost_per_action_type`; else use `breakdowns:["action_type"]`. If neither available, **fall back
  to all-click `ctr`** and label the row "all-click CTR (link CTR unavailable)".
- **CTR-Link** `= link_clicks ÷ I`. Ecommerce prospecting target ≥ 0.8–1.0%.
- **ThruPlay (hold) rate** `= TP ÷ I`. Proxy for the "hold" metric (15s). **There is no 3-second
  field**, so the literal *thumb-stop rate* (3s ÷ impressions) **cannot be computed** — report the
  ThruPlay rate plus the quartile retention curve and mark thumb-stop as "not available via MCP".
- **Quartile retention curve** `= [P25, P50, P75, P100] ÷ I` (or ÷ P25 for a hold-through shape).
- **Hold-through (proxy for hook-to-hold)** `= P100 ÷ P25` — of those who reached 25%, how many
  finished. Use as the body-of-ad health signal.
- **Frequency** comes back directly; **CPM-new** is not separable (no new-vs-repeat reach split) —
  approximate saturation with `frequency` + `frequency_value` breakdown and note the limitation.
- **Top-N spend concentration** `= Σ(top N amount_spent) ÷ Σ(all amount_spent)`.
- **Prospecting vs retargeting** — classify ad sets by whether they target retargeting custom
  audiences (subtypes WEBSITE/ENGAGEMENT/OFFLINE_CONVERSION/customer-list) from
  `ads_get_ad_account_custom_audiences`; best-effort, document the heuristic.
- **Monetary values** from Ahrefs-style cents do **not** apply here — Meta currency fields are in
  account currency units already.

---

## 5. Known gaps the skill must declare (do not fabricate)

1. **Thumb-stop rate (3s)** — not computable; ThruPlay/quartiles substituted.
2. **True link/outbound CTR** — only derivable via action-type cost map; otherwise all-click CTR.
3. **Attribution-window side-by-side conversions** (1DV vs 7DC counts) — not exposed; only the
   *configured* `attribution_setting` per ad set is available.
4. **MER / NC-ROAS / new-customer revenue** — require backend/CRM data; out of scope.
5. **Relevance/quality rankings** — not exposed.
6. **Landing-page / CRO / seasonality / ICP / margin / testing-calendar** — not in the ad platform;
   out of scope by design.
