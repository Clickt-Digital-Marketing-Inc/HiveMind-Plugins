---
name: google-ads-budget-pacing
description: Use when checking Google Ads budget pacing (daily spend distribution, month-to-date spend vs goal, over/under-pacing), reviewing whether budgets are too low to compete, applying the 20% scaling rule and 3x kill rule, assessing account-level MER, or reading spend concentration and per-campaign pace confidence. Pulls live spend data via the Google Ads MCP or a user-supplied CSV export and outputs prioritized budget moves — a reallocation shortlist — with ready-to-apply change tables.
---

# Google Ads — Budget & Pacing

Keep spend pacing to goal, find budget-constrained winners, and cut budget bleed — without
destabilizing learning.

**Cadence:** spend/pacing glance **daily**; full budget review (pacing vs goal, scale/kill, MER)
**monthly** (look at 30/60/90-day trends to justify budget changes).

**REQUIRED BACKGROUND:** load `google-ads-foundation` first.

## When to use
- "Are we pacing on budget", "are we overspending/underspending", "should I raise budgets".
- A budget-constrained campaign hitting its goal (raise candidate).
- An ad group/keyword burning spend with no conversions (kill candidate).
- Monthly client budget review / budget-increase justification.
- Spend is concentrated in a few campaigns, or a campaign's own pace looks off — the
  concentration + pace-pre-score layer below.

## Step 0 — choose the input path (MCP or CSV), before any pull

Per `google-ads-foundation/references/artifact-formats.md`'s dual-input contract: this skill
accepts data from **either** the Google Ads MCP **or** a user-supplied CSV export — both paths
run the same transcription-firewall + reconciliation discipline and yield an **identical
model**. Decide before pulling anything:

1. User already gave a CSV (file path or attached export) → CSV path.
2. MCP reachable and queryable → MCP path (the default for live pulls) — see "Pull the data" below.
3. MCP missing/erroring or the user prefers an export → ask for the CSV path, below.
4. Ambiguous → ask which the user wants; don't guess.

## Pull the data
1. **Campaign performance + impression share (30d)** — `campaign` performance query incl.
   `metrics.cost_micros`, `metrics.conversions`, `metrics.cost_per_conversion`,
   `metrics.search_budget_lost_impression_share`, `metrics.search_rank_lost_impression_share`.
2. **Daily budgets** — `campaign` structure query incl. `campaign_budget.amount_micros`,
   `campaign_budget.explicitly_shared`.
3. **Month-to-date spend** — same performance query with `segments.date DURING THIS_MONTH`.
4. **Keyword/ad-group spend (30d)** — `keyword_view` for the 3× kill assessment.
5. Ask the user for the **monthly budget goal** and **revenue** (for MER) — not in the MCP.

Convert all `cost_micros` ÷ 1e6 to the account currency.

> **Numbers never pass through the model.** Save every pull's raw result to a file (auto-saved
> `tool-results/*.txt` for big pulls; verbatim copy of the whole `{"result": [...]}` JSON for
> inline ones) and build the findings JSON with
> [scripts/assemble_findings.py](scripts/assemble_findings.py) — never type metrics into a JSON by
> hand. The assembler embeds reconciliation control totals that the core re-verifies on every
> build; hand-assembled or edited findings hard-fail. See the reference doc's "Transcription
> firewall" section for the exact command.

## The CSV path (no MCP, or the user has an export)

Two Google Ads UI **Campaigns** report exports (Reports → Predefined reports → Campaigns, or
Campaigns table → columns → Download → CSV):

1. **Window export** — date range = the reporting window (e.g. last 30 days). Columns: Campaign,
   Campaign type, Cost, Conversions, Budget, Search lost IS (budget), Search lost IS (rank).
2. **MTD export** — the same report, date range = **this month**. Columns: Campaign, Cost.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/google-ads-budget-pacing/scripts/assemble_from_csv.py" \
  --window campaigns_last30.csv --mtd campaigns_mtd.csv \
  --client-name "{Client Name}" --account-id {account} --currency {CUR} \
  --period "last 30 days" --monthly-goal {goal} --days-elapsed {N} --days-in-month {M} \
  -o findings.json
