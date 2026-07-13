---
name: cm3-by-product-report
description: Generate a per-product CM3 contribution-margin report from a Google Ads "Shopping products" CSV (optionally enriched with a Shopify "Gross profit by product" CSV). Default output is the locked 3-format analytical bundle from one compute pass — (1) an Obsidian-ready .md doc, (2) a self-contained interactive HTML explorer, and (3) a detailed Clickt-branded multi-tab .xlsx; the 7-slide executive .pptx deck is opt-in (--pptx). Segments every product into 5 CM3 bands (Excellent / High / Average / Low / Poor) and rolls up by Campaign, every Category level (L1–L5), every Product type level (L1–L5), and Vendor.
---

# CM3 by Product — Report Generator (md + HTML explorer + xlsx; pptx opt-in)

You are running the `cm3-by-product-report` skill. Your job: locate (or
collect) two CSVs plus four variable-cost assumptions, then call the bundled
`cm3_by_product.py` script — which produces the locked 3-format bundle from a
single compute pass:

1. **Obsidian Markdown** (`.md`) — provenance frontmatter, KPI + band tables,
   callouts, a full no-row-loss product table, and a `## Charts` section of
   static SVGs written to `{stem}_charts/` next to the md (revenue by CM3 band
   + revenue-vs-CM3% scatter, rendered at the run's parameters).
2. **Interactive HTML explorer** (`_explorer.html`) — self-contained (zero
   external refs); tune shipping/processing/fixed costs and the band cutoffs and
   the whole report re-bands live — the top-line KPIs, the by-band table, the
   charts, the **rollups** (By Campaign / By Vendor / By Category L1–L5 / By
   Product Type L1–L5, switched by a pill nav), and every product row all
   recompute from the same rows on every control change. It carries every report
   tab the xlsx does, plus a Methodology panel. The embedded JS matches the
   Python model (pinned by a jsdom rollup-parity harness).
3. **Detailed Excel** (`.xlsx`) — Clickt-branded multi-tab workbook,
   LibreOffice-normalized so it opens reliably in Excel.

The **7-slide executive `.pptx` deck is opt-in** — pass `--pptx` (or an explicit
`--output-pptx` path). It is not in the default bundle.

The compute logic, CSV parsing, COGS lookup, banding, rollups, and all the
writers live in `cm3_by_product.py` (+ `cm3_html.py` for the explorer). **Do NOT
recompute CM3 in Claude's head. Do NOT pre-parse either CSV.** The script is the
authoritative implementation.

## Operating procedure

Execute these steps in order. Do not skip ahead.

### Step 1 — Look for the two CSVs in the current workspace

Glob the cwd for both inputs:

- **Google Ads Shopping products CSV** — match any of: `*shopping*products*.csv`,
  `*google*ads*.csv`.
- **Shopify Gross profit by product CSV** (optional) — match any of:
  `*gross*profit*product*.csv`, `*shopify*gross*.csv`.

If exactly one file matches each glob, use it. If multiple match, show the user
the matches and ask which to use.

### Step 2 — If the Google Ads CSV is missing, ask for it (verbatim)

```
I need your Google Ads Shopping products CSV. To export: Google Ads → Reports → Predefined reports → Shopping → Shopping products → set date range → Download → CSV. Drop the file into this folder (or paste an absolute path) and tell me when it's ready.
```

Validate the file exists at the given path before continuing.

### Step 3 — Always offer the optional Shopify CSV (verbatim)

```
Optional: a Shopify 'Gross profit by product' CSV gives accurate per-product COGS. To export: Shopify admin → Analytics → Reports → Gross profit by product → set date range → Export → CSV. If you don't have one, I'll use the blanket COGS% fallback.
```

If the user provides a path, validate it exists. Otherwise proceed with the
blanket fallback.

### Step 4 — Collect the 4 numeric inputs

If `./cm3-by-product-inputs.json` exists, read it. Otherwise prompt with these
defaults:

| Field             | JSON key      | Unit | Default |
| ----------------- | ------------- | ---- | ------- |
| COGS % (fallback) | `cogs_pct`    | %    | 65      |
| Shipping %        | `ship_pct`    | %    | 20      |
| Processing %      | `proc_pct`    | %    | 2.9     |
| Fixed costs       | `fixed_costs` | $    | 0       |

Persist the result to `./cm3-by-product-inputs.json` so the run is re-runnable.

### Step 5 — Run the script

From the plugin's `skills/cm3-by-product-report/` directory (or any cwd; the
script is location-independent):

