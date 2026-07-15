#!/usr/bin/env python3
# Copyright (c) 2026 Clickt Digital Marketing Inc. All rights reserved.
"""Canonical audit model + scoring constants for meta-ads-audit.

Single source of truth for the Health Score / ICE math shared by THREE renderers:
the xlsx workbook (`build_audit_xlsx.py` imports these constants into its cell
formulas), the markdown record (`audit_md.py`), and the interactive HTML explorer
(`audit_html.py` mirrors the constants verbatim in its embedded JS kernel). Keeping
the numbers in one place — and asserting the mirror in `tests/test_audit.py` — is
what stops the three views from disagreeing.

Ported from google-ads-audit `scripts/audit_model.py`. Key deltas:

* The payload is the FLAT meta schema (see build_audit_xlsx.py docstring):
  `checks[]` carry a `category` string instead of living under nested sections;
  the check result field is named `flag`; check rows use `expected`
  (no `verify`, no `applies_to`); `sections{}` holds optional raw-evidence
  tables keyed by section_key.
* The Health Score is LEVER-WEIGHTED (Meta framework weights, pinned to the
  existing workbook's wscore_/wbase_ SUMPRODUCT semantics), not the flat
  earned/possible ratio google uses:
      health = Σ(score_s · w_s over included) / Σ(w_s over included)
  where score_s = section earned/possible × 100 kept UNROUNDED, a section is
  included iff its possible > 0, w_s comes from payload["category_weights"]
  (default SECTION_WEIGHTS; Competitive Landscape is weight 0), and the result
  is rounded ONCE at the very end.
* Findings get ICE defaults filled (impact ← SEVERITY_IMPACT[severity],
  confidence/ease ← DEFAULT_ICE) plus computed priority = I×C×E and a
  ROADMAP_BUCKETS bucket.
* `stem()` → "meta-audit_{slug}_{date}".

Stdlib only. Deterministic: a pure function of the payload — there is NO wall
clock in this module (`generated` / meta.generated_for_date are inputs).
"""
from __future__ import annotations

import math
import re


def round1(x: float) -> float:
    """Percent to 1dp, rounding half UP — the rule Excel and JS both use.

    Python's built-in round() is banker's: round(62.25, 1) == 62.2, while
    Excel's ROUND(62.25,1) == 62.3. Three runtimes, three rounding rules, and a
    score landing on a .x5 boundary printed 62.2 in the model and 62.3 in the
    workbook — the same class of divergence as an unrounded grade cell, one
    decimal over.

    The xlsx cannot simply be handed Python's number: its Health Score is a LIVE
    formula (edit a Flag in Excel and the score moves), which is the workbook's
    whole point. So the three share the RULE instead, and the kernel adopts
    Excel's. Scores are never negative, so half-up == half-away-from-zero.
    Ported verbatim from google-ads-audit's audit_model.round1.
    """
    return math.floor(x * 10 + 0.5) / 10

# --- Canonical scoring constants (mirrored verbatim by audit_html.py's JS kernel,
#     and imported by build_audit_xlsx.py; parity is asserted in tests) -----------
SEVERITY_WEIGHTS = {"Critical": 5.0, "High": 3.0, "Medium": 1.5, "Low": 0.5}
FLAG_SCORES = {"PASS": 1.0, "FLAG": 0.5, "FAIL": 0.0}  # N/A and blank are EXCLUDED
SEVERITY_IMPACT = {"Critical": 9, "High": 7, "Medium": 5, "Low": 3}
GRADE_CUTOFFS = [(90, "A"), (75, "B"), (60, "C"), (40, "D"), (0, "F")]
DEFAULT_ICE = 5  # neutral Confidence/Ease default for the live ICE re-rank
ROADMAP_BUCKETS = [(500, "30-day"), (250, "60-day"), (100, "90-day"), (0, "Parking lot")]

# Controlled vocabularies (byte-identical to build_audit_xlsx.py, which imports
# them from here). Drift silently distorts the Health Score, so normalize on
# build and warn (not error) on anything unmappable.
SEV_CANON = {"critical": "Critical", "high": "High", "medium": "Medium", "low": "Low"}
FLAG_CANON = {"pass": "PASS", "flag": "FLAG", "fail": "FAIL", "n/a": "N/A", "na": "N/A"}

