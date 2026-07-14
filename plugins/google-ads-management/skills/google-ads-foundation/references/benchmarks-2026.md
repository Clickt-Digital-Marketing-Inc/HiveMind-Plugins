# Benchmarks & Thresholds (2025–2026)

Thresholds used across the suite. Industry numbers are starting points — always prefer the
account's own trailing 90-day baseline when enough data exists. Drawn from current industry PPC
benchmarks and Google Ads platform guidance.

## Google Search benchmarks (cross-industry averages)

| Metric | Typical avg | Read it as |
|---|---|---|
| CTR (Search) | ~6.6% | < 3% on an ad group = relevance problem |
| Avg CPC (Search) | ~$5.26 | Rising CPC + flat conv = auction pressure or low QS |
| Conversion rate | ~7.5% | < half your account baseline = LP or intent issue |
| Cost per lead | ~$70 | Varies 5–10× by industry; trend matters more than absolute |
| Quality Score | 7–10 good · 5–6 watch · ≤4 act | Drives CPC and Ad Rank |
| Search impression share | ≥ 0.65 healthy | Lost-IS (budget) and lost-IS (rank) tell you which lever |

## Red-flag triggers (account health)

| Red flag | Trigger | Severity |
|---|---|---|
| Ad-group keyword sprawl | ≥ 20 active keywords in one ad group AND ad-group CTR < 3% | High |
| No campaign-level negatives | 0 campaign negative keywords on a Search campaign | High |
| Naming inconsistency | campaign names don't match the agreed regex | Medium |
| Automation without data | automated bid strategy + < 30 conversions in trailing 30 days | Critical |
| PMax brand cannibalization | PMax running with no brand exclusion/negative list while a brand Search campaign exists | High |

3+ red flags present → remediate structure before scaling spend (recovers ~20–35% of wasted budget).

## Bidding — data thresholds

- **Automation needs ~30+ conversions / campaign / 30 days** (Google's learning needs ~50 in 30
  days to exit the learning phase cleanly).
- **Daily budget ≥ ~5× target CPA** for stable Smart Bidding delivery.

### Data Maturity Score (0–100) → strategy

`Score = ConversionVolume×0.4 + ConversionValueVariance×0.3 + TrackingConfidence×0.3`

- ConversionVolume = min(conversions_per_month, 100).
- ConversionValueVariance = 100 − (coefficient_of_variation × 100). High variance (e.g. $50 and
  $5,000 orders) lowers it.
- TrackingConfidence: 100 = Enhanced Conversions + offline/CRM import + validation; 50 = basic
  conversion tracking; 0 = unreliable/missing.

| Score | Strategy |
|---|---|
| 0–30 Low | Manual CPC or Maximize Clicks (gather data) |
| 31–50 Emerging | Enhanced CPC |
| 51–70 Moderate | Target CPA or Maximize Conversions |
| 71–85 Mature | Target ROAS or Maximize Conversion Value |
| 86–100 Advanced | Target ROAS + Smart Bidding Exploration |

### 5 early-warning signals (automation failing)

| Signal | Trigger | Action |
|---|---|---|
| tCPA enabled, CPA spikes | +40% within 72h of switch | pause automation; gather 30+ conv on manual first |
| tROAS switch, IS drops | impression share −20%+ immediately | relax ROAS target 15–20% or use Max Conv. Value |
| spend up, conv flat | spend +30% with flat conversions | audit search terms; add negatives; tighten targeting |
| QS drops across ad groups | within 2 weeks of automation | narrow match types; expand negatives |
| stuck "Learning" | ≥ 14 days | consolidate low-volume campaigns or revert to manual |

## Keywords / search terms (SQR cadence)

- Audit cadence: **weekly** for spend ≥ $10k/mo, **bi-weekly** for $2k–$10k, **monthly** below $2k.
- Buckets: conversions ≥ 3 → add exact; clicks ≥ 10 & conv = 0 → negative; informational → route
  or exclude; competitor/junk → shared negative list.
- Account-level junk negatives: free, jobs, careers, diy, cheap, salary, images, meme.

## Quality Score forensics (act when QS ≤ 4–5)

- Step 1: search terms with CTR < 2% and ≥ 50 impressions drag Expected CTR.
- Step 2: mobile CTR < 1.5% → cut mobile bid adj 30–50% or fix mobile LP.
- Step 4: < 80% of keywords have an exact-phrase match in a headline → ad relevance issue.
- Step 5: keyword with impressions > 100, CTR < 1%, 0 conv → pause.
- Remediation timeline: days 1–7 no change, 8–14 begins, 15–30 full recovery. If no recovery by
  day 30, root cause is landing page or ad relevance, not Expected CTR.

## Budget & pacing

- Pacing target: month-to-date spend should track ~(days elapsed / days in month) of the monthly
  cap, ±10–15%. Flag > ±15% as over/under-pacing.
- **Scaling: never raise a budget > 20% at once** (resets learning).
- **3× kill rule:** an ad group/keyword that has spent ≥ 3× target CPA with 0 conversions is a
  candidate to pause.
- MER (Marketing Efficiency Ratio) = total revenue / total ad spend, tracked at account level.

## Remarketing tiers (audience targeting)

| Tier | Audience | Membership | Bid adj |
|---|---|---|---|
| High-intent abandoners | reached checkout/pricing, no convert | 7–14 days | +50% to +100% |
| Mid-funnel engagers | product/service pages, no checkout | 14–30 days | +20% to +40% |
| Past converters | converted in last 90–180 days | 90–180 days | +10% to +30% (cross/upsell) |

Exclude converters from the last 7 days from prospecting/remarketing.