```

Produces the **identical** findings JSON shape as `assemble_findings.py` (joined on Campaign
name, since a UI export carries no numeric campaign id) and stamps `meta.source = "user_csv"` —
surfaced in the report provenance, never presented as an API pull. The skill's `column_map` is
`WINDOW_COLUMN_MAP` / `MTD_COLUMN_MAP` in [scripts/assemble_from_csv.py](scripts/assemble_from_csv.py);
if a real export uses a header spelling that doesn't match, add the alias there and a fixture
test, then log the lesson.

## Diagnose
Thresholds from [benchmarks](../google-ads-foundation/references/benchmarks-2026.md) "Budget & pacing":

- **Pacing:** expected MTD = monthly_goal × (days_elapsed / days_in_month). Flag if actual is
  outside ±15% (over-pacing risks early exhaustion; under-pacing leaves volume on the table).
- **Budget-constrained winners:** campaigns with `search_budget_lost_impression_share` high
  (e.g. > 0.10) AND cost/conv at/under target → raise candidates.
- **Daily budget too low:** daily budget < ~5× target CPA → unstable Smart Bidding delivery.
- **Kill candidates (3× rule):** keyword/ad group with cost ≥ 3× target CPA and 0 conversions (30d).
- **MER:** total revenue ÷ total spend (account level). Flag below the user's break-even MER.
- **Spend concentration:** top-3 campaign share / HHI / effective-N over window spend
  (`_shared/analytics.concentration`) — very high concentration means the account's fate rides on
  a handful of campaigns; very low concentration (many small campaigns) often means fragmented,
  under-scaled budgets.
- **Per-campaign pace pre-score:** `campaign_pace_ratio = MTD ÷ (daily budget × days elapsed)` —
  is this campaign's own MTD spend on pace with its own daily budget? Verdict over/under/on-track
  at the same ±`pacing_tolerance` band as account pacing; **confidence** is "high" only with
  ≥7 days elapsed AND MTD ≥ target CPA (otherwise there isn't enough spend/time to trust the
  signal) — read the `pace_score` (declarative flags: over_pace/under_pace, constrained,
  zero_conv, weighted via `PACE_FLAG_WEIGHTS`) alongside confidence, not instead of it.

## Recommend (Critical → High → Medium)
- **Critical:** stop budget bleed — pause 3× kill candidates; rein in over-pacing campaigns that
  are below target efficiency (the advisor's **trim** shortlist: Kill ∪ over-pacing with CPA
  above target).
- **High:** raise budgets on budget-lost-IS winners — **≤ +20% per change** (larger jumps reset
  learning); re-check in 7–14 days before the next step (the advisor's **fund** shortlist).
- **Medium:** consolidate fragmented shared budgets where campaigns share an objective; reallocate
  from rank-lost-IS losers (those need QS/bid fixes, not more budget — route to
  `google-ads-quality-score` / `google-ads-bidding-strategy`); investigate low-confidence pace
  signals before acting on them.

Distinguish **budget**-lost vs **rank**-lost IS: budget-lost → add budget; rank-lost → raise QS/bids,
not budget.

## Advisor loop

After emitting the bundle (below), run the standard loop from
`google-ads-foundation/references/artifact-formats.md`: **emit → hero HTML → recommend →
offer-apply**. `build_budget_report.py` prints the prioritized reallocation shortlist right after
the bundle — present the `*_explorer.html` first, then walk the user through the **fund** (Raise,
≤+20%/step) and **trim** (Kill + over-pacing-above-target) shortlists, every number citing the
model (spend concentration, pace verdict/confidence, the bucket), then offer to generate the
`budget_changes` / `pause_list` Editor CSVs for the items the user accepts.

## Generate artifacts (in `artifacts/`)
**Analytical deliverable** — the standard three-format bundle, all rendered by the shared
`_shared/render` toolkit from one model (`scripts/budget_core.py`). Build from a findings JSON
(schema + the GAQL pulls are authoritative in
[references/budget-pacing-report.md](references/budget-pacing-report.md)):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/google-ads-budget-pacing/scripts/build_budget_report.py" --input findings.json --outdir artifacts \
  --brand "{Client Name}" --formats md,html,xlsx
```
- `*.md` — pacing read (MTD vs expected), headline KPIs + bucket split + spend concentration +
  pace pre-score aggregates, the raise / kill / rank-limited / low-budget sections, per-campaign
  pace pre-score table, the advisor's additional over-pacing trim candidates, pacing sensitivity,
  and a **full per-campaign table** with status + bucket (no row loss).
