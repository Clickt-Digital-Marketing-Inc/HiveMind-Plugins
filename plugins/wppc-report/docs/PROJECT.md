# wPPC — Weighted Profit-Per-Click Plugin

**Brief:** [wppc-plugin-plan.md](./wppc-plugin-plan.md) <!-- sibling file, this doc lives in docs/ -->
**Linear project:** https://linear.app/clickt/project/wppc-weighted-profit-per-click-plugin-41704dc00415
**Team:** Clickt
**Lessons Log:** the Linear document named "Lessons Log" on this project
**Domain:** software
**Client-facing identity:** Clickt Digital Marketing Inc. (same as executing org — no white-label attribution rule; note the plugin's OUTPUT is white-label for buyers, a product spec inside the issues)
**Tools & channels:** Python (pandas, click, pyyaml, openpyxl, vl-convert-python); Claude Code plugin packaging + marketplace.json; vendored GSAP + Vega-Lite; GitHub (Clickt-Digital-Marketing-Inc); Polar (product + GitHub Repository Access benefit)

## Summary

Take wPPC — a deterministic, sabermetric linear-weights PPC scoring tool (code-complete at v1.0.0, 19/19 tests, xlsx-only output) — to sale in the same manner as the audit plugins: an isolated private Clickt repo and a one-time Polar product gated by a GitHub Repository Access benefit. Before packaging, add additive/default-off methodology improvements (k-honesty, weight-drift detection, a 2-export decay delta, a non-functional incrementality seam) and replace xlsx-only output with the suite-standard HTML-first 3-format bundle (md + interactive HTML + xlsx backup) using a vendored Vega-Lite chart layer. Incrementality ships as its own separate plugin/product on a different track.

## Milestones

- **M1 — Methodology & metadata** — run-metadata block + k-honesty, W1 drift detection, W4 2-export decay delta, non-functional incrementality seam + contract doc.
- **M2 — HTML-first output & charts** — vendored Vega-Lite layer, HTML-first 3-format output from one model, CLI `--outdir` orchestration.
- **M3 — White-label, tests & packaging** — brand scrub + determinism/self-containment tests, package as plugin + register in marketplace.
- **M4 — Go-to-sale** — isolate to private Clickt repo + Polar product "HiveMind | wPPC" + GitHub-access gate.
- **Fast-follows (backlog)** — incrementality Layer-5 consumer, W4 full decay curve, W1 baseline lifecycle.

## Key decisions

See the brief's **Locked decisions** section — decisions made after planning live in the affected Linear issues, not here.

## How work happens here

All work is tracked in Linear; every issue is written to be executed as a standalone prompt. Session rules live in the [CLAUDE.md](../CLAUDE.md) at this plugin root. This document is orientation only — no status, no task lists (they would drift from Linear, and Linear wins).
