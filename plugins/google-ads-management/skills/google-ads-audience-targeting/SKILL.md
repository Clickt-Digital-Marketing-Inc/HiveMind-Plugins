---
name: google-ads-audience-targeting
description: Use when reviewing Google Ads audience targeting and remarketing, checking first-party data readiness (Customer Match, Enhanced Conversions, Consent Mode v2), or setting up Performance Max audience signals and brand exclusions. Scores every applied audience against its own campaign's other audiences (no bid adjustment, paused, zero conversions, wasted spend, high CPA, low CTR) into a weighted priority tier via the Google Ads MCP or a UI export, and reads first-party readiness gaps from a user-supplied checklist — this data is not in the API. Emits a reduced advisor bundle (markdown report + tunable xlsx) plus a bid-adjustments Editor CSV.
---

# Google Ads — Audience & Targeting

Reach high-value segments and stop over-serving the wrong users. In 2026 targeting precision
depends on first-party data (third-party cookies are gone), so this skill is part Google Ads,
part measurement-readiness.

**Cadence:** **monthly** review (audiences shift slower than bids/keywords).

**REQUIRED BACKGROUND:** load `google-ads-foundation` first — it documents the dual-input (MCP or
CSV) contract and the advisor output contract (emit -> report -> recommend -> offer-apply) this
skill follows.

## When to use
- "Set up remarketing", "review my audiences", "improve targeting".
- Planning Customer Match / first-party data activation.
- Adding audience signals or brand exclusions to Performance Max.

## Step 0 — pick the input path (per audience-foundation's dual-input contract)

Two independent datasets, each with its own path — decide **before** pulling anything:

1. **Applied audiences** (`ad_group_criterion`, type `USER_LIST`) — MCP by default; CSV (a Google
   Ads UI "Audiences" report export) only when the MCP is unavailable or the user already has the
   export. Never both for the same run.
2. **First-party readiness** (Customer Match / Enhanced Conversions / Consent Mode v2 / CMP) —
   **always CSV/manual**. This is API-blind (see `google-ads-foundation/references/
   artifact-formats.md`, "What the MCP cannot return") — never imply the API confirmed a match
   rate, list size, or configuration state. Ask the user to fill in the readiness template
   (Category / Item / Type / Status / Detail / Verified Date — see
   [references/audience-targeting-filter.md](references/audience-targeting-filter.md)) if they
   don't already have one; a report with no first-party data is still a valid, honest result (the
   report says so explicitly).

## Pull the data — three pulls, honest ad-group-level metrics

**`ad_group_criterion` exposes ZERO `metrics.*` fields** (metadata-confirmed live 2026-07-16 — a
single combined identity+metrics query against it, as this skill once documented, is rejected
outright by the API). Applied-audience identity and its performance metrics are therefore **two
separate pulls**, joined by `ad_group.id` in
[scripts/assemble_findings.py](scripts/assemble_findings.py):

1. **Applied-audience criteria (identity only, no metrics)** — `ad_group_criterion.CRITERIA_FIELDS`
   (`campaign.name`, `ad_group.name`, `ad_group.id`, `ad_group_criterion.type`,
   `.user_list.user_list`, `.bid_modifier`, `.status`, `.negative`), condition
   `ad_group_criterion.type = 'USER_LIST'`.
2. **Ad-group-level audience metrics** — `ad_group_audience_view.METRICS_FIELDS` (`ad_group.id`,
   `metrics.impressions`, `.clicks`, `.cost_micros`, `.conversions`) filtered by `segments.date`.
   This is the only Google Ads resource that carries metrics for USER_LIST performance, and its
   join grain is the **ad group**, not the individual list — `ad_group_criterion.user_list.user_list`
   does not resolve when joined onto this view in this MCP's GAQL implementation (verified live).
   Metrics pulled here are therefore **ad-group-level**: every USER_LIST criterion sharing an ad
   group shows the SAME cost/clicks/impressions/conversions — the API cannot attribute performance
   to one list among several on the same ad group. This limitation is labelled honestly throughout
   every artifact (see `metrics_granularity` below); it is never presented as per-list data.
3. **User-list names/types** — a third `user_list.USERLIST_FIELDS` query (GAQL cannot join
   `user_list.name`/`user_list.type` into pull 1). See
   [references/audience-targeting-filter.md](references/audience-targeting-filter.md) for the
   exact field lists (both pulled from the same constants `assemble_findings.py` uses — no
   duplicated field lists to drift).

