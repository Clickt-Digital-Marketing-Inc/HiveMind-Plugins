# Goals schema (v2)

`config/goals.json` holds goal sets; the newest set whose `effective_from` ≤ the period
start is active. Change targets by adding a new set, never by editing history. The reporting
**dashboard's Goals section** (the client index page) edits the active set visually and
exports this exact JSON.

```json
{
  "version": 2,
  "goal_sets": [
    {
      "effective_from": "2026-07-01",
      "status": "proposed",            // or "agreed" — proposed renders a badge
      "goals": [ /* goal objects */ ]
    }
  ]
}
```

## Goal object

| Field | Required | Meaning |
|---|---|---|
| `id` | ✓ | unique within the set; a month-specific goal with the same id overrides the default that month |
| `metric` | ✓ | one of the metric catalog ids below |
| `target` | ✓ | number, in the metric's natural unit (percent metrics: `2.4` = 2.4%) |
| `label` | | display name override (useful for SKU goals) |
| `direction` | | `"higher"` (default) or `"lower"` (e.g. nCAC, CPA-style targets) |
| `period` | | `"monthly"` (default — applies every month) or `"YYYY-MM"` for one month only (seasonal targets) |
| `sku_match` | sku metrics | case-insensitive substring matched against product titles |
| `format` | | formatter override (`currency0`, `currency2`, `int`, `pct1`, `pct2`, `ratio`) |

## Metric catalog

Store: `store_revenue`, `store_profit`, `orders`, `new_customers`, `sessions`,
`conversion_rate`, `aov` · Blended: `total_ad_spend`, `mer`, `ncac` (lower-is-better by
default) · Google: `google_spend`, `google_revenue`, `google_profit`, `google_poas`,
`google_roas` · Meta: `meta_spend`, `meta_revenue`, `meta_profit`, `meta_roas`,
`meta_poas`, `meta_purchases` · SKU: `sku_units`, `sku_revenue` (require `sku_match`).

Volume metrics pro-rate in the weekly pulse's MTD pace; rates/ratios hold steady.
A goal whose metric has no data this period renders its row without judgment ("—").

## SKU goals and data

SKU goals resolve against `store.sku_metrics` (preferred) or `store.top_products`.
If a client has SKU goals, the store adapter must pull those SKUs each cycle into
`store.sku_metrics: [{ "title": "", "revenue": 0, "units": 0 }]` — a goal against a
product missing from the pull shows "no data", never a guess.

## Update loop

1. Open the reporting dashboard (client index page) → **Goals** section → adjust targets / add goals → **Export JSON**.
2. Hand the JSON back (paste or file) — it replaces `config/goals.json` verbatim.
3. Rebuild; every report from then on judges against the new targets.
