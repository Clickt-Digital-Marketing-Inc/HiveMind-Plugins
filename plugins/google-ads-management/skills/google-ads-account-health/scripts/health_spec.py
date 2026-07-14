#!/usr/bin/env python3
"""Render spec for the account-health checks — adapts health_core's model to
the shared render toolkit (_shared/render). Stdlib only.

Reduced bundle (sanctioned by HM-545): md + xlsx only. Five heterogeneous
checks across different entity grains read poorly as one wide interactive
HTML explorer, so no `html_embed` / `js_kernel` / `html_controls` are
declared here — the md report + the tunable xlsx are the floor.
"""
from __future__ import annotations

import health_core as core
from render import model as M  # noqa: E402  (source_label — HM-572 canonical "Data source" line)


def _fmt_val(check: str, field: str, v):
    if v is None:
        return "—"
    if field == "ad_group_ctr":
        return f"{v * 100:.2f}%"
    if field in ("keyword_count", "negative_count", "conversions_30d"):
        return f"{v:,.2f}" if float(v) % 1 else f"{int(v):,}"
    if field == "name_pattern_ok":
        return "yes" if v else "no"
    if field in ("pmax_present", "brand_present"):
        return "yes" if v else "no"
    if field == "has_brand_exclusion":
        return "yes" if v else ("no" if v is False else "unconfirmed")
    return str(v)


# --------------------------------------------------------------------------
# Markdown adapters
# --------------------------------------------------------------------------
def md_params(model):
    p = model["params"]
    return [
        ("Data source", M.source_label(model["provenance"].get("source"))),
        ("Ad-group sprawl", f"≥ {p['sprawl_min_keywords']} keywords AND CTR < {p['sprawl_max_ctr'] * 100:.1f}%"),
        ("No campaign negatives", f"≤ {p['negatives_max_count']} campaign-level negatives (Search)"),
        ("Automation without data", f"automated bidding AND conversions(30d) < {p['automation_min_conversions']}"),
        ("Naming convention", "unconfirmed default — see below"),
        ("PMax brand cannibalization", "PMax campaign present AND an enabled brand Search campaign exists "
                                       "(brand-exclusion confirmation is manual — see below)"),
    ]


def md_kpis(model):
    s = model["summary"]
    by_check = s["by_check"]
    labels = model["check_labels"]
    out = [("Total flagged", f"{s['total_flagged']} / {s['universe']} checked rows"),
           ("By severity", f"Critical {s['by_severity']['Critical']} · High {s['by_severity']['High']} · "
                            f"Medium {s['by_severity']['Medium']}")]
    for c in model["checks"]:
        v = by_check[c]
        out.append((labels[c], f"{v['flagged']} / {v['universe']} flagged"))
    return out


def md_narrative(model):
    # Regex is shown as an inline-code narrative line, NOT a table cell — a
    # table cell's markdown-escaping doubles the regex's backslashes
    # (`\d` -> `\\d`), which is confusing for something meant to be copied
    # back into params.naming_regex verbatim.
    lines = [f"**Naming convention** (unconfirmed default — confirm with the user): "
            f"`{model['params']['naming_regex']}`", ""]
    if model["summary"]["total_flagged"] == 0:
        lines += [
            "> **0 flags across all five checks is a clean result, not an error.** Every ad group, "
            "campaign, and PMax pairing in scope was evaluated against the thresholds above and none "
            "tripped. Structural health does not guarantee performance health — pair this with "
            "`google-ads-performance-reporting` and `google-ads-quality-score`.",
        ]
    return lines


def _check_section(model, check):
    labels = model["check_labels"]
    rows = [r for r in model["rows"] if r["check"] == check]
    flagged = [r for r in rows if r["is_flagged"]]
    flagged.sort(key=lambda r: (-r["pre_score"], r["entity_name"]))
    if check == "sprawl":
        headers = ["Ad group", "Campaign", "Keywords", "CTR (30d)", "Pre-score"]
        aligns = ["l", "l", "r", "r", "r"]
        body = [[r["entity_name"], r["campaign_name"], _fmt_val(check, "keyword_count", r["keyword_count"]),
                  _fmt_val(check, "ad_group_ctr", r["ad_group_ctr"]), f"{r['pre_score']:.1f}"] for r in flagged]
    elif check == "no_negatives":
        headers = ["Campaign", "Negatives (campaign-level)", "Pre-score"]
        aligns = ["l", "r", "r"]
        body = [[r["campaign_name"], _fmt_val(check, "negative_count", r["negative_count"]),
                  f"{r['pre_score']:.1f}"] for r in flagged]
    elif check == "automation_no_data":
        headers = ["Campaign", "Bidding strategy", "Conversions (30d)", "Pre-score"]
        aligns = ["l", "l", "r", "r"]
        body = [[r["campaign_name"], r["bidding_strategy_type"] or "—",
                  _fmt_val(check, "conversions_30d", r["conversions_30d"]), f"{r['pre_score']:.1f}"]
                 for r in flagged]
    elif check == "naming":
        headers = ["Campaign", "Matches convention?", "Pre-score"]
        aligns = ["l", "l", "r"]
        body = [[r["campaign_name"], _fmt_val(check, "name_pattern_ok", r["name_pattern_ok"]),
                  f"{r['pre_score']:.1f}"] for r in flagged]
    else:  # pmax_cannibalization
        headers = ["PMax campaign", "Brand Search campaign exists?", "Brand exclusion confirmed?", "Pre-score"]
        aligns = ["l", "l", "l", "r"]
        body = [[r["campaign_name"], _fmt_val(check, "brand_present", r["brand_present"]),
                  _fmt_val(check, "has_brand_exclusion", r["has_brand_exclusion"]), f"{r['pre_score']:.1f}"]
                 for r in flagged]
    if check == "pmax_cannibalization" and not rows:
        empty = "_No Performance Max campaigns found in this account — check not applicable._"
    elif not flagged:
        empty = "_Clean — no entity met every condition for this check._"
    else:
        empty = "_None._"
    return {"title": f"{labels[check]} ({len(flagged)} flagged / {len(rows)} checked)",
            "note": None, "headers": headers, "aligns": aligns, "rows": body, "empty": empty}


