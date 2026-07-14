# Search-Term Waste Filter — two-block, campaign-benchmarked (advanced)

A stricter, tunable alternative to the 4-bucket SQR segmentation. It flags loose-match search terms
that waste spend, benchmarked against **each term's own campaign**, and ships the standard
three-format analytical bundle: a **markdown report** (narrative + a full per-term table), a
**self-contained interactive HTML explorer** (sliders + sensitivity, opens in any browser with no
install), and a **formula-driven xlsx** (LibreOffice-normalized so it opens in Excel). Reuses every
`google-ads-foundation` convention (micros, dates, `SEARCH` scope, dedup) — load that first.

All three formats are rendered by the shared toolkit (`_shared/render`) from one classification
engine (`scripts/waste_filter_core.py`), so they can never disagree; this file is the
**authoritative** input/output contract (the scripts' docstrings point here rather than restating
it).

## The two blocks

Each condition is AND-joined. Match type is **≠ Exact** (so Broad, Phrase, and the close variants
`NEAR_EXACT` / `NEAR_PHRASE`, plus `AI_MAX`). Conservative defaults: CTR factor **0.50**, cost
multiple **2.50**.

- **Block 1 — never-converted waste** → add as negative:
  `conversions(90d) ≤ 0` AND `CTR(90d) < 0.50 × campaign CTR(90d)` AND
  `cost(90d) > 2.50 × campaign cost/conversion(90d)`.
- **Block 2 — decaying converters** → review then negate:
  `conversions(30d) ≤ 0` AND `conversions(90d) > 0` AND the same CTR and cost bars.

Campaigns with **0 conversions in 90d** have an undefined cost/conv benchmark → their terms cannot
qualify. Report them as *excluded (no benchmark)*; never silently drop them.

**Conservative by design.** On well-managed accounts this often returns **0 / 0** — a valid
clean-bill result, not a bug (a single loose-match term rarely out-spends 2.5 conversions while also
under-indexing on CTR). Do not force hits. Instead, present the zero result honestly and let the
workbook's adjustable thresholds reveal near-misses (e.g. lowering the cost multiple). A useful read
is the threshold sensitivity: how many terms qualify as the cost multiple steps down (2.5 → 1.0 →
0.5 → 0.25).

## The three GAQL pulls (`mcp__google-ads-mcp__search_search`)

