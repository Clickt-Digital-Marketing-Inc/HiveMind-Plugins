# Budget & pacing — campaign-bucketed, account-paced (contract)

The budget review as a tunable analytical deliverable: every campaign bucketed for action, plus an
account-level pacing read (MTD vs goal × elapsed), a spend-concentration read, and a per-campaign
pace pre-score — shipped as the standard three-format bundle (md, self-contained interactive HTML,
formula-driven xlsx). Reuses every `google-ads-foundation` convention (micros, dates, currency) —
load that first.

All three formats are rendered by the shared toolkit (`_shared/render`) from one model
(`scripts/budget_core.py`); this file is the **authoritative** contract. The analytical bundle is
separate from the Google Ads Editor **apply** files (budget_changes / pause_list CSVs) — those are
produced by `google-ads-foundation/scripts/make_editor_csv.py` and applied manually.

## The buckets (priority order)

- **Kill** — 0 conversions (window) AND spend ≥ `kill_multiple × target_cpa` (the 3× rule) → pause.
- **Raise** — `budget-lost IS > flag` AND converting at/under target CPA → constrained winner; raise
  **≤ +20% per step**, re-check in 7–14 days.
- **Rank-limited** — `rank-lost IS > flag` → a quality/bid problem, **not** budget (route to
  `google-ads-quality-score` / `google-ads-bidding-strategy`).
- **Low budget** — daily budget < `min_budget_multiple × target_cpa` → too low for stable Smart Bidding.
- **OK** — none of the above.

Campaigns with **no daily-budget data** are kept with `status = "no_budget"` and never bucketed.
Account **pacing**: `expected MTD = monthly_goal × days_elapsed / days_in_month`; verdict is
over/under/on-track within `pacing_tolerance` (default ±15%). Defaults: target CPA **50**, flag
**0.10**, kill **3×**, min-budget **5×**.

## Spend concentration + per-campaign pace pre-score (HM-535)

Two additive layers over the same row set — every input row's other fields pass through
unchanged, no-row-loss holds regardless. Both are driven by `_shared/analytics.py`'s
`concentration` / `signals` / `pre_score` primitives (documented in `_shared/README.md`) — the
skill never reimplements that arithmetic, and `budget_spec.JS_KERNEL` splices
`analytics.JS_MIRROR` verbatim so the browser kernel and the xlsx formulas stay Node<->Python
parity-gated exactly like the buckets.

**Spend concentration** (`budget_core.summarize`, folded into `summary`): `analytics.concentration`
over every campaign's window `cost`, top-3 — `summary.conc_top_share` (fraction, 4dp),
`summary.conc_hhi` (0–10,000, 1dp), `summary.conc_effective_n` (inverse-Simpson, 2dp),
`summary.conc_top3_pct` (the same top_share ×100, 1dp — the KPI-card-friendly form).

**Per-campaign pace pre-score** (`budget_core.add_pace`, folded into each row):
- `campaign_pace_ratio = mtd_spend / (daily_budget × days_elapsed)`, half-up 2dp; `None` when the
  campaign has no daily budget or `days_elapsed == 0` (never 0 — a missing signal is not a zero).
- `pace_verdict` — `"over"` (`ratio > 1 + pacing_tolerance`) / `"under"` (`ratio < 1 -
  pacing_tolerance`) / `"on track"` / `"n/a"` (no ratio) — same tolerance band as account pacing.
- `pace_confidence` — `"high"` only when `days_elapsed >= 7 AND mtd_spend >= target_cpa`
  (otherwise `"low"`) — enough time and spend to trust the signal; computed for every row,
  independent of whether a ratio exists.
- `pace_flags` / `pace_score` — `analytics.signals` over four declarative rules (`over_pace`,
  `under_pace`, `constrained` — `budget_lost_is > budget_lost_is_flag` — and `zero_conv`), scored
  via `analytics.pre_score` against the module constant `PACE_FLAG_WEIGHTS = {"over_pace": 1.0,
  "under_pace": 1.0, "constrained": 1.5, "zero_conv": 2.0}`.

Account-level aggregates land in `summary`: `over_pace` / `under_pace` (row counts by verdict) and
`off_pace_high_conf` (verdict in over/under AND confidence high — the actionable subset).

## Advisor — reallocation shortlist

