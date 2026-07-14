# Quality Score forensics — triad-bucketed (contract)

The QS forensic as a tunable analytical deliverable: every keyword bucketed by its **primary
failing component** (the QS triad localizes the root cause), with a low-CTR **pause** flag, shipped
as the standard three-format bundle (md, self-contained interactive HTML, formula-driven xlsx).
Reuses every `google-ads-foundation` convention — load that first.

All three formats are rendered by the shared toolkit (`_shared/render`) from one model
(`scripts/qs_core.py`); this file is the **authoritative** contract. The analytical bundle is
separate from the Editor **apply** files (pause_list / bid_adjustments CSVs, RSA rewrites) produced
via `google-ads-foundation/scripts/make_editor_csv.py`.

## The buckets

For each scored keyword with **QS < threshold** (default 5), bucket by which triad components are
**below the component target** (default "Average", i.e. only Below-average is flagged):
- **Landing page** — `post_click_quality_score` is the worst below-target component → page (MANUAL).
- **Ad relevance** — `creative_quality_score` is the worst → headlines must echo the keyword phrases.
- **Expected CTR** — `search_predicted_ctr` is the worst → match-type/intent, pause low-CTR, RSAs.
- **Critical** — all three components below target → rebuild the ad group.
- **Other** — QS is low but no component is below target (watch).

(When two components tie, the worst rank wins; ties break in order LP → Ad rel → Exp CTR.)
A keyword is independently flagged a **pause** candidate when impressions ≥ `pause_min_impr` AND
CTR < `pause_max_ctr` AND 0 conversions.

## Dominant QS-factor concentration

Beyond the per-keyword bucket (a row's single primary failing component), `qs_core.dominant_factor`
answers "which component drags the **account** most, and where does it concentrate" using the
shared `_shared/analytics.py` primitives (kernel-mirrored in `js_kernel`, parity-gated):

1. **`component_drag`** — for every in-scope, scored keyword, sum its cost into EACH component
   that is below target (a Critical keyword's cost counts toward all three — this measures each
   component's account-wide drag, not the row's single bucket).
2. **`analytics.signals`** flags the component(s) carrying the highest drag cost (id `worst_factor`;
   ties are flagged together, honestly).
3. **`analytics.concentration`** runs twice: over the three components' drag cost (`top_n=1` — how
   much the single worst component accounts for: `top_share`/`hhi`/`effective_n`), then over the
   dominant component's cost by **ad group** (`top_n=3` — where within the account it concentrates).

