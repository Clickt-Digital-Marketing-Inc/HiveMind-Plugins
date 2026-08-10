---
name: google-ads-pmax-campaigns
description: Use when reporting on Google Ads Performance Max (PMax) campaigns — a 14-day momentum report that flags campaigns to SCALE (conversions up and ROAS surging) vs campaigns to CUT/INVESTIGATE (conversions down and ROAS collapsing) by comparing the last 14 days to the previous 14 days, plus asset-group concentration and a PMax-vs-Search cannibalization signal. Triggers include "Pmax report", "Performance Max winners and losers", "which Pmax campaigns should I scale or cut", "Pmax 14-day trend", "Pmax momentum", "Pmax asset group concentration", "is my PMax campaign cannibalizing Search". Pulls live campaign metrics via the Google Ads MCP (or a Google Ads UI CSV export) and emits a three-format analytical bundle: a markdown report, a self-contained interactive HTML explorer (tunable ROAS sliders), and a formula-driven .xlsx — plus prioritized advisor recommendations.
---

# Google Ads — Performance Max campaign momentum

Separate the Performance Max campaigns gaining momentum from the ones losing it,
fortnight over fortnight, so budget moves toward what is compounding and away from
what is decaying. One campaign = one row; **last 14 days vs previous 14 days**; two
blocks (scale / cut) benchmarked against each campaign's **own** prior period.

**Cadence:** PMax momentum check **weekly** for spend ≥ $10k/mo, **bi-weekly** for
$2k–$10k, **monthly** below that.

**REQUIRED BACKGROUND:** load `google-ads-foundation` first (account selection,
micros, date windows, the Diagnose → Recommend → Artifacts contract).

## When to use
- "How are my Performance Max campaigns trending?", "which PMax to scale or cut".
- Fortnightly PMax budget reallocation review.
- Spotting a PMax campaign that quietly decayed (ROAS halved) or quietly took off.

## Pull the data
Two pulls on `resource = "campaign"`, filtered to `campaign.advertising_channel_type
= 'PERFORMANCE_MAX'` and `campaign.status = 'ENABLED'`, identical except the date
window — run with **explicit equal `BETWEEN` ranges** so they are symmetric and
exclude the partial current day:
1. **Last 14 days** — `[today-14, today-1]`.
2. **Previous 14 days** — `[today-28, today-15]`.

Fields: `campaign.id, campaign.name, metrics.impressions, metrics.clicks,
metrics.cost_micros, metrics.conversions, metrics.conversions_value`. Convert
`cost_micros / 1e6` to currency; `conversions_value` is already in currency. Full
GAQL, the conversion/ROAS convention, and the findings-JSON schema are in
[references/pmax-momentum-filter.md](references/pmax-momentum-filter.md).
Authoritative constant: `WINDOW_FIELDS` in
[scripts/assemble_findings.py](scripts/assemble_findings.py).

Two more OPTIONAL pulls power the asset-group concentration + cannibalization
diagnostics (last-14d snapshots, not last/prev pairs): `resource = "asset_group"`
for the campaign's asset-group breakdown (constant: `ASSET_GROUP_FIELDS`), and
`resource = "campaign"` filtered to `SEARCH` for the Search-side cannibalization
pairing (reuses `WINDOW_FIELDS`). Full GAQL in the reference doc's "M1.4
(optional) — the two structural pulls".

**Dual input.** This skill also accepts a user-supplied Google Ads UI CSV export
instead of the MCP (`scripts/assemble_findings_csv.py`) — run google-ads-foundation's
Step-0 input-selection first; both paths yield an identical model, labelled
honestly via `meta.source`. See the reference doc's "Dual input" section.

> **Numbers never pass through the model.** Save every pull's raw result to a file (auto-saved
> `tool-results/*.txt` for big pulls; verbatim copy of the whole `{"result": [...]}` JSON for
> inline ones) and build the findings JSON with
> [scripts/assemble_findings.py](scripts/assemble_findings.py) — never type metrics into a JSON by
> hand. The assembler embeds reconciliation control totals that the core re-verifies on every
> build; hand-assembled or edited findings hard-fail. See the reference doc's "Transcription
> firewall" section for the exact command.

> PMax has no search impression-share (those metrics are null) and no
> keyword/ad-group breakdown — never report them here.

## Diagnose — two blocks (benchmarked against each campaign's own prior 14 days)
ROAS(window) = `conversions_value / cost` (0 when no spend).
- **Block 1 — scaling winner:** `conv(last) > conv(prev)` AND `ROAS(last) > 1.50 ×
  ROAS(prev)` AND `impr(last) > 0` AND `cost(last) > 0`.
- **Block 2 — declining loser:** `conv(last) < conv(prev)` AND `ROAS(last) < 0.50 ×
  ROAS(prev)` AND `impr(prev) > 0` AND `cost(prev) > 0`.

Thresholds are tunable (`roas_up_multiple`, `roas_down_multiple`, and a `min_cost`
spend floor that defaults to 0). Campaigns with no impressions in either window are
held out as **no-activity** — listed, never dropped. A quiet account can legitimately
return **0 / 0**; present that honestly and use the sensitivity tables (counts as the
ROAS bars relax) and near-miss lists rather than forcing hits.

## Recommend (Critical → High → Medium)
- **Critical:** the Block 2 decliners — diagnose before they burn another fortnight
  (asset-group fatigue, feed/landing issues, audience-signal drift, seasonality);
  cap or cut spend if the decline is real and not seasonal.
