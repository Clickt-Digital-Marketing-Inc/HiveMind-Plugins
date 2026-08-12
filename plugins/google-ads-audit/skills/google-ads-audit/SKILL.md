---
name: google-ads-audit
description: Use when a user asks to audit a Google Ads account, run a PPC or Google Ads audit, review account health, or hunt wasted spend, impression-share loss, Quality Score, negative-keyword, conversion-tracking, or bidding problems. Drives the Google Ads MCP (GAQL) to pull live data, scores it against a comprehensive 9-step audit framework plus modern Google checks (PMax, Consent Mode v2, Enhanced Conversions, Demand Gen), and produces a formula-driven xlsx audit workbook.
---

# Google Ads Audit

## Bundled path resolution

Before running bundled scripts, set `PLUGIN_ROOT` to the absolute path of this plugin directory: the nearest ancestor of this `SKILL.md` that contains either `.claude-plugin/plugin.json` or `.codex-plugin/plugin.json`. Resolve it from the loaded skill path; do not assume a host-specific environment variable or the current working directory. Then run commands that reference `${PLUGIN_ROOT}` unchanged.

## Overview

Conduct a full Google Ads account audit by pulling live data through the
`google-ads-mcp` server, evaluating it against a **comprehensive 9-step audit framework**
plus modern Google-specific checks, and emitting a **3-format deliverable bundle** from
one findings JSON: an **interactive, self-contained HTML report (the primary deliverable
— shareable by email or Netlify, white-label, with a live Health-Score gauge and ICE
re-ranking)**, an Obsidian-ready **markdown** record, and a **formula-driven .xlsx**
backup. All three compute the same weighted Health Score, ICE prioritization, and client
summary — this skill's job is to gather accurate data, judge each check
(PASS / FLAG / FAIL / N/A), and assemble the findings JSON the builders consume.

> **No MCP? The audit still runs.** If `google-ads-mcp` is not connected, walk the user
> through the three UI exports in `references/manual-exports.md` and build with `--csv-dir`.
> The manual path fully powers Concentration plus the structure/performance/keyword/budget
> checks; sections the exports can't cover are marked N/A — "Not available from manual
> export" — never approximated.

The nine areas: (1) account structure, (2) performance review, (3) keyword strategy,
(4) ad creatives & assets, (5) landing pages, (6) budget & bidding, (7) tracking &
measurement, (8) audiences, (9) scripts/recommendations/automation.

## When to use
- "Audit my Google Ads account", "run a PPC audit", "Google Ads health check".
- Diagnosing wasted spend, low impression share, Quality Score, weak structure,
  tracking gaps, or bidding fit.
- Taking over a new account (use a 3–6 month lookback) or a quarterly review.

## When NOT to use
- Meta/LinkedIn/TikTok/Microsoft audits (different platforms).
- Making changes to the account — this skill is **read-only analysis**; it never
  mutates campaigns.
- Landing-page health (404s/speed) and account Scripts content: not queryable via
  GAQL — flag these as manual review (mark N/A with a note).

## Workflow

To use the skill, work through these steps in order.

1. **Resolve the account — or gate to the manual path.** Call
   `customers_list_accessible_customers`. If the MCP is unavailable or errors, switch to
   the **manual-export path**: follow `references/manual-exports.md` (three UI CSV
   downloads), judge only what those exports evidence, mark the rest N/A, and pass the
   files via `--csv-dir` in step 6 — then skip steps 2–3. With the MCP present: if more
   than one customer is returned, ask the user which `customer_id` to audit, and pull
   account meta (`customer` resource) for currency, time zone, and conversion-tracking
   status.

2. **Set the lookback window.** Default **LAST_90_DAYS** for trend/structure and
   **LAST_30_DAYS** for `search_term_view` (GAQL rejects 90-day search terms). For a
   brand-new-account takeover, offer 3–6 months. Confirm the window with the user if
   ambiguous, then record both ranges in the findings `meta`.

