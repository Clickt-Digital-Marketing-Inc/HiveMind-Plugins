---
name: client-report-weekly
description: Use for the weekly client report cycle — "run the weekly report", "weekly pulse for the client", or when a scheduled Routine invokes /clickt-reporting:report-weekly. Pulls the just-completed ISO week, builds the pulse draft, requests John's commentary, and deploys ONLY after his approval.
---

# Weekly Report Cycle

Run one weekly pulse for a client whose `report-package/` was set up by
`client-report-setup`. The argument (or the thing to ask for) is the absolute path to
the client's `report-package/`. Read its `RUNBOOK.md` first — cycle, gates, hosting,
and the client's Known-issues section (value semantics, source quirks).

## The non-negotiable gate

**Nothing deploys until John approves.** The client may hold live credentials; a deploy
is client-visible the moment it lands. Build the draft, request commentary, stop. Only
John's reply (commentary, or an explicit "ship it" without commentary) unlocks
`deploy.sh`.

## Cycle

1. **Window**: the just-completed ISO week (Mon–Sun), prior week for WoW, plus
   month-to-date actuals (revenue, spend, orders, new customers) for goal pacing.
2. **Pull** every enabled block per `template/adapters/*` — save each raw response
   verbatim to `periods/<YYYY-Wnn>/raw/`. Store rates at ≥4dp (never pre-round to
   display precision — derived deltas drift). A blocked source becomes
   `available: false` with a reason; never approximate.
3. **Normalize** into `periods/<YYYY-Wnn>/data.json` per `template/schema/CONTRACT.md`
   (weekly extras: `meta_envelope.mtd`).
4. **Build**: `node template/build.mjs <YYYY-Wnn>` — the validator aborts on
   inconsistent numbers; fix data, not the validator.
5. **Spot-check gate**: verify headline numbers through an independent path (e.g. Meta
   Ads MCP vs Windsor) or, when none exists, internal triangulation (trend sums =
   totals, campaign sums ≤ totals, derived-metric recomputation). Record in
   `periods/<id>/raw/spot-check.md`. No match → no report.
6. **Draft review**: render `report-preview.html` (headless screenshot), and give John
   a plain-language summary — headline numbers, WoW moves, pace vs goals, anything a
   client would ask about.
7. **Ask for commentary** — see below.
8. **On approval**: write the reply into `periods/<id>/commentary.md` under `## pulse`
   (light markdown: paragraphs, **bold**, `- ` lists; tidy John's rough notes but keep
   his judgments — do not invent claims), rebuild (`build.mjs <id>`), assemble
   (`node template/build-dist.mjs`), deploy (`./deploy/deploy.sh`), then verify live
   (401 without credentials, 200 with; new pulse listed on the dashboard and in the
   monthly report's Weekly Pulses dropdown after its next rebuild). Commit the period
   folder.

## Asking for commentary

- **Interactive session**: summarize the draft, then ask directly for commentary —
  offer a drafted starting point built from the spot-check notes, clearly labeled as a
  draft for him to edit.
- **Scheduled/headless Routine**: end the turn with the draft summary and the request:
  what the numbers say, what you'd flag, and "Reply with commentary (or 'ship it') and
  I'll integrate and deploy." Do not wait in a loop, do not deploy, do not
  self-approve. John continues the Routine's session when ready; integration happens on
  his reply.

## Update side-effects worth remembering

- A goals JSON handed back from the dashboard's Goals editor replaces
  `config/goals.json` verbatim → rebuild report *and* dashboard (`build-dist.mjs`).
- Log new source quirks discovered during the pull in the client RUNBOOK's
  Known-issues section.
