# Adapter: `meta` block ← Windsor.ai MCP (`facebook` connector)

**Client instance:** PantryLot ad account `1182016997374640` (connected in Windsor ✓). CAD.

## Pull

Use Windsor `get_data` with connector `facebook`, three date windows (current, prior, YoY):

- **Totals (per window):** fields `spend, impressions, clicks, ctr, cpc, cpm, reach, frequency, actions_purchase (or purchases), action_values_purchase (purchase conversion value = revenue)`, no grouping.
- **Daily trend (current window only):** same spend/revenue fields grouped by `date`.
- **Campaign table (current window only):** grouped by `campaign`, fields `campaign, spend, impressions, clicks, purchases, purchase value`.

Check `get_fields(connector: "facebook")` for exact field ids if a pull errors — Windsor
field naming varies (e.g. `actions_offsite_conversion_fb_pixel_purchase`).

## Map → contract

| Contract field | Windsor field |
|---|---|
| `spend` | `spend` |
| `impressions` / `clicks` | same |
| `ctr` | `ctr` (verify percent, not fraction — contract wants percent) |
| `cpc` / `cpm` | same |
| `reach` / `frequency` | same |
| `purchases` | purchase actions count |
| `revenue` | purchase action value |
| `profit` | `action_values_complete_registration` — ProfitMetrics carries profit on the complete-registration event (per John, 2026-08-04) |

## Profit stream

- `profit` ← `action_values_complete_registration`. This is a repurposed standard event:
  ProfitMetrics fires complete-registration with value = order gross profit. Sanity checks:
  event count ≤ purchases; implied margin ~28-34% (matches Google PM margin, NOT the
  ~57% store blended margin). Meta POAS = profit ÷ spend.

## Gotchas

- **Value semantics: revenue** (`config.sections.meta.conversion_value_is: "revenue"`). ROAS.
- Reach is not additive across windows; pull it per window, never sum days.
- Meta attribution window changes restate history — note `pulled_at` and don't expect
  yesterday's pull to match today's for the same window.
- Save the raw `get_data` responses verbatim to `periods/<id>/raw/meta_*.json` before mapping.
