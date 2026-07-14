# Audience & Targeting Advisor — findings schema, scoring, and bundle (authoritative)

## Emitted-format set (for M3.1 catalog wiring — HM-547)

```
declared_formats: ["md", "xlsx"]
```

This is a **reduced bundle** by design (HM-546), not a partial rollout of the full three-format
set: `--formats` only accepts `md,xlsx`; requesting `html` fails loudly with a pointer to this
section. Reasons, so a future session doesn't "complete" it into a thin explorer:

- The applied-audience universe at any one account is small (a handful to a few dozen criteria) —
  there is no long tail that benefits from an interactive sortable/filterable table the way
  search-terms or products do.
- The scoring itself (6 declarative signals -> a weighted priority score -> a 3-tier bucket) is
  fully tunable in the **xlsx** Controls sheet already; an HTML slider explorer would duplicate
  that tuning surface without adding a genuinely different view.
- First-party readiness is a short (4-8 row) manual checklist, not a filterable dataset.

If a future session (M1 deepening or a user request) adds a dataset to this skill that genuinely
needs interactive filtering, add the HTML explorer then — with `js_kernel`/`html_*` adapters and
the Node<->Python parity gate — rather than manufacturing one now to "complete" the three-format
set. The `SPEC` in `scripts/audience_spec.py` intentionally has no `html_*`/`js_kernel` keys.

## Two independent datasets, one findings JSON

```json
{
  "meta": {
    "client_name": "...", "account_id": "...", "currency": "...",
    "window_30d": "2026-06-06 to 2026-07-05", "generated": "2026-07-05",
    "source": "mcp",
    "first_party_source": "user_csv",
    "reconciliation": {
      "audiences": {"rows": 12, "sums": {"cost": 0.0, "clicks": 0.0, "impressions": 0.0, "conversions": 0.0}},
      "first_party": {"rows": 5, "sums": {}},
      "raw_files": [{"file": "...", "sha256": "...", "bytes": 0}]
    }
  },
  "params": {},
  "audiences": [
    {"campaign": "...", "ad_group": "...", "list_name": "...", "list_type": "REMARKETING",
     "bid_modifier": 1.25, "criterion_status": "ENABLED", "negative": false,
     "impressions": 0, "clicks": 0, "cost": 0.0, "conversions": 0}
  ],
  "first_party": [
    {"category": "Enhanced Conversions", "item": "Enhanced Conversions for web enabled on the primary conversion action",
     "row_type": "config", "readiness": "Not configured", "detail": "...", "verified_date": "2026-07-01"}
  ]
}
```

- `audiences` — every applied-audience criterion (`ad_group_criterion`, `type = USER_LIST`) pulled
  for the account, deduped by `(campaign, ad_group, list_name)`. `source` is `"mcp"` or
  `"user_csv"` (honest label, never implied).
