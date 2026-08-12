---
name: google-ads-performance-reporting
description: Use when reporting Google Ads performance — daily visibility/engagement glance (impressions, impression share, CTR), or the monthly client report covering spend, conversions, revenue, ROAS, and top/bottom campaigns. Pulls live metrics via the Google Ads MCP, converts micros correctly, and outputs a clean client-ready report with data-backed recommendations.
---

# Google Ads — Performance Reporting (Visibility, Revenue & ROAS)

## Bundled path resolution

Before running bundled scripts, set `PLUGIN_ROOT` to the absolute path of this plugin directory: the nearest ancestor of this `SKILL.md` that contains either `.claude-plugin/plugin.json` or `.codex-plugin/plugin.json`. Resolve it from the loaded skill path; do not assume a host-specific environment variable or the current working directory. Then run commands that reference `${PLUGIN_ROOT}` unchanged.

Translate live account data into a clear, honest picture: are the ads visible, are they converting,
and what is the return. Reporting proves value and drives the budget conversation.

**Cadence:** quick visibility/engagement **glance daily**; full **monthly** report (revenue, ROAS,
recommendations) — month-end is where solid conclusions and budget recommendations are made.

**REQUIRED BACKGROUND:** load `google-ads-foundation` first.

## When to use
- "Build the monthly report", "how are we doing", "what's our ROAS".
- Daily: are impressions/impression share/CTR healthy.
- Preparing a budget-increase or strategy recommendation for the client.

## Pull the data — Step 0: MCP or CSV

Per `google-ads-foundation`'s dual-input contract, choose the input path **before** pulling
anything: the Google Ads MCP (below) when reachable, or two Google Ads UI **Campaigns** report
CSV exports (reporting window + prior window) when the user already has an export, the MCP is
unreachable, or they prefer a manual path. Both paths run the same transcription-firewall +
reconciliation discipline and produce an **identical** model — never promise MCP-only data
(Auction Insights, Customer Match, Enhanced-Conversions/Consent-Mode confirmation) from a CSV, or
vice versa.

1. **Account + campaign performance (period + prior period)** — campaign performance query with
   `impressions, clicks, ctr, average_cpc, cost_micros, conversions, conversions_value,
   cost_per_conversion, search_impression_share`. Run for the reporting window and the prior window
   for deltas (e.g. THIS_MONTH vs LAST_MONTH).
2. **Visibility daily glance** — same query with `LAST_7_DAYS`; watch impressions, impression
   share, CTR.
3. Ask the user for the **revenue/value source** if conversions_value isn't populated (e.g. offline
   revenue), and the **ROAS/MER goal**.

> **Numbers never pass through the model.** Save every pull's raw result to a file (auto-saved
> `tool-results/*.txt` for big pulls; verbatim copy of the whole `{"result": [...]}` JSON for
> inline ones) and build the findings JSON with
> [scripts/assemble_findings.py](scripts/assemble_findings.py) — never type metrics into a JSON by
> hand. The assembler embeds reconciliation control totals that the core re-verifies on every
> build; hand-assembled or edited findings hard-fail. See the reference doc's "Transcription
> firewall" section for the exact command.

