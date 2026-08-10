#!/usr/bin/env python3
"""xlsx layout for the account-health checks (pure data — NO openpyxl import).

Consumed by _shared/render/xlsx.py. This IS the interactive surface for the
reduced bundle (no HTML explorer): Controls (4 tunable thresholds + self-
rewriting logic text + live COUNTIFS results) + "Live checks" (every checked
entity, one row per (check, entity), with per-check Flagged?/Pre-score
formulas that branch on the Check column) + a static Checks snapshot.
"""
from __future__ import annotations

import health_core as core
import health_spec as hspec
from render import model as M  # noqa: E402  (source_label — HM-572 canonical "Data source" line)


def _title(pr, brand):
    client = pr.get("client_name") or brand or "Account"
    return ("Account Health & Structure — " + client
            + (f" ({pr['account_id']})" if pr.get("account_id") else ""))


def _subtitle(pr):
    cur = pr.get("currency") or "—"
    return (f"Currency {cur}  ·  30-day window {pr.get('window_30d') or '—'}  ·  "
            f"generated {pr.get('generated') or '—'}  ·  source {M.source_label(pr.get('source'))}")


_M = core.CHECK_MAX_SCORE  # {"sprawl": 6.0, "no_negatives": 7.0, ...}


def _route_cond(check: str) -> str:
    return '{C:Check}{row}="' + core.CHECK_LABELS[check] + '"'


def _nest_by_check(value_by_check: dict, fallback: str) -> str:
    """Build a provably-balanced `=IF(check=A,valA,IF(check=B,valB,...,fallback))`
    over core.CHECKS, in declaration order — one shared constructor for every
    per-check branching formula (Flagged?, Pre-score), so paren-matching is
    never hand-typed twice."""
    expr = fallback
    for check in reversed(core.CHECKS):
        expr = f'IF({_route_cond(check)},{value_by_check[check]},{expr})'
    return "=" + expr


_FLAGGED_VALUE = {
    "sprawl": 'IF(AND({C:Keywords}{row}>={ctrl:sprawl_min_keywords},'
              '{C:Ad-group CTR}{row}<{ctrl:sprawl_max_ctr}),"yes","")',
    "no_negatives": 'IF({C:Negatives}{row}<={ctrl:negatives_max_count},"yes","")',
    "automation_no_data": 'IF(AND({C:Automated bidding?}{row}="yes",'
                          '{C:Conversions 30d}{row}<{ctrl:automation_min_conversions}),"yes","")',
    "naming": 'IF({C:Name OK?}{row}="no","yes","")',
    "pmax_cannibalization": 'IF(AND({C:PMax?}{row}="yes",{C:Brand present?}{row}="yes"),"yes","")',
}
# Liveness gate (HM-603): a dormant campaign/ad group never trips a check, so the
# Flagged?/Pre-score formulas short-circuit to ""/0 before the per-check branch —
# mirrors health_core.score_rows (the {C:Liveness} guard wraps the nested IF).
_FLAGGED_FORMULA = ('=IF({C:Liveness}{row}="dormant","",'
                    + _nest_by_check(_FLAGGED_VALUE, fallback='""')[1:] + ')')

_PRE_SCORE_VALUE = {c: f'IF({{C:Flagged?}}{{row}}="yes",{_M[c]},0)' for c in core.CHECKS}
_PRE_SCORE_FORMULA = ('=IF({C:Liveness}{row}="dormant",0,'
                      + _nest_by_check(_PRE_SCORE_VALUE, fallback="0")[1:] + ')')

