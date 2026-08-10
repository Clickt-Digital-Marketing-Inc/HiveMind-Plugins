---
name: google-ads-pmax-listing-groups
description: Use when auditing Performance Max (PMax) listing groups, product partitions, or Shopping products for wasted spend — finding listing groups/products that convert too expensively, burn clicks without converting, or concentrate spend in a weak-ROAS tier, benchmarked against each unit's own campaign. Pulls live PMax data via the Google Ads MCP (asset_group_product_group_view + shopping_performance_view) or a user-supplied Google Ads UI CSV export, and runs a two-block campaign-benchmarked waste filter plus a tier-concentration + weak-ROAS signal, both tunable. Emits the standard three-format analytical bundle (markdown report, self-contained interactive HTML explorer, formula-driven .xlsx) and a prioritized, model-grounded advisor recommendation list.
---

# Google Ads — Performance Max Listing Groups

Find the PMax product partitions and products bleeding budget: the ones converting well above their
campaign's cost/conversion, the ones spending clicks with nothing to show, and the ones where spend
is concentrated in a tier that isn't paying back. Everything is benchmarked against **each unit's own
campaign** (not an account-wide rule), at two granularities (listing-group partitions + individual
products), from one tunable model.

**REQUIRED BACKGROUND:** load `google-ads-foundation` first — micros, dates, dedup, the dual
MCP-or-CSV input contract, and the advisor output contract (emit → report → recommend → offer-apply)
this skill follows.

**Cadence:** monthly for retail PMax; bi-weekly for spend ≥ $10k/mo. Only applies to **retail PMax**
(campaigns with a Merchant Center feed) — lead-gen PMax has no listing groups.

## When to use
- "Audit my PMax listing groups / product groups", "which products waste spend in Performance Max".
- PMax CPA inflating or ROAS slipping without an obvious campaign-level cause.
- Before excluding products / re-segmenting asset groups — to decide *which* on evidence.
- Monthly Shopping/PMax product performance review.

## Step 0 — pick the input path (MCP or CSV)

Per `google-ads-foundation`'s dual-input contract: MCP reachable → pull live (below); MCP
unreachable/erroring, or the user already has the exports → ask for the three Google Ads UI CSV
exports (Campaigns/PMax, Listing groups, Products) and run
[scripts/assemble_from_csv.py](scripts/assemble_from_csv.py) instead — see "CSV input path" in
[references/pmax-listing-waste-filter.md](references/pmax-listing-waste-filter.md) for the exact
reports/columns to request. Both paths yield an identical model (`meta.source` stamps which one ran).

## Pull the data (last 30 days) — full GAQL in [references/pmax-listing-waste-filter.md](references/pmax-listing-waste-filter.md)
1. **Listing-group metrics** — `asset_group_product_group_view` (PMax-only by construction): campaign,
   asset group, the listing-group-filter resource name, impressions, clicks, conversions,
   conversions_value, cost_micros. Window `segments.date DURING LAST_30_DAYS`. Constant: `LG_FIELDS`
   in [scripts/assemble_findings.py](scripts/assemble_findings.py).
2. **Listing-group labels** — `asset_group_listing_group_filter` (`case_value.*` + `type`), joined by
   resource name → a readable `Brand: … / Item ID: … / Type: …` label per partition. Constant:
   `LABEL_FIELDS`.
3. **Campaign benchmarks** — `campaign` (PMax): clicks, conversions, cost_micros → campaign cost/conv
   and clicks/conv. Serves both universes. Constant: `BENCH_FIELDS`.
4. **Per-product metrics** — `shopping_performance_view` segmented by `product_item_id` /
   `product_title`, filtered to the PMax campaign ids from step 3. Constant: `PRODUCT_FIELDS`.

The assembler converts `cost_micros/1e6`, derives each label, joins, and writes the findings JSON;
then run the builder. Use `metrics.conversions` (primary, attribution-modeled, fractional) for both
the unit and its campaign benchmark — never `all_conversions`, and never
`metrics.cost_per_conversion` (also micros).

> **Numbers never pass through the model.** Save every pull's raw result to a file (auto-saved
> `tool-results/*.txt` for big pulls; verbatim copy of the whole `{"result": [...]}` JSON for
> inline ones) and build the findings JSON with
> [scripts/assemble_findings.py](scripts/assemble_findings.py) — never type metrics into a JSON by
> hand. The assembler embeds reconciliation control totals that the core re-verifies on every
> build; hand-assembled or edited findings hard-fail. See the reference doc's "Transcription
> firewall" section for the exact command.

