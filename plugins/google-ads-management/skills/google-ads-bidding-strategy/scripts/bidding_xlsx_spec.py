#!/usr/bin/env python3
"""xlsx layout for the bidding-strategy Data Maturity Score (pure data — NO
openpyxl import). Consumed by _shared/render/xlsx.py. Reproduces the workbook:
Controls (tunable params + self-rewriting logic + live COUNTIF/AVERAGEIF
results), Live filter (every campaign + Status, scored rows carry formulas
referencing the Controls cells), and a Snapshot (the same sections as the
markdown report).

Caveat (documented, not enforced by the sheet): the Recommended-tier formula
is a fixed nested IF over band_edge_1..4 in ascending order. The Python/JS
kernels sort the edges defensively before banding; the xlsx formula does not —
keep the four edges in ascending order when tuning this workbook.
"""
from __future__ import annotations

import bidding_core as core
import bidding_spec as bspec
from render import model as M  # noqa: E402  (source_label — HM-572 canonical "Data source" line)


def _title(pr, brand):
    client = pr.get("client_name") or brand or "Account"
    return ("Bidding Strategy — Data Maturity Score — " + client
            + (f" ({pr['account_id']})" if pr.get("account_id") else ""))


def _subtitle(pr):
    cur = pr.get("currency") or "—"
    src = M.source_label(pr.get("source"))
    return (f"Currency {cur}  ·  30-day {pr.get('window_30d') or '—'}  ·  generated "
            f"{pr.get('generated') or '—'}  ·  source {src}")


