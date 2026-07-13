# Raw pulls — Meta Ads MCP recipes for the audit data files

The six pulls below feed the Concentration report, the Creative Signals layer, and the
deterministic pre-scorer. Their saved result files are the **only** source of those
numbers — `scripts/meta_rows.py` parses them deterministically, so metric values never
pass through the model (the transcription firewall). Verify any field you are unsure
about with `ads_get_field_context` before calling — never guess field names (see
`references/mcp-field-reference.md`).

## Save-verbatim instructions (non-negotiable)

Write the **ENTIRE tool result JSON exactly as returned** to the working directory —
including the envelope. `ads_get_ad_entities` returns

```json
{"ad_entities": "[{\"id\": …}]", "summary": {"total_count": 12}}
```

where `ad_entities` is a **JSON-encoded string** (a string containing JSON, quotes
escaped). Save that string-wrapped form as-is — do not decode it, do not extract the
inner list, do not pretty-print, retype, trim, or reformat rows, and do not "fix"
`"Not available"` values or currency strings. The parser double-parses the envelope
itself (and also tolerates an already-decoded list plus bare-list/`result`/`data`
wrappers). A malformed file fails loudly with a `RawResultError` pointing back here.

Canonical filenames (what `build_audit.py --raw-dir` expects):

| File | Tool | Required? |
|---|---|---|
| `campaigns.json` | `ads_get_ad_entities` (level `campaign`) | yes |
| `adsets.json` | `ads_get_ad_entities` (level `adset`) | yes |
| `ads.json` | `ads_get_ad_entities` (level `ad`) | yes |
| `adsets_7d.json` | `ads_get_ad_entities` (level `adset`, `last_7d`) | optional — unlocks CR-07 true bands |
| `datasets.json` | `ads_get_datasets` | optional — unlocks DI-01 |
| `dataset_quality.json` | `ads_get_dataset_quality` | optional — unlocks DI-04 |

Explicit flags (`--raw-campaigns` … `--raw-dataset-quality`) accept other paths without
renaming.

## The six pulls

### 1. Campaigns → `campaigns.json`
`ads_get_ad_entities` — `level: "campaign"`, `date_preset: "last_30d"`, fields:

```
id, name, spend, impressions, clicks, results, cost_per_result, objective,
daily_budget, lifetime_budget, bid_strategy, effective_status, created_time,
buying_type
```

### 2. Ad sets → `adsets.json`
`ads_get_ad_entities` — `level: "adset"`, `date_preset: "last_30d"`, fields:

```
id, name, campaign_id, spend, impressions, reach, frequency, clicks, results,
cost_per_result, optimization_goal, attribution_setting, effective_status,
daily_budget, lifetime_budget
```

`campaign_id` is what links ad sets to campaign objectives — without it AR-03/AR-04
skip.

### 3. Ads → `ads.json`
`ads_get_ad_entities` — `level: "ad"`, `date_preset: "last_90d"`, `limit: 1000`, fields:

```
id, name, spend, impressions, reach, frequency, clicks, ctr, cpm, results,
cost_per_result, cost_per_action_type, video_thruplay_watched_actions,
video_p25_watched_actions, video_p50_watched_actions, video_p75_watched_actions,
video_p100_watched_actions, created_time, effective_status
```

### 4. Ad sets, 7-day → `adsets_7d.json` (optional but recommended)
`ads_get_ad_entities` — `level: "adset"`, `date_preset: "last_7d"`, fields:

```
id, name, spend, impressions, reach, frequency
```

Frequency benchmarks are 7-day benchmarks: this pull is what unlocks the **true CR-07
PASS/FLAG/FAIL bands** (window ≤ 8 days). Without it, CR-07 runs on the 30-day ad-set
data in PASS-only mode (FLAG ceiling, never FAIL).

### 5. Datasets → `datasets.json` (optional)
`ads_get_datasets` with the `ad_account_id`. Save the whole result
(`{"datasets": [...], "page_info": {...}}`).

### 6. Dataset quality → `dataset_quality.json` (optional)
`ads_get_dataset_quality` with the `dataset_id`, **for each unique active dataset** from
pull 5. Save the result (`{channel: [events]}`); with several active datasets, save the
one for the primary (event-firing) dataset — DI-04 takes the max composite score across
channels for the business model's primary event (`Lead` / `Purchase`).

## Result-shape quirks (what the parser tolerates — do not "fix" the files)

Pinned from captured live results; `scripts/meta_rows.py` handles all of this:

- **Double-wrapped envelope.** `ad_entities` is a JSON string inside JSON (see above).
- **Requested `spend` comes back as `amount_spent`** — alias maps in the parser handle
  renamed result keys; save what the tool returned.