`budget_core.build_advisor(rows, params)` -> `model["advisor"] = {"fund": [...], "trim": [...]}`:

- **fund** — every `bucket == "Raise"` row (budget-constrained winner), `proposed_budget =
  daily_budget × 1.2` (the +20%/step cap), sorted by `budget_lost_is` descending. Identical to the
  md "Raise candidates" section — the fund shortlist IS that bucket, just packaged for the CLI/
  conversational advisor loop.
- **trim** — `bucket == "Kill"` (the 3× rule) **UNION** rows where `pace_verdict == "over" AND cpa
  > target_cpa` (`source: "over_pace"` — a laggard the pace pre-score catches that the Kill rule's
  0-conversions test does not), sorted by window `cost` descending. The md ships the Kill rows in
  their own "Kill candidates" section and the `over_pace`-sourced delta in "Advisor — additional
  trim candidates" (avoids duplicating the Kill list).

`build_budget_report.py` prints this shortlist to stdout right after the bundle (every number
sourced from the just-computed model) — the advisor loop's "recommend" step in
`google-ads-foundation/references/artifact-formats.md`.

## The GAQL pulls (`mcp__google-ads-mcp__search_search`)

**1 — Campaign performance + impression share (window, e.g. 30d):**
```
resource:   "campaign"
fields:     ["campaign.id","campaign.name","campaign.advertising_channel_type",
             "metrics.cost_micros","metrics.conversions",
             "metrics.search_budget_lost_impression_share","metrics.search_rank_lost_impression_share"]
conditions: ["segments.date DURING LAST_30_DAYS","campaign.status = 'ENABLED'"]
```
**2 — Daily budgets:** `campaign` with `campaign.id`, `campaign_budget.amount_micros`,
`campaign_budget.explicitly_shared` → `daily_budget` (÷1e6) per campaign (`campaign.id` is the
join key).
**3 — Month-to-date spend:** the same performance query with `segments.date DURING THIS_MONTH` →
`mtd_spend` (÷1e6) per campaign.

Distinguish **budget**-lost vs **rank**-lost IS (0–1 fractions, null for PMax/Display — pass through
as null). Ask the user for the **monthly budget goal**, **target CPA**, and the report date's
`days_elapsed` / `days_in_month` (not in the MCP).

**Transcription firewall (mandatory).** Every pull's raw result must land in a file before
anything else happens: a large pull exceeds the MCP token cap and auto-saves to a
`tool-results/*.txt` file — use that file as-is; for pulls that come back inline, copy the whole
tool result **verbatim** (the complete `{"result": [...]}` JSON, unedited) into a file. Then build
the findings JSON with `scripts/assemble_findings.py` — never assemble it by hand:

```
python3 scripts/assemble_findings.py \
  --performance <raw-perf-30d-file> --budgets <raw-budgets-file> --mtd <raw-this-month-file> \
  --client-name "{Client Name}" --account-id {account} --currency {CUR} \
  --period "last 30 days" \
  --monthly-goal {goal} --days-elapsed {N} --days-in-month {M} \
  -o findings.json
```

The assembler parses the raw files (micros conversion, per-campaign aggregation, the
daily-budget and MTD joins on `campaign.id`, null lost-IS pass-through), embeds control totals as
`meta.reconciliation`, and `budget_core` re-verifies those totals on every build — a findings JSON
whose numbers were typed or edited by hand hard-fails. Metric values therefore never pass through
the model: the model handles file paths and meta labels (client name, account id, period, the
user-supplied goal/days), and the pipeline handles the numbers.

## Dual input — the CSV path (`scripts/assemble_from_csv.py`)

Per `google-ads-foundation/references/artifact-formats.md`'s dual-input contract, this skill also
accepts two Google Ads UI **Campaigns** report exports in place of the three GAQL pulls above —
join key is the **Campaign name** (a UI export carries no numeric campaign id, unlike GAQL's
`campaign.id`):

```bash
python3 scripts/assemble_from_csv.py \
  --window campaigns_last30.csv --mtd campaigns_mtd.csv \
  --client-name "{Client Name}" --account-id {account} --currency {CUR} \
  --period "last 30 days" --monthly-goal {goal} --days-elapsed {N} --days-in-month {M} \
  -o findings.json
```

