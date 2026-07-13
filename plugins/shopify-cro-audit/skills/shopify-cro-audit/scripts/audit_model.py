#!/usr/bin/env python3
# Copyright (c) 2026 Clickt Digital Marketing Inc. All rights reserved.
"""Canonical audit model + scoring constants for shopify-cro-audit.

Single source of truth for the Funnel Health / (Impact x 2) + Ease math shared by
THREE renderers: the xlsx workbook (`build_cro_workbook.py` imports these constants
into its cell formulas), the markdown record (`audit_md.py`), and the interactive
HTML explorer (`audit_html.py` mirrors the constants verbatim in its embedded JS
kernel). Keeping the numbers in one place — and asserting the mirror in
`tests/test_audit.py` — is what stops the three views from disagreeing.

Ported from meta-ads-audit `scripts/audit_model.py`. Key deltas:

* The CRO framework has NO check IDs: eleven method-steps, of which only Step 1
  (GA4 & Shopify analytics) is quantitative. `sections` is therefore the fixed
  11-step list (STEPS), each carrying a run/partial/not_run status from
  meta.steps[] and `evidence` as a LIST of labeled {label, columns, rows} tables
  (the meta renderer's single evidence table, generalized).
* Scoring is Funnel Health 0-150, NOT the lever-weighted check score:
      health = MIN(150, 100 x mean(rate/bench over MEASURED stages))
  mirroring the workbook's ISNUMBER-weighted SUMPRODUCT on 01_Executive_Summary:
  blank/unmeasured stages are EXCLUDED from the mean (never scored as 0). Excel
  ROUNDs the result to 0dp and the grade formula reads the ROUNDED cell, so the
  Python mirror is `_round_half_up(x, 0)` (Excel ROUND parity — never banker's
  rounding) and `grade()` is applied to the INT score. `score_unrounded` is kept
  in the model for tests.
* Prioritization is (Impact x 2) + Ease — deliberately NOT ICE (the framework
  dropped Confidence on purpose; triangulation already encodes it). Buckets:
  Now >=24 / Next >=20 / Soon >=15 / Later <15.
* `stem()` -> "cro-audit_{slug}_{date}".

BENCH / SEV_CANON / CHANGE_CANON / STATUS_CANON / AOV band strings / Read-verdict
strings byte-match build_cro_workbook.py's cell formulas (the workbook imports
them back from here).

Stdlib only. Deterministic: a pure function of the payload — there is NO wall
clock in this module (`generated` / meta.generated_for_date are inputs).
"""
from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP

# --- Canonical scoring constants (mirrored verbatim by audit_html.py's JS kernel,
#     and imported by build_cro_workbook.py; parity is asserted in tests) -----------

# Funnel benchmarks — aggregated across 21 Shopify stores, FY2025 averages
# (% of sessions for atc/checkout/cvr; CVR % for mobile/desktop).
BENCH = {
    "atc": 7.23,        # added to cart
    "checkout": 5.96,   # reached checkout
    "cvr": 2.99,        # completed purchase
    "mobile": 2.87,
    "desktop": 4.51,
}

HEALTH_MAX = 150
GRADE_CUTOFFS = [(110, "A"), (90, "B"), (70, "C"), (50, "D"), (0, "F")]
READ_BELOW_FACTOR = 0.7  # rate >= bench*0.7 -> "Below benchmark" (vs "Well below")
SEVERITY_IMPACT = {"Critical": 9, "High": 7, "Medium": 5, "Low": 3}
DEFAULT_EASE = 5  # neutral 1-10 default for Ease (and impact fallback on unknown severity)
PRIORITY_BUCKETS = [(24, "Now"), (20, "Next"), (15, "Soon"), (0, "Later")]

# AOV -> CVR-context bands. Strings byte-match the 02_Analytics "AOV CVR band"
# cell formula in build_cro_workbook.py: <60 / <=200 / >200.
AOV_BANDS = [
    (60.0, "Sub-$60 band — peers median CVR ~4.63%"),
    (200.0, "$60–$200 band"),
    (None, "Over-$200 band — peers median CVR ~0.95%"),
]

