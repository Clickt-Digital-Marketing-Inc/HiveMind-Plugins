#!/usr/bin/env python3
"""xlsx layout for the PMax listing-group waste filter (pure data — NO openpyxl).

Consumed by the frozen _shared/render/xlsx.py. The frozen renderer builds exactly
three sheets (Controls / rows / snapshot), so:
  * Controls    — the Expensiveness-factor + tier-signal (concentration-share-min /
                  weak-ROAS-max) inputs + self-rewriting Block 1/2 logic + live
                  COUNTIF/SUMIF results (including tier signals) + campaign benchmarks.
  * Live filter — every listing-group PARTITION + Status; scored rows carry
                  block formulas referencing the Controls cells (live-tunable in
                  Excel); the tier-signal columns (spend share / ROAS / over-conc? /
                  weak ROAS? / tier signal?) are live for EVERY row regardless of
                  status — no-row-loss holds for the concentration read too.
  * Sensitivity — a static snapshot: recommendations, tier concentration, partition
                  sensitivity/near-misses/excluded AND the full PRODUCTS table +
                  product tier signals/sensitivity/near-misses (products are the
                  second universe; no separate sheet needed, so the frozen toolkit
                  is untouched).
"""
from __future__ import annotations

import pmax_listing_spec as pspec


def _title(pr, brand):
    client = pr.get("client_name") or brand or "Account"
    return ("Interactive PMax Listing-Group Waste Filter — " + client
            + (f" ({pr['account_id']})" if pr.get("account_id") else ""))


def _subtitle(pr):
    cur = pr.get("currency") or "—"
    return (f"Currency {cur}  ·  30-day {pr.get('window_30d') or '—'}  ·  generated "
            f"{pr.get('generated') or '—'}  ·  Performance Max only")


