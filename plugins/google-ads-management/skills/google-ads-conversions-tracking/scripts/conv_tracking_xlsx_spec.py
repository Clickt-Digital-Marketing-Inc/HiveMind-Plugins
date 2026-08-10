#!/usr/bin/env python3
"""xlsx layout for the conversions & tracking advisor (pure data — NO openpyxl
import). Consumed by _shared/render/xlsx.py.

Controls (tunable trend params + self-rewriting tier logic + live COUNTIF
results), Campaign trend (every campaign + Status, scored rows carry formulas
referencing the Controls cells), and a Snapshot tab (the config-health
checklist, the manual EC/Consent-Mode checks, and the drop-threshold
sensitivity table — the same sections the markdown report renders, via
conv_tracking_spec.md_sections).
"""
from __future__ import annotations

import conv_tracking_spec as ctspec


def _title(pr, brand):
    client = pr.get("client_name") or brand or "Account"
    return ("Conversions & Tracking Advisor — " + client
            + (f" ({pr['account_id']})" if pr.get("account_id") else ""))


def _subtitle(pr):
    cur = pr.get("currency") or "—"
    return (f"Currency {cur}  ·  current window {pr.get('window_90d') or '—'}  ·  prior window "
            f"{pr.get('window_30d') or '—'}  ·  generated {pr.get('generated') or '—'}")