# The seven Meta audit levers — (code, category_name, tab, section_key); order is
# canonical everywhere (model, workbook tabs, renderers). category_name strings
# byte-match build_audit_xlsx.py's ANALYSIS_TABS / COMPETITIVE_TAB — they are the
# product contract for payload["checks"][*]["category"].
SECTIONS = [
    ("DI", "Data Infrastructure & Signal", "02_Data_Infrastructure", "data_infrastructure"),
    ("AR", "Account Architecture", "03_Account_Architecture", "architecture"),
    ("BP", "Budget & Pacing", "04_Budget_Pacing", "budget"),
    ("AT", "Attribution", "05_Attribution", "attribution"),
    ("CR", "Creative Performance", "06_Creative_Performance", "creative"),
    ("CO", "Competitive Landscape", "07_Competitive", "competitive"),
    ("FP", "Future-Proofing", "08_Future_Proofing", "future_proofing"),
]

# Meta lever weights (John's pinned decision). CO is qualitative → weight 0: it
# contributes nothing to either sum even when it carries scorable checks.
SECTION_WEIGHTS = {"DI": 20.0, "AR": 20.0, "BP": 15.0, "AT": 10.0, "CR": 25.0,
                   "CO": 0.0, "FP": 10.0}

# Qualitative levers: no scored workbook tab, and weight PINNED to 0 in every
# renderer. THE single declaration — build_audit_xlsx derives ANALYSIS_TABS,
# COMPETITIVE_TAB, DEFAULT_CATEGORY_WEIGHTS and its exec-summary rows from this,
# and compute_model refuses to weight them. "CO is special" used to be spelled
# out in six places across two files; a seventh reader would have had to
# rediscover it, and any one of them drifting reintroduces a health score the
# workbook cannot reproduce (a payload weight for CO moved md/html while the
# xlsx, which builds no CO row, could not follow).
UNSCORED_SECTIONS = frozenset({"CO"})

_CHECK_KEYS = ("id", "name", "severity", "flag", "observed", "expected",
               "recommendation")
_FINDING_KEYS = ("id", "title", "category", "severity", "evidence",
                 "recommendation")


def slugify(s: str) -> str:
    """Lowercase, collapse non-alphanumerics to single hyphens, trim. Filename-safe."""
    out = re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")
    return out or "audit"


def grade(score: float) -> str:
    for cutoff, letter in GRADE_CUTOFFS:
        if score >= cutoff:
            return letter
    return "F"


def score_check(flag: str, severity: str):
    """(earned, possible) for one check; expects CANONICAL flag/severity strings.

    Returns (None, None) when the flag is N/A, blank, or unrecognized, so the
    check is excluded from BOTH sums (it is never scored as a zero). This
    exclusion is the single most common way to miscompute the score — keep it
    here, once.
    """
    if flag not in FLAG_SCORES:  # covers "N/A", "", None, and any stray value
        return (None, None)
    weight = SEVERITY_WEIGHTS.get(severity, 0.0)
    return (FLAG_SCORES[flag] * weight, weight)


def bucket_for(priority) -> str:
    """ROADMAP_BUCKETS lookup: first threshold ≤ priority wins."""
    for threshold, label in ROADMAP_BUCKETS:
        if priority >= threshold:
            return label
    return ROADMAP_BUCKETS[-1][1]


def stem(payload: dict, brand: str = "") -> str:
    """Tool-owned filename stem: meta-audit_{slug}_{date}.

    slug from meta.account_name | brand | meta.account_id; date from
    meta.generated_for_date (YYYY-MM-DD). Works on the payload OR the computed
    model — both carry a "meta" mapping with the same keys.
    """
    meta = (payload or {}).get("meta", {}) or {}
    slug = slugify(meta.get("account_name") or brand or meta.get("account_id")
                   or "audit")
    raw_date = str(meta.get("generated_for_date") or "")
    date = slugify(raw_date[:10]) if raw_date else "undated"
    return "meta-audit_%s_%s" % (slug, date)


def _ice_num(v):
    """Numeric ICE value or None (missing / blank / non-numeric). Integral floats
    collapse to int so embeds stay clean."""
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


