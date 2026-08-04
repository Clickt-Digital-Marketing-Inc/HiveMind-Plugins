# Adapter: `traffic` block ← GA4 via Windsor.ai MCP (`googleanalytics4`)

**Client instance:** property `507568174` — "PantryLot | Revenue | ProfitMetrics".
(A parallel property `507576481` tracks profit-based values; the traffic/funnel block uses
the **Revenue** property so funnel counts and channel revenue read in familiar terms.)

## Pull

Windsor `get_data`, connector `googleanalytics4`, filtered to the property:

- **Funnel (current + prior windows):** event counts for `view_item`, `add_to_cart`,
  `begin_checkout`, `purchase` (dimension: `eventName`, metric: `eventCount` — or the
  dedicated `addToCarts`, `checkouts`, `ecommercePurchases` metrics if exposed).
- **Channels (current window):** dimension `sessionDefaultChannelGroup`; metrics
  `sessions`, `totalRevenue` (or `purchaseRevenue`), `transactions`/`ecommercePurchases`.

Use `get_fields(connector: "googleanalytics4")` to confirm exact ids before the first pull.

## Map → contract

- `funnel.current/prior.{view_item, add_to_cart, begin_checkout, purchase}` ← event counts.
- `channels[]`: `channel` ← channel group label; `sessions`; `revenue`;
  `conversion_rate` ← transactions ÷ sessions × 100, stored at >=4dp (compute at adapter
  level from the same pull — do not mix sources inside one row; never pre-round rates to
  2dp, the engine derives deltas/attainment from stored values).

## Store profit + new customers (added 2026-08-04)

- `store.profit` ← `purchase_revenue` pulled from the **Profit property** (`507576481`,
  "PantryLot | Profit | ProfitMetrics") — same metric id, different property; its purchase
  values are profit. Sanity: store margin runs ~56-57%.
- `store.new_customers` ← `first_time_purchasers` (Revenue property `507568174`).
- Weekly `mtd.new_customers` ← same field for the month-to-date range.

## Gotchas

- Funnel steps must be monotonically decreasing; if GA4 returns purchase > begin_checkout
  (tracking gap), mark the block `available: false` with the reason rather than shipping
  a nonsensical funnel. The validator enforces this.
- GA4 thresholding can suppress small rows; note it in commentary if visible.
- Save raw responses to `periods/<id>/raw/ga4_*.json`.