XLSX = {
    "sheets": ["Controls", "Campaign trend", "Snapshot"],
    "controls_sheet": "Controls",
    "rows_sheet": "Campaign trend",
    "snapshot_sheet": "Snapshot",
    "title": _title,
    "subtitle": _subtitle,
    "intro": ("Adjust any YELLOW cell. The tier logic text, the live counts, and every campaign on "
              "the 'Campaign trend' tab recalculate instantly. The config-health checklist and the "
              "manual EC/Consent-Mode checks (Snapshot tab) are not tunable."),

    "params_title_row": 4,
    "params_title": "1 · CVR/CTR TREND PARAMETERS",
    "params": [
        {"row": 5, "label": "CVR drop threshold", "key": "cvr_drop_pct", "fmt": "0%",
         "note": "relative drop vs. prior window   (rule = 30%)",
         "dropdown": "0.1,0.15,0.2,0.25,0.3,0.4,0.5,0.6,0.75"},
        {"row": 6, "label": "Volume floor (conversions, current window)", "key": "min_conv_30d", "fmt": "0",
         "note": "flag campaigns below this   (rule = 30)", "dropdown": "10,20,30,40,50,75,100"},
        {"row": 7, "label": "CTR held/up factor", "key": "ctr_factor", "fmt": "0.00",
         "note": "× prior-window CTR   (rule = 1.00)", "dropdown": "0.50,0.75,0.90,1.00,1.10,1.25,1.50"},
        {"row": 8, "label": "Below-account-CVR factor", "key": "cvr_factor", "fmt": "0.00",
         "note": "× account avg CVR   (rule = 0.50)", "dropdown": "0.10,0.25,0.40,0.50,0.60,0.75,1.00"},
    ],

    "logic": {
        "title_row": 10,
        "title": "2 · TIER LOGIC   (rewrites itself as you change the values above)",
        "blocks": [
            {"head_row": 11, "head": "CRITICAL — score ≥ 6   →   fix now, then re-check next cycle",
             "rows": [
                 (12, '="A campaign scores 4 points when CVR (current) ≤ CVR (prior) × (1 - "&TEXT(C5,"0%")&")"'),
                 (13, '="   and +6 (instead) when that ALSO holds while CTR (current) ≥ CTR (prior) × "&TEXT(C7,"0.00")&"  — landing-page-suspect"'),
             ]},
            {"head_row": 15, "head": "HIGH — score ≥ 3   →   this week",
             "rows": [
                 (16, '="+2 points when CVR (current) < account avg CVR × "&TEXT(C8,"0.00")'),
             ]},
            {"head_row": 18, "head": "WATCH — score > 0   →   next optimization cycle",
             "rows": [
                 (19, '="+1 point when conversions (current window) < "&C6&"  (too thin for automated bidding)"'),
             ]},
            {"head_row": 21, "head": "Campaigns with 0 clicks in the prior window",
             "rows": [
                 (22, '="cannot be scored (undefined CVR/CTR comparison) — held out as no-benchmark, never dropped."'),
             ]},
        ],
    },

    "results": {
        "title_row": 24,
        "title": "3 · RESULTS (live)",
        "items": [
            {"row": 25, "label": "Critical", "cell": "C25", "formula": '=COUNTIF({QR},"Critical")', "fmt": "0"},
            {"row": 26, "label": "High", "cell": "C26", "formula": '=COUNTIF({QR},"High")', "fmt": "0"},
            {"row": 27, "label": "Watch", "cell": "C27", "formula": '=COUNTIF({QR},"Watch")', "fmt": "0"},
            {"row": 28, "label": "Total flagged", "cell": "C28",
             "formula": '=COUNTIF({QR},"Critical")+COUNTIF({QR},"High")+COUNTIF({QR},"Watch")', "fmt": "0"},
            {"row": 29, "label": "Campaigns (universe)", "cell": "C29",
             "value_key": "campaigns", "fmt": "0", "muted": True},
            {"row": 30, "label": "No-benchmark campaigns (see Snapshot tab)", "cell": "C30",
             "value_key": "no_benchmark", "fmt": "0", "muted": True},
            {"row": 31, "label": "Config actions flagged (see Snapshot tab)", "cell": "C31",
             "value_key": "config_flagged", "fmt": "0", "muted": True},
            {"row": 32, "label": "No ENABLED primary conversion action?", "cell": "C32",
             "value_key": "config_no_primary_action", "fmt": "0", "muted": True},
        ],
    },

    "controls_widths": {"A": 40, "B": 13, "C": 14, "D": 30, "E": 12, "F": 12, "G": 12, "H": 12},

    "rows_columns": [
        {"header": "Campaign", "kind": "data", "key": "campaign", "width": 32},
        {"header": "Status", "kind": "data", "key": "__status__", "width": 13},
        {"header": "Liveness", "kind": "data", "key": "liveness", "width": 15},
        {"header": "CTR (curr)", "kind": "data", "key": "ctr_curr", "fmt": "PCT", "width": 11},
        {"header": "CTR (prior)", "kind": "data", "key": "ctr_prior", "fmt": "PCT", "width": 11},
        {"header": "CVR (curr)", "kind": "data", "key": "cvr_curr", "fmt": "PCT", "width": 11},
        {"header": "CVR (prior)", "kind": "data", "key": "cvr_prior", "fmt": "PCT", "width": 11},
        {"header": "Cost (curr)", "kind": "data", "key": "cost_curr", "fmt": "MONEY", "width": 12},
        {"header": "Conv (curr)", "kind": "data", "key": "conversions_curr", "fmt": "NUM", "width": 11},
        {"header": "Account avg CVR", "kind": "data", "key": "account_avg_cvr", "fmt": "PCT", "width": 14},
        {"header": "CVR drop bar", "kind": "formula", "scored": True, "fmt": "PCT", "width": 11,
         "formula": '={C:CVR (prior)}{row}*(1-{ctrl:cvr_drop_pct})'},
        {"header": "CVR drop?", "kind": "formula", "scored": True, "width": 9,
         "formula": '=IF({C:CVR (curr)}{row}<={C:CVR drop bar}{row},TRUE,FALSE)'},
        {"header": "CTR held bar", "kind": "formula", "scored": True, "fmt": "PCT", "width": 11,
         "formula": '={C:CTR (prior)}{row}*{ctrl:ctr_factor}'},
        {"header": "CTR held/up?", "kind": "formula", "scored": True, "width": 10,
         "formula": '=IF({C:CTR (curr)}{row}>={C:CTR held bar}{row},TRUE,FALSE)'},
        {"header": "Landing page suspect?", "kind": "formula", "scored": True, "width": 12,
         "formula": '=AND({C:CVR drop?}{row},{C:CTR held/up?}{row})'},
        {"header": "Thin volume?", "kind": "formula", "width": 10,
         "formula": '=IF({C:Conv (curr)}{row}<{ctrl:min_conv_30d},TRUE,FALSE)'},
        {"header": "Below account CVR?", "kind": "formula", "width": 11,
         "formula": '=IF({C:CVR (curr)}{row}<{C:Account avg CVR}{row}*{ctrl:cvr_factor},TRUE,FALSE)'},
        # Liveness gate (HM-603): a dormant campaign scores 0 / no tier, mirroring
        # conv_tracking_core (the {C:Liveness} guard wraps the existing formulas).
        {"header": "Score", "kind": "formula", "width": 8,
         "formula": '=IF({C:Liveness}{row}="dormant",0,'
                    '({C:CVR drop?}{row}*4)+({C:Landing page suspect?}{row}*6)'
                    '+({C:Thin volume?}{row}*1)+({C:Below account CVR?}{row}*2))'},
        {"header": "Tier", "kind": "formula", "width": 10,
         "formula": '=IF({C:Liveness}{row}="dormant","",'
                    'IF({C:Status}{row}<>"scored","",'
                    'IF({C:Score}{row}>=6,"Critical",IF({C:Score}{row}>=3,"High",'
                    'IF({C:Score}{row}>0,"Watch","")))))'},
    ],
    "rows_freeze": "B2",

    "snapshot_title": "Config health · manual checks · sensitivity",
    "snapshot_intro": "Static snapshot at the generated parameters. Use the Controls tab to re-tune "
                      "the trend live.",
    "snapshot_sections": ctspec.md_sections,
    "snapshot_widths": {"A": 44, "B": 22, "C": 18, "D": 22, "E": 12, "F": 12, "G": 12, "H": 30},

    "check": {
        "param_cells": ["C5", "C6", "C7", "C8"],
        "cached_cell": "C25",
        "status_header": "Status",
        "qualifies_header": "Tier",
    },
}