# Machine Read verdicts — byte-match the 02_Analytics "Read" column formula.
READ_AT_ABOVE = "At / above benchmark"
READ_BELOW = "Below benchmark"
READ_WELL_BELOW = "Well below benchmark"

# Controlled vocabularies (byte-identical to build_cro_workbook.py, which imports
# them from here). Drift silently distorts grading, so normalize on build and
# warn (not error) on anything unmappable.
SEV_CANON = {"critical": "Critical", "high": "High", "medium": "Medium", "low": "Low"}
CHANGE_CANON = {"test": "Test", "ship": "Ship"}
STATUS_CANON = {"run": "run", "partial": "partial", "not_run": "not_run", "not run": "not_run"}

# The eleven CRO method-steps — (step, tab, title, steps_detail key); order is
# canonical everywhere (model, workbook tabs, renderers). tab/title strings
# byte-match build_cro_workbook.py's STEP_TABS. Step 1 is built from the
# payload's `analytics` block (detail key None); Step 11 is the roadmap — the
# findings panel IS its content, so it carries no evidence tables of its own.
STEPS = [
    (1, "02_Analytics", "Step 1 — GA4 & Shopify Analytics", None),
    (2, "03_Heuristic_LIFT", "Step 2 — Heuristic Analysis (LIFT Model)", "heuristic"),
    (3, "04_Review_Mining", "Step 3 — Review Mining", "review_mining"),
    (4, "05_Customer_Support", "Step 4 — Customer Support Analysis", "support"),
    (5, "06_Heatmaps", "Step 5 — Heatmap & Scrollmap Analysis", "heatmaps"),
    (6, "07_PostPurchase_Survey", "Step 6 — Post-Purchase Survey Analysis", "post_purchase_survey"),
    (7, "08_Email_Survey", "Step 7 — Email Long Survey Analysis", "email_survey"),
    (8, "09_User_Testing", "Step 8 — User Testing Analysis", "user_testing"),
    (9, "10_Marketing_Match", "Step 9 — Marketing Strategy Analysis", "marketing"),
    (10, "11_Competitor", "Step 10 — Competitor Analysis", "competitor"),
    (11, "13_Roadmap", "Step 11 — Testing Roadmap", None),
]

# Funnel stages: (payload rate key, BENCH key, stage label, payload count key).
# Labels byte-match the 02_Analytics funnel rows.
FUNNEL_STAGES = [
    ("atc_rate", "atc", "Added to cart", "atc"),
    ("checkout_rate", "checkout", "Reached checkout", "checkout"),
    ("cvr", "cvr", "Completed purchase", "purchases"),
]

_FINDING_KEYS = ("id", "title", "step_sources", "severity", "page", "evidence",
                 "recommendation", "change_type", "expected_lever")


def slugify(s: str) -> str:
    """Lowercase, collapse non-alphanumerics to single hyphens, trim. Filename-safe."""
    out = re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")
    return out or "audit"


def grade(score) -> str:
    """Letter for a Funnel Health score. The caller passes the INT score — the
    workbook's grade formula reads the ROUNDED funnel_health cell."""
    if score is None:
        return "—"
    for cutoff, letter in GRADE_CUTOFFS:
        if score >= cutoff:
            return letter
    return "F"


def _round_half_up(x, nd: int = 0) -> float:
    """Excel ROUND parity: round half AWAY from zero, never banker's rounding.

    Python's built-in round() is banker's (round(2.5) == 2); Excel ROUND(2.5, 0)
    is 3. Quantizing the repr() of the float also matches Excel on decimal-looking
    inputs (2.675 -> 2.68 at 2dp, where binary-float banker's gives 2.67).
    """
    q = Decimal(1).scaleb(-nd)
    return float(Decimal(repr(float(x))).quantize(q, rounding=ROUND_HALF_UP))


