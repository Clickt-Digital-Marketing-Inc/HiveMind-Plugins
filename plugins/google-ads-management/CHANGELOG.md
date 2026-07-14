# Changelog

All notable changes to the `google-ads-management` plugin.

## 2.0.0 — Advisor upgrade & 3-format parity

Headline release: every data skill is now a dual-input (Google Ads MCP **or** user CSV),
done-with-you **advisor** that emits an analytical bundle and then leads a prioritized,
model-grounded recommendation conversation. This redefines the output contract of the existing
management skills (previously Editor-CSV-first), hence the major version bump.

### Shared foundations (`_shared/`)
- **Analytics primitives** (`analytics.py`) — deterministic, kernel-mirrorable `concentration`
  (top-share / HHI / effective-N), `signals` (declarative per-row rule flags), and `pre_score`
  (weighted flag scoring), back-ported from the audit plugins. Pure stdlib; a canonical
  `JS_MIRROR` keeps the browser translation in lockstep.
- **Shared CSV manual-input path** (`csv_input.py`) — the CSV twin of the MCP path
  (`assemble_from_csv` / `load_csv_rows`) running the same transcription-firewall + reconciliation
  discipline, producing a model **identical** to the MCP path except for an honest
  `meta.source: user_csv` label. Handles Google Ads UI export quirks (locale header variance,
  title/summary rows, BOM, thousands separators, percent columns).
- **Advisor output contract** — documented in `google-ads-foundation` (emit hero HTML report →
  recommend from model numbers → offer Editor apply-CSVs), with an honest data-source posture for
  API-blind data (Auction Insights, Customer Match match rates, Enhanced-Conversions / Consent-Mode).

### 7 skills deepened (already-3-format → advisor + concentration/signals + CSV input)
`budget-pacing`, `keywords-search-terms`, `performance-reporting`, `pmax-campaigns`,
`pmax-listing-groups`, `products`, `quality-score` — added shared analytics (n-gram / asset-group /
tier / dominant-factor concentration, period/anomaly signals & pre-scorers), the advisor
recommendation layer, and the dual MCP/CSV input path.

### 5 skills built to advisor bundles
- Full 3-format bundle (md + interactive HTML explorer + tunable xlsx): `bidding-strategy`,
  `competitive-analysis` (Auction Insights via CSV), `conversions-tracking`.
- Reduced bundle (md + tunable xlsx — structural/checklist signal, no per-row HTML filter):
  `account-health`, `audience-targeting`.

### Hub + integration
- The `google-ads` hub (`references/catalog.json` + `SKILL.md`) wires the 5 newly-tunable/advisor
  skills into the "manage Google Ads" menu, with per-task input mode, window, and declared formats.

### Parity & verification
- Node↔Python kernel-parity gate coverage for **all** tunable kernels plus the shared
  analytics primitives (`skills/google-ads/tests/run_parity.py`): 13 kernels green.
- Provenance token normalized to `mcp` for live pulls (HM-572); conversions-tracking JS_KERNEL
  parity gate added (HM-571).

### First-published baseline
## 1.0.0
- Initial `google-ads-management` plugin: the `google-ads` hub plus foundation and the
  management skills, driving the read-only Google Ads MCP and producing Editor CSVs and the
  early md/HTML/xlsx bundles on the shared `render/` toolkit.
