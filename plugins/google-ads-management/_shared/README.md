# `_shared` — the shared toolkit

Data-transcription guards (`gaql_raw.py`, `reconcile.py`), the CSV
manual-input path (`csv_input.py`), the analytics primitives
(`analytics.py`), the widget emitter (`widget_emit.py`), and the
three-format render toolkit (`render/`, documented below).

## `analytics.py` — shared analytics primitives (HM-532)

Reusable, deterministic, kernel-mirrorable analytics — the machine-computed
pattern back-ported from the audit plugins (`meta-ads-audit` /
`shopify-cro-audit` `concentration.py` + `prescore.py`, which mirror the
MediaMetrics analytics module). Pure stdlib (`math` only) — importing
`analytics` never imports openpyxl, so it is safe everywhere (model cores,
specs, xlsx builders).

```python
import sys; sys.path.insert(0, "<plugin-root>/_shared")
from analytics import concentration, signals, pre_score, JS_MIRROR

concentration(rows, "cost", top_n=3)
#  -> {"n", "n_nonzero", "top_n", "total", "top_share", "hhi", "effective_n"}
flags = signals(rows, [{"id": "high_cost", "key": "cost", "op": "gt", "value": 100},
                       {"id": "over_2x_avg", "key": "cost", "op": "ge",
                        "value_key": "avg_cost", "mult": 2.0}])
#  -> one list of fired rule ids per row (row order preserved,
#     flags in rule declaration order; missing operand = rule does not fire)
pre_score({"flags": flags[0]}, {"high_cost": 3.0, "over_2x_avg": 5.0})
#  -> weighted sum over the row's UNIQUE flags, half-up 4dp
```

### Kernel-mirror contract

The exact arithmetic is normative and documented in the `analytics.py` module
docstring — JS and xlsx mirrors must match it verbatim:

- **Rounding** is half-up, `floor(x * 10^nd + 0.5) / 10^nd`, defined for the
  nonnegative quantities this module produces. JS:
  `Math.floor(x * Math.pow(10, nd) + 0.5) / Math.pow(10, nd)`; xlsx:
  `ROUND(x, nd)`. Python's banker's-rounding `round()` is never used. Keep
  thresholds/fixtures away from exact `.5` boundaries (binary-double edges are
  the one place xlsx `ROUND` can differ in the last decimal).
- **Coercion**: concentration values — finite *numeric-typed* values clipped
  to >= 0, everything else (strings included — a deliberate deviation from the
  audit plugins' `float(v)`) counts 0. Signal operands — finite number or
  *no signal* (the rule does not fire; missing data is never 0).
- **Ordering**: values are sorted descending before every float sum;
  `pre_score` sums over the sorted set of flag ids — results never depend on
  input row/flag order. Keep flag ids ASCII (Python and JS sort them
  identically only there).
- **concentration** math (per the audit plugins): `hhi = sum((v/total)^2) *
  10000` (0–10,000; half-up 1dp), `top_share = sum(top-N values)/total`
  (half-up 4dp), `effective_n = 1/sum((v/total)^2)` (inverse Simpson, half-up
  2dp). Empty/zero-sum -> all-zero metrics.
- **xlsx sketches**: `top_share = ROUND(SUM(LARGE(rng,{1..k}))/SUM(rng), 4)`;
  `hhi = ROUND(SUMPRODUCT((rng/SUM(rng))^2)*10000, 1)`; signals: one boolean
  column per rule; `pre_score = SUMPRODUCT(flag_cols, weights)`.

**`JS_MIRROR`** is the canonical browser translation (functions
`gxConcentration` / `gxSignals` / `gxPreScore` / `gxRoundHalfUp`). Skills
splice it into their spec's `js_kernel` instead of re-writing the math. The
Node<->Python parity gate covers it: `python3
skills/google-ads/tests/run_parity.py analytics-primitives` replays the shared
vectors (`_shared/tests/analytics_vectors.json`, plus any auto-discovered
`skills/*/tests/analytics_vectors*.json`) through both sides and asserts
equality. Editing `analytics.py` means editing `JS_MIRROR` in the same change —
the gate fails otherwise.

Tests: `python3 _shared/tests/test_analytics.py`.

## `csv_input.py` — shared CSV manual-input path (HM-533)

The CSV twin of the MCP path: when the MCP can't supply data (Auction
Insights, Customer Match match rates, Enhanced-Conversions/Consent-Mode
config) or the user simply has a Google Ads UI export, a skill assembles its
findings from the user-supplied CSV through the SAME transcription-firewall +
reconciliation discipline. Both paths produce an **identical findings/model
shape** — the skill's core cannot tell them apart, except by the honest
`meta.source` label (`"user_csv"`), which reports/artifacts must surface.
Pure stdlib (`csv`).

