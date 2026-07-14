# Performance report — campaign ROAS-bucketed, period-over-period (contract)

The monthly performance report as a tunable analytical deliverable: every campaign for the
reporting window, classified against a **ROAS goal** and annotated with **period-over-period**
deltas, shipped as the standard three-format bundle (md report, self-contained interactive HTML
explorer, formula-driven xlsx). Reuses every `google-ads-foundation` convention (micros, dates,
currency) — load that first.

All three formats are rendered by the shared toolkit (`_shared/render`) from one model
(`scripts/perf_core.py`), so they can never disagree. This file is the **authoritative** contract.

## The buckets (ROAS vs goal)

Each measured campaign (revenue tracked) is bucketed, holding the tunable params:

- **Scale** — `ROAS ≥ goal` AND `budget-lost impression share > flag` → a winner the budget is
  throttling. The data-backed budget-increase case (route to `google-ads-budget-pacing`).
- **Winner** — `ROAS ≥ goal`, not budget-constrained.
- **Fix** — `ROAS < goal` AND `spend ≥ min_spend` → a material laggard; fix before scaling.
- **Hold** — measured, sub-goal, below the spend floor.

Campaigns with **no revenue signal** (`conversions_value` not tracked) are kept with
`status = "no_value"` and **never ROAS-bucketed** — reported on CPA/volume, never dropped.
Defaults: ROAS goal **4.0**, budget-lost-IS flag **0.10**, anomaly delta flag **0.25**, min_spend **0**.

## Anomaly signals, pre-score & concentration

Built on the shared `_shared/analytics.py` primitives (the same kernel-mirror contract every
google-ads-management skill uses — mirrored verbatim in `perf_spec.JS_KERNEL` and the xlsx
formulas, gated by the Node↔Python parity harness):

- **Period-over-period anomaly signals** (`analytics.signals`) fire off the existing
  `spend_delta` / `conv_delta` / `value_delta` fields against the tunable **delta flag** (default
  25%): `spend_spike` (spend Δ > flag), `spend_drop` (spend Δ < −flag), `conv_drop` (conversions Δ
  < −flag), `value_drop` (revenue Δ < −flag). A campaign with no prior-period data (delta is
  `None`) is **never flagged** — missing data is "no signal," not a zero.
- **Anomaly pre-score** (`analytics.pre_score`) is a severity-weighted sum over a row's unique
  flags: `spend_spike` 2.0, `spend_drop` 1.5, `conv_drop` 2.5, `value_drop` 2.0 (a conversion or
  revenue drop outweighs a spend swing of the same magnitude). Computed for **every** row,
  including `no_value` campaigns — a lead-gen campaign's spend/conversions can still be
  anomalous even with no ROAS signal.
