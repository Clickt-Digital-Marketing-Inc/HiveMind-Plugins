#!/usr/bin/env python3
"""Render spec for the audience-targeting advisor — adapts audience_core's
model to the shared render toolkit (_shared/render). Stdlib only.

Reduced bundle (md + tunable xlsx — no HTML explorer; see
references/audience-targeting-filter.md for why). The scoring math lives once
in audience_core (Python) and is mirrored in the xlsx formulas
(audience_xlsx_spec); there is no js_kernel/html_* adapter because this
skill emits no HTML explorer.
"""
from __future__ import annotations

from render import model as M  # noqa: E402  (source_label — HM-572 canonical "Data source" line)


def _money(v, cur):
    if v is None:
        return "—"
    return f"{float(v):,.2f}" + (f" {cur}" if cur else "")


def _pct(v):
    if v is None:
        return "—"
    return f"{float(v) * 100:.1f}%"


def _n(v):
    f = float(v or 0)
    return int(f) if f.is_integer() else round(f, 2)


# --------------------------------------------------------------------------
# Markdown adapters
# --------------------------------------------------------------------------
def _granularity_label(pr):
    return ("ad-group level" if pr.get("metrics_granularity") == "ad_group_level"
            else "list level")


def md_params(model):
    p = model["params"]
    pr = model["provenance"]
    return [
        ("Priority scoring", f"weights: no-bid-adj {p['w_no_bid_adjustment']:g} · "
                             f"paused {p['w_paused_criterion']:g} · zero-conv {p['w_zero_conversions']:g} · "
                             f"wasted-spend {p['w_wasted_spend']:g} · high-CPA {p['w_high_cpa']:g} · "
                             f"low-CTR {p['w_low_ctr']:g}  "
                             f"(Critical ≥ {p['critical_threshold']:g}, High ≥ {p['high_threshold']:g})"),
        ("Cost / CTR bars", f"wasted-spend: 0-conversion cost > {p['cost_multiple']:.2f}× campaign avg cost · "
                            f"high-CPA: converting CPA > {p['cost_multiple']:.2f}× campaign avg CPA · "
                            f"low-CTR: CTR < {p['ctr_factor']:.2f}× campaign avg CTR (this pull's own "
                            "scored audiences — no separate benchmark query)"),
        ("Data source", f"Applied audiences: {M.source_label(pr.get('source'))}  ·  "
                        f"First-party readiness: {pr.get('first_party_source', 'not_supplied')}"),
        ("Metrics granularity", f"{_granularity_label(pr)}" +
                                (" — the Google Ads API exposes zero metrics.* fields on the applied-"
                                 "audience criterion itself; cost/clicks/impressions/conversions are "
                                 "pulled from ad_group_audience_view and shared across every USER_LIST "
                                 "criterion on the same ad group (never attributed to one list alone)."
                                 if pr.get("metrics_granularity") == "ad_group_level" else
                                 " — metrics are per-audience, as supplied.")),
    ]


def md_kpis(model):
    s = model["summary"]
    cur = model["provenance"]["currency"]
    return [
        ("Applied audiences", f"{s['total_audiences']} ({s['scored']} scored, {s['excluded']} exclusion, "
                              f"{s['manual']} manual — no ad-group metrics)"),
        ("Flagged (Critical/High/Medium)", f"{s['critical']}/{s['high']}/{s['medium']}  "
                                           f"({s['clean']} clean)"),
        ("Flagged spend", _money(s["flagged_cost"], cur)),
        ("Audience spend concentration (top-3 share)", _pct(s["spend_top3_share"])),
        ("First-party readiness gaps", f"{s['first_party_gaps']} of {s['first_party_total']} "
                                       f"(Critical {s['first_party_critical']}, "
                                       f"High {s['first_party_high']}, Medium {s['first_party_medium']})"),
    ]


def md_narrative(model):
    s = model["summary"]
    pr = model["provenance"]
    lines = []
    if pr.get("metrics_granularity") == "ad_group_level":
        lines.append(
            "> **Metrics granularity: ad-group level, not per-list.** The Google Ads API does not "
            "expose performance metrics on the applied-audience criterion itself, only on the ad "
            "group's overall audience view — so when two or more USER_LIST criteria share an ad "
            "group, they show the SAME cost/clicks/impressions/conversions. Don't read a flagged "
            "audience's numbers as caused solely by that list; use the list name and bid modifier "
            "to judge which one actually needs attention.")
    if s.get("manual"):
        lines.append(
            f"> **{s['manual']} applied audience(s) have no ad-group metrics for this window** "
            "(no ad_group_audience_view activity recorded) and are marked `manual` — never "
            "scored, never dropped. See the full table below.")
    if s["scored"] and s["critical"] == 0 and s["high"] == 0 and s["medium"] == 0:
        lines.append(
            "> **No applied audience flagged is a clean result, not an error.** Every scored "
            "audience has a bid adjustment set, is enabled, is converting, and is within the "
            "cost/CTR bars relative to its own campaign's other audiences.")
    if s["total_audiences"] == 0:
        lines.append(
            "> **Zero applied audiences is a valid — and actionable — result.** No USER_LIST "
            "criteria are attached to any ad group in this pull. That is itself the finding: "
            "there is no remarketing/audience layer running yet (see the first-party readiness "
            "table below before building one).")
    if s["first_party_total"] == 0:
        lines.append(
            "> **No first-party readiness data supplied.** Enhanced Conversions, Customer "
            "Match, and Consent Mode v2 status cannot be read from the Google Ads API — pass "
            "`--first-party-csv` to `build_audience_report.py` with the readiness checklist "
            "filled in (see references/audience-targeting-filter.md) to get gap-scored "
            "recommendations for this section.")
    return lines


