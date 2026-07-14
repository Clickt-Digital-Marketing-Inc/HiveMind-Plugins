---
name: google-ads-competitive-analysis
description: Use when doing a weekly Google Ads competitive check — detecting impression-share erosion, rising CPCs / auction pressure, and lost impression share to rank vs budget. Pulls live week-over-week impression-share and CPC metrics via the Google Ads MCP, computes a rank-vs-budget IS-loss attribution model, and folds in an optional user-supplied Auction Insights CSV for the competitor payload the API can't provide. Emits the standard md + interactive HTML + tunable xlsx bundle and a shoulder-to-shoulder recommendation walkthrough.
---

# Google Ads — Competitive Analysis (advisor)

The auction changes weekly as competitors shift bids and budgets. Catch erosion early — sudden CPC
rises or impression-share drops — attribute it to rank pressure or a budget cap, and react before
performance suffers.

**Cadence:** **weekly** (even a quick pass). The auction is the fastest-moving part of an account.

**REQUIRED BACKGROUND:** load `google-ads-foundation` first (the dual MCP-or-CSV input contract and
the advisor output contract this skill follows live in
`google-ads-foundation/references/artifact-formats.md`).

## Important scope note (read first)

The Google Ads MCP exposes **your own** impression-share and CPC metrics — that part of this
skill is a live MCP pull, always. It does **not** expose the **Auction Insights** report, so
competitor domains, their impression share, overlap rate, and ad copy are **not available via the
API** — that part is a user-supplied CSV export, entirely optional. Never invent competitor names
or numbers, and never present CSV-sourced competitor rows as if the API returned them.

## When to use

- "How are we doing vs competitors", weekly competitive check.
- CPCs climbing or impression share slipping.

## Step 0 — select the input path

Own-side metrics: MCP is the default (`mcp__google-ads-mcp__search_search`, cookbook below); fall
back to a Google Ads UI performance-report CSV export only if the MCP is unreachable (same dual
MCP-or-CSV contract every skill in this project follows — see `google-ads-foundation`).

Competitor payload: **always** the Auction Insights CSV path — there is no MCP path for it. Ask
for the export (or proceed own-side-only if the user has none); either way, tell the user plainly
what you can and cannot see before pulling anything.

## Pull the data (your side of the auction)

1. **Campaign impression-share + CPC, this week vs prior week** — `campaign` performance query
   with `metrics.search_impression_share`, `metrics.search_rank_lost_impression_share`,
   `metrics.search_budget_lost_impression_share`, `metrics.cost_micros`, `metrics.clicks`,
   `metrics.impressions`, `metrics.conversions`. Run for two back-to-back 7-day windows (see
   `references/competitive-pressure-filter.md` for the exact GAQL and date-window gotchas).
2. Optionally the **Auction Insights** export (Campaigns → Insights → Auction insights →
   Download → .csv) for the same this-week window, if the user wants the competitor read.

## Assemble + build (the transcription firewall)

```bash
python3 scripts/assemble_findings.py --this <raw-this> --prior <raw-prior> \
  [--auction-insights <csv>] --client-name "{Client}" --account-id {acct} --currency {CUR} \
  --window-this "..." --window-prior "..." -o findings.json
python3 scripts/build_competitive_report.py --input findings.json --outdir artifacts \
  --brand "{Client}" --formats md,html,xlsx --emit-widget artifacts/widget.json
```

Never hand-write `findings.json` — the assembler is the only thing that turns saved raw pulls (and
the optional CSV) into it, and embeds the reconciliation totals `competitive_core` re-verifies on
every build. Full schema, the GAQL pulls, the CSV column map, and the xlsx layout are documented
authoritatively in `references/competitive-pressure-filter.md`.

## Diagnose (what the model computes)

- **Rank pressure vs Budget capped** — a flagged campaign (WoW impression-share drop ≥ threshold
  OR CPC jump ≥ threshold, spending at least the minimum this week) is attributed to whichever
  loss driver worsened more: `search_rank_lost_impression_share` (competitor bids/quality) or
  `search_budget_lost_impression_share` (budget).
- **Competitor concentration** (only when an Auction Insights CSV was supplied) — top-N share /
  HHI / effective-N over the competitor rows' impression share: is the pressure concentrated in
  1–2 domains, or spread across many?
- Campaigns with no prior-week data, unavailable impression-share data (`--`), or zero activity
  both weeks are held out and reported separately — never silently dropped, never classified.

## Recommend (Critical → High → Medium), grounded in the model

Follow the advisor output contract: open with the HTML explorer, then walk through
Critical/High/Medium recommendations citing the model's numbers (never re-narrated raw data), then
offer next steps.

- **Critical:** a **Rank pressure** campaign with meaningful spend — protect position now. Route
  to `google-ads-quality-score` (Quality Score checks) and/or `google-ads-bidding-strategy` (bid
  review).
- **High:** a **Budget capped** campaign that is otherwise profitable — make the budget case.
  Route to `google-ads-budget-pacing`.
- **Medium:** near-miss campaigns (close to a threshold but not yet flagged) — watch next week;
  and, when a competitor CSV was supplied, the concentration read — a highly concentrated
  competitor set (few dominant domains) is a different conversation than a fragmented one.
- **Manual, always:** if no Auction Insights export was supplied, name it as the missing piece —
  competitor names, their share, and their live ad copy (Ads Transparency Center) are UI/manual
  pulls the API cannot replace.

## Generate artifacts (in `artifacts/`)

- `competitive-pressure_{account}_{date}.md` — the narrative report (provenance, headline,
  sensitivity, near-misses, competitor concentration, excluded campaigns, full per-campaign
  table).
- `competitive-pressure_{account}_{date}_explorer.html` — the self-contained interactive primary
  (sliders + sensitivity + competitor panel).
- `competitive-pressure_{account}_{date}.xlsx` — the tunable Controls + Live-pressure workbook.

No Editor apply-CSV is generated directly by this skill (it is diagnostic, not action-taking) —
recommendations route to the action skills above, which own their own apply-CSVs.

## Common mistakes / red flags

- **Never fabricate competitor data** — the API can't see it. Diagnose your own metrics; hand off
  competitor specifics to the Auction Insights CSV or a manual UI pull, and say so explicitly.
- **`--` is not 0%** — unavailable impression-share data is held out (`no_is`), never scored as a
  0% share.
- Distinguish rank-lost vs budget-lost IS — they lead to opposite actions (QS/bid vs budget).
- `min_cost` gates **flagging**, not visibility — every campaign stays in the full table regardless
  of spend.
- One week is noisy — confirm a trend or a clear step-change before recommending big moves.
- No changes are made here (read-only MCP + a CSV read); recommendations route to the action
  skills + the manual Auction Insights/Transparency Center steps.
