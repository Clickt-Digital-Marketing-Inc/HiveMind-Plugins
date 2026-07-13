---
name: shopify-cro-audit
description: >
  Use when the user asks to audit a Shopify store for conversion (CRO audit, conversion-rate audit,
  "why am I losing conversions", "where is my funnel leaking", 11-step CRO audit, ecommerce CRO
  review). Runs an 11-step CRO framework — analytics, LIFT heuristics, review mining, support,
  heatmaps, post-purchase + email surveys, user testing, marketing match, competitor analysis —
  pulling live data through the Shopify MCP (ShopifyQL) and/or ingesting GA4 + Shopify CSV exports,
  with the entire Step-1 analytics block machine-computed (never hand-transcribed). Emits a 3-format
  deliverable bundle from one payload: an interactive self-contained HTML report (the primary
  client-shareable deliverable, with a live 0–150 Funnel Health gauge and (Impact×2)+Ease
  re-ranking), an Obsidian-ready markdown record, and a formula-driven .xlsx backup — plus
  Concentration and CVR Signals analytics computed straight from the raw data files. Steps without
  data are declared "Not run", never fabricated.
metadata:
  author: Clickt Digital Marketing Inc.
  plugin: Marketer Hive Mind
  version: "2.0.0"
  updated: "2026-07-12"
---

# Shopify CRO Audit (11-Step Framework)

## Overview

Run a structured conversion-rate-optimization audit of a Shopify store following an **11-step CRO
framework for ecommerce** — organized **by analysis method, not page type** — and emit a **3-format
deliverable bundle** from one findings payload: an **interactive, self-contained HTML report (the
primary deliverable — client-shareable by email or static hosting, white-label, with a live
0–150 Funnel Health gauge and (Impact×2)+Ease re-ranking)**, an Obsidian-ready **markdown**
record, and a **formula-driven .xlsx** backup. All three compute the same Funnel Health score,
grade, and testing-roadmap prioritization — this skill's job is to gather accurate data, judge the
qualitative steps, and assemble the payload JSON the builders consume.

**The Step-1 analytics block is machine-computed.** Funnel rates, device/channel/landing-page CVRs,
revenue concentration, new-vs-returning, and AOV are parsed deterministically from saved Shopify
MCP results and/or GA4 + Shopify CSV exports — the numbers never pass through the model. Two
analytics layers derive **exclusively from the same saved data files, never from model-authored
text**: the **Concentration** report (HHI / Effective-N / Gini / Pareto-ABC across products,
landing pages, and channels) and the **CVR Signals** layer (Wilson confidence intervals,
two-proportion z-tests across segments, minimum-sessions significance gates, and
empirical-Bayes-shrunk page CVRs ranked by Wilson lower bound).

## Data paths (gate — resolve this first)

Two input paths feed the machine layer; they **legitimately combine**, and
`scripts/machine.py` owns the per-field precedence (never adjudicate sources yourself):

- **Shopify MCP available?** Run the ShopifyQL pulls in `references/shopify-pulls.md` and save
  every tool result **verbatim** to the exact `--raw-dir` filenames it specifies. This covers the
  funnel, device/referrer/landing splits, product revenue, totals + AOV, and customers — plus
  `get-shop-info` for currency and store identity.
- **CSV exports?** Walk the user through the GA4 + Shopify Analytics exports in
  `references/data-intake.md` and save them under its canonical `--csv-dir` filenames. GA4 is
  **CSV-only** (no GA4 MCP exists) and is the *only* source for new-vs-returning session CVR and
  the depth source for device/channels/landing pages.
- **Both?** Pass both `--raw-dir` and `--csv-dir` — the machine layer applies its documented
  per-field precedence (e.g. `shopify-conversion.csv` beats `analytics_funnel.json` beats
  `ga4-funnel.csv` for the funnel; GA4 beats MCP for device/channels/landing; Shopify beats GA4
  for revenue/AOV) and notes any >10% cross-source divergence honestly.

> **NEEDS-REAL-EXPORT-VALIDATION:** the CSV path is encoded from documented GA4/Shopify export
> headers and has **not yet been validated against real export files** — any mismatch fails loudly
> through the parser's wrong-report guard (`ManualCsvError`), and the path must be confirmed
> against genuine exports before it is trusted for client work. The Shopify MCP path **is**
> validated against live captured results.

