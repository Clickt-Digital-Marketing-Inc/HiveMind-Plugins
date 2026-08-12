---
name: meta-ads-audit
description: >
  Use when the user asks to audit a Meta (Facebook/Instagram) ad account, run a Meta Ads account
  audit, review Meta ad account structure/budget/creative/attribution, or produce a Meta audit
  report/workbook. Pulls live data from the Meta Ads MCP (or ingests Ads Manager CSV exports when
  no MCP is connected), scores it against a comprehensive Meta Ads account-audit framework with a
  deterministic pre-scorer, and emits a 3-format deliverable bundle from one findings payload: an
  interactive self-contained HTML report (the primary client-shareable deliverable), an
  Obsidian-ready markdown record, and a formula-driven .xlsx backup — plus Concentration and
  Creative Signals analytics computed straight from the raw data files.
metadata:
  author: Clickt Digital Marketing Inc.
  plugin: Marketer Hive Mind
  version: "2.0.0"
  updated: "2026-07-12"
---

# Meta Ads Account Audit

## Bundled path resolution

Before running bundled scripts, set `PLUGIN_ROOT` to the absolute path of this plugin directory: the nearest ancestor of this `SKILL.md` that contains either `.claude-plugin/plugin.json` or `.codex-plugin/plugin.json`. Resolve it from the loaded skill path; do not assume a host-specific environment variable or the current working directory. Then run commands that reference `${PLUGIN_ROOT}` unchanged.

## Overview

Conduct a full Meta Ads account audit by pulling live data through the **Meta Ads MCP**,
evaluating it against a **7-lever Meta account-audit framework** (40 check IDs, 35 scorable
— Data Infrastructure & Signal, Account Architecture, Budget & Pacing, Attribution, Creative
Performance, Competitive Landscape (unscored), Future-Proofing), and emitting a **3-format
deliverable bundle** from one findings payload: an **interactive, self-contained HTML report
(the primary deliverable — client-shareable by email or static hosting, white-label, with a
live Health-Score gauge and ICE re-ranking)**, an Obsidian-ready **markdown** record, and a
**formula-driven .xlsx** backup. All three compute the same weighted Health Score, ICE
prioritization, and client summary — this skill's job is to gather accurate data, judge each
check (PASS / FLAG / FAIL / N/A), and assemble the payload JSON the builders consume.

Two analytics layers derive **exclusively from the saved raw data files, never from
model-authored text**: the **Concentration** report (HHI / Effective-N / Gini / Pareto-ABC
across campaigns, ad sets, ads, and objectives) and the **Creative Signals** layer (creative
fatigue, reach saturation, effective-frequency zones, and — on the CSV path — ranking
decomposition).

> **No MCP? The audit still runs.** If the Meta Ads MCP is not connected, walk the user
> through the three Ads Manager exports in `references/manual-exports.md` and build with
> `--csv-dir`. **NEEDS-REAL-EXPORT-VALIDATION:** the CSV path is encoded from documented
> Ads Manager export headers and has not yet been validated against real export files —
> any mismatch fails loudly through the parser's wrong-report guard, and the path must be
> confirmed against genuine exports before it is trusted for client work. Sections the
> exports can't cover are marked N/A — "Not available from manual export" — never
> approximated.

**Build only what the data can actually measure.** Anything the platform cannot see
(landing-page/CRO, seasonality, ICP/margin, testing calendar, MER/NC-ROAS, thumb-stop 3s)
is **declared out of scope on the Audit_Scope tab — never fabricated**.

## When to use
- "Audit my Meta account", "run a Meta Ads audit", "review the FB/IG account".
- When a client engagement needs a defensible Meta health score + prioritized action plan.
- Diagnosing fragmented structure, creative fatigue, attribution reliance, budget-to-results
  mismatches, or signal-quality (dataset/EMQ) gaps.

## When NOT to use
- Single-metric questions ("what's my CPM?") — just query the MCP directly.
- Google/LinkedIn/TikTok/Microsoft audits — this skill is Meta-only.
- Making changes to the account — this skill is **read-only analysis**; it never mutates
  campaigns.

## Critical guidelines
- You MUST run the deterministic pre-scorer (`--prescore-only`) **before** judging any check,
  and use the framework's **canonical check IDs** — the final build enforces machine results
  by ID regardless of what you drafted.