```bash
TS=$(date +%Y%m%d-%H%M%S)
python3 "${CLAUDE_PLUGIN_ROOT}/skills/cm3-by-product-report/cm3_by_product.py" \
  --csv "<google-ads-shopping.csv>" \
  --cogs-csv "<shopify-gross-profit.csv-or-omit>" \
  --inputs ./cm3-by-product-inputs.json \
  --output-md   "./clickt-cm3-by-product-${TS}.md" \
  --output-html "./clickt-cm3-by-product-${TS}_explorer.html" \
  --output-xlsx "./clickt-cm3-by-product-${TS}.xlsx"
```

- `--cogs-csv` is optional.
- If you pass none of the `--output-*` flags, the script defaults to writing the
  3-format bundle (md + `_explorer.html` + xlsx) with a timestamped name in the
  current directory.
- Add `--pptx` to also emit the executive deck (off by default).
- The md's chart SVGs land in `<md-stem>_charts/` next to the md — ship that
  folder with the md. Static chart rendering needs `vl-convert-python` (in
  `requirements.txt`); if it is missing the build fails with exit code 2 —
  pass `--no-charts` to skip every chart (md SVGs, live explorer charts, and
  the tuner widget chart).
- The xlsx is LibreOffice-normalized by default; if LibreOffice (`soffice`) is
  missing the build fails with exit code 2 — pass `--no-normalize` to skip.
- Integrity-check a built workbook with `python3 "${CLAUDE_PLUGIN_ROOT}/skills/cm3-by-product-report/cm3_by_product.py" --check <file.xlsx>`.

### Step 6 — Read the script's stdout JSON and report back

The script's **final stdout line** is a single JSON object with these keys:

```
{"md": "...", "html": "...", "xlsx": "...",   // "pptx" only when --pptx was passed
 "revenue": ..., "ad_spend": ..., "cm3": ..., "cm3_pct": ..., "roas": ...,
 "excellent_count": ..., "poor_count": ...}
```

Print a 5-line headline summary to the user:

```
Revenue:         $<revenue>
Ad spend:        $<ad_spend>
CM3 (weighted):  <cm3_pct as %>
Excellent band:  <excellent_count> products
Poor band:       <poor_count> products
```

Then print the three output paths. Done.

## Bands

CM3% per product determines the band. The four lower cutoffs below are the
**defaults** — they are tunable via `--inputs`, the `--band-*` CLI flags, or the
in-Claude tuner, and the tuned values flow through every output and its provenance.

| Band      | CM3% range (default)                | Style    |
| --------- | ----------------------------------- | -------- |
| Excellent | ≥ 10%                               | Strong   |
| High      | 5% – 10%                            | Healthy  |
| Average   | 0% – 5%                             | Amber    |
| Low       | −25% – 0%                           | Amber    |
| Poor      | < −25%  OR  ad spend with $0 rev    | Red      |
| Inactive  | $0 spend AND $0 revenue             | (excl.)  |

## Output — Interactive HTML explorer (`_explorer.html`)

A single self-contained file (inline CSS + JS, data embedded as JSON, zero
external refs). Left rail tunes shipping %, processing %, fixed costs, and the
five band cutoffs; the KPI strip, band distribution, the live charts, and the
full product table recompute live in the browser. The embedded JS is
byte-identical to the Python model at the saved assumptions, and every product
appears in the table (no row loss). Built by `cm3_html.py` (stdlib at import;
the chart layer lazy-loads `vl-convert-python` only for static renders). The
only third-party bytes in the file are the pinned, checksummed Vega/Vega-Lite
runtime inlined from `_charts/vendor/`.

## Charts — generated, never authored

Two charts are declared in `cm3_html.CHARTS` and generated through the vendored
chart module (`_charts/charts.py` + `_charts/vendor/`, vendored from Clickt's
shared render toolkit chart layer; a drift test enforces byte-parity in the
development monorepo):

| id                    | mark  | where                               |
| --------------------- | ----- | ----------------------------------- |
| `revenue_by_band`     | bar   | md SVG · live explorer · tuner widget |
| `revenue_cm3_scatter` | point | md SVG · live explorer              |

One declaration drives both render paths: static SVG at build time
(vl-convert, exact-pinned) and the live explorer charts (vendored runtime),
which re-derive from the same recomputed rows as the table on every control
change. Chart colors are the explorer's own band palette. All aggregation
lives in the Vega-Lite `transform` array. `--no-charts` opts out.

> **Charts are generated, never authored.** Every chart is produced by
> `cm3_by_product.py` through the vendored chart module from the declared
> chart specs. Never hand-write or edit SVG, Vega-Lite JSON, chart HTML, or
> the vendored JS; never "fix" a chart in the output file. If a chart is
> wrong, the spec or the model is wrong — change it there and re-run the
> builder. Same run, same chart, byte for byte.

