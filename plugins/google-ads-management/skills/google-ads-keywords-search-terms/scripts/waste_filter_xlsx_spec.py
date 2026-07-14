#!/usr/bin/env python3
"""xlsx layout for the search-term waste filter (pure data — NO openpyxl import).

Consumed by _shared/render/xlsx.py. Reproduces the reference workbook:
Controls (tunable params + self-rewriting logic + live COUNTIF/SUMIF results +
campaign benchmarks), Live filter (every term + Status, scored rows carry
formulas referencing the Controls cells), and a Sensitivity snapshot (the same
sections as the markdown report).
"""
from __future__ import annotations

import waste_filter_core as core
import waste_filter_spec as wfspec


def _title(pr, brand):
    client = pr.get("client_name") or brand or "Account"
    return ("Interactive Search-Term Waste Filter — " + client
            + (f" ({pr['account_id']})" if pr.get("account_id") else ""))


def _subtitle(pr):
    cur = pr.get("currency") or "—"
    src = wfspec.SOURCE_LABELS.get(pr.get("source", "mcp"), pr.get("source", ""))
    return (f"Currency {cur}  ·  90-day {pr.get('window_90d') or '—'}  ·  30-day "
            f"{pr.get('window_30d') or '—'}  ·  generated {pr.get('generated') or '—'}  ·  "
            f"Search campaigns only  ·  Data source: {src}")


_TOGGLE_OPTIONS = [[lbl, en] for lbl, en in core.MATCH_TYPES]

