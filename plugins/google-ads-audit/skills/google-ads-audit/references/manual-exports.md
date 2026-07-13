# Manual exports — the no-MCP path

When the `google-ads-mcp` server is not connected, the audit runs from **CSV
exports the user downloads from the Google Ads web UI**. Walk the user through
the three exports below, then build with `--csv-dir` (or the explicit
`--csv-campaigns` / `--csv-keywords` / `--csv-search-terms` flags).
`scripts/manual_csv.py` parses the files verbatim and deterministically —
numbers never pass through the model.

## Honesty rules

- The manual path fully powers the **Concentration** report and gives solid
  evidence for **account structure, performance, keyword strategy (incl.
  Quality Score), and budget & bidding basics**.
- Checks whose data is not in these exports (ad assets detail, conversion
  actions, audiences, recommendations, PMax internals) are marked
  **N/A — "Not available from manual export"**. Never approximate them.
- Files must be **verbatim downloads**: no re-saving, trimming, or editing.
  The parser expects the UI's preamble lines, `Total:` footer rows, and
  display formatting, and handles them itself.

## The three exports (Google Ads web UI, English interface)

Tell the user, for each report: set the **date range** (top right) first, then
**Download (⬇) → .csv**.

### 1. Campaign report → `campaigns.csv`
*Campaigns page · recommended range: last 90 days.*
Ensure these columns are on (⚙/Columns → Modify columns):
**Campaign, Campaign type, Cost, Conversions** (required by the parser) plus —
recommended for the audit checks — Impressions, Clicks, CTR, Avg. CPC,
Conv. value, Cost/conv., Search impr. share, Search lost IS (budget),
Search lost IS (rank), Bid strategy type, Budget.

### 2. Search keyword report → `keywords.csv`
*Keywords → Search keywords · same range.*
Required: **Keyword, Match type, Cost, Conversions**. Recommended: Campaign,
Ad group, Status, **Quality Score, Exp. CTR, Landing page exp., Ad relevance**,
Impressions, Clicks — the QS trio powers the keyword-strategy checks.

### 3. Search terms report → `search_terms.csv`
*Keywords → Search terms · last 30 days (or match the others; the report is
labeled with its own range either way).*
Required: **Search term, Cost, Conversions**. Recommended: Match type,
Added/Excluded, Campaign, Impressions, Clicks. Note: PMax-sourced terms appear
with Match type "Performance Max" — they are kept.

## Build

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/google-ads-audit/scripts/build_audit.py" \
  --input findings.json --outdir "<user-chosen-dir>" --brand "{Client Name}" \
  --csv-dir "<dir-with-the-three-csv-files>"
```

`--csv-dir` expects the canonical names `campaigns.csv` / `keywords.csv` /
`search_terms.csv`; the UI's default names ("Campaign report.csv" …) work via
the explicit flags without renaming. Each Concentration dimension is labeled
with **its own file's date range** (read from the export's second line), so
mismatched windows stay honest. `--csv-*` and `--raw-*` are mutually
exclusive — one source of truth per build.

## Which columns unlock which machine-scored checks

The deterministic pre-scorer (`scripts/prescore.py`) machine-scores checks when
their columns are present; missing columns just fall back to auditor judgment
(the pre-scorer lists them under `skipped`):

| Export column(s) | Unlocks |
|---|---|
| Campaign report: Impr. + Clicks | PR-01 (Search CTR vs benchmark) + CTR KPI |
| Campaign report: Search impr. share | PR-04 + KPI |
| Campaign report: Search lost IS (budget) / (rank) | PR-05 / PR-06 + KPIs |
| Campaign report: Bid strategy type | BB-02 (eCPC), KW-03 join, BB-01 evidence |
| Campaign report: Conv. value | PR-03 ROAS evidence |
| Keyword report: Ad group + Campaign | KW-05 / AS-03 duplicate detection |
| Keyword report: Quality Score | Quality Score (cost-wtd) KPI |
| Search terms report: (required columns) | KW-02 wasted spend |
| Search terms report: Added/Excluded | excludes already-negatived terms from KW-02 |

## Known export quirks (handled by the parser — do not "fix" the files)

Two preamble lines (title + date range) before the header; multi-line cells
inside quotes (e.g. "Ad strength details"); `--` placeholders; `%` suffixes;
thousands separators; `CA$`-style currency prefixes; `Total:` footer rows;
UTF-8 BOM. A wrong file for a slot fails loudly with "is this the right
report?" — it never mis-parses silently.