def md_sections(model):
    cur = model["provenance"]["currency"]
    secs = []

    secs.append({
        "title": "Priority breakdown — applied audiences",
        "note": "Every scored audience's priority tier, from the weighted signal score "
                "(Critical ≥ critical_threshold, High ≥ high_threshold, Medium = any signal, "
                "blank = clean). Excluded (negative/exclusion) criteria are never scored.",
        "headers": ["Priority", "Count", "Spend"],
        "aligns": ["l", "r", "r"],
        "rows": [
            ["Critical", model["summary"]["critical"],
             _money(sum(r["cost"] for r in model["rows"] if r["priority"] == "Critical"), cur)],
            ["High", model["summary"]["high"],
             _money(sum(r["cost"] for r in model["rows"] if r["priority"] == "High"), cur)],
            ["Medium", model["summary"]["medium"],
             _money(sum(r["cost"] for r in model["rows"] if r["priority"] == "Medium"), cur)],
            ["Clean", model["summary"]["clean"],
             _money(sum(r["cost"] for r in model["rows"] if r["status"] == "scored" and r["priority"] == ""), cur)],
            ["Excluded (never scored)", model["summary"]["excluded"], "—"],
            ["Manual (no ad-group metrics — never scored)", model["summary"]["manual"], "—"],
        ],
    })

    fp_rows = model["first_party"]
    secs.append({
        "title": "First-party readiness — Customer Match / Enhanced Conversions / Consent Mode",
        "note": "User-supplied (CSV/manual) — never read from the Google Ads API. `Type` is "
                "this row's data lineage (`config` = a technical setting; `manual` = an "
                "externally-tracked item such as a Customer Match list).",
        "headers": ["Category", "Item", "Type", "Readiness (as supplied)", "Gap?", "Severity", "Detail", "Verified"],
        "aligns": ["l", "l", "l", "l", "l", "l", "l", "l"],
        "rows": [[r["category"], r["item"], r["status"], r["readiness"] or "—",
                  "Yes" if r["gap"] else "No", r["severity"] or "—", r["detail"] or "—",
                  r["verified_date"] or "—"] for r in fp_rows],
        "empty": "_No first-party readiness data supplied — see the note above._",
    })
    return secs


def md_rows(model):
    """Every applied audience with a status — the no-row-loss layer for the md."""
    cur = model["provenance"]["currency"]
    gran = _granularity_label(model["provenance"])
    metrics_hdr = f"({gran})"
    headers = ["Campaign", "Ad Group", "Audience", "List Type", "Status", "Bid Modifier",
               f"Cost {metrics_hdr} ({cur})" if cur else f"Cost {metrics_hdr}",
               f"Conv. {metrics_hdr}", "CPA", f"CTR {metrics_hdr}", "Flags", "Score", "Priority"]
    out = []
    for r in model["rows"]:
        out.append([
            r["campaign"], r["ad_group"], r["list_name"], r["list_type"], r["status"],
            f"{r['bid_modifier']:.2f}",
            ("—" if r["cost"] is None else f"{r['cost']:,.2f}"),
            ("—" if r["conversions"] is None else f"{r['conversions']:.2f}"),
            _money(r.get("cpa"), cur), _pct(r["ctr"]), ", ".join(r.get("flags") or []) or "—",
            ("—" if r["score"] is None else f"{r['score']:.2f}"), r["priority"] or "",
        ])
    return {
        "title": "All applied audiences (every row, with status)",
        "note": "No row loss: every applied-audience criterion in the pull appears here — "
                "scored (with flags/score/priority), excluded (negative/exclusion criteria, "
                "never scored), or manual (no ad-group metrics for this window, never scored). "
                f"Cost/Conv./CTR are {gran} — see the granularity note above when ad-group level. "
                "Sorted by cost (highest first; manual rows have no known cost and sort with the "
                "zero-cost rows).",
        "headers": headers,
        "aligns": ["l", "l", "l", "l", "l", "r", "r", "r", "r", "r", "l", "r", "l"],
        "rows": out,
        "empty": "_No applied-audience criteria in this pull._",
    }


# --------------------------------------------------------------------------
# The spec object the toolkit consumes. No html_*/js_kernel keys — this
# skill's reduced bundle has no HTML explorer (references/
# audience-targeting-filter.md documents the emitted-format set for M3.1).
# --------------------------------------------------------------------------
SPEC = {
    "slug_prefix": "audience-targeting",
    "title": "Audience & Targeting Advisor",
    "window_labels": ("_unused_", "Applied-audience window"),
    "about": {
        "summary": "Scores every applied audience against its own campaign's other audiences "
                   "(no bid adjustment set, paused, zero conversions, high cost, or low CTR) "
                   "into a weighted priority tier, and reads first-party (Customer Match / "
                   "Enhanced Conversions / Consent Mode v2) readiness gaps from a user-supplied "
                   "checklist — this data is not in the Google Ads API.",
        "legend": [
            {"label": "Critical", "desc": "Weighted signal score at or above the critical threshold."},
            {"label": "High", "desc": "Weighted signal score at or above the high threshold."},
            {"label": "Medium", "desc": "At least one signal fired, below the high threshold."},
            {"label": "Excluded", "desc": "A negative/exclusion audience criterion — never scored."},
            {"label": "Manual", "desc": "No ad-group-level metrics for this window "
                                        "(no ad_group_audience_view activity) — never scored."},
        ],
    },
    "methodology_ref": "references/audience-targeting-filter.md",
    "md_params": md_params,
    "md_kpis": md_kpis,
    "md_narrative": md_narrative,
    "md_sections": md_sections,
    "md_rows": md_rows,
    # xlsx layout is attached in audience_xlsx_spec to keep this module
    # stdlib-only and import-light; build_audience_report.py wires it in.
}