- You MUST confirm the account is usable before querying: `is_ads_mcp_enabled` AND
  `is_queryable`.
- You MUST verify field names with `ads_get_field_context` before calling
  `ads_get_ad_entities`, and MUST NOT request fields confirmed unavailable (see
  `references/mcp-field-reference.md`). Never pass `inline_link_clicks`,
  `video_3_sec_watched_actions`, `outbound_clicks`, `quality_ranking`, or a standalone
  `actions`/`action_values` — use the documented derivations instead.
- You MUST save the entity pulls **verbatim** to the exact filenames in
  `references/raw-pulls.md` — they are the only source of the Concentration, Creative
  Signals, and pre-scorer numbers (metric values never pass through the model).
- You MUST mark un-measurable checks `N/A` (excluded from scoring) and list out-of-scope
  areas — do not invent data, benchmarks, or competitors.
- You MUST label every window honestly (see **Honest-window rules** below).

## Required tooling
- **Meta Ads MCP — core:** `ads_get_ad_accounts`, `ads_get_field_context`,
  `ads_get_ad_entities`, `ads_get_datasets`, `ads_get_dataset_quality`,
  `ads_insights_advertiser_context`.
- **Meta Ads MCP — optional/contextual:** `ads_get_dataset_stats`, `ads_get_creatives`,
  `ads_get_creative_ads`, `ads_get_ad_account_custom_audiences`, `ads_library_search`
  (Competitive lever only), `ads_insights_industry_benchmark`,
  `ads_insights_performance_trend`, `ads_get_opportunity_score`,
  `ads_catalog_get_dynamic_ads_health` (ecommerce only).
- **Python 3** (stdlib) for md/html; **openpyxl ≥ 3.1** only for the xlsx backup
  (`python3 -m pip install 'openpyxl>=3.1'`).

## Workflow

To use the skill, work through these steps in order.

1. **Gate: MCP or manual path.** If the Meta Ads MCP is unavailable or errors, switch to the
   **manual-export path**: follow `references/manual-exports.md` (three Ads Manager CSV
   exports), judge only what those exports evidence, mark the rest N/A, and pass the files
   via `--csv-dir` in step 6 — then skip steps 2–4. With the MCP present: call
   `ads_get_ad_accounts`, pick the target, and **stop** unless `is_ads_mcp_enabled` and
   `is_queryable` are both true — surface `not_queryable_reason` and ask the user.

2. **Resolve scope.** `ads_insights_advertiser_context` → business model (Ecommerce vs
   Lead Gen), funnel, objective. Record it; it drives `--business-model` (CR-04 scoring and
   the DI-04 primary event). Fix the date windows: structure/budget/attribution `last_30d`;
   creative `last_90d`; optionally a `last_7d` ad-set pull (it unlocks the CR-07 true
   frequency bands). Confirm with the user if ambiguous.

3. **Verify fields (before any entity pull).** Call `ads_get_field_context` for every field
   you intend to request and confirm it resolves and supports the level you need. Known-good
   vs known-bad fields are listed in `references/mcp-field-reference.md`.

4. **Pull data and save the pulls verbatim.** Run the six pulls in
   `references/raw-pulls.md` (exact tool calls + field lists). Write the complete, unedited
   tool-result JSON of each pull — string-wrapped `ad_entities` envelope and all — to a
   working directory as:
   - `campaigns.json`, `adsets.json`, `ads.json` (required),
   - `adsets_7d.json`, `datasets.json`, `dataset_quality.json` (optional unlocks).

   These files are the **only** source of the Concentration, Creative Signals, and
   pre-scorer numbers — they are parsed deterministically by the bundled scripts, so metric
   values never pass through the model. Do not retype, trim, or reformat rows.

5. **Run the pre-scorer FIRST, then evaluate the judgment checks.** The mechanical checks
   are machine-scored — get their results before judging anything:
   ```bash
   python3 "${PLUGIN_ROOT}/skills/meta-ads-audit/scripts/build_audit.py" \
     --prescore-only --raw-dir "<workdir>" --business-model "{Lead Gen|Ecommerce}"
   ```
   (`--csv-dir` on the manual path; works without `--input`.) The JSON lists machine-scored
   `checks` (copy them as-is — the final build enforces them regardless), `evidence` for
   judgment checks, deterministic `kpis`, and `skipped` items that fall back to your
   judgment. Then score every remaining check in `references/audit-framework.md` as
   PASS / FLAG / FAIL / N/A with severity (Critical / High / Medium / Low), driving every
   threshold from `references/metrics-benchmarks.md` and preferring the account's own
   baseline. Put the actual observed number or evidence in each check's `observed` field,
   and use the framework's **canonical check IDs** — the build matches machine results by
   ID and injects any machine-scored check you omit.