def md_sections(model):
    secs = [_check_section(model, c) for c in model["checks"]]

    tf = model["top_fixes"]
    secs.append({
        "title": "Top structural fixes (ranked by pre-score across checks)",
        "note": "Every entity that tripped its check's full rule set, ranked by severity weight. "
                "Work Critical, then High, then Medium.",
        "headers": ["Severity", "Check", "Entity", "Campaign", "Pre-score", "Status"],
        "aligns": ["l", "l", "l", "l", "r", "l"],
        "rows": [[r["severity"], r["check_label"], r["entity_name"], r["campaign_name"],
                  f"{r['pre_score']:.1f}", r["status"]] for r in tf],
        "empty": "_No structural red flags — account passes all five checks._",
    })
    return secs


def md_rows(model):
    """Every (check, entity) row with its status — the no-row-loss layer."""
    headers = ["Check", "Entity type", "Entity", "Campaign", "Keywords", "Ad-group CTR",
               "Negatives", "Bidding strategy", "Conv (30d)", "Name OK?", "PMax?", "Brand present?",
               "Brand excl. confirmed?", "Flagged?", "Pre-score", "Status"]
    out = []
    for r in model["rows"]:
        out.append([
            r["check_label"], r["entity_type"], r["entity_name"], r["campaign_name"],
            _fmt_val(r["check"], "keyword_count", r["keyword_count"]),
            _fmt_val(r["check"], "ad_group_ctr", r["ad_group_ctr"]),
            _fmt_val(r["check"], "negative_count", r["negative_count"]),
            r["bidding_strategy_type"] or "—",
            _fmt_val(r["check"], "conversions_30d", r["conversions_30d"]),
            _fmt_val(r["check"], "name_pattern_ok", r["name_pattern_ok"]),
            _fmt_val(r["check"], "pmax_present", r["pmax_present"]),
            _fmt_val(r["check"], "brand_present", r["brand_present"]),
            _fmt_val(r["check"], "has_brand_exclusion", r["has_brand_exclusion"]),
            "yes" if r["is_flagged"] else "no",
            f"{r['pre_score']:.1f}", r["status"],
        ])
    return {
        "title": "Every checked entity (no row loss)",
        "note": "Every ad group / campaign evaluated by any of the five checks, one row per "
                "(check, entity) pair, with its status (`scored` / `config` / `manual`) and "
                "whether it was flagged. `—` marks a column that does not apply to that check.",
        "headers": headers, "aligns": ["l"] * 4 + ["r", "r", "r", "l", "r"] + ["l"] * 5 + ["r", "l"],
        "rows": out,
        "empty": "_No ad groups or campaigns in scope._",
    }


CHARTS = [
    {
        "id": "flags_by_check",
        "title": "Flags by check",
        "mark": {"type": "bar"},
        "transform": [
            {"filter": "datum.is_flagged"},
            {"aggregate": [{"op": "count", "as": "flagged"}], "groupby": ["check_label"]},
        ],
        "encoding": {
            "y": {"field": "check_label", "type": "nominal", "title": None,
                  "sort": "-x"},
            "x": {"field": "flagged", "type": "quantitative", "title": "Flagged entities"},
            "color": {"value": "#0369a1"},
            "tooltip": [{"field": "check_label", "title": "Check"},
                        {"field": "flagged", "title": "Flagged"}],
        },
        "height": 160,
        "md": True, "widget": False,
    },
]


# --------------------------------------------------------------------------
# The spec object the toolkit consumes. No html_embed/js_kernel/xlsx here —
# xlsx is attached by build_health_report.py (keeps this module import-light);
# xlsx is the ONLY interactive surface for this reduced bundle.
# --------------------------------------------------------------------------
SPEC = {
    "slug_prefix": "account-health",
    "row_noun": "checked entities",
    "title": "Account Health & Structure",
    "about": {
        "summary": "Five structural red-flag checks across different entity grains: ad-group "
                   "keyword sprawl, missing campaign negatives, naming-convention drift, "
                   "automated bidding running without enough conversion data, and Performance "
                   "Max campaigns coexisting with an unconfirmed brand-exclusion list. Each row "
                   "is one (check, entity) evaluation with a status honestly labelling how "
                   "confident that row is: `scored` (fully queryable), `config` (deterministic "
                   "but runs against an unconfirmed default), or `manual` (the read-only API "
                   "cannot supply the fact — needs a human to confirm in the UI).",
        "legend": [
            {"label": "Critical", "desc": "Automated bidding running on too little conversion data — active risk."},
            {"label": "High", "desc": "Ad-group sprawl, missing negatives, or PMax/brand coexistence."},
            {"label": "Medium", "desc": "Naming-convention drift — hygiene, not budget risk."},
        ],
    },
    "methodology_ref": "references/account-health-filter.md",
    "md_params": md_params,
    "md_kpis": md_kpis,
    "md_narrative": md_narrative,
    "md_sections": md_sections,
    "md_rows": md_rows,
    "charts": CHARTS,
    # xlsx layout is attached in health_xlsx_spec, wired in by build_health_report.py.
}
