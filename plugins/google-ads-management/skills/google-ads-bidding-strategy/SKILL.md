---
name: google-ads-bidding-strategy
description: Use when reviewing or choosing a Google Ads bidding strategy (manual vs automated, Target CPA/ROAS, Maximize Conversions/Value, ECPC), scoring an account's data maturity, diagnosing whether automated bidding is failing (CPA spike, impression-share drop, stuck learning), or checking learning-phase health. Computes a per-campaign Data Maturity Score + bid-strategy-mismatch signal from the Google Ads MCP or a CSV export, and emits the md + interactive HTML + tunable xlsx advisor bundle.
---

# Google Ads — Bidding Strategy

Match the bidding strategy to each campaign's **data maturity**, and catch automation that is
running ahead of (or behind) what the data supports before it wastes spend.

**Cadence:** **weekly** review (bidding reacts to competitor behavior); daily during the first two
weeks after any strategy switch.

**REQUIRED BACKGROUND:** load `google-ads-foundation` first (the advisor + dual-input output
contract in `references/artifact-formats.md` governs this skill's loop).

## When to use
- "What bid strategy should I use", "should I switch to Target ROAS/CPA".
- Just switched strategies and performance moved.
- CPA spiked, impression share dropped, or a campaign is stuck in "Learning".
- Any account where automation is on but conversion tracking is thin.

## Step 0 — choose the input path
Per the foundation's dual-input contract: a user-supplied CSV wins outright; otherwise pull the
Google Ads MCP. Either way the two judgment components below (value variance, tracking confidence)
are **always** manual — see `references/bidding-strategy-maturity.md#judgment-inputs-both-paths`.

- **MCP** — one `campaign` structure+performance pull (`bidding_strategy_type`,
  `ai_max_setting.enable_ai_max`, `metrics.conversions`, `metrics.cost_micros`,
  `metrics.conversions_value`) over the last 30 days.
- **CSV** — ask for the Google Ads UI *Campaigns* report (Campaign, Campaign ID, Bid strategy
  type, Conversions, Cost, optional Conv. value), same 30-day window.

Build the findings JSON with `scripts/assemble_findings.py` (never by hand — see the reference doc
for the exact commands and the transcription-firewall discipline).

## The model — Data Maturity Score + bid-strategy-mismatch signal
Full formula, band table, and mismatch rule: `references/bidding-strategy-maturity.md`. In brief:

`Score = VolumeScore×0.40 + ValueVarianceScore×0.30 + TrackingConfidenceScore×0.30` (0-100,
tunable weights). VolumeScore is hard-scored from `conv30` vs a tunable target; the other two are
optional judgment inputs (assumed-neutral when absent, with an honest `confidence` flag — never
presented as measured). The score maps to a recommended tier (tunable band edges, default
30/50/70/85); the campaign's **current** strategy maps to a tier via a fixed lookup. The gap
between the two, plus the **≥ 30 conversions/30 days automation gate**, drives the mismatch signal:
`Over-automated (under-data)` (Critical), `Over-automated`, `Under-automated`, or aligned.

## Build the bundle, then advise (emit → report → recommend → offer-apply)
1. `python3 scripts/build_bidding_report.py --input findings.json --outdir artifacts --formats md,html,xlsx --emit-widget widget.json`
2. Open with the **HTML explorer** (`*_explorer.html`) — the hero deliverable — alongside the
   tuner widget.
3. Present recommendations **Critical → High → Medium**, every number cited from the model
   (`references/bidding-strategy-maturity.md#advisor-recommendations-critical--high--medium`):
   - **Critical** — every `Over-automated (under-data)` campaign: revert to Manual CPC/Max Clicks
     until `conv_gate` conversions/30d accrue.
   - **High** — every plain `Over-automated`/`Under-automated` campaign: move to the
     `recommended_label` tier; set tCPA/tROAS from trailing actuals, not an aggressive guess.
   - **Medium** — `borderline` campaigns (closest to a tier boundary) as a watch list.
4. Strategy changes are applied **manually** (read-only MCP) — offer the artifacts, don't declare
   "done". No Editor CSV applies a bid-strategy change; the bundle is the plan.

## Common mistakes / red flags
- Never enable Target CPA/ROAS without ~30+ conversions and a primary conversion action present.
- Don't react to a learning-phase dip in the first 1–2 weeks — that's expected, not failure.
- Setting tROAS/tCPA too aggressively starves delivery. Relax the target 15–20% if impression
  share drops after a switch.
- Never present `value_score`/`tracking_score` as measured when they're the tunable
  assumed-neutral default — the row's `confidence` field says so; repeat that honestly.