A criterion whose ad group has no matching pull-2 row (no `ad_group_audience_view` activity in the
window) is **never dropped**: it carries `status = "manual"` and `"—"` metric values — the assembler
never fabricates a zero for a metric it didn't observe. This mirrors how this skill already treats
first-party-readiness gaps: represent by status, don't drop.

**Campaign types** — `campaign` structure query (to spot PMax campaigns needing signals/brand
exclusions, and brand Search campaigns to protect) — used conversationally, not scored
(authoritative constant: `CAMPAIGN_TYPE_FIELDS` in
[scripts/assemble_findings.py](scripts/assemble_findings.py)).

Note: remarketing list sizes, membership durations, Customer Match upload status/match rate,
Enhanced Conversions, and Consent Mode are **not** exposed by this MCP — always the first-party
CSV/manual path.

> **Numbers never pass through the model.** Save every pull's raw result to a file and build the
> findings JSON with [scripts/assemble_findings.py](scripts/assemble_findings.py) — never type
> metrics into a JSON by hand. The assembler embeds reconciliation control totals that the core
> re-verifies on every build; hand-assembled or edited findings hard-fail.

## Diagnose — priority scoring + first-party readiness

**Applied audiences** are scored (`_shared/analytics.signals` + `pre_score`) against **their own
campaign's other applied audiences from the same pull** — no separate benchmark query:

| Signal | Fires when |
|---|---|
| No bid adjustment | `bid_modifier == 1.0` |
| Paused criterion | criterion `status == PAUSED` |
| Zero conversions | `conversions == 0` in the window |
| Wasted spend | zero conversions **and** cost over the cost bar (× campaign avg cost) |
| High CPA | converting, but CPA over the cost bar (× campaign avg CPA) |
| Low CTR | CTR under the CTR bar (× campaign avg CTR) |

The weighted sum buckets each audience into **Critical / High / Medium / clean** (all weights and
bars are tunable in the xlsx Controls sheet; defaults in
[references/audience-targeting-filter.md](references/audience-targeting-filter.md)). Negative/
exclusion criteria are **never scored** — kept and shown (never dropped) so the report can confirm,
by name, which lists are attached as exclusions (e.g. verifying a recent-converters exclusion is
actually in place — always **read the list name yourself**, never infer its purpose from the ID).
A third status, **`manual`**, covers a targeting criterion whose ad group has no matching
`ad_group_audience_view` metrics for the window — also never scored, values shown as `"—"`, never
a fabricated zero.

**First-party readiness** rows get a deterministic gap read from the free-text Readiness column
the user supplies (case-insensitive; unrecognized text counts as a gap — cautious default), and a
severity from the category: **Enhanced Conversions / Consent Mode v2 → Critical** (the 2026
measurement foundation), **Customer Match → High** (a missed targeting upside), everything else →
Medium.

**PMax (manual to confirm):** audience signals provided? brand exclusion list set so PMax doesn't
cannibalize brand Search? (coordinate with `google-ads-account-health`).

## Recommend (Critical → High → Medium)
- **Critical:** any Critical-priority applied audience (from the model, cited by name and score);
  any Critical first-party gap — missing Enhanced Conversions or Consent Mode v2 (first-party data
  is the foundation for all targeting in 2026).
- **High:** any High-priority applied audience; Customer Match gaps (missed activation).
- **Medium:** Medium-priority applied audiences (hygiene); CMP/other first-party gaps; layer
  demographic/geo exclusions to refine quality; add audience signals to PMax.

Every number in a recommendation must be traceable to the model (the printed summary or the
artifacts) — never re-narrated from raw pulls. See `google-ads-foundation`'s advisor output
contract for the full emit → report → recommend → offer-apply loop.

## Generate artifacts (in `artifacts/`) — reduced bundle

This is the **thinnest-fit** skill in the advisor upgrade: a small applied-audience universe and a
short first-party checklist don't need an interactive HTML explorer (see
[references/audience-targeting-filter.md](references/audience-targeting-filter.md) for why —
don't "complete" this into a thin explorer). Emitted formats: **`md` + `xlsx`**.

- `*.md` — provenance, headline KPIs, the priority breakdown, the first-party readiness table, the
  clean-result framing, and the full per-audience table (status/flags/score/priority — no row
  loss).
