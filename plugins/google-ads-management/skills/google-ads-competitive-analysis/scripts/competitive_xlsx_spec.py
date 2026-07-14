#!/usr/bin/env python3
"""xlsx layout for the competitive-pressure filter (pure data — NO openpyxl
import). Consumed by _shared/render/xlsx.py. Reproduces the reference
workbook shape: Controls (tunable params + self-rewriting logic + live
COUNTIF/SUMIF results + the Auction Insights competitor table), Live pressure
(every campaign + Status, scored rows carry formulas referencing the Controls
cells), and a Snapshot (the same sections as the markdown report).
"""
from __future__ import annotations

import competitive_spec as cspec


def _title(pr, brand):
    client = pr.get("client_name") or brand or "Account"
    return ("Interactive Competitive Pressure Filter — " + client
            + (f" ({pr['account_id']})" if pr.get("account_id") else ""))


def _subtitle(pr):
    cur = pr.get("currency") or "—"
    ai = " · Auction Insights: user-supplied CSV" if pr.get("auction_insights_source") == "user_csv" \
        else " · Auction Insights: not supplied (own-side only)"
    return (f"Currency {cur}  ·  this week {pr.get('window_this') or '—'}  ·  prior week "
            f"{pr.get('window_prior') or '—'}  ·  generated {pr.get('generated') or '—'}  ·  "
            f"Search campaigns only{ai}")


