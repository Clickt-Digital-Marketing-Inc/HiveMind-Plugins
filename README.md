# HiveMind Plugins

Clickt's HiveMind plugins for **Claude Code**, in one marketplace. The separately
owned Pyrito Reporting package is also available here as a pinned private source and
installs directly from its canonical repository in both Claude Code and Codex. **Deliverable**
plugins turn live ad/store data (or CSV exports) into self-contained, white-label
client reports; a **management suite** runs ongoing Google Ads work as done-with-you
advisors; a **hosted reporting** system runs recurring client report cycles; and
**workflow** plugins run your day on Linear, Gmail, and Google Calendar.

Authored by **Clickt Digital Marketing Inc.** ([clickt.ca](https://clickt.ca)).
This repo is public and its locally bundled plugins are free to install and run. No
signup is required for those plugins. `pyrito-reporting` is different: its source
repository is private, and installation requires access to that repository.

### Deliverable plugins

Each emits an interactive HTML report, an Obsidian-ready markdown record, and a
formula-driven xlsx workbook from a single compute pass.

| Plugin | What it does | Data in |
| --- | --- | --- |
| **google-ads-audit** | Full Google Ads account audit against a 9-step framework + modern checks (PMax, Consent Mode v2, Enhanced Conversions, Demand Gen); live Health-Score gauge + ICE roadmap. | Google Ads MCP (GAQL) |
| **meta-ads-audit** | Full Meta (Facebook/Instagram) audit against a 7-lever framework with a deterministic pre-scorer, Concentration, and Creative Signals (fatigue, reach saturation, effective frequency, ranking decomposition). | Meta Ads MCP **or** Ads Manager CSV exports |
| **shopify-cro-audit** | 11-step Shopify conversion-rate-optimization audit; machine-computed funnel analytics, a 0–150 Funnel Health gauge, Concentration, and CVR Signals (Wilson CIs, z-tests, empirical-Bayes page CVRs). | Shopify MCP (ShopifyQL) and/or GA4 + Shopify CSV exports |
| **cm3-profitability** | Per-product CM3 contribution-margin report; CM3 bands + rollups by campaign, category (L1–L5), product type (L1–L5), and vendor, with a live HTML explorer that re-bands every table as you tune assumptions. | Google Ads Shopping-products CSV (+ optional Shopify Gross-profit CSV) |
| **wppc-report** | wPPC (Weighted Profit-Per-Click) — a sabermetric linear-weights model: funnel events credited at expected CM3 value, indexed to the account baseline, shrunk for sample size, and scored above replacement (Margin Above Replacement), behind a Scale/Cut/Watch decision lens with four charts. | Google & Meta Ads segment CSV exports |

### Management suite

An ongoing-management layer rather than a one-shot report: an in-Claude menu that
routes to focus-area **done-with-you advisors**, each of which diagnoses live data
behind a transcription firewall, leads a prioritized recommendation loop, and hands
you ready-to-apply Google Ads Editor CSVs.

| Plugin | What it does | Data in |
| --- | --- | --- |
| **google-ads-management** | Menu hub + 12 Google Ads advisors — budget pacing, bidding strategy, keywords/search terms, Quality Score, audiences, conversions & tracking, performance reporting, competitive analysis, PMax campaigns, PMax listing groups, products, and account health. Each tunable skill emits the same 3-format bundle (interactive HTML + markdown + tunable xlsx) with Node↔Python kernel parity (account health & audience targeting ship a reduced md + xlsx bundle). | Google Ads MCP (GAQL) **or** Ads UI / Editor / Auction Insights CSV exports |

### Hosted client reporting

A standing reporting system rather than a single document: the canonical private
package scaffolds an engine into a client repo and then runs the recurring cycle
against it. This public marketplace stores only commit-pinned source metadata; it does
not carry a second engine copy.
Its Claude source records use the canonical repository's HTTPS URL so private access
can use the operator's existing Git credential helper.

| Plugin | What it does | Data in |
| --- | --- | --- |
| **pyrito-reporting** | Canonical Pyrito package for approval-gated monthly reports and weekly pulses. The marketplace source is pinned to the verified private release commit; production remains at `reports.gethivemind.co`. | Windsor.ai / platform MCPs (needs Node ≥18) |
| **clickt-reporting** | Transitional command shim for saved `/clickt-reporting:report-*` invocations. It points at the shim inside the same pinned canonical commit and never carries or runs an independent engine. | Install `pyrito-reporting` to run workflows. |

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
   /plugin install pyrito-reporting@hivemind-plugins
   /plugin install clickt-reporting@hivemind-plugins
   ```
   > `orchestrator` is also published in the standalone `clickt-orchestrator` marketplace — install it from **one** marketplace only (two installs of the same plugin name collide).

   `pyrito-reporting@hivemind-plugins` resolves to the private canonical repository at
   the approved commit recorded in [the 1.5.0 release notes](docs/pyrito-reporting-1.5.0.md).
   It requires Git access to `Pyrito-ai/Pyrito-Reporting`; the private engine is not
   copied into this public repository.

### Install Pyrito Reporting directly

Direct installation from the canonical private repository is the primary path. It
requires repository access.

Claude Code:

```text
/plugin marketplace add Pyrito-ai/Pyrito-Reporting
/plugin install pyrito-reporting@pyrito-reporting
```

Codex:

```bash
codex plugin marketplace add Pyrito-ai/Pyrito-Reporting --ref main
codex plugin add pyrito-reporting@pyrito-reporting
```

Start a fresh conversation after installation so the setup, weekly, and monthly
workflows are discovered.

### Migrate existing `clickt-reporting` installs

The `clickt-reporting` marketplace identity remains available as a fail-closed command
shim. It does not include a reporting engine and cannot publish a report by itself.

1. Install `pyrito-reporting` from the canonical marketplace above.
2. Replace `/clickt-reporting:report-setup`, `/clickt-reporting:report-weekly`, and
   `/clickt-reporting:report-monthly` with the equivalent `/pyrito-reporting:...`
   commands in saved prompts and scheduled routines.
3. Confirm setup, weekly, and monthly discovery in a fresh conversation.
4. Keep the shim enabled until every saved invocation has been checked.

The shim is retained through the final no-stranding audit in PYR-73 and may retire only
after separate human approval and the objective compatibility window in the release
notes. Domain migration is explicitly deferred to a separate project; the current
production hostname remains `reports.gethivemind.co`.

### Set up what your chosen plugins need

   - *Deliverable plugins & the management suite*: Python 3 with `pip install openpyxl`;
     `google-ads-management` also needs `vl-convert-python==1.7.0` for its charts, and
     `cm3-profitability` needs `pip install python-pptx vl-convert-python==1.7.0`.
   - *Hosted client reporting*: `pyrito-reporting` needs **Node ≥18**, access to
     `Pyrito-ai/Pyrito-Reporting`, and its data source (Windsor.ai or the platform
     MCPs); no Python. `clickt-reporting` is only a migration shim.
   - *Workflow plugins*: no Python required (exception: `orchestrator`'s checkout-guard
     hook wants `python3` on PATH, and fails open without it). Connect the MCP servers
     they use: Linear (project-coordinator, social-media-manager, morning-briefing,
     orchestrator), plus Gmail + Google Calendar (morning-briefing), web access
     (social-media-manager), and your transcript/email/tracker tools (catch-up).
     `memo` needs nothing — it writes a markdown file and stops.

## Requirements

- **Claude Code** with plugin support for this marketplace. The canonical reporting
  package also supports **Codex** through its own private Git marketplace.
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

This repo is public, and every plugin in it is free to install and run. No
signup is required to install anything above.

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
