# Audit Framework — Meta audit levers mapped to Meta MCP calls

This is the execution map. Each check lists the **exact MCP call**, what to compute, and the
pass/fail rule (thresholds live in `metrics-benchmarks.md`; field facts in `mcp-field-reference.md`).
Run levers in order; each produces rows for one payload section (see SKILL.md §"Payload schema").

Check IDs: `DI` data infrastructure · `AR` architecture · `BP` budget/pacing · `AT` attribution ·
`CR` creative · `CO` competitive · `FP` future-proofing.

---

## Lever 0 — Scope & context (no scoring)

1. `ads_get_ad_accounts` → pick account; **stop** unless `is_ads_mcp_enabled` and `is_queryable`
   (surface `not_queryable_reason`).
2. `ads_insights_advertiser_context` → business model (Lead Gen vs Ecommerce), funnel, primary
   objective. Records `business_model` (drives a few thresholds + the workbook named range).
3. Set windows: 30d (structure/budget/attribution), 90d (creative concentration), 14–30d
   `time_increment` trend (fatigue).

---

## Lever 1 — Data Infrastructure & Signal  → section `data_infrastructure`

| ID | Check | MCP call | Rule |
|---|---|---|---|
| DI-01 | Dataset/pixel exists & active | `ads_get_datasets(ad_account_id)` | FAIL if none/inactive |
| DI-02 | CAPI live (server events) | `ads_get_dataset_stats(dataset_id, aggregation='event', event_source='SERVER_ONLY')` vs `WEB_ONLY` | FAIL if no server events; FLAG if server ≪ web |
| DI-03 | Dedup signal | both WEB_ONLY and SERVER_ONLY present for key events | FLAG if one-sided |
| DI-04 | EMQ (Purchase/Lead) | `ads_get_dataset_quality(dataset_id)` | FAIL < 6, FLAG 6–8, PASS ≥ 8 |
| DI-05 | Match-key coverage | `dataset_quality` per-key | FLAG sparse keys |
| DI-06 | Event freshness | `dataset_quality` freshness | FAIL if stale/no recent uploads |
| DI-07 | Key event volume ≥ 25/wk | `dataset_stats` (≤28d window) for the optimization event | FAIL ~0 on active campaign; FLAG < 25/wk |

## Lever 2 — Account Architecture  → section `architecture`

Pull once: `ads_get_ad_entities(level='campaign', fields=[id,name,objective,amount_spent,results,daily_budget,lifetime_budget,bid_strategy,effective_status], date_preset='last_30d', sort='amount_spent_descending')`
and `level='adset'` with `[id,name,optimization_goal,amount_spent,results,attribution_setting,daily_budget,lifetime_budget,effective_status]`.

| ID | Check | Compute | Rule |
|---|---|---|---|
| AR-01 | Top-3 spend concentration | Σ top-3 campaign spend ÷ total | FLAG < 60%, FAIL < 45% |
| AR-02 | Fragmentation / learning starvation | count ad sets with `results` < 25 in 30d | FLAG if "more than a handful"; FAIL if majority |
| AR-03 | Conflated goals | ad sets in one campaign with divergent `optimization_goal` | FLAG mixed goals |
| AR-04 | Goal↔objective alignment | `objective` vs ad-set `optimization_goal` | FAIL hard mismatch (sales obj → LINK_CLICKS) |
| AR-05 | Prospecting:retargeting split | classify ad sets via `ads_get_ad_account_custom_audiences` subtypes (WEBSITE/ENGAGEMENT/OFFLINE/customer-list = retargeting) | FLAG retargeting > 35%, FAIL > 50% |
| AR-06 | Exclusions present | converters/customers excluded on prospecting (best-effort: audience names + subtypes) | FLAG none |
| AR-07 | Legacy/"shanty-town" drift | old `created_time` campaigns still spending with poor `cost_per_result` | FLAG |
| AR-08 | Naming hygiene | inspect `name` patterns | LOW flag if opaque |

## Lever 3 — Budget & Pacing  → section `budget`

| ID | Check | MCP call / compute | Rule |
|---|---|---|---|
| BP-01 | Daily vs lifetime pacing | presence of `daily_budget` vs `lifetime_budget` on high-spend campaigns | FLAG rigid daily caps on evergreen/high-volume |
| BP-02 | Spend vs results contribution | per campaign: spend share vs `results` share | FLAG any > 10% spend & < 5% results |
| BP-03 | Budget-capped efficient campaigns | high efficiency (`cost_per_result` low) + small budget | FLAG opportunity |
| BP-04 | Bid strategy fit | `bid_strategy` vs objective/scale | FLAG undefined at scale |
| BP-05 | Marginal trend | `ads_insights_performance_trend` (CPR/ROAS over time) | FLAG rising CPR while flat spend |

