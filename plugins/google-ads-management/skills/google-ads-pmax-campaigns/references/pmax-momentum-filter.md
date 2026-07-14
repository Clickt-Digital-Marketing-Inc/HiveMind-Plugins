# Performance Max momentum filter — authoritative spec

The single source of truth for the Pmax momentum skill: the GAQL pulls, the
block logic, the tunable parameters, the findings-JSON schema, the conversion /
ROAS convention, the PMax caveats, and the output bundle. Script docstrings point
here; they never re-document the schema.

One **Performance Max campaign = one row**, compared across two equal windows —
the **last 14 days** vs the **previous 14 days** — to separate campaigns gaining
momentum (scale them) from campaigns losing it (investigate/cut).

---

## Block logic (each condition AND-joined)

ROAS(window) = `conversions_value / cost` for that window, and is defined as **0.0
when the window has no spend** (nothing was spent, so nothing was returned to
measure).

**Block 1 — scaling winner** (candidate to scale budget):
1. `conversions(last) > conversions(prev)`
2. `ROAS(last) > roas_up_multiple × ROAS(prev)`   (rule = **1.50**)
3. `impressions(last) > 0`
4. `cost(last) > min_cost`   (rule = **0**, i.e. the bare `cost > 0`)

**Block 2 — declining loser** (investigate, restructure or cut):
1. `conversions(last) < conversions(prev)`
2. `ROAS(last) < roas_down_multiple × ROAS(prev)`   (rule = **0.50**)
3. `impressions(prev) > 0`
4. `cost(prev) > min_cost`   (rule = **0**)

The two blocks are mutually exclusive (conversions strictly up vs strictly down;
a campaign with equal conversions is unflagged). Useful edge behaviour:
- **New launch** (`ROAS(prev) = 0`): the up-bar becomes `ROAS(last) > 0`, so a
  campaign that went from nothing to positive return and grew conversions is a
  Block 1 winner. It can **never** be a Block 2 loser (nothing to decline from).
- **Went dark** (`cost(last) = 0` → `ROAS(last) = 0`): if it had prior spend and
  conversions fell, it is a Block 2 loser.

### Tunable parameters (defaults = the rule as written)
| Param | Default | Meaning |
|---|---|---|
| `roas_up_multiple` | 1.50 | Block 1 ROAS bar (× prior ROAS) |
| `roas_down_multiple` | 0.50 | Block 2 ROAS bar (× prior ROAS) |
| `min_cost` | 0.0 | spend floor per window; raise to suppress tiny-spend noise |

### No-activity hold-out
A campaign with **no impressions in either window** has no trend to evaluate. It
is kept with `status = "no_activity"`, never classified and never dropped (it is
listed in the report and carries a Status in every format — no row loss).

---

## Asset-group concentration

**M1.4 deepening.** Diversification diagnostic, separate from the momentum blocks:
for every PMax campaign with an asset-group breakdown pulled, what share of its
LAST-14-day spend sits in its single largest asset group.

Built on the shared `_shared/analytics.py` `concentration` primitive at `top_n=1`
(the single largest asset group — an xlsx-formula-friendly `MAXIFS/SUMIFS` ratio,
not a full top-N share):

- `top_share = max(asset_group.cost) / sum(asset_group.cost)` for that campaign's
  asset groups (last-14d window).
- `hhi = sum((cost_i/total)^2) * 10000` (0–10,000; the same Herfindahl the
  primitive reports for every campaign, not just flagged ones).
