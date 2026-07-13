# Raw pulls — Shopify MCP recipes for the audit data files

The pulls below feed the machine-computed Step-1 `analytics` block, the Concentration report,
and the CVR Signals layer. Their saved result files are the **only** source of those numbers —
`scripts/shopify_rows.py` parses them deterministically, so metric values never pass through
the model (the transcription firewall). Every envelope fact in this document was pinned from
**live captured results (2026-07-12)** — the parsers are built to exactly these shapes.

## Save-verbatim instructions (non-negotiable)

Write the **ENTIRE tool result JSON exactly as returned** to the working directory — the whole
ShopifyQL envelope (`query`, `columns`, `rows`, `rowCount`, `summaryMetric`, `shopDomain`,
`chartHint` and all). Do not extract the rows, do not pretty-print, retype, trim, or reformat,
and do not "fix" fraction-valued PERCENT columns or comma-formatted `summaryMetric` strings.
The parser coerces everything itself and tolerates stray non-JSON text around the document. A
malformed or error-shaped file fails loudly with a `RawResultError` pointing back here.

Canonical filenames (what `build_cro_audit.py --raw-dir` expects):

| File | Tool | Required? |
|---|---|---|
| `shop_info.json` | `get-shop-info` | recommended — currency + store identity |
| `analytics_funnel.json` | `run-analytics-query` (pull 1) | yes — the funnel |
| `analytics_device.json` | `run-analytics-query` (pull 2) | yes — device split |
| `analytics_referrer.json` | `run-analytics-query` (pull 3) | yes — channel split |
| `analytics_landing.json` | `run-analytics-query` (pull 4) | yes — landing pages |
| `analytics_products.json` | `run-analytics-query` (pull 5) | yes — revenue concentration |
| `analytics_totals.json` | `run-analytics-query` (pull 6) | yes — totals + AOV |
| `analytics_customers.json` | `run-analytics-query` (pull 7) | optional — order-share evidence |
| `orders.json` | `list-orders` | optional — context/provenance only |
| `products.json` | `search_products` | optional — catalog context only |

Explicit per-file flags accept other paths without renaming (see `build_cro_audit.py --help`).

## The ShopifyQL pulls (`run-analytics-query`)

Use `SINCE -90d UNTIL today` as the default window (swap consistently if the user picks another
window — **all pulls must share one window**). Queries verbatim:

### 1. Funnel → `analytics_funnel.json`
```
FROM sessions SHOW sessions, sessions_with_cart_additions, sessions_that_reached_checkout,
sessions_that_completed_checkout, conversion_rate SINCE -90d UNTIL today
```
Single row: the four stage counts (INTEGER) + `conversion_rate` (PERCENT — a **fraction**,
verified `== purchases/sessions` exactly).

### 2. Device split → `analytics_device.json`
```
FROM sessions SHOW sessions, conversion_rate GROUP BY session_device_type SINCE -90d UNTIL today
```
Rows: `session_device_type` (STRING — `mobile`/`desktop`/`tablet`/`other`), sessions, CVR.

### 3. Referrer split → `analytics_referrer.json`
```
FROM sessions SHOW sessions, conversion_rate GROUP BY referrer_source SINCE -90d UNTIL today
```
Rows: `referrer_source` (e.g. `search`, `social`, `direct`, `email`), sessions, CVR.

### 4. Landing pages → `analytics_landing.json`
```
FROM sessions SHOW sessions, conversion_rate GROUP BY landing_page_path ORDER BY sessions DESC
LIMIT 1000 SINCE -90d UNTIL today
```
**Always `LIMIT 1000`** — GROUP BY results are truncated by LIMIT, and the full universe is
needed for honest share/concentration/CVR-gate math (the report embeds only the top 25, but the
shares are computed against everything returned).

### 5. Sales by product → `analytics_products.json`
```
FROM sales SHOW net_sales, gross_sales, orders GROUP BY product_title ORDER BY net_sales DESC
LIMIT 1000 SINCE -90d UNTIL today
```
**Always `LIMIT 1000`** (same universe rule). `net_sales`/`gross_sales` are MONEY, `orders`
INTEGER.

### 6. Totals + AOV → `analytics_totals.json`
```
FROM sales SHOW orders, net_sales, total_sales, average_order_value SINCE -90d UNTIL today
```
Single row. `average_order_value` is taken **verbatim** — see the AOV trap below.

### 7. Customers → `analytics_customers.json` (optional)
```
FROM sales SHOW customers, returning_customers, returning_customer_rate SINCE -90d UNTIL today
```
`returning_customer_rate` is an **order-share fraction, not a session CVR** — it lands as
evidence only. Session-based new-vs-returning CVR is **not exposed by ShopifyQL** (a
`FROM customers SHOW new_customers, returning_customers` probe errors "Column Not Found");
GA4's `ga4-new-returning.csv` is the only source for `analytics.new_vs_returning`.

## Other tools

