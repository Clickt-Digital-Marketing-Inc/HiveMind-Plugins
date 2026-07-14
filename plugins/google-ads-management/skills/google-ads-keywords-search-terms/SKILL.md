---
name: google-ads-keywords-search-terms
description: Use when running a Google Ads search-query report (SQR) audit, managing negative keywords (three-tier framework), doing monthly keyword analysis, finding high-converting search terms to add as exact-match, or stopping spend on irrelevant queries. Pulls the live search terms report via the Google Ads MCP and outputs an .md report plus negative-keyword and add-keyword CSVs for Google Ads Editor. Also runs an advanced campaign-benchmarked two-block wasted-spend filter that emits a three-format analytical bundle (markdown report + self-contained interactive HTML explorer + tunable formula-driven .xlsx).
---

# Google Ads — Keywords & Search Terms

Turn the search terms report into action: capture converting queries, block budget bleed, keep ad
groups tightly themed. Negatives are the single most underused lever for cutting waste — and the
primary control under broad match / AI Max.

**Cadence:** SQR audit **weekly** for spend ≥ $10k/mo, **bi-weekly** for $2k–$10k, **monthly**
below that. Full keyword analysis **monthly**.

**REQUIRED BACKGROUND:** load `google-ads-foundation` first.

## When to use
- "Audit my search terms", "find negative keywords", "what should I add as keywords".
- CPA inflating without more conversions (irrelevant query bleed).
- Monthly keyword performance / expansion review.
- Running broad match or AI Max (negatives become the main guardrail).

## Pull the data
1. **Search terms report (30d)** — `search_term_view` query (cookbook) with cost, clicks,
   conversions, conversions_value, and `segments.keyword.info.text/match_type`.
2. **Existing campaign negatives** — `campaign_criterion` (negative=true) to avoid proposing dupes.
3. **Keyword performance + QS (30d)** — `keyword_view` for the monthly keyword analysis.

For the advanced two-block waste filter (below) pull **three** windows instead — search terms 90d,
search terms 30d (the conversion split), and campaign benchmarks 90d — per
[references/search-term-waste-filter.md](references/search-term-waste-filter.md).

> **Numbers never pass through the model.** Save every pull's raw result to a file (auto-saved
> `tool-results/*.txt` for big pulls; verbatim copy of the whole `{"result": [...]}` JSON for
> inline ones) and build the findings JSON with
> [scripts/assemble_findings.py](scripts/assemble_findings.py) — never type metrics into a JSON by
> hand. The assembler embeds reconciliation control totals that the core re-verifies on every
> build; hand-assembled or edited findings hard-fail. See the reference doc's "Transcription
> firewall" section for the exact command.

**No MCP? Use a CSV.** The waste filter also accepts three Google Ads UI exports instead of the
three raw pulls — ask for *Insights & reports → Search terms* (90d window, then again for the 30d
window) and *Campaigns* (90d window), then run `assemble_findings.py --csv-terms-90d ... \
--csv-terms-30d ... --csv-benchmarks ...`. Both paths run the same reconciliation discipline and
produce an identical model; the report's provenance always names the data source. See "The CSV
path" in [references/search-term-waste-filter.md](references/search-term-waste-filter.md).

## Diagnose — 4-bucket SQR segmentation
For each search term (dedupe, ≥ 30d), bucket per
[benchmarks](google-ads-foundation/references/benchmarks-2026.md):

| Bucket | Trigger | Action |
|---|---|---|
| High-converting | conversions ≥ 3 | add as **exact** in a themed ad group |
| Wasted spend | clicks ≥ 10 AND conversions = 0 | add as **campaign negative** (Phrase) |
| Informational | starts with how/what/why/guide/free/etc and is top-of-funnel vs a bottom-funnel campaign | negate or route to an awareness campaign |
| Competitor / junk | competitor names, irrelevant categories | add to a **shared** negative list |