- **Spend + conversion concentration** (`analytics.concentration`, top-3, over `cost` and
  `conversions`) reports top-3 share / HHI (0–10,000) / effective-N — how reliant the account is
  on a handful of campaigns. Static per build (top_n isn't a tunable control).

`model["summary"]["anomalies"]` is the count of flagged rows; `model["concentration"]` holds the
`spend` and `conversions` concentration dicts; each row carries `flags` (list of fired signal ids)
and `pre_score` (float).

## The two GAQL pulls (`mcp__google-ads-mcp__search_search`)

> **Gotcha:** `LAST_90_DAYS` is not a valid GAQL literal. Use `THIS_MONTH`/`LAST_MONTH`, or an
> explicit `BETWEEN` ending **yesterday** (today is partial). Use equal-length windows for PoP.

**1 — Campaign performance, reporting window** (and **2 — the same query for the prior window**):
```
resource:   "campaign"
fields:     ["campaign.id","campaign.name","campaign.advertising_channel_type","campaign.status",
             "metrics.impressions","metrics.clicks","metrics.ctr","metrics.cost_micros",
             "metrics.conversions","metrics.conversions_value",
             "metrics.search_impression_share","metrics.search_budget_lost_impression_share",
             "metrics.search_rank_lost_impression_share"]
conditions: ["segments.date DURING THIS_MONTH", "campaign.status != 'REMOVED'"]
orderings:  ["metrics.cost_micros DESC"]
```
Run the prior-window query with `LAST_MONTH` (or the matching `BETWEEN`) and join it into each
campaign's `prior_*` fields by `campaign.id`.

**Which conversion metric.** Use `metrics.conversions` / `metrics.conversions_value` — the account's
**primary** goals (attribution-modeled, may be fractional). If value isn't tracked, omit
`conversions_value` for that campaign (it becomes `no_value`); never fabricate revenue. ROAS =
`conversions_value / spend`.

**Impression share** fields are 0–1 fractions and are **null for PMax/Display** — pass them through
as null (the report shows "—"), don't coerce to 0.

**Transcription firewall (mandatory).** Every pull's raw result must land in a file before
anything else happens: a large pull may exceed the MCP token cap and auto-save to a
`tool-results/*.txt` file — use that file as-is; for pulls that come back inline, copy the whole
tool result **verbatim** (the complete `{"result": [...]}` JSON, unedited) into a file. Then build
the findings JSON with `scripts/assemble_findings.py` — never assemble it by hand:

```
python3 scripts/assemble_findings.py \
  --campaigns-period <raw-period-file> --campaigns-prior <raw-prior-file> \
  --client-name "{Client Name}" --account-id {account} --currency {CUR} \
  --period "<period-start> to <period-end>" --prior-period "<prior-start> to <prior-end>" \
  -o findings.json
```

The assembler parses the raw files (micros conversion; per-`campaign.id` aggregation; the
prior-window join into each campaign's `prior_*` fields, prior-only campaigns kept as zero-current
rows; impression-share fields passed through as null when unpopulated, never coerced to 0), embeds
control totals as `meta.reconciliation`, and `perf_core` re-verifies those totals on every build —
a findings JSON whose numbers were typed or edited by hand hard-fails. Metric values therefore
never pass through the model: the model handles file paths and meta labels (client name, account
id, periods), and the pipeline handles the numbers. For campaigns whose conversion **value** is not
tracked (e.g. lead-gen), pass `--no-value-campaigns <id,id,...>` — a labeling judgment, not a
number — and the assembler omits their `conversions_value` keys so they land as `no_value` instead
of a fabricated ROAS of 0.

## The findings JSON

What the assembler produces (and the script's input contract):

```json
{
  "meta":   {"client_name","account_id","currency","period","prior_period","generated",
             "source"},                                    // "mcp" or "user_csv" (dual-input honesty)
  "params": {"roas_goal": 4.0, "budget_lost_is_flag": 0.10, "delta_flag": 0.25, "min_spend": 0},  // all optional
  "campaigns": [{
     "campaign_id","campaign","status","channel",
     "impressions","clicks","cost",                         // cost already /1e6
     "conversions","conversions_value",                     // omit conversions_value if not tracked
     "search_impression_share","search_budget_lost_is","search_rank_lost_is",   // 0–1 fractions or null
     "prior_cost","prior_conversions","prior_conversions_value","prior_impressions","prior_clicks"
  }]
}
```

## Dual input: MCP or a Google Ads UI CSV export

Per the `google-ads-foundation` dual-input contract, this skill accepts its data from **either**
the Google Ads MCP (above) **or** two user-supplied Google Ads UI **Campaigns** report CSV
exports — one for the reporting window, one for the prior window, same columns. Choose the path
at Step 0 (before any pull) per `google-ads-foundation`'s selection rules; never promise the MCP
for data it can't return.

**Requesting the export.** Ask the user to open the Campaigns table, add the columns `Impr.`,
`Clicks`, `Cost`, `Conversions`, `Conv. value`, `Search impr. share`, `Search lost IS (budget)`,
`Search lost IS (rank)`, set the date range to the reporting window, then Download → CSV — and
repeat for the prior window (same columns, prior-window date range).

```bash
python3 scripts/assemble_from_csv.py \
  --campaigns-period <period-export.csv> --campaigns-prior <prior-export.csv> \
  --client-name "{Client Name}" --account-id {account} --currency {CUR} \
  --period "<period-start> to <period-end>" --prior-period "<prior-start> to <prior-end>" \
  --no-value-campaigns "<Campaign Name>,<Campaign Name>"  \
  -o findings.json
```

- Rows are joined by **campaign name** (UI exports carry no `campaign.id`) — `scripts/assemble_from_csv.py`'s
  `COLUMN_MAP`.
- `--no-value-campaigns` takes **campaign names** (not ids) whose `Conv. value` isn't a tracked
  revenue signal — mirrors the MCP path's `--no-value-campaigns` flag.
- `meta.source` is stamped `"user_csv"` and surfaced in the report provenance — never presented as
  an API pull.
- Reconciliation is embedded identically to the MCP path (`perf_core.RECONCILE_ARRAYS`); a
  fixture test (`tests/test_perf.py::test_csv_matches_mcp_model`) asserts the two paths yield an
  **identical** `compute_model()` result for the same underlying data.
- **Known limitation:** the shared CSV parser (`_shared/csv_input.py`) reads an absent cell as
  `0.0`, never `None` — unlike the MCP path, which passes a PMax/Display campaign's search-IS
  fields through as null. A CSV-assembled report with PMax/Display campaigns will show `0%`
  impression share for those rows instead of "—"; say so if the account has PMax/Display
  campaigns and the CSV path is used.

## Build the bundle

```bash
python3 scripts/build_perf_report.py --input findings.json --outdir artifacts \
  --brand "{Client Name}" --formats md,html,xlsx
# xlsx only / structural check:
python3 scripts/build_perf_workbook.py --input findings.json --output report.xlsx --brand "{Client}"
python3 scripts/build_perf_workbook.py --check --input report.xlsx
```
Files land as `performance-report_{account}_{date}.{md,_explorer.html,xlsx}`. Tests:
`python3 tests/test_perf.py`.

**What each format is for** — all from one model, so no two can disagree.
- `*.md` — header (account, period, currency), headline KPIs (spend, revenue, ROAS, CPA,
  **anomalies**, bucket counts), the budget-increase + anomaly callouts, top campaigns by revenue,
  Scale candidates, ROAS laggards, the visibility/impression-share section, ROAS-goal sensitivity,
  **an Anomalies table** (flagged campaigns, sorted by pre-score) and a **Concentration table**
  (spend/conversion top-3 share, HHI, effective-N), **and a full per-campaign table** with status +
  bucket (no row loss).
- `*_explorer.html` — interactive: **ROAS-goal slider** + budget-lost-IS flag + **anomaly delta-flag
  slider** + spend floor, live KPIs and bucket/anomaly counts, a live Scale-candidate list and
  goal-sensitivity strip, a **live Anomalies card** (re-tunes with the delta-flag slider) and a
  **static Concentration card**, and the full sortable campaign table. Self-contained; the embedded
  JS matches the Python model exactly (Node-verified, incl. the spliced `_shared/analytics.py`
  kernel).
- `*.xlsx` — Controls (tunable goal/flags/delta-flag → live `COUNTIF`/`SUM`/`LARGE`/`SUMPRODUCT`
  totals, incl. anomaly count and spend/conversion concentration) · Campaigns (every row + Status;
  every row carries an `Anomaly score` formula, measured rows also carry the Bucket formula, both
  referencing the Controls cells; Bucket stays the last column) · Snapshot. LibreOffice-normalized
  so it opens in Excel; `--check` validates an existing file.

**Excel-open honesty.** The xlsx is normalized through LibreOffice (`soffice`); if it is missing the
build fails (exit 2). Real-Excel open is not verified here — the HTML explorer and LibreOffice are
the verified-open paths.

## Advisor loop (emit → report → recommend → offer-apply)

Per `google-ads-foundation`'s advisor output contract: after `build_perf_report.py` emits the
bundle, open with the `*_explorer.html` (the hero deliverable), then present prioritized
recommendations grounded in the model's numbers:

- **Critical** — an active anomaly with real budget/revenue impact already occurring (e.g. a
  `value_drop`-flagged campaign burning spend post-drop) — quantify the loss from `pre_score`/
  `value_delta`/spend at the current rate.
- **High** — a `Scale` bucket campaign (budget-constrained winner) — the budget-increase case;
  route to `google-ads-budget-pacing`. A concentration risk (very high top-3 share/HHI, low
  effective-N) worth diversifying spend across more campaigns.
- **Medium** — `Fix`-bucket laggards, and non-critical anomalies (e.g. an isolated `spend_spike`
  with no revenue impact) worth a watch-list entry.

Every number quoted comes from the emitted artifacts (the md report / the builder's printed
summary) — never re-narrated from raw MCP/CSV rows. This skill is read-only (no Editor CSVs of its
own); recommendations route to the action skills that do apply changes.