**Build only what the data can actually measure.** Any step without sufficient data is **declared
`not_run` (or `partial`) on the Audit Scope tab — never fabricated.** The most powerful findings
are **triangulated**: the same problem appearing in analytics + behavior + customer voice.

## When to use
- "Audit my Shopify store / run a CRO audit / conversion audit", "where's my funnel leaking?",
  "11-step CRO audit", "review my store for conversions".
- A client engagement that needs a defensible CRO roadmap with a shareable report.

## When NOT to use
- Ad-account audits → use `google-ads-audit` / `meta-ads-audit`.
- Per-product profitability → use `cm3-by-product-report`.
- Editing the live store — this skill is **read-only analysis**; it never mutates the store.

## Critical guidelines
- You MUST run the machine layer **FIRST** (`build_cro_audit.py --machine-only`) before writing
  any analytics numbers, and you MUST transcribe **only the fields it reports as `skipped`** —
  the final build recomputes the whole `analytics` block and **replaces your values regardless**,
  logging every correction (stderr `machine: analytics.funnel.atc_rate 6.20->6.10
  (shopify-conversion.csv)`; `machine_corrections` in the final JSON line; an Overview line in
  every format).
- You MUST save the Shopify MCP pulls **verbatim** to the exact filenames in
  `references/shopify-pulls.md` — they are the only source of the machine analytics,
  Concentration, and CVR Signals numbers (metric values never pass through the model). Do not
  retype, trim, or reformat rows; do not "fix" fraction-valued PERCENT columns.
- You MUST mark any step without sufficient data as `not_run` (or `partial`) in `meta.steps[]`
  and never invent reviews, survey responses, heatmap data, or competitors.
- You MUST prioritize with **`(Impact × 2) + Ease`** (1–10 each). Do **NOT** use ICE — the
  framework drops Confidence on purpose.
- You MUST drive every threshold and benchmark from `references/benchmarks.md` and every
  step→source mapping from `references/audit-framework.md`; ask for data exactly as
  `references/data-intake.md` specifies.
- You MUST build with `scripts/build_cro_audit.py` (it owns the filenames and runs the workbook
  `--check` gate automatically) and ask the user **where to save** the bundle at runtime.

## Required tooling
- **Shopify MCP (optional but preferred):** `run-analytics-query` (ShopifyQL),
  `get-shop-info`; optional `list-orders` / `search_products` for context pulls.
- **WebFetch** — storefront + top landing page (Step 2 heuristic) and competitor URLs (Step 10).
  Degrade to auditor notes if a URL isn't provided or a fetch fails.
- **Python 3** (stdlib) for md/html; **openpyxl ≥ 3.1** only for the xlsx backup
  (`python3 -m pip install -r "${CLAUDE_PLUGIN_ROOT}/requirements.txt"`).

## Workflow

To use the skill, work through these steps in order.

1. **Gate: resolve the data paths.** Check whether the Shopify MCP is connected (a quick
   `get-shop-info` proves it). Glob the working folder for provided exports (`ga4-*.csv`,
   `shopify-*.csv`, `reviews*.csv`, `fairing*.csv`/`kno*.csv`, `typeform*.csv`). Decide: MCP path,
   CSV path, or both (see **Data paths** above).

2. **Prompt for the data (verbatim, only what's missing).** Always secure **Tier 1** first (the
   Step-1 sources) — the audit weights Impact by traffic, so Step 1 is the foundation. Use the
   exact prompts, export paths, and canonical filenames in `references/data-intake.md`. Then ask
   for the store + competitor URLs, and offer each Tier 3 per-step export. Persist a
   `cro-audit-inputs.json` manifest of what was provided so the run is re-runnable. For anything
   the user can't provide, tell them it will be marked "Not run" and what to collect next.

3. **MCP path: pull and save verbatim.** Run the ShopifyQL pulls in
   `references/shopify-pulls.md` (exact queries) plus `get-shop-info`, and write each complete,
   unedited tool-result JSON to a working directory under the canonical `--raw-dir` filenames
   (`shop_info.json`, `analytics_funnel.json`, …). A malformed or error-shaped file fails loudly
   with a `RawResultError` pointing back at that doc.

