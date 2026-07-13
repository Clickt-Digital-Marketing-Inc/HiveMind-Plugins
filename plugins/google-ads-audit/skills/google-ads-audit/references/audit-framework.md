# Audit Framework — 9 Steps + Google Deep Checks

Each check becomes one row in a `sections[].checks[]` entry of the findings JSON.
Set `result` to PASS / FLAG / FAIL / N/A and `severity` to Critical / High /
Medium / Low. Use N/A when the area doesn't apply (e.g. ecommerce check on a
lead-gen account, or data not obtainable via GAQL) — N/A is excluded from scoring.

**Severity guide:** Critical = money leak or broken measurement (5.0× weight);
High = material efficiency loss (3.0×); Medium = best-practice gap (1.5×);
Low = polish (0.5×). `applies_to`: `Lead Gen`, `Ecommerce`, or `Both`.

Default check IDs per tab (extend as the account warrants):

## 03 — Account Structure
| ID | Check | Pass when | Sev | Applies |
|----|-------|-----------|-----|---------|
| AS-01 | Consistent campaign naming | One convention incl. type + objective | Medium | Both |
| AS-02 | Brand vs non-brand separated | Brand isolated in own campaign | High | Both |
| AS-03 | No keyword cannibalization | Same high-intent kw not duplicated across campaigns | Medium | Both |
| AS-04 | Ad groups tightly themed | Coherent themes; not bloated (kw w/ impressions>0) | Medium | Both |
| AS-05 | Network/segmentation sane | Search/Display/PMax/Shopping segmented by intent | Medium | Both |

## 04 — Performance Review
| ID | Check | Pass when | Sev | Applies |
|----|-------|-----------|-----|---------|
| PR-01 | CTR at/above benchmark | Within vertical range (see benchmarks) | Medium | Both |
| PR-02 | CPA within 20% of target | Blended CPA near target | High | Lead Gen |
| PR-03 | ROAS at/above target | Conv value / cost ≥ target | High | Ecommerce |
| PR-04 | Search Impression Share healthy | Above benchmark | Medium | Both |
| PR-05 | Lost IS (Budget) controlled | < 10% | High | Both |
| PR-06 | Lost IS (Rank) controlled | < 20–25% | Medium | Both |
| PR-07 | No anomalous CPC spikes | No unexplained CPC/spend jumps | Medium | Both |

Put the actual numbers in each check's `observed` field; the `kpis[]` block renders
a scorecard on this tab.

## 05 — Keyword Strategy
| ID | Check | Pass when | Sev | Applies |
|----|-------|-----------|-----|---------|
| KW-01 | Negative keyword lists applied | ≥3 themed shared lists attached | Critical | Both |
| KW-02 | Wasted spend controlled | <5% spend on >$10 / 0-conv terms | High | Both |
| KW-03 | Legacy BMM reviewed | BROAD+Manual CPC examined, not left unmanaged | Medium | Both |
| KW-04 | Match-type balance | Exact for control, broad only w/ Smart Bidding | Medium | Both |
| KW-05 | No duplicate keywords | No dupes across ad groups/campaigns | Medium | Both |
| KW-06 | Intent alignment | Keywords match buy/compare/research intent | Medium | Both |

## 06 — Ad Creatives & Assets
| ID | Check | Pass when | Sev | Applies |
|----|-------|-----------|-----|---------|
| AD-01 | RSAs not ETAs | No deprecated expanded text ads | Medium | Both |
| AD-02 | Ad Strength ≥ Good | RSA/PMax strength Good or Excellent | Medium | Both |
| AD-03 | Core assets present | Sitelinks, callouts, structured snippets | Medium | Both |
| AD-04 | No disapproved ads | 0 disapprovals; policy clean | High | Both |
| AD-05 | Pinning used sparingly | Pins intentional, not over-constraining | Low | Both |

## 07 — Landing Pages
| ID | Check | Pass when | Sev | Applies |
|----|-------|-----------|-----|---------|
| LP-01 | No broken final URLs | No 404 / product-not-found (manual crawl) | High | Both |
| LP-02 | Message match | LP copy aligns with ad + keyword | Medium | Both |
| LP-03 | Mobile + speed (manual) | Fast LCP, mobile-friendly | Medium | Both |
*(LP-01/LP-03 usually N/A from GAQL — flag for manual review.)*

## 08 — Budget & Bidding
| ID | Check | Pass when | Sev | Applies |
|----|-------|-----------|-----|---------|
| BB-01 | Bidding strategy fits goal | tCPA (lead gen) / tROAS (ecommerce) | High | Both |
| BB-02 | No deprecated eCPC | Enhanced CPC not in use | Medium | Both |
| BB-03 | Budget follows performance | Spend concentrated in best campaigns | Medium | Both |
| BB-04 | Top campaigns not budget-capped | High-ROI campaigns not limited | High | Both |
| BB-05 | Targets realistic | tCPA/tROAS within ~20% of historical | High | Both |

## 09 — Tracking & Measurement
| ID | Check | Pass when | Sev | Applies |
|----|-------|-----------|-----|---------|
| TR-01 | Conversion actions valid | ≥1 ENABLED primary action recording | Critical | Both |
| TR-02 | Enhanced Conversions on | EC for Leads/Web enabled | High | Both |
| TR-03 | Consent Mode v2 (EU) | CMv2 if serving EU/EEA | Critical | Both |
| TR-04 | No duplicate conversion counting | One primary action per event | Critical | Both |
| TR-05 | GA4 linked | GA4 ↔ Google Ads linked (partly manual) | Medium | Both |
| TR-06 | Sensible counting type | "One"/"Every" matches goal type | Medium | Both |

## 10 — Audiences
| ID | Check | Pass when | Sev | Applies |
|----|-------|-----------|-----|---------|
| AU-01 | Remarketing lists active | Lists populated and eligible | Medium | Both |
| AU-02 | Exclusions sensible | No high-value audience excluded | Low | Both |
| AU-03 | Segmentation used | Audiences in observation/targeting per goal | Medium | Both |

## 11 — Scripts, Recommendations & Automation
| ID | Check | Pass when | Sev | Applies |
|----|-------|-----------|-----|---------|
| AT-01 | Recommendations triaged | Auto-apply off for budget/match-type recos | Medium | Both |
| AT-02 | Scripts reviewed (manual) | Account scripts current, non-conflicting | Low | Both |
| AT-03 | Automated rules sane | No conflicting rules | Low | Both |

## PMax deep checks (add where PMax exists)
| ID | Check | Pass when | Sev | Tab |
|----|-------|-----------|-----|-----|
| PM-01 | Asset groups complete | Full headlines/images/video per group | Medium | 06 |
| PM-02 | Audience signals set | Relevant signals per asset group | Medium | 10 |
| PM-03 | Search themes configured | Themes added to guide PMax | Low | 05 |
| PM-04 | Brand cannibalization low | <~15% conv from brand terms; brand exclusions set | High | 03 |

## Post-audit logic

**Findings** — turn every FAIL and material FLAG into a `findings[]` row with a
horizon (30/60/90). Critical/High → usually 30. The workbook seeds ICE Impact from
severity (Critical 9 / High 7 / Medium 5 / Low 3); the auditor fills Confidence and
Ease (1–10) so ICE = Impact × Confidence × Ease ranks the work.

**Health Score** — the workbook computes it: per check, earned = flag(PASS 1 /
FLAG 0.5 / FAIL 0) × severity weight; score = Σ earned / Σ possible × 100, N/A
excluded. Grade A ≥90, B 75–89, C 60–74, D 40–59, F <40.
