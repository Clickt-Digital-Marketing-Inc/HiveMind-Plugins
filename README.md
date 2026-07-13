# HiveMind Plugins

Clickt's HiveMind marketing plugins for **Claude Code**, in one marketplace. Four
plugins that turn live ad/store data (or CSV exports) into self-contained,
white-label client deliverables — each emitting an interactive HTML report, an
Obsidian-ready markdown record, and a formula-driven xlsx workbook from a single
compute pass.

| Plugin | What it does | Data in |
| --- | --- | --- |
| **google-ads-audit** | Full Google Ads account audit against a 9-step framework + modern checks (PMax, Consent Mode v2, Enhanced Conversions, Demand Gen); live Health-Score gauge + ICE roadmap. | Google Ads MCP (GAQL) |
| **meta-ads-audit** | Full Meta (Facebook/Instagram) audit against a 7-lever framework with a deterministic pre-scorer, Concentration, and Creative Signals (fatigue, reach saturation, effective frequency, ranking decomposition). | Meta Ads MCP **or** Ads Manager CSV exports |
| **shopify-cro-audit** | 11-step Shopify conversion-rate-optimization audit; machine-computed funnel analytics, a 0–150 Funnel Health gauge, Concentration, and CVR Signals (Wilson CIs, z-tests, empirical-Bayes page CVRs). | Shopify MCP (ShopifyQL) and/or GA4 + Shopify CSV exports |
| **cm3-profitability** | Per-product CM3 contribution-margin report; CM3 bands + rollups by campaign, category (L1–L5), product type (L1–L5), and vendor, with a live HTML explorer that re-bands every table as you tune assumptions. | Google Ads Shopping-products CSV (+ optional Shopify Gross-profit CSV) |

> **Source-available.** Free to install and use within Claude Code for your own or
> your clients' accounts. You may read and modify the source locally, but not
> resell, redistribute, mirror, or re-host it. See [`LICENSE`](LICENSE).

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
   ```
3. **Install Python dependencies** (only what your chosen plugins need):
   ```
   pip install openpyxl                            # xlsx backup — all four
   pip install python-pptx vl-convert-python==1.7.0 # cm3-profitability only
   ```

## Requirements

- **Claude Code** with plugin support.
- **Python 3.** The audits' HTML + markdown renderers are standard-library only;
  `openpyxl` (>=3.1) is needed for the xlsx workbooks. `cm3-profitability`
  additionally needs `python-pptx` and the exact pin `vl-convert-python==1.7.0`.
- **LibreOffice** (optional) — used headlessly to normalize xlsx output; the
  bundles still build without it.
- **Data** — each plugin works from its own MCP (Google Ads / Meta Ads / Shopify)
  **or** from CSV exports; `cm3-profitability` is CSV-only. See each plugin's
  `SKILL.md` for the exact export recipes.

## Use

Ask for the plugin's job in plain language — e.g. *"audit my Google Ads account"*,
*"run a Meta ads audit"*, *"run a Shopify CRO audit"*, *"run a CM3 report"* — or use
its slash command. Each plugin resolves the account/CSVs, computes deterministically
(numbers are parsed by code, never guessed by the model), asks where to save, and
builds the bundle. All access is **read-only**; the plugins never change your
accounts. Reports are **white-label** — they lead with the client's name and carry
no vendor branding.

## Plugins & docs

Each plugin's full workflow lives in its `SKILL.md` under
`plugins/<name>/skills/<name>/`.

## License

Source-available. Copyright (c) 2026 Clickt Digital Marketing Inc. All rights
reserved. Free to use, not to redistribute — see [`LICENSE`](LICENSE).