6. **Assemble the payload.** Build the object in **Payload schema** below. Turn every FAIL
   and material FLAG into a `findings[]` row with ICE scores (defaults are filled from
   severity when omitted).

7. **Build the deliverable bundle.** Ask the user **where to save** the report (suggest
   `~/Downloads` as a sensible default), then build all three formats to that directory:
   ```bash
   python3 "${PLUGIN_ROOT}/skills/meta-ads-audit/scripts/build_audit.py" \
     --input audit-payload.json --outdir "<user-chosen-dir>" --brand "{Client Name}" \
     --raw-dir "<workdir-with-the-saved-pulls>" --business-model "{Lead Gen|Ecommerce}"
   ```
   The tool owns the filenames (`meta-audit_{slug}_{date}.{md,html,xlsx}`), runs the
   workbook's `--check` gate automatically, **copies the bundle to `~/Downloads`** in
   addition to the chosen outdir (skipped when `~/Downloads` does not exist, when it
   *is* the outdir, or under `--no-downloads`), and prints the paths (the last stdout
   line is a JSON object with
   `outputs`/`health`/`grade`/`checks`/`findings`/`prescore_corrections`).
   Flags: `--formats md,html` skips the xlsx (md/html need no openpyxl; an unknown
   format is an error, not a silent no-op); `--no-animate` builds motion-free HTML;
   `--no-downloads` suppresses the `~/Downloads` copy; explicit
   `--raw-campaigns`/`--raw-adsets`/`--raw-ads`/`--raw-adsets-7d`/`--raw-datasets`/
   `--raw-dataset-quality` replace `--raw-dir`; on the manual path use `--csv-dir`
   (or `--csv-campaigns`/`--csv-adsets`/`--csv-ads`) — `--raw-*` and `--csv-*` are
   mutually exclusive. Omit the data files and the bundle still builds, just without
   Concentration / Creative Signals / prescore.

   **The deterministic pre-scorer runs automatically** whenever raw/csv inputs are given:
   the mechanical checks and the KPI scorecard are recomputed in Python and **enforced
   over the payload** — any disagreement with your drafted results is corrected and logged
   to stderr (`prescore: CR-06 PASS->FAIL (top-5 ads 78.0% > 70%)`), and the final JSON
   line reports `prescore_corrections`. Your `recommendation` text is always preserved.
   `--no-prescore` opts out (not recommended).

   > **Corrections move the score, not your prose.** The pre-scorer enforces `checks`,
   > `observed` and `kpis` — it never rewrites `findings[]`. Every check it MOVED whose
   > narrative no longer follows is reported in `prescore.unreconciled` as
   > `{id, result, reason}`, with a `prescore: WARNING …` line each, in **both**
   > directions:
   > - `reason: "missing"` — scored FAIL/FLAG and **no finding covers it**: the score
   >   dropped and the roadmap is silent about why. **Add a finding.**
   > - `reason: "cleared"` — scored PASS/N-A while **a finding still argues it**: the
   >   score rose and the roadmap still tells the client to fix a non-problem.
   >   **Drop or amend that finding.**
   >
   > **Act on every one**, then rebuild, so the roadmap matches the score you present.
   > The warning reaches you on stderr and appears in the `.md` record and the `.xlsx`
   > working copy — deliberately **not** in the client-facing HTML, which is the
   > deliverable you send once they are resolved.

8. **Surface results.** Point the user at the **`.html`** (the primary client-shareable
   deliverable) with its clickable path, and report the Health Score + grade and the top
   3–5 quick wins (lowest-effort Critical/High findings). Note the report is interactive:
   a tab per lever, and on the Findings tab the user adjusts Confidence/Ease to re-rank by
   ICE live. The `.md` is the readable/vault record; the `.xlsx` is the editable backup
   (PASS/FLAG/FAIL dropdowns recalculate the Health Score on open). Close with an explicit
   **"Out of scope (not measurable from this data): …"** note.

