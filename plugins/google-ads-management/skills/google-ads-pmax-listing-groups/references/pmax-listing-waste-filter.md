# PMax Listing-Group Waste Filter — two-block, campaign-benchmarked

Flags Performance Max **listing groups** (product partitions) and **products** (item-id) that waste
spend, benchmarked against **each unit's own campaign** over the last 30 days, and ships the standard
analytical bundle: a markdown report, a **self-contained interactive HTML explorer** (one slider +
live recompute, opens in any browser with no install), and a formula-driven, LibreOffice-normalized
**.xlsx**. Reuses every `google-ads-foundation` convention (micros, dates, dedup,
`metrics.conversions`) — load that first.

All formats share one classification engine (`scripts/pmax_listing_core.py`) so they can never
disagree; this file is the **authoritative** input/output contract (the scripts' docstrings point
here rather than restating it).

## The two blocks

Each unit is benchmarked against its **own campaign** (30d). A single tunable **expensiveness factor
F** (default **1.50**) scales both bars. The two blocks are mutually exclusive by the conversion
split.

- **Block 1 — expensive converters** → review / segment / exclude:
  `conversions(unit) > 0` AND `cost/conv(unit) > F × cost/conv(campaign)`.
  *(They convert, but above F× the campaign's cost per conversion.)*
- **Block 2 — zero-conversion waste** → exclude / down-prioritize:
  `conversions(unit) = 0` AND `clicks(unit) > F × clicks/conv(campaign)` AND `conversions(campaign) > 0`.
  *(No conversions despite spending more clicks than the campaign needs, on average, to get one.)*

Campaigns with **0 conversions in 30d** have an undefined cost/conv and clicks/conv benchmark → their
units cannot qualify. Report them as *excluded (no benchmark)*; never silently drop them.

**Conservative by design.** On a healthy account this can return **0 / 0** — a valid clean-bill
result, not a bug. Present the zero honestly and use the explorer's slider (and the sensitivity
table — how many units qualify as F steps down 2.0 → 1.5 → 1.0 → 0.5) to surface near-misses, rather
than forcing hits.

## Two granularities, one engine

The same core classifies two universes against the same campaign benchmark:

- **Partitions** (`listing_groups`) — the PMax listing-group tree per asset group. The **primary**,
  live-tunable, no-row-loss universe in all three formats.
- **Products** (`products`) — individual item-ids. A **drill-down**: a full table + sensitivity +
  near-misses in the md report and the HTML explorer (live), and a static snapshot on the xlsx
  *Sensitivity* tab (re-run, or use the HTML, to re-tune products).

Either array may be omitted; an absent universe is simply empty.

## Tier concentration + signal (independent of the expensiveness factor)

Alongside the two blocks, each universe (partitions, products) is read as a "tier" set. Three more
tunable params (all default-on, all in `params`):

| Param | Default | Meaning |
|---|---|---|
| `concentration_top_n` | `3` | top-N units read for the concentration KPIs |
| `concentration_share_min` | `0.30` | a unit's own share of its universe's 30d spend above which it's "over-concentrated" |
| `weak_roas_max` | `1.00` | a unit's ROAS (`conversions_value / cost`) below which it's "weak" |

Two reads, both computed from `_shared/analytics.py` (kernel-mirrored verbatim in the HTML explorer
and the xlsx formulas — never re-implemented per format):

- **Concentration** (`analytics.concentration(rows, "cost", top_n=concentration_top_n)`) — top-N
  share of 30d spend, HHI (0–10,000), and effective-N, over the WHOLE universe (every row, scored or
  no_benchmark — no-row-loss holds for this read too).
- **Tier signal** (`analytics.signals`, per row) — two declarative rules, `over_concentrated`
  (`cost_share > concentration_share_min`) and `weak_roas` (`roas < weak_roas_max`); a row's
  `tier_signal` is true only when **both** fire — "spend concentrated in a tier with weak ROAS". A
  unit can carry a tier signal whether or not it also qualifies Block 1/2 — the two reads are
  independent. `roas` is `None` (no signal, never 0) when `cost = 0`.