## Diagnose — two-block filter + tier concentration signal (F = 1.50; tier bars 0.30 / 1.00)
Each unit is scored against its **own campaign**; the two blocks are mutually exclusive by the
conversion split.
- **Block 1 — expensive converters** → review / segment / exclude:
  `conversions(unit) > 0` AND `cost/conv(unit) > F × campaign cost/conv`.
- **Block 2 — zero-conversion waste** → exclude / down-prioritize:
  `conversions(unit) = 0` AND `clicks(unit) > F × campaign clicks/conv` AND `campaign conversions > 0`.

Campaigns with 0 conversions (30d) have an undefined benchmark → their units are kept as *excluded
(no benchmark)*, never dropped. These thresholds are conservative: a clean account often returns
**0 / 0** — a valid result. Present it honestly and use the explorer's slider + the sensitivity read
(how many qualify as F steps down 2.0 → 1.5 → 1.0 → 0.5) to surface near-misses, rather than forcing
hits.

Independent of F: a **tier signal** flags a unit whose own share of its universe's 30d spend exceeds
`concentration_share_min` (default 0.30) **and** whose ROAS is below `weak_roas_max` (default
1.00) — "spend concentrated in a tier with weak ROAS". `model["summary"]["concentration"]` (top-N
share / HHI / effective-N) reads how concentrated the whole universe is, regardless of whether any
unit trips the signal.

## Recommend (Critical → High → Medium)
`pmax_listing_core.recommendations(model)` computes this list from the model — every number is
traceable to the bundle, nothing is narrated from raw data (present it conversationally, then point
at the md report / HTML explorer for the backing numbers):
- **Critical — Block 2 (zero-conversion waste):** exclude or down-prioritize the partition/product in
  the asset group's listing-group tree (web UI), or move it to a test asset group. Direct bleed.
- **High — Block 1 (expensive converters):** segment into their own asset group/campaign with a
  tighter tCPA/tROAS; exclude only if the margin is negative (they *do* convert). **High — tier
  signal:** reallocate spend away from concentrated, weak-ROAS units.
- **Medium:** the near-miss watchlist (relax F in the explorer to review); re-check the "Everything
  else" catch-all partition (often a sign an asset group needs subdividing).

An empty tier is honest — a clean account can return zero recommendations; never fabricate one to
fill a severity.

## Generate artifacts (in `artifacts/`)
The standard three-format analytical deliverable, from one findings JSON via
[scripts/build_pmax_listing_filter.py](scripts/build_pmax_listing_filter.py) (`--formats md,html,xlsx`),
all rendered by the shared `_shared/render` toolkit from one model. Per the advisor loop: **open with
the HTML explorer** (the hero deliverable), then walk the recommendations above, then offer to apply
them (manual — see below).
- `*.md` — narrative: provenance (incl. data source), **prioritized recommendations**, **tier
  concentration**, headline counts (partitions **and** products), the **0/0-is-clean** explanation,
  **tier signals**, sensitivity tables, near-misses, excluded campaigns, **and full per-unit tables**
  (status + block; no row loss). Put this story in the report.
- `*_explorer.html` — **interactive primary**: self-contained, one Expensiveness-factor slider
  re-tuning the partition table + products panel + both sensitivity strips live, plus a **tier
  concentration & signal card**, in any browser (no install/Excel/cloud); embedded JS matches the
  Python model exactly (including the tier-signal math, via the shared `analytics` primitives).
- `*.xlsx` — Controls (expensiveness factor + the two tier-signal thresholds) + Live-filter
  (partitions, live formulas incl. tier signals for every row) + Sensitivity (recommendations, tier
  concentration, and the products snapshot); a `Status` column means no row loss. Needs `openpyxl`,
  LibreOffice-normalized so it opens in Excel.
- `*_charts/*.svg` — deterministic Vega-Lite charts (flagged-spend-by-block bar, ROAS-vs-spend
  scatter over the partitions) rendered at build time and referenced from the md; the explorer
  renders the same charts live from the factor slider. `--no-charts` skips them.

> **Charts are generated, never authored.** Every chart is produced by `build_pmax_listing_filter.py`
> through the shared chart module from the spec's `SPEC["charts"]` declaration. Never hand-write
> or edit SVG, Vega-Lite JSON, chart HTML, or the vendored JS; never "fix" a chart in the output
> file. If a chart is wrong, the spec or the model is wrong — change it there and re-run the
> builder. Same run, same chart, byte for byte.