- **Every metric is a human-formatted string.** Money: `"CA$1,023.31 CAD"`
  (currency-symbol prefix, thousands commas, a NON-BREAKING SPACE before the ISO code).
  Counts: `"583,301"`. Frequency: `"3.21"`. `ctr`: a **percent string** (`"0.0658%"`,
  all-click). `cpm`: a money string. The parser coerces all of these; rates are
  recomputed from counts downstream anyway.
- **Dates are `"11 June 2026"`** (`D MonthName YYYY`, English) — parsed with an explicit
  month map, never locale-dependent. Every row carries `date_start`/`date_stop`, which is
  where the honest window labels come from.
- **`"Not available"` (with or without a parenthesised explanation) = missing.** Any
  value string starting with `Not available` is dropped (key omitted) — e.g. campaign
  `daily_budget` often reads `"Not available (Uses ad set daily budget…)"` because
  budgets live at ad-set level for non-CBO campaigns.
- **`results` / `cost_per_result` arrive in a dual shape** under `{"value": X}`: either a
  string like `"107 (Leads (form))"` — count + indicator, nested parens kept — or a list
  of `{indicator, values: [{value, …}]}` items. The parser extracts a numeric `results`
  plus its `results_indicator`; only conversion-like indicators also populate
  `conv_results`.
- **Indicators are heterogeneous across campaigns** (Reach next to Leads in one
  account). Results are objective-relative: results-based scoring only happens within a
  homogeneous indicator set.
- **`cost_per_action_type` returns `"Not available"` on every ad in practice** — the
  raw path cannot derive link clicks; all-click CTR is evidence-only, and scored CR-04
  is a manual-CSV-path unlock.
- **`bid_strategy` is a human label** (`"Highest volume"`), often absent at campaign
  level. `effective_status` vocab seen: `ACTIVE`, `PAUSED`, `CAMPAIGN_PAUSED`.
- **Unrequested extras can appear** (e.g. `cost_per_video_view`) — unknown keys are
  ignored gracefully.
- **`datasets` can contain duplicates** (same `dataset_id` twice) — deduped by id. An
  epoch-zero `last_fired_time` (`"1969-12-31T16:00:00-0800"`) means **never fired**.
- **`dataset_quality`** is `{channel: [{event_name, event_match_quality:
  {composite_score, match_key_feedback}, data_freshness?}]}` — `composite_score` is a
  real number; `data_freshness` may be absent per event.
- Video milestones (`video_p25…p100`, ThruPlay) are count strings on video ads and
  `"Not available"` on static ads.

## Which checks each file unlocks

The pre-scorer (`scripts/prescore.py`) machine-scores a check only when its inputs are
present; anything missing is listed under `skipped` with the reason and falls back to
auditor judgment.

| File | Machine-scored checks | Evidence / KPIs |
|---|---|---|
| `campaigns.json` | AR-01 (top-3 spend share), BP-02 (spend vs results — homogeneous indicators only), AR-04 (objectives side) | AR-07 legacy campaigns, BP-01 budget mode, BP-03 scale candidates, BP-04 bid-strategy mix; Spend / Results / Cost-per-Result KPIs; Concentration campaigns + objectives dimensions |
| `adsets.json` | AR-02 (learning starvation), AR-03 (mixed goals), AR-04 (goals side), AT-02 (1d_view reliance), AT-03 (7d_click preference), CR-07 (PASS-only mode on a 30d window) | AT-01 attribution mix; effective-frequency zones (Creative Signals); Concentration ad_sets dimension |
| `ads.json` | CR-03 (hold-through), CR-06 (top-5 ad spend share), CR-08 (refresh cadence — raw path only; CSV lacks created time) | CR-02 ThruPlay rate, CR-04 all-click CTR (evidence-only on the raw path), CR-05 delivering-ad count, CR-01 nearest signals; CTR / CPM KPIs; creative fatigue + reach saturation (Creative Signals); Concentration ads dimension |
| `adsets_7d.json` | CR-07 **true bands** (<3 PASS / 3–5 FLAG / >5 FAIL) | Frequency KPI on the honest 7-day window |
| `datasets.json` | DI-01 (active dataset exists; never-fired datasets noted) | — |
| `dataset_quality.json` | DI-04 (EMQ for the business-model's primary event: ≥8 PASS / 6–8 FLAG / <6 FAIL) | — |

Scored CR-04 (CTR-Link, Ecommerce) and ranking decomposition (Quality / Engagement /
Conversion rankings) are **manual-CSV-path unlocks** — see
`references/manual-exports.md`.
