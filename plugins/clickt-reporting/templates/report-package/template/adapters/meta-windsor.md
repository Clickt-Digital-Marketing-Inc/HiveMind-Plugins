# Adapter: `meta` block ← Windsor.ai MCP (`facebook` connector)

**Configure before use:** replace `<WINDSOR_META_AD_ACCOUNT_ID>` with the approved client
account and verify its currency and connector access.

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
| `profit` | a client-configured field only when its values are verified as profit; otherwise null |

## Profit stream

- Map `profit` only from the field named in the approved client configuration and only
  after independently verifying its semantics. Never infer profit from a standard event
  name. Meta POAS = verified profit ÷ spend.

## Gotchas

- **Value semantics: revenue** (`config.sections.meta.conversion_value_is: "revenue"`). ROAS.
- Reach is not additive across windows; pull it per window, never sum days.
- Meta attribution window changes restate history — note `pulled_at` and don't expect
  yesterday's pull to match today's for the same window.
- Save the raw `get_data` responses verbatim to `periods/<id>/raw/meta_*.json` before mapping.