## Payload schema

The builders read this exact shape (keys are stable; `tests/sample-payload.json` is a
complete worked example and a valid `--input`):

```jsonc
{
  "meta": {
    "account_id": "123456789", "account_name": "…", "business_model": "Ecommerce|Lead Gen",
    "currency": "USD",
    "windows": { "structure": "last_30d", "creative": "last_90d", "trend": "last_30d daily" },
    "generated_for_date": "YYYY-MM-DD", "auditor": "…",
    "out_of_scope": ["…"]                       // listed on the Audit_Scope tab
  },
  "category_weights": {                          // optional; defaults applied if omitted
    "Data Infrastructure & Signal": 20, "Account Architecture": 20, "Budget & Pacing": 15,
    "Attribution": 10, "Creative Performance": 25, "Future-Proofing": 10
  },
  "checks": [                                    // canonical framework IDs; category MUST
    { "id": "DI-02", "category": "Data Infrastructure & Signal",   // match a weight key
      "name": "CAPI live (server events)", "severity": "Critical",
      "flag": "PASS|FLAG|FAIL|N/A",
      "observed": "…", "expected": "…", "recommendation": "…" }
  ],
  "kpis": [                                      // OPTIONAL (additive) — scorecard rows;
    { "metric": "CTR (all-click)", "value": 0.658, "unit": "%",   // the pre-scorer's rows
      "benchmark": "", "flag": "N/A", "notes": "… window …" }     // replace yours by name
  ],
  "sections": {                                  // optional raw-evidence tables, per tab
    "architecture": { "columns": ["Campaign","Spend","Results","Spend %","Cost/Result"],
                      "rows": [["…",18400,612,"31%",30.07]] }
    // section keys: data_infrastructure, architecture, budget, attribution, creative,
    //               competitive, future_proofing
  },
  "findings": [
    { "id": "F-001", "title": "…", "category": "…", "severity": "Critical|High|Medium|Low",
      "evidence": "…", "recommendation": "…", "impact": 9, "confidence": 9, "ease": 6 }
    // impact/confidence/ease optional — defaults: impact from severity (9/7/5/3),
    // confidence/ease 5; priority = I*C*E buckets the 30/60/90 roadmap
  ]
}
```

**Concentration and Creative Signals are NOT part of this JSON.** They derive exclusively
from the saved raw pulls (or CSV exports) passed via `--raw-dir`/`--csv-dir` — never from
the payload — so their row-level numbers never pass through the model.

