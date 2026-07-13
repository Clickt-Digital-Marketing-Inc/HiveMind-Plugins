# HiveMind Plugins

Clickt's HiveMind plugins for **Claude Code**, in one marketplace. Two families:
**deliverable** plugins that turn live ad/store data (or CSV exports) into
self-contained, white-label client reports, and **workflow** plugins that run your
day on Linear, Gmail, and Google Calendar.

### Deliverable plugins

Each emits an interactive HTML report, an Obsidian-ready markdown record, and a
formula-driven xlsx workbook from a single compute pass.

| Plugin | What it does | Data in |
| --- | --- | --- |
| **google-ads-audit** | Full Google Ads account audit against a 9-step framework + modern checks (PMax, Consent Mode v2, Enhanced Conversions, Demand Gen); live Health-Score gauge + ICE roadmap. | Google Ads MCP (GAQL) |
| **meta-ads-audit** | Full Meta (Facebook/Instagram) audit against a 7-lever framework with a deterministic pre-scorer, Concentration, and Creative Signals (fatigue, reach saturation, effective frequency, ranking decomposition). | Meta Ads MCP **or** Ads Manager CSV exports |
| **shopify-cro-audit** | 11-step Shopify conversion-rate-optimization audit; machine-computed funnel analytics, a 0–150 Funnel Health gauge, Concentration, and CVR Signals (Wilson CIs, z-tests, empirical-Bayes page CVRs). | Shopify MCP (ShopifyQL) and/or GA4 + Shopify CSV exports |
| **cm3-profitability** | Per-product CM3 contribution-margin report; CM3 bands + rollups by campaign, category (L1–L5), product type (L1–L5), and vendor, with a live HTML explorer that re-bands every table as you tune assumptions. | Google Ads Shopping-products CSV (+ optional Shopify Gross-profit CSV) |

### Workflow plugins

Skill-driven — no Python, no build step. They read and act through connected MCP
servers.

| Plugin | What it does | Runs on |
| --- | --- | --- |
| **project-coordinator** | Refine an idea into a brief, plan the work into Linear, structure the project folder, and keep every issue executable as a standalone prompt (software or marketing projects). | Linear MCP |
| **social-media-manager** | Plan a batch of posts: trend scan (Reddit + news), a voice-true interview that builds a persistent voice profile, then a writing prompt + a Higgsfield media prompt per post, each filed as a scheduled Linear issue. | Linear MCP + web |
| **morning-briefing** | Summarize Gmail and draft replies, report Linear progress + blockers, prioritize your issues, block focus time on your calendar, and flag 3-week time-off bottlenecks. | Gmail + Linear + Google Calendar MCPs |

> **Source-available.** Free to install and use within Claude Code for your own or
> your clients' accounts. You may read and modify the source locally, but not
> resell, redistribute, mirror, or re-host it. See [`LICENSE`](LICENSE).
>
> The social-media-manager stores your voice profile at
> `~/.claude/social-media-manager/voice-profile.md` — **on your machine, outside
> this repo.** Nothing personal is published here.

## Install

1. **Add the marketplace** in Claude Code:
   ```
   /plugin marketplace add Clickt-Digital-Marketing-Inc/HiveMind-Plugins
   ```
2. **Install the plugin(s) you want:**
   ```
   /plugin install google-ads-audit@hivemind-plugins
   /plugin install meta-ads-audit@hivemind-plugins
   /plugin install shopify-cro-audit@hivemind-plugins
   /plugin install cm3-profitability@hivemind-plugins
   /plugin install project-coordinator@hivemind-plugins
   /plugin install social-media-manager@hivemind-plugins
   /plugin install morning-briefing@hivemind-plugins
   ```
3. **Set up what your chosen plugins need:**
   - *Deliverable plugins* — Python 3 with `pip install openpyxl` (all four);
     `cm3-profitability` also needs `pip install python-pptx vl-convert-python==1.7.0`.
   - *Workflow plugins* — no Python. Connect the MCP servers they use: Linear
     (all three), plus Gmail + Google Calendar (morning-briefing) and web access
     (social-media-manager).

## Requirements

- **Claude Code** with plugin support.
- **Deliverable plugins — Python 3.** The audits' HTML + markdown renderers are
  standard-library only; `openpyxl` (>=3.1) is needed for the xlsx workbooks.
  `cm3-profitability` additionally needs `python-pptx` and the exact pin
  `vl-convert-python==1.7.0`. **LibreOffice** (optional) normalizes xlsx output.
  Data comes from each plugin's own MCP (Google Ads / Meta Ads / Shopify) **or**
  from CSV exports; `cm3-profitability` is CSV-only.
- **Workflow plugins — MCP servers, no Python.** `project-coordinator` and
  `social-media-manager` use the Linear MCP (social also uses web access);
  `morning-briefing` uses the Gmail, Linear, and Google Calendar MCPs. See each
  plugin's `SKILL.md` for the exact tools it calls.

## Use

Ask for the plugin's job in plain language:

- **Deliverables** — *"audit my Google Ads account"*, *"run a Meta ads audit"*,
  *"run a Shopify CRO audit"*, *"run a CM3 report"*. Each resolves the account/CSVs,
  computes deterministically (numbers are parsed by code, never guessed by the
  model), asks where to save, and builds the bundle. Access is **read-only** and
  the reports are **white-label** — they lead with the client's name, no vendor
  branding.
- **Workflows** — *"set up this project"* / *"plan this into Linear"*,
  *"plan my social posts"*, *"give me my morning briefing"*. These act through your
  connected tools; anything with an outward effect (sending mail, creating issues,
  booking calendar time) is confirmed with you first.

## Plugins & docs

Each plugin's full workflow lives in its `SKILL.md` under
`plugins/<name>/skills/<name>/`.

## License

Source-available. Copyright (c) 2026 Clickt Digital Marketing Inc. All rights
reserved. Free to use, not to redistribute — see [`LICENSE`](LICENSE).