- `first_party` — Customer Match / Enhanced Conversions / Consent Mode v2 / CMP readiness rows.
  **Always** `first_party_source = "user_csv"` once supplied (`"not_supplied"` if the CLI's
  `--first-party-csv` was omitted) — this dataset has **no MCP path**; the Google Ads API does not
  return match rates, list membership sizes, or Enhanced-Conversions/Consent-Mode configuration
  state (see `google-ads-foundation/references/artifact-formats.md`, "What the MCP cannot
  return"). Never present this data as an API-confirmed pull.

## The MCP path — two GAQL pulls

1. **Applied-audience criteria** (`ad_group_criterion`):
   ```
   fields: campaign.name, ad_group.name, ad_group_criterion.type,
           ad_group_criterion.user_list.user_list, ad_group_criterion.bid_modifier,
           ad_group_criterion.status, ad_group_criterion.negative,
           metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions
   condition: ad_group_criterion.type = 'USER_LIST'
   ```
2. **User-list names/types** (`user_list`) — GAQL cannot join `user_list.name`/`user_list.type`
   into the `ad_group_criterion` query above (they live on a different resource), so a second,
   cheap query resolves them:
   ```
   fields: user_list.id, user_list.name, user_list.type
   ```
   `scripts/assemble_findings.py` joins pull 2 onto pull 1 by the numeric id parsed from the
   `ad_group_criterion.user_list.user_list` resource name. A list with no match in pull 2 keeps a
   fallback name (`"List <id>"`) rather than being dropped.

**Never pulled**: remarketing list membership size, Customer Match match rate, Enhanced
Conversions / Consent Mode configuration state — all API-blind; verify in the UI or supply via
`--first-party-csv`.

## The CSV path — `scripts/audience_csv.py`

- `assemble_audiences_from_csv(csv_path, meta)` — the CSV alternative to the MCP pull, for a
  Google Ads UI "Audiences" report export. `AUDIENCE_COLUMN_MAP` declares the columns (Campaign,
  Ad group, Audience, Audience type, Bid adj., Criterion status, Targeting, Impr., Clicks, Cost,
  Conversions). The UI's bid-adjustment column is a **delta percent** (e.g. `+25%`); the assembler
  converts it to the API's 1.0-based multiplier (`bid_modifier = 1.0 + delta`) **after**
  reconciliation, so the embedded control totals are always the raw parsed numeric columns, never
  a derived one. `Targeting` values containing "exclu" (case-insensitive) mark `negative = true`.
- `assemble_first_party_from_csv(csv_path, meta)` — the first-party readiness checklist.
  `FIRST_PARTY_COLUMN_MAP`: `Category`, `Item`, `Type` (`config` or `manual`), `Status` (free text
  — e.g. "Configured", "Not configured", "Partial", "Unknown"), `Detail`, `Verified Date`. There is
  no native Google Ads UI report for this — it is a manual template the user fills in (a CRM
  export, an internal audit spreadsheet, or hand-typed rows). `row_type` values outside
  `config`/`manual` default to `manual`.
- **MCP-vs-CSV parity** (`tests/test_core.py`): the same applied-audience data through
  `assemble_findings.py` and `assemble_audiences_from_csv` yields an identical `compute_model()`
  result except for `provenance.source`.

## Scoring — applied audiences (`scripts/audience_core.py`)

Every deduped applied-audience row gets a `status`:

- **`scored`** — a targeting criterion (`negative = false`). Evaluated by 6 declarative
  `_shared/analytics.signals` rules, benchmarked against **its own campaign's other scored
  audiences from this same pull** (no separate benchmark query). `wasted_spend` and `high_cpa`
  split the "spending too much" case in two — mirroring the two-block pattern already proven in
  `google-ads-keywords-search-terms`' `waste_filter_core` (never-converted waste vs. elevated
  cost-per-conversion among converters) — so a high-spending, well-converting audience is never
  penalized just for spending a lot:
  | id | fires when |
  |---|---|
  | `no_bid_adjustment` | `bid_modifier == 1.0` |
  | `paused_criterion` | `criterion_status == "PAUSED"` |
  | `zero_conversions` | `conversions == 0` |
  | `wasted_spend` | `conversions == 0` AND `cost > cost_multiple × campaign_avg_cost` |
  | `high_cpa` | `conversions > 0` AND `cpa > cost_multiple × campaign_avg_cpa` |
  | `low_ctr` | `ctr < ctr_factor × campaign_avg_ctr` (default `ctr_factor = 0.5`) |

  Default `cost_multiple = 2.0` for both cost signals. `wasted_spend`/`high_cpa` are mutually
  exclusive by construction: `cost_if_zero_conv` and `cpa` are computed as `None` on the rows they
  don't apply to, and `analytics.signals`' "missing operand = no fire" rule means each row can
  only ever trip the one that applies to it.

  `campaign_avg_cost` = arithmetic mean cost per scored audience in the campaign;
  `campaign_avg_ctr` = `SUM(clicks) / SUM(impressions)` over the campaign's scored audiences
  (weighted, not mean-of-ratios); `campaign_avg_cpa` = `SUM(cost) / SUM(conversions)` (weighted)
  over the campaign's scored audiences that have at least one conversion — `None` if none do (in
  which case `high_cpa` cannot fire for anyone in that campaign — no baseline to compare against).
  A campaign with exactly one scored audience compares that audience to itself — none of the three
  benchmark-relative signals can fire on a lone audience under the default bars, which is correct,
  not a bug.

  `_shared/analytics.pre_score` weights the fired flags into a `score`; `priority` buckets the
  score: `score >= critical_threshold` -> **Critical**, `score >= high_threshold` -> **High**,
  `score > 0` -> **Medium**, `score == 0` -> clean (blank). All five weights and both thresholds
  are tunable (xlsx Controls sheet); defaults are documented in `audience_core.DEFAULT_PARAMS`.

