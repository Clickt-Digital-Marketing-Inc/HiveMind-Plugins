# Executive Summary Deck — Slide Layout Notes

> Reference document for `build_pptx()` in `cm3_by_product.py`.
> Comment-only — no executable code. Edit this when the deck layout changes.

The deck always has **7 slides** in this order. The slide builder reads from
the `ctx` dict produced by `compute()` plus the `period` and `currency`
strings parsed from the Google Ads CSV.

## Brand application (every slide)

- **Title band:** `BRAND["yellow"]` (#F3B61C) full-width across top.
- **Title type:** Fraunces, 32–40pt, color = `BRAND["ink"]` (#0B0F0E).
- **Body type:** Inter, 14–18pt, color = `BRAND["ink"]`.
- **Big-number type:** Fraunces, 56–72pt, color = `BRAND["ink"]`.
- **Eyebrow / labels:** JetBrains Mono, 9–10pt, color = `BRAND["fg_dim"]` (#5C6361).
- **Surface:** `BRAND["paper"]` (#FFFFFF) background.
- **Band accents** (pills + chart bars): green for Excellent/High, amber for
  Average/Low, red for Poor.

## Slide 1 — Title

| Element        | Content                                                   |
| -------------- | --------------------------------------------------------- |
| Eyebrow        | "CLICKT · GOOGLE ADS SHOPPING — CM3 BY PRODUCT"           |
| Title          | "CM3 by Product — Executive Summary"                      |
| Subtitle       | Period (e.g. "Apr 1 – 30, 2026") · Currency               |
| Footer byline  | "Clickt — clickt.ca/tools"                                |

## Slide 2 — Headline KPIs

Stacked rows of big-number + label. One row per metric.

| Row | Label                | Source                                          |
| --- | -------------------- | ----------------------------------------------- |
| 1   | Total revenue        | `ctx["totals"].conv_value`                      |
| 2   | Total ad spend       | `ctx["totals"].cost`                            |
| 3   | CM3 $                | `ctx["totals"].cm3`                             |
| 4   | CM3 %                | `cm3 / revenue` (— if revenue == 0)             |
| 5   | ROAS                 | `revenue / ad spend` (— if ad spend == 0)       |
| 6   | MER                  | Same formula as ROAS for shopping-only data — labelled separately for exec clarity |

## Slide 3 — CM3 band distribution

Embedded clustered bar chart.

- Categories: `["Excellent", "High", "Average", "Low", "Poor"]`
- Values: `[ctx["by_band"][band].n_products for band in categories]`
- Bar colors per band:
  - Excellent → green (`#2D7A4A`)
  - High → green-soft (`#5BA89A`)
  - Average → amber (`#B8861B`)
  - Low → amber-soft (`#D99A0A`)
  - Poor → red (`#B33A28`)

## Slide 4 — Top 10 products by CM3$

Table, 5 columns: Title (truncate ~60 chars) · Revenue · CM3 $ · CM3 % · Band.

Selection: `sorted(products, key=lambda p: -p.cm3)[:10]`.

## Slide 5 — Bottom 10 products by CM3$

Same columns as Slide 4.

Selection:
`sorted([p for p in products if p.band in ("Low","Poor")], key=lambda p: p.cm3)[:10]`.

If fewer than 10 Low/Poor products exist, fill the remainder with the
lowest-CM3 active products to keep the table consistent.

## Slide 6 — Top 5 campaigns by CM3$

Table, 5 columns: Campaign · Products · Revenue · CM3 $ · CM3 %.

Selection: `sorted(by_campaign.items(), key=lambda kv: -kv[1].cm3)[:5]`.

## Slide 7 — What to do next

Three deterministic bullets, all derived from `ctx`:

1. **Pause N products in Poor band burning $X/mo.**
   - N = `ctx["by_band"]["Poor"].n_products`
   - X = `ctx["by_band"]["Poor"].cost`

2. **Scale top Excellent products generating $Y CM3.**
   - List up to top 3 Excellent products by CM3 $.
   - Y = sum of those 3.

3. **Investigate COGS for unresolved products** — only when
   `ctx["cogs_source_counts"].get("Input", 0) > 0` (i.e. blanket fallback
   fired). Otherwise replace with:
   **Reinvest top campaign CM3 — campaign \<top\> drove $Z CM3 at \<x\>%.**

Keep the same three bullets, in the same order, every run. No drift.
