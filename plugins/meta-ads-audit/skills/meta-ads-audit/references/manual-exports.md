# Manual exports — the no-MCP path

> **NEEDS-REAL-EXPORT-VALIDATION.** The column names on this page (and in
> `scripts/manual_csv.py`) are encoded from the documented Meta Ads Manager export
> format, NOT yet validated against real export files. Column spellings, the
> summary-row shape, and the ranking value strings must be confirmed against genuine
> exports before this path is trusted for client work. Until then, any mismatch
> surfaces loudly through the parser's wrong-report guard ("is this the right
> report?") — it never mis-parses silently. English-language exports assumed.

When the Meta Ads MCP is not connected, the audit runs from **CSV exports the user
downloads from Meta Ads Manager**. Walk the user through the three exports below, then
build with `--csv-dir` (or the explicit `--csv-campaigns` / `--csv-adsets` /
`--csv-ads` flags). `scripts/manual_csv.py` parses the files verbatim and
deterministically — numbers never pass through the model.

## Honesty rules

- The manual path fully powers the **Concentration** report and gives solid evidence
  for **account architecture, budget & pacing, attribution mix, and creative
  performance basics** — and it is the **only** path that scores **CR-04 (CTR-Link)**
  and unlocks **ranking decomposition** (see below).
- Checks whose data is not in these exports (dataset/pixel health, EMQ, CAPI, ad
  created dates → CR-08 refresh cadence, audience/catalog internals) are marked
  **N/A — "Not available from manual export"**. Never approximate them.
- Files must be **verbatim downloads**: no re-saving, trimming, or editing. The parser
  handles the summary row, `--` placeholders, currency-suffixed headers, and quoted
  multi-line cells itself.
- Every file's window is read from its own **Reporting starts / Reporting ends**
  columns — mismatched windows stay honest because each metric line names the window
  it was measured on.
- Meta results are objective-relative: include the **Result indicator** column so the
  parser can tell Leads from Reach — results-based checks are only scored when the
  indicators are homogeneous.

## The three exports (Ads Manager → Reports → Export table data → .csv)

Set the **date range** first, pick the level tab (Campaigns / Ad sets / Ads), make sure
the columns below are in the report (Columns → Customize columns), then export as
**.csv**. Include **Reporting starts / Reporting ends** on every export (usually
automatic).

### 1. Campaign export → `campaigns.csv`
*Campaigns tab · recommended range: last 30 days.*
Required: **Campaign name, Amount spent, Impressions, Results**. Recommended:
Result indicator, Reach, Frequency, Clicks (all), CTR (all),
CPM (cost per 1,000 impressions), Objective, Bid strategy, Campaign budget,
Campaign budget type.

### 2. Ad set export → `adsets.csv`
*Ad sets tab · same range (last 30 days).*
Required: **Ad set name, Amount spent, Impressions, Results**. Recommended:
Campaign name, Result indicator, Reach, **Frequency**, Clicks (all),
**Attribution setting**, Objective, Ad set budget, Ad set budget type.
> **Frequency-bands trade-off:** CR-07 gets its true bands
> (<3 PASS / 3–5 FLAG / >5 FAIL) only when the ad-set file's own window is ≤ 8 days;
> on a 30-day export it runs in PASS-only mode (FLAG ceiling, never FAIL). The CSV
> path has no separate 7-day slot — if the user can export twice, run
> `--prescore-only` a second time with a **last-7-days ad-set export** as
> `adsets.csv` to read the true frequency bands, and keep the 30-day file for the
> main build (AR-02's 25-results learning floor assumes ~30 days). The MCP raw path
> handles both windows in one build via `adsets_7d.json`.

### 3. Ad export → `ads.csv`
*Ads tab · recommended range: last 90 days (creative window).*
Required: **Ad name, Amount spent, Impressions, Results**. Recommended:
Campaign name, Result indicator, Reach, Frequency, Clicks (all), **Link clicks**,
CTR (all), CPM (cost per 1,000 impressions), ThruPlays, Video plays at 25%,
Video plays at 50%, Video plays at 75%, Video plays at 100%,
**Quality ranking, Engagement rate ranking, Conversion rate ranking**.

**The rankings columns are the CSV-only unlock**: Quality / Engagement rate /
Conversion rate ranking power the Creative Signals **ranking decomposition** (the raw
MCP path cannot request them). Values like `Below average (bottom 20% of ads)`
canonicalize to `BELOW_AVERAGE`; `Not enough data` / blanks are omitted honestly.
**Link clicks** is likewise CSV-only and is what makes CR-04 (CTR-Link, Ecommerce)
scorable — the raw path's all-click CTR is evidence-only.

## Build

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/meta-ads-audit/scripts/build_audit.py" \
  --input audit-payload.json --outdir "<user-chosen-dir>" --brand "{Client Name}" \
  --csv-dir "<dir-with-the-three-csv-files>" --business-model "{Lead Gen|Ecommerce}"
```

`--csv-dir` expects the canonical names `campaigns.csv` / `adsets.csv` / `ads.csv`;
other filenames work via the explicit flags without renaming. `--csv-*` and `--raw-*`
are mutually exclusive — one source of truth per build. Run
`--prescore-only --csv-dir …` first, exactly as on the MCP path.

## Which columns unlock which machine-scored checks

The deterministic pre-scorer (`scripts/prescore.py`) machine-scores checks when their
columns are present; missing columns just fall back to auditor judgment (listed under
`skipped` with the reason).

| Export column(s) | Unlocks |
|---|---|
| Campaign export: required columns | AR-01 (top-3 spend share), BP-02 (spend vs results — homogeneous Result indicator only), Spend / Results / Cost-per-Result KPIs, Concentration campaigns dimension |
| Campaign export: Objective | Concentration objectives dimension |
| Campaign export: Bid strategy / budget columns | BP-04 / BP-01 evidence |
| Ad set export: required columns | AR-02 (learning starvation), Concentration ad_sets dimension |
| Ad set export: Attribution setting | AT-02, AT-03 + AT-01 evidence |
| Ad set export: Frequency | CR-07 (PASS-only on 30d; true bands iff the file's window ≤ 8 days) + effective-frequency zones |
| Ad export: required columns | CR-06 (top-5 ad spend share), Concentration ads dimension |
| Ad export: Reach + Frequency | creative fatigue + reach saturation (Creative Signals) |
| Ad export: Link clicks | **CR-04 scored** (Ecommerce) + CTR-Link KPI |
| Ad export: Video plays 25–100% / ThruPlays | CR-03 (hold-through) / CR-02 evidence |
| Ad export: Quality / Engagement rate / Conversion rate ranking | **ranking decomposition** (Creative Signals) |

Not available on the CSV path: **CR-08** (no ad created time in exports), **DI-01 /
DI-04** (dataset health needs the MCP pulls), and **AR-03 / AR-04** (exports carry no
ad-set optimization-goal + campaign-id linkage) — these stay with auditor judgment or
require the MCP raw pulls.

## Known export quirks (handled by the parser — do not "fix" the files)

Header on row 1 (a defensive header scan is retained anyway); currency-suffixed money
headers (`Amount spent (CAD)`) matched by prefix; a summary/total row whose name cell
is empty or reads `Results from …` (dropped); quoted cells with embedded newlines;
thousands commas; `''` / `-` / `--` / em-dash placeholders → missing (never zero);
`%` suffixes; UTF-8 BOM; `Reporting starts`/`Reporting ends` accepted as ISO
(`2026-06-11`) or human (`11 June 2026`) dates. A wrong file for a slot fails loudly
naming the missing columns.
