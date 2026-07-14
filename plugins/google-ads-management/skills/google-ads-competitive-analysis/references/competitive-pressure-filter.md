# Competitive Pressure Filter — WoW IS/CPC deltas + rank-vs-budget attribution

Flags Search campaigns losing auction position week-over-week, and ships the standard
three-format analytical bundle: a **markdown report** (narrative + a full per-campaign table), a
**self-contained interactive HTML explorer** (sliders + sensitivity + a competitor-concentration
panel, opens in any browser with no install), and a **formula-driven xlsx** (LibreOffice-normalized
so it opens in Excel). Reuses every `google-ads-foundation` convention (micros, dates, `SEARCH`
scope) — load that first.

All three formats are rendered by the shared toolkit (`_shared/render`) from one classification
engine (`scripts/competitive_core.py`), so they can never disagree; this file is the
**authoritative** input/output contract (the scripts' docstrings point here rather than restating
it).

## Two data sources — own-side (MCP) is always live; competitors are ALWAYS user-supplied

**Own-side impression-share and CPC metrics are queryable via the Google Ads MCP.** The
**Auction Insights report — competitor domains, their impression share, overlap rate, and
position-above rate — is NOT available via the Google Ads API.** There is no GAQL resource that
returns it. This skill therefore always computes the own-side model from the MCP (or a plain
performance-report CSV export, per `google-ads-foundation`'s dual-input contract) and accepts the
competitor payload **only** via a user-supplied Auction Insights CSV export — optional, and
clearly labelled. **Never imply the API returned competitor names or share.**

## The own-side model

Two GAQL pulls (`mcp__google-ads-mcp__search_search`), same fields, two non-overlapping 7-day
windows — **this week** and the **prior week** (end both at yesterday; today's data is partial):

```
resource:   "campaign"
fields:     ["campaign.id","campaign.name","campaign.advertising_channel_type",
             "metrics.cost_micros","metrics.clicks","metrics.impressions","metrics.conversions",
             "metrics.search_impression_share","metrics.search_rank_lost_impression_share",
             "metrics.search_budget_lost_impression_share"]
conditions: ["segments.date BETWEEN '<start>' AND '<end>'",
             "campaign.advertising_channel_type = 'SEARCH'"]
orderings:  ["metrics.cost_micros DESC"]
```

Run once for `<this-week-start> .. <yesterday>` and once for `<prior-week-start> ..
<this-week-start - 1 day>` (7-day windows, back to back, no gap/overlap).

**Gotcha:** `LAST_7_DAYS` moves as the report date changes — use an explicit `BETWEEN` so the two
pulls stay a clean back-to-back week pair when a report is regenerated later.

**Impression-share fields can be `--` (unavailable).** Google Ads withholds `search_impression_share`
(and the rank-/budget-lost variants) below its own data threshold. Treat a missing/non-numeric
value as **unknown, not zero** — a campaign with `--` this or prior week is held out with
`status="no_is"`, never scored as a 0% share.

`average_cpc` is **recomputed** from `cost / clicks` (not read from `metrics.average_cpc`) so it
stays internally consistent with the cost/click totals the reconciliation totals check.

**Transcription firewall (mandatory).** Save both pulls verbatim to files, then build the findings
JSON with `scripts/assemble_findings.py` — never assemble it by hand:

```bash
python3 scripts/assemble_findings.py \
  --this <raw-this-week-file> --prior <raw-prior-week-file> \
  --client-name "{Client Name}" --account-id {account} --currency {CUR} \
  --window-this "<this-week-start> to <yesterday>" \
  --window-prior "<prior-week-start> to <this-week-start - 1 day>" \
  -o findings.json
```

Add `--auction-insights <csv>` (below) to the same command to fold in the competitor CSV; the
own-side model is byte-identical with or without it (proven in `tests/`).

## The competitor payload — Auction Insights CSV (optional, user-supplied)

Ask the user to export, in the Google Ads UI: **Campaigns → the campaign(s) in question →
Insights → Auction insights → Download → .csv**, for the same **this-week** window as the own-side
pull. Required columns: **Display URL domain** and **Impr. share**; also keep **Overlap rate**,
**Position above rate**, and **Top of page rate** if present — the export includes a **"You"** row
representing the account itself, which the model keeps (for transparency) but excludes from the
competitor concentration read.

```bash
python3 scripts/assemble_findings.py \
  --this <raw-this-week-file> --prior <raw-prior-week-file> \
  --auction-insights auction_insights_export.csv \
  --client-name "{Client Name}" --account-id {account} --currency {CUR} \
  --window-this "..." --window-prior "..." -o findings.json
```

Competitor rows carry `status="competitor_csv"` in the model (never dropped, never merged into the
own-side campaign rows) and `meta.auction_insights_source = "user_csv"` in the report provenance —
**never** presented as an API pull. `scripts/competitive_core.build_competitors` runs
`_shared/analytics.concentration()` (top-N share / HHI / effective-N) over the non-self rows to
answer "is competitive pressure concentrated in 1–2 domains, or spread across many?"

## Flags — Rank pressure / Budget capped

A **scored** campaign (both weeks have real impression-share data) spending **at least
`min_cost`** this week (default $50) is **flagged** when EITHER fires, week-over-week:

- **IS drop** — `impression_share_this - impression_share_prior <= -is_drop_flag` (default 5
  percentage points, i.e. `<= -0.05`).
- **CPC jump** — `(avg_cpc_this - avg_cpc_prior) / avg_cpc_prior >= cpc_jump_flag` (default 15%).

A flagged campaign's **block** is attributed to whichever loss driver worsened more this week:

- **Rank pressure** — `rank_lost_is_delta >= budget_lost_is_delta` (competitor bids/quality
  pushing you down the page) → route to `google-ads-quality-score` and/or
  `google-ads-bidding-strategy`.
- **Budget capped** — otherwise (the budget-lost-IS delta is the larger driver) → route to
  `google-ads-budget-pacing`.

`_shared/analytics.signals()` evaluates the two flag rules (declarative, not hand-rolled
if/else); `_shared/analytics.pre_score()` (weights: IS-drop 2.0, CPC-jump 1.0) ranks flagged
campaigns by pressure severity for the "Live pressure" sort order. Campaigns below `min_cost` are
**never** flagged regardless of how large their deltas are (see the SmallSpend fixture row) —
they still appear in the full table with `status="scored"`, `eligible=false`.

Campaigns with **no prior-week row** (`status="no_prior"`, e.g. a new or recently resumed
campaign), **unavailable impression-share data** (`status="no_is"`), or **zero activity both
weeks** (`status="inactive"`) are held out, reported separately, and **never classified** — never
silently dropped.

## The findings JSON

What the assembler produces (and the script's input contract):

```json
{
  "meta":   {"client_name","account_id","currency","window_this","window_prior","generated",
             "source": "mcp", "auction_insights_source": "user_csv" | ""},
  "params": {                                     // all optional; defaults below = rule "as written"
     "is_drop_flag": 0.05, "cpc_jump_flag": 0.15, "min_cost": 50.0, "concentration_top_n": 3
  },
  "campaigns": [{"campaign_id","campaign",
                "cost_this","clicks_this","impressions_this","conversions_this","avg_cpc_this",
                "impression_share_this","rank_lost_is_this","budget_lost_is_this",     // null = "--"
                "cost_prior","clicks_prior","impressions_prior","conversions_prior","avg_cpc_prior",
                "impression_share_prior","rank_lost_is_prior","budget_lost_is_prior",  // null = "--"
                "has_prior"}],                     // false = no matching prior-week row
  "competitors": [{"domain","campaign","impression_share","overlap_rate",
                   "position_above_rate","top_of_page_rate"}]   // [] on an MCP-only run
}
```
Impression-share-style fields are ratios (`0.10` = 10%); `cost`/`avg_cpc` are in the account
currency (already divided by 1e6). `impression_share_*` / `rank_lost_is_*` / `budget_lost_is_*`
are `null` when Google Ads returned `--` (unavailable, not zero).

## Build the deliverable bundle

```bash
# md + html — dependency-free, needs only Python
python3 scripts/build_competitive_report.py \
  --input findings.json --outdir artifacts --brand "{Client Name}" --formats md,html
# all three (xlsx needs openpyxl; normalizes via LibreOffice)
python3 scripts/build_competitive_report.py \
  --input findings.json --outdir artifacts --brand "{Client Name}" --formats md,html,xlsx
```
Files land in `artifacts/` as `competitive-pressure_{account}_{date}.{ext}` (`.md`,
`_explorer.html`, `.xlsx`). Run the unit tests with `python3 tests/test_competitive.py` and the
shared-toolkit tests with `python3 ../../_shared/render/tests/test_render_toolkit.py`.

**What each format is for** — all rendered by `_shared/render` from one model, so no two can
disagree.
- `*.md` — the narrative / trust layer: provenance header (account, windows, currency, generated,
  thresholds, whether an Auction Insights export was supplied), headline counts, the
  **"0 flagged is clean"** explanation, the **sensitivity table**, the **near-miss** ranking, the
  **competitor concentration** read, the **excluded-campaign** list, and a **full per-campaign
  table** with each row's `status` and assigned `block` (the no-row-loss layer). Zero dependencies.
- `*_explorer.html` — the **interactive primary**: self-contained (inline CSS+JS, data embedded, no
  external refs), with range **sliders** (IS-drop threshold, CPC-jump threshold, minimum spend),
  live counts, a **sensitivity strip**, a **competitor concentration panel**, and the campaign
  table with status badges. Opens in any browser — no install, no Excel, no cloud. The embedded JS
  computes byte-identical results to the Python model (Node-verified).
- `*.xlsx` — the tunable Controls + Live-pressure workbook (see layout below), with a **Snapshot**
  tab and a **Status** column (no row loss). Built via the shared `render.xlsx`.

**Currency** from `meta.currency` is shown in every header and on cost columns.

**Excel-open honesty.** The xlsx is **normalized through LibreOffice** (`soffice`) by default. If
`soffice` is missing the xlsx build **fails (exit 2)** rather than shipping a file that may not
open (`--no-normalize` overrides). For a zero-friction interactive deliverable that needs no
spreadsheet app at all, prefer the **HTML explorer**.

## xlsx layout

**Controls** sheet — (1) **Flag parameters** — yellow dropdowns: IS-drop threshold `C5`, CPC-jump
threshold `C6`, minimum this-week spend `C7`; (2) **Flag & block logic** — plain-language rules
that **rewrite themselves** from those cells; (3) **Results (live)** — `COUNTIF`/`SUMIF` over the
Live-pressure `Block` column; (4) **Auction Insights competitors** — the user-supplied CSV rows, so
the honesty label is visible in the workbook itself, not just the report prose.

**Live pressure** sheet — **every** Search campaign (frozen header + auto-filter; flagged rows
highlighted). A **Status** column marks `scored` / `no prior` / `no is` / `inactive`; held-out rows
keep their metrics but are left unclassified (never dropped). Scored rows carry formula columns
referencing the Controls cells (`Eligible?`, `IS-drop fired?`, `CPC-jump fired?`, `Flagged?`,
`Block` = `AND()`/`IF()` of the conditions).

**Snapshot** sheet — a static snapshot at the generated parameters: flags per IS-drop threshold,
the top near-misses, the competitor concentration read, and the excluded-campaign list.

Changing any Controls cell recomputes the Live pressure sheet and the counts — no rebuild needed.

## Common mistakes / red flags

- **Never fabricate competitor data.** If no Auction Insights CSV was supplied, the report and
  xlsx say so explicitly — do not infer competitor names, share, or overlap from anything else.
- **`--` is not 0%.** A campaign with unavailable impression-share data is `no_is`, never scored as
  a 0% share (that would manufacture a false 100pp "drop").
- Distinguish **Rank pressure** vs **Budget capped** — they lead to opposite actions (Quality
  Score/bids vs a budget decision).
- **`min_cost` gates flagging, not visibility** — a low-spend campaign with a huge WoW swing still
  appears in the full table (`status="scored"`, `eligible=false`); it is just never flagged, since
  a small-spend swing is usually noise.
- One week is noisy — confirm a trend or a clear step-change (or a supplied competitor CSV) before
  recommending big moves.
- No changes are made here (read-only MCP + a CSV read); recommendations route to the action
  skills (`google-ads-quality-score`, `google-ads-bidding-strategy`, `google-ads-budget-pacing`).
