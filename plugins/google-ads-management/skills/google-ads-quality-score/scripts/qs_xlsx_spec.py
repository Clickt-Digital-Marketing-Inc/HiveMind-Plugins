#!/usr/bin/env python3
"""xlsx layout for the Quality Score forensics report (pure data — NO openpyxl import).

Consumed by _shared/render/xlsx.py. Controls (QS-low threshold + component target
+ pause thresholds → live bucket counts) · Keywords (every keyword + Status;
scored rows carry the primary-bottleneck Bucket formula and a Pause flag, both
reacting to the Controls cells) · Snapshot (the md sections).

The Bucket formula is composed programmatically below — it encodes each
below-target component as rank*10+order, takes the MIN (lowest rank, then
component order LP<AR<CTR), and maps it back to the component name, mirroring
qs_core.classify_row.
"""
from __future__ import annotations

import qs_spec as qspec
from render import model as M  # noqa: E402  (source_label — HM-572 canonical "Data source" line)

_T = "{ctrl:component_target}"
_LOW = "{ctrl:qs_low_threshold}"


def _below(col):
    return f'AND({{C:{col}}}{{row}}>0,{{C:{col}}}{{row}}<{_T})'


def _enc(col, order):
    return f'IF({_below(col)},{{C:{col}}}{{row}}*10+{order},999)'


def _bucket_formula():
    vlp, var, vctr = _enc("LPr", 0), _enc("ARr", 1), _enc("CTRr", 2)
    mn = f'MIN({vlp},{var},{vctr})'
    nbelow = f'(IF({_below("LPr")},1,0)+IF({_below("ARr")},1,0)+IF({_below("CTRr")},1,0))'
    primary = (f'IF({mn}={vlp},"Landing page",'
               f'IF({mn}={var},"Ad relevance","Expected CTR"))')
    return (f'=IF(OR({{C:Status}}{{row}}<>"scored",{{C:QS}}{{row}}>={_LOW}),"",'
            f'IF({nbelow}=0,"Other",IF({nbelow}=3,"Critical",{primary})))')


_PAUSE_FORMULA = ('=IF(AND({C:Status}{row}="scored",{C:Impr}{row}>={ctrl:pause_min_impr},'
                  '{C:CTR}{row}<{ctrl:pause_max_ctr},{C:Conv}{row}=0),"pause","")')


def _title(pr, brand):
    client = pr.get("client_name") or brand or "Account"
    return ("Quality Score Forensics — " + client
            + (f" ({pr['account_id']})" if pr.get("account_id") else ""))


def _subtitle(pr):
    cur = pr.get("currency") or "—"
    src = M.source_label(pr.get("source"), csv_label="user-supplied CSV export")
    return (f"Currency {cur}  ·  {pr.get('window_90d') or '—'}  ·  {pr.get('window_30d') or ''}"
            f"  ·  generated {pr.get('generated') or '—'}  ·  source {src}")


# Dominant-QS-factor drag cost — live SUMPRODUCT mirroring qs_core.component_drag:
# in-scope (QS < threshold), scored, cost summed where the component's rank is a
# below-target 1..target-1 value. Placed after the Buckets block; C21/C22/C23
# feed the dominant/share cells below (same-sheet refs, no {R:}/{ctrl:} tokens
# needed for those two).
def _drag_formula(rank_col):
    return (f'=SUMPRODUCT(({{R:Status}}="scored")*({{R:QS}}<{_LOW})*'
            f'({{R:{rank_col}}}>0)*({{R:{rank_col}}}<{_T})*{{R:Cost}})')


_DOMINANT_FORMULA = ('=IF(AND(C21=0,C22=0,C23=0),"—",'
                     'IF(AND(C21>=C22,C21>=C23),"Landing page",'
                     'IF(C22>=C23,"Ad relevance","Expected CTR")))')
# ROUND(...,4) matches analytics.py's kernel-mirror contract for top_share
# (top_n=1 of the 3 components == MAX) — same rounding as gxRoundHalfUp/Python.
_DOMINANT_SHARE_FORMULA = '=IFERROR(ROUND(MAX(C21:C23)/SUM(C21:C23),4),0)'


