# Data Intake — exactly what to ask for, where to export it, and which fields are required

This is the canonical intake spec. For every dataset: **where it lives, how to export it, and the
columns the audit needs.** Prompt the user one block at a time. Validate each file exists before
continuing. If a dataset is not provided, mark its step **`not_run`** in the payload — never fabricate.

Convention: ask the user to drop files into the working folder (or paste an absolute path). Glob the
cwd first (`ga4-*.csv`, `shopify-*.csv`, `reviews*.csv`, `fairing*.csv`/`kno*.csv`, `typeform*.csv`)
and only prompt for what is missing.

> **Shopify MCP connected?** The MCP path (`references/shopify-pulls.md`) covers most of Tier 1
> without any Shopify exports — the GA4 CSVs remain the only source for per-page depth, device,
> channels, and new-vs-returning. Both paths combine under `--raw-dir` + `--csv-dir`; the machine
> layer owns the per-field precedence below.

---

## Canonical `--csv-dir` filenames (the machine layer's contract)

`build_cro_audit.py --csv-dir` discovers exports **by these exact filenames**; each file is
parsed deterministically by `scripts/manual_csv.py`, which enforces the required columns as a
wrong-report guard (a mismatched export fails loudly — `ManualCsvError` — rather than
mis-parsing). Save/rename the user's exports to these names in one folder.

> **NEEDS-REAL-EXPORT-VALIDATION:** the parsers are encoded from documented GA4/Shopify export
> headers and have not yet been validated against real export files. Any header drift trips the
> wrong-report guard; confirm against genuine exports before trusting the CSV path for client
> work.

| Filename | Export (recipe below) | Required columns (guard) | Fields / signals unlocked |
|---|---|---|---|
| `ga4-landing.csv` | GA4 Landing pages report | `Landing page + query string` (or `Landing page`), `Sessions` | `analytics.landing_pages[]` (**1st precedence**); page-level CVR Signals; landing-pages Concentration |
| `ga4-funnel.csv` | GA4 Funnel exploration | `Step`, `Active users`/`Users` | `analytics.funnel` (**last-resort fallback** — GA4 counts USERS, not sessions; basis noted) |
| `ga4-device.csv` | GA4 Tech overview / Device category | `Device category`, `Sessions` | `analytics.device[]` (**1st**); device z-tests |
| `ga4-channels.csv` | GA4 Traffic acquisition | `Session default channel group`, `Sessions` | `analytics.channels[]` (**1st**); channel z-tests; channels Concentration |
| `ga4-new-returning.csv` | GA4 New / established | `New / established` (variants accepted), `Sessions`/`Active users` | `analytics.new_vs_returning` (**ONLY source** — no MCP equivalent); NvR z-test |
| `shopify-conversion.csv` | Shopify Conversion over time + funnel | `Sessions` + funnel-stage columns (cart / checkout / converted) | `analytics.funnel` (**PRIMARY funnel source**) |
| `shopify-sales-product.csv` | Shopify Sales by product | `Product title`, `Net sales` (or Total/Gross sales) | `analytics.revenue_concentration[]` (**1st**); products Concentration |
| `shopify-traffic-source.csv` | Shopify Sales/sessions by traffic source | `Referrer source`/`Traffic source`, `Sessions` | `analytics.channels[]` (2nd, after GA4) |
| `shopify-landing.csv` | Shopify Sessions by landing page | `Landing page path`/`Landing page`, `Sessions` | `analytics.landing_pages[]` (2nd, after GA4) |
| `shopify-customers.csv` | Shopify first-time vs returning customers | `Customer type` (variants accepted) + ≥1 numeric column | returning-customer **evidence** (order-share, not a CVR) |
| `shopify-aov.csv` | Shopify Average order value | `Average order value` | `analytics.aov` (**1st**; taken **verbatim** — AOV is never recomputed from totals) |

Per-field precedence when the MCP path is also present (first usable source wins; funnel stages
are **never mixed across sources**): funnel `shopify-conversion.csv` > `analytics_funnel.json` >
`ga4-funnel.csv`; device/channels/landing/new-vs-returning **GA4 CSV first**, then Shopify
CSV/MCP; revenue concentration + AOV **Shopify CSV first**, then MCP. Sources diverging by more
than 10% on total sessions earn an honest note in the report.

