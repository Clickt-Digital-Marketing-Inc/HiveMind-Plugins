---
name: google-ads-quality-score
description: Use when Google Ads Quality Score is low or dropping (below 5), CPCs are rising, or you need a forensic Quality Score audit. Runs the 6-step diagnosis (search-term CTR, device split, ad relevance keyword-to-headline matrix, low-CTR keyword pause, A/B test setup) over live MCP data, flags the landing-page-experience checks that must be done manually, and outputs fixes with a remediation timeline.
---

# Google Ads — Quality Score Forensics

## Bundled path resolution

Before running bundled scripts, set `PLUGIN_ROOT` to the absolute path of this plugin directory: the nearest ancestor of this `SKILL.md` that contains either `.claude-plugin/plugin.json` or `.codex-plugin/plugin.json`. Resolve it from the loaded skill path; do not assume a host-specific environment variable or the current working directory. Then run commands that reference `${PLUGIN_ROOT}` unchanged.

Quality Score drives CPC and Ad Rank — it is not a vanity metric. When it drops below 5, diagnose
systematically across its three components (Expected CTR, Ad relevance, Landing page experience)
rather than applying generic tips.

**Cadence:** monitor QS **weekly**; run the full 6-step forensic when an ad group's QS is ≤ 4–5.

**REQUIRED BACKGROUND:** load `google-ads-foundation` first.

## When to use
- "Quality Score dropped", "my CPCs went up", "low quality score".
- Weekly QS check; before/after big ad or keyword changes.

## Pull the data — MCP or CSV (dual input)

**Step 0 — pick the input path before pulling anything**, per `google-ads-foundation/references/
artifact-formats.md` "Dual input": MCP reachable → live pull (default). MCP unreachable
(`login-customer-id` not set, etc.) or the user already has an export → ask for the Google Ads UI
**Keywords** export (add the Quality Score / Landing page exp. / Ad relevance / Expected CTR
columns) and run `scripts/assemble_findings_csv.py` instead of the pulls below — see
[references/quality-score-report.md](references/quality-score-report.md) "Dual input" for the
exact ask and command. Both paths yield an identical model; `meta.source` is surfaced honestly in
every artifact.

**MCP path:**
1. **Keywords + QS triad (30d)** — `keyword_view` with `quality_info.quality_score`,
   `creative_quality_score`, `post_click_quality_score`, `search_predicted_ctr`, plus CTR/impr.
2. **Search terms (30d)** — `search_term_view` for low-CTR drag (step 1).
3. **Device split** — add `segments.device` to the `keyword_view` query (step 2).
4. **Ads / RSA assets** — `ad_group_ad` with `responsive_search_ad.headlines/descriptions` and
   `ad_strength` (step 4 matrix).

> **Numbers never pass through the model.** Save every pull's raw result to a file (auto-saved
> `tool-results/*.txt` for big pulls; verbatim copy of the whole `{"result": [...]}` JSON for
> inline ones) and build the findings JSON with
> [scripts/assemble_findings.py](scripts/assemble_findings.py) — never type metrics into a JSON by
> hand. The assembler embeds reconciliation control totals that the core re-verifies on every
> build; hand-assembled or edited findings hard-fail. See the reference doc's "Transcription
> firewall" section for the exact command.

## Diagnose — the 6-step audit
Per [benchmarks](google-ads-foundation/references/benchmarks-2026.md) "Quality Score forensics":

1. **Expected-CTR drag:** search terms / keywords with CTR < 2% and ≥ 50 impressions.
2. **Device:** if mobile CTR < 1.5% and mobile dominates impressions → mobile is dragging QS.
3. **Landing page experience (MANUAL):** the QS component `post_click_quality_score` shows
   BELOW_AVERAGE, but Core Web Vitals / page speed are **not** in this MCP. Direct the user to
   Search Console → Page Experience / PageSpeed (LCP > 2.5s, CLS > 0.1, slow TTFB). Flag, don't fake.
4. **Ad relevance matrix:** map each keyword to its ad group's RSA headlines. If < 80% of keywords
   appear (as exact phrase) in at least one headline → ad relevance is the issue.
5. **Low-CTR keywords:** impressions > 100, CTR < 1%, 0 conversions → pause.
6. **A/B test (if 1–5 inconclusive):** 3 RSA variants, rotate evenly 14 days / 100+ impr each,
   compare CTR + CVR, pause loser, scale winner. Repeat monthly.

Use the QS triad to localize the root cause: BELOW_AVERAGE Expected CTR → steps 1/2/5;
Ad relevance → step 4; Landing page → step 3.

## Recommend (Critical → High → Medium)

Lead with the **dominant-QS-factor finding** — which component (Expected CTR / Ad relevance /
Landing page) drags the account most, and where it concentrates (model numbers: `dominant_factor`
in the model, the first card in the HTML explorer, the first section in the md/xlsx) — then the
deepened RSA-rewrite recommendations (`*_rsa_rewrites.md`, citing per-ad-group cost/keywords),
then:
- **Critical:** pause the step-5 keywords (low CTR, 0 conv) — they drag Expected CTR with no upside.
- **High:** rewrite RSAs so headlines contain the ad group's exact keyword phrases (step 4,
  `scripts/build_rsa_rewrites.py`); cut mobile bid adjustment 30–50% or fix the mobile LP (step 2).
- **Medium:** restructure broad ad groups into tighter themes (route to
  `google-ads-keywords-search-terms`); set up the step-6 A/B test.

