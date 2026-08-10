#!/usr/bin/env python3
"""xlsx layout for the performance report (pure data — NO openpyxl import).

Consumed by _shared/render/xlsx.py. Controls (ROAS goal + flags + the anomaly
delta flag, live bucket/anomaly counts and spend/conversion concentration) ·
Campaigns (every campaign + Status; every row carries an Anomaly-score formula,
measured rows also carry a Bucket formula, both referencing the Controls
cells) · Snapshot (the md sections, incl. Anomalies + Concentration tables).
"""
from __future__ import annotations

import perf_spec as pspec


def _title(pr, brand):
    client = pr.get("client_name") or brand or "Account"
    return ("Performance Report — " + client
            + (f" ({pr['account_id']})" if pr.get("account_id") else ""))


def _subtitle(pr):
    cur = pr.get("currency") or "—"
    return (f"Currency {cur}  ·  period {pr.get('window_90d') or '—'}  ·  prior "
            f"{pr.get('window_30d') or '—'}  ·  generated {pr.get('generated') or '—'}")


XLSX = {
    "sheets": ["Controls", "Campaigns", "Snapshot"],
    "controls_sheet": "Controls",
    "rows_sheet": "Campaigns",
    "snapshot_sheet": "Snapshot",
    "scored_status": "measured",
    "title": _title,
    "subtitle": _subtitle,
    "intro": "Adjust any YELLOW cell. Bucket/anomaly counts, every campaign's Bucket + Anomaly "
             "score, and the concentration stats recalculate instantly.",

    "params_title_row": 4,
    "params_title": "1 · PARAMETERS",
    "params": [
        {"row": 5, "label": "ROAS goal (value ÷ spend)", "key": "roas_goal", "fmt": "0.00",
         "note": "at/above goal = Winner/Scale", "dropdown": "1,2,3,4,5,6,8,10"},
        {"row": 6, "label": "Budget-lost-IS flag", "key": "budget_lost_is_flag", "fmt": "0.00",
         "note": "a goal-clearer above this = Scale", "dropdown": "0,0.05,0.1,0.15,0.2,0.3,0.5"},
        {"row": 7, "label": "Anomaly delta flag", "key": "delta_flag", "fmt": "0.00",
         "note": "period-over-period swing beyond this = anomaly",
         "dropdown": "0.1,0.15,0.2,0.25,0.3,0.4,0.5"},
        {"row": 8, "label": "Fix spend floor", "key": "min_spend", "fmt": "#,##0.00",
         "note": "sub-goal at/above this spend = Fix"},
    ],

    "results": {
        "title_row": 10,
        "title": "2 · RESULTS (live)",
        "items": [
            {"row": 11, "label": "Scale (budget-constrained winners)", "cell": "C11",
             "formula": '=COUNTIF({R:Bucket},"Scale")', "fmt": "0"},
            {"row": 12, "label": "Winner", "cell": "C12", "formula": '=COUNTIF({R:Bucket},"Winner")', "fmt": "0"},
            {"row": 13, "label": "Fix (laggards)", "cell": "C13", "formula": '=COUNTIF({R:Bucket},"Fix")', "fmt": "0"},
            {"row": 14, "label": "Hold", "cell": "C14", "formula": '=COUNTIF({R:Bucket},"Hold")', "fmt": "0"},
            {"row": 15, "label": "Total spend", "cell": "C15", "formula": "=SUM({R:Spend})", "fmt": "MONEY"},
            {"row": 16, "label": "Total revenue", "cell": "C16", "formula": "=SUM({R:Revenue})", "fmt": "MONEY"},
            {"row": 17, "label": "Account ROAS", "cell": "C17", "formula": '=IF(C15=0,"",C16/C15)', "fmt": "0.00"},
            {"row": 18, "label": "No-value campaigns (not ROAS-bucketed)", "cell": "C18",
             "value_key": "no_value", "fmt": "0", "muted": True},
            {"row": 19, "label": "Anomalies (score > 0)", "cell": "C19",
             "formula": '=COUNTIF({R:Anomaly score},">0")', "fmt": "0"},
            {"row": 20, "label": "Spend concentration — top-3 share", "cell": "C20",
             "formula": '=IF(SUM({R:Spend})=0,0,ROUND((IFERROR(LARGE({R:Spend},1),0)+'
                        'IFERROR(LARGE({R:Spend},2),0)+IFERROR(LARGE({R:Spend},3),0))/'
                        'SUM({R:Spend}),4))', "fmt": "0.00%"},
            {"row": 21, "label": "Spend concentration — HHI (0–10,000)", "cell": "C21",
             "formula": '=IF(SUM({R:Spend})=0,0,ROUND(SUMPRODUCT(({R:Spend}/SUM({R:Spend}))^2)*10000,1))',
             "fmt": "#,##0.0"},
            {"row": 22, "label": "Spend concentration — Effective-N", "cell": "C22",
             "formula": '=IF(SUM({R:Spend})=0,0,IF(SUMPRODUCT(({R:Spend}/SUM({R:Spend}))^2)=0,0,'
                        'ROUND(1/SUMPRODUCT(({R:Spend}/SUM({R:Spend}))^2),2)))', "fmt": "0.00"},
            {"row": 23, "label": "Conversion concentration — top-3 share", "cell": "C23",
             "formula": '=IF(SUM({R:Conv})=0,0,ROUND((IFERROR(LARGE({R:Conv},1),0)+'
                        'IFERROR(LARGE({R:Conv},2),0)+IFERROR(LARGE({R:Conv},3),0))/'
                        'SUM({R:Conv}),4))', "fmt": "0.00%"},
            {"row": 24, "label": "Conversion concentration — HHI (0–10,000)", "cell": "C24",
             "formula": '=IF(SUM({R:Conv})=0,0,ROUND(SUMPRODUCT(({R:Conv}/SUM({R:Conv}))^2)*10000,1))',
             "fmt": "#,##0.0"},
            {"row": 25, "label": "Conversion concentration — Effective-N", "cell": "C25",
             "formula": '=IF(SUM({R:Conv})=0,0,IF(SUMPRODUCT(({R:Conv}/SUM({R:Conv}))^2)=0,0,'
                        'ROUND(1/SUMPRODUCT(({R:Conv}/SUM({R:Conv}))^2),2)))', "fmt": "0.00"},
        ],
    },

    "controls_widths": {"A": 34, "B": 12, "C": 14, "D": 30},

    "rows_columns": [
        {"header": "Campaign", "kind": "data", "key": "campaign", "width": 32},
        {"header": "Channel", "kind": "data", "key": "channel", "width": 18},
        {"header": "Status", "kind": "data", "key": "__status__", "width": 12},
        {"header": "Liveness", "kind": "data", "key": "liveness", "width": 15},
        {"header": "Impr", "kind": "data", "key": "impressions", "width": 9},
        {"header": "Clicks", "kind": "data", "key": "clicks", "width": 8},
        {"header": "CTR", "kind": "data", "key": "ctr", "fmt": "PCT", "width": 8},
        {"header": "Spend", "kind": "data", "key": "cost", "fmt": "MONEY", "width": 11},
        {"header": "Conv", "kind": "data", "key": "conversions", "fmt": "NUM", "width": 8},
        {"header": "Revenue", "kind": "data", "key": "value", "fmt": "MONEY", "width": 12},
        {"header": "ROAS", "kind": "data", "key": "roas", "fmt": "NUM", "width": 8},
        {"header": "Budget-lost IS", "kind": "data", "key": "budget_lost_is", "fmt": "PCT", "width": 13},
        {"header": "Spend Δ", "kind": "data", "key": "spend_delta", "fmt": "PCT", "width": 10},
        {"header": "Conv Δ", "kind": "data", "key": "conv_delta", "fmt": "PCT", "width": 10},
        {"header": "Value Δ", "kind": "data", "key": "value_delta", "fmt": "PCT", "width": 10},
        # Anomaly score: mirrors perf_core.ANOMALY_WEIGHTS verbatim (kernel-mirror
        # contract). ISNUMBER-guarded per delta — a blank cell (no prior period)
        # never fires, matching the analytics.signals() "missing = no signal" rule.
        # Applies to EVERY row (no `scored` gate): anomalies aren't ROAS-gated.
        # Liveness gate (HM-603): a dormant campaign scores 0 anomaly / no bucket,
        # mirroring perf_core (the {C:Liveness} guard wraps the existing formulas).
        {"header": "Anomaly score", "kind": "formula", "width": 12,
         "formula": '=IF({C:Liveness}{row}="dormant",0,'
                    'IF(ISNUMBER({C:Spend Δ}{row}),IF({C:Spend Δ}{row}>{ctrl:delta_flag},2,0)+'
                    'IF({C:Spend Δ}{row}<-{ctrl:delta_flag},1.5,0),0)'
                    '+IF(ISNUMBER({C:Conv Δ}{row}),IF({C:Conv Δ}{row}<-{ctrl:delta_flag},2.5,0),0)'
                    '+IF(ISNUMBER({C:Value Δ}{row}),IF({C:Value Δ}{row}<-{ctrl:delta_flag},2,0),0))',
         "fmt": "0.00"},
        {"header": "Bucket", "kind": "formula", "scored": True, "width": 10,
         "formula": '=IF({C:Liveness}{row}="dormant","",'
                    'IF({C:ROAS}{row}="","",IF({C:ROAS}{row}>={ctrl:roas_goal},'
                    'IF(AND({C:Budget-lost IS}{row}<>"",{C:Budget-lost IS}{row}>{ctrl:budget_lost_is_flag}),"Scale","Winner"),'
                    'IF({C:Spend}{row}>={ctrl:min_spend},"Fix","Hold"))))'},
    ],
    "rows_freeze": "C2",

    "snapshot_title": "Top campaigns, budget candidates & ROAS-goal sensitivity",
    "snapshot_intro": "Static snapshot at the generated parameters. Use the Controls tab to re-tune live.",
    "snapshot_sections": pspec.md_sections,
    "snapshot_widths": {"A": 40, "B": 16, "C": 14, "D": 16, "E": 14, "F": 12},

    "check": {
        "param_cells": ["C5", "C6", "C7", "C8"],
        "cached_cell": "C11",
        "status_header": "Status",
        "qualifies_header": "Bucket",
    },
}