Exposed on the model as `dominant_factor` (`drag`, `dominant_component`, `concentration`,
`location`, `location_rows`) and as summary KPIs (`dominant_component`, `dominant_share_pct`,
`dominant_location_share_pct`). The bundle leads with this finding (md narrative + a dedicated
snapshot section + the HTML explorer's first "extra" card) before the per-bucket detail.

> **`quality_score` of 0/null = UNSCORED** (too little data / not eligible), NOT a literal 0. Unscored
> keywords are kept with `status="unscored"` and **never bucketed or averaged in**.
> **Landing page experience is MANUAL:** a below-average LP component is a pointer; Core Web Vitals /
> page speed are **not** in this MCP — confirm in Search Console → Page Experience / PageSpeed.

## Dual input (MCP or CSV)

This skill accepts its data from **either** the Google Ads MCP **or** a user-supplied CSV (a
Google Ads UI "Keywords" export with the QS diagnostic columns added). Both paths run the same
transcription-firewall + reconciliation discipline and yield an identical model (per
`google-ads-foundation/references/artifact-formats.md`). Pick the CSV path when the MCP is
unreachable (e.g. `login-customer-id` not set) or the user already has an export.

**Ask for:** Google Ads UI → Keywords page → add the **Quality Score**, **Landing page exp.**,
**Ad relevance**, **Expected CTR** columns → set the date range → **Download → .csv**.

**Assemble:**
```bash
python3 scripts/assemble_findings_csv.py \
  --csv export.csv \
  --client-name "{Client Name}" --account-id {account} --currency {CUR} \
  --period "last 30 days" \
  -o findings.json
```
Uses `_shared/csv_input.py` (`COLUMN_MAP` in `assemble_findings_csv.py`) — the file is parsed
verbatim, never through the model. Two CSV-specific normalizations `qs_core` doesn't need on the
MCP path: the UI's "Broad match"/"Phrase match"/"Exact match" labels are normalized to the GAQL
enum token, and — because the UI export has no internal ad-group id — the ad group **name**
stands in for `ad_group_id` (the same field the MCP path's numeric id fills), so keywords still
dedupe/group per ad group correctly. `meta.source` is stamped `"user_csv"` and surfaced in every
artifact's provenance (md params table, xlsx subtitle, the HTML explorer's dominant-factor card).
The resulting `findings.json` feeds `build_qs_report.py` / `build_qs_workbook.py` exactly like the
MCP path — the builders don't know or care which path produced it.

## The GAQL pull (`mcp__google-ads-mcp__search_search`)

**Keywords + QS triad (30d):**
```
resource:   "keyword_view"
fields:     ["campaign.name","ad_group.id","ad_group.name",
             "ad_group_criterion.keyword.text","ad_group_criterion.keyword.match_type",
             "ad_group_criterion.quality_info.quality_score",
             "ad_group_criterion.quality_info.post_click_quality_score",     // landing page exp
             "ad_group_criterion.quality_info.creative_quality_score",       // ad relevance
             "ad_group_criterion.quality_info.search_predicted_ctr",         // expected CTR
             "metrics.impressions","metrics.clicks","metrics.ctr","metrics.cost_micros",
             "metrics.conversions"]
conditions: ["segments.date DURING LAST_30_DAYS","campaign.status = 'ENABLED'",
             "ad_group.status = 'ENABLED'","ad_group_criterion.status = 'ENABLED'"]
orderings:  ["ad_group_criterion.quality_info.quality_score ASC"]
```
The three component fields come back as `BELOW_AVERAGE` / `AVERAGE` / `ABOVE_AVERAGE` (or `UNKNOWN`).
Dedupe by `(ad_group_id, keyword.text, match_type)`. `cost_micros / 1e6`.

**Transcription firewall (mandatory).** The pull's raw result must land in a file before anything
else happens: a large pull exceeds the MCP token cap and auto-saves to a `tool-results/*.txt`
file — use that file as-is; if the result comes back inline, copy the whole tool result
**verbatim** (the complete `{"result": [...]}` JSON, unedited) into a file. Then build the
findings JSON with `scripts/assemble_findings.py` — never assemble it by hand:

```
python3 scripts/assemble_findings.py \
  --keywords <raw-keyword_view-file> \
  --client-name "{Client Name}" --account-id {account} --currency {CUR} \
  --period "last 30 days" \
  -o findings.json
```

The assembler parses the raw file (micros conversion, per-key aggregation; QS/triad point-in-time
from the first row per key; 0/null/absent QS kept unscored), embeds control totals as
`meta.reconciliation`, and `qs_core` re-verifies those totals on every build — a findings JSON
whose numbers were typed or edited by hand hard-fails. Metric values therefore never pass through
the model: the model handles file paths and meta labels (client name, account id, period), and
the pipeline handles the numbers.

## The findings JSON

What the assembler produces (and the script's input contract):

```json
{
  "meta": {"client_name","account_id","currency","period","generated"},
  "params": {"qs_low_threshold": 5, "component_target": 2,
             "pause_min_impr": 100, "pause_max_ctr": 0.01},   // all optional; component_target 1/2/3
  "keywords": [{
     "ad_group_id","ad_group","campaign","keyword","match_type",
     "quality_score",                                          // 1–10, or null/0 = unscored
     "landing_page_exp","ad_relevance","expected_ctr",         // BELOW_AVERAGE / AVERAGE / ABOVE_AVERAGE
     "impressions","clicks","cost","conversions"               // cost /1e6
  }]
}
```

## Build the bundle

```bash
python3 scripts/build_qs_report.py --input findings.json --outdir artifacts \
  --brand "{Client Name}" --formats md,html,xlsx
python3 scripts/build_qs_workbook.py --check --input report.xlsx
```
Files land as `quality-score_{account}_{date}.{md,_explorer.html,xlsx}`. Tests:
`python3 tests/test_qs.py`.

- `*.md` — headline KPIs (avg QS, in-scope, the component split, pause candidates), a section per
  failing component with its fix, the pause-candidate list, QS-threshold sensitivity, the manual-LP
  reminder, and a **full per-keyword table** with the triad ratings, bucket, and pause flag.
- `*_explorer.html` — interactive: **QS-low slider**, a **component-target dropdown**
  (Below/Average/Above), and pause thresholds; live bucket counts, a live pause list and
  QS-threshold strip, and the sortable keyword table. Self-contained; embedded JS matches the Python
  model exactly (Node-verified).
- `*.xlsx` — Controls (QS-low, component target, pause thresholds → live `COUNTIF` bucket counts) ·
  Keywords (every keyword + Status; scored rows carry the primary-bottleneck Bucket formula and the
  Pause flag) · Snapshot. LibreOffice-normalized; `--check` validates it.

**Then deliver the forensic apply-files** for what you recommend: `pause_list` (step-5 low-CTR
keywords), `bid_adjustments` (mobile), and the RSA-rewrite worklist — via
`google-ads-foundation/scripts/make_editor_csv.py` and `scripts/build_rsa_rewrites.py` (below).
Edits are applied **manually** (read-only MCP). QS is a trailing indicator — re-check ~30 days
after a fix.

### The RSA-rewrite advisor (`*_rsa_rewrites.md`)

Deepens step 4 (the ad-relevance keyword↔headline matrix): every in-scope keyword whose **Ad
relevance** component rates below target (the same test `dominant_factor`'s "Ad relevance" drag
uses — includes Critical keywords, whose Ad relevance is below target too), grouped by ad group
and prioritized by spend:

```bash
python3 scripts/build_rsa_rewrites.py --input findings.json --outdir artifacts --brand "{Client Name}"
```
Extends (never replaces) the bundle — run it **after** `build_qs_report.py`, from the same
`findings.json`. The MCP is read-only and does not return current RSA headline text, so this is a
**prescriptive worklist** (what each ad group's headlines must contain, citing the model's cost/
impressions per keyword), not a live keyword↔headline diff — cross-reference it against the ad
group's current RSAs in the Google Ads UI or Editor before publishing.

## The advisor loop

After the bundle (and the RSA rewrites) build, follow `google-ads-foundation/references/
artifact-formats.md`'s advisor output contract: **emit → report → recommend → offer-apply**.
1. Open with the `*_explorer.html` hero deliverable.
2. **Lead with the dominant-QS-factor finding** ("which component drags the account most, and
   where it concentrates" — model numbers, not narration) — it's the first card in the explorer's
   "extra" panel and the first section in the md/xlsx.
3. Present the deepened RSA-rewrite recommendations (`*_rsa_rewrites.md`), citing the model's
   per-ad-group cost/keyword counts, grouped Critical → High → Medium per the severity taxonomy.
4. Offer the apply artifacts: `pause_list` / `bid_adjustments` CSVs (`make_editor_csv.py`) for the
   recommendations the user accepts — done-with-you, not fire-and-forget.