XLSX = {
    "sheets": ["Controls", "Live filter", "Snapshot"],
    "controls_sheet": "Controls",
    "rows_sheet": "Live filter",
    "snapshot_sheet": "Snapshot",
    "title": _title,
    "subtitle": _subtitle,
    "intro": ("Adjust any YELLOW cell. The logic text, the live counts, and every campaign on the "
              "'Live filter' tab recalculate instantly. Keep the four band edges in ascending order."),

    "params_title_row": 4,
    "params_title": "1 · MATURITY PARAMETERS",
    "params": [
        {"row": 5, "label": "Volume saturation (conv/30d)", "key": "conv_target", "fmt": "0",
         "note": "conv30 at which the volume component reaches 100   (rule = 30)"},
        {"row": 6, "label": "Automation data gate (conv/30d)", "key": "conv_gate", "fmt": "0",
         "note": "below this + automated bidding = Over-automated (under-data)   (rule = 30)"},
        {"row": 7, "label": "Tier-gap flag threshold", "key": "tier_gap_threshold", "fmt": "0",
         "note": "tiers of difference before a plain mismatch fires   (rule = 1)"},
        {"row": 8, "label": "Band edge 1 — Manual → Enhanced CPC", "key": "band_edge_1", "fmt": "0",
         "note": "rule = 30"},
        {"row": 9, "label": "Band edge 2 — Enhanced CPC → Target CPA", "key": "band_edge_2", "fmt": "0",
         "note": "rule = 50"},
        {"row": 10, "label": "Band edge 3 — Target CPA → Target ROAS", "key": "band_edge_3", "fmt": "0",
         "note": "rule = 70"},
        {"row": 11, "label": "Band edge 4 — Target ROAS → + Exploration", "key": "band_edge_4", "fmt": "0",
         "note": "rule = 85"},
        {"row": 12, "label": "Volume weight", "key": "volume_weight", "fmt": "0.00", "note": "rule = 0.40"},
        {"row": 13, "label": "Value-variance weight", "key": "value_weight", "fmt": "0.00", "note": "rule = 0.30"},
        {"row": 14, "label": "Tracking-confidence weight", "key": "tracking_weight", "fmt": "0.00",
         "note": "rule = 0.30"},
        {"row": 15, "label": "Assumed value-variance score (no data)", "key": "assumed_value_score",
         "fmt": "0", "note": "neutral default = 50"},
        {"row": 16, "label": "Assumed tracking-confidence score (no data)", "key": "assumed_tracking_score",
         "fmt": "0", "note": "neutral default = 50"},
    ],

    "logic": {
        "title_row": 18,
        "title": "2 · MATURITY BANDS & MISMATCH LOGIC   (rewrites itself as you change the values above)",
        "blocks": [
            {"head_row": 19, "head": "Maturity score  →  recommended tier",
             "rows": [
                 (20, '="0 = Manual CPC / Maximize Clicks        (score < "&TEXT(C8,"0")&")"'),
                 (21, '="1 = Enhanced CPC                        ("&TEXT(C8,"0")&" ≤ score < "&TEXT(C9,"0")&")"'),
                 (22, '="2 = Target CPA / Maximize Conversions   ("&TEXT(C9,"0")&" ≤ score < "&TEXT(C10,"0")&")"'),
                 (23, '="3 = Target ROAS / Max Conversion Value  ("&TEXT(C10,"0")&" ≤ score < "&TEXT(C11,"0")&")"'),
                 (24, '="4 = Target ROAS + Smart Bidding Exploration   (score ≥ "&TEXT(C11,"0")&")"'),
             ]},
            {"head_row": 26, "head": "Mismatch rule",
             "rows": [
                 (27, '="Over-automated (under-data):  conv30 < "&TEXT(C6,"0")&" AND current tier is automated (≥ 1)"'),
                 (28, '="Over-automated:  current tier − recommended tier  >  "&TEXT(C7,"0")'),
                 (29, '="Under-automated:  current tier − recommended tier  <  -"&TEXT(C7,"0")'),
             ]},
        ],
    },

    "results": {
        "title_row": 31,
        "title": "3 · RESULTS (live)",
        "items": [
            {"row": 32, "label": "Over-automated (under-data) campaigns", "cell": "C32",
             "formula": '=COUNTIF({QR},"Over-automated (under-data)")', "fmt": "0"},
            {"row": 33, "label": "Over-automated campaigns", "cell": "C33",
             "formula": '=COUNTIF({QR},"Over-automated")', "fmt": "0"},
            {"row": 34, "label": "Under-automated campaigns", "cell": "C34",
             "formula": '=COUNTIF({QR},"Under-automated")', "fmt": "0"},
            {"row": 35, "label": "Total mismatched", "cell": "C35",
             "formula": ('=COUNTIF({QR},"Over-automated (under-data)")+COUNTIF({QR},"Over-automated")'
                        '+COUNTIF({QR},"Under-automated")'), "fmt": "0"},
            {"row": 36, "label": "Avg maturity score (scored)", "cell": "C36",
             "formula": '=IFERROR(AVERAGEIF({R:Status},"scored",{R:Maturity score}),0)', "fmt": "0.00"},
            {"row": 37, "label": "Universe (all campaigns)", "cell": "C37",
             "value_key": "universe", "fmt": "0", "muted": True},
            {"row": 38, "label": "No spend in window", "cell": "C38",
             "value_key": "no_spend", "fmt": "0", "muted": True},
            {"row": 39, "label": "Unsupported bidding strategy", "cell": "C39",
             "value_key": "unsupported_strategy", "fmt": "0", "muted": True},
            {"row": 40, "label": "Spend on under-data automation", "cell": "C40",
             "value_key": "critical_spend", "fmt": "MONEY", "muted": True},
            {"row": 41, "label": "Top-3 spend share", "cell": "C41",
             "value_key": "spend_top3_share", "fmt": "PCT", "muted": True},
        ],
    },

    "controls_widths": {"A": 40, "B": 13, "C": 14, "D": 55},

    "rows_columns": [
        {"header": "Campaign", "kind": "data", "key": "campaign", "width": 32},
        {"header": "Status", "kind": "data", "key": "__status__", "width": 13},
        {"header": "Bidding strategy", "kind": "data", "key": "bidding_strategy", "width": 22},
        {"header": "Current tier", "kind": "data", "key": "current_tier", "fmt": "0", "width": 8},
        {"header": "Current tier label", "kind": "data", "key": "current_label", "width": 30},
        {"header": "Conv 30d", "kind": "data", "key": "conv30", "fmt": "NUM", "width": 9},
        {"header": "Cost", "kind": "data", "key": "cost", "fmt": "MONEY", "width": 10},
        {"header": "Value score", "kind": "data", "key": "value_score", "fmt": "NUM", "width": 9},
        {"header": "Tracking score", "kind": "data", "key": "tracking_score", "fmt": "NUM", "width": 9},
        {"header": "Confidence", "kind": "data", "key": "confidence", "width": 11},
        {"header": "Volume score", "kind": "formula", "scored": True, "fmt": "NUM", "width": 11,
         "formula": '=MIN(100,MAX(0,({C:Conv 30d}{row}/{ctrl:conv_target})*100))'},
        {"header": "Value score used", "kind": "formula", "scored": True, "fmt": "NUM", "width": 13,
         "formula": '=IF(ISBLANK({C:Value score}{row}),{ctrl:assumed_value_score},{C:Value score}{row})'},
        {"header": "Tracking score used", "kind": "formula", "scored": True, "fmt": "NUM", "width": 14,
         "formula": '=IF(ISBLANK({C:Tracking score}{row}),{ctrl:assumed_tracking_score},{C:Tracking score}{row})'},
        {"header": "Maturity score", "kind": "formula", "scored": True, "fmt": "NUM", "width": 12,
         "formula": ('=ROUND({C:Volume score}{row}*{ctrl:volume_weight}'
                    '+{C:Value score used}{row}*{ctrl:value_weight}'
                    '+{C:Tracking score used}{row}*{ctrl:tracking_weight},2)')},
        {"header": "Recommended tier", "kind": "formula", "scored": True, "fmt": "0", "width": 14,
         "formula": ('=IF({C:Maturity score}{row}>={ctrl:band_edge_4},4,'
                    'IF({C:Maturity score}{row}>={ctrl:band_edge_3},3,'
                    'IF({C:Maturity score}{row}>={ctrl:band_edge_2},2,'
                    'IF({C:Maturity score}{row}>={ctrl:band_edge_1},1,0))))')},
        {"header": "Tier gap", "kind": "formula", "scored": True, "fmt": "0", "width": 8,
         "formula": '={C:Current tier}{row}-{C:Recommended tier}{row}'},
        {"header": "Under data?", "kind": "formula", "scored": True, "width": 10,
         "formula": '=IF({C:Conv 30d}{row}<{ctrl:conv_gate},TRUE,FALSE)'},
        {"header": "Mismatch", "kind": "formula", "scored": True, "width": 28,
         "formula": ('=IF(AND({C:Under data?}{row},{C:Current tier}{row}>=1),"Over-automated (under-data)",'
                    'IF({C:Tier gap}{row}>{ctrl:tier_gap_threshold},"Over-automated",'
                    'IF({C:Tier gap}{row}<-{ctrl:tier_gap_threshold},"Under-automated","")))')},
    ],
    "rows_freeze": "D2",

    "snapshot_title": "Gate sensitivity, borderline campaigns & exclusions",
    "snapshot_intro": "Static snapshot at the generated parameters. Use the Controls tab to re-tune live.",
    "snapshot_sections": bspec.md_sections,
    "snapshot_widths": {"A": 40, "B": 22, "C": 16, "D": 22, "E": 26, "F": 20},

    "check": {
        "param_cells": ["C5", "C6", "C7", "C8", "C9", "C10", "C11", "C12", "C13", "C14", "C15", "C16"],
        "cached_cell": "C32",
        "status_header": "Status",
        "qualifies_header": "Mismatch",
    },
}