Follow the [advisor loop](references/quality-score-report.md#the-advisor-loop) — emit → report
(dominant factor first) → recommend → offer the apply-CSVs — per `google-ads-foundation/
references/artifact-formats.md`'s advisor output contract.

**Remediation timeline (tell the user):** days 1–7 no visible change, 8–14 begins, 15–30 full
recovery. No recovery by day 30 → root cause is landing page or ad relevance, not Expected CTR.

## Generate artifacts (in `artifacts/`)
**Analytical deliverable** — the standard three-format bundle, all rendered by the shared
`_shared/render` toolkit from one model (`scripts/qs_core.py`), bucketing every keyword by its
**primary failing QS component**. Build from a findings JSON (schema + the GAQL pull are
authoritative in [references/quality-score-report.md](references/quality-score-report.md)):

```bash
python3 "${PLUGIN_ROOT}/skills/google-ads-quality-score/scripts/build_qs_report.py" --input findings.json --outdir artifacts \
  --brand "{Client Name}" --formats md,html,xlsx
```
- `*.md` — headline KPIs (avg QS, in-scope, component split, pause candidates, **dominant QS
  factor**), a dominant-QS-factor concentration section (by component, then where it concentrates
  by ad group) leading the section list, a section per failing component (Landing page / Ad
  relevance / Expected CTR / Critical / Other) with its fix, the pause-candidate list, QS-threshold
  sensitivity, the manual-LP reminder, and a **full per-keyword table** with the triad ratings +
  bucket + pause flag (no row loss; unscored kept separate).
- `*_explorer.html` — interactive: **QS-low slider**, a **component-target dropdown**, and pause
  thresholds; live bucket counts, a live pause list, a live "Dominant QS factor" card (leads the
  extra panel), sortable keyword table. Self-contained.
- `*.xlsx` — Controls (QS-low / target / pause → live bucket counts **and** live below-target
  drag-cost + dominant-factor + share formulas) · Keywords (every keyword + Status; scored rows
  carry the primary-bottleneck Bucket formula + Pause flag) · Snapshot (incl. the dominant-factor
  detail tables).
- `*_charts/*.svg` — deterministic Vega-Lite charts (spend-by-bucket bar, QS-distribution
  histogram) rendered at build time and referenced from the md; the explorer renders the same
  charts live from the controls. `--no-charts` skips them.

> **Charts are generated, never authored.** Every chart is produced by `build_qs_report.py`
> through the shared chart module from the spec's `SPEC["charts"]` declaration. Never hand-write
> or edit SVG, Vega-Lite JSON, chart HTML, or the vendored JS; never "fix" a chart in the output
> file. If a chart is wrong, the spec or the model is wrong — change it there and re-run the
> builder. Same run, same chart, byte for byte.

**Forensic apply-files** (Google Ads Editor; applied manually — MCP is read-only) via
`${PLUGIN_ROOT}/skills/google-ads-foundation/scripts/make_editor_csv.py`:
- `pause_list` CSV — step-5 low-CTR keywords (the bundle's pause candidates).
- `bid_adjustments` CSV — mobile bid-adjustment changes.
- `*_rsa_rewrites.md` — the deepened keyword↔headline worklist (`scripts/build_rsa_rewrites.py`,
  run after the bundle from the same findings.json): every below-target-Ad-relevance keyword,
  grouped by ad group and prioritized by spend, with headlines that must include the keyword phrases.

## Resources
- [references/quality-score-report.md](references/quality-score-report.md) — **authoritative** contract.
- [scripts/qs_core.py](scripts/qs_core.py) — single-source model/kernel (bucket classification +
  `dominant_factor` concentration, via `_shared/analytics.py`); mirrored in the spec's `js_kernel`
  and the xlsx Bucket/dominant-factor formulas.
- [scripts/qs_spec.py](scripts/qs_spec.py) / [scripts/qs_xlsx_spec.py](scripts/qs_xlsx_spec.py).
- [scripts/build_qs_report.py](scripts/build_qs_report.py) /
  [scripts/build_qs_workbook.py](scripts/build_qs_workbook.py) (`--check`).
- [scripts/build_rsa_rewrites.py](scripts/build_rsa_rewrites.py) — the RSA-rewrite advisor artifact.
- [scripts/assemble_findings.py](scripts/assemble_findings.py) (MCP path) /
  [scripts/assemble_findings_csv.py](scripts/assemble_findings_csv.py) (CSV path — dual input).
- [tests/test_qs.py](tests/test_qs.py) + [tests/sample-findings.json](tests/sample-findings.json);
  [tests/test_qs_csv.py](tests/test_qs_csv.py) (CSV path + MCP-vs-CSV identical-model assertion).

## Common mistakes / red flags
- **`quality_score` of 0/null = unscored** (too little data / not eligible), not a literal 0.
  Treat unscored keywords separately; don't average them in or "fix" them as if QS were zero.
- Don't prescribe generic "improve your ads" — name the failing **component** (Expected CTR /
  Ad relevance / Landing page) from the QS triad and fix that.
- Don't claim a landing-page diagnosis from MCP data — page speed/CWV are **manual**; flag them.
- The RSA-rewrite worklist is a **prescription grounded in the model**, not a live keyword↔headline
  diff — the MCP doesn't return current RSA headline text; cross-reference against the ad group's
  live RSAs before publishing.
- The CSV path's `ad_group_id` is a stand-in (the ad group name) — honest and functionally
  equivalent for dedupe/grouping, but not the account's internal id; don't present it as one.
- QS is a trailing indicator — don't declare failure before 30 days post-fix.
- Pausing keywords and editing RSAs is **manual** (read-only MCP) — deliver the artifacts.