Three-tier negative framework: **account/shared** (universal junk: free, jobs, careers, diy,
cheap, salary, images, meme), **campaign** (off-objective terms, competitors), **ad group**
(cross-contamination between themed groups — exact-match negatives).

Monthly keyword analysis: top performers (reallocate toward), rising CPC/falling CTR keywords,
keywords with impressions but 0 clicks, and gaps to expand into.

### Advanced — two-block campaign-benchmarked waste filter (conservative, tunable)
A stricter, auditable alternative to the "wasted spend" bucket, benchmarked against **each term's
own campaign** (not an account-wide rule). Match type ≠ Exact; defaults CTR factor **0.50**, cost
multiple **2.50**.
- **Block 1 — never-converted waste:** `conv(90d) = 0` AND `CTR < 0.50 × campaign CTR` AND
  `cost > 2.50 × campaign cost/conv` → add as negative.
- **Block 2 — decaying converters:** `conv(30d) = 0` AND `conv(90d) > 0` AND the same CTR/cost bars
  → review then negate.

Campaigns with 0 conv (90d) have an undefined cost/conv benchmark → segregate those terms as
*excluded*, never drop them silently. These thresholds are deliberately conservative: a clean
account often returns **0 / 0**, which is a valid result — present it honestly and use the workbook's
adjustable thresholds (and a sensitivity read as the cost multiple steps down) to surface
near-misses, rather than forcing hits. Full spec, the three GAQL pulls, and the findings-JSON schema
are in [references/search-term-waste-filter.md](references/search-term-waste-filter.md).

The waste filter also surfaces **n-gram concentration**: which unigrams/bigrams (tokens/token
pairs) concentrate the wasted spend across the flagged terms, with HHI/top-share/effective-N —
strong candidates for a single shared-negative rather than negating term-by-term. See "N-gram
concentration" in the reference doc.

## Recommend (Critical → High → Medium)
- **Critical:** add the wasted-spend queries (10+ clicks, 0 conv) as negatives now — direct bleed.
- **High:** add high-converting queries as exact-match in tightly themed ad groups; build/extend
  the shared junk negative list.
- **Medium:** route informational queries; expand into gap keywords; pause keywords with
  impressions but no clicks/conversions.

## Generate artifacts (in `artifacts/`)
- `*_report.md` — the primary deliverable: bucket counts, spend-saved estimate, top adds,
  keyword-analysis findings, and (if run) the two-block filter summary.
- `negative_keywords` CSV — bleed + competitor/junk terms (campaign-level or shared; **Phrase**
  default, Exact for single junk tokens; never Broad without justification).
- `add_keywords` CSV — converting search terms as Exact, mapped to the right ad group.
- **Two-block waste-filter bundle** — the standard three-format analytical deliverable, from one
  findings JSON via [scripts/build_waste_filter.py](scripts/build_waste_filter.py)
  (`--formats md,html,xlsx`), all rendered by the shared `_shared/render` toolkit from one model:
  - `*.md` — narrative: provenance, headline, the **0/0-is-clean** explanation, sensitivity table,
    near-misses, excluded campaigns, **and a full per-term table** (status + block; no row loss).
    Put this story in the report.
  - `*_explorer.html` — **interactive primary**: self-contained sliders + sensitivity + near-miss,
    opens in any browser (no install/Excel/cloud); embedded JS matches the Python model exactly.
  - `*.xlsx` — tunable Controls + Live-filter + Sensitivity workbook with a Status column (no row
    loss); needs `openpyxl`, LibreOffice-normalized so it opens in Excel.
  - `*_charts/*.svg` — deterministic Vega-Lite charts (wasted-spend-by-block bar, CTR-vs-cost
    scatter) rendered at build time and referenced from the md; the explorer renders the same
    charts live from the sliders. `--no-charts` skips them.