XLSX = {
    "sheets": ["Controls", "Keywords", "Snapshot"],
    "controls_sheet": "Controls",
    "rows_sheet": "Keywords",
    "snapshot_sheet": "Snapshot",
    "scored_status": "scored",
    "title": _title,
    "subtitle": _subtitle,
    "intro": ("Adjust any YELLOW cell. Component target: 1 = Below average, 2 = Average, 3 = Above "
              "average (a component below the target is the bottleneck). Buckets recalculate instantly."),

    "params_title_row": 4,
    "params_title": "1 · PARAMETERS",
    "params": [
        {"row": 5, "label": "QS-low threshold (QS < this in scope)", "key": "qs_low_threshold", "fmt": "0",
         "dropdown": "2,3,4,5,6,7,8"},
        {"row": 6, "label": "Component target (1=below,2=avg,3=above)", "key": "component_target", "fmt": "0",
         "dropdown": "1,2,3"},
        {"row": 7, "label": "Pause · min impressions", "key": "pause_min_impr", "fmt": "0"},
        {"row": 8, "label": "Pause · max CTR", "key": "pause_max_ctr", "fmt": "0.00%"},
    ],

    "results": {
        "title_row": 10,
        "title": "2 · BUCKETS & DOMINANT FACTOR (live)",
        "items": [
            {"row": 11, "label": "Landing page", "cell": "C11", "formula": '=COUNTIF({R:Bucket},"Landing page")', "fmt": "0"},
            {"row": 12, "label": "Ad relevance", "cell": "C12", "formula": '=COUNTIF({R:Bucket},"Ad relevance")', "fmt": "0"},
            {"row": 13, "label": "Expected CTR", "cell": "C13", "formula": '=COUNTIF({R:Bucket},"Expected CTR")', "fmt": "0"},
            {"row": 14, "label": "Critical (all three)", "cell": "C14", "formula": '=COUNTIF({R:Bucket},"Critical")', "fmt": "0"},
            {"row": 15, "label": "Other (low QS, none below)", "cell": "C15", "formula": '=COUNTIF({R:Bucket},"Other")', "fmt": "0"},
            {"row": 16, "label": "In scope (QS < threshold)", "cell": "C16", "formula": "=C11+C12+C13+C14+C15", "fmt": "0"},
            {"row": 17, "label": "Low-CTR pause candidates", "cell": "C17", "formula": '=COUNTIF({R:Pause?},"pause")', "fmt": "0"},
            {"row": 18, "label": "Unscored (kept separate)", "cell": "C18", "value_key": "unscored", "fmt": "0", "muted": True},
            {"row": 19, "label": "Average QS (scored)", "cell": "C19", "value_key": "avg_qs", "fmt": "0.00", "muted": True},
            {"row": 21, "label": "Landing page — below-target cost", "cell": "C21",
             "formula": _drag_formula("LPr"), "fmt": "MONEY"},
            {"row": 22, "label": "Ad relevance — below-target cost", "cell": "C22",
             "formula": _drag_formula("ARr"), "fmt": "MONEY"},
            {"row": 23, "label": "Expected CTR — below-target cost", "cell": "C23",
             "formula": _drag_formula("CTRr"), "fmt": "MONEY"},
            {"row": 24, "label": "Dominant QS factor", "cell": "C24",
             "formula": _DOMINANT_FORMULA, "fmt": None},
            {"row": 25, "label": "Dominant factor's share of below-target cost", "cell": "C25",
             "formula": _DOMINANT_SHARE_FORMULA, "fmt": "PCT"},
        ],
    },

    "controls_widths": {"A": 40, "B": 12, "C": 14, "D": 24},

    "rows_columns": [
        {"header": "Keyword", "kind": "data", "key": "keyword", "width": 30},
        {"header": "Ad group", "kind": "data", "key": "ad_group", "width": 20},
        {"header": "Match", "kind": "data", "key": "match_type", "width": 10},
        {"header": "Status", "kind": "data", "key": "__status__", "width": 10},
        {"header": "QS", "kind": "data", "key": "qs", "fmt": "0", "width": 6},
        {"header": "Landing page", "kind": "data", "key": "lp_label", "width": 14},
        {"header": "Ad relevance", "kind": "data", "key": "ar_label", "width": 14},
        {"header": "Expected CTR", "kind": "data", "key": "ctr_label", "width": 14},
        {"header": "LPr", "kind": "data", "key": "lp", "fmt": "0", "width": 5},
        {"header": "ARr", "kind": "data", "key": "ar", "fmt": "0", "width": 5},
        {"header": "CTRr", "kind": "data", "key": "ctr_q", "fmt": "0", "width": 5},
        {"header": "Impr", "kind": "data", "key": "impressions", "fmt": "NUM", "width": 9},
        {"header": "CTR", "kind": "data", "key": "ctr", "fmt": "PCT", "width": 8},
        {"header": "Cost", "kind": "data", "key": "cost", "fmt": "MONEY", "width": 10},
        {"header": "Conv", "kind": "data", "key": "conversions", "fmt": "NUM", "width": 7},
        {"header": "Pause?", "kind": "formula", "scored": True, "width": 8, "formula": _PAUSE_FORMULA},
        {"header": "Bucket", "kind": "formula", "scored": True, "width": 14, "formula": _bucket_formula()},
    ],
    "rows_freeze": "E2",

    "snapshot_title": "Keywords by failing component & QS-threshold sensitivity",
    "snapshot_intro": "Static snapshot at the generated parameters. Use the Controls tab to re-tune live.",
    "snapshot_sections": qspec.md_sections,
    "snapshot_widths": {"A": 34, "B": 22, "C": 8, "D": 16, "E": 16, "F": 16, "G": 12},

    "check": {
        "param_cells": ["C5", "C6", "C7", "C8"],
        "cached_cell": "C11",
        "status_header": "Status",
        "qualifies_header": "Bucket",
    },
}