XLSX = {
    "sheets": ["Controls", "Live pressure", "Snapshot"],
    "controls_sheet": "Controls",
    "rows_sheet": "Live pressure",
    "snapshot_sheet": "Snapshot",
    "title": _title,
    "subtitle": _subtitle,
    "intro": ("Adjust any YELLOW cell. The logic text, the live counts, and every campaign on "
              "the 'Live pressure' tab recalculate instantly."),

    "params_title_row": 4,
    "params_title": "1 · FLAG PARAMETERS",
    "params": [
        {"row": 5, "label": "IS-drop flag threshold", "key": "is_drop_flag", "fmt": "0.00%",
         "note": "WoW percentage-point drop   (rule = 5.00%)",
         "dropdown": "0.02,0.03,0.05,0.08,0.10,0.15,0.20"},
        {"row": 6, "label": "CPC-jump flag threshold", "key": "cpc_jump_flag", "fmt": "0.00%",
         "note": "WoW CPC increase   (rule = 15.00%)",
         "dropdown": "0.05,0.10,0.15,0.20,0.30,0.50"},
        {"row": 7, "label": "Minimum this-week spend", "key": "min_cost", "fmt": "MONEY",
         "note": "flag eligibility floor   (rule = 50.00)"},
    ],

    "logic": {
        "title_row": 9,
        "title": "2 · FLAG & BLOCK LOGIC   (rewrites itself as you change the values above)",
        "blocks": [
            {"head_row": 10, "head": "FLAG — a campaign is flagged when ALL of these are true",
             "rows": [
                 (11, '="    1.  This-week cost  ≥  "&TEXT(C7,"#,##0.00")'),
                 (12, '="    2.  Has both this-week and prior-week impression-share data"'),
                 (13, '="    3.  IS Δ (WoW)  ≤  -"&TEXT(C5,"0.00%")&"   OR   CPC Δ (WoW)  ≥  "&TEXT(C6,"0.00%")'),
             ]},
            {"head_row": 15, "head": "BLOCK ATTRIBUTION — for a flagged campaign",
             "rows": [
                 (16, '="Rank pressure  when the rank-lost-IS delta (WoW) ≥ the budget-lost-IS delta (WoW)"'),
                 (17, '="Budget capped  otherwise (the budget-lost-IS delta is the larger driver)"'),
             ]},
        ],
    },

    "results": {
        "title_row": 19,
        "title": "3 · RESULTS (live)",
        "items": [
            {"row": 20, "label": "Rank pressure campaigns", "cell": "C20",
             "formula": '=COUNTIF({R:Block},"Rank pressure")', "fmt": "0"},
            {"row": 21, "label": "Budget capped campaigns", "cell": "C21",
             "formula": '=COUNTIF({R:Block},"Budget capped")', "fmt": "0"},
            {"row": 22, "label": "Total flagged", "cell": "C22",
             "formula": '=COUNTIF({R:Block},"Rank pressure")+COUNTIF({R:Block},"Budget capped")', "fmt": "0"},
            {"row": 23, "label": "Flagged spend (this week)", "cell": "C23",
             "formula": '=SUMIF({R:Block},"Rank pressure",{R:Cost this wk})'
                        '+SUMIF({R:Block},"Budget capped",{R:Cost this wk})', "fmt": "MONEY"},
            {"row": 24, "label": "Campaigns (universe)", "cell": "C24",
             "value_key": "campaigns", "fmt": "0", "muted": True},
            {"row": 25, "label": "Competitor rows (Auction Insights CSV)", "cell": "C25",
             "value_key": "competitor_rows", "fmt": "0", "muted": True},
        ],
    },

    "aux": [
        {"title_row": 27,
         "title": "4 · AUCTION INSIGHTS COMPETITORS (user-supplied CSV — NOT from the Google Ads API)",
         "header_row": 28, "start_row": 29, "source": "competitors", "sort_key": "impression_share",
         "columns": [("Domain", "domain", None), ("Campaign", "campaign", None),
                     ("Impr. share", "impression_share", "PCT"),
                     ("Overlap rate", "overlap_rate", "PCT"),
                     ("Position above rate", "position_above_rate", "PCT")]},
    ],

    "controls_widths": {"A": 40, "B": 13, "C": 16, "D": 30, "E": 12, "F": 12},

    "rows_columns": [
        {"header": "Campaign", "kind": "data", "key": "campaign", "width": 32},
        {"header": "Status", "kind": "data", "key": "__status__", "width": 13},
        {"header": "Cost this wk", "kind": "data", "key": "cost_this", "fmt": "MONEY", "width": 12},
        {"header": "Cost prior wk", "kind": "data", "key": "cost_prior", "fmt": "MONEY", "width": 12},
        {"header": "IS this wk", "kind": "data", "key": "impression_share_this", "fmt": "PCT", "width": 10},
        {"header": "IS prior wk", "kind": "data", "key": "impression_share_prior", "fmt": "PCT", "width": 10},
        {"header": "IS Δ", "kind": "data", "key": "is_delta_pp", "fmt": "PCT", "width": 9},
        {"header": "CPC this wk", "kind": "data", "key": "avg_cpc_this", "fmt": "MONEY", "width": 11},
        {"header": "CPC prior wk", "kind": "data", "key": "avg_cpc_prior", "fmt": "MONEY", "width": 11},
        {"header": "CPC Δ", "kind": "data", "key": "cpc_delta_pct", "fmt": "PCT", "width": 9},
        {"header": "Rank-lost Δ", "kind": "data", "key": "rank_lost_delta", "fmt": "PCT", "width": 11},
        {"header": "Budget-lost Δ", "kind": "data", "key": "budget_lost_delta", "fmt": "PCT", "width": 12},
        {"header": "Eligible?", "kind": "formula", "scored": True, "width": 9,
         "formula": '=IF({C:Cost this wk}{row}>={ctrl:min_cost},TRUE,FALSE)'},
        {"header": "IS-drop fired?", "kind": "formula", "scored": True, "width": 12,
         "formula": '=IF(AND(ISNUMBER({C:IS Δ}{row}),{C:IS Δ}{row}<=-{ctrl:is_drop_flag}),TRUE,FALSE)'},
        {"header": "CPC-jump fired?", "kind": "formula", "scored": True, "width": 12,
         "formula": '=IF(AND(ISNUMBER({C:CPC Δ}{row}),{C:CPC Δ}{row}>={ctrl:cpc_jump_flag}),TRUE,FALSE)'},
        {"header": "Flagged?", "kind": "formula", "scored": True, "width": 8,
         "formula": '=AND({C:Eligible?}{row},OR({C:IS-drop fired?}{row},{C:CPC-jump fired?}{row}))'},
        {"header": "Block", "kind": "formula", "scored": True, "width": 13,
         "formula": '=IF({C:Flagged?}{row},IF({C:Rank-lost Δ}{row}>={C:Budget-lost Δ}{row},'
                    '"Rank pressure","Budget capped"),"")'},
    ],
    "rows_freeze": "C2",

    "snapshot_title": "Sensitivity, near-misses & concentration",
    "snapshot_intro": "Static snapshot at the generated parameters. Use the Controls tab to re-tune live.",
    "snapshot_sections": cspec.md_sections,
    "snapshot_widths": {"A": 44, "B": 30, "C": 16, "D": 16, "E": 14, "F": 10},

    "check": {
        "param_cells": ["C5", "C6", "C7"],
        "cached_cell": "C20",
        "status_header": "Status",
        "qualifies_header": "Block",
    },
}
