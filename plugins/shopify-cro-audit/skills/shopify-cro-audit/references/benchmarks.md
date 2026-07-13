# Benchmarks, Scoring & Prioritization

Source: aggregated FY2025 averages across 21 Shopify stores ($688M combined revenue). These are the
numbers baked into the workbook's named benchmark cells on `14_Reference` (editable — override them
and every grade recomputes on open).

## Funnel benchmarks (% of sessions)

| Stage | Benchmark | Named cell |
|-------|-----------|------------|
| Added to cart | **7.23%** | `bench_atc` |
| Reached checkout | **5.96%** | `bench_checkout` |
| Completed purchase (CVR) | **2.99%** (mean; median 2.81%) | `bench_cvr` |

Reading: the biggest leak is almost always **pre-ATC** — ~92.8% of visitors leave without adding
anything. ~17.6% drop between ATC and checkout; ~49.8% abandon after starting checkout.

## Device benchmarks (CVR)

| Device | Benchmark | Named cell |
|--------|-----------|------------|
| Mobile | **2.87%** | `bench_mobile` |
| Desktop | **4.51%** | `bench_desktop` |

Mobile is typically 40–60% below desktop. **This reflects purchase intent, not broken UX** — desktop
skews high-intent (deliberate sit-down buyers); mobile is discovery. Don't recommend cloning desktop
onto mobile. Do make mobile checkout frictionless (wallets, fast load) and warm cold mobile traffic.

## AOV → CVR context

CVR is inversely related to price. Stores under **$60** had a median CVR ~**4.63%**; stores over
**$200** had a median ~**0.95%**. Always read a store's CVR relative to its AOV band before judging it.

## Funnel Health Score (workbook headline)

`funnel_health` = `MIN(150, AVERAGE(rate_atc/bench_atc, rate_checkout/bench_checkout, rate_cvr/bench_cvr) × 100)`.
**100 = exactly at benchmark.** Grade bands:

| Grade | Funnel Health |
|-------|---------------|
| A | ≥ 110 |
| B | 90–109 |
| C | 70–89 |
| D | 50–69 |
| F | < 50 |

This grades only the **measured funnel** (Step 1). It is deliberately *not* a composite of the
qualitative steps — averaging subjective severities into a single score would be fabricated precision.
The real deliverable is the prioritized roadmap.

## Severity (for findings)

| Severity | Use for |
|----------|---------|
| Critical | Money leak / broken measurement / a primary-funnel blocker on a high-traffic page |
| High | Material efficiency loss; strong friction on a key page |
| Medium | Best-practice gap; meaningful but not blocking |
| Low | Minor polish |

Seed `impact` from severity (Critical ~9 / High ~7 / Medium ~5 / Low ~3), then adjust.

## Prioritization — `(Impact × 2) + Ease`  (NOT ICE)

| Factor | Question | Scale | Weight |
|--------|----------|-------|--------|
| Impact | How much will this move conversions **on a high-traffic page**? | 1–10 | **×2** |
| Ease | How fast to design, build, and launch? | 1–10 | ×1 |

`Priority = Impact×2 + Ease` (max 30). Confidence is **dropped on purpose**: when Impact is scored with
traffic + triangulation in mind, confidence is already baked in, and a separate 1–10 confidence score
just adds noise. The workbook computes Priority live and sorts the roadmap descending.

Roadmap buckets (live formula on `13_Roadmap`):

| Bucket | Priority |
|--------|----------|
| Now | ≥ 24 |
| Next | 20–23 |
| Soon | 15–19 |
| Later | < 15 |

## Triangulation

A finding present in multiple sources (e.g. analytics drop-off **and** heatmap **and** survey) is
higher-confidence and should carry higher Impact. `12_Findings_Log` shows a live **# sources** count
derived from each finding's comma-separated `step_sources`. Prefer multi-source findings at the top of
the roadmap.

## Test vs Ship

Not every fix is an A/B test. **Ship** low-risk, obviously-correct changes directly (broken links,
missing shipping info, a misleading price display, clear UX bugs). **Test** anything where the outcome
is uncertain or a wrong move could hurt — layout changes, pricing experiments, messaging angles. Set
`change_type` accordingly; for lower-page-section tests, require a scroll-depth trigger so non-viewers
don't dilute results.
