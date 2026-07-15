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

`health.score`/`health.grade` are **None** when no check was scoreable — an audit
that gathered no evidence is *not scored*, not a zero. Renderers must show that as
"not scored"; the same applies to a section's `score_pct`.

Stdlib only. Deterministic: a pure function of the findings, except
`provenance.generated` (pass `generated=` to pin it in tests).
"""
from __future__ import annotations

import copy
import datetime as _dt
import math
import re

# --- Canonical scoring constants (mirrored verbatim by audit_html.py's JS kernel,
#     and imported by generate_workbook.py; parity is asserted in tests) ----------
SEVERITY_WEIGHTS = {"Critical": 5.0, "High": 3.0, "Medium": 1.5, "Low": 0.5}
FLAG_SCORES = {"PASS": 1.0, "FLAG": 0.5, "FAIL": 0.0}  # N/A and blank are EXCLUDED
SEVERITY_IMPACT = {"Critical": 9, "High": 7, "Medium": 5, "Low": 3}
GRADE_CUTOFFS = [(90, "A"), (75, "B"), (60, "C"), (40, "D"), (0, "F")]
DEFAULT_ICE = 5  # neutral Confidence/Ease default for the live ICE re-rank
# Substituted whenever severity is absent or unrecognized, so no consumer ever
# reaches its own fallback — those fallbacks disagreed (see normalize_severity).
DEFAULT_SEVERITY = "Medium"
DEFAULT_IMPACT = SEVERITY_IMPACT[DEFAULT_SEVERITY]

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


def round1(x: float) -> float:
    """Percent to 1dp, rounding half UP — the rule Excel and JS both use.

    Python's built-in round() is banker's: round(6.25, 1) == 6.2, while Excel's
    ROUND(6.25,1) == 6.3 and JS Math.round(62.5)/10 == 6.3. Three runtimes, three
    rounding rules, and a score landing on a .x5 boundary printed 6.2 in the model
    and 6.3 in the workbook.

    The xlsx cannot simply be handed Python's number — its Health Score is a LIVE
    formula (edit a Result in Excel and the score moves), which is the workbook's
    whole point. So the three must share the rounding RULE instead, and the kernel
    adopts Excel's. Scores are never negative, so half-up == half-away-from-zero
    (do not reuse this for a signed metric without revisiting that).

    Same rule as the JS `Math.round(e/p*1000)/10`, though the JS reaches it by a
    different float path (`e/p*1000` vs `x*10` here), so the two are rule-equivalent
    rather than provably bit-identical. Nothing compares them directly: sectionPct
    reads Python's `score_pct`, and the JS what-if has no Python counterpart.
    """
    return math.floor(x * 10 + 0.5) / 10


def grade(score: float) -> str:
    for cutoff, letter in GRADE_CUTOFFS:
        if score >= cutoff:
            return letter
    return "F"


def normalize_result(raw) -> tuple[str, str | None]:
    """One check `result` -> (canonical, warning). Canonical is PASS/FLAG/FAIL/N/A/"".

    The findings JSON is model-authored, so a stray casing ("Fail") or an invisible
    trailing space ("N/A ") is plausible. Python tests membership exactly while an
    Excel `=` comparison is case-INSENSITIVE, so an un-canonicalized value scores
    differently in the workbook than in the model — and a value matching neither
    arm leaves the xlsx helper cells empty, cascading `#VALUE!` all the way into
    the client report. Canonicalize once, before any renderer sees the value.

    Blank stays blank: "" already means the same thing to both runtimes (excluded).
    An unrecognized value degrades to N/A — the safe direction, matching what
    `score_check` already did — but returns a warning so it is not silent.
    """
    s = str(raw if raw is not None else "").strip().upper()
    if s in FLAG_SCORES or s in ("N/A", ""):
        return s, None
    return "N/A", f"unrecognized result {raw!r} — scored N/A"


# Canonicalizing against SEVERITY_WEIGHTS is only correct while SEVERITY_IMPACT
# shares its vocabulary — findings[] severity is canonicalized here but consumed
# via SEVERITY_IMPACT. Pin the assumption rather than leave it implicit.
assert set(SEVERITY_WEIGHTS) == set(SEVERITY_IMPACT), (
    "SEVERITY_WEIGHTS and SEVERITY_IMPACT must share their severity vocabulary")
_SEVERITY_CANON = {s.upper(): s for s in SEVERITY_WEIGHTS}


def normalize_severity(raw) -> tuple[str, str | None]:
    """One `severity` -> (canonical, warning). Same divergence as normalize_result.

    Python looks SEVERITY_WEIGHTS up exactly, so "high" misses and weighs 0.0 and
    the check leaves the score entirely. Excel's `=` is case-insensitive, so
    D="high" matches IF(D="High",3,…) and the workbook happily scores it. Net
    effect measured: the model reports the audit "not scored" while the client's
    workbook prints 100 / A.

    An unrecognized value becomes DEFAULT_SEVERITY — the same substitution
    compute_model already makes when severity is absent — rather than being left
    for each consumer's own fallback to handle. Those fallbacks do NOT agree: the
    model seeds ICE impact 0 while the xlsx ICE tab seeds 5, so one bad string put
    the same finding at the bottom of the HTML's priority list and mid-table in the
    workbook's. An unknown key also slips past summary's fixed crit/high/med/low
    reads, so the finding vanished from the counts entirely. Canonicalizing to a
    known key here makes every one of those fallbacks unreachable.
    """
    s = str(raw if raw is not None else "").strip()
    canon = _SEVERITY_CANON.get(s.upper())
    if canon:
        return canon, None
    return DEFAULT_SEVERITY, f"unrecognized severity {raw!r} — treated as {DEFAULT_SEVERITY}"


def normalize_findings(findings: dict) -> tuple[dict, list[str]]:
    """Deep-copied `findings` with `result` and `severity` canonicalized, + warnings.

    Pure and idempotent, so every entry point can call it defensively without the
    orchestrator having to guarantee it ran first.
    """
    out = copy.deepcopy(findings)
    warnings: list[str] = []

    def _sev(obj, label):
        # Absent -> the documented default, written INTO the row. compute_model
        # already substituted it, but only for scoring: the row still carried "",
        # so the HTML showed a blank severity, the findings log wrote a blank cell,
        # and 15_Client_Report's COUNTIF/COUNTA then dropped the finding entirely.
        # Substituting here is what makes every renderer agree. Silent, because an
        # absent severity has always meant the default; a present-but-wrong one warns.
        if "severity" not in obj:
            obj["severity"] = DEFAULT_SEVERITY
            return
        canon, warn = normalize_severity(obj["severity"])
        if warn:
            warnings.append(f"{label}: {warn}")
        obj["severity"] = canon

    for sec in out.get("sections", []):
        for c in sec.get("checks", []):
            label = f"{sec.get('tab', '?')} {c.get('id', '?')}"
            canon, warn = normalize_result(c.get("result", ""))
            if warn:
                warnings.append(f"{label}: {warn}")
            c["result"] = canon
            _sev(c, label)
    # findings[] severity feeds sev_count and the ICE impact seed, and the xlsx ICE
    # tab looks SEVERITY_IMPACT up the same way — canonicalize it on this side too.
    for f in out.get("findings", []):
        _sev(f, f"finding {f.get('id', '?')}")
    return out, warnings


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
    findings, _ = normalize_findings(findings)  # idempotent; direct callers get it too
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
            severity = c.get("severity", DEFAULT_SEVERITY)
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
            "score_pct": (round1(sec_earned / sec_possible * 100) if sec_possible else None),
        })

    # Nothing scoreable (every result N/A or blank) -> not scored, NOT zero. This
    # function takes care never to score an individual N/A check as a zero; scoring
    # an all-N/A audit 0.0/F would undo that at the top line and brand an account
    # with an F on evidence nobody gathered.
    score = round1(total_earned / total_possible * 100) if total_possible else None
    letter = grade(score) if score is not None else None

    sev_count = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
    by_horizon = {"30": 0, "60": 0, "90": 0}
    findings_out = []
    for f in findings.get("findings", []):
        severity = f.get("severity", DEFAULT_SEVERITY)
        sev_count[severity] = sev_count.get(severity, 0) + 1
        horizon = str(f.get("horizon", ""))
        if horizon in by_horizon:
            by_horizon[horizon] += 1
        row = {k: f.get(k, "") for k in _FINDING_KEYS}
        # Unreachable fallback after normalize_severity, but it must MATCH the xlsx
        # ICE tab's (generate_workbook build_ice) — they used to be 0 here and 5 there.
        row["impact"] = SEVERITY_IMPACT.get(severity, DEFAULT_IMPACT)
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