`model["summary"]["concentration"]` / `["tier_signals"]` / `["signal_spend"]` (and the same three keys
nested under `["item"]` for products) surface this in every format; `model["recommendations"]` folds a
tier signal into a **High**-severity recommendation (see "Advisor recommendations" below).

## The GAQL pulls (`mcp__google-ads-mcp__search_search`)

All windows use `segments.date DURING LAST_30_DAYS` (a valid literal that ends *yesterday*, matching
the Google Ads UI's LAST_30_DAYS).

**1 — Listing-group metrics (30d)** — the partition universe. `asset_group_product_group_view` is
**PMax-only by construction** (legacy Shopping uses `product_group_view`):
```
resource:   "asset_group_product_group_view"
fields:     ["campaign.id","campaign.name","asset_group.id","asset_group.name",
             "asset_group_product_group_view.asset_group_listing_group_filter",
             "metrics.impressions","metrics.clicks","metrics.conversions",
             "metrics.conversions_value","metrics.cost_micros"]
conditions: ["segments.date DURING LAST_30_DAYS","metrics.cost_micros > 0",
             "campaign.status = 'ENABLED'"]
orderings:  ["metrics.cost_micros DESC"]
```

**2 — Listing-group labels (structural, no date)** — what each partition *is*. Join key:
pull-1 `asset_group_product_group_view.asset_group_listing_group_filter` ==
pull-2 `asset_group_listing_group_filter.resource_name`:
```
resource:   "asset_group_listing_group_filter"
fields:     ["asset_group_listing_group_filter.resource_name","asset_group_listing_group_filter.id",
             "asset_group_listing_group_filter.type",
             "asset_group_listing_group_filter.case_value.product_brand.value",
             "asset_group_listing_group_filter.case_value.product_item_id.value",
             "asset_group_listing_group_filter.case_value.product_type.value",
             "asset_group_listing_group_filter.case_value.product_type.level",
             "asset_group_listing_group_filter.case_value.product_category.category_id",
             "asset_group_listing_group_filter.case_value.product_category.level",
             "asset_group_listing_group_filter.case_value.product_condition.condition",
             "asset_group_listing_group_filter.case_value.product_channel.channel",
             "asset_group_listing_group_filter.case_value.product_custom_attribute.index",
             "asset_group_listing_group_filter.case_value.product_custom_attribute.value"]
```
Build each `listing_group` label + `dimension` from the populated `case_value` sub-field (e.g.
`Brand: Nike` / `Item ID: ABC123` / `Type: Shoes`). A UNIT node with no `case_value` is the catch-all
→ label `Everything else`.

**3 — Campaign benchmarks (30d)** — serves BOTH universes:
```
resource:   "campaign"
fields:     ["campaign.id","campaign.name","metrics.clicks","metrics.conversions","metrics.cost_micros"]
conditions: ["segments.date DURING LAST_30_DAYS","campaign.advertising_channel_type = 'PERFORMANCE_MAX'"]
```
Per campaign: `cost/conv = (cost_micros/1e6) / conversions` and `clicks/conv = clicks / conversions`.
Compute from raw — do **not** use `metrics.cost_per_conversion` (also micros). Skip
`conversions = 0` (undefined).

**4 — Per-product metrics (30d)** — the product universe. `shopping_performance_view` spans Shopping
*and* PMax, so keep only rows whose `campaign.id` is in the PMax set from pull 3:
```
resource:   "shopping_performance_view"
fields:     ["campaign.id","campaign.name","segments.product_item_id","segments.product_title",
             "metrics.impressions","metrics.clicks","metrics.conversions",
             "metrics.conversions_value","metrics.cost_micros"]
conditions: ["segments.date DURING LAST_30_DAYS","metrics.cost_micros > 0"]
orderings:  ["metrics.cost_micros DESC"]
```

**Which conversion metric.** Use `metrics.conversions` — the account's **primary** conversion goals,
attribution-modeled, often **fractional** (e.g. `2.75`). The same metric is used for the unit and its
campaign benchmark so the comparison is like-for-like. Do not substitute `metrics.all_conversions`.

**Micros.** Divide every `*_micros` by 1,000,000 (`cost_micros`). Trap: `metrics.average_cpc` /
`average_cpm` are also micros despite the name (unused here). `metrics.conversions_value` is **not**
micros.

**Transcription firewall (mandatory).** Every pull's raw result must land in a file before
anything else happens: a big pull (listing groups or products) can exceed the MCP token cap and
auto-save to a `tool-results/*.txt` file — use that file as-is; for pulls that come back inline,
copy the whole tool result **verbatim** (the complete `{"result": [...]}` JSON, unedited) into a
file. Then build the findings JSON with `scripts/assemble_findings.py` — never assemble it by hand:

```
python3 scripts/assemble_findings.py \
  --listing-groups <raw-listing-group-file> --labels <raw-labels-file> \
  --benchmarks <raw-benchmarks-file> --products <raw-products-file> \
  --client-name "{Client Name}" --account-id {account} --currency {CUR} \
  --window-30d "<30d-start> to <yesterday>" \
  -o findings.json
```

`--listing-groups`/`--labels` travel together (the labels pull carries no metrics — it only names
each partition); `--products` is optional — at least one universe must be present. The assembler
parses the raw files (micros conversion, per-key aggregation, the label join on the filter resource
name, the PMax-campaign filter on products), embeds control totals as `meta.reconciliation`, and
`pmax_listing_core` re-verifies those totals on every build — a findings JSON whose numbers were
typed or edited by hand hard-fails. Metric values therefore never pass through the model: the model
handles file paths and meta labels (client name, account id, window), and the pipeline handles the
numbers.

## Assemble the findings JSON

What `scripts/assemble_findings.py` produces (and the core's input contract — micros converted,
each `listing_group` label derived, cost already `/1e6`):
```json
{
  "meta":   {"client_name","account_id","currency","window_30d","generated","source"},
  "params": {"expensiveness_factor": 1.50, "concentration_top_n": 3,
             "concentration_share_min": 0.30, "weak_roas_max": 1.00},
  "benchmarks":     [{"campaign_id","campaign","clicks","cost","conversions"}],
  "listing_groups": [{"campaign_id","campaign","asset_group_id","asset_group",
                      "listing_group_id","listing_group","dimension",
                      "impressions","clicks","cost","conversions","conversions_value"}],
  "products":       [{"campaign_id","campaign","item_id","title",
                      "impressions","clicks","cost","conversions","conversions_value"}]
}
```
`cost` is in the account currency (already `/1e6`). `listing_groups` and `products` are each optional,
but at least one must be present. `meta.source` is stamped `"mcp"` by
`assemble_findings.py` — see "CSV input path" below for the CSV twin.

## CSV input path — dual input (MCP or CSV)

This skill accepts its data from **either** the Google Ads MCP (above) **or** a user-supplied Google
Ads UI CSV export — see the dual-input contract in
`../../google-ads-foundation/references/artifact-formats.md`. Both paths run the same
transcription-firewall + reconciliation discipline and yield an **identical findings/model shape**
(asserted by `tests/test_pmax_listing.py::test_mcp_vs_csv_identical_model`) — the core cannot tell
them apart except by the honest `meta.source` label (`"user_csv"` on this path).

**When to use it:** the MCP is unreachable/erroring, or the user already has the exports. Ask for
these three UI reports, last 30 days (match the MCP pulls' window):

| Export | Where in the Google Ads UI | Columns to keep |
|---|---|---|
| Campaigns (PMax only) | Campaigns view, filtered to Performance Max | Campaign, Clicks, Cost, Conversions |
| Listing groups | Performance Max campaign → Asset groups → "Listing groups" | Campaign, Asset group, Listing group, Impr., Clicks, Cost, Conversions, Conv. value |
| Products (optional) | Insights & reports → Shopping/PMax product performance | Campaign, Item ID, Item title, Impr., Clicks, Cost, Conversions, Conv. value |

```bash
python3 scripts/assemble_from_csv.py \
  --campaigns <campaigns-export.csv> --listing-groups <listing-groups-export.csv> \
  --products <products-export.csv> \
  --client-name "{Client Name}" --account-id {account} --currency {CUR} \
  --window-30d "<30d-start> to <yesterday>" \
  -o findings.json
```
`--campaigns` is always required; `--listing-groups` and/or `--products` (at least one) follow the
same optional-universe rule as the MCP path.

**Honesty about the join keys.** A flat UI export carries no numeric campaign id (the campaign
**name** is used as `campaign_id` — a stable key as long as names are unique in the account) and no
listing-group-filter resource id or `case_value` dimension breakdown — those two fields
(`listing_groups[].listing_group_id`, `.dimension`) are the **only** difference between the two
paths' output; the exported "Listing group" column text becomes the label directly (the
`"Brand: Nike"`-style prefix only exists on the MCP path, derived from `case_value.*`). Every metric
(impressions, clicks, cost, conversions, conversions_value) and every derived model field (ROAS,
cost_share, block, tier_signal, concentration, recommendations) is identical between the two paths
for the same underlying data. Column-header spellings are matched via the skill's `COLUMN_MAP`s in
`scripts/assemble_from_csv.py` (case-insensitive, currency-suffix-tolerant — see
`_shared/csv_input.py`); if a real export uses a different header, add the alias + a fixture test and
log the lesson in the project's Lessons Log.

## Advisor recommendations

`pmax_listing_core.recommendations(model)` turns the model into prioritized, model-grounded
recommendations (Critical → High → Medium — see the advisor output contract in
`../../google-ads-foundation/references/artifact-formats.md`), embedded as `model["recommendations"]`
and surfaced first in the md report and the xlsx Sensitivity snapshot:

- **Critical** — Block 2 (zero-conversion waste), partitions and/or products, citing the flagged
  count and spend.
- **High** — Block 1 (expensive converters), same citation pattern; **and** a separate item for the
  tier concentration + weak-ROAS signal (count + spend + the two thresholds).
- **Medium** — the near-miss watchlist (units just below the expensiveness-factor bar, excluding
  anything already qualifying) and a dominant `"Everything else"` catch-all partition (a sign the
  asset group needs subdividing).

Every recommendation's `artifact` field is the same honest manual callout: this skill has **no**
Editor apply-CSV (PMax listing-group/product exclusions are manual in the web UI), so the flagged
rows in the bundle themselves ARE the worklist. Empty severities are honest — a clean account can
return an empty `recommendations` list; nothing is fabricated to fill a tier.

## Build the deliverable bundle

```bash
# dependency-free primaries (md + html) — needs only Python
python3 scripts/build_pmax_listing_filter.py \
  --input findings.json --outdir artifacts --brand "{Client Name}" --formats md,html
# add the formula-driven workbook (needs openpyxl; normalizes via LibreOffice)
python3 scripts/build_pmax_listing_filter.py \
  --input findings.json --outdir artifacts --brand "{Client Name}" --formats md,html,xlsx
# validate an existing workbook
python3 scripts/build_pmax_listing_workbook.py --check --input artifacts/<file>.xlsx
```
Files land in `artifacts/` as `pmax-listing-waste_{account}_{date}.{ext}`. Run the unit tests with
`python3 tests/test_pmax_listing.py`.

**What each format is for**
- `*.md` — narrative / trust layer: provenance header (account, 30d window, currency, generated,
  factor, tier-signal bars, **data source**), **prioritized recommendations** (Critical/High/Medium),
  **tier concentration** (top-N share / HHI / effective-N per universe), headline counts (partitions
  **and** products), the **"0/0 = clean"** explanation, **tier signals** (units both over-concentrated
  and weak on ROAS), the **sensitivity** tables, **near-miss** rankings, **excluded** campaigns, and
  **full per-unit tables** (every partition and every product, with status + block — no row loss).
  Zero dependencies.
- `*_explorer.html` — the **interactive primary**: self-contained (inline CSS+JS, data embedded, no
  external refs), one **Expensiveness-factor slider** re-tuning the partition table, the products
  panel, both sensitivity strips, and both near-miss lists live; a **tier concentration & signal**
  card (top-N share, HHI, effective-N, tier-signal count/spend) for both universes, recomputed via
  the same shared `analytics` primitives as the Python model. Opens in any browser — no install, no
  Excel, no cloud. The embedded JS computes byte-identical results to the Python model.
- `*.xlsx` — **Controls** (the expensiveness factor + the two tier-signal thresholds
  (`concentration_share_min`, `weak_roas_max`) + self-rewriting Block 1/2 logic + live
  `COUNTIF`/`SUMIF` results, **including tier signals** + campaign benchmarks) · **Live filter**
  (every partition + a `Status` column; block formulas are scored-only, but the spend-share/ROAS/tier
  columns are **live for every row** — no-row-loss holds for concentration too) · **Sensitivity** (a
  static snapshot: recommendations, tier concentration, partition sensitivity/near-misses/excluded
  **and** the full products table + product tier signals/sensitivity/near-misses). Needs `openpyxl`;
  LibreOffice-normalized so it opens in Excel.

**Currency** from `meta.currency` is shown in every header and on cost columns.

**Excel-open honesty.** openpyxl output can fail to open in Excel-for-Mac, so the xlsx is
**normalized through LibreOffice** (`soffice`) by default — this writes the structure Excel expects
and caches values *while preserving every formula*. If `soffice` is missing the build **fails (exit
2)** rather than shipping a file that may not open (`--no-normalize` overrides). `--check` **fails**
on a file with no cached values. Real-Excel open is **not** verified here — the verified-open paths
are the **HTML explorer** and LibreOffice; recommend the buyer confirm the xlsx in Excel once if that
is their primary surface. In xlsx, **partitions are live-formula** while **products are a static
snapshot** at the generated factor — re-tune products live in the HTML explorer or re-run the build.

## Applying the findings (manual — read-only MCP)

PMax listing-group / product exclusions are **not** supported by Google Ads Editor; there is **no
apply-CSV** for this skill. The flagged rows in the bundle ARE the worklist:
- **Block 2 (zero-conv waste):** in the asset group's listing-group tree (Google Ads web UI), exclude
  or down-prioritize the partition, or exclude the specific item-id; or move it to a test asset group.
- **Block 1 (expensive converters):** they convert above F× campaign CPA — segment into their own
  asset group / campaign with a tighter tCPA/tROAS, or exclude if the margin is negative.
- **Tier signal (concentrated + weak ROAS):** independent of Block 1/2 — reallocate budget away from
  units holding a disproportionate share of 30d spend at a sub-bar ROAS; a good candidate for the
  same segmentation/exclusion move as Block 1, decided on the modeled numbers in the recommendation.

## Scope notes / honesty

- This report only applies to **retail PMax** (campaigns with a Merchant Center product feed).
  Lead-gen PMax campaigns have no listing groups — `asset_group_product_group_view` and
  `shopping_performance_view` return no rows for them.
- The resource/field design was verified live against the connected MCP; the numeric path ships with a
  synthetic fixture (`tests/sample-pmax-findings.json`) because the accounts accessible during
  development run lead-gen (non-retail) PMax only. Run against any retail-PMax account to populate it.
- Auction Insights, margin/profit, and Merchant Center feed health are **not** in this report — mark
  those manual.