`WINDOW_COLUMN_MAP` (Campaign, Campaign type, Cost, Conversions, Budget, the two Search-lost-IS
columns) and `MTD_COLUMN_MAP` (Campaign, Cost) are declared in the script. `daily_budget` and the
two lost-IS fields are read as raw strings and parsed by hand (`_num_or_none` / `_pct_or_none`),
**not** via `csv_input`'s generic `"num"`/`"pct"` coercion — that coercion defaults an absent cell
to `0.0`, which would collapse the MCP path's "no daily budget data" (`status = "no_budget"`) and
"PMax has no Search lost IS" (`null`) semantics into a false zero. A blank/dash/"Shared"-only cell
stays a missing value (key omitted / `null`), exactly like the MCP assembler. `cost`/`conversions`/
`mtd_spend` use `csv_input.load_csv_rows`'s standard `"num"` type (an export always carries those).
Reconciliation (`reconcile.build` over the merged `campaigns` array, `meta.source = "user_csv"`) is
computed the same way as the MCP assembler — `budget_core.load_findings` cannot tell the paths
apart. `tests/sample-window.csv` + `tests/sample-mtd.csv` are the CSV twin of
`tests/sample-findings.json`; `tests/test_budget.py::test_csv_path_identical_to_mcp` asserts the
two paths compute a byte-identical model (campaign id aside — the CSV path uses the campaign name).

## The findings JSON

What the assembler produces (and the script's input contract):

```json
{
  "meta": {"client_name","account_id","currency","period","generated",
           "monthly_goal","days_elapsed","days_in_month"},
  "params": {"target_cpa": 50, "budget_lost_is_flag": 0.10, "kill_multiple": 3,
             "min_budget_multiple": 5, "pacing_tolerance": 0.15},   // all optional
  "campaigns": [{
     "campaign_id","campaign","channel",
     "daily_budget",                                // ÷1e6; omit if unavailable -> status no_budget
     "cost","mtd_spend","conversions",              // cost/mtd ÷1e6
     "search_budget_lost_is","search_rank_lost_is"  // 0–1 fractions or null
  }]
}
```
`monthly_goal`, `days_elapsed`, `days_in_month` may live in `meta` or `params` (meta wins).

## Build the bundle

```bash
python3 scripts/build_budget_report.py --input findings.json --outdir artifacts \
  --brand "{Client Name}" --formats md,html,xlsx
python3 scripts/build_budget_workbook.py --check --input report.xlsx
```
Files land as `budget-pacing_{account}_{date}.{md,_explorer.html,xlsx}`. Tests:
`python3 tests/test_budget.py`.

- `*.md` — pacing read, headline KPIs (incl. spend concentration + pace-pre-score aggregates) +
  bucket split, the raise/kill/rank/low-budget sections (with the +20% raise targets and the kill
  list), the per-campaign pace pre-score table, the advisor's additional over-pacing trim
  candidates, pacing sensitivity, and a **full per-campaign table** with status + bucket.
- `*_explorer.html` — interactive: **monthly-goal / target-CPA / flag / multiples /
  pacing-tolerance** controls, a live pacing + concentration card and the advisor's fund/trim
  shortlists, and the sortable campaign table. Self-contained; the embedded JS matches the Python
  model exactly (Node-verified; splices `analytics.JS_MIRROR`).
- `*.xlsx` — Controls (goal/CPA/days/flags/pacing-tolerance → live pacing + `COUNTIF` bucket
  counts + concentration `LARGE`/`SUMPRODUCT` formulas + pace-verdict counts) · Campaigns (every
  row + Status; every row carries the live Pace ratio/verdict/Confidence/Pace score formulas,
  measured rows carry the priority-ordered Bucket formula) · Snapshot. LibreOffice-normalized;
  `--check` validates it.

`build_budget_report.py` also prints the advisor's fund/trim reallocation shortlist to stdout
right after the bundle — see "Advisor — reallocation shortlist" above.

**Then deliver the apply-CSVs** for what you recommend: `budget_changes` (current vs proposed daily
budget, ≤ +20%, reason — the advisor's **fund** list) and `pause_list` (the advisor's **trim**
list) via `google-ads-foundation/scripts/make_editor_csv.py`. Budget changes are applied
**manually** (the MCP is read-only).