3. **Pull data section by section.** Follow the recipes in
   `references/gaql-queries.md` — one block per audit step, giving the GAQL
   `resource`, `fields`, and `conditions` for each `search_search` call. **Before
   querying any field you are unsure about, verify it with
   `metadata_get_resource_metadata` — never guess field names.** Record each pull in
   `data_inventory`.

   **Save three pulls verbatim for the Concentration report.** Write the complete,
   unedited `search_search` result JSON (`{"result":[...]}`) of the Step-2 campaign
   pull, the Step-3 keyword pull, and the Step-3 search-terms pull to
   `campaigns.json`, `keywords.json`, and `search_terms.json` in a working directory.
   These files are the **only** source of the concentration numbers — they are parsed
   deterministically by `scripts/concentration.py`, so metric values never pass
   through the model. Do not retype, trim, or reformat rows.

4. **Run the pre-scorer FIRST, then evaluate the judgment checks.** The mechanical
   checks are machine-scored — get their results before judging anything:
   ```bash
   python3 "${PLUGIN_ROOT}/skills/google-ads-audit/scripts/build_audit.py" \
     --prescore-only --raw-dir "<workdir>/raw" --business-model "{Lead Gen|Ecommerce}"
   ```
   (`--csv-dir` on the manual path.) The JSON lists machine-scored `checks`
   (copy them as-is — the final build enforces them regardless), `evidence` for
   judgment checks, deterministic `kpis`, and `skipped` items that fall back to
   your judgment. Then score every remaining check in
   `references/audit-framework.md` as PASS / FLAG / FAIL / N/A with severity
   (Critical / High / Medium / Low), comparing KPIs against
   `references/benchmarks.md` and preferring the account's own baseline. Put the
   actual observed number or evidence in each check's `observed` field, and use
   the framework's **canonical check IDs** — the build matches machine results
   by ID.

5. **Assemble the findings JSON.** Build the object below. Turn every FAIL and
   material FLAG into a `findings[]` row with a 30/60/90 horizon.

6. **Build the deliverable bundle.** Ask the user **where to save** the report, then build
   all three formats to that directory. Suggest a sensible default: if the HiveMind bundle
   is installed, run its `resolve_vault.py` and propose the vault; otherwise propose
   `~/Downloads`. Let the user confirm or override, then:
   ```bash
   python3 "${PLUGIN_ROOT}/skills/google-ads-audit/scripts/build_audit.py" \
     --input findings.json --outdir "<user-chosen-dir>" --brand "{Client Name}" \
     --raw-dir "<working-dir-with-the-three-saved-pulls>"
   ```
   The tool owns the filenames (`ads-audit_{slug}_{date}.{html,md,xlsx}`), runs the
   workbook's `--check` gate automatically, and prints the paths (the last stdout line is
   a JSON object with `html`/`md`/`xlsx`/`score`/`grade`; `score` and `grade` are `null`
   when no check returned a scoreable result — report that as **not scored**, never as
   0 or F). Flags: `--formats html,md`
   skips the xlsx; `--no-animate` builds motion-free HTML; `--recalc` additionally
   recalculates the xlsx in LibreOffice and fails the build unless it evaluates to the
   same Health Score as the model (needs `soffice` on PATH); `--raw-dir` (or the explicit
   `--raw-campaigns` / `--raw-keywords` / `--raw-search-terms`) feeds the saved raw pulls
   to the **Concentration** report — omit them and the bundle still builds, just without
   the Concentration tab/section. On the manual path use `--csv-dir` (or `--csv-campaigns`
   / `--csv-keywords` / `--csv-search-terms`) with the UI exports instead; `--raw-*` and
   `--csv-*` are mutually exclusive.

   **The deterministic pre-scorer runs automatically** whenever raw/csv inputs are
   given: mechanical checks (impression-share, wasted spend, duplicates, eCPC, …) and
   the KPI scorecard are recomputed in Python and **enforced over the findings JSON** —
   any disagreement with your drafted results is corrected and logged to stderr
   (`prescore: KW-02 PASS->FAIL (…)`), and the final JSON line reports
   `prescore_corrections`. Your `recommendation` text is always preserved.
   `--no-prescore` opts out (not recommended).

7. **Surface results.** Point the user at the **`.html`** (the primary deliverable) with its
   clickable path, and report the Health Score + grade and the top 3–5 quick wins
   (lowest-effort Critical/High findings). Note the report is interactive: a tab per audit
   area, and on the **Findings** tab the user adjusts Confidence/Ease to re-rank by ICE
   live. The `.md` is the readable/vault record; the `.xlsx` stays editable in Excel/Sheets
   (business-model switch on `01_Audit_Scope`, Confidence/Ease on `13_ICE_Prioritization`).