These are **analytical** deliverables. PMax listing-group / product exclusions are **manual** in the
Google Ads web UI (Editor does not support them and the MCP is read-only) — there is **no apply-CSV**
for this skill; the flagged rows in the bundle are the worklist.

## Resources
- [references/pmax-listing-waste-filter.md](references/pmax-listing-waste-filter.md) —
  **authoritative** two-block + tier-signal spec, the four GAQL pulls, the CSV input path, the
  advisor recommendations contract, findings-JSON schema, output bundle, the Excel-open honesty, and
  the retail-PMax-only scope note.
- [scripts/pmax_listing_core.py](scripts/pmax_listing_core.py) — the single-source classification +
  tier-concentration/signal engine / model (stdlib + `_shared/analytics`); its math is mirrored in the
  spec's `js_kernel` and the xlsx formulas. `recommendations(model)` is the advisor helper.
- [scripts/pmax_listing_spec.py](scripts/pmax_listing_spec.py) — the md/html render spec (KPIs,
  sections incl. recommendations/tier concentration/tier signals, full unit tables, the factor slider,
  columns, JS kernel splicing in `analytics.JS_MIRROR`, the live Products panel).
- [scripts/pmax_listing_xlsx_spec.py](scripts/pmax_listing_xlsx_spec.py) — the xlsx workbook layout
  (Controls / Live filter / Sensitivity), pure data, no openpyxl.
- [scripts/build_pmax_listing_filter.py](scripts/build_pmax_listing_filter.py) — thin CLI: builds the
  md/html/xlsx bundle via `_shared/render`.
- [scripts/build_pmax_listing_workbook.py](scripts/build_pmax_listing_workbook.py) — thin xlsx CLI
  (`--check`, `--normalize/--no-normalize`).
- [scripts/assemble_findings.py](scripts/assemble_findings.py) — MCP-path assembler (raw GAQL pulls ->
  findings JSON, `meta.source="mcp"`).
- [scripts/assemble_from_csv.py](scripts/assemble_from_csv.py) — CSV-path assembler (Google Ads UI
  exports -> the same findings JSON shape, `meta.source="user_csv"`) — see "CSV input path" in the
  reference doc for the exact reports/columns to request.
- The shared toolkit: `../../_shared/render` — `build_bundle`, `render_md`, `render_html`, and the
  lazy-openpyxl `xlsx` renderer (**frozen — import only**); `../../_shared/analytics.py` — concentration
  / signals primitives; `../../_shared/csv_input.py` — the CSV manual-input path.
- [tests/test_pmax_listing.py](tests/test_pmax_listing.py) +
  [tests/sample-pmax-findings.json](tests/sample-pmax-findings.json) +
  [tests/analytics_vectors_pmax_listing.json](tests/analytics_vectors_pmax_listing.json) — unit tests
  (fixture for both universes, no-row-loss, dedupe, strict block + tier-signal boundaries, empty
  edges, fractional conv, MCP-vs-CSV identical model, recommendations, md/html parity + lazy import),
  the synthetic fixture, and the analytics-primitives parity vectors (auto-discovered by the shared
  parity harness).

## Common mistakes / red flags
- **Retail PMax only.** Lead-gen PMax campaigns have no product feed → no listing groups; the pulls
  return nothing. Don't report an empty pull as "no waste" — say the campaign has no listing groups.
- Don't blindly exclude **Block 1** units — they convert. Segment or tighten targets first; exclude
  only on negative margin.
- Use `metrics.conversions` (primary) consistently; mixing in `all_conversions` or using the micros
  `cost_per_conversion` will mis-rank units.
- A dominant **"Everything else"** partition usually means the asset group isn't subdivided — flag it
  for partitioning rather than excluding.
- Applying changes is **manual** (read-only MCP; Editor has no PMax listing-group support) — deliver
  the bundle as the worklist; the buyer actions it in the web UI.
- A tier signal is **not** a Block 1/2 flag — a unit can carry one without qualifying either block
  (or qualify a block without carrying one). Present them as separate findings, don't conflate.
- On the **CSV path**, a flat UI export has no filter-resource id or `case_value` dimension — never
  imply the CSV assembled a real listing-group-filter join id; `meta.source` must say `user_csv`.
