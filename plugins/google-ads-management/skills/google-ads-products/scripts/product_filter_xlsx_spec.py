#!/usr/bin/env python3
"""xlsx layout for the product-segments filter (pure data — NO openpyxl import).

Consumed by _shared/render/xlsx.py. Three sheets:
  Controls       — tunable params (yellow cells) + self-rewriting segment logic +
                   live COUNTIF/SUMIF results.
  Live products  — every product + a Status column (no row loss); scored rows
                   carry formula columns referencing the Controls cells; the final
                   Segment column is the qualifies column.
  Sensitivity    — a static snapshot (the same sections as the markdown report).

The cost column header MUST be exactly "Cost": the generic renderer derives the
SUMIF cost range ({COSTR}) by looking up that header. The last rows column MUST
be the qualifies column ("Segment"). Formula columns are flagged scored=True, so
the renderer leaves them blank on non-scored (inactive) rows.
"""
from __future__ import annotations

import product_filter_spec as pspec


def _title(pr, brand):
    client = pr.get("client_name") or brand or "Account"
    return ("Interactive Product Segments — " + client
            + (f" ({pr['account_id']})" if pr.get("account_id") else ""))


def _subtitle(pr):
    cur = pr.get("currency") or "—"
    return (f"Currency {cur}  ·  30-day {pr.get('window_30d') or '—'}  ·  14-day "
            f"{pr.get('window_14d') or '—'}  ·  prev-14-day {pr.get('window_prev14d') or '—'}  ·  "
            f"generated {pr.get('generated') or '—'}  ·  Shopping/PMax products (account-aggregated)")


