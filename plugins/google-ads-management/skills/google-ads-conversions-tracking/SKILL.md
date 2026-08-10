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

1. **Conversion actions config + all conversions** — `conversion_action`: status, type, category,
   `primary_for_goal`, `counting_type`, attribution model, `metrics.all_conversions` (all
   conversions incl. secondary — the only conversions metric selectable at the `conversion_action`
   grain; `metrics.conversions` is **not** valid there). The checklist is then segmented by
   `primary_for_goal` into primary (health-framing) and secondary sections. Authoritative constant:
   `CONFIG_FIELDS` in [scripts/assemble_findings.py](scripts/assemble_findings.py).
2. **Campaign trend, current window** — `campaign`: status, clicks, impressions, cost, conversions.
   (`campaign.status` drives the liveness gate below — a paused/removed campaign with zero spend in
   both windows can't manufacture a fake CVR-drop Critical.) Constant: `CAMPAIGN_FIELDS`.
3. **Campaign trend, prior window** — same fields, the comparable prior period (e.g. last 7 days vs
   prior 7 days; or `THIS_MONTH` vs `LAST_MONTH` — never literally "90d/30d", whatever window pair
   the operator picks). Same constant: `CAMPAIGN_FIELDS`.

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
- A paused/dead campaign's CVR "drop" is not a finding. Every trend row is tagged with a **liveness**
  band (see below) and dormant rows are scored to zero — don't hand the user a Critical on a
  campaign that isn't running.

## Campaign liveness gate (three-band)

Every campaign_trend row is tagged by `_shared/analytics.segment_liveness` (mirrored verbatim into
the browser kernel and the xlsx `Liveness` column) so severity is scored only on what's live:

- **live** — `ENABLED` **and** spend > 0 in the current window → scored normally.
- **recently_active** — any recent signal that isn't live: `PAUSED`/`REMOVED` but spent mid-window ·
  `ENABLED` but idle (zero current spend) · spend only in the prior window → **still scored**, but
  the row carries a `liveness_note` so the recommendation is hedged ("confirm intent before acting")
  rather than presented as a hard Critical.
- **dormant** — not `ENABLED` **and** zero spend in **both** windows → **present-but-tagged, zeroed**
  (tier `""`, score 0, flags `[]`). Never dropped (no-row-loss); a dead campaign can no longer
  manufacture a fake CVR-drop Critical.

**Three-band fully derivable:** the campaign_trend rows carry current-window spend (`cost_curr`) AND
prior-window spend (`cost_prior`), so `segment_liveness` is called with `prior_spend_key="cost_prior"`
and all three bands (including the "spent only in the prior window" path) are reachable — no invented
prior window. `liveness` is data, not a tunable: it depends on status + spend (fixed pulled facts),
computed once in Python and read (not re-derived) by the live kernel and the xlsx formulas.
