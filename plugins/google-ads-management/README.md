# Google Ads Management

Ongoing, cadence-based Google Ads management, delivered as **done-with-you advisors**.
Each data skill takes live account data (read-only Google Ads MCP) **or** a user-supplied
CSV export, diagnoses it against 2026 thresholds, emits an analytical bundle, then leads a
prioritized recommendation conversation grounded in the model's own numbers — and offers
ready-to-apply Google Ads Editor CSVs.

Invoke **"manage Google Ads"** to open the `google-ads` hub — an interactive in-Claude menu
that lists every task and routes to it. If you already know the task ("budget pacing",
"quality score", "PMax"), invoke that skill directly.

## The advisor model

Every data skill follows the same contract (documented in
[`google-ads-foundation`](skills/google-ads-foundation/) →
`references/artifact-formats.md`):

1. **Dual input** — the Google Ads MCP (read-only GAQL) or a Google Ads UI CSV export.
   Both paths run through the same transcription firewall and reconciliation, and produce an
   **identical model** — the only difference is an honest `meta.source` label surfaced in the
   report. Data the API cannot return (Auction Insights, Customer Match match rates,
   Enhanced-Conversions / Consent-Mode confirmation) is user-supplied CSV/manual and is always
   labelled as such — never presented as an API pull.
2. **Emit the bundle**, hero-first:
   - `*.md` — narrative report with a full per-row table (no row is dropped).
   - `*_explorer.html` — one self-contained interactive file (inline CSS+JS, data embedded,
     zero external references); live sliders re-run the same kernel as the report.
   - `*.xlsx` — a formula-driven, tunable workbook, LibreOffice-normalized so it opens in Excel.
3. **Recommend** — prioritized actions grounded in the model numbers.
4. **Offer apply** — Google Ads Editor CSVs for the changes you approve.

Two skills ship an **honestly-scoped reduced bundle** (`md` + tunable `xlsx`, no HTML explorer)
because their signal is structural/checklist-shaped rather than a tunable per-row filter:
**account health** and **audience & targeting**.

## Skills

**Shared background**
- **`google-ads-foundation`** — account selection, the metadata-first GAQL method, money/date/dedup
  conventions, and the dual-input + advisor output contract every focus skill depends on. Load it first.

**Hub**
- **`google-ads`** — the "manage Google Ads" menu; lists and routes to every task (including the
  Audit, CM3 Profitability, and MediaMetrics skills in sibling plugins).

**Data skills** (12 — full 3-format bundle unless noted)

| Skill | Focus | Bundle |
|---|---|---|
| `google-ads-account-health` | Structural red flags (sprawl, missing negatives, naming, automation-without-data, PMax cannibalization) | md + xlsx (reduced) |
| `google-ads-budget-pacing` | MTD pace vs goal, 20% scale / 3x kill rules, account MER | md + html + xlsx |
| `google-ads-bidding-strategy` | Manual vs automated fit, tCPA/tROAS, data-maturity, learning-phase health | md + html + xlsx |
| `google-ads-keywords-search-terms` | SQR audit, three-tier negatives, add-keyword finds, two-block waste filter | md + html + xlsx |
| `google-ads-quality-score` | 6-step QS forensics: CTR, device split, ad-relevance matrix, low-CTR pause | md + html + xlsx |
| `google-ads-audience-targeting` | Remarketing tiers + bid adjustments, first-party readiness, PMax signals | md + xlsx (reduced) |
| `google-ads-conversions-tracking` | Conversion health, primary actions/counting/attribution, CVR-drop diagnosis | md + html + xlsx |
| `google-ads-performance-reporting` | Daily glance or monthly client report (spend, conv, revenue, ROAS) | md + html + xlsx |
| `google-ads-competitive-analysis` | Impression-share erosion, auction pressure, rank vs budget lost IS | md + html + xlsx |
| `google-ads-pmax-campaigns` | 14-day momentum: scale vs cut/investigate | md + html + xlsx |
| `google-ads-pmax-listing-groups` | Per-partition / per-product waste, campaign-benchmarked filter | md + html + xlsx |
| `google-ads-products` | Zombie / surging / declining products across Shopping + PMax | md + html + xlsx |

## Engineering guarantees

- **Transcription firewall** — MCP/CSV numbers never pass through the model's token stream:
  raw pull → `assemble_findings.py` / `assemble_from_csv` → `reconcile` control totals →
  `compute_model`. Findings without reconciliation warn/fail UNVERIFIED. Quoted numbers come
  from the artifacts, never from memory.
- **Kernel parity** — each tunable skill's classification/scoring math lives once in a Python
  `_core.py`, mirrored verbatim in the browser `js_kernel` and the xlsx formulas. A
  Node↔Python parity gate (`skills/google-ads/tests/run_parity.py`) proves the Python and JS
  kernels agree; the xlsx is validated by LibreOffice recalc.
- **No row loss** — every input row survives into the model carrying a `status`
  (`scored` / `manual` / `config` / `competitor_csv` / `no_benchmark`); reduced-bundle and
  API-blind data are represented by status, never dropped.

The shared toolkit lives in [`_shared/`](_shared/) (analytics primitives, CSV input path, data
guards, and the three-format `render/` toolkit) — see [`_shared/README.md`](_shared/README.md).

## Requirements & running

- Python deps: `pip install -r requirements.txt` (openpyxl ≥3.1, vl-convert-python==1.7.0).
- LibreOffice (`soffice`) on PATH for xlsx normalization/recalc.
- Data source: the Google Ads MCP (read-only) **or** a Google Ads UI CSV export.

Start with **"manage Google Ads"** (the hub) or invoke a specific skill; each skill's `SKILL.md`
documents its cadence, inputs, and the exact GAQL/CSV it needs.

Proprietary — see the repository [`LICENSE`](../../LICENSE).