XLSX = {
    "sheets": ["Controls", "Live products", "Sensitivity"],
    "controls_sheet": "Controls",
    "rows_sheet": "Live products",
    "snapshot_sheet": "Sensitivity",
    "title": _title,
    "subtitle": _subtitle,
    "intro": ("Adjust any YELLOW cell. The logic text, the live counts, and every product on the "
              "'Live products' tab recalculate instantly. Cost = last 30 days."),

    "params_title_row": 4,
    "params_title": "1 · SEGMENT PARAMETERS",
    "params": [
        {"row": 5, "label": "Surge multiple", "key": "surge_multiple", "fmt": "0.00",
         "note": "conv(14d) > this × conv(prev-14d)   (rule = 1.50)",
         "dropdown": "1.25,1.50,1.75,2.00,2.50,3.00"},
        {"row": 6, "label": "Decline multiple", "key": "decline_multiple", "fmt": "0.00",
         "note": "conv(14d) < this × conv(prev-14d)   (rule = 0.50)",
         "dropdown": "0.25,0.33,0.50,0.66,0.75"},
        {"row": 7, "label": "Zombie · min 30d cost floor", "key": "zombie_cost_min", "fmt": "0.00",
         "note": "cost(30d) must be strictly greater   (rule = 0)",
         "dropdown": "0,1,5,10,25,50,100"},
        {"row": 8, "label": "Zombie · max 30d conversions", "key": "zombie_conv_max", "fmt": "0",
         "note": "non-converting if ≤ this   (rule = 0)", "dropdown": "0,1,2"},
    ],

    "logic": {
        "title_row": 10,
        "title": "2 · SEGMENT LOGIC   (rewrites itself as you change the values above)",
        "blocks": [
            {"head_row": 11, "head": "ZOMBIE — wasted spend   →   exclude / pause the product",
             "rows": [
                 (12, '="Flag a product as ZOMBIE when ALL of these are true:"'),
                 (13, '="    1.  Conversions (30 days)  ≤  "&C8'),
                 (14, '="    2.  Cost (30 days)  >  "&TEXT(C7,"0.00")'),
                 (15, '="    3.  Merchant ID is present in the last 14 days"'),
             ]},
            {"head_row": 17, "head": "SURGING — accelerating   →   scale budget / priority",
             "rows": [
                 (18, '="Flag a product as SURGING when:"'),
                 (19, '="    1.  Conversions (14 days)  >  "&TEXT(C5,"0.00")&"  ×  conversions (previous 14 days)"'),
                 (20, '="    2.  Conversions (previous 14 days)  >  0"'),
             ]},
            {"head_row": 22, "head": "DECLINING — collapsing   →   investigate feed / price / stock",
             "rows": [
                 (23, '="Flag a product as DECLINING when:"'),
                 (24, '="    1.  Conversions (14 days)  <  "&TEXT(C6,"0.00")&"  ×  conversions (previous 14 days)"'),
             ]},
        ],
    },

    "results": {
        "title_row": 26,
        "title": "3 · RESULTS (live)",
        "items": [
            {"row": 27, "label": "Zombie products", "cell": "C27",
             "formula": '=COUNTIF({QR},"Zombie")', "fmt": "0"},
            {"row": 28, "label": "Surging products", "cell": "C28",
             "formula": '=COUNTIF({QR},"Surging")', "fmt": "0"},
            {"row": 29, "label": "Declining products", "cell": "C29",
             "formula": '=COUNTIF({QR},"Declining")', "fmt": "0"},
            {"row": 30, "label": "Zombie wasted cost (30d)", "cell": "C30",
             "formula": '=SUMIF({QR},"Zombie",{COSTR})', "fmt": "MONEY"},
            {"row": 31, "label": "Candidate universe (products)", "cell": "C31",
             "value_key": "universe", "fmt": "0", "muted": True},
            {"row": 32, "label": "Inactive (no spend / no impressions)", "cell": "C32",
             "value_key": "inactive", "fmt": "0", "muted": True},
            {"row": 33, "label": "Products with no merchant id", "cell": "C33",
             "value_key": "no_merchant", "fmt": "0", "muted": True},
        ],
    },

    "controls_widths": {"A": 40, "B": 13, "C": 14, "D": 30},

    "rows_columns": [
        {"header": "Product", "kind": "data", "key": "product_title", "width": 34},
        {"header": "Item ID", "kind": "data", "key": "product_item_id", "width": 18},
        {"header": "Status", "kind": "data", "key": "__status__", "width": 11},
        {"header": "Merchant ID", "kind": "data", "key": "merchant_id", "width": 14},
        {"header": "Cost", "kind": "data", "key": "cost_30d", "fmt": "MONEY", "width": 11},
        {"header": "Conv 30d", "kind": "data", "key": "conversions_30d", "fmt": "NUM", "width": 9},
        {"header": "Impr 30d", "kind": "data", "key": "impressions_30d", "fmt": "NUM", "width": 9},
        {"header": "Conv prev-14d", "kind": "data", "key": "conversions_prev14d", "fmt": "NUM", "width": 12},
        {"header": "Conv 14d", "kind": "data", "key": "conversions_14d", "fmt": "NUM", "width": 9},
        {"header": "Impr 14d", "kind": "data", "key": "impressions_14d", "fmt": "NUM", "width": 9},
        {"header": "Impr prev-14d", "kind": "data", "key": "impressions_prev14d", "fmt": "NUM", "width": 12},
        {"header": "Zombie?", "kind": "formula", "scored": True, "width": 9,
         "formula": '=AND({C:Conv 30d}{row}<={ctrl:zombie_conv_max},{C:Cost}{row}>{ctrl:zombie_cost_min},{C:Merchant ID}{row}<>"")'},
        {"header": "Surging?", "kind": "formula", "scored": True, "width": 9,
         "formula": '=AND({C:Conv prev-14d}{row}>0,{C:Conv 14d}{row}>{ctrl:surge_multiple}*{C:Conv prev-14d}{row})'},
        {"header": "Declining?", "kind": "formula", "scored": True, "width": 9,
         "formula": '=IF({C:Conv 14d}{row}<{ctrl:decline_multiple}*{C:Conv prev-14d}{row},TRUE,FALSE)'},
        {"header": "Segment", "kind": "formula", "scored": True, "width": 11,
         "formula": '=IF({C:Zombie?}{row},"Zombie",IF({C:Surging?}{row},"Surging",IF({C:Declining?}{row},"Declining","")))'},
    ],
    "rows_freeze": "D2",

    "snapshot_title": "Sensitivity & excluded",
    "snapshot_intro": "Static snapshot at the generated parameters. Use the Controls tab to re-tune live.",
    "snapshot_sections": pspec.md_sections,
    "snapshot_widths": {"A": 40, "B": 22, "C": 16, "D": 12, "E": 12, "F": 8},

    "check": {
        "param_cells": ["C5", "C6", "C7", "C8"],
        "cached_cell": "C27",
        "status_header": "Status",
        "qualifies_header": "Segment",
    },
}