4. **Run the machine layer FIRST.** Before writing a single analytics number:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/shopify-cro-audit/scripts/build_cro_audit.py" \
     --machine-only --raw-dir "<workdir>" --csv-dir "<exports-folder>"
   ```
   (either input flag alone is fine; works without `--input`.) It prints a JSON object with
   `machine` (the computed analytics fields + machine Read verdicts + sources),
   `cvr_signals`, and `concentration`. Copy the machine analytics as-is into your payload —
   or simply leave `analytics` sparse; the final build injects and enforces the machine values
   regardless. Transcribe **only** the fields listed under `skipped` (each names its missing
   input), from the user's remaining exports.

5. **Steps 3, 6, 7 — customer voice from exports.** Analyze the reviews / post-purchase /
   email-survey CSVs. Categorize and **quantify** themes; extract objections, drivers, verbatim
   voice, near-abandonment factors, and the survey-vs-GA4 attribution gap.

6. **Steps 2 & 10 — WebFetch the store + competitors.** WebFetch the store + top landing page;
   evaluate every funnel page against the six **LIFT** factors (value prop, relevance, clarity,
   urgency, anxiety, distraction) mobile-first. WebFetch competitors; build the offer/pricing
   table, above-the-fold comparison, and messaging gaps. If no URL, fall back to auditor notes
   and mark `partial`. These steps are LLM-judged by design — the machine layer never touches
   them.

7. **Steps 4, 5, 8, 9 — auditor-supplied.** Use the support questionnaire answers, heatmap
   observations, user-testing notes, and marketing inputs the user provided. If a step has none,
   mark it `not_run` with a one-line "collect next" reason.

8. **Assemble findings + payload.** Turn every notable observation into a `findings[]` entry with
   **all** applicable `step_sources` (drives the live triangulation count), `severity`, `page`,
   `evidence`, `recommendation`, `impact` (1–10, weighted by page traffic + triangulation),
   `ease` (1–10), `change_type` (Test/Ship), `expected_lever`. Build the payload per the schema
   below (mirror `tests/sample-payload.json`).

9. **Build the deliverable bundle.** Ask the user **where to save** the report (suggest
   `~/Downloads` as a sensible default), then build all three formats to that directory:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/shopify-cro-audit/scripts/build_cro_audit.py" \
     --input cro-payload.json --outdir "<user-chosen-dir>" --brand "{Client Name}" \
     --raw-dir "<workdir>" --csv-dir "<exports-folder>"
   ```
   The tool owns the filenames (`cro-audit_{slug}_{date}.{md,html,xlsx}`), runs the workbook's
   `--check` gate automatically, **copies the bundle to `~/Downloads`** in addition to the chosen
   outdir, and prints the paths (the last stdout line is a JSON object with
   `outputs`/`health`/`grade`/`findings`/`machine_corrections`). Flags: `--formats md,html`
   skips the xlsx (md/html need no openpyxl); `--no-animate` builds motion-free HTML;
   `--no-downloads` skips the Downloads copy; explicit per-file `--csv-*`/`--raw-*` flags
   replace the directory flags (see `--help`); `--no-machine` skips the machine layer (not
   recommended). `--raw-dir` and `--csv-dir` are **not** mutually exclusive — they combine under
   the machine layer's per-field precedence. Omit the data files entirely and the bundle still
   builds, just without machine analytics / Concentration / CVR Signals.

   **The machine layer runs automatically at build time** whenever raw/csv inputs are given: the
   whole `analytics` block is recomputed in Python and **enforced over the payload** — any
   disagreement with your drafted values is corrected and logged to stderr, and the final JSON
   line reports `machine_corrections`. Your `steps_detail`, `findings`, and `meta` (except a
   blank-currency fill) are always preserved.

10. **Surface results.** Point the user at the **`.html`** (the primary client-shareable
    deliverable) with its clickable path, and report the Funnel Health score + grade and the top
    3–5 roadmap items (quick wins first, with Test/Ship). Note the report is interactive: a tab
    per step, and on the Findings tab the user adjusts Impact/Ease to re-rank by
    `(Impact×2)+Ease` live. The `.md` is the readable/vault record; the `.xlsx` is the editable
    backup (override a rate or an Impact/Ease cell and it recalculates on open). Close with an
    explicit **"Not run (data not provided): …"** list.