- **`get-shop-info` → `shop_info.json`** — flat `{name, domain, email, planName, currencyCode,
  timezone, country, criticalUserMessage}`. Fills `meta.currency` (blank-only) and the store
  label.
- **`list-orders` → `orders.json`** (optional) — `{orders: [{id: "gid://shopify/Order/N",
  name: "#3910", createdAt: ISO-Z, customerName, totalPrice: str, currencyCode,
  financialStatus, fulfillmentStatus, lineItemCount}], totalCount, requestedCount}`. Max
  50/page, **no line-item detail**, and `totalCount` is **all-time**, not the window. This pull
  is shape-pin/context only — the ShopifyQL sales queries are the aggregated source.
- **`search_products` → `products.json`** (optional) — GraphQL envelope
  `{data: {products: {edges: [{node: {...}}], pageInfo: {hasNextPage, endCursor}}}}`.
  Descriptions are truncated with "…" by the tool; product ids are `gid://` URIs; variants are
  nested edges/node. Catalog context only.

## Result-shape quirks (what the parser expects — do not "fix" the files)

Pinned from captured live results; `scripts/shopify_rows.py` handles all of this:

- **The ShopifyQL envelope** is
  `{"query", "columns": [{"name", "dataType"}], "rows": [[str, ...]], "rowCount",
  "chartHint"?, "summaryMetric"?, "shopDomain"}`.
- **Rows are arrays of STRINGS**, positionally matched to `columns`. The parser coerces by
  `dataType`: INTEGER → int (digit strings like `"21915"`), MONEY → float (plain decimal
  strings like `"11020.94"`, no symbols/commas), STRING → verbatim.
- **PERCENT dataType = FRACTION values.** `conversion_rate` `"0.019803…"` means **1.98%**
  (verified `== purchases/sessions` exactly). Never multiply by 100 in a saved file — fractions
  are the CVR Signals unit, and `machine.py` converts fraction → percent exactly once at the
  payload boundary.
- **`summaryMetric.value` is a comma-formatted string of the sum over the RETURNED rows only**
  (never the universe: a products pull with `LIMIT 50` summarized 91,835.43 while the account
  total was 162,463.19). The parser uses it as a **parse checksum**, not a universe total.
  Because GROUP BY results are LIMIT-truncated, **always query `LIMIT 1000`** and let the build
  compare Σrows vs the no-GROUP-BY total — any tail gap earns an honest note.
- **AOV TRAP (validated live):** `average_order_value` (242.494) is NEITHER
  `total_sales/orders` (298.91) NOR `net_sales/orders` (252.66) — Shopify's AOV formula is its
  own. The column value is authoritative **verbatim**; it is never recomputed from totals,
  anywhere in the toolchain or in your narrative.
- **Error shape:** a failed query returns error prose plus the **echoed empty envelope** (empty
  `columns` + `rows`) wrapped in an injection-warning tag. The parser treats any result with
  empty columns/rows + error text as a `RawResultError` — fix the query and re-pull; never edit
  the saved file into shape.
- `shopDomain` is the **myshopify subdomain** (e.g. `x1y2z3-ab`), not the storefront domain —
  provenance only, never the report's store label.

## Which file unlocks which analytics field / signal

`machine.py` computes a field only when a source for it is present; anything missing is listed
under `skipped` with the reason and falls back to hand transcription. CSV exports outrank or
interleave with these pulls per the documented per-field precedence (see
`references/data-intake.md`).

| File | Machine analytics fields | Signals unlocked |
|---|---|---|
| `shop_info.json` | `meta.currency` (fill-if-blank), store label | provenance stamp |
| `analytics_funnel.json` | `analytics.funnel` (2nd precedence, after `shopify-conversion.csv`) | CVR Signals site block (sessions, conversions, Wilson CI, `n*` gate) |
| `analytics_device.json` | `analytics.device[]` (after `ga4-device.csv`) | device two-proportion z-tests incl. the Mobile-vs-Desktop headline z |
| `analytics_referrer.json` | `analytics.channels[]` (after `ga4-channels.csv` / `shopify-traffic-source.csv`) | channel z-tests; channels Concentration dimension |
| `analytics_landing.json` | `analytics.landing_pages[]` (after `ga4-landing.csv` / `shopify-landing.csv`) | page-level EB shrinkage + Wilson lower-bound ranking; landing-pages Concentration dimension |
| `analytics_products.json` | `analytics.revenue_concentration[]` (after `shopify-sales-product.csv`) | products Concentration dimension (HHI / Gini / ABC) |
| `analytics_totals.json` | `analytics.aov` (after `shopify-aov.csv`; **verbatim**) | AOV-band Read verdict |
| `analytics_customers.json` | — (order-share evidence note only; never `new_vs_returning`) | returning-customer evidence line |
| `orders.json` | — | context/provenance only |
| `products.json` | — | catalog context only |

`analytics.new_vs_returning` has **no MCP source** — it unlocks only via `ga4-new-returning.csv`
(see `references/data-intake.md`).
