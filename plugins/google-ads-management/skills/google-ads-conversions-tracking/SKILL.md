---
name: google-ads-conversions-tracking
description: Use when monitoring Google Ads conversions weekly, validating conversion-tracking health (primary actions, counting, attribution), diagnosing a conversion-rate drop (high CTR but low CVR signals a landing-page issue), or checking whether tracking is solid enough for automated bidding. Pulls live conversion data and conversion_action config via the Google Ads MCP (or a CSV export), scores the config-health checklist and the CVR/CTR trend, and ships a done-with-you md/html/xlsx advisor bundle.
---

# Google Ads — Conversions & Tracking Advisor

Conversions are the success metric for lead-gen and sales accounts and the fuel for Smart Bidding.
Weekly is the right cadence — daily invites knee-jerk reactions to noise; monthly hides trends.

**Cadence:** **weekly** conversion review; tracking-health validation monthly and before enabling
any automation.

**REQUIRED BACKGROUND:** load `google-ads-foundation` first (dual-input contract, advisor output
contract, micros/date conventions).

## When to use
- "How are conversions trending", "my conversions dropped", "is my tracking set up right".
- High CTR but low conversion rate (landing-page suspicion).
- Before turning on Target CPA/ROAS (coordinate with `google-ads-bidding-strategy`).

## Step 0 — pick the input path

Follow `google-ads-foundation`'s dual-input Step 0 before pulling anything:

1. **Conversion-action config + campaign trend** — MCP path by default (`search_search`); CSV path
   (a Google Ads UI export) if the MCP is unreachable or the user already has one.
2. **Enhanced Conversions / Consent Mode confirmation** — **always** manual/CSV. The API does not
   expose this (`google-ads-foundation`'s API-blind list). Ask for the small `Check,Value,Note`
   template (see `references/conversion-tracking-filter.md`) or proceed without it — the advisor
   still ships two honest "not confirmed via API" rows, never silently dropped.

## Pull the data (MCP path)

1. **Conversion actions config + 30d conversions** — `conversion_action`: status, type, category,
   `primary_for_goal`, `counting_type`, attribution model, `metrics.conversions`.
2. **Campaign trend, current window** — `campaign`: clicks, impressions, cost, conversions.
3. **Campaign trend, prior window** — same fields, the comparable prior period (e.g. last 7 days vs
   prior 7 days; or `THIS_MONTH` vs `LAST_MONTH` — never literally "90d/30d", whatever window pair
   the operator picks).

Full GAQL + the transcription-firewall assembly command:
`references/conversion-tracking-filter.md`.

## Build the bundle + advise (the loop)

1. **Emit.** `python3 scripts/build_conv_tracking_report.py --input findings.json --outdir
   artifacts --formats md,html,xlsx --emit-widget widget.json`.
2. **Open with the hero HTML report** (`*_explorer.html`) — sliders over the CVR-drop threshold,
   volume floor, CTR-held factor, and below-account-CVR factor; a live sensitivity strip; static
   panels for the config-health checklist and the manual EC/Consent-Mode checks.
3. **Present prioritized recommendations** (Critical → High → Medium), each citing the model's
   numbers:
   - **Critical:** `summary.config_no_primary_action` true, or a config row flagged
     `dormant_primary` — fix before touching bids. A campaign tiered **Critical**
     (`landing_page_suspect` — CVR dropped while CTR held/improved) — route to the landing page,
     not the ad copy.
   - **High:** a campaign tiered **High** (a clear CVR drop, or well below the account's average
     CVR) — this week; a config row flagged `every_counting_lead` or `duplicate_primary_category`.
   - **Medium:** a campaign tiered **Watch** (thin volume alone); a config row flagged
     `legacy_attribution`; enabling Enhanced Conversions / Consent Mode confirmation where the
     manual check reads `not_confirmed`.
4. **Offer the apply artifacts.** Tracking/tag fixes and landing-page changes are manual (read-only
   MCP) — there is no Editor CSV for them; offer the prioritized checklist itself as the
   deliverable and point at the exact conversion action / campaign each item names.

## Common mistakes / red flags
- Don't react to a single window's conversion wobble — the sensitivity table shows whether the
  read holds as the CVR-drop threshold moves.
- A conversion drop with steady clicks usually means **broken tracking**, not worse performance —
  check the config-health table and recent account changes before touching bids.
- Don't assert Enhanced Conversions / Consent Mode state from MCP data — it isn't there. Every
  `manual_checks` row is honestly `user_csv` or `not_confirmed`, never presented as an API result.
- A campaign with 0 clicks in the prior window is `no_benchmark`, not "clean" — it's excluded from
  scoring (undefined CVR/CTR baseline), not silently dropped; it still appears in the bundle.