## Payload schema

The builders read this exact shape (keys are stable; `tests/sample-payload.json` is a complete
worked example and a valid `--input`):

```jsonc
{
  "meta": {
    "store_name": "...", "store_url": "https://...", "currency": "USD",
    "date_range": "...", "generated_for_date": "YYYY-MM-DD", "auditor": "...",
    "data_inventory": [ { "dataset": "...", "status": "provided|missing", "notes": "..." } ],
    "steps": [ { "step": 1, "name": "...", "status": "run|partial|not_run", "reason": "..." } ]  // all 11
  },
  "analytics": {                                   // Step 1 — MACHINE-COMPUTED at build time.
    // The build recomputes every field below from --raw-dir/--csv-dir and REPLACES what you
    // wrote (corrections logged). Hand-fill ONLY fields the machine reported as `skipped`.
    // Rates are PERCENT values (6.1 = 6.1%).
    "funnel": { "sessions": 0, "atc": 0, "checkout": 0, "purchases": 0,
                "atc_rate": 0.0, "checkout_rate": 0.0, "cvr": 0.0 },   // rates = % of sessions
    "device": [ { "device": "Mobile", "sessions": 0, "cvr": 0.0 } ],
    "channels": [ { "channel": "...", "sessions": 0, "cvr": 0.0, "revenue": 0 } ],
    "landing_pages": [ { "page": "/...", "sessions": 0, "share_pct": 0.0 } ],
    "revenue_concentration": [ { "product": "...", "revenue": 0, "share_pct": 0.0 } ],
    "new_vs_returning": { "new_cvr": 0.0, "returning_cvr": 0.0 }, "aov": 0.0
  },
  "steps_detail": {
    "heuristic": { "findings": [ { "page": "...", "lift_factor": "...", "severity": "...",
                                   "observed": "...", "recommendation": "..." } ] },
    "review_mining": { "themes": [ { "theme": "...", "pct": 0 } ],
                       "objections": ["..."], "drivers": ["..."], "voice": ["..."] },
    "support": { "rows": [ { "question_or_complaint": "...", "category": "...", "site_gap": "..." } ] },
    "heatmaps": { "rows": [ { "page": "...", "device": "...", "metric": "...", "observation": "..." } ] },
    "post_purchase_survey": { "near_abandonment": ["..."], "triggers": ["..."],
                              "attribution": [ { "channel": "...", "survey_pct": 0, "ga4_pct": 0, "note": "..." } ] },
    "email_survey": { "rows": [ { "insight_type": "...", "finding": "...", "pct_or_n": "..." } ] },
    "user_testing": { "rows": [ { "tester_or_theme": "...", "quote": "...", "issue": "..." } ] },
    "marketing": { "rows": [ { "area": "...", "observed": "...", "gap": "..." } ] },
    "competitor": { "offer_table": { "columns": ["..."], "rows": [["..."]] },
                    "atf": { "columns": ["..."], "rows": [["..."]] }, "messaging_gaps": ["..."] }
  },
  "findings": [
    { "id": "F-001", "title": "...", "step_sources": ["Analytics","Heuristic"],
      "severity": "Critical|High|Medium|Low", "page": "...", "evidence": "...", "recommendation": "...",
      "impact": 9, "ease": 8, "change_type": "Test|Ship", "expected_lever": "..." }
    // impact/ease optional — defaults: impact from severity (9/7/5/3), ease 5;
    // priority = Impact×2 + Ease buckets the roadmap (Now ≥24 / Next ≥20 / Soon ≥15 / Later)
  ]
}
```

**Concentration and CVR Signals are NOT part of this JSON.** They derive exclusively from the
saved raw pulls / CSV exports passed via `--raw-dir`/`--csv-dir` — never from the payload — so
their row-level numbers never pass through the model.

## Scoring (unchanged from the framework)

- **Funnel Health (0–150):** `MIN(150, 100 × mean(rate / benchmark))` over the **measured stages
  only** (ATC rate vs 7.23, checkout rate vs 5.96, CVR vs 2.99 — blank stages are excluded from
  the mean, never zero-filled), rounded half-up to an integer. Grades on the rounded score:
  **A ≥ 110, B ≥ 90, C ≥ 70, D ≥ 50, F < 50**. Identical in Python, the HTML report's live JS,
  and the workbook formulas.
