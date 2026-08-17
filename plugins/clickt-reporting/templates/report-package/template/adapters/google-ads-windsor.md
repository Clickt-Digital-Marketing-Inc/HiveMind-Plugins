# Adapter: `google_ads` block ← Windsor.ai MCP (`google_ads` connector)

**Configure before use:** replace `<WINDSOR_GOOGLE_ADS_ACCOUNT_ID>` with the approved
client account and verify connector access. Use the direct google-ads-mcp recipe only when
that approved connection is available.

## Pull

Windsor `get_data`, connector `google_ads`, `accounts: ["<WINDSOR_GOOGLE_ADS_ACCOUNT_ID>"]`:

- **Totals (per window — current / prior / YoY):** fields
  `spend, impressions, clicks, ctr, cpc, conversions, conversions_value`.
- **Daily trend (current window):** `date, spend, conversions_value`.
- **Campaign table (current window):** `campaign, spend, impressions, clicks, conversions, conversions_value`.

## Map → contract

| Contract field | Windsor field | Transform |
|---|---|---|
| `spend` | `spend` | round 2dp |
| `impressions` / `clicks` | direct | |
| `ctr` | `ctr` | × 100 (Windsor returns a fraction, e.g. 0.0197 → 1.97) |
| `cpc` | `cpc` | round 2dp |
| `conversions` | `conversions` | fractional (data-driven attribution) — keep decimals, template renders as int |
| `conversion_value` | `conversions_value` | round 2dp |

## Revenue stream (added 2026-08-04)

- `google_ads.*.revenue` ← sum of the **PM Revenue** conversion actions, pulled with
  fields `conversion_action_name, all_conversions, all_conversions_value` and summing the
  actions listed in `config.accounts.google_ads.revenue_conversion_actions`.
- Same Google attribution as the profit stream, so POAS and ROAS are comparable ratios.
- Windows without the configured revenue actions leave `revenue` null and omit
  value-based YoY comparisons.

## Gotchas

- **Value semantics:** derive from `config.sections.google_ads.conversion_value_is`; never
  infer profit or revenue from campaign names. Render POAS for verified profit and ROAS
  for revenue.
- **YoY:** compare value only when both windows use the same verified semantics.
- Windsor `ctr` is a fraction here (unlike some connectors) — always cross-check
  clicks/impressions before mapping.
- Save raw responses verbatim to `periods/<id>/raw/google_windsor.json`.
