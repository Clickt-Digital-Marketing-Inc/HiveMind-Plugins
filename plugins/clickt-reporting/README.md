# clickt-reporting

Clickt's hosted ecomm client reporting system as a Claude Code plugin. Born from the
PantryLot reporting build (2026-08); PantryLot's
`Clients/PantryLot/Reporting/report-package/` is the reference instance.

## What it does

- **`/clickt-reporting:report-setup`** — onboard a client: interview (accounts,
  profit-vs-revenue value semantics, sources), scaffold the bundled engine into the
  client repo, verify data sources, host at `reports.clickt.ca/<slug>/` behind
  per-client basic auth, schedule the weekly Routine (Monday 08:00 default).
- **`/clickt-reporting:report-weekly`** — the Routine workload: pull the just-completed
  ISO week + MTD, validate, spot-check, build the pulse **draft**, ask John for
  commentary, integrate it, and deploy **only after his approval**.
- **`/clickt-reporting:report-monthly`** — full-month tabbed report (Executive Summary /
  Attainment / Google Ads / Meta Ads / Store / Weekly Pulses), per-section commentary,
  same approval gate.

## The engine (bundled at `templates/report-package/`)

Zero-dependency Node builder rendering self-contained HTML (light/dark, Clickt division
branding, CVD-validated chart palettes). Normalized data contract with a hard validator
(builds abort on inconsistent numbers), adapter recipes per source (Windsor.ai,
platform MCPs, GA4 fallback), flexible v2 goals (metric catalog, SKU-scoped, seasonal
month targets, lower-is-better directions) with an in-dashboard Goals editor that
exports `goals.json`, and a client dashboard listing all reports.

## Principles (enforced by the skills)

1. Numbers are never fabricated — blocked sources render an explicit unavailable state.
2. Value semantics are config: profit → POAS, revenue → ROAS, never blended; MER and
   nCAC suppress themselves when any channel's spend is missing.
3. Every cycle keeps raw pulls verbatim + a spot-check record.
4. Drafts until John approves — the deploy gate survives automation.

## Install (dev)

```
/plugin marketplace add /Users/johngreenhow/Documents/Tools/clickt-reporting
/plugin install clickt-reporting@clickt-reporting-dev
```

Released via the `hivemind-plugins` marketplace.
