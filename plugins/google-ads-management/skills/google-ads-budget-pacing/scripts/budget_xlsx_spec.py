#!/usr/bin/env python3
"""xlsx layout for the budget & pacing report (pure data — NO openpyxl import).

Consumed by _shared/render/xlsx.py. Controls (goal/CPA/days/flags → live pacing
and bucket counts) · Campaigns (every campaign + Status; measured rows carry the
priority-ordered Bucket formula) · Snapshot (the md sections).
"""
from __future__ import annotations

import budget_spec as bspec
from render import model as M  # noqa: E402  (source_label — HM-572 canonical "Data source" line)


def _title(pr, brand):
    client = pr.get("client_name") or brand or "Account"
    return ("Budget & Pacing — " + client
            + (f" ({pr['account_id']})" if pr.get("account_id") else ""))


def _subtitle(pr):
    cur = pr.get("currency") or "—"
    source_label = M.source_label(pr.get("source"), csv_label="user-supplied CSV export")
    return (f"Currency {cur}  ·  window {pr.get('window_90d') or '—'}  ·  {pr.get('window_30d') or ''}"
            f"  ·  generated {pr.get('generated') or '—'}  ·  source: {source_label}")


XLSX = {
    "sheets": ["Controls", "Campaigns", "Snapshot"],
    "controls_sheet": "Controls",
    "rows_sheet": "Campaigns",
    "snapshot_sheet": "Snapshot",
    "scored_status": "measured",
    "title": _title,
    "subtitle": _subtitle,
    "intro": "Adjust any YELLOW cell. Pacing, the bucket counts and every campaign's Bucket recalculate instantly.",

    "params_title_row": 4,
    "params_title": "1 · PARAMETERS",
    "params": [
        {"row": 5, "label": "Monthly spend goal", "key": "monthly_goal", "fmt": "#,##0.00",
         "note": "0 = pacing N/A"},
        {"row": 6, "label": "Target CPA", "key": "target_cpa", "fmt": "#,##0.00",
         "note": "cost / conversion target"},
        {"row": 7, "label": "Days elapsed", "key": "days_elapsed", "fmt": "0"},
        {"row": 8, "label": "Days in month", "key": "days_in_month", "fmt": "0"},
        {"row": 9, "label": "Budget/Rank-lost-IS flag", "key": "budget_lost_is_flag", "fmt": "0.00",
         "dropdown": "0,0.05,0.1,0.15,0.2,0.3,0.5"},
        {"row": 10, "label": "Kill multiple (× target CPA)", "key": "kill_multiple", "fmt": "0",
         "dropdown": "2,3,4,5"},
        {"row": 11, "label": "Min budget multiple (× target CPA)", "key": "min_budget_multiple", "fmt": "0",
         "dropdown": "3,5,8,10"},
        {"row": 12, "label": "Pacing tolerance (± band)", "key": "pacing_tolerance", "fmt": "0.00",
         "note": "account AND per-campaign pace verdict", "dropdown": "0,0.05,0.1,0.15,0.2,0.3,0.5"},
    ],

    "results": {
        "title_row": 14,
        "title": "2 · PACING, BUCKETS & CONCENTRATION (live)",
        "items": [
            {"row": 15, "label": "MTD spend", "cell": "C15", "formula": "=SUM({R:MTD})", "fmt": "MONEY"},
            {"row": 16, "label": "Expected MTD", "cell": "C16",
             "formula": '=IF(OR(C5=0,C8=0),"",C5*(C7/C8))', "fmt": "MONEY"},
            {"row": 17, "label": "Pace (MTD ÷ expected)", "cell": "C17",
             "formula": '=IF(OR(C16="",C16=0),"",C15/C16)', "fmt": "0%"},
            {"row": 18, "label": "Kill (3× rule)", "cell": "C18", "formula": '=COUNTIF({R:Bucket},"Kill")', "fmt": "0"},
            {"row": 19, "label": "Raise (constrained winners)", "cell": "C19", "formula": '=COUNTIF({R:Bucket},"Raise")', "fmt": "0"},
            {"row": 20, "label": "Rank-limited", "cell": "C20", "formula": '=COUNTIF({R:Bucket},"Rank-limited")', "fmt": "0"},
            {"row": 21, "label": "Low budget", "cell": "C21", "formula": '=COUNTIF({R:Bucket},"Low budget")', "fmt": "0"},
            {"row": 22, "label": "OK", "cell": "C22", "formula": '=COUNTIF({R:Bucket},"OK")', "fmt": "0"},
            {"row": 23, "label": "No-budget (not bucketed)", "cell": "C23",
             "value_key": "no_budget", "fmt": "0", "muted": True},
            # Spend concentration (analytics.concentration mirror — see _shared/README.md's
            # xlsx sketch: top_share = ROUND(SUM(LARGE(rng,{1..k}))/SUM(rng),4) etc.). IFERROR
            # guards the LARGE() edge case of fewer than 3 spending campaigns.
            {"row": 24, "label": "Top-3 spend share", "cell": "C24",
             "formula": '=IFERROR(ROUND(SUM(LARGE({R:Spend},{1,2,3}))/SUM({R:Spend}),4),"")',
             "fmt": "PCT"},
            {"row": 25, "label": "HHI (0–10,000)", "cell": "C25",
             "formula": '=ROUND(SUMPRODUCT(({R:Spend}/SUM({R:Spend}))^2)*10000,1)', "fmt": "0.0"},
            {"row": 26, "label": "Effective N", "cell": "C26",
             "formula": '=ROUND(1/SUMPRODUCT(({R:Spend}/SUM({R:Spend}))^2),2)', "fmt": "0.00"},
            # Per-campaign pace pre-score aggregates (analytics.signals mirror).
            {"row": 27, "label": "Over-pacing campaigns", "cell": "C27",
             "formula": '=COUNTIF({R:Pace verdict},"over")', "fmt": "0"},
            {"row": 28, "label": "Under-pacing campaigns", "cell": "C28",
             "formula": '=COUNTIF({R:Pace verdict},"under")', "fmt": "0"},
            {"row": 29, "label": "Off-pace (high confidence)", "cell": "C29",
             "formula": '=SUMPRODUCT((({R:Pace verdict}="over")+({R:Pace verdict}="under"))'
                        '*({R:Confidence}="high"))', "fmt": "0"},
        ],
    },

    "controls_widths": {"A": 36, "B": 12, "C": 14, "D": 26},

    "rows_columns": [
        {"header": "Campaign", "kind": "data", "key": "campaign", "width": 30},
        {"header": "Channel", "kind": "data", "key": "channel", "width": 18},
        {"header": "Status", "kind": "data", "key": "__status__", "width": 12},
        {"header": "Liveness", "kind": "data", "key": "liveness", "width": 15},
        {"header": "Daily budget", "kind": "data", "key": "daily_budget", "fmt": "MONEY", "width": 12},
        {"header": "Spend", "kind": "data", "key": "cost", "fmt": "MONEY", "width": 11},
        {"header": "MTD", "kind": "data", "key": "mtd_spend", "fmt": "MONEY", "width": 11},
        {"header": "Conv", "kind": "data", "key": "conversions", "fmt": "NUM", "width": 8},
        {"header": "CPA", "kind": "data", "key": "cpa", "fmt": "MONEY", "width": 10},
        {"header": "Budget-lost IS", "kind": "data", "key": "budget_lost_is", "fmt": "PCT", "width": 13},
        {"header": "Rank-lost IS", "kind": "data", "key": "rank_lost_is", "fmt": "PCT", "width": 12},
        # Per-campaign pace pre-score (mirrors budget_core.add_pace / PACE_FLAG_WEIGHTS
        # verbatim). Computed for EVERY row, no_budget included — matches add_pace's
        # unconditional pass (never "scored": True, unlike Bucket).
        # Liveness gate (HM-603): a dormant campaign gets no pace ratio/score and
        # no bucket, mirroring budget_core (add_pace / classify_row). The
        # {C:Liveness}="dormant" guard wraps each existing formula; Pace verdict
        # follows the empty Pace ratio to "n/a" without its own guard.
        {"header": "Pace ratio", "kind": "formula", "fmt": "0.00", "width": 10,
         "formula": '=IF({C:Liveness}{row}="dormant","",'
                    'IF(OR({C:Daily budget}{row}="",{C:Daily budget}{row}<=0,{ctrl:days_elapsed}=0),'
                    '"",ROUND({C:MTD}{row}/({C:Daily budget}{row}*{ctrl:days_elapsed}),2)))'},
        {"header": "Pace verdict", "kind": "formula", "width": 12,
         "formula": '=IF({C:Pace ratio}{row}="","n/a",'
                    'IF({C:Pace ratio}{row}>1+{ctrl:pacing_tolerance},"over",'
                    'IF({C:Pace ratio}{row}<1-{ctrl:pacing_tolerance},"under","on track")))'},
        {"header": "Confidence", "kind": "formula", "width": 11,
         "formula": '=IF({C:Liveness}{row}="dormant","low",'
                    'IF(AND({ctrl:days_elapsed}>=7,{C:MTD}{row}>={ctrl:target_cpa}),"high","low"))'},
        {"header": "Pace score", "kind": "formula", "fmt": "0.00", "width": 11,
         "formula": '=IF({C:Liveness}{row}="dormant",0,'
                    'IF(AND({C:Pace ratio}{row}<>"",{C:Pace ratio}{row}>1+{ctrl:pacing_tolerance}),1,0)*1'
                    '+IF(AND({C:Pace ratio}{row}<>"",{C:Pace ratio}{row}<1-{ctrl:pacing_tolerance}),1,0)*1'
                    '+IF(AND({C:Budget-lost IS}{row}<>"",{C:Budget-lost IS}{row}>{ctrl:budget_lost_is_flag}),1,0)*1.5'
                    '+IF({C:Conv}{row}=0,1,0)*2)'},
        {"header": "Bucket", "kind": "formula", "scored": True, "width": 12,
         "formula": '=IF({C:Liveness}{row}="dormant","",'
                    'IF(AND({C:Conv}{row}=0,{C:Spend}{row}>={ctrl:kill_multiple}*{ctrl:target_cpa}),"Kill",'
                    'IF(AND({C:Budget-lost IS}{row}<>"",{C:Budget-lost IS}{row}>{ctrl:budget_lost_is_flag},{C:Conv}{row}>0,{C:CPA}{row}<>"",{C:CPA}{row}<={ctrl:target_cpa}),"Raise",'
                    'IF(AND({C:Rank-lost IS}{row}<>"",{C:Rank-lost IS}{row}>{ctrl:budget_lost_is_flag}),"Rank-limited",'
                    'IF(AND({C:Daily budget}{row}<>"",{C:Daily budget}{row}<{ctrl:min_budget_multiple}*{ctrl:target_cpa}),"Low budget","OK")))))'},
    ],
    "rows_freeze": "C2",

    "snapshot_title": "Raise / Kill / Rank-limited / Low-budget & pacing sensitivity",
    "snapshot_intro": "Static snapshot at the generated parameters. Use the Controls tab to re-tune live.",
    "snapshot_sections": bspec.md_sections,
    "snapshot_widths": {"A": 40, "B": 16, "C": 16, "D": 14, "E": 14, "F": 12},

    "check": {
        "param_cells": ["C5", "C6", "C7", "C8", "C9", "C10", "C11", "C12"],
        "cached_cell": "C18",
        "status_header": "Status",
        "qualifies_header": "Bucket",
    },
}