- **`excluded`** — a negative/exclusion criterion (`negative = true`). **Never scored** — cost/
  clicks/conversions on an exclusion criterion don't mean "targeting waste," so applying the
  signals above would manufacture false positives. Kept (never dropped) so the report can show
  which lists are attached as exclusions, letting the advisor confirm — by name, honestly, not by
  inferred semantics — that a recent-converters exclusion is actually in place.

A bonus KPI, `_shared/analytics.concentration(scored_rows, "cost", top_n=3)`, reports how
concentrated applied-audience spend is across the top 3 audiences (`top_share`, `hhi`,
`effective_n`) — useful context for "are we over-reliant on one remarketing list."

## Scoring — first-party readiness (`scripts/audience_core.py`)

No numeric signals here — the input is a free-text `readiness` column the user fills in. Every
row gets a deterministic, case-insensitive substring read:

```
has_not = "not" in readiness.lower() or "partial" in readiness.lower()
has_ok  = any(tok in readiness.lower() for tok in ("configured","complete","done","yes","verified"))
gap     = has_not or not has_ok      # unrecognized text counts as a gap (cautious default)
```

`severity` (only when `gap` is true) reads the `category` text: `"enhanced conversion"` /
`"consent mode"` -> **Critical** (the 2026 measurement foundation — see SKILL.md); `"customer
match"` -> **High** (a missed targeting upside); anything else -> **Medium**. This mirrors
SKILL.md's existing Critical/High/Medium framing for first-party items. The `status` field on
every first-party row is its own `row_type` (`"config"` or `"manual"`) — the project's data-
lineage convention, never `"scored"` (this dataset is never computed from performance data).

## Kernel-mirror contract

The Python core is the single source of truth. It is mirrored in the **xlsx formulas**
(`scripts/audience_xlsx_spec.py`) verbatim — the same 6 boolean flag columns, the same weighted
sum for Score, the same nested-IF for Priority, and (on the "Audiences" sheet) `AVERAGEIFS`/
`SUMIFS` for the campaign benchmarks. There is **no JS kernel** — this skill emits no HTML
explorer, so there is nothing to keep in sync with a browser-side re-implementation. This skill's
participation in "the Node<->Python parity gate" (per `docs/orchestration.md` / CLAUDE.md) is the
shared `_shared/analytics.py` primitives gate: `tests/analytics_vectors.json` exercises this
skill's own `signals`/`pre_score`/`concentration` call shapes against `analytics.JS_MIRROR`,
auto-discovered by `skills/google-ads/tests/run_parity.py analytics-primitives`.

## Bundle

`scripts/build_audience_report.py --formats md,xlsx` (default) emits:

- `*.md` — provenance, headline KPIs, the priority breakdown table, the first-party readiness
  table, the clean-result framing, and the full per-audience table (status/flags/score/priority;
  no row loss).
- `*.xlsx` — Controls (tunable weights/bars/thresholds + live COUNTIF/COUNTIFS/SUMPRODUCT
  results) + Audiences (every row, formula-scored) + First-Party Readiness (static snapshot).

Plus `*_bid_adjustments.csv` (Google Ads Editor import, via
`google-ads-foundation/scripts/make_editor_csv.py`'s `bid_adjustments` schema) — **only** for
audiences flagged `wasted_spend` or `high_cpa` (a directionally-justified `-20%` reduction).
Audiences flagged only `paused_criterion` / `no_bid_adjustment` / `zero_conversions` / `low_ctr`
are **not** auto-written to the CSV: no defensible number can be assigned without knowing which
remarketing tier a list represents (a low-intent vs. high-intent audience should NOT get the same
treatment, and this skill has no way to know which is which from the data alone) — those stay
manual recommendations in the report and the advisor's conversational narration, per the honesty
rules in SKILL.md.
