#!/usr/bin/env python3
# Copyright (c) 2026 Clickt Digital Marketing Inc. All rights reserved.
"""Canonical audit model + scoring constants for google-ads-audit.

Single source of truth for the Health Score / ICE math shared by THREE renderers:
the xlsx workbook (`generate_workbook.py` imports these constants into its cell
formulas), the markdown record (`audit_md.py`), and the interactive HTML explorer
(`audit_html.py` mirrors the constants verbatim in its embedded JS kernel). Keeping
the numbers in one place — and asserting the mirror in `tests/test_audit.py` — is
what stops the three views from disagreeing.

`compute_model(findings)` turns the findings JSON (schema in SKILL.md) into a
JSON-serializable model: per-check earned/possible, per-section rollups, the
weighted Health Score + grade, ICE impact seeds, and summary counts.

Stdlib only. Deterministic: a pure function of the findings, except
`provenance.generated` (pass `generated=` to pin it in tests).
"""
from __future__ import annotations

import datetime as _dt
import re

# --- Canonical scoring constants (mirrored verbatim by audit_html.py's JS kernel,
#     and imported by generate_workbook.py; parity is asserted in tests) ----------
SEVERITY_WEIGHTS = {"Critical": 5.0, "High": 3.0, "Medium": 1.5, "Low": 0.5}
FLAG_SCORES = {"PASS": 1.0, "FLAG": 0.5, "FAIL": 0.0}  # N/A and blank are EXCLUDED
SEVERITY_IMPACT = {"Critical": 9, "High": 7, "Medium": 5, "Low": 3}
GRADE_CUTOFFS = [(90, "A"), (75, "B"), (60, "C"), (40, "D"), (0, "F")]
DEFAULT_ICE = 5  # neutral Confidence/Ease default for the live ICE re-rank

# The nine analysis tabs that feed the Health Score (order = layout order).
ANALYSIS_TABS = [
    ("03_Account_Structure", "1. Account Structure"),
    ("04_Performance_Review", "2. Performance Review"),
    ("05_Keyword_Strategy", "3. Keyword Strategy"),
    ("06_Ad_Creatives_Assets", "4. Ad Creatives & Assets"),
    ("07_Landing_Pages", "5. Landing Pages"),
    ("08_Budget_Bidding", "6. Budget & Bidding"),
    ("09_Tracking_Measurement", "7. Tracking & Measurement"),
    ("10_Audiences", "8. Audiences"),
    ("11_Automation_Recommendations", "9. Scripts, Recommendations & Automation"),
]

_CHECK_KEYS = ("id", "name", "verify", "applies_to", "severity", "result",
               "observed", "recommendation")
_FINDING_KEYS = ("id", "section", "title", "severity", "recommendation",
                 "effort", "horizon", "owner")


def slugify(s: str) -> str:
    """Lowercase, collapse non-alphanumerics to single hyphens, trim. Filename-safe."""
    out = re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")
    return out or "audit"


def grade(score: float) -> str:
    for cutoff, letter in GRADE_CUTOFFS:
        if score >= cutoff:
            return letter
    return "F"


def score_check(result: str, severity: str):
    """(earned, possible) for one check.

    Returns (None, None) when the result is N/A, blank, or unrecognized, so the
    check is excluded from BOTH sums (it is never scored as a zero). This exclusion
    is the single most common way to miscompute the score — keep it here, once.
    """
    if result not in FLAG_SCORES:  # covers "N/A", "", and any stray value
        return (None, None)
    weight = SEVERITY_WEIGHTS.get(severity, 0.0)
    return (FLAG_SCORES[result] * weight, weight)


def stem(model: dict, brand: str = "") -> str:
    """Tool-owned filename stem: ads-audit_{slug}_{date}.

    slug from account_id|client_name|brand; date from audit_date|generated (YYYY-MM-DD).
    """
    prov = model.get("provenance", {})
    slug = slugify(prov.get("account_id") or prov.get("client_name") or brand or "audit")
    raw_date = str(prov.get("audit_date") or prov.get("generated") or "")
    date = slugify(raw_date[:10]) if raw_date else "undated"
    return f"ads-audit_{slug}_{date}"


