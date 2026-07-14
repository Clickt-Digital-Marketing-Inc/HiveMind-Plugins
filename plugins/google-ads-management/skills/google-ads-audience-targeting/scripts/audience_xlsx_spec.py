#!/usr/bin/env python3
"""xlsx layout for the audience-targeting advisor (pure data — NO openpyxl
import). Consumed by _shared/render/xlsx.py. Three sheets:

  Controls               — tunable scoring params (yellow cells) + live
                            COUNTIF/COUNTIFS/SUMPRODUCT results.
  Audiences               — every applied-audience criterion + a Status column
                            (no row loss); scored rows carry formula columns
                            mirroring audience_core.classify EXACTLY; excluded
                            (negative/exclusion) rows never get the formula
                            columns. Last column ("Priority") is the
                            qualifies column.
  First-Party Readiness   — static snapshot: the priority breakdown + the
                            first-party readiness table (audience_spec.
                            md_sections). Not tunable — the gap/severity read
                            is a fixed text match on the user-supplied
                            Readiness column, not a scored/weighted signal.

The "Cost" rows-sheet header must be exactly "Cost" (the generic renderer
derives the SUMPRODUCT cost range {COSTR} from it). The last rows column must
be "Priority" (the qualifies column). Formula columns are flagged scored=True
so the renderer leaves them blank on excluded (never-scored) rows.
"""
from __future__ import annotations

import audience_spec as aspec
from render import model as M  # noqa: E402  (source_label — HM-572 canonical "Data source" line)


def _title(pr, brand):
    client = pr.get("client_name") or brand or "Account"
    return ("Interactive Audience & Targeting Advisor — " + client
            + (f" ({pr['account_id']})" if pr.get("account_id") else ""))


def _subtitle(pr):
    cur = pr.get("currency") or "—"
    return (f"Currency {cur}  ·  window {pr.get('window_30d') or '—'}  ·  "
            f"generated {pr.get('generated') or '—'}  ·  applied audiences: "
            f"{M.source_label(pr.get('source'))}  ·  first-party readiness: "
            f"{pr.get('first_party_source', 'not_supplied')}")