**CSV path.** No MCP, or the user already has an export: ask for two Google Ads UI **Campaigns**
report exports (reporting window + prior window, same columns — name the exact columns from
[references/performance-report.md](references/performance-report.md#dual-input-mcp-or-a-google-ads-ui-csv-export))
and build the findings JSON with
[scripts/assemble_from_csv.py](scripts/assemble_from_csv.py) — same reconciliation discipline,
`meta.source` stamped `"user_csv"` and surfaced honestly in the report.

## Compute (get the math right)
- Spend = `cost_micros / 1e6` in the account `currency_code`.
- CTR = clicks / impressions; CVR = conversions / clicks.
- CPA = spend / conversions; **ROAS = conversions_value / spend**; MER = total revenue / total spend.
- Impression share is a 0–1 fraction → show as %. Lost-IS (budget) vs (rank) explains visibility
  gaps. Period-over-period deltas for every headline metric.

## Diagnose / interpret
Use [benchmarks](google-ads-foundation/references/benchmarks-2026.md) as context, but compare to the
account's own trend first:
- **Visibility:** low/declining impression share or impressions → reach problem (budget vs rank).
- **Engagement:** high impressions + low CTR → ad copy/relevance review (route to QS skill).
- **Revenue/ROAS:** rank campaigns by ROAS; call out top revenue drivers and ROAS laggards.
- **Anomalies:** campaigns whose spend/conversions/revenue swung beyond the delta flag (default
  25%) vs the prior period — sorted by a severity-weighted pre-score (a conversion/revenue drop
  outweighs a spend swing). A campaign with no prior-period data is never flagged.
- **Concentration:** how reliant the account is on its top 3 campaigns for spend/conversions (top-3
  share, HHI, effective-N) — a high-concentration account is one budget or account-suspension away
  from real risk.
- Tie findings to actions: strong ROAS + budget-lost IS → budget-increase case
  (route to `google-ads-budget-pacing`); weak ROAS → fix before scaling; an active anomaly →
  investigate now (see Recommend).

## Recommend (data-backed, client-facing — the advisor loop)
After emitting the bundle, open with the `*_explorer.html` (the hero deliverable), then present
prioritized recommendations grounded in the model's numbers (Critical → High → Medium — see
[references/performance-report.md](references/performance-report.md#advisor-loop-emit--report--recommend--offer-apply)
for the full taxonomy and severity rules):
- Lead with what the numbers support: scale the proven ROAS winners, fix or pause the laggards.
- Make the budget-increase case explicitly when winners are budget-constrained and hitting goal.
- Surface active anomalies (Critical/High per severity) and concentration risk before routine
  bucket commentary — they're time-sensitive.
- Keep recommendations honest — if results are thin, say so and propose the diagnostic step
  (which sibling skill to run), don't inflate. This skill is read-only; route action to the sibling
  skills (`google-ads-budget-pacing`, `google-ads-quality-score`) rather than generating its own
  apply-CSVs.

## Generate artifacts (in `artifacts/`)
The report is the standard three-format analytical bundle, all rendered by the shared
`_shared/render` toolkit from one model (`scripts/perf_core.py`), so the formats can never disagree.
Build it from a findings JSON (schema + the two GAQL pulls are authoritative in
[references/performance-report.md](references/performance-report.md)):

```bash
python3 "${PLUGIN_ROOT}/skills/google-ads-performance-reporting/scripts/build_perf_report.py" --input findings.json --outdir artifacts \
  --brand "{Client Name}" --formats md,html,xlsx
```
- `*.md` — client-ready report: header (account, period, currency), headline KPIs with the bucket +
  anomaly counts, budget-increase + anomaly callouts, top campaigns by revenue, Scale candidates,
  ROAS laggards, the impression-share visibility section, ROAS-goal sensitivity, an **Anomalies**
  table and a **Concentration** table, **and a full per-campaign table** with status + bucket (no
  row loss).
- `*_explorer.html` — interactive: **ROAS-goal slider** + budget-lost-IS flag + **anomaly delta-flag
  slider** + spend floor, live KPIs/bucket/anomaly counts, a live Scale-candidate list, a live
  Anomalies card, a static Concentration card, and the sortable campaign table. Self-contained;
  embedded JS matches the Python model exactly (incl. the spliced `_shared/analytics.py` kernel).
- `*.xlsx` — Controls (tunable goal/flags/delta-flag → live counts/totals/concentration) ·
  Campaigns (every row + Status; every row carries an Anomaly-score formula, measured rows also
  carry a Bucket formula, Bucket stays last) · Snapshot. LibreOffice-normalized; `--check` validates it.
- `*_charts/*.svg` — deterministic Vega-Lite charts (top-12 spend-by-campaign bar, revenue-vs-spend
  scatter for tracked-value campaigns) rendered at build time and referenced from the md; the
  explorer renders the same charts live. `--no-charts` skips them.

> **Charts are generated, never authored.** Every chart is produced by `build_perf_report.py`
> through the shared chart module from the spec's `SPEC["charts"]` declaration. Never hand-write
> or edit SVG, Vega-Lite JSON, chart HTML, or the vendored JS; never "fix" a chart in the output
> file. If a chart is wrong, the spec or the model is wrong — change it there and re-run the
> builder. Same run, same chart, byte for byte.

Reporting is **read-only**: no changes are made. Recommendations route to the action skills
(`google-ads-budget-pacing` for the budget-increase case, `google-ads-quality-score` for engagement).

## Resources
- [references/performance-report.md](references/performance-report.md) — **authoritative** contract:
  the two GAQL pulls, conversion-metric note, findings-JSON schema, the ROAS buckets, and the bundle.
- [scripts/perf_core.py](scripts/perf_core.py) — single-source model/kernel (stdlib); its math is
  mirrored in the spec's `js_kernel` and the xlsx Bucket formula.
- [scripts/perf_spec.py](scripts/perf_spec.py) / [scripts/perf_xlsx_spec.py](scripts/perf_xlsx_spec.py)
  — the md/html render spec and the xlsx layout (pure data).
- [scripts/build_perf_report.py](scripts/build_perf_report.py) — bundle CLI;
  [scripts/build_perf_workbook.py](scripts/build_perf_workbook.py) — xlsx `--check` wrapper.
- [scripts/assemble_from_csv.py](scripts/assemble_from_csv.py) — CSV-input path (dual-input
  contract); joins two Google Ads UI Campaigns-report exports by campaign name.
- The shared toolkit: `../../_shared/render` (see `../../_shared/README.md`); the shared analytics
  primitives: `../../_shared/analytics.py` (concentration / signals / pre_score).
- [tests/test_perf.py](tests/test_perf.py) + [tests/sample-findings.json](tests/sample-findings.json)
  + [tests/analytics_vectors_perf.json](tests/analytics_vectors_perf.json) (per-skill Node↔Python
  parity fixtures for the anomaly rules/weights and concentration shapes this skill uses).

## Common mistakes / red flags
- Always divide `cost_micros` by 1e6 and label the currency — never report raw micros or assume USD.
- ROAS uses `conversions_value`; if value tracking is absent, say ROAS is unavailable and report
  CPA/volume instead of fabricating a return.
- Impression-share fields are null for PMax/Display on the **MCP** path — don't report them as 0.
  On the **CSV** path this distinction is lost (the shared CSV parser reads an absent cell as
  `0.0`) — say so rather than reporting a false 0% for PMax/Display rows.
- A campaign with no prior-period data must never be anomaly-flagged (missing delta = no signal,
  not a zero swing) — the assemblers already guarantee this; don't hand-patch a missing prior.
- State the exact date range and account; period-over-period only between equal-length windows.
- Reporting is read-only by nature here — no changes are made; recommendations route to action skills.