def _num(v):
    """Strict numeric or None — Excel ISNUMBER parity for the measured-stage test.

    Only real int/float values count (bool excluded). Numeric STRINGS return None:
    a rate transcribed as text into the workbook is ISNUMBER()=FALSE there and
    must be excluded here too, or Python and Excel would grade different funnels.
    """
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _num_loose(v):
    """Numeric Impact/Ease value or None (missing / blank / non-numeric).

    Looser than _num on purpose: Excel ARITHMETIC coerces numeric text ("8"*2
    computes), so numeric strings are accepted for the priority math. Integral
    floats collapse to int so embeds stay clean."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        num = v
    else:
        s = str(v).strip() if v is not None else ""
        if not s:
            return None
        try:
            num = float(s)
        except ValueError:
            return None
    if isinstance(num, float) and num.is_integer():
        return int(num)
    return num


def priority(impact, ease) -> int:
    """Roadmap priority = (Impact x 2) + Ease. NOT ICE — Confidence was dropped
    on purpose (triangulation already encodes it). Max 30."""
    p = impact * 2 + ease
    if isinstance(p, float) and p.is_integer():
        p = int(p)
    return p


def bucket_for(priority_value) -> str:
    """PRIORITY_BUCKETS lookup: first threshold <= priority wins."""
    for threshold, label in PRIORITY_BUCKETS:
        if priority_value >= threshold:
            return label
    return PRIORITY_BUCKETS[-1][1]


def read_verdict(rate_pct, bench_pct) -> str:
    """Machine Read for a rate vs its benchmark (both PERCENT units).

    Byte-mirrors the 02_Analytics Read formula:
      rate >= bench          -> "At / above benchmark"
      rate >= bench * 0.7    -> "Below benchmark"
      else                   -> "Well below benchmark"
    Blank/non-numeric rate or bench -> "" (no verdict; e.g. Tablet has no bench).
    """
    rv = _num(rate_pct)
    bv = _num(bench_pct)
    if rv is None or bv is None:
        return ""
    if rv >= bv:
        return READ_AT_ABOVE
    if rv >= bv * READ_BELOW_FACTOR:
        return READ_BELOW
    return READ_WELL_BELOW


def aov_band(aov) -> str:
    """AOV CVR band string (byte-mirrors the 02_Analytics band formula):
    <60 sub-$60 / <=200 $60-$200 / >200 over-$200. Blank -> ""."""
    av = _num(aov)
    if av is None:
        return ""
    if av < AOV_BANDS[0][0]:
        return AOV_BANDS[0][1]
    if av <= AOV_BANDS[1][0]:
        return AOV_BANDS[1][1]
    return AOV_BANDS[2][1]


def funnel_health(rates: dict) -> tuple:
    """(unrounded, int_score, grade) for a funnel-rates dict (PERCENT units).

    rates keys: atc_rate / checkout_rate / cvr. Mirrors the workbook's
    ISNUMBER-weighted formula: mean of rate/bench over ONLY the measured
    (numeric) stages — blank stages are excluded, never scored as 0 — then
    MIN(150, 100 x mean), ROUND half-up to 0dp, grade on the INT score.
    No measured stages -> (None, None, "—")  (Excel shows "N/A" / "—").
    """
    rates = rates or {}
    ratios = []
    for rate_key, bench_key, _label, _count_key in FUNNEL_STAGES:
        rv = _num(rates.get(rate_key))
        if rv is None:
            continue
        ratios.append(rv / BENCH[bench_key])
    if not ratios:
        return (None, None, "—")
    unrounded = min(float(HEALTH_MAX), 100.0 * (sum(ratios) / len(ratios)))
    score = int(_round_half_up(unrounded, 0))
    return (unrounded, score, grade(score))


def stem(payload: dict, brand: str = "") -> str:
    """Tool-owned filename stem: cro-audit_{slug}_{date}.

    slug from meta.store_name | brand | meta.store_url; date from
    meta.generated_for_date (YYYY-MM-DD). Works on the payload OR the computed
    model — both carry a "meta" mapping with the same keys.
    """
    meta = (payload or {}).get("meta", {}) or {}
    slug = slugify(meta.get("store_name") or brand or meta.get("store_url") or "audit")
    raw_date = str(meta.get("generated_for_date") or "")
    date = slugify(raw_date[:10]) if raw_date else "undated"
    return "cro-audit_%s_%s" % (slug, date)


# --- evidence builders (labels mirror the workbook's section_label strings) -------

def _device_bench_key(device) -> str | None:
    """Prefix-matched device benchmark: mob* -> mobile, desk* -> desktop, else
    None (Tablet/other rows get NO benchmark and NO machine Read — pinned trap)."""
    d = str(device or "").lower()
    if d.startswith("mob"):
        return "mobile"
    if d.startswith("desk"):
        return "desktop"
    return None


def _index_vs_bench(rate, bench):
    """Index (100 = bench) as the half-up-rounded int Excel DISPLAYS (format "0"),
    or "" when the rate is not measured."""
    rv = _num(rate)
    bv = _num(bench)
    if rv is None or bv is None or bv == 0:
        return ""
    return int(_round_half_up(rv / bv * 100.0, 0))


def _step1_evidence(analytics) -> list:
    """Step 1 bespoke evidence: funnel KPI table (Stage/Count/Rate %/Benchmark %/
    Index/Read with machine Reads) + device / channels / landing pages /
    revenue-concentration / new-vs-returning+AOV tables."""
    a = analytics or {}
    if not a:
        return []
    funnel = a.get("funnel", {}) or {}
    tables = []

    # Funnel KPI table. Sessions row is the 100% base ("Funnel base" read).
    sessions = funnel.get("sessions", "")
    rows = [["Sessions", sessions, (100 if _num(sessions) is not None else ""),
             "", "", "Funnel base"]]
    for rate_key, bench_key, label, count_key in FUNNEL_STAGES:
        rate = funnel.get(rate_key, "")
        bench = BENCH[bench_key]
        rows.append([label, funnel.get(count_key, ""), rate, bench,
                     _index_vs_bench(rate, bench), read_verdict(rate, bench)])
    tables.append({
        "label": "Conversion funnel (vs FY2025 DTC benchmarks)",
        "columns": ["Stage", "Count", "Rate %", "Benchmark %", "Index", "Read"],
        "rows": rows,
    })

    rows = []
    for d in a.get("device") or []:
        dev = d.get("device", "")
        cvr = d.get("cvr", "")
        bkey = _device_bench_key(dev)
        bench = BENCH[bkey] if bkey else ""
        rows.append([dev, d.get("sessions", ""), cvr, bench,
                     _index_vs_bench(cvr, bench) if bkey else "",
                     read_verdict(cvr, bench) if bkey else ""])
    tables.append({
        "label": "Device segmentation (frame the mobile gap as intent, not broken UX)",
        "columns": ["Device", "Sessions", "CVR %", "Benchmark %", "Index", "Read"],
        "rows": rows,
    })

    tables.append({
        "label": "Acquisition — conversion rate by channel",
        "columns": ["Channel", "Sessions", "CVR %", "Revenue"],
        "rows": [[c.get("channel", ""), c.get("sessions", ""), c.get("cvr", ""),
                  c.get("revenue", "")] for c in (a.get("channels") or [])],
    })

    tables.append({
        "label": "Top landing pages (traffic concentration → where to focus)",
        "columns": ["Landing page", "Sessions", "Share %"],
        "rows": [[p.get("page", ""), p.get("sessions", ""), p.get("share_pct", "")]
                 for p in (a.get("landing_pages") or [])],
    })

    tables.append({
        "label": "Revenue concentration (hero SKUs)",
        "columns": ["Product", "Revenue", "Share %"],
        "rows": [[p.get("product", ""), p.get("revenue", ""), p.get("share_pct", "")]
                 for p in (a.get("revenue_concentration") or [])],
    })

    nvr = a.get("new_vs_returning", {}) or {}
    aov = a.get("aov", "")
    tables.append({
        "label": "New vs. returning & AOV",
        "columns": ["Metric", "Value"],
        "rows": [
            ["New-visitor CVR %", nvr.get("new_cvr", "")],
            ["Returning-visitor CVR %", nvr.get("returning_cvr", "")],
            ["Average order value", aov],
            ["AOV CVR band", aov_band(aov)],
        ],
    })
    return tables


def _ev_heuristic(d) -> list:
    return [{
        "label": "LIFT factors: Value Proposition · Relevance · Clarity · Urgency · Anxiety · Distraction",
        "columns": ["Page / section", "LIFT factor", "Severity", "Observed", "Test recommendation"],
        "rows": [[f.get("page", ""), f.get("lift_factor", ""), f.get("severity", ""),
                  f.get("observed", ""), f.get("recommendation", "")]
                 for f in (d.get("findings") or [])],
    }]


def _ev_review_mining(d) -> list:
    return [
        {"label": "Theme distribution (% of reviews mentioning — may exceed 100%)",
         "columns": ["Theme", "% of reviews"],
         "rows": [[t.get("theme", ""), t.get("pct", "")] for t in (d.get("themes") or [])]},
        {"label": "Objections (what almost stopped them)",
         "columns": ["Objection"],
         "rows": [[o] for o in (d.get("objections") or [])]},
        {"label": "Purchase drivers (what convinced them)",
         "columns": ["Driver"],
         "rows": [[o] for o in (d.get("drivers") or [])]},
        {"label": "Customer voice (verbatim phrases to reuse in copy)",
         "columns": ["Phrase"],
         "rows": [[o] for o in (d.get("voice") or [])]},
    ]


def _ev_support(d) -> list:
    return [{
        "label": "Support questions & complaints → site gaps",
        "columns": ["Question / complaint", "Category", "Site gap → proactive fix"],
        "rows": [[r.get("question_or_complaint", ""), r.get("category", ""),
                  r.get("site_gap", "")] for r in (d.get("rows") or [])],
    }]


def _ev_heatmaps(d) -> list:
    return [{
        "label": "Heatmap / scrollmap observations",
        "columns": ["Page", "Device", "Metric (scroll / click / dead zone)", "Observation → action"],
        "rows": [[r.get("page", ""), r.get("device", ""), r.get("metric", ""),
                  r.get("observation", "")] for r in (d.get("rows") or [])],
    }]


def _ev_post_purchase(d) -> list:
    return [
        {"label": "What nearly stopped you from ordering (active conversion killers)",
         "columns": ["Near-abandonment factor"],
         "rows": [[x] for x in (d.get("near_abandonment") or [])]},
        {"label": "What convinced you to order (triggers to amplify)",
         "columns": ["Purchase trigger"],
         "rows": [[x] for x in (d.get("triggers") or [])]},
        {"label": "Attribution check — survey 'how did you hear' vs GA4",
         "columns": ["Channel", "Survey %", "GA4 %", "Gap / note"],
         "rows": [[x.get("channel", ""), x.get("survey_pct", ""), x.get("ga4_pct", ""),
                   x.get("note", "")] for x in (d.get("attribution") or [])]},
    ]


def _ev_email_survey(d) -> list:
    return [{
        "label": "Survey insights",
        "columns": ["Insight type", "Finding", "% / n"],
        "rows": [[r.get("insight_type", ""), r.get("finding", ""), r.get("pct_or_n", "")]
                 for r in (d.get("rows") or [])],
    }]


def _ev_user_testing(d) -> list:
    return [{
        "label": "User-testing sessions",
        "columns": ["Tester / theme", "Verbatim quote", "Friction → fix"],
        "rows": [[r.get("tester_or_theme", ""), r.get("quote", ""), r.get("issue", "")]
                 for r in (d.get("rows") or [])],
    }]


def _ev_marketing(d) -> list:
    return [{
        "label": "Marketing ↔ site match",
        "columns": ["Area (ad-match / promo / channel gap)", "Observed", "Gap → action"],
        "rows": [[r.get("area", ""), r.get("observed", ""), r.get("gap", "")]
                 for r in (d.get("rows") or [])],
    }]


def _ev_competitor(d) -> list:
    offer = d.get("offer_table") or {}
    atf = d.get("atf") or {}
    return [
        {"label": "Offer & pricing comparison",
         "columns": list(offer.get("columns") or
                         ["Brand", "Price", "Subscription discount", "Bundles", "Guarantee", "Shipping"]),
         "rows": [list(r) for r in (offer.get("rows") or [])]},
        {"label": "Above-the-fold comparison (mobile)",
         "columns": list(atf.get("columns") or
                         ["Brand", "Headline", "Star rating", "Trust badges", "Primary CTA", "Notes"]),
         "rows": [list(r) for r in (atf.get("rows") or [])]},
        {"label": "Messaging gaps / untapped angles",
         "columns": ["Gap or angle no competitor is using"],
         "rows": [[x] for x in (d.get("messaging_gaps") or [])]},
    ]


_STEP_EVIDENCE = {
    "heuristic": _ev_heuristic,
    "review_mining": _ev_review_mining,
    "support": _ev_support,
    "heatmaps": _ev_heatmaps,
    "post_purchase_survey": _ev_post_purchase,
    "email_survey": _ev_email_survey,
    "user_testing": _ev_user_testing,
    "marketing": _ev_marketing,
    "competitor": _ev_competitor,
}


# --- the model -------------------------------------------------------------------

def compute_model(payload: dict, *, brand: str = "", generated: str | None = None,
                  concentration: dict | None = None, cvr_signals: dict | None = None,
                  machine: dict | None = None) -> dict:
    """CRO audit payload -> the model every renderer consumes. See module docstring.

    concentration / cvr_signals / machine — optional precomputed blocks (from
    concentration.py / cvr_signals.py / machine.py, derived from raw pull files
    or CSV exports, never from the payload); stored verbatim (None allowed).
    """
    payload = payload or {}
    meta_in = dict(payload.get("meta", {}) or {})
    analytics = payload.get("analytics", {}) or {}
    detail_in = payload.get("steps_detail", {}) or {}
    warnings: list[str] = []

    store_name = str(meta_in.get("store_name", "") or "")
    if brand:
        store_name = brand

    # --- health: Funnel Health 0-150 over the measured stages only ---------------
    funnel = analytics.get("funnel", {}) or {}
    unrounded, score, letter = funnel_health(funnel)
    health = {
        "score": score,  # INT (Excel ROUND(...,0) parity); None when nothing measured
        "score_unrounded": (round(unrounded, 4) if unrounded is not None else None),
        "grade": letter,
        "max": HEALTH_MAX,
    }

    # --- step statuses from meta.steps[] ------------------------------------------
    known_steps = {n for n, _t, _ti, _k in STEPS}
    steps_meta: dict[int, dict] = {}
    for s in meta_in.get("steps", []) or []:
        try:
            n = int(s.get("step", -1))
        except (TypeError, ValueError):
            warnings.append("meta.steps: non-numeric step %r ignored" % s.get("step"))
            continue
        if n not in known_steps:
            warnings.append("meta.steps: unknown step %r ignored" % n)
            continue
        steps_meta[n] = s

    # --- sections: the 11 steps in canonical order --------------------------------
    sections_out = []
    n_run = n_partial = n_not_run = 0
    for step_no, tab, title, detail_key in STEPS:
        s = steps_meta.get(step_no) or {}
        raw = str(s.get("status", "") or "").strip()
        status = STATUS_CANON.get(raw.lower())
        if status is None:
            if raw:
                warnings.append("step %d: unknown status %r -> not_run" % (step_no, raw))
            status = "not_run"
        reason = str(s.get("reason", "") or "")
        if status == "run":
            n_run += 1
        elif status == "partial":
            n_partial += 1
        else:
            n_not_run += 1

        if step_no == 1:
            evidence = _step1_evidence(analytics)
        elif detail_key is not None:
            block = detail_in.get(detail_key)
            evidence = _STEP_EVIDENCE[detail_key](block) if block else []
        else:
            evidence = []  # Step 11: the findings/roadmap panel is its content

        sections_out.append({
            "step": step_no,
            "tab": tab,
            "title": title,
            "status": status,
            "reason": reason,
            "evidence": evidence,
        })

    # --- findings: canon vocab + Impact/Ease defaults + priority + bucket ---------
    sev_count = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
    by_bucket = {label: 0 for _, label in PRIORITY_BUCKETS}
    findings_out = []
    for f in payload.get("findings", []) or []:
        fid = str(f.get("id", "?") or "?")
        sev_raw = str(f.get("severity", "") or "").strip()
        sev = SEV_CANON.get(sev_raw.lower())
        if sev is None:
            if sev_raw:
                warnings.append("finding %s: unknown severity %r" % (fid, sev_raw))
            sev = sev_raw
        if sev in sev_count:
            sev_count[sev] += 1
        ct_raw = str(f.get("change_type", "") or "").strip()
        change = CHANGE_CANON.get(ct_raw.lower())
        if change is None:
            if ct_raw:
                warnings.append("finding %s: change_type %r not Test/Ship" % (fid, ct_raw))
            change = ct_raw

        row = {k: f.get(k, "") for k in _FINDING_KEYS}
        row["severity"] = sev
        row["change_type"] = change
        row["step_sources"] = [str(x) for x in (f.get("step_sources") or [])]
        row["n_sources"] = len(row["step_sources"])  # triangulation count

        impact = _num_loose(f.get("impact"))
        if impact is None:
            impact = SEVERITY_IMPACT.get(sev, DEFAULT_EASE)
        ease = _num_loose(f.get("ease"))
        if ease is None:
            ease = DEFAULT_EASE
        pri = priority(impact, ease)
        bucket = bucket_for(pri)
        by_bucket[bucket] += 1
        row["impact"] = impact
        row["ease"] = ease
        row["priority"] = pri
        row["bucket"] = bucket
        findings_out.append(row)

    # Sort by priority desc; Python's sort is stable, so equal-priority findings
    # keep payload order (deterministic).
    findings_out.sort(key=lambda r: -r["priority"])

    # --- provenance / meta passthrough --------------------------------------------
    meta_out = {
        "store_name": store_name,  # the client label everywhere downstream
        "store_url": str(meta_in.get("store_url", "") or ""),
        "currency": meta_in.get("currency", ""),
        "date_range": meta_in.get("date_range", ""),
        "generated_for_date": meta_in.get("generated_for_date", ""),
        "auditor": meta_in.get("auditor", ""),
        # NO wall clock (determinism): fall back to generated_for_date, never now().
        "generated": generated or meta_in.get("generated_for_date", "") or "",
        "data_inventory": [dict(x) for x in meta_in.get("data_inventory", []) or []],
        "steps": [dict(x) for x in meta_in.get("steps", []) or []],
        "n_steps": len(STEPS),
        "n_steps_run": n_run,
        "n_steps_partial": n_partial,
        "n_steps_not_run": n_not_run,
        "n_findings": len(findings_out),
    }

    return {
        "meta": meta_out,
        "health": health,
        "sections": sections_out,
        "findings": findings_out,
        "kpis": [],  # CRO has no KPI strip; kept for renderer-shape compatibility
        "concentration": concentration,
        "cvr_signals": cvr_signals,
        "machine": machine,
        "summary": {
            "n_run": n_run, "n_partial": n_partial, "n_not_run": n_not_run,
            "crit": sev_count["Critical"], "high": sev_count["High"],
            "med": sev_count["Medium"], "low": sev_count["Low"],
            "score": score, "grade": letter, "findings_by_bucket": by_bucket,
        },
        "warnings": warnings,
    }