## Lever 4 — Attribution & Incrementality  → section `attribution`

| ID | Check | MCP call | Rule |
|---|---|---|---|
| AT-01 | Attribution-window inventory | `attribution_setting` per ad set | record distribution |
| AT-02 | 1-day-view reliance | share of ad sets on `1d_view_*` | FLAG heavy 1DV |
| AT-03 | 7DC preference | share on `7d_click` | PASS if dominant |
| AT-04 | Action-type mix | `breakdowns:['action_type']` on account/campaign | FLAG retargeting-skewed action mix |
| AT-05 | MER / NC-ROAS | — | **N/A** — emit informational row, never score |

## Lever 5 — Creative Performance  → section `creative`

Pull: `ads_get_ad_entities(level='ad', fields=[id,name,amount_spent,impressions,frequency,ctr,cpm,results,cost_per_result,cost_per_action_type,video_thruplay_watched_actions,video_p25_watched_actions,video_p100_watched_actions,created_time,effective_status], date_preset='last_90d', sort='amount_spent_descending')`.
Then `ads_get_creatives` for format/object_type on the top ads.

| ID | Check | Compute (see field ref §4) | Rule |
|---|---|---|---|
| CR-01 | Thumb-stop (3s) | **N/A** — no 3s field | informational only |
| CR-02 | ThruPlay (hold) rate | `video_thruplay_watched_actions ÷ impressions` | track + trend; FLAG sharp drop |
| CR-03 | Hold-through | `video_p100 ÷ video_p25` | FLAG < ~35–40% |
| CR-04 | CTR-Link | `(spend ÷ cost_per_action_type[link_click]) ÷ impressions`; fallback all-click `ctr` (label it) | FLAG < 0.8% ecom prospecting |
| CR-05 | Concept count (prospecting) | distinct delivering creatives | FLAG < 6 |
| CR-06 | Spend concentration | top-5 ads spend ÷ total (L90) | FLAG > 70% |
| CR-07 | Frequency | `frequency` (prospecting) | FLAG > 3, FAIL > 5 |
| CR-08 | Refresh cadence | newest active-ad `created_time` | FLAG nothing new > 30d |
| CR-09 | Format diversity | `ads_get_creatives` object_type/format mix | FLAG 1–2 formats |

## Lever 6 — Competitive  → section `competitive` (qualitative, weight 0)

| ID | Check | MCP call | Output |
|---|---|---|---|
| CO-01 | Competitor active ads | `ads_library_search(search_terms / page_ids, countries)` | list angles/offers |
| CO-02 | Whitespace angles | pattern-read results | note gaps (discount vs value vs gifting) |

> Needs competitor names/terms + country. If absent, **ask the user**; do not invent competitors.

## Lever 7 — Future-Proofing  → section `future_proofing`

| ID | Check | MCP call | Rule |
|---|---|---|---|
| FP-01 | Opportunity score | `ads_get_opportunity_score(ad_account_id)` | record score + top recs |
| FP-02 | Catalog/feed health (ecom) | `ads_catalog_get_dynamic_ads_health` | FAIL on feed errors |
| FP-03 | Anomalies | `ads_insights_anomaly_signal` | FLAG active anomalies |
| FP-04 | Signal resilience | restate DI-02/DI-04 (CAPI + EMQ) | **informational — mark `N/A`** so the same evidence is not scored twice (it is already scored under Data Infrastructure) |

---

## Omitted by design (MCP cannot measure — declare, never fabricate)

- **Landing-page / CRO**: load speed, headline-match, clarity, friction, trust, scrollmaps/heatmaps,
  Post-Click CVR/bounce.
- **Testing discipline**: written calendar, 10%/10x mix, sample-size/duration guardrails,
  documented learnings (only *count of concurrent variants* is inferable, not the discipline).
- **Business/goal**: ICP, customer value tiers, margin by SKU, payback period, seasonality/promo
  calendar, inventory/staffing constraints.
- **Incrementality economics**: MER, NC-ROAS, new-customer revenue, 1DV-vs-7DC conversion splits.
- **Third-party attribution (Triple Whale/Northbeam) CAPI passback** — not inspectable here.

The workbook's `Audit_Scope` tab must list these so the reader knows coverage boundaries.
