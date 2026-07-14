#!/usr/bin/env python3
"""xlsx layout for the Performance Max momentum filter (pure data — NO openpyxl import).

Consumed by _shared/render/xlsx.py. Three sheets:
  Controls       — tunable params (yellow) + self-rewriting logic + live
                   COUNTIF/SUMIF results.
  Campaign trends — every Pmax campaign + Status; active rows carry formulas
                   referencing the Controls cells (recompute live).
  Sensitivity    — static snapshot (the same sections as the markdown report).

The last-window cost column is named exactly "Cost" so the toolkit's {COSTR}
token resolves to it for the winner/loser SUMIFs.
"""
from __future__ import annotations

import pmax_spec as pspec


def _title(pr, brand):
    client = pr.get("client_name") or brand or "Account"
    return ("Performance Max Momentum — " + client
            + (f" ({pr['account_id']})" if pr.get("account_id") else ""))


def _subtitle(pr):
    cur = pr.get("currency") or "—"
    return (f"Currency {cur}  ·  last 14d {pr.get('window_last') or '—'}  ·  prev 14d "
            f"{pr.get('window_prev') or '—'}  ·  generated {pr.get('generated') or '—'}  ·  "
            "Performance Max campaigns only")


XLSX = {
    "sheets": ["Controls", "Campaign trends", "Sensitivity"],
    "controls_sheet": "Controls",
    "rows_sheet": "Campaign trends",
    "snapshot_sheet": "Sensitivity",
    "title": _title,
    "subtitle": _subtitle,
    "intro": ("Adjust any YELLOW cell. The logic text, the live counts, and every campaign on the "
              "'Campaign trends' tab recalculate instantly."),

    "params_title_row": 4,
    "params_title": "1 · MOMENTUM THRESHOLDS",
    "params": [
        {"row": 5, "label": "ROAS up multiple (Block 1)", "key": "roas_up_multiple", "fmt": "0.00",
         "note": "ROAS(last) must exceed this × ROAS(prev)   (rule = 1.50)",
         "dropdown": "1.00,1.25,1.50,1.75,2.00,2.50,3.00"},
        {"row": 6, "label": "ROAS down multiple (Block 2)", "key": "roas_down_multiple", "fmt": "0.00",
         "note": "ROAS(last) must fall below this × ROAS(prev)   (rule = 0.50)",
         "dropdown": "0.10,0.25,0.40,0.50,0.60,0.75,0.90,1.00"},
        {"row": 7, "label": "Minimum spend per window", "key": "min_cost", "fmt": "0.00",
         "note": "noise floor; 0 = the literal 'cost > 0' rule"},
    ],

    "logic": {
        "title_row": 9,
        "title": "2 · BLOCK LOGIC   (rewrites itself as you change the thresholds above)",
        "blocks": [
            {"head_row": 10, "head": "BLOCK 1 — scaling winner   →   candidate to scale budget",
             "rows": [
                 (11, '="Flag a Performance Max campaign as BLOCK 1 when ALL of these are true:"'),
                 (12, '="    1.  Conversions (last 14d)  >  Conversions (previous 14d)"'),
                 (13, '="    2.  ROAS (last 14d)  >  "&TEXT(C5,"0.00")&"  ×  ROAS (previous 14d)"'),
                 (14, '="    3.  Impressions (last 14d) > 0   AND   Cost (last 14d) > "&TEXT(C7,"0.00")'),
             ]},
            {"head_row": 16, "head": "BLOCK 2 — declining loser   →   investigate, restructure or cut",
             "rows": [
                 (17, '="Flag a Performance Max campaign as BLOCK 2 when ALL of these are true:"'),
                 (18, '="    1.  Conversions (last 14d)  <  Conversions (previous 14d)"'),
                 (19, '="    2.  ROAS (last 14d)  <  "&TEXT(C6,"0.00")&"  ×  ROAS (previous 14d)"'),
                 (20, '="    3.  Impressions (prev 14d) > 0   AND   Cost (prev 14d) > "&TEXT(C7,"0.00")'),
             ]},
        ],
    },

    "results": {
        "title_row": 22,
        "title": "3 · RESULTS (live)",
        "items": [
            {"row": 23, "label": "Block 1 — scaling winners", "cell": "C23",
             "formula": '=COUNTIF({QR},"Block 1")', "fmt": "0"},
            {"row": 24, "label": "Block 2 — declining losers", "cell": "C24",
             "formula": '=COUNTIF({QR},"Block 2")', "fmt": "0"},
            {"row": 25, "label": "Total flagged", "cell": "C25",
             "formula": '=COUNTIF({QR},"Block 1")+COUNTIF({QR},"Block 2")', "fmt": "0"},
            {"row": 26, "label": "Winner spend (last 14d)", "cell": "C26",
             "formula": '=SUMIF({QR},"Block 1",{COSTR})', "fmt": "MONEY"},
            {"row": 27, "label": "Loser spend (last 14d)", "cell": "C27",
             "formula": '=SUMIF({QR},"Block 2",{COSTR})', "fmt": "MONEY"},
            {"row": 28, "label": "Universe (Pmax campaigns)", "cell": "C28",
             "value_key": "universe", "fmt": "0", "muted": True},
            {"row": 29, "label": "No-activity (held out, see Sensitivity tab)", "cell": "C29",
             "value_key": "no_activity", "fmt": "0", "muted": True},
        ],
    },

    "controls_widths": {"A": 34, "B": 13, "C": 14, "D": 30, "E": 12, "F": 12, "G": 12, "H": 12},

    "rows_columns": [
        {"header": "Campaign", "kind": "data", "key": "campaign", "width": 34},
        {"header": "Status", "kind": "data", "key": "__status__", "width": 12},
        {"header": "Impr last", "kind": "data", "key": "impr_last", "width": 9},
        {"header": "Cost", "kind": "data", "key": "cost_last", "fmt": "MONEY", "width": 11},
        {"header": "Conv last", "kind": "data", "key": "conv_last", "fmt": "NUM", "width": 9},
        {"header": "Value last", "kind": "data", "key": "value_last", "fmt": "MONEY", "width": 11},
        {"header": "ROAS last", "kind": "data", "key": "roas_last", "fmt": "NUM", "width": 9},
        {"header": "Impr prev", "kind": "data", "key": "impr_prev", "width": 9},
        {"header": "Cost prev", "kind": "data", "key": "cost_prev", "fmt": "MONEY", "width": 10},
        {"header": "Conv prev", "kind": "data", "key": "conv_prev", "fmt": "NUM", "width": 9},
        {"header": "Value prev", "kind": "data", "key": "value_prev", "fmt": "MONEY", "width": 11},
        {"header": "ROAS prev", "kind": "data", "key": "roas_prev", "fmt": "NUM", "width": 9},
        {"header": "Conv up?", "kind": "formula", "scored": True, "width": 9,
         "formula": '=IF({C:Conv last}{row}>{C:Conv prev}{row},TRUE,FALSE)'},
        {"header": "ROAS up?", "kind": "formula", "scored": True, "width": 9,
         "formula": '=IF({C:ROAS last}{row}>{ctrl:roas_up_multiple}*{C:ROAS prev}{row},TRUE,FALSE)'},
        {"header": "Block1?", "kind": "formula", "scored": True, "width": 8,
         "formula": '=AND({C:Conv up?}{row},{C:ROAS up?}{row},{C:Impr last}{row}>0,{C:Cost}{row}>{ctrl:min_cost})'},
        {"header": "Conv down?", "kind": "formula", "scored": True, "width": 10,
         "formula": '=IF({C:Conv last}{row}<{C:Conv prev}{row},TRUE,FALSE)'},
        {"header": "ROAS down?", "kind": "formula", "scored": True, "width": 10,
         "formula": '=IF({C:ROAS last}{row}<{ctrl:roas_down_multiple}*{C:ROAS prev}{row},TRUE,FALSE)'},
        {"header": "Block2?", "kind": "formula", "scored": True, "width": 8,
         "formula": '=AND({C:Conv down?}{row},{C:ROAS down?}{row},{C:Impr prev}{row}>0,{C:Cost prev}{row}>{ctrl:min_cost})'},
        {"header": "Qualifies", "kind": "formula", "scored": True, "width": 11,
         "formula": '=IF({C:Block1?}{row},"Block 1",IF({C:Block2?}{row},"Block 2",""))'},
    ],
    "rows_freeze": "C2",

    "snapshot_title": "Winners / losers, sensitivity & near-misses",
    "snapshot_intro": "Static snapshot at the generated parameters. Use the Controls tab to re-tune live.",
    "snapshot_sections": pspec.md_sections,
    # Widened for the M1.4 sections: asset-group concentration / cannibalization
    # (up to 7 cols) and the advisor recommendations table (long text columns).
    "snapshot_widths": {"A": 40, "B": 30, "C": 22, "D": 18, "E": 18, "F": 40, "G": 12},

    "check": {
        "param_cells": ["C5", "C6", "C7"],
        "cached_cell": "C23",
        "status_header": "Status",
        "qualifies_header": "Qualifies",
    },
}