Units: cells containing `%` are read as percent; GA4 `*rate*` columns without `%` default to
fractions; a parsed site CVR above 20% aborts as mis-scaled units. All Tier 1 exports should
share **one date window** (90 days recommended).

---

## TIER 1 — CORE (required to run Step 1; the audit's foundation)

The whole framework starts with traffic + funnel data: a small win on a high-traffic page beats a big
win on a page nobody visits. Without Tier 1 you cannot weight Impact correctly.

### GA4 (Google Analytics 4) — 5 exports
GA4 is the only source for per-page sessions site-wide, device-level CVR, and segment funnels.
Export each report as CSV (in any GA4 report: top-right **Share → Download file → CSV**; in an
Exploration: **Export** top-right).

| # | Report (path in GA4) | Required columns |
|---|----------------------|------------------|
| 1 | **Landing pages** — Reports → Engagement → Landing page | `Landing page + query string`, `Sessions` (and `Key events`/`Session conversion rate`, `Total revenue` if shown) |
| 2 | **Funnel** — Explore → Funnel exploration; steps: `session_start` → `add_to_cart` → `begin_checkout` → `purchase` | step name, `Users`/`Sessions` at each step, completion/abandonment rate |
| 3 | **Device** — Reports → Tech → Overview (or Explore by `Device category`) | `Device category`, `Sessions`, `Session conversion rate` (or key events / sessions) |
| 4 | **Channels** — Reports → Acquisition → Traffic acquisition (by `Session default channel group`) | `Session default channel group`, `Sessions`, `Session key event rate`/CVR, `Total revenue` |
| 5 | **New vs returning** — Explore, dimension `New / established` (or Reports → Retention) | `New/returning`, `Sessions`, conversion rate |

Verbatim prompt:
```
I need 5 GA4 CSV exports (last 90 days unless you prefer another window):
1. Landing pages — Reports → Engagement → Landing page → Share → Download CSV.
2. Funnel — Explore → Funnel exploration with steps session_start → add_to_cart → begin_checkout → purchase → Export.
3. Device — Reports → Tech → Overview (or Explore by Device category) with Sessions + Session conversion rate.
4. Channels — Reports → Acquisition → Traffic acquisition by Session default channel group (Sessions, CVR, Revenue).
5. New vs returning — Explore by New/established (or Retention).
Drop them in this folder (name them ga4-landing.csv, ga4-funnel.csv, etc.) and tell me when ready.
```

### Shopify Analytics — sales, AOV, channel
Admin → **Analytics → Reports**. Open each report, set the date range, then **Export → CSV**.