**Advisor loop.** After `build_waste_filter.py` emits the bundle it prints an advisor negatives
summary — top Block 1/2 terms by cost, the top wasteful n-grams (with concentration stats), and
total wasted spend, every figure read from the model — then offers the `negative_keywords` Editor
CSV. Open with the `*_explorer.html` (the hero deliverable) before narrating; present the summary
as Critical/High/Medium recommendations; generate the apply-CSVs only once the user confirms which
recommendations to act on. Full contract: `google-ads-foundation/references/artifact-formats.md`.

> **Charts are generated, never authored.** Every chart is produced by `build_waste_filter.py`
> through the shared chart module from the spec's `SPEC["charts"]` declaration. Never hand-write
> or edit SVG, Vega-Lite JSON, chart HTML, or the vendored JS; never "fix" a chart in the output
> file. If a chart is wrong, the spec or the model is wrong — change it there and re-run the
> builder. Same run, same chart, byte for byte.

The in-Claude **tuner** (`--emit-widget`) embeds only the in-play envelope (scored terms with
CTR below their campaign CTR — the only rows the sliders can ever surface) so it stays lean on large
accounts; headline counts come from the embedded full-model summary. This trimming is **live-preview
only** — the md/html/xlsx above always carry the full universe.

These are **analytical** deliverables. The Google Ads Editor **apply** files (negative/add-keyword
CSVs) are separate — generate them with `${CLAUDE_PLUGIN_ROOT}/skills/google-ads-foundation/scripts/make_editor_csv.py`.

## Resources
- [references/search-term-waste-filter.md](references/search-term-waste-filter.md) — **authoritative**
  two-block spec, the three GAQL pulls, conversion-metric note, findings-JSON schema, output bundle,
  and the Excel-open honesty.
- [scripts/waste_filter_core.py](scripts/waste_filter_core.py) — the single-source classification
  engine / model (stdlib only); its math is mirrored in the spec's `js_kernel` and xlsx formulas.
- [scripts/waste_filter_spec.py](scripts/waste_filter_spec.py) — the md/html render spec (KPIs,
  sections, full row table, controls, columns, JS kernel) consumed by the shared toolkit.
- [scripts/waste_filter_xlsx_spec.py](scripts/waste_filter_xlsx_spec.py) — the xlsx workbook layout
  (Controls / Live filter / Sensitivity), pure data, no openpyxl.
- [scripts/build_waste_filter.py](scripts/build_waste_filter.py) — thin CLI: builds the md/html/xlsx
  bundle via `_shared/render`.
- [scripts/build_search_term_filter_workbook.py](scripts/build_search_term_filter_workbook.py) — thin
  xlsx CLI wrapper (`--check`, `--normalize/--no-normalize`).
- The shared toolkit: `../../_shared/render` (see `../../_shared/README.md`) — `build_bundle`,
  `render_md`, `render_html`, and the lazy-openpyxl `xlsx` renderer.
- [tests/test_filter.py](tests/test_filter.py) + [tests/sample-findings.json](tests/sample-findings.json)
  — unit tests (fixture, no-row-loss, dedupe, empty, fractional-conv, n-gram/advisor-summary,
  md/html bundle parity + lazy import) and the synthetic fixture.
- [tests/test_csv_path.py](tests/test_csv_path.py) — the CSV dual-input path: MCP-vs-CSV identical
  model, UI match-type label mapping, the Campaign-ID/name join-key fallback, malformed-export
  errors.
- [tests/test_ngram_parity.py](tests/test_ngram_parity.py) — this skill's own Node JS<->Python
  parity check for the n-gram mirror spliced into `waste_filter_spec.JS_KERNEL` (needs `node`).

## Common mistakes / red flags
- **Never** propose Broad-match negatives without explicit justification — they silently block
  valid traffic. Default to Phrase.
- Check the proposed negative won't block an existing converting keyword/term (cross-reference the
  high-converting bucket and existing negatives) before adding.
- Don't add an "exact" keyword that duplicates an existing one (dedupe by text+match_type).
- Adding keywords/negatives is **manual** (read-only MCP) — deliver the CSVs for Editor import.
- AI Max / broad match → lean harder on negatives; recommend conversion-tracking maturity first.
