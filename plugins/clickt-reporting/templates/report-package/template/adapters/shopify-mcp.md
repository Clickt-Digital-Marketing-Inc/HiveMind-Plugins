# Adapter: `store` block ← Shopify MCP (preferred) / GA4 fallback

**Client instance:** PantryLot (`www.pantrylot.com`, CAD).

## Preferred source: Shopify MCP

Pull per window (current / prior / YoY):

- Totals: sessions (Shopify analytics), orders, total sales/revenue, from which
  `aov = revenue ÷ orders` and `conversion_rate = orders ÷ sessions × 100`.
- Daily trend (current window): revenue + orders per day.
- Top products (current window): title, orders, revenue — top 5 by revenue.

> **Status 2026-08-04:** the Shopify MCP server (`stg-gap0n8`) did not finish connecting in
> the build session, so its exact tool names are undocumented. On the next cycle, list its
> tools first and record the exact calls here. Until then the fallback below applies.

## Fallback source: GA4 (property 507568174)

Same shapes from GA4 ecommerce metrics: `sessions`, `ecommercePurchases`/`transactions`
(orders), `purchaseRevenue` (revenue), daily by `date`; top products by `itemName` with
`itemsPurchased` + `itemRevenue`.

**Honesty rule:** GA4 numbers are analytics-tracked, not Shopify's order ledger — they will
undercount slightly. This is a *different source*, not an approximation: set
`meta_envelope.sources.store` to `windsor:googleanalytics4` so the method notes disclose it,
and prefer switching back to Shopify MCP when available. Never mix Shopify and GA4 numbers
inside the same block.

## Gotchas

- Shopify "total sales" includes/excludes taxes+shipping depending on the report — pick one
  definition, note it here, and keep it stable across periods.
- Refunds land on the refund date, which can make daily revenue negative — the contract
  allows it; the validator's non-negativity check applies to period totals, not trend days.
- Save raw pulls to `periods/<id>/raw/store_*.json`.
