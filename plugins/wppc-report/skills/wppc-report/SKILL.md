---
name: wppc-report
description: Generate a wPPC (Weighted Profit-Per-Click) report — a sabermetric PPC report that scores Google Ads or Meta Ads segment exports on weighted profit per click. Use when the user says "wPPC", "weighted profit per click", "sabermetric PPC report", "margin above replacement", "MAR report", or wants to score a Google/Meta segments CSV export (keywords, ads, campaigns) on true contribution-margin value per click instead of margin-blind CVR/ROAS. Requires a segments CSV export, a column-mapping YAML, and per-order CM3 economics; emits a 3-format bundle — an interactive self-contained HTML report (primary), an Obsidian-ready markdown record, and a formula-driven xlsx backup — into a directory you choose.
---

# wPPC — Weighted Profit-Per-Click report

## What the report is

A sabermetric linear-weights report for Google & Meta Ads segment exports. Every
funnel event is credited at its expected contribution-margin (CM3) value, indexed
to the account baseline, shrunk for sample size, and scored above replacement — so
it surfaces *true value* per click and gates noisy decisions, instead of ranking
on margin-blind CVR/ROAS.

The metrics (one row per segment):

- **wPPC** — expected CM3 per click: `(Σ reach(S)·w(S) + repeats·w(repeat)) / clicks`.
  The weights `w(S)` are the incremental profit expectancy of reaching each funnel
  state, derived so they telescope to `CM3_order` along a full path (self-checked,
  PASS/FAIL).
- **wPPC+** — wPPC indexed to the account baseline within the platform; **100 =
  average**, 140 = 40% more expected margin per click than the account.
- **wPPC_shrunk / stabilized** — empirical-Bayes estimate pulled toward the account
  parent by `k` clicks (`k = σ²_within / τ²_between`, method-of-moments; falls back
  to 250 when unstable). `stabilized = Y` when `clicks ≥ k` — trust it; below that
  it's mostly prior.
- **MAR** — Margin Above Replacement, the counting/sort stat:
  `(wPPC_shrunk − wPPC_replacement) · clicks`, where replacement is the
  clicks-weighted 25th-percentile segment. High = scale, negative = cut.
- **closing_ratio** — realized CM3/click ÷ wPPC. `<1` = fills the funnel but fails
  to close (landing/checkout problem); `>1` = converts above what its funnel depth
  predicts (regression candidate).

## What it emits (one bundle per run, one platform)

One `build_model` computes every number once; three formats render it (no format
re-derives a number). The tool owns the filenames — you choose only the directory:

- **`wppc_{platform}_{slug}_{date}.html`** — the **primary deliverable**: a
  self-contained, interactive, white-label HTML report. Sortable/filterable segment
  table (by stabilized, MAR sign, wPPC+ band, id search) with conditional coloring,
  a **decision lens** (Scale / Cut / Watch per segment), the weights + telescoping
  self-check panel, a run-metadata header, and four charts (MAR, wPPC+, derived
  weights, closing-ratio-vs-wPPC). Opens offline — no network calls; all runtime
  (Vega-Lite + GSAP) is vendored and checksummed. Theme-aware (light/dark).
- **`wppc_{platform}_{slug}_{date}.md`** — an Obsidian-ready markdown record
  (run-metadata frontmatter + segments/weights/decay tables + static chart SVGs).
- **`wppc_{platform}_{slug}_{date}.xlsx`** — a formula-driven backup workbook:
  **Report** (segments sorted by MAR, conditional formatting, decay columns when a
  prior period is supplied), **Weights** (derived `w(S)` + self-check), **Charts**
  (native Excel charts), **Run** (the run-metadata block).
- **`wppc_{platform}_{slug}_{date}.weights.json`** — a weight-inputs snapshot
  (always written); pass it to a later run's `--weights-baseline` to detect drift.

**White-label:** the report leads with the account/segment data — no logo, no
agency credit, no third-party names in any emitted artifact. Safe to hand to a
client as-is.

## Required inputs

1. **Platform** — `google` or `meta`. One run scores exactly one platform; never
   compare raw wPPC across platforms.