| Report | Required columns |
|--------|------------------|
| **Sales by product** (Total sales by product) | product title, net/total sales, units, orders |
| **Sales by traffic source** / referrer | source, sessions, orders, conversion rate, sales |
| **Sessions by landing page** | landing page, sessions (Shopify's per-entry-page proxy) |
| **Conversion over time** + the funnel summary on the Analytics dashboard | sessions, added-to-cart, reached-checkout, sessions converted (%) |
| **Customers: first-time vs returning** | new vs returning orders / conversion |
| **Average order value** (this period vs last) | AOV value, trend |

Verbatim prompt:
```
From Shopify admin → Analytics → Reports, export these as CSV (same date range as GA4):
- Sales by product, Sales by traffic source, Sessions by landing page, Conversion over time
  (plus the funnel summary numbers from the Analytics dashboard), First-time vs returning customers, and AOV.
Drop them in this folder (shopify-*.csv). If a report is missing, the Shopify Sidekick prompts below get the numbers fast.
```

Shopify Sidekick quick-pull fallback (paste into the Sidekick box in Shopify admin):
- "What are my top landing pages by sessions in the last 30 days?"
- "What were my top 10 products by revenue in the last 90 days?"
- "What is my online store conversion rate for the last 30 days vs the previous 30 days?"
- "Show me a breakdown of sales by traffic source for the last 90 days."
- "How many returning customers purchased in the last 30 days vs new customers?"
- "What is my average order value this month compared to last month?"

> **Shopify vs GA4:** Shopify gives sessions by *landing* page but cannot report sessions/users for a
> page reached via internal navigation. For per-page sessions, device-level CVR, and segmented funnels,
> use GA4. Use both: Shopify for commerce/sales truth, GA4 for traffic/behavior depth.

---

## TIER 2 — STORE URLS (no file; enables Steps 2 & 10 via WebFetch)

Ask for the **store URL** + the **top landing-page URL** from Step 1 (the page most paid traffic hits),
and **3–5 competitor URLs**. The skill WebFetches these to run the LIFT heuristic (Step 2) and the
offer/above-the-fold comparison (Step 10). If no URL is given, those steps fall back to auditor notes.

```
Give me: (a) your store URL, (b) the product/landing page most of your paid traffic lands on, and
(c) 3–5 competitor store URLs. I'll load them and run the heuristic + competitor comparison myself.
```

---

## TIER 3 — PER-STEP SUPPLEMENTARY (each unlocks one step; "Not run" if absent)

### Step 3 — Reviews (review mining)
Export **all** reviews (not a sample; negative reviews carry the best objections).
- **Judge.me:** admin → Judge.me → Settings → Export reviews → CSV.
- **Okendo / Yotpo / Loox / Stamped:** Reviews app → Export / Data export → CSV.
- Required columns: `rating`, `title`, `body`/review text, `product`, `date`, `verified` (if present).

### Step 4 — Customer support (questionnaire, no export)
Send these 5 questions to whoever answers customer inquiries:
1. What do customers complain about most?
2. Top 3 questions from potential buyers (pre-purchase)?
3. What about the offer/pricing confuses people?
4. Top 3 complaints after purchase?
5. How are these common questions usually answered?

### Step 5 — Heatmaps / scrollmaps
- **Microsoft Clarity (free)** or **Hotjar / Lucky Orange**. Need ≥2 weeks of data on the key pages.
- Provide per key page, **mobile and desktop separately**: scroll-depth % to ATC / reviews / comparison
  table, top clicked elements, dead clicks, dead zones. Screenshots or noted metrics both work.

### Step 6 — Post-purchase survey
- **Fairing / KnoCommerce / Enquire** → export responses CSV. Required: response date, question, answer.
- The 4 questions that matter: how did you hear about us; what made you start thinking about a product
  like this; what convinced you to order today; **what nearly stopped you from ordering**.

### Step 7 — Email long survey
- **Typeform / Google Forms → Sheets**, exported CSV. ~7–10 questions; **≥200 responses** for
  significance; target buyers from the last 90 days (exclude the last 7). Always incentivized.

### Step 8 — User testing
- **UserBrain** (or similar): 5 first-time testers matching the target demographic, think-aloud through
  browse → add to cart → checkout → final impressions. Provide session notes/transcripts (or Loom links).

### Step 9 — Marketing strategy
- Top-performing ad creatives (**Meta Ads Library** links/screenshots), channel CVR (from Step 1 GA4),
  the **promo calendar for the last 6 months** (count of sitewide sales), and the **free-shipping
  threshold vs the hero product price**.

### Step 10 — Competitor (pairs with Tier 2 URLs)
- 3–5 competitor URLs (auto-fetched). Optionally: notes from actually buying through a competitor's
  funnel (every upsell, cross-sell, post-purchase offer, email).

---

## What "enough data" means per step

| Step | Minimum to mark `run` |
|------|-----------------------|
| 1 Analytics | GA4 funnel + landing pages + device, and Shopify sales/AOV |
| 2 Heuristic | Store URL (WebFetch) **or** auditor walkthrough notes |
| 3 Review mining | A reviews export with ≥~100 reviews |
| 4 Support | At least the complaints + top-questions answers |
| 5 Heatmaps | Scroll/click data or screenshots for ≥1 key page, mobile + desktop |
| 6 Post-purchase | Survey export with a usable response count |
| 7 Email survey | ≥~200 responses |
| 8 User testing | ≥3 session transcripts/notes |
| 9 Marketing | Top ad creatives + channel CVR + promo cadence |
| 10 Competitor | ≥3 competitor URLs or detailed notes |

Anything below the minimum → `partial` (note what's thin) or `not_run` (note what to collect next).
