# HiveMind Plugins

Clickt's HiveMind plugins for **Claude Code**, in one marketplace. **Deliverable**
plugins turn live ad/store data (or CSV exports) into self-contained, white-label
client reports; a **management suite** runs ongoing Google Ads work as done-with-you
advisors; and **workflow** plugins run your day on Linear, Gmail, and Google Calendar.

Authored by **Clickt Digital Marketing Inc.** ([clickt.ca](https://clickt.ca)).
This repository is private.
Installing plugins from this marketplace requires access to `Clickt-Digital-Marketing-Inc/HiveMind-Plugins`.

### Deliverable plugins

Each emits an interactive HTML report, an Obsidian-ready markdown record, and a
formula-driven xlsx workbook from a single compute pass.

| Plugin | What it does | Data in |
| --- | --- | --- |
| **google-ads-audit** | Full Google Ads account audit against a 9-step framework + modern checks (PMax, Consent Mode v2, Enhanced Conversions, Demand Gen); live Health-Score gauge + ICE roadmap. | Google Ads MCP (GAQL) |
| **meta-ads-audit** | Full Meta (Facebook/Instagram) audit against a 7-lever framework with a deterministic pre-scorer, Concentration, and Creative Signals (fatigue, reach saturation, effective frequency, ranking decomposition). | Meta Ads MCP **or** Ads Manager CSV exports |
| **shopify-cro-audit** | 11-step Shopify conversion-rate-optimization audit; machine-computed funnel analytics, a 0–150 Funnel Health gauge, Concentration, and CVR Signals (Wilson CIs, z-tests, empirical-Bayes page CVRs). | Shopify MCP (ShopifyQL) and/or GA4 + Shopify CSV exports |
| **cm3-profitability** | Per-product CM3 contribution-margin report; CM3 bands + rollups by campaign, category (L1–L5), product type (L1–L5), and vendor, with a live HTML explorer that re-bands every table as you tune assumptions. | Google Ads Shopping-products CSV (+ optional Shopify Gross-profit CSV) |

### Management suite

An ongoing-management layer rather than a one-shot report: an in-Claude menu that
routes to focus-area **done-with-you advisors**, each of which diagnoses live data
behind a transcription firewall, leads a prioritized recommendation loop, and hands
you ready-to-apply Google Ads Editor CSVs.

| Plugin | What it does | Data in |
| --- | --- | --- |
| **google-ads-management** | Menu hub + 12 Google Ads advisors — budget pacing, bidding strategy, keywords/search terms, Quality Score, audiences, conversions & tracking, performance reporting, competitive analysis, PMax campaigns, PMax listing groups, products, and account health. Each tunable skill emits the same 3-format bundle (interactive HTML + markdown + tunable xlsx) with Node↔Python kernel parity (account health & audience targeting ship a reduced md + xlsx bundle). | Google Ads MCP (GAQL) **or** Ads UI / Editor / Auction Insights CSV exports |

### Workflow plugins

Skill-driven: no Python, no build step. They read and act through connected MCP
servers.

| Plugin | What it does | Runs on |
| --- | --- | --- |
| **memo** | Interrogate a raw idea, scale the depth to the stakes, pressure-test it against the objections a director would actually raise, then write a decision memo: the ask first, real options, a reasoned recommendation, and an honest account of what would kill it. Every claim marked measured/estimated/assumed/derived. | Nothing — no MCP, no Python |
| **project-coordinator** | Refine an idea into a brief, plan the work into Linear, structure the project folder, and keep every issue executable as a standalone prompt (software or marketing projects). | Linear MCP |
| **social-media-manager** | Plan a batch of posts: trend scan (Reddit + news), a voice-true interview that builds a persistent voice profile, then a writing prompt + a Higgsfield media prompt per post, each filed as a scheduled Linear issue. | Linear MCP + web |
| **morning-briefing** | Summarize Gmail and draft replies, report Linear progress + blockers, prioritize your issues, block focus time on your calendar, and flag 3-week time-off bottlenecks. | Gmail + Linear + Google Calendar MCPs |
| **catch-up** | Turn everything new since the last run — call transcripts, email — into tracked work: extract tasks/decisions/questions, de-dupe against your tracker, file issues review-first, and draft (never send) the replies and follow-ups you owe. | Transcript + email + tracker MCPs (tool-agnostic; setup skill binds them) |
| **orchestrator** | Run a Linear-governed project as rounds of parallel, tiered executors in git worktrees: merge gate, reflect pass, QC, checkpoint/halt discipline, interactive review-queue closeout (`/orchestrator:close-issues`) and lessons review (`/orchestrator:lessons-review`). Execution-side counterpart to project-coordinator. | Linear MCP + git (`python3` optional, for the checkout-guard hook — fails open without it) |

> **Source-available under the [PolyForm Shield License 1.0.0](https://polyformproject.org/licenses/shield/1.0.0).**
> Free to install and use within Claude Code for the internal business operations
> of you and your company — including work on your own clients' accounts. No
> redistribution, no re-hosting, no sublicensing, no resale — of the software or
> anything based on it, in whole or in part. See [`LICENSE`](LICENSE).
>
> The social-media-manager stores your voice profile at
> `~/.claude/social-media-manager/voice-profile.md`, **on your machine, outside
> this repo.** Nothing personal is published here.

## Install

1. **Add the marketplace** in Claude Code:
   ```
   /plugin marketplace add Clickt-Digital-Marketing-Inc/HiveMind-Plugins
   ```
2. **Install a plugin.** Example:
   ```
   /plugin install google-ads-audit@hivemind-plugins
   ```
   Installable slugs, each `@hivemind-plugins`:
   ```
   /plugin install google-ads-audit@hivemind-plugins
   /plugin install meta-ads-audit@hivemind-plugins
   /plugin install shopify-cro-audit@hivemind-plugins
   /plugin install cm3-profitability@hivemind-plugins
   /plugin install google-ads-management@hivemind-plugins
   /plugin install memo@hivemind-plugins
   /plugin install project-coordinator@hivemind-plugins
   /plugin install social-media-manager@hivemind-plugins
   /plugin install morning-briefing@hivemind-plugins
   /plugin install wppc-report@hivemind-plugins
   /plugin install catch-up@hivemind-plugins
   /plugin install orchestrator@hivemind-plugins
   ```
   > `orchestrator` is also published in the standalone `clickt-orchestrator` marketplace — install it from **one** marketplace only (two installs of the same plugin name collide).
3. **Set up what your chosen plugins need:**
   - *Deliverable plugins & the management suite*: Python 3 with `pip install openpyxl`;
     `google-ads-management` also needs `vl-convert-python==1.7.0` for its charts, and
     `cm3-profitability` needs `pip install python-pptx vl-convert-python==1.7.0`.
   - *Workflow plugins*: no Python required (exception: `orchestrator`'s checkout-guard
     hook wants `python3` on PATH, and fails open without it). Connect the MCP servers
     they use: Linear (project-coordinator, social-media-manager, morning-briefing,
     orchestrator), plus Gmail + Google Calendar (morning-briefing), web access
     (social-media-manager), and your transcript/email/tracker tools (catch-up).
     `memo` needs nothing — it writes a markdown file and stops.

## Requirements

- **Claude Code** with plugin support.
- **Deliverable plugins & the management suite, Python 3.** The HTML + markdown
  renderers are standard-library only; `openpyxl` (>=3.1) is needed for the xlsx
  workbooks. `google-ads-management` needs `vl-convert-python==1.7.0` for its static
  chart SVGs; `cm3-profitability` additionally needs `python-pptx` and the same
  `vl-convert-python==1.7.0` pin. **LibreOffice** (optional) normalizes xlsx output.
  Data comes from each plugin's own MCP (Google Ads / Meta Ads / Shopify) **or** from
  CSV exports; `google-ads-management` takes either, `cm3-profitability` is CSV-only.
- **Workflow plugins, MCP servers, no Python.** `project-coordinator` and
  `social-media-manager` use the Linear MCP (social also uses web access);
  `morning-briefing` uses the Gmail, Linear, and Google Calendar MCPs. See each
  plugin's `SKILL.md` for the exact tools it calls.

## Use

Ask for the plugin's job in plain language:

- **Deliverables**: *"audit my Google Ads account"*, *"run a Meta ads audit"*,
  *"run a Shopify CRO audit"*, *"run a CM3 report"*. Each resolves the account/CSVs,
  computes deterministically (numbers are parsed by code, never guessed by the
  model), asks where to save, and builds the bundle. Access is **read-only** and
  the reports are **white-label**: they lead with the client's name, no vendor
  branding.
- **Workflows**: *"set up this project"* / *"plan this into Linear"*,
  *"plan my social posts"*, *"give me my morning briefing"*. These act through your
  connected tools; anything with an outward effect (sending mail, creating issues,
  booking calendar time) is confirmed with you first.

## Plugins & docs

Each plugin's full workflow lives in its `SKILL.md` under
`plugins/<name>/skills/<name>/`.

## Community and updates

This repository is private.
Installing plugins from this marketplace requires access to `Clickt-Digital-Marketing-Inc/HiveMind-Plugins`.

If you want the HiveMind community and a heads-up when new plugins ship, one
email at [gethivemind.co](https://gethivemind.co) gets you both. This is
optional; it exists for people who want ongoing updates, not as a gate on the
plugins themselves.

<!-- TODO(CF-04): direct Discourse community URL when confirmed -->

## Support

Questions, bugs, or requests: [support@clickt.ca](mailto:support@clickt.ca).

## License

[PolyForm Shield License 1.0.0](https://polyformproject.org/licenses/shield/1.0.0).
Copyright (c) 2026 Clickt Digital Marketing Inc. Use is licensed for the internal
business operations of you and your company; distribution, sublicensing, and sale —
of the software or anything based on it — are not. See [`LICENSE`](LICENSE).
