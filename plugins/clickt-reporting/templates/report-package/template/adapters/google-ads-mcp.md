# Adapter: `google_ads` block ← google-ads-mcp (direct GAQL)

**Configure before use:** replace `<GOOGLE_ADS_CUSTOMER_ID>` and
`<GOOGLE_ADS_LOGIN_CUSTOMER_ID>` with approved client values.

## MCC login boundary

The google-ads-mcp authenticates through a manager account set by
`GOOGLE_ADS_LOGIN_CUSTOMER_ID`. If the client account is not under that manager, queries
fail with an access error. Fix the approved manager configuration and restart the server.
Verify access first with `customers_list_accessible_customers`.

## Pull (GAQL via `search_search`)

Per window (current / prior / YoY), resource `customer` for totals:

```sql
SELECT metrics.cost_micros, metrics.impressions, metrics.clicks, metrics.ctr,
       metrics.average_cpc, metrics.conversions, metrics.conversions_value
FROM customer WHERE segments.date BETWEEN 'YYYY-MM-DD' AND 'YYYY-MM-DD'
```

Daily trend (current window): same fields `FROM customer` + `segments.date`, one row/day.
Campaign table (current window): same fields `FROM campaign` + `campaign.name`,
`WHERE campaign.status != 'REMOVED'`, order by cost desc.

## Map → contract

| Contract field | GAQL field | Transform |
|---|---|---|
| `spend` | `metrics.cost_micros` | ÷ 1,000,000 |
| `impressions` / `clicks` | direct | |
| `ctr` | `metrics.ctr` | × 100 (API returns fraction; contract wants percent) |
| `cpc` | `metrics.average_cpc` | ÷ 1,000,000 |
| `conversions` | `metrics.conversions` | |
| `conversion_value` | `metrics.conversions_value` | |

## Gotchas

- **Value semantics: PROFIT** (client rule; `conversion_value_is: "profit"` in client.json).
  The template renders POAS. Never call it ROAS in commentary.
- Currency is the account currency (CAD) — no conversion needed.
- Save raw responses verbatim to `periods/<id>/raw/google_*.json` before mapping.