- **High:** the Block 1 winners — scale budget while ROAS is compounding; check
  they are not just pulling brand/seasonal demand before scaling hard. Also High:
  **asset-group concentration risk** (a campaign's spend sits ≥ 80% in one asset
  group across 2+ active groups) — diversify creative/audience signals before
  scaling that campaign further.
- **Medium:** steady campaigns — leave alone; revisit the near-misses next cycle.
  Also Medium: **PMax/Search cannibalization risk** (a PMax campaign's share of
  its theme-matched Search spend clears 60%) — a heuristic, verify with Search
  impression share before acting.

Budget moves in PMax are **manual** (read-only MCP) — this report informs the
decision; it does not change spend. `build_pmax_filter.py` prints these
prioritized recommendations right after the artifact summary — relay them to the
user grouped Critical → High → Medium, every number pulled from the model/report,
never re-narrated from raw data (the [advisor output
contract](../google-ads-foundation/references/artifact-formats.md)).

## Generate artifacts (in `artifacts/`)
The standard three-format analytical bundle, from one findings JSON via
[scripts/build_pmax_filter.py](scripts/build_pmax_filter.py) (`--formats md,html,xlsx`),
all rendered by the shared `_shared/render` toolkit from one model:
- `*.md` — narrative: provenance (both 14-day windows), headline, the **0/0-is-valid**
  framing, winners/losers tables, ROAS-up/down sensitivity, near-misses, no-activity
  hold-outs, and a full per-campaign table (status + signal; no row loss).
- `*_explorer.html` — **interactive primary**: self-contained ROAS sliders + spend
  floor with live sensitivity and near-miss panels; opens in any browser (no
  install/Excel/cloud); embedded JS matches the Python model exactly.
- `*.xlsx` — tunable Controls + Campaign-trends + Sensitivity workbook with a Status
  column (no row loss); needs `openpyxl`, LibreOffice-normalized so it opens in Excel.
- `*_charts/*.svg` — deterministic Vega-Lite charts (last-14d spend-by-signal bar,
  ROAS-vs-spend scatter) rendered at build time and referenced from the md; the
  explorer renders the same charts live from the sliders. `--no-charts` skips them.

> **Charts are generated, never authored.** Every chart is produced by `build_pmax_filter.py`
> through the shared chart module from the spec's `SPEC["charts"]` declaration. Never hand-write
> or edit SVG, Vega-Lite JSON, chart HTML, or the vendored JS; never "fix" a chart in the output
> file. If a chart is wrong, the spec or the model is wrong — change it there and re-run the
> builder. Same run, same chart, byte for byte.

This is a **diagnostic/reporting** skill — PMax has no keyword/ad-group apply files,
so it emits **no Google Ads Editor CSVs**. (That apply path,
`${CLAUDE_PLUGIN_ROOT}/skills/google-ads-foundation/scripts/make_editor_csv.py`, is separate and unrelated.)

## Resources
- [references/pmax-momentum-filter.md](references/pmax-momentum-filter.md) —
  **authoritative** block spec, the two GAQL pulls (+ the two optional M1.4
  structural pulls), conversion/ROAS convention, findings-JSON schema, the
  asset-group-concentration and cannibalization-heuristic rules, dual input
  (CSV), output bundle, and Excel-open honesty.
- [scripts/pmax_core.py](scripts/pmax_core.py) — the single-source classification
  engine / model (stdlib only); its math is mirrored in the spec's `js_kernel` and
  the xlsx formulas. Also owns `asset_group_concentration`, `cannibalization`, and
  `recommendations` (built on `_shared/analytics.py`'s parity-gated primitives).
- [scripts/pmax_spec.py](scripts/pmax_spec.py) — the md/html render spec (KPIs,
  winners/losers, sensitivity, near-misses, full row table, controls, JS kernel,
  plus the M1.4 concentration/cannibalization/recommendations panels).
- [scripts/pmax_xlsx_spec.py](scripts/pmax_xlsx_spec.py) — the xlsx workbook layout
  (Controls / Campaign trends / Sensitivity), pure data, no openpyxl.
- [scripts/build_pmax_filter.py](scripts/build_pmax_filter.py) — thin CLI: builds the
  md/html/xlsx bundle via `_shared/render` and prints the advisor recommendations.
- [scripts/build_pmax_workbook.py](scripts/build_pmax_workbook.py) — thin xlsx CLI
  wrapper (`--check`, `--normalize/--no-normalize`).
- [scripts/assemble_findings_csv.py](scripts/assemble_findings_csv.py) — the CSV
  (dual-input) twin of `assemble_findings.py`; declares this skill's `COLUMN_MAP`.
- [tests/test_pmax.py](tests/test_pmax.py) + [tests/sample-findings-pmax.json](tests/sample-findings-pmax.json)
  — unit tests (fixture, no-row-loss, no-activity, empty, dedupe, zero-prior-ROAS,
  min-spend floor, sensitivity, asset-group concentration, cannibalization,
  recommendations, CSV-vs-MCP identical model, md/html parity + lazy import) and
  the synthetic fixture.

## Common mistakes / red flags
- A halved ROAS on a still-spending PMax campaign is easy to miss in a topline
  report — that is exactly Block 2; act on it before the next fortnight.
- Don't scale a Block 1 winner that is merely absorbing brand/seasonal demand — check
  the asset groups and search-themes first.
- 14-day windows are noisy for low-volume accounts; raise `min_cost` (and trust the
  longer-cadence reporting skill) rather than over-reacting to a single fortnight.
- Reading PMax is **manual + read-only**: this report recommends budget moves; it
  never makes them.
