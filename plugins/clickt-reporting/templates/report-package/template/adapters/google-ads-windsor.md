# Adapter: `google_ads` block ← Windsor.ai MCP (`google_ads` connector)

**Client instance:** PantryLot account `544-317-0313` ("adscale_ecom_PantryLot" in Windsor;
connected 2026-08-04). This is the ACTIVE Google adapter for PantryLot — the direct
google-ads-mcp recipe (`google-ads-mcp.md`) is the alternative once its OAuth is fixed.

## Pull

Windsor `get_data`, connector `google_ads`, `accounts: ["544-317-0313"]`:

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
  actions listed in `config.accounts.google_ads.revenue_conversion_actions`
  ("PM Revenue - Browser" + "PM Revenue - Conversion Booster").
- Same Google attribution as the profit stream, so POAS and ROAS are comparable ratios.
- Windows that predate ProfitMetrics have **no PM actions** (July 2025 used TagFly
  revenue tracking) — leave `revenue` null and drop value-based YoY comparisons there.

## Gotchas

- **Value semantics: PROFIT** (ProfitMetrics; the campaign is literally named
  "Pmax | Profitable tPOAS 75"). Template renders POAS. Never call it ROAS.
- **YoY:** resolved 2026-08-04 — July 2025 has no PM conversion actions (pre-ProfitMetrics,
  TagFly revenue tracking), so 2025 conversion value = revenue. Value-based YoY comparisons
  are omitted until a profit-tracked YoY window exists.
- Windsor `ctr` is a fraction here (unlike some connectors) — always cross-check
  clicks/impressions before mapping.
- Save raw responses verbatim to `periods/<id>/raw/google_windsor.json`.
