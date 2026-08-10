# HiveMind Plugins

Clickt's private Claude Code marketplace for marketing deliverables, ongoing account
management, hosted reporting, and internal workflow tools.

Authored by **Clickt Digital Marketing Inc.** ([clickt.ca](https://clickt.ca)). This
repository is private. Installation requires a GitHub account that has been granted read
access to `Clickt-Digital-Marketing-Inc/HiveMind-Plugins`, plus working GitHub credentials
in the environment where Claude Code installs the marketplace. Repository access does not
replace the [PolyForm Shield License 1.0.0](https://polyformproject.org/licenses/shield/1.0.0).

## Plugins

The marketplace manifest is the source of truth for the installable population.

| Plugin | Purpose | Runtime and dependencies | Data / connectors |
| --- | --- | --- | --- |
| **google-ads-audit** | Deterministic Google Ads audit with HTML, Markdown, and xlsx outputs. | Python >=3.9; `openpyxl>=3.1` for xlsx. | Read-only Google Ads MCP (GAQL) or Google Ads CSV exports. |
| **meta-ads-audit** | Meta account audit with concentration and creative-signal analysis. | Python 3; `openpyxl>=3.1` for xlsx. | Read-only Meta Ads MCP or Ads Manager CSV exports. |
| **shopify-cro-audit** | Shopify CRO audit with machine-computed funnel analytics. | Python 3; `openpyxl>=3.1` for xlsx. | Shopify MCP/ShopifyQL and/or GA4 plus Shopify CSV exports. |
| **cm3-profitability** | Per-product CM3 contribution-margin reporting. | No local compute runtime; protected remote execution only, with no local fallback. | Google Ads Shopping-products CSV; optional Shopify gross-profit CSV; authenticated protected-compute connector. |
| **google-ads-management** | Menu hub and twelve done-with-you Google Ads advisors. | Python 3; `openpyxl>=3.1`, `vl-convert-python==1.7.0`; optional LibreOffice for xlsx normalization. | Read-only Google Ads MCP or Google Ads UI/Editor/Auction Insights CSV exports. |
| **wppc-report** | Weighted Profit-Per-Click report for Google and Meta segments. | Python >=3.11; `pandas>=2.0`, `pyyaml>=6.0`, `click>=8.1`, `openpyxl>=3.1`, `vl-convert-python==1.7.0`. | Google Ads and Meta Ads CSV exports. |
| **clickt-reporting** | Hosted monthly reports and weekly pulses with an approval-gated deploy. | Node >=18; zero npm runtime dependencies in the bundled builder. | Windsor.ai and/or read-only Google Ads, Meta Ads, Shopify, and GA4 connectors, depending on client configuration. |
| **memo** | Interrogate an idea and produce a decision-ready Markdown memo. | No Python or build step. | No connector required. |
| **project-coordinator** | Turn a brief into governed, executable project work. | No Python or build step. | Linear MCP. |
| **social-media-manager** | Research, interview, plan, and file social content work. | No Python or build step. | Linear MCP plus web access. |
| **morning-briefing** | Email, project, priority, calendar, and time-off briefing. | No Python or build step. | Gmail, Linear, and Google Calendar MCPs. |
| **catch-up** | Convert new transcripts and email into reviewed work and draft replies. | No Python or build step. | Operator-selected transcript, email, and tracker connectors. |
| **orchestrator** | Coordinate Linear-governed multi-agent rounds and review queues. | Git; Python 3 is optional for the checkout guard. | Linear MCP. |

The six analytical deliverable plugins keep numbers in deterministic code paths rather
than asking the model to transcribe calculations. Output availability varies by plugin;
read its `SKILL.md` before assuming every format is supported.

## Install

1. Confirm that your GitHub account can clone this private repository and that Claude
   Code can use those credentials.
2. Add the marketplace:

   ```text
   /plugin marketplace add Clickt-Digital-Marketing-Inc/HiveMind-Plugins
   ```

3. Install any of the manifest-derived slugs below:

   ```text
   /plugin install google-ads-audit@hivemind-plugins
   /plugin install meta-ads-audit@hivemind-plugins
   /plugin install shopify-cro-audit@hivemind-plugins
   /plugin install cm3-profitability@hivemind-plugins
   /plugin install google-ads-management@hivemind-plugins
   /plugin install wppc-report@hivemind-plugins
   /plugin install clickt-reporting@hivemind-plugins
   /plugin install memo@hivemind-plugins
   /plugin install project-coordinator@hivemind-plugins
   /plugin install social-media-manager@hivemind-plugins
   /plugin install morning-briefing@hivemind-plugins
   /plugin install catch-up@hivemind-plugins
   /plugin install orchestrator@hivemind-plugins
   ```

`orchestrator` is also published in the standalone `clickt-orchestrator` marketplace.
Install it from one marketplace only because duplicate plugin names collide.

## Setup and use

Install only the dependencies listed for the chosen plugin. Connector-backed plugins need
the corresponding read-only MCP/app connection or the documented CSV alternative. An MCP
connection does not authorize account mutation: the marketing plugins analyze and emit
reviewable files; the operator applies any account changes separately.

Ask for the job in plain language, such as “audit my Google Ads account,” “run a CM3
report,” “manage Google Ads,” “set up client reporting,” or “give me my morning briefing.”
Each workflow's full contract lives under `plugins/<name>/skills/`.

The social-media-manager stores its voice profile at
`~/.claude/social-media-manager/voice-profile.md`, outside this repository.

## Updates, support, and license

Authorized users receive marketplace updates through Git. Optional community announcements
are available at [gethivemind.co](https://gethivemind.co); community signup does not grant
repository access.

Questions, bugs, or requests: [support@clickt.ca](mailto:support@clickt.ca).

[PolyForm Shield License 1.0.0](https://polyformproject.org/licenses/shield/1.0.0).
Copyright (c) 2026 Clickt Digital Marketing Inc. Use is licensed for the internal business
operations of you and your company; distribution, sublicensing, and sale of the software
or anything based on it are not. See [LICENSE](LICENSE).