## Honest-window rules
- Every window label comes **from the data** (each row's `date_start`/`date_stop`), never
  from the requested preset — a "last_30d" pull is labeled with its actual dates.
  `meta.windows` in the payload records what you *asked Meta for*; it is provenance for
  the header only and must never be fed to Concentration / Creative Signals / the
  pre-scorer, which read the files themselves.
- Each input file carries its own window; mismatched windows stay honest because every
  observed/KPI line names the window it was measured on.
- **CR-07 (frequency)** gets its full PASS/FLAG/FAIL bands only on a ≤ 8-day window
  (the optional `adsets_7d.json` pull or a short CSV export); on 30-day data it degrades
  to **PASS-only mode** (FLAG ceiling, never FAIL) with an explicit window note.
- **CR-08 (refresh cadence)** is measured against `generated_for_date` (or the max
  `date_stop` in the data) — never the wall clock.
- Never present a metric as covering a window the underlying file does not.

## Data-accuracy rules (prevent wrong findings)
- Meta `results` are **objective-relative** (Reach vs Leads vs ThruPlays are not
  comparable). Results-based shares are only computed within a homogeneous indicator;
  mixed-indicator accounts get the spend mix as evidence, never a score.
- Only conversion-like results count as conversions (`conv_results`); Reach / video /
  view / engagement / click indicators are excluded, with the exclusions named.
- **Reach and frequency are non-additive** — never sum them across rows; aggregates that
  can't include them say so.
- Rates are recomputed from counts (CTR = clicks/impressions; CPM = spend/impressions×1000);
  returned rate strings are a fallback only.
- Any value string starting with `"Not available"` is treated as missing — the key is
  omitted, never zero-filled.
- Analyze ACTIVE entities for delivery checks; when status is absent, spend > 0 is the
  documented proxy.

## Bundled resources (load as needed)
- `references/raw-pulls.md` — the exact six MCP pulls (tool + fields), save-verbatim
  instructions, result-shape quirks, and which checks each file unlocks.
- `references/manual-exports.md` — the no-MCP Ads Manager export recipe (which reports,
  which columns) + honesty rules. **NEEDS-REAL-EXPORT-VALIDATION.**
- `references/audit-framework.md` — the execution map: each check → data source +
  pass/fail rule, and the explicit list of omitted (non-measurable) items.
- `references/metrics-benchmarks.md` — thresholds, severity weights, category weights,
  grade bands, ICE rubric.
- `references/mcp-field-reference.md` — verified field catalog, breakdown limits, metric
  formulas, and known gaps. **Read this before constructing any `ads_get_ad_entities` call.**
- `scripts/build_audit.py` — the entry point: builds md + interactive HTML + xlsx to
  `--outdir` (+ a `~/Downloads` copy). `--help` for usage.
- `scripts/audit_model.py` — canonical scoring constants + `compute_model()` (single source
  for all three formats).
- `scripts/audit_html.py` — the self-contained interactive HTML report (GSAP, white-label,
  theme-aware).
- `scripts/audit_md.py` — the Obsidian-ready markdown record.
- `scripts/meta_rows.py` — the raw-pull parser (transcription firewall): tolerant envelope
  + normalization shared by every downstream consumer.
- `scripts/concentration.py` — HHI/Effective-N/Gini/Lorenz/ABC metrics across campaigns,
  ad sets, ads, and objectives.
- `scripts/creative_signals.py` — creative fatigue, reach saturation, effective-frequency
  zones, ranking decomposition (stdlib).
- `scripts/prescore.py` — the deterministic pre-scorer: machine-scores the mechanical
  checks + KPI scorecard from the data files and enforces them at build time.
- `scripts/manual_csv.py` — Meta Ads Manager **UI export** parser for the no-MCP path
  (same firewall, same downstream pipeline).
- `scripts/build_audit_xlsx.py` — the xlsx backend (openpyxl ≥ 3.1; `--input`/`--output`,
  `--check`).
- `tests/sample-payload.json` — a reference payload showing the exact JSON shape.
- `tests/test_audit.py` — conformance tests (score parity, self-containment, determinism).

## Output contract
- Three files, one stem: `meta-audit_<slug>_<YYYY-MM-DD>.{html,md,xlsx}` in the
  user-chosen outdir, plus a copy of each in `~/Downloads` (unless it is absent, is
  itself the outdir, or `--no-downloads` was passed).
- **HTML** — the primary client-shareable deliverable: self-contained (no external
  requests), white-label, live Health-Score gauge, a tab per lever, evidence tables,
  Concentration + Creative Signals panels, ICE re-ranking.
- **md** — Obsidian-ready record with the same sections.
- **xlsx** — the editable backup: `00_Audit_Scope` … `11_Reference` (12 scored tabs with
  live formulas — overriding a Flag cell recalculates the workbook on open) plus
  values-only `12_Concentration` / `13_Creative_Signals` when data files were provided.
- A chat summary: Health Score + grade, top 3–5 priorities, per-lever one-liners, and the
  out-of-scope declaration.

## Troubleshooting
- **Account not queryable** → surface `not_queryable_reason`; do not proceed.
- **Field rejected / empty result** → re-check `ads_get_field_context`; consult
  `references/mcp-field-reference.md`.
- **Raw file won't parse** → the loader's error names the file and points at
  `references/raw-pulls.md` — re-save the tool result verbatim (string-wrapped
  `ad_entities` and all).
- **Prescore skips a check** → the `skipped` entry names the missing input; re-pull or
  re-export per the referenced doc, or leave it to judgment.
- **No video metrics** → expected for static-only ads; video checks skip/N-A honestly.
- **openpyxl missing** → md/html still build; install `'openpyxl>=3.1'` for the xlsx.
- **`--check` reports missing named ranges** → regenerate; do not hand-edit the workbook
  before delivery.

---
Authored by Clickt Digital Marketing Inc. — Marketer Hive Mind.