## In-Claude tuner (`--emit-widget`)

When this skill is launched through the **Google Ads hub** it is treated as a
*tunable* task: instead of building files up front, the hub renders an in-Claude
tuner. The same `cm3_by_product.py` builder emits it:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/cm3-by-product-report/cm3_by_product.py" --csv "<shopping.csv>" [--cogs-csv "<shopify.csv>"] \
  --brand "<label>" --emit-widget /tmp/cm3_widget.html
```

This writes a self-contained `show_widget` HTML **fragment** (no `build_widget.py`
step — cm3 is bespoke). It reuses the explorer's recompute kernel and exposes the
same tunable controls (COGS fallback / shipping / processing / fixed costs + the
four band cutoffs), plus a Charts card inlining the widget-flagged static SVG
(`revenue_by_band`) rendered at the report defaults. Its **Outputs** row — Save to HiveMind / Export Excel /
Download HTML / Export PowerPoint — `sendPrompt`s a one-shot rebuild via this
builder at the operator's tuned params (`--cogs-pct --ship-pct --proc-pct
--fixed-costs --band-exc --band-high --band-avg --band-low` + one `--output-*`).
Save writes `--output-md` into the vault `raw/reports/`; the tuned params are
recorded in the md frontmatter so the saved report matches the tuner. See the hub
SKILL.md Step 4 (mode A) / Step 5 for the orchestration.

## Output — Excel tabs (detailed)

- **Summary** — Hero CM3, total revenue, ad spend, all KPIs, band breakdown
- **By Band** — One section per band with top products
- **By Product** — 1 row per product, sorted by CM3 desc, frozen header,
  auto-filter; band column rendered as a coloured pill
- **By Campaign** — Per-campaign rollup with CM3, ROAS, share of CM3
- **By Vendor** — Vendor extracted from `" : Vendor"` title suffix
  (only present when the Google Ads titles contain that pattern)
- **By Category** — Levels 1–5 of Google product Category (only non-empty levels)
- **By Product Type** — Levels 1–5 of merchant Product type (only non-empty levels)
- **Inputs & Methodology** — Every input, formula, band threshold, plus the
  COGS resolution coverage table (Title / Vendor / Store avg / Input)

## Output — Executive PowerPoint deck (opt-in, `--pptx`)

1. Title slide — period + currency, Clickt brand band
2. Headline KPIs — Revenue, Ad spend, CM3 $, CM3 %, ROAS, MER
3. CM3 band distribution — bar chart, product count per band
4. Top 10 products by CM3 $ — table
5. Bottom 10 products by CM3 $ — loss-leader table
6. Top 5 campaigns by CM3 $ — table with CM3 % column
7. What to do next — 3 deterministic data-driven bullets

## Output — Obsidian Markdown

YAML frontmatter, executive paragraph, KPI table, band-distribution table, a
`## Charts` section referencing the static SVGs in `<stem>_charts/` (relative
paths, so the md renders on GitHub and in editor previews), top/bottom 10
tables, rollups by Campaign / Category L1 / Product Type L1 / Vendor,
`> [!warning]` and `> [!success]` callouts, and a Related section with
`[[CM3 Calculator]]` + `[[Max CAC]]` wikilinks.

## Constraints — do not deviate

- Variable-cost formulas: `CM1 = Rev × (1 − cogs_pct − ship_pct − proc_pct)`,
  `CM2 = CM1 − Ad spend`, `CM3 = CM2 − Allocated fixed`. When a Shopify GP
  CSV is supplied, `cogs_pct` is resolved per-product; otherwise the input
  `cogs_pct` is the blanket value.
- The script consumes all 5 Category levels and all 5 Product type levels.
  Empty levels are auto-skipped — keep this behaviour so the same script
  works for any merchant.
- Currency is read from the Google Ads `Currency code` column.
- Output is deterministic: same inputs ⇒ same numbers, same layout. No
  random ordering, no "creative" exec summaries — the wording on the
  recommendation slide / callouts is template-driven from the data.

## Install / first-run

After installing the plugin, run once:

```bash
pip install -r "${CLAUDE_PLUGIN_ROOT}/requirements.txt"
```

## On error

- If the script exits non-zero, surface its stderr verbatim. Do not retry
  silently. Do not guess at the failure.
- If `openpyxl` or `python-pptx` is missing, the script's traceback names the
  module; relay the `pip install -r "${CLAUDE_PLUGIN_ROOT}/requirements.txt"` hint.