2. **Segments CSV export** — a Google Ads or Meta Ads segment export (keywords,
   ads, etc.) with clicks and the funnel-event columns.
3. **Column-mapping YAML** — **mandatory**; no column names are hardcoded. Start
   from `config/`:
   - `config/mapping.example.yaml` — fully commented template to copy and adapt
   - `config/mapping.google.sample.yaml` — matches `sample_data/google_segments.sample.csv`
   - `config/mapping.meta.sample.yaml` — matches `sample_data/meta_segments.sample.csv`

   Required per platform: `skip_rows` (Google UI exports add 2 preamble rows),
   `segment_id`, `denominator` (the click — NOT impressions; Meta uses Link Clicks),
   a `funnel` column for each of
   `click / engagement / add_to_cart / initiate_checkout / purchase`, `repeats`, and
   `currency` (`CM3_order`, `repeat_rate`, `CM3_repeat`). A missing mapped column
   fails with a precise error naming the column and platform — it never guesses.
4. **Output directory** — ask the user where to save the bundle (e.g. `~/Downloads`).
   The tool owns the filenames; the user owns only the directory.

## How to run

Install the runtime once, then run the module. `cd` to the plugin root (the
directory containing `pyproject.toml`).

```bash
cd "<plugin root>"                       # quote it — the path may contain spaces
python3 -m pip install -r requirements.txt   # pandas, pyyaml, click, openpyxl, vl-convert-python==1.7.0
python3 -m wppc.cli report \
  --platform <google|meta> \
  --input <segments.csv> \
  --mapping <config/mapping...yaml> \
  --outdir <output-dir>                  # ask the user where to save
```

The final stdout line is machine-readable JSON with the written paths and headline
scalars: `{"md":…,"html":…,"xlsx":…,"weights":…,"baseline":…,"k":…,"k_source":…,"outdir":…}`.
After a successful run, point the user at the **HTML** first ("open this").

**Useful flags** (all optional, all default-off):
- `--formats md,html,xlsx` — write a subset (default: all three). The
  `.weights.json` sidecar is always written.
- `--no-animate` — build the HTML without GSAP motion.
- `--prior-input <prior.csv>` — enable the 2-export **decay** delta: per-segment
  wPPC+ movement (Rising / Flat / Falling) vs a prior period, kept separate from the
  point-in-time score. `--decay-band <pts>` sets the trend band (default 5.0).
- `--weights-baseline <prior.weights.json>` — flag weight-input **drift** beyond
  `--drift-tolerance` (default 0.15) vs a prior blessed snapshot.
- `--output <out.xlsx>` — back-compat alias: writes ONLY the xlsx to that exact
  path (plus its `.weights.json` sidecar). Mutually exclusive with `--outdir`.

### Worked example (bundled sample data)

```bash
cd "<plugin root>"
python3 -m wppc.cli report --platform google \
  --input sample_data/google_segments.sample.csv \
  --mapping config/mapping.google.sample.yaml \
  --outdir ~/Downloads
```

## Layer-5 incrementality seam (v1: inert)

An optional `--incrementality <file>` flag accepts a Layer-5 incrementality (IM)
table JSON from the separate Incrementality plugin — a
`{"tiers": [{"tier", "value", "ci", "power", "window", "timestamp"}, ...]}` shape.
In v1 the file is only loaded, shape-validated, and recorded ("provided, not
applied (v1)") — the correction is **not** applied to any score, so output with or
without the flag is identical. The full contract (pipeline placement, confidence
banding, staleness, tier granularity) is locked in
`wppc/references/incrementality-seam.md` for the fast-follow that wires the
multiplier in.

## Caveats

- **Never compare raw wPPC across platforms.** Indexing and shrinkage happen within
  one platform only; each run produces one bundle for one platform.
- **Weights, k, baseline, and replacement are always derived from your data at
  runtime.** Nothing is hardcoded — different exports yield different weights, so do
  not reuse numbers across accounts or date ranges.
- Treat `wPPC_shrunk` as prior-dominated when `stabilized = N` (clicks < k); gate
  scale/cut decisions on stabilized segments and MAR.