- **Priority = (Impact × 2) + Ease** (1–10 each; no Confidence). Buckets: **Now ≥ 24,
  Next ≥ 20, Soon ≥ 15, Later < 15**.
- Benchmarks, severity weights, and AOV bands live in `references/benchmarks.md`.

## CVR Signals (computed from the data files)

Rate-significance statistics over sessions/conversions — the honest answer to "is mobile really
worse?" and "which pages are actually underperforming?":

- **Site block:** sessions, conversions, CVR with a **Wilson 95% CI**, and the minimum sessions
  per segment (`n*`) needed for significance at the site CVR.
- **Segments:** device / channels / new-vs-returning rows with **two-proportion z-tests** against
  the complement of sibling rows from the **same source** (never cross-source); |z| ≥ 1.96 gets a
  significance pill. The headline device z (Mobile vs Desktop) is called out.
- **Pages:** top 25 by sessions with raw CVR, **empirical-Bayes-shrunk CVR** (prior = site CVR,
  k = median sessions/page), **Wilson lower bound** (the ranking key), and a `gated` flag for
  pages below `n*` — full-universe math happens before the top-25 cut.
- **Derived-counts honesty:** when an export ships only rates, conversions are derived
  (`floor(sessions × cvr + 0.5)`), flagged `derived: true`, and noted.

Surfaces: an HTML panel, a `## CVR Signals` md section, and the values-only `16_CVR_Signals`
xlsx tab.

## Concentration (computed from the data files)

HHI, Effective-N, Gini (with Lorenz curves), and crossing-inclusive Pareto-ABC across three
dimensions: **products** (revenue / orders), **landing pages** (sessions / derived conversions),
and **channels** (sessions / revenue or derived conversions). Small dimensions (< 8 entities)
are reported without verdicts. Surfaces: an HTML panel, a md section, and the values-only
`15_Concentration` xlsx tab.

## Data-accuracy rules (prevent wrong findings)
- **AOV is verbatim, never recomputed.** Shopify's `average_order_value` is neither
  `total_sales/orders` nor `net_sales/orders` (validated live) — the toolchain takes the column
  as-is, and so must any narrative.
- **Never mix funnel stages across sources** — the funnel is single-source by precedence; the
  GA4 funnel counts **users**, not sessions (the build notes the basis when it falls back).
- **ShopifyQL PERCENT columns are fractions** (0.0198 = 1.98%) — the parsers own the conversion;
  never "fix" a saved file or multiply by 100 yourself.
- **`summaryMetric` sums only the returned rows**, not the universe — LIMIT-truncated GROUP BY
  results carry an honest tail-gap note.
- **New-vs-returning session CVR comes only from GA4**; Shopify's `returning_customer_rate` is
  an order-share (evidence, not a CVR).
- Landing-page URLs are normalized (lowercase, strip `?query`, strip trailing `/`) and merged
  before any math; shares are computed against the **full universe**, not the embedded top-25.
- Tablet/other device rows have **no benchmark** — they get no Read verdict, only evidence.
- Every window label comes from the data (`SINCE -90d UNTIL today` on the MCP path; the export's
  own date range on the CSV path) — never present a metric as covering a window the underlying
  file does not.

## Bundled resources (load as needed)
- `references/shopify-pulls.md` — the exact ShopifyQL pulls + `get-shop-info` (queries,
  canonical `--raw-dir` filenames, save-verbatim doctrine, envelope shape quirks, and which file
  unlocks which analytics field / signal).
- `references/data-intake.md` — **the intake spec**: per dataset, exact export path + required
  columns + verbatim prompts + the canonical `--csv-dir` filenames table.
  **NEEDS-REAL-EXPORT-VALIDATION** on the parsing path.
- `references/audit-framework.md` — the 11-step execution map: method, what to extract, payload
  key, tab.
- `references/benchmarks.md` — funnel/device/AOV benchmarks, severity, Funnel Health,
  `(Impact×2)+Ease`.
