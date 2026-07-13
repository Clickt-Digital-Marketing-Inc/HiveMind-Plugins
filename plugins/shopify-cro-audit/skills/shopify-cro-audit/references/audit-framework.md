# Audit Framework — the 11 analyses

The execution map for each step: the key question, the method, what to extract, the payload key it
feeds, and the workbook tab it renders to. **Organize by analysis method, not page type** — that is
the framework's central thesis. The strongest findings are **triangulated**: the same problem showing
up in analytics + behavior + customer voice. Capture `step_sources` on every finding so triangulation
is visible.

Each step writes to `steps_detail.<key>` (qualitative) and/or `analytics` (Step 1), and contributes
`findings[]`. Set `meta.steps[]` status to `run` / `partial` / `not_run` for every step.

---

## Step 1 — GA4 & Shopify Analytics → `analytics` → `02_Analytics`
**Q: Where does traffic go, and what does the buying funnel actually look like?**
- **Landing pages & concentration:** top entry pages by sessions; which one page dominates. This sets
  where Impact is highest — weight every later finding by the traffic of the page it touches.
- **Funnel:** sessions → add-to-cart → reached-checkout → purchase. Transcribe the rates GA4/Shopify
  already report into `analytics.funnel` (`atc_rate`, `checkout_rate`, `cvr` as % of sessions). The
  workbook grades them against the benchmarks. The biggest leak is usually pre-ATC.
- **Device:** mobile vs desktop CVR. Report separately. Frame the gap as **purchase intent**, not
  broken UX — do not recommend cloning desktop onto mobile.
- **Channels:** CVR by channel; mismatches between highest-traffic and highest-converting channels.
- **New vs returning:** returning convert 2–5×; an unusually wide gap = weak first-visit trust.
- **Revenue concentration:** the 1–2 hero SKUs driving 50%+ of sales — focus PDP testing there.

## Step 2 — Heuristic Analysis (LIFT Model) → `steps_detail.heuristic` → `03_Heuristic_LIFT`
**Q: On the main funnels, are conversion drivers missing or inhibitors present?**
Start where the traffic is (Step 1), on the device users use (usually mobile), in funnel order.
WebFetch the store + top landing page. Evaluate every page/section against the six LIFT factors and
log `{page, lift_factor, severity, observed, recommendation}`:

| LIFT factor | Lens |
|-------------|------|
| **Value Proposition** (core) | Is the cost↔benefit clear? If not, nothing else matters. |
| **Relevance** (driver) | Does the page match how the visitor arrived (the ad/source)? |
| **Clarity** (driver) | Is the value prop + CTA immediately obvious? |
| **Urgency** (driver) | Any reason to act now? |
| **Anxiety** (inhibitor) | What doubts/risks remain (trust, guarantees, terms)? |
| **Distraction** (inhibitor) | What pulls attention from the goal? |

Every finding gets a severity AND a specific test, never just "this is bad."

## Step 3 — Review Mining → `steps_detail.review_mining` → `04_Review_Mining`
**Q: What objections block buying, what drives it, and what words do customers use?**
Analyze **all** reviews. Categorize by theme and **quantify** each theme's share (`themes[].pct`).
Negative/3-star reviews carry the richest objections. Extract three lists:
- `objections` — "I almost didn't buy because…", "I was worried about…" → highest-priority fixes.
- `drivers` — what convinced them (often differs from what the brand markets).
- `voice` — verbatim phrases to reuse in copy/ads/PDP.

## Step 4 — Customer Support → `steps_detail.support` → `05_Customer_Support`
**Q: What do buyers ask before, and complain about after?**
From the 5-question questionnaire, log `{question_or_complaint, category, site_gap}`. Pre-purchase
questions = trust gaps the PDP should answer proactively. The fastest path to quick wins.

