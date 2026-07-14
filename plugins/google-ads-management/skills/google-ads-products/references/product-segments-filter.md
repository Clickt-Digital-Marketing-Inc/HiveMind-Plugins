# Product-Segments Filter — Zombie · Surging · Declining (Shopping/PMax)

Flags **products** (account-aggregated by `product_item_id` across Shopping + Performance Max) into
three actionable segments, and ships the standard three-format analytical bundle: a **markdown
report** (narrative + a full per-product table), a **self-contained interactive HTML explorer**
(sliders + live sensitivity, opens in any browser with no install), and a **formula-driven xlsx**
(LibreOffice-normalized so it opens in Excel). Reuses every `google-ads-foundation` convention
(micros, dates, dedup, the Diagnose→Recommend→Artifacts contract) — load that first.

All three formats are rendered by the shared toolkit (`_shared/render`) from one classification
engine (`scripts/product_filter_core.py`), so they can never disagree; this file is the
**authoritative** input/output contract (the scripts' docstrings point here rather than restating it).

## The three segments

Each row is one product, metrics summed across the account (all Shopping/PMax campaigns) per window.
Conservative defaults match the rule "as written": surge **1.50**, decline **0.50**, zombie cost
floor **0**, zombie max conv **0**.

- **Zombie — wasted spend** → exclude / pause the product:
  `conversions(30d) ≤ 0` AND `cost(30d) > 0` AND `merchant id present (last 14d)`.
- **Surging — accelerating** → scale budget / priority:
  `conversions(14d) > 1.50 × conversions(prev-14d)` AND `conversions(prev-14d) > 0`.
- **Declining — collapsing** → investigate feed / price / stock:
  `conversions(14d) < 0.50 × conversions(prev-14d)`.

The segments are mutually exclusive by construction (a zombie has no 30-day conversions, so it can
neither surge nor decline; surge and decline are opposite inequalities). Precedence **Zombie >
Surging > Declining** makes any degenerate row deterministic.

> **Note on the rule's impression terms.** The original spec also writes `impressions(prev-14d) > 0`
> (surge) and `impressions(14d) >= 0` (decline). For count data `impressions >= 0` is always true, and
> `conversions(prev-14d) > 0` already implies `impressions(prev-14d) > 0` (a conversion requires a
> click requires an impression). So the load-bearing guard kept in code is `conversions(prev-14d) > 0`
> for surge; the impression terms are retained only as comments mirroring the rule verbatim. If
> `conversions(prev-14d) == 0`, a product can never be Declining (the inequality is impossible for
> non-negative counts) — correct, and it falls out naturally.

**Conservative by design.** On healthy accounts this often flags **few or zero** products — a valid
clean result, not a bug. Present the zero honestly and let the explorer's adjustable multipliers
reveal near-misses (the surge/decline sensitivity strips show how counts move as the multipliers
step).

## No-row-loss status taxonomy

Every product survives into the model with a `status`:
- `scored` — has cost or impressions in at least one window (evaluable).
- `inactive` — zero cost AND zero impressions in **every** window (nothing to score; segment "").

Merchant presence is **not** a status — it is the `merchant_id` value plus a `<>""` term in the
zombie test, so the Python, embedded-JS, and xlsx-formula paths compute byte-identical results. A
product with spend but an empty merchant id is `scored`, can still Surge/Decline, but can never be a
Zombie.

## The GAQL pulls (`mcp__google-ads-mcp__search_search`)

> **Probe first.** Product reporting is not used elsewhere in this plugin. Before building the pulls,
> call `mcp__google-ads-mcp__metadata_get_resource_metadata` for `shopping_performance_view` to
> confirm the selectable fields/segments on the live API version (`segments.product_item_id`,
> `segments.product_title`, `segments.product_merchant_id`, `campaign.advertising_channel_type`,
> `metrics.conversions`, `metrics.cost_micros`, `metrics.impressions`).

> **Channel coverage (verified live 2026-06-27).** `shopping_performance_view` returns per-product
> (`segments.product_item_id`) metrics across **both Shopping and Performance Max** campaigns, so one
> resource covers both. Attribute each product's channel by joining campaign info
> (`campaign.advertising_channel_type` is selectable here as a joined attribute even though the
> metadata tool omits it; if a given API version rejects it, filter by PMax-vs-Shopping campaign ids
> instead). Coverage still requires a **Merchant Center product feed**: lead-gen accounts
> (PMax-for-leads, no feed) return **no** product rows — report that honestly ("0 products — an empty
> result is still a valid result") rather than implying a data gap. State which channels actually
> returned rows; don't claim coverage the pulls didn't return.

> **Date literals.** `LAST_90_DAYS`/`LAST_60_DAYS` are **not** valid GAQL literals; `LAST_14_DAYS`
> and `LAST_30_DAYS` are. `LAST_N_DAYS` ends **yesterday** (today is partial). For the previous-14-day
> baseline use an explicit `BETWEEN`.

**Window math** (example: today `2026-06-27`, so yesterday `2026-06-26`):
- **30-day** (zombie cost/conv): `BETWEEN '2026-05-28' AND '2026-06-26'` (= `LAST_30_DAYS`).
- **Last-14-day** (surge/decline current + merchant presence): `BETWEEN '2026-06-13' AND '2026-06-26'`
  (= `LAST_14_DAYS`).
- **Previous-14-day** (baseline): `BETWEEN '2026-05-30' AND '2026-06-12'`.
  General rule: `prev_end = last14_start − 1 day`, `prev_start = last14_start − 14 days`.

**Pull 1 — products, last 30 days** (master list; zombie inputs + identity):
```
resource:   "shopping_performance_view"
fields:     ["segments.product_item_id","segments.product_title","segments.product_merchant_id",
             "campaign.advertising_channel_type",
             "metrics.conversions","metrics.cost_micros","metrics.impressions"]
conditions: ["segments.date BETWEEN '<30d-start>' AND '<yesterday>'"]
orderings:  ["metrics.cost_micros DESC"]
```
**Pull 2 — products, last 14 days** (surge/decline current; merchant presence):
```
resource:   "shopping_performance_view"
fields:     ["segments.product_item_id","segments.product_merchant_id","metrics.conversions","metrics.impressions"]
conditions: ["segments.date BETWEEN '<14d-start>' AND '<yesterday>'"]
```
**Pull 3 — products, previous 14 days** (baseline):
```
resource:   "shopping_performance_view"
fields:     ["segments.product_item_id","metrics.conversions","metrics.impressions"]
conditions: ["segments.date BETWEEN '<prev14d-start>' AND '<prev14d-end>'"]
```

**Which conversion metric.** Use `metrics.conversions` — the account's **primary** conversion goals,
attribution-modeled, and often **fractional** (e.g. `2.75`). Do **not** substitute
`metrics.all_conversions`. Use the same metric for all three windows so the comparison is like-for-like.

**Transcription firewall (mandatory).** Every pull's raw result must land in a file before
anything else happens: the big 30-day pull usually exceeds the MCP token cap and auto-saves to a
`tool-results/*.txt` file — use that file as-is; for pulls that come back inline, copy the whole
tool result **verbatim** (the complete `{"result": [...]}` JSON, unedited) into a file. Then build
the findings JSON with `scripts/assemble_findings.py` — never assemble it by hand:

```
python3 scripts/assemble_findings.py \
  --products-30d <raw-30d-file> --products-14d <raw-14d-file> --products-prev14d <raw-prev14d-file> \
  --client-name "{Client Name}" --account-id {account} --currency {CUR} \
  --window-30d "<30d-start> to <yesterday>" --window-14d "<14d-start> to <yesterday>" \
  --window-prev14d "<prev14d-start> to <prev14d-end>" \
  -o findings.json
```

The assembler parses the raw files (micros conversion; per-`product_item_id` aggregation across
campaigns/channels; the channel-set union; the merchant id from the most recent window the product
appears in; missing windows default to 0), embeds control totals as `meta.reconciliation`, and
`product_filter_core` re-verifies those totals on every build — a findings JSON whose numbers were
typed or edited by hand hard-fails. Metric values therefore never pass through the model: the model
handles file paths and meta labels (client name, account id, windows), and the pipeline handles the
numbers.

## CSV manual-input path

Every bundle/advisory skill accepts its data from **either** the Google Ads MCP or a
user-supplied CSV (the [dual-input contract](../../google-ads-foundation/references/artifact-formats.md#dual-input-mcp-or-csv)).
For this skill the CSV path is three exports of the Google Ads UI **Products**
report (Insights & reports → Reports → Predefined reports → Shopping →
Product, or the Campaigns → Products view), one per window — the CSV twin of
the three GAQL pulls above, same date ranges, same join.

**Use the CSV path when:** the MCP is unreachable or misconfigured
(`login-customer-id` not set), or the user already has the exports. This
skill's data is **not** API-blind (`shopping_performance_view` is queryable),
so default to the MCP path when it's reachable — see Step 0 of the dual-input
contract for the full decision order.

**What to export per window** — same date ranges as the three GAQL pulls above,
one CSV each, with these columns:

| Window | Required columns | Optional (enrichment) |
|---|---|---|
| 30-day | Item ID · Cost · Conversions · Impressions | Item title · Merchant Center ID · Campaign type |
| Last-14-day | Item ID · **Merchant Center ID** · Conversions · Impressions | — |
| Previous-14-day | Item ID · Conversions · Impressions | — |

The 14-day export's **Merchant Center ID column is required, not optional**:
the join always adopts the 14-day pull's merchant-id value for any product
that appears there (even blank — this is exactly the "merchant id present in
the last 14 days" zombie test), so an export missing that column would
silently blank every such product's merchant id instead of raising. The
assembler enforces this — a 14-day export without it raises `CsvInputError`
naming the missing column rather than producing a silently wrong Zombie count.

**`CSV_COLUMN_MAP`** (declared in `scripts/assemble_findings.py`), one entry
per logical field the join (`product_filter_core.merge_product_windows`)
expects, aliases covering header spellings the UI export may use:

```python
CSV_COLUMN_MAP = {
    "product_item_id": {"aliases": ["Item ID", "Item Id", "Product ID", "Product Id"], "type": "str"},
    "product_title":   {"aliases": ["Item title", "Product title", "Product Title", "Title"], "type": "str"},
    "merchant_id":     {"aliases": ["Merchant Center ID", "Merchant Center Id", "Merchant ID"], "type": "str"},
    "channel":         {"aliases": ["Campaign type", "Advertising channel type"], "type": "str"},
    "conversions":     {"aliases": ["Conversions", "Conv."], "type": "num"},
    "cost":            {"aliases": ["Cost"], "type": "num"},
    "impressions":     {"aliases": ["Impr.", "Impressions"], "type": "num"},
}
```

> **Channel-label honesty.** The UI's "Campaign type" column may read as a
> human label ("Shopping", "Performance Max") rather than the API enum
> ("SHOPPING", "PERFORMANCE_MAX"). `channels` is enrichment only — it plays no
> role in the Zombie/Surging/Declining tests — so a casing mismatch between
> the MCP and CSV paths never changes a segment or a dollar figure; it can
> only change how the channel tag displays. If a real export's spelling isn't
> recognized as the value you expect, that's fine — it still lands in
> `channels` verbatim.

**Assemble the findings JSON** — same script, CSV flags instead of the raw-pull
flags (mutually exclusive with `--products-30d/-14d/-prev14d`):

```bash
python3 scripts/assemble_findings.py \
  --csv-30d products_30d.csv --csv-14d products_14d.csv --csv-prev14d products_prev14d.csv \
  --client-name "{Client Name}" --account-id {account} --currency {CUR} \
  --window-30d "<30d-start> to <yesterday>" --window-14d "<14d-start> to <yesterday>" \
  --window-prev14d "<prev14d-start> to <prev14d-end>" \
  -o findings.json
```

`assemble_csv` runs the CSVs through `_shared/csv_input.load_csv_rows` (the
same transcription-firewall discipline as the MCP path: title rows and
`Total: ...` summary rows handled, typed conversion, ambiguous/missing
columns raise `CsvInputError`) and joins them with the **same**
`product_filter_core.merge_product_windows` the MCP assembler uses — one join
algorithm, so the two paths can never disagree. `meta.source` is stamped
`"user_csv"` (the MCP path stamps `"mcp"`); both flow through
`meta.reconciliation` control totals exactly like the MCP path. The report
provenance table surfaces "Data source" honestly — never presented as an API
pull. MCP-vs-CSV parity is proven in
[tests/test_filter.py](../tests/test_filter.py)'s
`test_csv_matches_mcp_model` (same product data through both assemblers →
identical `compute_model` output, modulo the source label).

## The findings JSON

What the assembler produces (and the script's input contract):

```json
{
  "meta":   {"client_name","account_id","currency","window_30d","window_14d","window_prev14d",
             "generated","source"},             // source: "mcp" | "user_csv" (HM-540/HM-572)
  "params": {                                  // all optional; defaults below = rule "as written"
     "surge_multiple": 1.50,
     "decline_multiple": 0.50,
     "zombie_cost_min": 0,
     "zombie_conv_max": 0
  },
  "products": [{"product_item_id","product_title","merchant_id","channels":["SHOPPING","PERFORMANCE_MAX"],
                "conversions_30d","cost_30d","impressions_30d",       // cost already /1e6
                "conversions_14d","impressions_14d",
                "conversions_prev14d","impressions_prev14d"}]
}
```
`cost_30d` is in the account currency (already divided by 1e6). The dedupe/merge key is
`product_item_id`; rows sharing it are summed (account aggregate). Missing windows default to 0.

## Build the deliverable bundle

```bash
# md + html — dependency-free, needs only Python
python3 scripts/build_product_report.py \
  --input findings.json --outdir artifacts --brand "{Client Name}" --formats md,html
# all three (xlsx needs openpyxl; normalizes via LibreOffice) + 3 action worklists
python3 scripts/build_product_report.py \
  --input findings.json --outdir artifacts --brand "{Client Name}" --formats md,html,xlsx
```
Files land in `artifacts/` as `product-segments_{account}_{date}.{ext}` (`.md`, `_explorer.html`,
`.xlsx`) plus `..._zombie_worklist.csv`, `..._surging_worklist.csv`, `..._declining_worklist.csv`.
Run the unit tests with `python3 tests/test_filter.py`.

**What each format is for** — all from one model, so no two can disagree:
- `*.md` — the narrative / trust layer: provenance header (account, currency, the 30d/14d/prev-14d
  windows, generated, thresholds, **data source**), headline counts, the **clean-result** framing
  when nothing flags, a **Recommendations (Critical → High → Medium)** table citing the model's own
  numbers (per-product examples + the worklist that applies each tier), the **surge** and **decline
  sensitivity** tables, the **inactive-products** list, and a **full per-product table** with each
  row's `status` and `segment` (the no-row-loss layer). Zero deps.
- `*_explorer.html` — the **interactive primary**: self-contained (inline CSS+JS, data embedded, no
  external refs), with **sliders** (surge multiple, decline multiple) + **zombie floors**, live
  counts + wasted spend, two **sensitivity strips**, and the full product table with a status column,
  a live Segment badge, and a "qualifying only" toggle. Opens in any browser — no install, no Excel,
  no cloud. The embedded JS computes byte-identical results to the Python model (Node-verified).
- `*.xlsx` — the tunable Controls + Live-products workbook (layout below) with a **Sensitivity** tab
  and a **Status** column (no row loss). Built via the shared `render.xlsx`; the wrapper
  `scripts/build_product_report_workbook.py --check` validates an existing file.

**Currency** from `meta.currency` is shown in every header and on cost columns.

**Action worklists.** Three CSVs (Zombie / Surging / Declining), columns `Segment, Product Item ID,
Product Title, Merchant ID, 30d Cost, Conv 14d, Conv Prev 14d, Action, Reason`. **Not** Google Ads
Editor imports — product-level exclusions are managed in the Shopping/PMax **listing groups** (UI),
not via a generic Editor CSV. Treat them as prioritized **manual worklists**.

**Excel-open honesty.** openpyxl output can fail to open in Excel-for-Mac, so the xlsx is
**normalized through LibreOffice** (`soffice`) by default — it writes the structure Excel expects and
caches values *while preserving every formula*. If `soffice` is missing the xlsx build **fails (exit
2)** rather than shipping a file that may not open (`--no-normalize` overrides). `--check` **fails**
on a file with no cached values. Real-Excel open is **not** verified here — the verified-open paths
are the **HTML explorer** and **LibreOffice**; prefer the HTML explorer for a zero-friction
interactive deliverable.

## xlsx layout

**Controls** sheet — three sections driving the same formulas: (1) **Segment parameters** — yellow
dropdowns: surge multiple `C5`, decline multiple `C6`, zombie cost floor `C7`, zombie max conv `C8`;
(2) **Segment logic** — plain-language rules that **rewrite themselves** from those cells; (3)
**Results (live)** — `COUNTIF`/`SUMIF` over the Live-products `Segment` column.

**Live products** sheet — **every** product (frozen header + auto-filter; flagged rows highlighted).
A **Status** column marks `scored` vs `inactive`; inactive rows keep their metrics but are left
unscored (never dropped, never miscounted). Scored rows carry formula columns referencing the
Controls cells (`Zombie? = AND(conv30 ≤ C8, cost > C7, merchant <> "")`, `Surging? = AND(prev-14d
conv > 0, conv14 > C5 × prev-14d)`, `Declining? = conv14 < C6 × prev-14d`, `Segment = Zombie / Surging
/ Declining / ""` with the same precedence). The cost column is headed **Cost** (= last 30 days) so
the wasted-spend `SUMIF` targets it.

**Sensitivity** sheet — a static snapshot at the generated parameters: the surge ladder, the decline
ladder, and the excluded-inactive list.

Changing any Controls cell recomputes the Live products and the counts — no rebuild needed.