XLSX = {
    "sheets": ["Controls", "Audiences", "First-Party Readiness"],
    "controls_sheet": "Controls",
    "rows_sheet": "Audiences",
    "snapshot_sheet": "First-Party Readiness",
    "title": _title,
    "subtitle": _subtitle,
    "intro": ("Adjust any YELLOW cell. The flag columns, the Score, the Priority tier, and the "
              "live counts below recalculate instantly. Excluded (negative) audience criteria are "
              "shown but never scored."),

    "params_title_row": 4,
    "params_title": "1 · PRIORITY SCORING PARAMETERS",
    "params": [
        {"row": 5, "label": "Cost bar (× campaign avg cost / avg CPA)", "key": "cost_multiple", "fmt": "0.00",
         "note": "wasted-spend: 0-conv cost > this × campaign avg cost; high-CPA: CPA > this × campaign "
                 "avg CPA (rule = 2.00)", "dropdown": "1.50,2.00,2.50,3.00"},
        {"row": 6, "label": "Low-CTR bar (× campaign avg CTR)", "key": "ctr_factor", "fmt": "0.00",
         "note": "flag when CTR < this × the campaign's own avg CTR among scored audiences (rule = 0.50)",
         "dropdown": "0.25,0.50,0.75,1.00"},
        {"row": 7, "label": "Weight · no bid adjustment", "key": "w_no_bid_adjustment", "fmt": "0.00",
         "note": "bid modifier left at 1.00 (rule = 1.00)", "dropdown": "0,1,2,3,4,5"},
        {"row": 8, "label": "Weight · paused criterion", "key": "w_paused_criterion", "fmt": "0.00",
         "note": "audience attached but PAUSED (rule = 3.00)", "dropdown": "0,1,2,3,4,5"},
        {"row": 9, "label": "Weight · zero conversions", "key": "w_zero_conversions", "fmt": "0.00",
         "note": "0 conversions in the window (rule = 1.00)", "dropdown": "0,1,2,3,4,5"},
        {"row": 10, "label": "Weight · wasted spend", "key": "w_wasted_spend", "fmt": "0.00",
         "note": "0 conversions AND cost over the cost bar (rule = 3.00)", "dropdown": "0,1,2,3,4,5"},
        {"row": 11, "label": "Weight · high CPA", "key": "w_high_cpa", "fmt": "0.00",
         "note": "converting, but CPA over the cost bar (rule = 3.00)", "dropdown": "0,1,2,3,4,5"},
        {"row": 12, "label": "Weight · low CTR", "key": "w_low_ctr", "fmt": "0.00",
         "note": "CTR under the low-CTR bar (rule = 1.00)", "dropdown": "0,1,2,3,4,5"},
        {"row": 13, "label": "Critical threshold (score ≥)", "key": "critical_threshold", "fmt": "0.00",
         "note": "rule = 6.00", "dropdown": "4,5,6,7,8,9,10"},
        {"row": 14, "label": "High threshold (score ≥)", "key": "high_threshold", "fmt": "0.00",
         "note": "rule = 3.00", "dropdown": "1,2,3,4,5,6"},
    ],

    "results": {
        "title_row": 16,
        "title": "2 · RESULTS (live)",
        "items": [
            {"row": 17, "label": "Critical", "cell": "C17", "formula": '=COUNTIF({QR},"Critical")', "fmt": "0"},
            {"row": 18, "label": "High", "cell": "C18", "formula": '=COUNTIF({QR},"High")', "fmt": "0"},
            {"row": 19, "label": "Medium", "cell": "C19", "formula": '=COUNTIF({QR},"Medium")', "fmt": "0"},
            {"row": 20, "label": "Clean (scored, no signal)", "cell": "C20",
             "formula": '=COUNTIFS({R:Status},"scored",{QR},"")', "fmt": "0"},
            {"row": 21, "label": "Excluded (negative — never scored)", "cell": "C21",
             "value_key": "excluded", "fmt": "0", "muted": True},
            {"row": 22, "label": "Flagged spend", "cell": "C22",
             "formula": '=SUMPRODUCT(({QR}<>"")*{COSTR})', "fmt": "MONEY"},
            {"row": 23, "label": "Applied audiences (universe)", "cell": "C23",
             "value_key": "total_audiences", "fmt": "0", "muted": True},
            {"row": 24, "label": "Scored", "cell": "C24", "value_key": "scored", "fmt": "0", "muted": True},
            {"row": 25, "label": "First-party readiness items", "cell": "C25",
             "value_key": "first_party_total", "fmt": "0", "muted": True},
            {"row": 26, "label": "First-party gaps", "cell": "C26",
             "value_key": "first_party_gaps", "fmt": "0", "muted": True},
            {"row": 27, "label": "First-party gaps — Critical", "cell": "C27",
             "value_key": "first_party_critical", "fmt": "0", "muted": True},
            {"row": 28, "label": "First-party gaps — High", "cell": "C28",
             "value_key": "first_party_high", "fmt": "0", "muted": True},
            {"row": 29, "label": "First-party gaps — Medium", "cell": "C29",
             "value_key": "first_party_medium", "fmt": "0", "muted": True},
        ],
    },

    "controls_widths": {"A": 42, "B": 13, "C": 16, "D": 40},

    "rows_columns": [
        {"header": "Campaign", "kind": "data", "key": "campaign", "width": 26},
        {"header": "Ad Group", "kind": "data", "key": "ad_group", "width": 22},
        {"header": "Audience", "kind": "data", "key": "list_name", "width": 26},
        {"header": "List Type", "kind": "data", "key": "list_type", "width": 14},
        {"header": "Status", "kind": "data", "key": "__status__", "width": 11},
        {"header": "Criterion Status", "kind": "data", "key": "criterion_status", "width": 13},
        {"header": "Bid Modifier", "kind": "data", "key": "bid_modifier", "fmt": "0.00", "width": 11},
        {"header": "Cost", "kind": "data", "key": "cost", "fmt": "MONEY", "width": 11},
        {"header": "Conversions", "kind": "data", "key": "conversions", "fmt": "NUM", "width": 11},
        {"header": "Impressions", "kind": "data", "key": "impressions", "fmt": "NUM", "width": 11},
        {"header": "Clicks", "kind": "data", "key": "clicks", "fmt": "NUM", "width": 9},
        {"header": "CTR", "kind": "data", "key": "ctr", "fmt": "PCT", "width": 9},
        {"header": "Campaign Avg Cost", "kind": "formula", "scored": True, "fmt": "MONEY", "width": 15,
         "formula": '=AVERAGEIFS({R:Cost},{R:Campaign},{C:Campaign}{row},{R:Status},"scored")'},
        {"header": "Campaign Avg CTR", "kind": "formula", "scored": True, "fmt": "PCT", "width": 14,
         "formula": ('=IF(SUMIFS({R:Impressions},{R:Campaign},{C:Campaign}{row},{R:Status},"scored")=0,0,'
                      'SUMIFS({R:Clicks},{R:Campaign},{C:Campaign}{row},{R:Status},"scored")/'
                      'SUMIFS({R:Impressions},{R:Campaign},{C:Campaign}{row},{R:Status},"scored"))')},
        {"header": "CPA", "kind": "formula", "scored": True, "fmt": "MONEY", "width": 11,
         "formula": '=IF({C:Conversions}{row}=0,0,{C:Cost}{row}/{C:Conversions}{row})'},
        {"header": "Campaign Avg CPA", "kind": "formula", "scored": True, "fmt": "MONEY", "width": 15,
         "formula": ('=IF(SUMIFS({R:Conversions},{R:Campaign},{C:Campaign}{row},{R:Status},"scored",'
                      '{R:Conversions},">0")=0,0,'
                      'SUMIFS({R:Cost},{R:Campaign},{C:Campaign}{row},{R:Status},"scored",'
                      '{R:Conversions},">0")/'
                      'SUMIFS({R:Conversions},{R:Campaign},{C:Campaign}{row},{R:Status},"scored",'
                      '{R:Conversions},">0"))')},
        {"header": "No Bid Adj?", "kind": "formula", "scored": True, "width": 10,
         "formula": '=({C:Bid Modifier}{row}=1)'},
        {"header": "Paused?", "kind": "formula", "scored": True, "width": 9,
         "formula": '=({C:Criterion Status}{row}="PAUSED")'},
        {"header": "Zero Conv?", "kind": "formula", "scored": True, "width": 10,
         "formula": '=({C:Conversions}{row}=0)'},
        {"header": "Wasted Spend?", "kind": "formula", "scored": True, "width": 11,
         "formula": ('=AND({C:Conversions}{row}=0,'
                      '{C:Cost}{row}>{ctrl:cost_multiple}*{C:Campaign Avg Cost}{row})')},
        {"header": "High CPA?", "kind": "formula", "scored": True, "width": 10,
         "formula": ('=AND({C:Conversions}{row}>0,'
                      '{C:CPA}{row}>{ctrl:cost_multiple}*{C:Campaign Avg CPA}{row})')},
        {"header": "Low CTR?", "kind": "formula", "scored": True, "width": 10,
         "formula": '=({C:CTR}{row}<{ctrl:ctr_factor}*{C:Campaign Avg CTR}{row})'},
        {"header": "Score", "kind": "formula", "scored": True, "fmt": "0.00", "width": 9,
         "formula": ('=({C:No Bid Adj?}{row}*{ctrl:w_no_bid_adjustment})'
                      '+({C:Paused?}{row}*{ctrl:w_paused_criterion})'
                      '+({C:Zero Conv?}{row}*{ctrl:w_zero_conversions})'
                      '+({C:Wasted Spend?}{row}*{ctrl:w_wasted_spend})'
                      '+({C:High CPA?}{row}*{ctrl:w_high_cpa})'
                      '+({C:Low CTR?}{row}*{ctrl:w_low_ctr})')},
        {"header": "Priority", "kind": "formula", "scored": True, "width": 11,
         "formula": ('=IF({C:Score}{row}<=0,"",IF({C:Score}{row}>={ctrl:critical_threshold},"Critical",'
                      'IF({C:Score}{row}>={ctrl:high_threshold},"High","Medium")))')},
    ],
    "rows_freeze": "F2",

    "snapshot_title": "First-Party Readiness & Priority Breakdown",
    "snapshot_intro": "Static snapshot — the priority-breakdown counts and the first-party readiness "
                      "checklist. First-party readiness has no tunable params: the gap/severity read is "
                      "a fixed text match on the Readiness column you supplied, not a scored signal.",
    "snapshot_sections": aspec.md_sections,
    "snapshot_widths": {"A": 34, "B": 34, "C": 14, "D": 22, "E": 10, "F": 10, "G": 30, "H": 12},

    "check": {
        "param_cells": ["C5", "C6", "C7", "C8", "C9", "C10", "C11", "C12", "C13", "C14"],
        "cached_cell": "C17",
        "status_header": "Status",
        "qualifies_header": "Priority",
    },
}
