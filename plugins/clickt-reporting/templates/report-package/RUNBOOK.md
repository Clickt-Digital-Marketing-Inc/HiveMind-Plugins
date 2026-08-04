# Reporting Package — Runbook

Repeatable cycle for the hosted HTML reports (monthly + weekly pulse). The engine is
client-agnostic (see `template/schema/CONTRACT.md`); this folder is one client's instance.

## The cycle (monthly or weekly)

1. **Pull** each enabled source per its recipe in `template/adapters/` → save raw
   responses verbatim to `periods/<id>/raw/`.
2. **Normalize** into `periods/<id>/data.json` per the contract. Never approximate a
   blocked source — set `available: false` with a reason; the section renders an honest
   unavailable state.
3. **Validate + build**:
   ```bash
   node report-package/template/build.mjs <period-id>     # e.g. 2026-07 or 2026-W31
   ```
   The validator aborts on inconsistent numbers. Fix data, not the validator.
4. **Spot-check gate** (client-facing rule from `Reporting/CLAUDE.md`): verify 3–4
   headline numbers through an independent path (e.g. Meta Ads MCP vs Windsor) and record
   the result in `periods/<id>/raw/spot-check.md`. No match → no report.
5. **Review**: John reviews `report-preview.html` (browser-openable twin of the
   artifact-ready `report.html`).
6. **Commentary**: John writes `periods/<id>/commentary.md` — one block per `## section`
   heading: `exec`, `attainment`, `google_ads`, `meta`, `store` (monthly) or `pulse`
   (weekly). Rebuild (step 3).
7. **Publish** (only after John approves — drafts rule): deploy to the client's folder on
   **reports.clickt.ca** — `./deploy/deploy.sh` builds `dist/<slug>/` (index + standalone
   report pages) and rsyncs it to the server. The folder is behind per-client basic auth,
   so deploying a draft is safe; share credentials with the client only after sign-off.
8. Commit the period folder.

## Hosting (reports.clickt.ca)

- **Server:** Hetzner box `root@5.161.204.210` (`ubuntu-4gb-ash-1`), Caddy in Docker
  (compose + Caddyfile in `/root/vaultwarden/`, timestamped `.bak-*` backups alongside).
- **Layout:** `/root/reports/<client-slug>/` mounted read-only at `/srv/reports`, served at
  `https://reports.clickt.ca/<client-slug>/`. Root shows a generic landing page — no
  client enumeration. `X-Robots-Tag: noindex` + `Cache-Control: no-store` on everything.
- **Access:** per-client HTTP basic auth (`basic_auth` block per client folder in the
  Caddyfile; bcrypt via `docker exec caddy caddy hash-password`). Credentials live in
  Vaultwarden (`vw.clickt.ca`); one username/password per client.
- **Deploy:** `./deploy/deploy.sh` (rsync of `dist/<slug>/`). Static files only — no
  Caddy action needed for content updates.
- **New client hosting:** `mkdir /root/reports/<slug>`, append a matcher + `basic_auth`
  block to the Caddyfile, `docker exec caddy caddy reload --config /etc/caddy/Caddyfile`
  (graceful, zero-downtime — container recreation is only needed for new *mounts*).

## Cadence

- **Monthly**: run in the first days of the new month for the full prior month
  (+ prior-month and YoY comparison windows).
- **Weekly pulse**: run Monday/Tuesday for the just-completed ISO week (Mon–Sun), plus
  MTD actuals for goal pacing.

## Goals

`config/goals.json`, schema v2 — see `template/schema/GOALS.md`. Flexible per store:
any metric from the catalog (store, blended, per-channel, SKU-scoped), monthly defaults
plus month-specific seasonal targets, higher/lower directions. `status: "proposed"`
renders a badge until agreed; change targets by adding a new goal set with a later
`effective_from`, never by editing history.

**Update loop:** the reporting dashboard (the client index page at
reports.clickt.ca/<slug>/) carries a **Goals** editor — John (or John with the client)
adjusts targets, hits Export JSON, and hands the JSON back; it replaces
`config/goals.json` verbatim and the next build judges against it. Rebuild the dashboard
with `node template/build-dist.mjs` after a goals change so the editor shows the new set.

## Testing the engine (no live data needed)

```bash
npm run report:fixtures      # regenerate + golden-build monthly & weekly fixtures
node report-package/template/build.mjs --fixture broken   # must abort with errors
```

## Known issues / state

*(Per-client: record data-source quirks, tracking gaps, and open items here as cycles
surface them — e.g. value-semantics rules, YoY validity, attribution artifacts.)*

## Onboarding the next ecomm client

1. Copy `report-package/` WITHOUT `periods/` into the new client's repo
   (or copy only `template/` + `RUNBOOK.md` and write fresh `config/`).
2. Edit `config/client.json`: name, currency, locale, accent palette, account ids,
   **value semantics per channel** (`conversion_value_is: "revenue"` unless the client
   tracks profit like PantryLot), adapter per block.
3. Write/reuse adapters for the client's sources (all-Windsor, platform MCPs, or manual
   CSV — anything that can fill the contract).
4. Seed `config/goals.json` (status "proposed" until agreed).
5. Run the cycle. The engine needs zero changes — if it does, the change belongs in the
   contract discussion, not a fork.