XLSX = {
    "sheets": ["Controls", "Live checks", "Checks snapshot"],
    "controls_sheet": "Controls",
    "rows_sheet": "Live checks",
    "snapshot_sheet": "Checks snapshot",
    "title": _title,
    "subtitle": _subtitle,
    "intro": ("Adjust any YELLOW cell. The logic text, the live counts, and every row on the "
              "'Live checks' tab recalculate instantly. Naming and PMax-cannibalization are not "
              "numerically tunable (see the logic text) — their thresholds live in the findings "
              "JSON / are confirmed manually."),

    "params_title_row": 4,
    "params_title": "1 · TUNABLE THRESHOLDS",
    "params": [
        {"row": 5, "label": "Ad-group sprawl · min keywords", "key": "sprawl_min_keywords", "fmt": "0",
         "note": "flag when enabled keyword count ≥ this   (rule = 20)",
         "dropdown": "10,15,20,25,30,40,50"},
        {"row": 6, "label": "Ad-group sprawl · max CTR", "key": "sprawl_max_ctr", "fmt": "PCT",
         "note": "flag when ad-group CTR (30d) < this   (rule = 3.00%)",
         "dropdown": "0.01,0.02,0.03,0.04,0.05,0.06"},
        {"row": 7, "label": "No negatives · max allowed", "key": "negatives_max_count", "fmt": "0",
         "note": "flag Search campaigns with ≤ this many negatives   (rule = 0)",
         "dropdown": "0,1,2,3"},
        {"row": 8, "label": "Automation · min conversions (30d)", "key": "automation_min_conversions", "fmt": "0",
         "note": "flag automated bidding below this   (rule = 30)",
         "dropdown": "10,20,30,40,50,75,100"},
    ],

    "logic": {
        "title_row": 10,
        "title": "2 · CHECK LOGIC   (rewrites itself as you change the thresholds above)",
        "blocks": [
            {"head_row": 11, "head": "AD-GROUP SPRAWL — segment into themed 5–10 keyword groups",
             "rows": [
                 (12, '="Flag an ad group as SPRAWL when BOTH are true:"'),
                 (13, '="    1.  Enabled keyword count  ≥  "&C5'),
                 (14, '="    2.  Ad-group CTR (30 days)  <  "&TEXT(C6,"0.00%")'),
             ]},
            {"head_row": 16, "head": "NO CAMPAIGN NEGATIVES — add campaign-level negatives",
             "rows": [
                 (17, '="Flag a Search campaign as NO NEGATIVES when:"'),
                 (18, '="    1.  Campaign-level negative keywords  ≤  "&C7'),
             ]},
            {"head_row": 20, "head": "AUTOMATION WITHOUT DATA — revert to Manual CPC / Max Clicks",
             "rows": [
                 (21, '="Flag a campaign as AUTOMATION WITHOUT DATA when BOTH are true:"'),
                 (22, '="    1.  Bidding strategy is automated (Maximize Conversions/Value, Target CPA/ROAS/IS)"'),
                 (23, '="    2.  Conversions (30 days)  <  "&C8'),
             ]},
            {"head_row": 25, "head": "NAMING INCONSISTENCY — rename to the convention (manual, Editor)",
             "rows": [
                 (26, '="Flag a campaign when its name fails the default convention regex — NOT tunable "'
                      '&"here (edit params.naming_regex in the findings JSON) and confirm the segments/geos "'
                      '&"with the user before renaming."'),
             ]},
            {"head_row": 28, "head": "PMAX BRAND CANNIBALIZATION — confirm the brand-exclusion list (UI)",
             "rows": [
                 (29, '="Flag a PMax campaign as CANNIBALIZATION when BOTH are true:"'),
                 (30, '="    1.  The account also runs an ENABLED brand Search campaign"'),
                 (31, '="    2.  Whether a brand-exclusion list is attached is MANUAL — the read-only API "'
                      '&"cannot confirm it; verify in the Google Ads UI."'),
             ]},
        ],
    },

    "results": {
        "title_row": 33,
        "title": "3 · RESULTS (live)",
        "items": [
            {"row": 34, "label": core.CHECK_LABELS["sprawl"] + " — flagged", "cell": "C34",
             "formula": '=COUNTIFS({R:Check},"' + core.CHECK_LABELS["sprawl"] + '",{R:Flagged?},"yes")', "fmt": "0"},
            {"row": 35, "label": core.CHECK_LABELS["no_negatives"] + " — flagged", "cell": "C35",
             "formula": '=COUNTIFS({R:Check},"' + core.CHECK_LABELS["no_negatives"] + '",{R:Flagged?},"yes")', "fmt": "0"},
            {"row": 36, "label": core.CHECK_LABELS["automation_no_data"] + " — flagged", "cell": "C36",
             "formula": '=COUNTIFS({R:Check},"' + core.CHECK_LABELS["automation_no_data"] + '",{R:Flagged?},"yes")', "fmt": "0"},
            {"row": 37, "label": core.CHECK_LABELS["naming"] + " — flagged", "cell": "C37",
             "formula": '=COUNTIFS({R:Check},"' + core.CHECK_LABELS["naming"] + '",{R:Flagged?},"yes")', "fmt": "0"},
            {"row": 38, "label": core.CHECK_LABELS["pmax_cannibalization"] + " — flagged", "cell": "C38",
             "formula": '=COUNTIFS({R:Check},"' + core.CHECK_LABELS["pmax_cannibalization"] + '",{R:Flagged?},"yes")', "fmt": "0"},
            {"row": 39, "label": "Total flagged (all checks)", "cell": "C39",
             "formula": '=COUNTIF({R:Flagged?},"yes")', "fmt": "0"},
            {"row": 40, "label": "Entities checked (all checks, no row loss)", "cell": "C40",
             "value_key": "universe", "fmt": "0", "muted": True},
        ],
    },

    "controls_widths": {"A": 40, "B": 13, "C": 14, "D": 26},

    "rows_columns": [
        {"header": "Check", "kind": "data", "key": "check_label", "width": 26},
        {"header": "Entity type", "kind": "data", "key": "entity_type", "width": 12},
        {"header": "Entity", "kind": "data", "key": "entity_name", "width": 30},
        {"header": "Campaign", "kind": "data", "key": "campaign_name", "width": 30},
        {"header": "Keywords", "kind": "data", "key": "keyword_count", "fmt": "NUM", "width": 10},
        {"header": "Ad-group CTR", "kind": "data", "key": "ad_group_ctr", "fmt": "PCT", "width": 12},
        {"header": "Negatives", "kind": "data", "key": "negative_count", "fmt": "NUM", "width": 10},
        {"header": "Bidding strategy", "kind": "data", "key": "bidding_strategy_type", "width": 22},
        {"header": "Automated bidding?", "kind": "data", "key": "automated_bidding_label", "width": 15},
        {"header": "Conversions 30d", "kind": "data", "key": "conversions_30d", "fmt": "NUM", "width": 13},
        {"header": "Name OK?", "kind": "data", "key": "name_pattern_ok_label", "width": 10},
        {"header": "PMax?", "kind": "data", "key": "pmax_present_label", "width": 8},
        {"header": "Brand present?", "kind": "data", "key": "brand_present_label", "width": 13},
        {"header": "Brand excl. confirmed?", "kind": "data", "key": "has_brand_exclusion_label", "width": 18},
        {"header": "Status", "kind": "data", "key": "__status__", "width": 10},
        {"header": "Liveness", "kind": "data", "key": "liveness", "width": 15},
        {"header": "Pre-score", "kind": "formula", "width": 10, "fmt": "0.0",
         "formula": _PRE_SCORE_FORMULA},
        {"header": "Flagged?", "kind": "formula", "width": 9,
         "formula": _FLAGGED_FORMULA},
    ],
    "rows_freeze": "C2",
    # default scored_status="scored": config/manual rows (naming/pmax) get the
    # amber "needs confirmation" shading on Status — a deliberate, honest cue.
    # Pre-score/Flagged? carry no "scored" gate (no `"scored": True` below), so
    # they are always written — every row's formula branches on its own Check.

    "snapshot_title": "Checks snapshot",
    "snapshot_intro": "Static snapshot at the generated parameters. Use the Controls tab to re-tune "
                       "the live Flagged?/Pre-score columns on 'Live checks'.",
    "snapshot_sections": hspec.md_sections,
    "snapshot_widths": {"A": 30, "B": 30, "C": 16, "D": 16, "E": 20, "F": 10},

    "check": {
        "param_cells": ["C5", "C6", "C7", "C8"],
        "cached_cell": "C39",
        "status_header": "Status",
        "qualifies_header": "Flagged?",
    },
}