- `effective_n = 1 / sum((cost_i/total)^2)` (inverse Simpson — "effectively how
  many equally-sized asset groups").

**`concentration_risk` fires when** `top_share >= concentration_top_share_threshold`
(default **0.80**) **AND** the campaign has **2+ active** (nonzero-cost) asset
groups. A campaign with only one active asset group trivially has a 100% top
share — that is a structural fact (nothing to diversify against yet), not a
diversification risk, so it is shown but never flagged.

Tunable: `concentration_top_share_threshold` (default 0.80).

Why it matters: a PMax campaign whose spend is almost entirely inside one asset
group is fragile — if that group's creative fatigues, its audience signal drifts,
or its landing page breaks, the whole campaign's momentum goes with it. This is a
STRUCTURAL read (current asset-group mix), independent of the momentum blocks
above (which compare two time windows).

## Cannibalization heuristic

**M1.4 deepening.** A heuristic PMax-vs-Search overlap signal: for each ACTIVE
(status = "scored") PMax campaign, pair it with any enabled Search campaign whose
**normalized name** shares a significant word token, then compare last-14-day
spend.

**Theme-token normalization** (`pmax_core._theme_tokens`): strip 4-digit years
and punctuation, lowercase, drop channel/type boilerplate (`pmax`, `performance`,
`max`, `search`, `shopping`, `display`, `video`, `app`, `campaign`, `ads`,
`google`, `the`, `and`, `or`, `for`) and tokens under 3 characters. Deliberately
does **NOT** strip targeting-scope words like `brand` / `nonbrand` / `generic` /
`core` — those ARE meaningful theme signals here; a PMax campaign siphoning
branded Search traffic is exactly the case this heuristic is meant to surface.
Two campaigns are a candidate pair when their token sets intersect (e.g. `"PMax -
Prospecting"` and `"Search - Prospecting - NonBrand"` share `"prospecting"`).

**`cannibalization_risk` fires when**, for a PMax campaign matched to one or more
Search campaigns:

1. `pmax_theme_share = pmax_cost_last / (pmax_cost_last + sum(matched search
   cost_last)) >= cannibalization_share_threshold` (default **0.60**), **AND**
2. `pmax_cost_last + sum(matched search cost_last) > cannibalization_min_cost`
   (default **0.0** — a floor to suppress noise from tiny-spend pairs).

Tunables: `cannibalization_share_threshold` (default 0.60), `cannibalization_min_cost`
(default 0.0).

**Documented limitation — this is a NAME heuristic, not verified overlap.** The
Google Ads API exposes no cross-campaign keyword/audience-overlap metric (that
data lives only in Auction Insights, which is CSV/manual per
`google-ads-foundation`'s honesty rules). Two campaigns sharing a name token is a
*candidate* signal, not proof that PMax is capturing demand that would otherwise
have gone to Search — always pair a flag with a manual check of Search impression
share and the PMax campaign's asset-group audience signals before acting.

---

## The two GAQL pulls

Load `google-ads-foundation` first (account selection, micros, conventions). Both
pulls run on `resource = "campaign"` filtered to Performance Max, the only
difference being the date window. Use **explicit, equal `BETWEEN` ranges** for both
so the comparison is symmetric and excludes the partial current day.

```
resource = "campaign"
fields = [
  "campaign.id",
  "campaign.name",
  "metrics.impressions",
  "metrics.clicks",
  "metrics.cost_micros",
  "metrics.conversions",
  "metrics.conversions_value"
]
conditions = [
  "campaign.status = 'ENABLED'",
  "campaign.advertising_channel_type = 'PERFORMANCE_MAX'",
  "segments.date BETWEEN '<start>' AND '<end>'"
]
orderings = ["metrics.cost_micros DESC"]
```

- **Last 14 days** = `[today-14, today-1]`; **previous 14 days** = `[today-28, today-15]`.
- `cost_micros` is **micros** → divide by 1,000,000 to get currency before writing
  findings. `conversions_value` is already in the account currency.
- `metrics.conversions` is the account's **primary** conversions metric
  (attribution-modeled; may be fractional) — that is what we trend, by design.
- **PMax caveat:** search impression-share metrics are **null** for Performance
  Max — never query or report them here.

**Transcription firewall (mandatory).** Every pull's raw result must land in a file before
anything else happens: a big pull can exceed the MCP token cap and auto-save to a
`tool-results/*.txt` file — use that file as-is; for pulls that come back inline, copy the whole
tool result **verbatim** (the complete `{"result": [...]}` JSON, unedited) into a file. Then build
the findings JSON with `scripts/assemble_findings.py` — never assemble it by hand:

```
python3 scripts/assemble_findings.py \
  --last-window <raw-last-14d-file> --prev-window <raw-prev-14d-file> \
  --client-name "{Client Name}" --account-id {account} --currency {CUR} \
  --window-last "<today-14> to <today-1>" --window-prev "<today-28> to <today-15>" \
  -o findings.json
```

The assembler parses the raw files (micros conversion, per-campaign aggregation within each
window), embeds control totals as `meta.reconciliation`, and `pmax_core` re-verifies those totals
on every build — a findings JSON whose numbers were typed or edited by hand hard-fails. Metric
values therefore never pass through the model: the model handles file paths and meta labels
(client name, account id, windows), and the pipeline handles the numbers.

### M1.4 (optional) — the two structural pulls

Two more pulls power the asset-group concentration + cannibalization diagnostics above. Both
are OPTIONAL — a findings JSON without them still computes a full momentum model; the two
diagnostics are simply empty. Both are single-window snapshots at the **last 14 days** (not
last/prev pairs — they read the current structure, not a trend).

**Asset groups** — `resource = "asset_group"`, same PMax/Enabled filter, last-14d window:

```
resource = "asset_group"
fields = [
  "campaign.id", "campaign.name", "asset_group.id", "asset_group.name",
  "metrics.impressions", "metrics.clicks", "metrics.cost_micros",
  "metrics.conversions", "metrics.conversions_value"
]
conditions = [
  "campaign.status = 'ENABLED'",
  "campaign.advertising_channel_type = 'PERFORMANCE_MAX'",
  "segments.date BETWEEN '<last-14d-start>' AND '<last-14d-end>'"
]
```

**Search campaigns** — `resource = "campaign"`, same shape as the momentum pull but filtered to
Search instead of PMax, last-14d window only:

```
resource = "campaign"
fields = [ "campaign.id", "campaign.name", "metrics.impressions", "metrics.clicks",
           "metrics.cost_micros", "metrics.conversions", "metrics.conversions_value" ]
conditions = [
  "campaign.status = 'ENABLED'",
  "campaign.advertising_channel_type = 'SEARCH'",
  "segments.date BETWEEN '<last-14d-start>' AND '<last-14d-end>'"
]
```

Assemble both into the findings JSON alongside the momentum pulls:

```
python3 scripts/assemble_findings.py \
  --last-window <raw-last-14d-file> --prev-window <raw-prev-14d-file> \
  --asset-groups <raw-asset-groups-last-14d-file> \
  --search-campaigns <raw-search-campaigns-last-14d-file> \
  --client-name "{Client Name}" --account-id {account} --currency {CUR} \
  --window-last "<today-14> to <today-1>" --window-prev "<today-28> to <today-15>" \
  -o findings.json
```

---

## Findings-JSON schema (consumed by `scripts/pmax_core.py`)

```json
{
  "meta": {
    "client_name": "Acme Retail",
    "account_id": "7654321",
    "currency": "CAD",
    "window_last": "2026-06-13 to 2026-06-26",
    "window_prev": "2026-05-30 to 2026-06-12",
    "generated": "2026-06-27"
  },
  "params": { "roas_up_multiple": 1.50, "roas_down_multiple": 0.50, "min_cost": 0.0 },
  "last_window": [
    { "campaign_id": 1, "campaign": "PMax | Shopping - Core",
      "impressions": 10000, "clicks": 300, "cost": 500.0,
      "conversions": 50, "conversions_value": 5000.0 }
  ],
  "prev_window": [
    { "campaign_id": 1, "campaign": "PMax | Shopping - Core",
      "impressions": 8000, "clicks": 250, "cost": 480.0,
      "conversions": 30, "conversions_value": 1440.0 }
  ]
}
```

- `cost` and `conversions_value` are in **account currency** (the agent converts
  `cost_micros / 1e6` when assembling findings).
- `meta.params` is optional; omitted keys fall back to the rule defaults — including
  the M1.4 diagnostic thresholds `concentration_top_share_threshold` (0.80),
  `cannibalization_share_threshold` (0.60), `cannibalization_min_cost` (0.0).
- `meta.source` is optional; `"mcp"` (the default when absent) or `"user_csv"` — see
  "Dual input" below. Reports always surface it honestly.
- Each window array is per-campaign for that window. A campaign present in only one
  window is treated as zeros in the other. Rows are deduped by `campaign_id` within
  each window (a segmented export could split a campaign).
- `asset_groups` (M1.4, **optional**): one row per (campaign, asset group) at the
  LAST-14d window: `{"campaign_id", "campaign", "asset_group_id", "asset_group",
  "impressions", "clicks", "cost", "conversions", "conversions_value"}`. Powers
  "Asset-group concentration" above.
- `search_campaigns` (M1.4, **optional**): one row per Search campaign at the
  LAST-14d window, same shape as a `last_window` row. Powers "Cannibalization
  heuristic" above.

---

## Dual input (MCP or CSV)

Every pull above can also come from a user-supplied Google Ads UI CSV export
instead of the MCP — see `google-ads-foundation/references/artifact-formats.md`
for the general contract. This skill's CSV assembler is
`scripts/assemble_findings_csv.py`, driven by one `COLUMN_MAP` (logical fields:
`campaign_id`, `campaign`, `impressions`, `clicks`, `cost`, `conversions`,
`conversions_value`, plus `asset_group_id`/`asset_group` for the asset-group
export) shared across all four possible exports:

```
python3 scripts/assemble_findings_csv.py \
  --last-window-csv last14.csv --prev-window-csv prev14.csv \
  --asset-groups-csv asset_groups.csv --search-campaigns-csv search14.csv \
  --client-name "{Client Name}" --account-id {account} --currency {CUR} \
  --window-last "<today-14> to <today-1>" --window-prev "<today-28> to <today-15>" \
  -o findings.json
```

Ask the user for, in the Google Ads UI (**Campaigns** report unless noted), with
**"Campaign ID" added as a column** (Columns → Modify columns — required so
campaign identity matches the GAQL path's `campaign.id`):

| Export | Filter | Window | Flag |
|---|---|---|---|
| `--last-window-csv` | Performance Max, Enabled | last 14 days | required |
| `--prev-window-csv` | Performance Max, Enabled | previous 14 days | required |
| `--asset-groups-csv` | (Asset groups report), add "Asset group"/"Asset group ID" columns | last 14 days | optional (M1.4) |
| `--search-campaigns-csv` | Search, Enabled | last 14 days | optional (M1.4) |

The CSV path yields an **identical model** to the MCP path for the same data
(asserted in `tests/test_pmax.py::test_csv_matches_mcp`) — `pmax_core` cannot tell
the paths apart except by the honest `meta.source = "user_csv"` label, which the
report/explorer/xlsx all surface in the provenance ("Data source" row/panel).

---

## Output bundle (one model → three formats)

All three are rendered from one in-memory model (`compute_model`) via the shared
`_shared/render` toolkit, so they can never disagree. `min_cost`-style numbers and
classification live **once** in `pmax_core`; the HTML JS and the xlsx formulas only
mirror it.

- **`*.md`** — narrative: provenance (incl. the two 14-day windows, labelled
  honestly), headline KPIs, the **0/0-is-valid** framing when nothing flags,
  winners / losers tables, ROAS-up and ROAS-down sensitivity, near-misses, the
  no-activity hold-out, the M1.4 asset-group-concentration and cannibalization
  tables, an advisor-recommendations table, and a full per-campaign table
  (status + signal; no row loss). Put this story in the report.
- **`*_explorer.html`** — the interactive primary: a single self-contained file
  (inline CSS+JS, data embedded as JSON, zero external references). ROAS sliders +
  a spend-floor input, with the KPIs, sensitivity strips and near-miss lists
  recomputing live in any browser. No install, no Excel, no cloud.
- **`*.xlsx`** — Controls (tunable thresholds + self-rewriting logic +
  live COUNTIF/SUMIF) · Campaign trends (every campaign + Status; active rows carry
  formulas referencing the Controls cells) · Sensitivity (static snapshot). Needs
  `openpyxl`; **normalized through LibreOffice** so it opens in Excel. If `soffice`
  is missing the build fails (exit 2) rather than shipping a file that may not open
  — `--no-normalize` overrides. Real-Excel open is not verifiable here, so the HTML
  is the no-dependency primary.

### Honest window labels
The generic renderers hard-label the `window_90d`/`window_30d` provenance slots as
"90-day"/"30-day". This skill compares 14-day windows, so it leaves those slots
empty and surfaces the real windows under `window_last`/`window_prev` (md via the
params block, html via a "Comparison windows" panel, xlsx via the subtitle). The
shared toolkit is **not** modified.

---

## This is a diagnostic / reporting skill
Performance Max has no keywords or ad groups to push via Google Ads Editor, so this
skill emits **no apply-CSVs** — budget scale-ups and pull-backs are manual decisions
the report recommends. (The Editor-CSV apply path in
`google-ads-foundation/scripts/make_editor_csv.py` is unrelated and untouched.)