def compute_model(payload: dict, *, brand: str = "", generated: str | None = None,
                  concentration: dict | None = None, prescore: dict | None = None,
                  creative_signals: dict | None = None) -> dict:
    """Meta audit payload -> the model every renderer consumes. See module docstring.

    concentration / prescore / creative_signals — optional precomputed blocks
    (from concentration.py / prescore.py / creative_signals.py, derived from raw
    pull files, never from the payload); stored verbatim (None allowed).
    """
    payload = payload or {}
    meta_in = dict(payload.get("meta", {}) or {})
    warnings: list[str] = []

    account_name = str(meta_in.get("account_name", "") or "")
    if brand:
        account_name = brand

    # --- section weights: payload override wins per category, default otherwise --
    overrides = payload.get("category_weights") or {}
    known_cats = {cat for _, cat, _, _ in SECTIONS}
    for key in sorted(overrides):
        if key not in known_cats:
            warnings.append("category_weights: unknown category %r ignored" % key)

    # --- pass 1: normalize every check once, count, bucket by canonical category --
    buckets = {cat: [] for _, cat, _, _ in SECTIONS}
    n_pass = n_flag = n_fail = n_na = 0
    n_checks = 0
    for c in payload.get("checks", []) or []:
        n_checks += 1
        cid = str(c.get("id", "?") or "?")
        sev_raw = str(c.get("severity", "") or "").strip()
        sev = SEV_CANON.get(sev_raw.lower())
        if sev is None:
            if sev_raw:
                warnings.append("check %s: unknown severity %r -> Sev.Wt 0 (not scored)"
                                % (cid, sev_raw))
            else:
                warnings.append("check %s: missing severity -> Sev.Wt 0 (not scored)"
                                % cid)
        flag_raw = str(c.get("flag", "") or "").strip()
        flag = FLAG_CANON.get(flag_raw.lower())
        if flag is None and flag_raw:
            warnings.append("check %s: unknown flag %r -> excluded from score"
                            % (cid, flag_raw))

        if flag == "PASS":
            n_pass += 1
        elif flag == "FLAG":
            n_flag += 1
        elif flag == "FAIL":
            n_fail += 1
        else:
            n_na += 1

        sev_display = sev if sev is not None else sev_raw
        flag_display = flag if flag is not None else flag_raw
        earned, possible = score_check(flag, sev_display)

        row = {k: c.get(k, "") for k in _CHECK_KEYS}
        row["severity"] = sev_display
        row["flag"] = flag_display
        row["result"] = flag_display  # alias: google-base renderers read "result"
        row["sev_w"] = SEVERITY_WEIGHTS.get(sev_display, 0.0)
        row["flag_score"] = FLAG_SCORES.get(flag)  # None for N/A/blank/unknown
        row["earned"] = earned
        row["possible"] = possible

        cat = str(c.get("category", "") or "")
        if cat in buckets:
            buckets[cat].append(row)
        else:
            warnings.append("check %s: unknown category %r -> excluded from scoring"
                            % (cid, cat))

    # --- pass 2: sections in canonical order; lever-weighted health --------------
    evidence_in = payload.get("sections", {}) or {}
    sections_out = []
    total_earned = 0.0
    total_possible = 0.0
    weighted_num = 0.0   # Σ(score_s · w_s) over included — score_s UNROUNDED
    weighted_den = 0.0   # Σ(w_s) over included
    for code, cat, tab, section_key in SECTIONS:
        checks_out = buckets[cat]
        sec_earned = sum(r["earned"] for r in checks_out if r["possible"] is not None)
        sec_possible = sum(r["possible"] for r in checks_out if r["possible"] is not None)
        total_earned += sec_earned
        total_possible += sec_possible

        weight_default = SECTION_WEIGHTS[code]
        # An unscored lever is structurally weight-0: the workbook builds no row
        # for it, so a nonzero weight is a value ONLY this function could honour
        # — health would move in md/html while the xlsx, unable to represent it,
        # disagreed. Pinned here from UNSCORED_SECTIONS rather than trusted to
        # callers or to SECTION_WEIGHTS staying 0.
        if code in UNSCORED_SECTIONS:
            if cat in overrides:
                warnings.append(
                    "category_weights[%r]: %s is qualitative and always weight 0 "
                    "(the workbook builds no scored tab for it) -> %r ignored"
                    % (cat, cat, overrides[cat]))
            weight = 0.0
        else:
            weight_raw = overrides.get(cat, weight_default)
            try:
                weight = float(weight_raw)
            except (TypeError, ValueError):
                warnings.append("category_weights[%r]: non-numeric %r -> default %.1f"
                                % (cat, weight_raw, weight_default))
                weight = weight_default

        score_s = (sec_earned / sec_possible * 100.0) if sec_possible > 0 else None
        included = sec_possible > 0
        if included:
            weighted_num += score_s * weight
            weighted_den += weight

        sections_out.append({
            "code": code,
            "tab": tab,
            "title": cat,
            "category": cat,
            "weight": weight,
            "included": included,
            "checks": checks_out,
            "earned": round(sec_earned, 4),
            "possible": round(sec_possible, 4),
            # round1, not round(): the HTML and md display this verbatim, and
            # the workbook's D cell shows the same lever score rounded for
            # display by Excel's half-away rule ("0.0" number_format, set in
            # build_exec_summary — the value itself stays unrounded because the
            # health SUMPRODUCT reads it). round() is half-even, so an exact .x5
            # lever score (2.25/20 = 11.25) printed 11.2 here and 11.3 there.
            "score_pct": (round1(score_s) if score_s is not None else None),
            "evidence": evidence_in.get(section_key) or None,
        })

    # Round ONCE, at the end, from unrounded section scores (Excel wscore_/wbase_
    # parity). Denominator 0 (nothing included, or only weight-0 levers) → 0.0.
    # round1 shares Excel's rule — the workbook computes this same quotient in a
    # LIVE formula and rounds it with ROUND(), so the kernel must round the same
    # way or a .x5 boundary ships two different numbers (and, at a cutoff, two
    # different grades).
    score = round1(weighted_num / weighted_den) if weighted_den > 0 else 0.0
    letter = grade(score)

    # --- findings: ICE defaults + priority + roadmap bucket ----------------------
    sev_count = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
    by_bucket = {label: 0 for _, label in ROADMAP_BUCKETS}
    findings_out = []
    for f in payload.get("findings", []) or []:
        sev_raw = str(f.get("severity", "") or "").strip()
        sev = SEV_CANON.get(sev_raw.lower()) or sev_raw
        if sev in sev_count:
            sev_count[sev] += 1
        row = {k: f.get(k, "") for k in _FINDING_KEYS}
        row["severity"] = sev
        impact = _ice_num(f.get("impact"))
        if impact is None:
            impact = SEVERITY_IMPACT.get(sev, DEFAULT_ICE)
        confidence = _ice_num(f.get("confidence"))
        if confidence is None:
            confidence = DEFAULT_ICE
        ease = _ice_num(f.get("ease"))
        if ease is None:
            ease = DEFAULT_ICE
        priority = impact * confidence * ease
        if isinstance(priority, float) and priority.is_integer():
            priority = int(priority)
        bucket = bucket_for(priority)
        by_bucket[bucket] += 1
        row["impact"] = impact
        row["confidence"] = confidence
        row["ease"] = ease
        row["priority"] = priority
        row["bucket"] = bucket
        findings_out.append(row)

    # --- provenance / meta passthrough -------------------------------------------
    windows_in = dict(meta_in.get("windows", {}) or {})
    windows = {"structure": windows_in.get("structure", ""),
               "creative": windows_in.get("creative", ""),
               "trend": windows_in.get("trend", "")}
    for k in sorted(windows_in):
        if k not in windows:
            windows[k] = windows_in[k]

    meta_out = {
        "account_name": account_name,  # the client label everywhere downstream
        "account_id": str(meta_in.get("account_id", "") or ""),
        "business_model": meta_in.get("business_model", ""),
        "currency": meta_in.get("currency", ""),
        "windows": windows,
        "generated_for_date": meta_in.get("generated_for_date", ""),
        "auditor": meta_in.get("auditor", ""),
        "out_of_scope": list(meta_in.get("out_of_scope", []) or []),
        # NO wall clock (determinism): fall back to generated_for_date, never now().
        "generated": generated or meta_in.get("generated_for_date", "") or "",
        "n_checks": n_checks,
        "n_findings": len(findings_out),
    }

    return {
        "meta": meta_out,
        "sections": sections_out,
        "kpis": [dict(k) for k in payload.get("kpis", []) or []],
        "findings": findings_out,
        "concentration": concentration,
        "prescore": prescore,
        "creative_signals": creative_signals,
        "health": {
            "score": score,
            "grade": letter,
            "earned": round(total_earned, 4),
            "possible": round(total_possible, 4),
            "weighted": True,
        },
        "summary": {
            "n_pass": n_pass, "n_flag": n_flag, "n_fail": n_fail, "n_na": n_na,
            "crit": sev_count["Critical"], "high": sev_count["High"],
            "med": sev_count["Medium"], "low": sev_count["Low"],
            "score": score, "grade": letter, "findings_by_bucket": by_bucket,
        },
        "warnings": warnings,
    }