```python
import sys; sys.path.insert(0, "<plugin-root>/_shared")
from csv_input import assemble_from_csv, load_csv_rows, CsvInputError

rows, findings = assemble_from_csv(
    "export.csv",
    column_map=COLUMN_MAP,                       # the skill's own map (below)
    required_fields=("term", "campaign", "cost", "clicks", "conversions"),
    reconcile_spec={"array": "search_terms",     # where rows live in findings
                    "sums": ["cost", "clicks", "conversions"]},
    meta={"client_name": ..., "account_id": ..., "currency": ...,
          "window_90d": ..., "generated": ...})
# findings == {"meta": {..., "source": "user_csv", "reconciliation": {...}},
#              "params": {}, "search_terms": rows}
```

### How a skill declares its `column_map`

One entry per **logical field** (the key its findings rows carry), with an
alias list covering every header spelling the Google Ads UI may export
(locale/version variance) and a type:

```python
COLUMN_MAP = {
    "term":   {"aliases": ["Search term", "Search terms"], "type": "str"},
    "cost":   {"aliases": ["Cost"], "type": "num"},   # "Cost (CAD)" matches too
    "clicks": {"aliases": ["Clicks", "Interactions"], "type": "num"},
    "ctr":    {"aliases": ["CTR", "Interaction rate"], "type": "pct"},
}
```

- Matching is normalized (case-insensitive, whitespace-collapsed, BOM/quotes
  stripped); a parenthesised header suffix is tolerated (`Cost (CAD)` matches
  alias `Cost`, but `Cost per click` does not).
- Types: `str` (default), `num` (float; tolerates thousands separators,
  currency prefixes, `%`, and absent markers `''`/`--`/dashes → 0.0), `pct`
  (percent-scale column → fraction: `12.3%` → 0.123).
- Missing required columns and ambiguous mappings raise `CsvInputError`
  naming the fields, the offending columns, and the accepted aliases.
- UI-export quirks handled: title rows above the real header (defensive
  header-row scan anchored on `required_fields`), `Total: ...` summary rows
  dropped, extra unmapped columns ignored, UTF-8 BOM.
- When a real export uses a header spelling that isn't mapped yet, add it to
  the alias list **and a fixture test**, and append the lesson to the Lessons
  Log.

Skills assembling **several CSVs** into one findings dict call
`load_csv_rows(path, column_map, required_fields)` per file (→ `(rows,
provenance_stamp)`) and run `reconcile.build` themselves over the merged
arrays, exactly like an MCP-path `assemble_findings.py`.

### How the user is prompted for the export

The skill's SKILL.md instructs: in the Google Ads UI, open the relevant
report (e.g. *Insights & reports → Search terms*), set the **date range the
skill's window requires**, keep/add the columns the skill's `column_map`
needs, then **Download → .csv**, and share the file path. The skill then
runs `assemble_from_csv` — the file is parsed verbatim; numbers never pass
through the model (transcription firewall), and reconciliation stays
mandatory: findings without control totals warn/fail exactly as the MCP path
does. Never present CSV-sourced findings as an API pull — surface
`meta.source` in the report provenance.

Tests: `python3 _shared/tests/test_csv_input.py` (includes the MCP-vs-CSV
identical-shape assertion).

# `_shared/render` — the analytical-bundle toolkit

Shared, reusable renderers so every `google-ads-management` skill emits the same
three-format analytical deliverable from its own single-source-of-truth model:

- `*.md` — narrative report (provenance header, headline KPIs, sections, and a
  full per-row table so **no row is dropped**). Stdlib only.
- `*_explorer.html` — one self-contained file (inline CSS+JS, data embedded as
  JSON, **zero external references**); interactive where the skill has tunable
  params, a rich static explorer otherwise. Stdlib only.
- `*.xlsx` — formula-driven workbook, normalized through LibreOffice so it opens
  in Excel. The **only** part of the toolkit that imports `openpyxl`, and it is
  imported lazily (see below).
- `*_charts/*.svg` — optional deterministic Vega-Lite charts (one per declared
  chart), rendered at build time by `vl-convert` and referenced relatively from
  the md. The explorer renders the same charts **live** from the vendored
  runtime (`render/vendor/`). See "Charts" below.

This toolkit does **not** touch the Google Ads Editor apply-CSVs
(`google-ads-foundation/scripts/make_editor_csv.py`) — those are action files and
are produced separately by the skills.

## Public API

```python
import sys; sys.path.insert(0, "<plugin-root>/_shared")
from render import build_bundle, render_md, render_html
from render import model as render_model      # formatting + contract helpers

written = build_bundle(model, spec, outdir, formats=("md", "html", "xlsx"),
                       brand="Acme Corp", normalize=True)   # -> [Path, ...]
md  = render_md(model, spec)     # str
htm = render_html(model, spec)   # str
```

`openpyxl` is loaded lazily by `build_bundle` only when `"xlsx"` is requested, so
**importing `render` never imports `openpyxl`** (proven in
`render/tests/test_render_toolkit.py`). The xlsx build FAILS (`SystemExit 2`) if
LibreOffice (`soffice`) is missing and `normalize=True` — a file that may not open
in Excel is worse than a hard error.

## The model contract