> **Gotcha:** `LAST_90_DAYS` is **not** a valid GAQL date literal (only `LAST_7/14/30_DAYS` exist).
> Use an explicit `BETWEEN`. To match Google's `LAST_N_DAYS` convention, **end the window
> yesterday** (today's data is partial) and keep the 30d window's end date identical to the 90d's.

**1 — Search terms, last 90 days** (the universe; cost/CTR/conversions per term):
```
resource:   "search_term_view"
fields:     ["campaign.id","campaign.name","ad_group.name","search_term_view.search_term",
             "segments.search_term_match_type","metrics.conversions","metrics.clicks",
             "metrics.impressions","metrics.ctr","metrics.cost_micros"]
conditions: ["segments.date BETWEEN '<90d-start>' AND '<yesterday>'",
             "campaign.advertising_channel_type = 'SEARCH'",
             "segments.search_term_match_type != 'EXACT'",
             "metrics.cost_micros > 0"]
orderings:  ["metrics.cost_micros DESC"]
```

**2 — Search terms, last 30 days** (only the conversion split Block 2 needs). Pull terms with
`metrics.conversions > 0` to get the *converted-in-30d* set; any term not in it has `conv(30d)=0`:
```
resource:   "search_term_view"
fields:     ["campaign.id","ad_group.name","search_term_view.search_term",
             "segments.search_term_match_type","metrics.conversions"]
conditions: ["segments.date BETWEEN '<30d-start>' AND '<yesterday>'",
             "campaign.advertising_channel_type = 'SEARCH'",
             "segments.search_term_match_type != 'EXACT'",
             "metrics.conversions > 0"]
```

**3 — Campaign benchmarks, last 90 days** (per-campaign CTR and cost/conversion):
```
resource:   "campaign"
fields:     ["campaign.id","campaign.name","metrics.ctr","metrics.cost_micros","metrics.conversions"]
conditions: ["segments.date BETWEEN '<90d-start>' AND '<yesterday>'",
             "campaign.advertising_channel_type = 'SEARCH'"]
```
Per campaign: `campaign cost/conv = (cost_micros/1e6) / conversions` (compute from raw — do **not**
use `metrics.cost_per_conversion`, which is also micros). Skip `conversions = 0` (undefined).

**Which conversion metric.** Use `metrics.conversions` — the account's **primary** conversion goals,
attribution-modeled, and often **fractional** (e.g. `2.75`). Do not substitute
`metrics.all_conversions` (counts secondary actions too) or the filter will under-flag waste. The
same metric must be used for both the per-term `conversions_*` and the campaign benchmark so the
comparison is like-for-like.

**Transcription firewall (mandatory).** Every pull's raw result must land in a file before
anything else happens: the big 90d pull usually exceeds the MCP token cap and auto-saves to a
`tool-results/*.txt` file — use that file as-is; for pulls that come back inline, copy the whole
tool result **verbatim** (the complete `{"result": [...]}` JSON, unedited) into a file. Then build
the findings JSON with `scripts/assemble_findings.py` — never assemble it by hand:

```
python3 scripts/assemble_findings.py \
  --terms-90d <raw-90d-file> --terms-30d <raw-30d-file> --benchmarks <raw-benchmarks-file> \
  --client-name "{Client Name}" --account-id {account} --currency {CUR} \
  --window-90d "<90d-start> to <yesterday>" --window-30d "<30d-start> to <yesterday>" \
  -o findings.json
```

The assembler parses the raw files (micros conversion, per-key aggregation, the 30d join),
embeds control totals as `meta.reconciliation`, and `waste_filter_core` re-verifies those totals
on every build — a findings JSON whose numbers were typed or edited by hand hard-fails. Metric
values therefore never pass through the model: the model handles file paths and meta labels
(client name, account id, windows), and the pipeline handles the numbers. `assemble()` stamps
`meta.source = "mcp"`.

## The CSV path (dual input — no MCP required)

When the MCP is unreachable or the user prefers a UI export, the same three data points come from
**three Google Ads UI exports** instead of three saved raw pulls (the dual-input contract in
`google-ads-foundation/references/artifact-formats.md`):

1. **Search terms report, 90d window** — *Insights & reports → Search terms*, date range set to
   the 90d window, columns: Search term, Match type, Campaign, Ad group, Impr., Clicks, Cost,
   Conversions.
2. **Search terms report, 30d window** — same report, 30d window, same columns (only the
   conversion split matters; rows with 0 conversions are harmless noise, not required).
3. **Campaigns report, 90d window** — *Campaigns*, 90d window, columns: Campaign, CTR, Cost,
   Conversions.

Optionally add a **Campaign ID** column (customize columns → Attributes) to any/all three exports
for an exact join key identical to the MCP path's `campaign.id`; without it, the campaign **name**
is used as the join key (correct unless two campaigns share a display name).

```bash
python3 scripts/assemble_findings.py \
  --csv-terms-90d terms90.csv --csv-terms-30d terms30.csv --csv-benchmarks bench.csv \
  --client-name "{Client Name}" --account-id {account} --currency {CUR} \
  --window-90d "<90d-start> to <yesterday>" --window-30d "<30d-start> to <yesterday>" \
  -o findings.json
```

`assemble_csv()` (in `scripts/assemble_findings.py`) parses the three files through
`_shared/csv_input.load_csv_rows` with this skill's `TERMS_COLUMN_MAP` / `BENCH_COLUMN_MAP`
(aliases + types), maps the UI's "Match type" label to the GAQL enum `waste_filter_core` expects
(`MATCH_TYPE_UI_MAP`; add an entry + a fixture test if a real export uses an unmapped spelling),
drops EXACT rows the same way the MCP path does, embeds the same `meta.reconciliation` control
totals, and stamps `meta.source = "user_csv"`. The two paths yield an **identical**
`compute_model()` output for the same underlying data (proven in
`tests/test_csv_path.py::test_csv_matches_mcp_model`) — `waste_filter_core` cannot tell them apart
except by the honest `source` label, which the report's provenance surfaces ("Data source" row).

## The findings JSON

What the assembler produces (and the script's input contract):

```json
{
  "meta":   {"client_name","account_id","currency","window_90d","window_30d","generated",
             "source"},                        // optional; "mcp" (default) | "user_csv"
  "params": {                                  // all optional; defaults below = rule "as written"
     "ctr_factor": 0.50,
     "cost_multiple": 2.50,
     "block1_max_conv_90d": 0,
     "block2_min_conv_90d": 0,
     "block2_max_conv_30d": 0,
     "match_types_in_scope": ["BROAD","PHRASE","NEAR_EXACT","NEAR_PHRASE","AI_MAX"]
  },
  "benchmarks":   [{"campaign_id","campaign","ctr","cost","conversions"}],   // 90d; cost already /1e6
  "search_terms": [{"campaign_id","campaign","ad_group","term","match_type",
                    "impressions","clicks","ctr","cost",                     // cost already /1e6
                    "conversions_90d","conversions_30d"}]
}
```
`ctr` is a ratio (0.10 = 10%). `cost` is in the account currency (already divided by 1e6).

## Build the deliverable bundle

```bash
# md + html — dependency-free, needs only Python
python3 scripts/build_waste_filter.py \
  --input findings.json --outdir artifacts --brand "{Client Name}" \
  --formats md,html
# all three (xlsx needs openpyxl; normalizes via LibreOffice)
python3 scripts/build_waste_filter.py \
  --input findings.json --outdir artifacts --brand "{Client Name}" \
  --formats md,html,xlsx
```
Files land in `artifacts/` as `search-term-waste_{account}_{date}.{ext}`
(`.md`, `_explorer.html`, `.xlsx`). Run the unit tests with `python3 tests/test_filter.py`, the
CSV dual-input tests with `python3 tests/test_csv_path.py`, this skill's own n-gram JS<->Python
parity check with `python3 tests/test_ngram_parity.py` (needs `node`, no npm packages), and the
shared-toolkit tests with `python3 ../../_shared/render/tests/test_render_toolkit.py`.

**What each format is for** — all rendered by `_shared/render` from one model, so no two can disagree.
- `*.md` — the narrative / trust layer: provenance header (account, windows, currency, generated,
  thresholds), headline counts, the **"0/0 = clean account"** explanation, the **sensitivity table**,
  the **near-miss** ranking, the **excluded-campaign** list, and a **full per-term table** with each
  row's `status` and assigned `block` (the no-row-loss layer). Zero dependencies.
- `*_explorer.html` — the **interactive primary**: self-contained (inline CSS+JS, data embedded, no
  external refs), with range **sliders** (CTR factor, cost multiple), conversion-threshold inputs,
  match-type toggles, live counts + wasted spend, a **sensitivity strip**, a **near-miss** list, and
  the full term table with status badges + a "qualifying only" toggle. Opens in any browser — no
  install, no Excel, no cloud. The headline "0/0 is clean" question is answered at a glance. The
  embedded JS computes byte-identical results to the Python model (Node-verified).
- `*.xlsx` — the tunable Controls + Live-filter workbook (see layout below), with a **Sensitivity**
  tab and a **Status** column (no row loss). Built via the shared `render.xlsx`; the wrapper
  `scripts/build_search_term_filter_workbook.py --check` validates an existing file.

**Currency** from `meta.currency` is shown in every header and on cost columns.

**Excel-open honesty.** openpyxl output can fail to open in Excel-for-Mac, so the xlsx is
**normalized through LibreOffice** (`soffice`) by default — this writes the structure Excel expects
and caches values *while preserving every formula*. If `soffice` is missing the xlsx build **fails
(exit 2)** rather than shipping a file that may not open (`--no-normalize` overrides). `--check`
**fails** on a file with no cached values. Real-Excel open is **not** verified in CI — the
verified-open paths are the **HTML explorer** and **LibreOffice**; recommend the buyer confirm the
xlsx in Excel once if that is their primary surface. For a zero-friction interactive deliverable that
needs no spreadsheet app at all, prefer the **HTML explorer**.

## N-gram concentration (top wasteful tokens)

`compute_model()` adds a `ngrams` block: unigrams + adjacent bigrams tokenized from every Block
1/2 term's text (lowercase, whitespace-split, unique per term), with wasted spend summed per
n-gram (`waste_filter_core.term_ngrams` / `waste_ngrams`). `_shared/analytics.concentration` (the
shared HHI / top-share / effective-N primitive, HM-532) runs over the n-gram-cost distribution so
the report can say, e.g., "the top 5 n-grams carry 64% of the n-gram-weighted waste." Surfaced in
every format: a "Top wasteful n-grams" table in the md (and, via `snapshot_sections`, the xlsx
Sensitivity tab), a live-recomputing card in the HTML explorer (`gxTermNgrams` / `gxWasteNgrams`,
spliced into `js_kernel` alongside `analytics.JS_MIRROR`), and the advisor summary's top-5 callout.
These are candidates for a **shared/account-level** negative — a token appearing across several
wasteful terms is worth blocking once rather than term-by-term.

## The advisor loop

`scripts/build_waste_filter.py` prints `waste_filter_core.advisor_summary(model)` after every
emit — the *recommend* step of the emit → report → recommend → offer-apply loop
(`google-ads-foundation/references/artifact-formats.md`). It cites the model's own numbers only
(top Block 1/2 terms by cost, the top-5 wasteful n-grams with concentration stats, total wasted
spend) and closes by naming the Editor CSV offer (`negative_keywords` via `make_editor_csv.py`) —
never generated automatically. A 0/0 result prints the clean-account message instead of forcing a
citation.

## xlsx layout

**Controls** sheet — five sections driving the same formulas: (1) **Filter parameters** — yellow
dropdowns: CTR factor `C5`, cost multiple `C6`, Block 1 max conv90 `C7`, Block 2 min conv90 `C8`,
Block 2 max conv30 `C9`; (2) **Match types in scope** — `yes/no` per type (`C12:C16`, enum `B12:B16`);
(3) **Filter & block logic** — plain-language rules that **rewrite themselves** from those cells;
(4) **Results (live)** — `COUNTIF`/`SUMIF` over the Live-filter `Qualifies` column; (5) **Campaign
benchmarks**.

**Live filter** sheet — **every** loose-match term (frozen header + auto-filter; qualifying rows
highlighted). A **Status** column marks `scored` vs `no benchmark`; `no benchmark` rows keep their
metrics but are left unscored (never dropped, never miscounted). Scored rows carry formula columns
referencing the Controls cells (`CTR threshold = campaign CTR × Controls!C5`, `Cost threshold =
campaign cost/conv × Controls!C6`, `Match in scope? = VLOOKUP(...)`, `Block1?`/`Block2?` = AND() of
the conditions, `Qualifies` = `Block 1` / `Block 2` / "").

**Sensitivity** sheet — a static snapshot at the generated parameters: qualifiers per cost multiple,
the top near-misses per block (with "qualifies if cost-multiple ≤ X"), and the excluded-campaign
list.

Changing any Controls cell recomputes the Live filter and the counts — no rebuild needed.
