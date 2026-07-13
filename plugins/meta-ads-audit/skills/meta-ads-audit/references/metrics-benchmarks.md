# Metrics, Benchmarks & Scoring

Thresholds reflect a comprehensive Meta Ads account-audit framework. Each row
notes whether it is **fully measurable** from the Meta MCP, **proxied**, or **N/A (out of scope)**.
Treat thresholds as flags for a conversation, not absolute pass/fail truth — context (objective,
business model, flight) always wins.

---

## 1. Diagnostic thresholds

### Account architecture
| Check | Healthy | Flag | FAIL | MCP status |
|---|---|---|---|---|
| Top-3 campaigns share of spend | ≥ 60% | 45–60% | < 45% (over-fragmented) | Measurable (`amount_spent` by campaign) |
| Optimization events per ad set / 30d | ≥ 50 (≈ 25/wk after ramp) | 25–50 | < 25 (learning-starved) | Measurable (`results` per adset/30d) |
| Active campaign / ad-set count vs spend | few, well-funded | many thin | dozens < 25 results | Measurable |
| Prospecting : retargeting spend | ≈ 80 : 20 | 65:35–50:50 | retargeting > 50% | Proxy (audience classification) |
| Optimization goal vs objective alignment | aligned (e.g. OUTCOME_SALES → OFFSITE_CONVERSIONS/VALUE) | soft mismatch | hard mismatch (e.g. sales obj. optimizing LINK_CLICKS) | Measurable (`objective` vs `optimization_goal`) |
| Exclusions present on prospecting | customers/converters excluded | partial | none | Proxy (`custom_audiences` + naming) |

### Budget & pacing
| Check | Healthy | Flag | MCP status |
|---|---|---|---|
| Daily vs lifetime pacing | lifetime/rolling on evergreen winners | rigid daily caps on high-volume campaigns | Measurable (`daily_budget`/`lifetime_budget`) |
| Campaign with > 10% spend & < 5% of results | none | any (review) | Measurable (`amount_spent` vs `results` share) |
| Bid strategy intent | cost/bid cap or value where appropriate | undefined / default lowest-cost at scale w/o cap | Measurable (`bid_strategy`) |
| Spend trend / marginal direction | stable/improving CPR | rising CPR while spend flat | Measurable (`ads_insights_performance_trend`) |

### Attribution
| Check | Healthy | Flag | MCP status |
|---|---|---|---|
| Ad-set attribution window | `7d_click` (recommended) | many on `1d_view_*` | Measurable (`attribution_setting`) |
| Over-reliance on view/1-day | low | heavy `1d_view_1d_click` | Partial (configured window only) |
| 1DV vs 7DC conversion split | — | — | **N/A** (not exposed) |
| MER / NC-ROAS reality-check | — | — | **N/A** (needs backend) |

### Creative
| Check | Healthy | Flag | FAIL | MCP status |
|---|---|---|---|---|
| Thumb-stop rate (3s ÷ impr) | ≥ 25% | — | — | **N/A** — substitute below |
| ThruPlay (hold) rate (15s ÷ impr) | category-relative; track trend | sharp drop | — | Proxy for "hold" |
| Hold-through (P100 ÷ P25) | ≥ ~35–40% | < 35% (weak body) | — | Proxy for hook-to-hold |
| CTR-Link (ecom prospecting) | ≥ 0.8–1.0% | 0.5–0.8% | < 0.5% | Derived (`cost_per_action_type[link_click]`) or all-click fallback |
| Active distinct concepts (prospecting) | 6–10+ | 3–5 | < 3 | Measurable (distinct creatives w/ delivery) |
| Spend concentration (≤ 5 ads share of L90) | < 50% | 50–70% | > 70% (fragile) | Measurable |
| Frequency (prospecting, 7d) | < 3.0 | 3–5 | > 5 | Measurable (`frequency`) |
| Creative refresh cadence | new concepts every 7–14d | stale > 30d | none new > 60d | Proxy (`created_time` of active ads) |
| Format diversity | UGC/static/carousel/video/testimonial mix | 1–2 formats | single format | Measurable (`ads_get_creatives`) |

### Data infrastructure & future-proofing
| Check | Healthy | Flag | FAIL | MCP status |
|---|---|---|---|---|
| Dataset/pixel present & active | yes | — | none/inactive | Measurable (`ads_get_datasets`) |
| CAPI live (server events present) | SERVER_ONLY volume > 0 alongside web | server ≪ web | no server events | Measurable (`dataset_stats` by `event_source`) |
| Dedup signal (web & server both present) | both channels firing | one-sided | — | Proxy (channel split) |
| EMQ (Purchase) | ≥ 8.0 | 6–8 | < 6 | Measurable (`dataset_quality`) |
| Event freshness | recent | stale days | no recent uploads | Measurable (`dataset_quality`) |
| Key event volume | ≥ 25/wk | < 25/wk | ~0 on active campaign | Measurable (`dataset_stats`) |
| Catalog/feed health (ecom) | healthy | warnings | errors/out-of-stock served | Measurable (`catalog_get_dynamic_ads_health`) |
| Opportunity score | high | mid | low + critical recs | Measurable (`opportunity_score`) |

---

## 2. Severity weights (per check)

| Severity | Weight | Use for |
|---|---|---|
| Critical | 5.0 | Signal loss, no CAPI, learning-starved core campaigns, hard goal mismatch |
| High | 3.0 | Fragmentation, fragile creative concentration, heavy 1DV reliance, frequency > 5 |
| Medium | 1.5 | Daily-cap rigidity, weak hold-through, thin format diversity |
| Low | 0.5 | Naming hygiene, minor refresh-cadence drift |

**Auto-Flag → numeric:** `PASS = 1.0`, `FLAG = 0.5`, `FAIL = 0.0`, `N/A = excluded`.

---

## 3. Category weights & Health Score

Default category weights (sum = 100); structure + creative dominate:

| Category | Weight |
|---|---|
| Data Infrastructure & Signal | 20 |
| Account Architecture | 20 |
| Budget & Pacing | 15 |
| Attribution | 10 |
| Creative Performance | 25 |
| Future-Proofing | 10 |

> Competitive lever is qualitative — surfaced as findings, not scored (weight 0).

**Health Score** (0–100):
```
category_score   = Σ(flag_numeric × severity_weight) / Σ(severity_weight)  × 100   [over scored, non-N/A checks]
health_score     = Σ(category_score × category_weight) / Σ(category_weight present)
```
N/A checks are dropped from both numerator and denominator so out-of-scope items never penalize.

**Grade bands:** A ≥ 90 · B 75–89 · C 60–74 · D 40–59 · F < 40.

---

## 4. ICE prioritization (Findings → Roadmap)

`Priority = Impact × Confidence × Ease` (each 1–10 → 1–1000).

- **Impact (1–10):** 10 = > 15% account-level revenue/efficiency lift; 1–3 = polish.
- **Confidence (1–10):** 10 = documented Meta-platform evidence; 1–3 = speculative.
- **Ease (1–10):** 10 = < 15 min, reversible (e.g. attribution-window change, exclusion add);
  1 = quarter-long strategic work.
- **Quick Win flag:** `Ease ≥ 8 AND Impact ≥ 7`.

**Roadmap buckets:** 30-day ≥ 500 · 60-day 250–499 · 90-day 100–249 · Parking lot < 100.

Default severity → Impact seed: Critical 9 · High 7 · Medium 5 · Low 3 (auditor may override).