## Step 5 — Heatmaps & Scrollmaps → `steps_detail.heatmaps` → `06_Heatmaps`
**Q: How far do users scroll, what do they click, what do they ignore?**
Per key page, **mobile and desktop separately**, log `{page, device, metric, observation}`:
- Scroll depth to ATC / reviews / comparison sections.
- Most-clicked elements; dead clicks (false affordances); dead zones (removal/repositioning candidates).
- **Scroll-depth trap:** low reach to a section ≠ unimportant — the few who get there are highest
  intent. When recommending a test on a lower section, note that a scroll-depth trigger is required.

## Step 6 — Post-Purchase Survey → `steps_detail.post_purchase_survey` → `07_PostPurchase_Survey`
**Q: Why did they buy, what almost stopped them, how did they really find you?**
- `near_abandonment` — the most valuable list (active conversion killers).
- `triggers` — tipping-point factors to amplify.
- `attribution[]` — survey "how did you hear" vs GA4 %; large gaps reveal an attribution blind spot.

## Step 7 — Email Long Survey → `steps_detail.email_survey` → `08_Email_Survey`
**Q: What are the deeper motivations, objections, and decision journeys?**
Targets buyers 30–90 days out; ≥200 responses. Log `{insight_type, finding, pct_or_n}` covering:
problem being solved, most/least-liked, the one thing they needed to know before buying, why-us-over-
competitor. Surfaces blockers post-purchase surveys miss (the buyer already committed).

## Step 8 — User Testing → `steps_detail.user_testing` → `09_User_Testing`
**Q: How do real first-time visitors experience the site — and what frustrates them?**
5 think-aloud testers, browse → ATC → checkout → impressions. The gold is unprompted reactions
("where's the price?", "this looks fake"). Log `{tester_or_theme, quote, issue}`.

## Step 9 — Marketing Strategy → `steps_detail.marketing` → `10_Marketing_Match`
**Q: Does the site deliver on the ad's promise?**
Log `{area, observed, gap}` across: **ad-to-page message match** (top creatives vs landing page above
the fold), **promo cadence** (>4 sales in 6 months likely trains customers to wait), **free-shipping
threshold vs hero price**, and **channel CVR gaps** (a low-CVR channel is often a landing-experience
problem, not a traffic problem).

## Step 10 — Competitor Analysis → `steps_detail.competitor` → `11_Competitor`
**Q: How do offer, experience, and value prop compare to direct competitors?**
WebFetch 3–5 competitors. Build:
- `offer_table` — price, subscription discount, bundles, guarantee, shipping side by side.
- `atf` — above-the-fold (mobile) comparison: headline, star rating, trust badges, primary CTA.
- `messaging_gaps` — angles no competitor uses that your customer voice (Step 3) says matter.

## Step 11 — Testing Roadmap → `findings` → `12_Findings_Log` + `13_Roadmap`
**Q: How do dozens of findings become a focused, high-impact plan?**
- **Triangulate:** a problem in analytics + heatmap + customer voice outranks a single-source one.
- **Prioritize with `(Impact × 2) + Ease`** (1–10 each). **Do not use ICE** — Confidence is dropped
  on purpose (triangulation already encodes it). The workbook computes Priority live.
- **Impact accounts for page traffic** (Step 1). **Ease** = speed to design/build/launch.
- **Test vs Ship:** set `change_type`. Ship low-risk obvious fixes (broken link, missing shipping info,
  clear UX bug) directly; Test uncertain layout/pricing/messaging changes.

---

## Turning observations into findings

Every notable observation across steps 1–10 becomes a `findings[]` entry:
`{id, title, step_sources[], severity, page, evidence, recommendation, impact, ease, change_type, expected_lever}`.
- `step_sources` = which analyses surfaced it (drives the live triangulation count). List **all** that apply.
- Seed `impact` from severity (Critical ~9 / High ~7 / Medium ~5 / Low ~3) then adjust for page traffic
  and triangulation. Set `ease` by build effort/risk.
- `severity` ∈ Critical/High/Medium/Low. `change_type` ∈ Test/Ship.