- `scripts/build_cro_audit.py` — the entry point: machine layer + md + interactive HTML + xlsx
  to `--outdir` (+ a `~/Downloads` copy). `--help` for usage; `--machine-only` for step 4.
- `scripts/audit_model.py` — canonical scoring constants + `compute_model()` (single source for
  all three formats).
- `scripts/machine.py` — the deterministic analytics assembler: computes the Step-1 block from
  the data files and enforces it over the payload at build time (replace + log).
- `scripts/shopify_rows.py` — the Shopify MCP raw-pull parser (transcription firewall): ShopifyQL
  envelope coercion + adapters shared by every downstream consumer.
- `scripts/manual_csv.py` — the GA4 / Shopify UI-export parser for the CSV path (same firewall,
  same downstream pipeline). **NEEDS-REAL-EXPORT-VALIDATION.**
- `scripts/cvr_signals.py` — Wilson / z-test / EB-shrinkage rate-significance layer (stdlib).
- `scripts/concentration.py` — HHI/Effective-N/Gini/Lorenz/ABC across products, landing pages,
  channels.
- `scripts/audit_html.py` — the self-contained interactive HTML report (GSAP, white-label,
  theme-aware, 0–150 gauge).
- `scripts/audit_md.py` — the Obsidian-ready markdown record.
- `scripts/build_cro_workbook.py` — the xlsx backend (openpyxl ≥ 3.1; `--input`/`--output`,
  `--check`).
- `tests/sample-payload.json` — a complete reference payload; a valid `--input` and a smoke test.
- `tests/test_audit.py` — conformance tests (scoring parity, self-containment, determinism).

## Output contract
- Three files, one stem: `cro-audit_<slug>_<YYYY-MM-DD>.{html,md,xlsx}` in the user-chosen
  outdir, plus a copy of each in `~/Downloads`.
- **HTML** — the primary client-shareable deliverable: self-contained (no external requests),
  white-label, live 0–150 Funnel Health gauge, a tab per step with evidence tables and
  run/partial/not-run banners, the Step-1 funnel KPI table with machine Read verdicts,
  Concentration + CVR Signals panels, findings with live `(Impact×2)+Ease` re-ranking, and a
  machine-layer summary line ("N fields machine-computed · M corrections").
- **md** — Obsidian-ready record with the same sections.
- **xlsx** — the editable backup: `00_Audit_Scope` … `14_Reference` (15 tabs with live formulas —
  override a rate, Impact, Ease, or benchmark and it recalculates on open; editable input cells
  are highlighted) plus values-only `15_Concentration` / `16_CVR_Signals` when data files were
  provided.
- A chat summary: Funnel Health + grade, top priorities, per-analysis one-liners, and the
  Not-run list.

## Troubleshooting
- **Raw file won't parse / `RawResultError`** → the error names the file and points at
  `references/shopify-pulls.md` — re-save the tool result verbatim. An error-shaped result
  (empty columns/rows + error prose) means the query itself failed; fix the query, don't edit
  the file.
- **`ManualCsvError: wrong report`** → the export's headers don't match the canonical file's
  required columns — re-export per `references/data-intake.md` (this is the
  NEEDS-REAL-EXPORT-VALIDATION guard doing its job).
- **`ManualCsvError` on a >20% site CVR** → a percent value leaked through as a fraction
  (mis-scaled units); re-check the export rather than overriding.
- **Machine `skipped` a field** → the entry names the missing input; pull or export it per the
  referenced doc, or hand-fill just that field.
- **No store/competitor URL** → run Step 2/10 from auditor notes; mark `partial`; don't invent.
- **Sparse data on a step** → `partial` (note what's thin) or `not_run` (note what to collect).
- **GA4 export has preamble/comment rows** → expected; the parser skips `#`-comment preambles
  and stops at the blank line before GA4's second (day-by-day) section.
- **openpyxl missing / PEP 668 error** → md/html still build; for the xlsx:
  `python3 -m pip install --user --break-system-packages openpyxl`.
- **`--check` reports a missing named range or `#REF!`** → regenerate from the payload; do not
  hand-edit the workbook before delivery.

---
Framework: an 11-step CRO audit checklist for ecommerce.
Authored by Clickt Digital Marketing Inc. — Marketer Hive Mind.
