# Normalized Data Contract (`data.json`)

The template engine reads ONLY this shape. Adapters (any source: Windsor, platform MCPs, CSV)
produce it; `validate.mjs` enforces it. Source-specific knowledge stops at the adapter boundary.

## Conventions

- Currency values: client currency (see `config/client.json`), plain numbers, 2dp max.
- `ctr`, `conversion_rate`: **percent** (e.g. `2.45` = 2.45%). Store rates at **>=4dp**
  (never pre-round to display precision) — the engine derives deltas and attainment from
  stored values, and 2dp inputs make derived figures drift a full display unit.
- Rates ratios (`cpc`, `cpm`, `aov`, `frequency`): plain numbers.
- Dates: `YYYY-MM-DD`. Period ids: `YYYY-MM` (monthly) or `YYYY-Wnn` (weekly, ISO week).
- Any block may set `"available": false` with an `unavailable_reason` string — the template
  renders that section in a "data unavailable this period" state. Never approximate.
- `yoy` is nullable everywhere (first-year clients).
- Derived metrics (POAS, ROAS, MER, nCAC, deltas, funnel drop-offs, attainment) are computed
  by the engine at build time — adapters never precompute them. nCAC = total ad spend ÷
  store new customers; like MER it is suppressed unless every enabled channel's spend is
  present. `store.profit` and `store.new_customers` are optional source facts (nullable);
  tiles depending on them render only when present. Channel profit is never estimated: it renders
  only when the platform reports a client-configured, independently verified profit
  stream. A channel without one shows an explicit "not tracked" state.

## Envelope

```json
{
  "meta_envelope": {
    "period_type": "monthly",            // or "weekly"
    "period_id": "2026-07",              // or "2026-W32"
    "period_label": "July 2026",
    "date_range":  { "start": "2026-07-01", "end": "2026-07-31" },
    "prior_range": { "start": "2026-06-01", "end": "2026-06-30" },
    "yoy_range":   { "start": "2025-07-01", "end": "2025-07-31" },   // or null
    "partial_period": false,
    "pulled_at": "2026-08-04",
    "sources": { "google_ads": "google-ads-mcp", "meta": "windsor:facebook",
                 "store": "shopify-mcp", "traffic": "windsor:googleanalytics4" },
    "mtd": null,                         // weekly only — see Weekly extras
    "method_notes": ["optional extra disclosure lines appended to the rendered method notes"]
  }
}
```

## `google_ads`

```json
{
  "available": true,
  "unavailable_reason": null,
  "current": { "spend": 0, "impressions": 0, "clicks": 0, "ctr": 0, "cpc": 0,
               "conversions": 0, "conversion_value": 0, "revenue": null },
  "prior":   { /* same fields */ },
  "yoy":     null,
  "trend":   [ { "date": "2026-07-01", "spend": 0, "conversion_value": 0 } ],
  "campaigns": [ { "name": "", "spend": 0, "impressions": 0, "clicks": 0,
                   "conversions": 0, "conversion_value": 0 } ]
}
```

`conversion_value` basis comes from `config.sections.google_ads.conversion_value_is`
(`"profit"` → engine renders **POAS**, `"revenue"` → ROAS).
`revenue` is optional/nullable: a second, revenue-based value stream when the account tracks
one (for example, a configured set of revenue conversion actions). When present the engine also
renders a Revenue tile and revenue-based ROAS alongside POAS. When both streams are present,
`conversion_value` (profit) must not exceed `revenue`.

## `meta`

```json
{
  "available": true,
  "unavailable_reason": null,
  "current": { "spend": 0, "impressions": 0, "clicks": 0, "ctr": 0, "cpc": 0, "cpm": 0,
               "reach": 0, "frequency": 0, "purchases": 0, "revenue": 0, "profit": null },
  "prior":   { /* same fields */ },
  "yoy":     null,
  "trend":   [ { "date": "2026-07-01", "spend": 0, "revenue": 0 } ],
  "campaigns": [ { "name": "", "spend": 0, "impressions": 0, "clicks": 0,
                   "purchases": 0, "revenue": 0 } ]
}
```

## `store`

```json
{
  "available": true,
  "unavailable_reason": null,
  "current": { "sessions": 0, "orders": 0, "conversion_rate": 0, "aov": 0, "revenue": 0,
               "profit": null, "new_customers": null },
  "prior":   { /* same fields */ },
  "yoy":     null,
  "trend":   [ { "date": "2026-07-01", "revenue": 0, "orders": 0 } ],
  "top_products":    [ { "title": "", "revenue": 0, "units": 0 } ],
  "bottom_products": [ { "title": "", "revenue": 0, "units": 0 } ]   // optional, may be []
}
```

## `traffic`

```json
{
  "available": true,
  "unavailable_reason": null,
  "funnel": {
    "current": { "view_item": 0, "add_to_cart": 0, "begin_checkout": 0, "purchase": 0 },
    "prior":   { /* same fields */ }
  },
  "channels": [ { "channel": "Paid Search", "sessions": 0, "revenue": 0, "conversion_rate": 0 } ]
}
```

## Weekly extras

Weekly `data.json` uses the same blocks (trend/campaign/product tables optional) plus
`meta_envelope.mtd` for goal pacing:

```json
"mtd": { "range": { "start": "2026-08-01", "end": "2026-08-09" },
         "store_revenue": 0, "total_ad_spend": 0, "orders": 0, "new_customers": null }
```

## Validator sanity checks (`validate.mjs`)

Errors (abort build): missing/negative required fields; funnel not monotonically decreasing;
derived-metric inconsistency beyond tolerance — `ctr ≈ clicks/impressions·100` (10%),
`cpc ≈ spend/clicks` (5%), `aov ≈ revenue/orders` (2%),
`conversion_rate ≈ orders/sessions·100` (10%); campaign spend sum exceeding block spend by >2%;
trend sums off block totals by >5%.
Warnings (build continues): unavailable blocks, missing yoy, empty tables, partial period.