def _now_iso() -> str:
    return _dt.datetime.now().replace(microsecond=0).isoformat()


def compute_model(findings: dict, *, brand: str = "", generated: str | None = None,
                  concentration: dict | None = None, prescore: dict | None = None) -> dict:
    """Findings JSON -> the model every renderer consumes. See module docstring.

    concentration — optional precomputed block from concentration.py (derived
    from raw GAQL pull files, never from findings.json); stored verbatim.
    prescore — optional merge summary from prescore.merge_into_findings
    (which checks were machine-scored/corrected); stored verbatim."""
    meta = dict(findings.get("meta", {}))
    if brand:
        meta["client_name"] = brand

    n_pass = n_flag = n_fail = n_na = 0
    n_checks = 0
    total_earned = 0.0
    total_possible = 0.0
    sections_out = []

    for sec in findings.get("sections", []):
        checks_out = []
        sec_earned = 0.0
        sec_possible = 0.0
        for c in sec.get("checks", []):
            n_checks += 1
            result = c.get("result", "")
            severity = c.get("severity", "Medium")
            earned, possible = score_check(result, severity)
            if result == "PASS":
                n_pass += 1
            elif result == "FLAG":
                n_flag += 1
            elif result == "FAIL":
                n_fail += 1
            else:
                n_na += 1
            if possible is not None:
                sec_earned += earned
                sec_possible += possible
            row = {k: c.get(k, "") for k in _CHECK_KEYS}
            row["sev_w"] = SEVERITY_WEIGHTS.get(severity, 0.0)
            row["flag_score"] = FLAG_SCORES.get(result)  # None for N/A/blank
            row["earned"] = earned
            row["possible"] = possible
            checks_out.append(row)
        total_earned += sec_earned
        total_possible += sec_possible
        sections_out.append({
            "tab": sec.get("tab", ""),
            "title": sec.get("title", ""),
            "checks": checks_out,
            "earned": round(sec_earned, 4),
            "possible": round(sec_possible, 4),
            "score_pct": (round(sec_earned / sec_possible * 100, 1) if sec_possible else None),
        })

    score = round(total_earned / total_possible * 100, 1) if total_possible else 0.0
    letter = grade(score)

    sev_count = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
    by_horizon = {"30": 0, "60": 0, "90": 0}
    findings_out = []
    for f in findings.get("findings", []):
        severity = f.get("severity", "Medium")
        sev_count[severity] = sev_count.get(severity, 0) + 1
        horizon = str(f.get("horizon", ""))
        if horizon in by_horizon:
            by_horizon[horizon] += 1
        row = {k: f.get(k, "") for k in _FINDING_KEYS}
        row["impact"] = SEVERITY_IMPACT.get(severity, 0)
        findings_out.append(row)

    provenance = {
        "client_name": meta.get("client_name", ""),
        "account_id": meta.get("account_id", ""),
        "currency": meta.get("currency", ""),
        "timezone": meta.get("timezone", ""),
        "business_model": meta.get("business_model", ""),
        "date_range": meta.get("date_range", ""),
        "search_terms_range": meta.get("search_terms_range", ""),
        "auditor": meta.get("auditor", ""),
        "audit_date": meta.get("audit_date", ""),
        "generated": generated or _now_iso(),
        "n_checks": n_checks,
        "n_findings": len(findings_out),
    }

    return {
        "provenance": provenance,
        "sections": sections_out,
        "kpis": [dict(k) for k in findings.get("kpis", [])],
        "data_inventory": [dict(d) for d in findings.get("data_inventory", [])],
        "findings": findings_out,
        "concentration": concentration,
        "prescore": prescore,
        "health": {
            "earned": round(total_earned, 4),
            "possible": round(total_possible, 4),
            "score": score,
            "grade": letter,
        },
        "summary": {
            "n_pass": n_pass, "n_flag": n_flag, "n_fail": n_fail, "n_na": n_na,
            "crit": sev_count["Critical"], "high": sev_count["High"],
            "med": sev_count["Medium"], "low": sev_count["Low"],
            "score": score, "grade": letter, "findings_by_horizon": by_horizon,
        },
    }
