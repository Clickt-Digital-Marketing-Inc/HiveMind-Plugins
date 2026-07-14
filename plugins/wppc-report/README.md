# wPPC — Weighted Profit-Per-Click

A sabermetric linear-weights report for Google & Meta Ads segment exports. Every
funnel event is credited at its expected contribution-margin (CM3) value, indexed
to the account baseline, shrunk for sample size, and scored above replacement — so
the report surfaces *true value* per click and gates noisy decisions, instead of
ranking on margin-blind CVR/ROAS.

> Weights, k, baseline, and replacement are **always derived from your data at
> runtime**. Nothing is hardcoded. Index and shrink **within one platform only** —
> never compare raw wPPC across Google vs Meta.

## Install

```bash
cd wppc-report
pip install -r requirements.txt   # pandas, pyyaml, click, openpyxl, vl-convert-python==1.7.0
# or, as an editable package (adds the `wppc` console script):
pip install -e .
pip install -e ".[test]"          # + pytest, to run the suite
```

## Run

One run scores one platform and writes a bundle into a directory **you** choose —
the tool owns the filenames (`wppc_{platform}_{slug}_{date}.*`):

```bash
python3 -m wppc.cli report --platform google \
  --input sample_data/google_segments.sample.csv \
  --mapping config/mapping.google.sample.yaml \
  --outdir ~/Downloads
```

One `build_model` computes every number once; three formats render it (no format
re-derives a number):

- **`.html`** — the primary deliverable: a self-contained, interactive, white-label
  report. Sortable/filterable segment table, a **Scale / Cut / Watch** decision lens,
  the weights + self-check panel, and four charts (MAR, wPPC+, derived weights,
  closing-ratio-vs-wPPC). Opens offline — Vega-Lite + GSAP are vendored and
  checksummed. Theme-aware (light/dark).
- **`.md`** — an Obsidian-ready record (run-metadata frontmatter + tables + static
  chart SVGs).
- **`.xlsx`** — a formula-driven backup: **Report / Weights / Charts / Run** tabs.
- **`.weights.json`** — a weight-inputs snapshot (always written); feed it to a later
  run's `--weights-baseline` to detect drift.

The final stdout line is machine-readable JSON with the written paths and headline
scalars (`md, html, xlsx, weights, baseline, k, k_source, outdir`).

**White-label:** every emitted artifact leads with the account/segment data — no
logo, no agency credit, no third-party names. Safe to hand to a client as-is.

Useful optional flags (all default-off): `--formats md,html,xlsx` (subset),
`--no-animate` (HTML without GSAP), `--prior-input <prior.csv>` (+ `--decay-band`) for
the 2-export decay delta, `--weights-baseline <prior.weights.json>` (+
`--drift-tolerance`) for weight-drift detection, `--incrementality <file>` (v1 inert
Layer-5 seam — see `wppc/references/incrementality-seam.md`), and `--output <out.xlsx>`
as a back-compat alias that writes only the xlsx.

## Column mapping (no column names are hardcoded)

Copy [`config/mapping.example.yaml`](config/mapping.example.yaml), point each
concept at the exact header in **your** export, and pass it with `--mapping`. Set
`skip_rows` to the number of preamble rows your export has (Google UI exports add
2: a title row and a date-range row). If a mapped column is missing, the run fails
with a precise error naming the column and platform — it never guesses.

Required per platform: `skip_rows`, `segment_id`, `denominator` (the click — NOT
impressions; Meta uses Link Click), a `funnel` column for each of
`click / engagement / add_to_cart / initiate_checkout / purchase`, `repeats`, and
`currency` (`CM3_order`, `repeat_rate`, `CM3_repeat`).

## The metrics

- **wPPC** — expected CM3 per click: `(Σ reach(S)·w(S) + repeats·w(repeat)) / clicks`.
  The weights `w(S)` are the incremental profit expectancy of reaching each funnel
  state, derived so they telescope to `CM3_order` along a full path (self-checked).
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

## Tests

```bash
pytest -q
```

Covers the weight telescoping self-check, the two-keyword worked example
(A = 4.08, B = 2.59), shrinkage pulling a thin segment toward baseline, the k
fallback, the `skip_rows`/missing-column behavior, the monotonicity clamp, and the
render contract (3-format agreement, HTML self-containment, vendored-asset SHA-256
parity, `animate=False` zero-GSAP, and determinism modulo the injected timestamp).

> Note: the source framework states keyword B = 2.89, but its listed line items
> telescope to 1,035.30, i.e. **2.59** — an arithmetic slip in the doc. The
> methodology is authoritative, so the fixture asserts 2.59. Keyword A (4.08) is
> correct in the source and reproduced exactly.