- `*_explorer.html` — interactive: **monthly-goal / target-CPA / flag / multiples / pacing-tolerance**
  controls, a live pacing + concentration card and the fund/trim advisor shortlists, sortable
  campaign table. Self-contained; embedded JS matches the Python model exactly (splices
  `analytics.JS_MIRROR`).
- `*.xlsx` — Controls (goal/CPA/days/flags/pacing-tolerance → live pacing + bucket counts +
  concentration + pace-verdict counts) · Campaigns (every row + Status; measured rows carry the
  priority-ordered Bucket formula, every row carries the live Pace ratio/verdict/Confidence/Pace
  score formulas) · Snapshot. LibreOffice-normalized.
- `*_charts/*.svg` — deterministic Vega-Lite charts (campaigns-by-bucket bar, top-campaigns-by-spend
  bar colored by bucket) rendered at build time and referenced from the md; the explorer renders the
  same charts live from the controls. `--no-charts` skips them.

> **Charts are generated, never authored.** Every chart is produced by `build_budget_report.py`
> through the shared chart module from the spec's `SPEC["charts"]` declaration. Never hand-write
> or edit SVG, Vega-Lite JSON, chart HTML, or the vendored JS; never "fix" a chart in the output
> file. If a chart is wrong, the spec or the model is wrong — change it there and re-run the
> builder. Same run, same chart, byte for byte.

**Apply files** (Google Ads Editor; applied manually — MCP is read-only) via
`${CLAUDE_PLUGIN_ROOT}/skills/google-ads-foundation/scripts/make_editor_csv.py`:
- `budget_changes` CSV — current vs proposed daily budget, change % (**≤ +20%**), reason.
- `pause_list` CSV — 3× kill candidates.

## Resources
- [references/budget-pacing-report.md](references/budget-pacing-report.md) — **authoritative** contract.
- [scripts/budget_core.py](scripts/budget_core.py) — single-source model/kernel (buckets +
  pacing + spend concentration + per-campaign pace pre-score + the advisor shortlist); mirrored
  in the spec's `js_kernel` and the xlsx Bucket / Pace ratio / Pace verdict / Confidence / Pace
  score formulas.
- [scripts/budget_spec.py](scripts/budget_spec.py) / [scripts/budget_xlsx_spec.py](scripts/budget_xlsx_spec.py).
- [scripts/build_budget_report.py](scripts/build_budget_report.py) (prints the advisor shortlist
  after emit) / [scripts/build_budget_workbook.py](scripts/build_budget_workbook.py) (`--check`).
- [scripts/assemble_findings.py](scripts/assemble_findings.py) (MCP path) /
  [scripts/assemble_from_csv.py](scripts/assemble_from_csv.py) (CSV path).
- [tests/test_budget.py](tests/test_budget.py) + [tests/sample-findings.json](tests/sample-findings.json)
  + [tests/sample-window.csv](tests/sample-window.csv) / [tests/sample-mtd.csv](tests/sample-mtd.csv)
  (CSV-path fixtures, asserted identical to the MCP-path model).

## Common mistakes / red flags
- Never recommend > 20% budget increase in one step.
- Don't add budget to a rank-lost-IS campaign — that's a quality/bid problem.
- Daily Google budgets can spend up to ~2× on a given day; judge pacing over the month, not one day.
- Budget changes are applied **manually** (read-only MCP) — deliver the change table.
- Always anchor scale/kill decisions to ≥ 30 days of data and the user's actual goal/MER.
- Don't act on a low-confidence pace signal (< 7 days elapsed, or MTD spend below target CPA) as
  if it were high-confidence — flag it and wait for more data instead.
- CSV-path findings are labelled `meta.source = "user_csv"` — never present them as a live API
  pull; the honesty rule applies to concentration/pace numbers exactly as it does to buckets.