`compute_model(findings)` (the skill's own single source of truth) returns a
JSON-serializable dict. The renderers rely on this minimum:

| key | meaning |
|---|---|
| `provenance` | `{client_name, account_id, currency, window_90d, window_30d, generated, params}` |
| `params` | resolved tunable parameters |
| `rows` | list of row dicts; **every input row present**, each with a `status` |
| `summary` | headline numbers (KPI source) |

Anything else the skill needs (benchmarks, sensitivity, near-misses, …) also lives
on the model and is surfaced through the spec's adapter functions — the generic
renderers never reach into skill-specific internals.

Guards in `render.model`: `require_model`, `assert_no_row_loss(model, n_input)`,
`require_spec`, plus `slugify / money / pct / num / mdcell / stem`.

## The spec contract

A per-skill dict describing how to render that model. Stdlib data + small adapter
functions + JS strings — **a spec never imports openpyxl**.

| field | used by | meaning |
|---|---|---|
| `slug_prefix`, `title` | all | filename stem + report title (required) |
| `methodology_ref` | md | path to the skill's authoritative reference doc |
| `md_params(model)` | md | extra provenance-table rows `[(label, value)]` |
| `md_kpis(model)` | md | headline bullets `[(label, value_str)]` |
| `md_narrative(model)` | md | optional prose lines (e.g. the "0/0 is clean" block) |
| `md_sections(model)` | md, xlsx | tables `[{title, note?, headers, rows, aligns?, empty?}]` |
| `md_rows(model)` | md | the full per-row table (no-row-loss layer) |
| `html_embed(model)` | html | the JSON embedded in the page |
| `html_controls` | html | sliders / number / multi controls bound to params |
| `html_columns` | html | the rows-table columns `{key,label,num?,fmt?}` |
| `html_kpis` | html | KPI cards `{label,key,cls?,money?}` over the summary object |
| `js_kernel` | html | JS string assigning `classify(r,P)` & `summarize(rows,P)` |
| `js_extra` | html | optional JS assigning `renderExtra(host,H)` (live panels) |
| `charts` | md, html, widget | declarative Vega-Lite chart list (see "Charts") |
| `chart_rows(model)` | charts | optional rows adapter; default `model['rows']` |
| `xlsx` | xlsx | the workbook layout (see `render/xlsx.py` docstring) |

`fmt` values: `money`, `pct`, `int`, `num`, `block`, `status`, `text`.

## Charts — generated, never authored

Charts are **declared** in the spec and **generated** by `render/charts.py`;
nobody (human or AI) ever hand-writes chart SVG/HTML. One declaration drives
both render paths — static SVG at build time (`vl-convert-python`, exact-pinned,
lazy-imported) and the live explorer charts (vendored Vega + Vega-Lite in
`render/vendor/`, pinned to the same Vega-Lite minor; see `vendor/VERSIONS.md`).
All aggregation lives in the Vega-Lite `transform` array, so the static and live
charts share one transform definition verbatim; the live charts re-derive from
the same `classify(r,P)`-augmented rows as the table on every control change.

```python
SPEC["charts"] = [{
    "id": "spend_by_block",        # stable [a-z0-9_]+ slug -> filename + DOM id
    "title": "Wasted spend by block",
    "mark": {"type": "bar"},       # verbatim Vega-Lite
    "transform": [                 # verbatim Vega-Lite — the ONE transform definition
        {"filter": "datum.block != ''"},
        {"aggregate": [{"op": "sum", "field": "cost", "as": "spend"}],
         "groupby": ["block"]},
    ],
    "encoding": {...},             # verbatim Vega-Lite
    "width": 640, "height": 240,   # optional; fixed defaults, never content-sized
    "md": True,                    # static SVG shipped with the md (default True)
    "widget": True,                # static SVG inlined in the tuner widget (default False)
}]
```

Determinism: canonical JSON (sorted keys) everywhere, fixed theme
(`charts.CLICKT_THEME`), no inline `data`, no `sample` transforms, chart data in
model-row order — same model + spec in, byte-identical SVG/HTML out (proven in
the toolkit tests). If charts are declared and `vl-convert` is missing the build
FAILS (`SystemExit 2`), mirroring the soffice discipline; `charts=False`
(CLI `--no-charts`) opts out explicitly. A chartless spec renders byte-identical
to the pre-chart toolkit.

The generic engine owns the **chrome** (provenance, KPI cards, sortable/filterable
row table, section tables, normalize, `--check`, slug/naming). The skill owns the
**compute kernel** — written once in Python (the model) and mirrored in `js_kernel`
(browser) and `xlsx` formula columns (Excel). The Node-vs-Python equality gate keeps
the Python and JS kernels in sync.

## Reference consumer

`skills/google-ads-keywords-search-terms/` drives this toolkit:
`waste_filter_core.py` (model/kernel) → `waste_filter_spec.py` (md/html spec) +
`waste_filter_xlsx_spec.py` (xlsx layout) → `build_waste_filter.py` (thin CLI).

## Tests

```
python3 _shared/render/tests/test_render_toolkit.py      # toolkit invariants
python3 skills/google-ads-keywords-search-terms/tests/test_filter.py
```