- `*.xlsx` — **Controls** (tunable weights/bars/thresholds + live results) + **Audiences** (every
  row, formula-scored — mirrors the Python model exactly) + **First-Party Readiness** (static
  snapshot). Needs `openpyxl`; LibreOffice-normalized so it opens in Excel.
- `*_bid_adjustments.csv` — Google Ads Editor import, via
  `${CLAUDE_PLUGIN_ROOT}/skills/google-ads-foundation/scripts/make_editor_csv.py`, **only** for
  audiences flagged `wasted_spend`/`high_cpa` (a directionally-justified `-20%`). Everything else
  flagged is a **manual** recommendation — no defensible number can be assigned without knowing
  which remarketing tier a list represents.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/google-ads-audience-targeting/scripts/build_audience_report.py" \
  --input findings.json --first-party-csv first_party.csv \
  --outdir artifacts --brand "{Client Name}" --formats md,xlsx
```

## Resources
- [references/audience-targeting-filter.md](references/audience-targeting-filter.md) —
  **authoritative** findings-JSON schema (both datasets), the two GAQL pulls, the CSV column maps,
  the scoring/gap-read spec, the kernel-mirror contract, and the declared emitted-format set for
  M3.1.
- [scripts/audience_core.py](scripts/audience_core.py) — single-source scoring engine / model
  (stdlib + `_shared/analytics`); mirrored verbatim in the xlsx formulas.
- [scripts/audience_spec.py](scripts/audience_spec.py) — md render spec (KPIs, sections, full row
  table) consumed by the shared toolkit. No `html_*`/`js_kernel` — this skill emits no HTML.
- [scripts/audience_xlsx_spec.py](scripts/audience_xlsx_spec.py) — the xlsx workbook layout
  (Controls / Audiences / First-Party Readiness), pure data, no openpyxl.
- [scripts/assemble_findings.py](scripts/assemble_findings.py) — MCP-path transcription-firewall
  assembler (three raw pulls — criteria identity, ad-group-level metrics, user-list names — joined
  by `ad_group.id` into the `audiences` findings array).
- [scripts/audience_csv.py](scripts/audience_csv.py) — the skill's `column_map`s + CSV assemblers
  for both datasets (applied audiences alternative path; first-party readiness — always this
  path).
- [scripts/build_audience_report.py](scripts/build_audience_report.py) — thin CLI: builds the
  md/xlsx bundle + the bid-adjustments worklist via `_shared/render`.
- [tests/test_core.py](tests/test_core.py) + fixtures — unit tests (fixture priorities, no-row-
  loss, dedupe, excluded-never-scored, first-party gap/severity, empty edges, the raw-pull
  assembler, the CSV path, MCP-vs-CSV parity, md bundle + lazy openpyxl) and
  [tests/analytics_vectors.json](tests/analytics_vectors.json) (this skill's own Python↔JS
  primitives parity fixtures, auto-discovered by the shared gate).

## Common mistakes / red flags
- Don't claim list sizes, membership durations, Customer Match match rates, or Enhanced
  Conversions/Consent Mode status from MCP data — they aren't exposed. Always the first-party
  CSV/manual path, and label it (`meta.source` / `first_party_source`) honestly in the report.
- Don't read an MCP-pulled audience's cost/clicks/conversions as caused solely by that one list —
  it's **ad-group-level** (the API's audience-metrics view has no per-list grain; see "Pull the
  data"). `meta.metrics_granularity` / `provenance.metrics_granularity` says so honestly in every
  artifact; never re-narrate it as per-audience precision.
- Don't infer what a negative/exclusion audience list is *for* from its name or ID — read the name
  and ask, don't guess whether it's actually the recent-converters exclusion.
- Don't auto-generate a bid-adjustment percent for `paused_criterion` / `no_bid_adjustment` /
  `zero_conversions` / `low_ctr` — those need a human decision about the audience's funnel tier;
  only `wasted_spend`/`high_cpa` get a directionally-justified worklist row.
- Always exclude recent converters from remarketing to avoid paying to reach people mid-purchase —
  verify by reading the applied-audience table's exclusion rows, not by assumption.
- Audience list creation, Customer Match upload, and consent setup are **manual** — deliver the
  report + worklist, not a "done".
- A clean account (no Critical/High/Medium applied-audience flags) is a valid result — say so
  rather than inflating a Medium; the same goes for zero applied audiences at all (a real finding:
  no remarketing layer exists yet).