XLSX = {
    "sheets": ["Controls", "Live filter", "Sensitivity"],
    "controls_sheet": "Controls",
    "rows_sheet": "Live filter",
    "snapshot_sheet": "Sensitivity",
    "title": _title,
    "subtitle": _subtitle,
    "intro": ("Adjust any YELLOW cell. The logic text, the live counts, and every term on the "
              "'Live filter' tab recalculate instantly."),

    "params_title_row": 4,
    "params_title": "1 · FILTER PARAMETERS",
    "params": [
        {"row": 5, "label": "CTR threshold factor", "key": "ctr_factor", "fmt": "0.00",
         "note": "× campaign CTR   (rule = 0.50)", "dropdown": "0.10,0.20,0.25,0.30,0.40,0.50,0.60,0.75,0.90,1.00"},
        {"row": 6, "label": "Cost multiple", "key": "cost_multiple", "fmt": "0.00",
         "note": "× campaign cost/conversion   (rule = 2.50)", "dropdown": "0.25,0.50,0.75,1.00,1.25,1.50,2.00,2.50,3.00"},
        {"row": 7, "label": "Block 1 · max conversions (90d)", "key": "block1_max_conv_90d", "fmt": "0",
         "note": "non-converting if ≤ this   (rule = 0)", "dropdown": "0,1,2,3,5"},
        {"row": 8, "label": "Block 2 · min conversions (90d)", "key": "block2_min_conv_90d", "fmt": "0",
         "note": "converted earlier if > this   (rule = 0)", "dropdown": "0,1,2,3"},
        {"row": 9, "label": "Block 2 · max conversions (30d)", "key": "block2_max_conv_30d", "fmt": "0",
         "note": "cold now if ≤ this   (rule = 0)", "dropdown": "0,1,2,3"},
    ],

    "toggles": {
        "title_row": 11,
        "section_title": "2 · MATCH TYPES IN SCOPE   (toggle yes/no)",
        "start_row": 12,
        "options": _TOGGLE_OPTIONS,
        "param_key": "match_types_in_scope",
        "dropdown": "yes,no",
        "note": ("D12", "Pure Exact match is excluded at the data source and cannot be re-added here."),
    },

    "logic": {
        "title_row": 18,
        "title": "3 · FILTER & BLOCK LOGIC   (rewrites itself as you change the values above)",
        "blocks": [
            {"head_row": 19, "head": "BLOCK 1 — never-converted waste   →   add as negative keyword",
             "rows": [
                 (20, '="Flag a search term as BLOCK 1 when ALL of these are true:"'),
                 (21, '="    1.  Conversions (90 days)  ≤  "&C7'),
                 (22, '="    2.  Match type is one of the in-scope types toggled ""yes"" above"'),
                 (23, '="    3.  CTR  <  "&TEXT(C5,"0.00")&"  ×  its own campaign CTR"'),
                 (24, '="    4.  Cost  >  "&TEXT(C6,"0.00")&"  ×  its own campaign cost/conversion"'),
             ]},
            {"head_row": 26, "head": "BLOCK 2 — decaying converters   →   review then negate",
             "rows": [
                 (27, '="Flag a search term as BLOCK 2 when ALL of these are true:"'),
                 (28, '="    1.  Conversions (90 days)  >  "&C8&"     (converted earlier in the window)"'),
                 (29, '="    2.  Conversions (30 days)  ≤  "&C9&"     (but has gone cold recently)"'),
                 (30, '="    3.  Match type is one of the in-scope types toggled ""yes"" above"'),
                 (31, '="    4.  CTR  <  "&TEXT(C5,"0.00")&"  ×  campaign CTR"'),
                 (32, '="    5.  Cost  >  "&TEXT(C6,"0.00")&"  ×  campaign cost/conversion"'),
             ]},
        ],
    },

    "results": {
        "title_row": 34,
        "title": "4 · RESULTS (live)",
        "items": [
            {"row": 35, "label": "Block 1 qualifying terms", "cell": "C35",
             "formula": '=COUNTIF({QR},"Block 1")', "fmt": "0"},
            {"row": 36, "label": "Block 2 qualifying terms", "cell": "C36",
             "formula": '=COUNTIF({QR},"Block 2")', "fmt": "0"},
            {"row": 37, "label": "Total qualifying terms", "cell": "C37",
             "formula": '=COUNTIF({QR},"Block 1")+COUNTIF({QR},"Block 2")', "fmt": "0"},
            {"row": 38, "label": "Wasted spend of qualifying", "cell": "C38",
             "formula": '=SUMIF({QR},"Block 1",{COSTR})+SUMIF({QR},"Block 2",{COSTR})', "fmt": "MONEY"},
            {"row": 39, "label": "Candidate universe (loose-match terms)", "cell": "C39",
             "value_key": "universe", "fmt": "0", "muted": True},
            {"row": 40, "label": "Terms with no benchmark (see Sensitivity tab)", "cell": "C40",
             "value_key": "no_benchmark", "fmt": "0", "muted": True},
        ],
    },

    "aux": [
        {"title_row": 42, "title": "5 · CAMPAIGN BENCHMARKS (90 days) — what the % and × multipliers measure against",
         "header_row": 43, "start_row": 44, "source": "benchmarks", "sort_key": "cost",
         "columns": [("Campaign", "name", None), ("CTR", "ctr", "PCT"), ("Cost", "cost", "MONEY"),
                     ("Conversions", "conv", "NUM"), ("Cost/conv", "cpa", "MONEY")]},
    ],

    "controls_widths": {"A": 36, "B": 13, "C": 14, "D": 22, "E": 12, "F": 12, "G": 12, "H": 12},

    "rows_columns": [
        {"header": "Campaign", "kind": "data", "key": "campaign", "width": 32},
        {"header": "Ad group", "kind": "data", "key": "ad_group", "width": 22},
        {"header": "Search term", "kind": "data", "key": "term", "width": 40},
        {"header": "Match type", "kind": "data", "key": "match_type", "width": 12},
        {"header": "Status", "kind": "data", "key": "__status__", "width": 13},
        {"header": "Impr", "kind": "data", "key": "impressions", "width": 7},
        {"header": "Clicks", "kind": "data", "key": "clicks", "width": 7},
        {"header": "CTR", "kind": "data", "key": "ctr", "fmt": "PCT", "width": 8},
        {"header": "Cost", "kind": "data", "key": "cost", "fmt": "MONEY", "width": 10},
        {"header": "Conv 90d", "kind": "data", "key": "conv90", "fmt": "NUM", "width": 9},
        {"header": "Conv 30d", "kind": "data", "key": "conv30", "fmt": "NUM", "width": 9},
        {"header": "Match in scope?", "kind": "formula", "scored": True, "width": 13,
         "formula": '=IFERROR(VLOOKUP({C:Match type}{row},{MT_RANGE},2,FALSE),"no")'},
        {"header": "Campaign CTR", "kind": "data", "key": "camp_ctr", "fmt": "PCT", "width": 12},
        {"header": "Campaign cost/conv", "kind": "data", "key": "camp_cpa", "fmt": "MONEY", "width": 16},
        {"header": "CTR threshold", "kind": "formula", "scored": True, "fmt": "PCT", "width": 12,
         "formula": '={C:Campaign CTR}{row}*{ctrl:ctr_factor}'},
        {"header": "Cost threshold", "kind": "formula", "scored": True, "fmt": "MONEY", "width": 12,
         "formula": '={C:Campaign cost/conv}{row}*{ctrl:cost_multiple}'},
        {"header": "CTR pass?", "kind": "formula", "scored": True, "width": 9,
         "formula": '=IF({C:CTR}{row}<{C:CTR threshold}{row},TRUE,FALSE)'},
        {"header": "Cost pass?", "kind": "formula", "scored": True, "width": 9,
         "formula": '=IF({C:Cost}{row}>{C:Cost threshold}{row},TRUE,FALSE)'},
        {"header": "Block1?", "kind": "formula", "scored": True, "width": 8,
         "formula": '=AND({C:Conv 90d}{row}<={ctrl:block1_max_conv_90d},{C:Match in scope?}{row}="yes",{C:CTR pass?}{row},{C:Cost pass?}{row})'},
        {"header": "Block2?", "kind": "formula", "scored": True, "width": 8,
         "formula": '=AND({C:Conv 90d}{row}>{ctrl:block2_min_conv_90d},{C:Conv 30d}{row}<={ctrl:block2_max_conv_30d},{C:Match in scope?}{row}="yes",{C:CTR pass?}{row},{C:Cost pass?}{row})'},
        {"header": "Qualifies", "kind": "formula", "scored": True, "width": 11,
         "formula": '=IF({C:Block1?}{row},"Block 1",IF({C:Block2?}{row},"Block 2",""))'},
    ],
    "rows_freeze": "C2",

    "snapshot_title": "Sensitivity & near-misses",
    "snapshot_intro": "Static snapshot at the generated parameters. Use the Controls tab to re-tune live.",
    "snapshot_sections": wfspec.md_sections,
    "snapshot_widths": {"A": 44, "B": 30, "C": 14, "D": 16, "E": 22, "F": 8},

    "check": {
        "param_cells": ["C5", "C6", "C7", "C8", "C9"],
        "cached_cell": "C35",
        "status_header": "Status",
        "qualifies_header": "Qualifies",
    },
}
