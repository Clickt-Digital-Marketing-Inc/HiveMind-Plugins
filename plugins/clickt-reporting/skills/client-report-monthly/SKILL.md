---
name: client-report-monthly
description: Use for the monthly client report cycle — "run the monthly report", "build the client's July report". Pulls the full prior month (plus prior-month and YoY windows), builds the tabbed monthly report draft, requests John's commentary per section, and deploys ONLY after his approval.
---

# Monthly Report Cycle

Same discipline as `client-report-weekly` (read it — the deploy gate, spot-check gate,
and commentary flow apply identically). Differences:

## Windows and data

- Current = the full prior calendar month; prior = the month before; YoY = same month
  last year **only when its value basis is comparable** (e.g. a pre-profit-tracking year
  makes value YoY invalid — set `yoy: null`, drop `yoy_range`, and disclose via
  `meta_envelope.method_notes`). Check the client RUNBOOK's Known-issues.
- Full block depth: daily trend series, campaign tables, funnel (view → cart →
  checkout → purchase), channel split, top products. Campaign/trend sums must
  reconcile with totals (validator + spot-check).
- SKU-scoped goals (see `template/schema/GOALS.md`) need those SKUs pulled into
  `store.sku_metrics`.

## Build

```bash
node template/build.mjs <YYYY-MM>
node template/build-dist.mjs     # refreshes dashboard: report lists + Goals editor
```

The monthly report is tabbed (Executive Summary / Attainment / Google Ads / Meta Ads /
Store / Weekly Pulses); the Weekly Pulses tab auto-discovers sibling pulse periods.

## Commentary

Section ids in `periods/<YYYY-MM>/commentary.md`: `## exec`, `## attainment`,
`## google_ads`, `## meta`, `## store`. Offer John a per-section draft grounded in the
spot-check notes; he edits or replaces. Empty sections render "Commentary to follow" —
fine for a first deploy only if John explicitly approves shipping without commentary.

## After approval

Deploy via `./deploy/deploy.sh`, verify live (auth + titles + tabs), commit. If goals
changed this cycle (dashboard export handed back), replace `config/goals.json`
verbatim first so attainment judges against the new set.
