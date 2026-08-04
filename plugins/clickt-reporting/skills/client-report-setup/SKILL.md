---
name: client-report-setup
description: Use when onboarding a new ecomm client into Clickt's hosted reporting system — "set up client reporting", "onboard <client> reports", "new report package". Interviews for accounts and value semantics, scaffolds the report-package engine into the client repo, configures data-source adapters, sets up hosting at reports.clickt.ca with per-client basic auth, and schedules the weekly report Routine.
---

# Client Report Setup

Onboard one ecomm client into the Clickt reporting system: scaffold → configure →
verify sources → host → schedule. The engine ships with this plugin at
`${CLAUDE_PLUGIN_ROOT}/templates/report-package/`.

**Read first:** the bundled `templates/report-package/RUNBOOK.md` (the cycle and its
gates) and `template/schema/CONTRACT.md` (the data contract). They govern everything.

## 1. Interview

Ask (AskUserQuestion where options exist; keep it to what config needs):

- Client name, slug (kebab), website, currency, locale.
- Client repo path (report-package lands at `<client-repo>/<project>/report-package/`).
- **Ad accounts + value semantics** — per channel: account id, and whether conversion
  value is **profit or revenue** (`conversion_value_is`). Ask explicitly about
  ProfitMetrics/profit tracking: Google profit often = primary conversion actions with a
  parallel "PM Revenue" action set; Meta profit is often carried on the
  complete-registration event value. Never assume; never blend POAS with ROAS.
- **Data sources per block** (google_ads / meta / store / traffic): Windsor connector,
  direct platform MCP, or manual export. Windsor is the default when the account is
  connected there.
- Store/analytics: Shopify MCP if available, else GA4 fallback (disclosed in method
  notes). GA4 property ids — note dual properties when ProfitMetrics splits Revenue/Profit.
- Proposed goals (or agree to seed from the first pull's actuals, status "proposed").

## 2. Scaffold

```bash
cp -R "${CLAUDE_PLUGIN_ROOT}/templates/report-package" <client-repo>/<project>/report-package
cd <client-repo>/<project>/report-package
mv config/client.example.json config/client.json   # then edit per interview
mv config/goals.example.json config/goals.json
```

- Edit `config/client.json`: client block, accounts, `sections.*.conversion_value_is`,
  adapter names. Branding tokens live in `template/partials/styles.css` (Clickt division
  system: HiveMind teal primary, Performance volt/moss data accents, Studio plum
  structural, ember attention) — chart series colors are CVD-validated data variants; do
  not swap raw brand steps into charts without re-running the dataviz palette validator.
- Add npm scripts to the client project's `package.json` if present:
  `"report:build": "node report-package/template/build.mjs"`,
  `"report:fixtures": "node report-package/template/fixtures/make-fixtures.mjs && node report-package/template/build.mjs --fixture monthly && node report-package/template/build.mjs --fixture weekly"`.
- Golden-build check: run `report:fixtures` — both fixtures must build; the broken
  fixture (`--fixture broken`) must abort.
- Write/adjust adapter recipes in `template/adapters/` for this client's sources
  (bundled recipes are working references from prior clients — verify field ids with
  `get_fields` before the first pull; Windsor `ctr` fields may be fractions → ×100).

## 3. Verify sources

Before promising anything: `get_connectors` (Windsor) / platform MCP probes for every
block. A block with no working source is configured `available: false` from day one —
the report renders an honest "unavailable" state, never approximations.

## 4. Hosting (reports.clickt.ca)

Shared Hetzner box — see the bundled RUNBOOK's Hosting section for server details.
New client = folder + auth block + graceful reload (no container recreation):

1. `ssh` to the server: `mkdir /root/reports/<slug>`.
2. Generate a password locally (`openssl rand -base64 15`), hash it with
   `docker exec caddy caddy hash-password`, and append to the Caddyfile
   (`/root/vaultwarden/Caddyfile`, timestamped backup first):
   ```
   @<slug> path /<slug> /<slug>/*
   basic_auth @<slug> {
       <slug> <bcrypt-hash>
   }
   ```
   inside the `reports.clickt.ca` site block, then
   `docker exec caddy caddy reload --config /etc/caddy/Caddyfile` (zero-downtime).
3. Give John the plaintext credential once, for Vaultwarden — never write it to a repo.
4. First deploy: `./deploy/deploy.sh`, then verify: `/` 200, `/<slug>/` 401 without
   credentials, 200 with; page titles correct.

## 5. Schedule the weekly Routine

Create a scheduled task (default **Monday 08:00**, John's timezone) whose prompt is
self-contained, e.g.:

> Run /clickt-reporting:report-weekly for `<absolute path to report-package>` — pull the
> just-completed ISO week, build the pulse draft, request commentary from John, and hold
> all deployment until he approves.

Confirm day/time with John before creating. Monthly runs can be a second Routine (1st of
month) or on-demand via `/clickt-reporting:report-monthly`.

## Hard rules

- Client deliverables are drafts until John approves. Hosting is auth-gated, but once a
  client holds credentials, **deploys are client-visible — the weekly/monthly skills
  hold deployment until John approves.**
- Numbers are never fabricated or approximated; blocked sources render unavailable.
- Validator failures abort builds — fix data, not the validator.
- Every cycle records raw pulls verbatim plus a spot-check note.