## Findings JSON schema

The builder reads this exact shape (keys are stable; see `scripts/example_findings.json`
for a complete worked example):

```json
{
  "meta": {"client_name","account_id","currency","timezone",
           "business_model": "Lead Gen | Ecommerce",
           "date_range","search_terms_range","auditor","audit_date"},
  "data_inventory": [{"pull","resource","rows","status","notes"}],
  "kpis":           [{"metric","value","unit","benchmark","flag","notes"}],
  "sections": [{"tab","title","checks": [
      {"id","name","verify","applies_to": "Lead Gen|Ecommerce|Both",
       "severity": "Critical|High|Medium|Low",
       "result": "PASS|FLAG|FAIL|N/A","observed","recommendation"}]}],
  "findings": [{"id","section","title",
                "severity","recommendation","effort",
                "horizon": "30|60|90","owner"}]
}
```

`sections[].tab` MUST be one of: `03_Account_Structure`, `04_Performance_Review`,
`05_Keyword_Strategy`, `06_Ad_Creatives_Assets`, `07_Landing_Pages`,
`08_Budget_Bidding`, `09_Tracking_Measurement`, `10_Audiences`,
`11_Automation_Recommendations`. `kpis` renders a scorecard on the Performance tab.

**Concentration is NOT part of this JSON.** The Concentration report (HHI /
Effective-N / Gini / Pareto-ABC across search terms, keywords, campaigns, and campaign
types) derives exclusively from the saved raw pull files passed via `--raw-dir` — never
from findings.json — so its row-level numbers never pass through the model.

## Data-accuracy rules (prevent wrong findings)
- Analyze **ENABLED** campaigns/ad groups only (except clutter checks).
- Dedupe keywords by `(ad_group_id, keyword_text, match_type)`.
- Only flag wasted spend on terms with **> $10 spend AND 0 conversions**.
- Count **shared/account-level negative lists** alongside campaign negatives before
  judging coverage.
- BROAD + Manual CPC = legacy BMM, not intentional broad match.
- Cost is in **micros** (÷1,000,000); impression-share/rate fields are **fractions**
  (×100 for %).

## Negative-keyword guidance
- Default to **Exact** `[keyword]` for specific irrelevant queries, **Phrase**
  `"keyword"` for irrelevant intent patterns.
- **Never** recommend Broad-match negatives unless explicitly justified (they block
  too widely).
- Recommend **shared negative lists** at account level (Informational, Job-seeker,
  Competitor, Free-intent), not just per-campaign negatives.

## Resources
- `references/gaql-queries.md` — GAQL `resource`/`fields`/`conditions` per audit step + gotchas.
- `references/audit-framework.md` — the check tables (IDs, thresholds, severity) + post-audit logic.
- `references/benchmarks.md` — KPI benchmarks, impression-share reading, ICE scoring.
- `scripts/build_audit.py` — the entry point: builds md + interactive HTML + xlsx to `--outdir`. `--help` for usage.
- `scripts/audit_model.py` — canonical scoring constants + `compute_model()` (single source for all three formats).
- `scripts/audit_html.py` — the self-contained interactive HTML report (GSAP, white-label, theme-aware).
- `scripts/audit_md.py` — the Obsidian-ready markdown record.
- `scripts/concentration.py` — raw-pull parser (transcription firewall) + HHI/Effective-N/Gini/Lorenz/ABC metrics for the Concentration report.
- `scripts/manual_csv.py` — Google Ads **UI export** parser for the no-MCP path (same firewall, same downstream pipeline).
- `scripts/prescore.py` — the deterministic pre-scorer: machine-scores the mechanical checks + KPI scorecard from the data files and enforces them at build time.
- `references/manual-exports.md` — the manual-path export recipe (which reports, which columns) + honesty rules.
- `scripts/generate_workbook.py` — builds/validates the 18-tab xlsx backup (openpyxl); `--check` gate. `--help` for usage.
- `scripts/example_findings.json` — a complete findings JSON example.
- `tests/test_audit.py` — conformance tests (score parity, self-containment, determinism).