XLSX = {
    "sheets": ["Controls", "Live filter", "Sensitivity"],
    "controls_sheet": "Controls",
    "rows_sheet": "Live filter",
    "snapshot_sheet": "Sensitivity",
    "title": _title,
    "subtitle": _subtitle,
    "intro": ("Adjust the YELLOW Expensiveness-factor cell. The logic text, the live counts, and "
              "every partition on the 'Live filter' tab recalculate instantly. (Products are a "
              "static snapshot on the 'Sensitivity' tab — re-tune them live in the HTML explorer.)"),

    "params_title_row": 4,
    "params_title": "1 · EXPENSIVENESS FACTOR & TIER SIGNAL",
    "params": [
        {"row": 5, "label": "Expensiveness factor", "key": "expensiveness_factor", "fmt": "0.00",
         "note": "× campaign cost/conv (B1) and × campaign clicks/conv (B2)   (rule = 1.50)",
         "dropdown": "0.50,0.75,1.00,1.25,1.50,1.75,2.00,2.50,3.00"},
        {"row": 6, "label": "Concentration share min", "key": "concentration_share_min", "fmt": "0.00",
         "note": "tier signal fires when a unit's share of 30d spend exceeds this   (rule = 0.30)",
         "dropdown": "0.10,0.15,0.20,0.25,0.30,0.35,0.40,0.50"},
        {"row": 7, "label": "Weak ROAS max", "key": "weak_roas_max", "fmt": "0.00",
         "note": "tier signal fires when conv. value / cost is below this   (rule = 1.00)",
         "dropdown": "0.50,0.75,1.00,1.25,1.50,2.00"},
    ],

    "logic": {
        "title_row": 9,
        "title": "2 · FILTER & BLOCK LOGIC   (rewrites itself as you change the factor above)",
        "blocks": [
            {"head_row": 10, "head": "BLOCK 1 — expensive converters   →   review / segment / exclude",
             "rows": [
                 (11, '="Flag a listing group / product as BLOCK 1 when BOTH are true:"'),
                 (12, '="    1.  Conversions (30 days)  >  0"'),
                 (13, '="    2.  Cost / conversion  >  "&TEXT(C5,"0.00")&"  ×  its own campaign cost / conversion"'),
             ]},
            {"head_row": 15, "head": "BLOCK 2 — zero-conversion waste   →   exclude / down-prioritize",
             "rows": [
                 (16, '="Flag a listing group / product as BLOCK 2 when ALL are true:"'),
                 (17, '="    1.  Conversions (30 days)  =  0"'),
                 (18, '="    2.  Clicks  >  "&TEXT(C5,"0.00")&"  ×  its own campaign clicks / conversion"'),
                 (19, '="    3.  The campaign itself had conversions (30 days)  >  0"'),
             ]},
        ],
    },

    "results": {
        "title_row": 21,
        "title": "3 · RESULTS (live — listing-group partitions)",
        "items": [
            {"row": 22, "label": "Block 1 — expensive converters", "cell": "C22",
             "formula": '=COUNTIF({QR},"Block 1")', "fmt": "0"},
            {"row": 23, "label": "Block 2 — zero-conversion waste", "cell": "C23",
             "formula": '=COUNTIF({QR},"Block 2")', "fmt": "0"},
            {"row": 24, "label": "Total flagged partitions", "cell": "C24",
             "formula": '=COUNTIF({QR},"Block 1")+COUNTIF({QR},"Block 2")', "fmt": "0"},
            {"row": 25, "label": "Flagged spend of qualifying", "cell": "C25",
             "formula": '=SUMIF({QR},"Block 1",{COSTR})+SUMIF({QR},"Block 2",{COSTR})', "fmt": "MONEY"},
            {"row": 26, "label": "Candidate universe (partitions)", "cell": "C26",
             "value_key": "universe", "fmt": "0", "muted": True},
            {"row": 27, "label": "Partitions with no benchmark (see Sensitivity tab)", "cell": "C27",
             "value_key": "no_benchmark", "fmt": "0", "muted": True},
            {"row": 28, "label": "Tier signals (concentrated + weak ROAS)", "cell": "C28",
             "formula": '=COUNTIF({R:Tier signal?},TRUE)', "fmt": "0"},
            {"row": 29, "label": "Tier signal spend", "cell": "C29",
             "formula": '=SUMIF({R:Tier signal?},TRUE,{R:Cost})', "fmt": "MONEY"},
        ],
    },

    "aux": [
        {"title_row": 31,
         "title": "4 · CAMPAIGN BENCHMARKS (30 days) — what the × multiplier measures against",
         "header_row": 32, "start_row": 33, "source": "benchmarks", "sort_key": "cost",
         "columns": [("Campaign", "name", None), ("Clicks", "clicks", "NUM"),
                     ("Cost", "cost", "MONEY"), ("Conversions", "conv", "NUM"),
                     ("Cost/conv", "cpa", "MONEY"), ("Clicks/conv", "clicks_per_conv", "NUM")]},
    ],

    "controls_widths": {"A": 40, "B": 13, "C": 14, "D": 14, "E": 14, "F": 14, "G": 14},

    "rows_columns": [
        {"header": "Campaign", "kind": "data", "key": "campaign", "width": 30},
        {"header": "Asset group", "kind": "data", "key": "group", "width": 20},
        {"header": "Listing group", "kind": "data", "key": "label", "width": 28},
        {"header": "Dimension", "kind": "data", "key": "dimension", "width": 16},
        {"header": "Status", "kind": "data", "key": "__status__", "width": 13},
        {"header": "Impr", "kind": "data", "key": "impressions", "width": 8},
        {"header": "Clicks", "kind": "data", "key": "clicks", "width": 8},
        {"header": "Cost", "kind": "data", "key": "cost", "fmt": "MONEY", "width": 11},
        {"header": "Conv", "kind": "data", "key": "conv", "fmt": "NUM", "width": 8},
        {"header": "Conv value", "kind": "data", "key": "value", "fmt": "MONEY", "width": 12},
        {"header": "Campaign cost/conv", "kind": "data", "key": "camp_cpa", "fmt": "MONEY", "width": 16},
        {"header": "Campaign clicks/conv", "kind": "data", "key": "camp_clicks_per_conv", "fmt": "NUM", "width": 17},
        {"header": "Cost/conv", "kind": "formula", "scored": True, "fmt": "MONEY", "width": 11,
         "formula": '=IF({C:Conv}{row}>0,{C:Cost}{row}/{C:Conv}{row},"")'},
        {"header": "CPA threshold", "kind": "formula", "scored": True, "fmt": "MONEY", "width": 12,
         "formula": '={C:Campaign cost/conv}{row}*{ctrl:expensiveness_factor}'},
        {"header": "Clicks threshold", "kind": "formula", "scored": True, "fmt": "NUM", "width": 13,
         "formula": '={C:Campaign clicks/conv}{row}*{ctrl:expensiveness_factor}'},
        {"header": "Block1?", "kind": "formula", "scored": True, "width": 8,
         "formula": '=AND({C:Conv}{row}>0,{C:Cost/conv}{row}>{C:CPA threshold}{row})'},
        {"header": "Block2?", "kind": "formula", "scored": True, "width": 8,
         "formula": '=AND({C:Conv}{row}=0,{C:Clicks}{row}>{C:Clicks threshold}{row})'},
        # Tier concentration + signal (HM-539) — live for EVERY row (scored or
        # no_benchmark; no-row-loss holds), driven by the two new yellow cells.
        {"header": "Spend share", "kind": "formula", "fmt": "PCT", "width": 11,
         "formula": '=IF(SUM({R:Cost})>0,{C:Cost}{row}/SUM({R:Cost}),0)'},
        {"header": "ROAS", "kind": "formula", "fmt": "NUM", "width": 8,
         "formula": '=IF({C:Cost}{row}>0,{C:Conv value}{row}/{C:Cost}{row},"")'},
        {"header": "Over-conc?", "kind": "formula", "width": 10,
         "formula": '={C:Spend share}{row}>{ctrl:concentration_share_min}'},
        {"header": "Weak ROAS?", "kind": "formula", "width": 10,
         "formula": '=IF(ISNUMBER({C:ROAS}{row}),{C:ROAS}{row}<{ctrl:weak_roas_max},FALSE)'},
        {"header": "Tier signal?", "kind": "formula", "width": 10,
         "formula": '=AND({C:Over-conc?}{row},{C:Weak ROAS?}{row})'},
        {"header": "Qualifies", "kind": "formula", "scored": True, "width": 11,
         "formula": '=IF({C:Block1?}{row},"Block 1",IF({C:Block2?}{row},"Block 2",""))'},
    ],
    "rows_freeze": "D2",

    "snapshot_title": "Recommendations, concentration, sensitivity, near-misses & products",
    "snapshot_intro": ("Static snapshot at the generated factor. Partitions re-tune live on the "
                       "Controls tab; products and these tables re-tune live in the HTML explorer."),
    "snapshot_sections": pspec.md_sections,
    "snapshot_widths": {"A": 40, "B": 28, "C": 14, "D": 18, "E": 20, "F": 10, "G": 10, "H": 10, "I": 8},

    "check": {
        "param_cells": ["C5", "C6", "C7"],
        "cached_cell": "C22",
        "status_header": "Status",
        "qualifies_header": "Qualifies",
    },
}
