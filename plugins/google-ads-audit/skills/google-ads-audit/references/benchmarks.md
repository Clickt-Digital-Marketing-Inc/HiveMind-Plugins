# Benchmarks & ICE Scoring

Directional benchmarks for flagging KPIs. Always prefer the account's own
historical baseline over generic ranges — these are sanity checks, not targets.
Use the `business_model` switch (Lead Gen vs Ecommerce) to pick the column.

## Search KPI benchmarks
| Metric | DTC Ecommerce | B2C Lead Gen | B2B / SaaS | Notes |
|--------|---------------|--------------|------------|-------|
| Search CTR | 4–6% | 4–7% | 2–5% | Brand >> non-brand |
| Avg CPC | $0.50–$2 | $2–$8 | $4–$15 | Highly vertical-dependent |
| Conversion rate | 1.5–3% | 3–8% | 2–5% | Landing-page dependent |
| CPA | varies | target-driven | target-driven | Judge vs client target |
| ROAS | ≥ target | n/a | n/a | Ecommerce profitability |
| Search Impression Share | >65% | >65% | >60% | Below = budget/rank loss |
| Lost IS (Budget) | <10% | <10% | <10% | High = under-funded |
| Lost IS (Rank) | <20% | <20% | <25% | High = Quality Score / bid |
| Quality Score (cost-wtd) | ≥7 | ≥7 | ≥6 | Improves CPC & Ad Rank |
| Wasted spend | <5% | <5% | <10% | >$10 & 0-conv terms |

## How to flag a KPI
- **PASS** — within or better than the benchmark / client target.
- **FLAG** — within ~25% of the threshold, or trending the wrong way.
- **FAIL** — materially worse (e.g. CPA > 40% over target; Lost IS Budget > 20%).

## Reading impression share
- High **Lost IS (Budget)** → raise budget or improve efficiency; budget is the cap.
- High **Lost IS (Rank)** → improve Quality Score (expected CTR, ad relevance,
  landing-page experience) or bids; Ad Rank is the cap.
- High Search IS **and** low conversion volume → reaching everyone but not converting;
  look at intent/targeting, not budget.

## ICE prioritization (post-audit)
Score each finding **Impact × Confidence × Ease**, each 1–10.
- **Impact** — how much it moves spend efficiency / conversions / revenue.
  Seeded from severity: Critical 9, High 7, Medium 5, Low 3 (adjust if warranted).
- **Confidence** — how sure the change works, given account data and experience.
- **Ease** — how little effort/risk to implement (10 = trivial).

Highest ICE first. A high-Impact / low-ICE item (hard or low-confidence) can still
be worth a small test. Map findings to a 30/60/90 roadmap:
- **30 days** — quick wins + critical fixes (broken tracking, wasted spend, negatives).
- **60 days** — structural changes (brand split, bidding migration, budget reallocation).
- **90 days** — strategic/testing (new audiences, landing-page tests, PMax expansion).

## Modern Google notes (2025–2026)
- **eCPC is deprecated** — migrate to tCPA / tROAS / Max Conversions(/Value).
- **Enhanced Conversions** materially improve measurement; enable for Leads/Web.
- **Consent Mode v2** is required for EU/EEA serving to preserve modeling.
- **Demand Gen** replaced Video Action Campaigns — migrate remaining VACs.
- **PMax** runs on inputs: asset-group completeness, audience signals, search themes,
  and brand exclusions matter as much as budget.
