#!/usr/bin/env python3
"""Render spec for the competitive-pressure filter — adapts competitive_core's
model to the shared render toolkit (_shared/render). Stdlib only.

The classification math lives once in competitive_core (Python) and is
mirrored in `JS_KERNEL` (browser, built on `_shared/analytics.JS_MIRROR`) —
the Node-vs-Python equality gate keeps them in sync.
"""
from __future__ import annotations

import sys
from pathlib import Path

import competitive_core as core

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))
import analytics  # noqa: E402
from render import model as M  # noqa: E402  (source_label — HM-572 canonical "Data source" line)


def _money(v, cur):
    return f"{float(v):,.2f}" + (f" {cur}" if cur else "")


def _pct(v, nd=1):
    return "—" if v is None else f"{float(v) * 100:.{nd}f}%"


# --------------------------------------------------------------------------
# Markdown adapters
# --------------------------------------------------------------------------
def md_params(model):
    p = model["params"]
    return [
        ("Data source", M.source_label(model["provenance"].get("source"))),
        ("Flag thresholds", f"IS drop ≥ {p['is_drop_flag'] * 100:.1f}pp WoW  OR  "
            f"CPC jump ≥ {p['cpc_jump_flag'] * 100:.1f}% WoW  (min spend "
            f"{_money(p['min_cost'], model['provenance']['currency'])} this week)"),
        ("Competitor data", model["provenance"]["auction_insights_source"] == "user_csv"
            and "Auction Insights export supplied — competitor rows below are USER-SUPPLIED, "
                "not from the Google Ads API"
            or "No Auction Insights export supplied — own-side pressure only; the API cannot "
               "return competitor names or share (see Common mistakes)"),
    ]


def md_kpis(model):
    s = model["summary"]
    cur = model["provenance"]["currency"]
    return [
        ("Rank pressure", str(s["rank_pressure"])),
        ("Budget capped", str(s["budget_capped"])),
        ("Flagged spend (this week)", _money(s["flagged_cost_this"], cur)),
        ("Campaigns", f"{s['campaigns']} ({s['scored']} scored, {s['no_prior']} no-prior, "
            f"{s['no_is']} no-IS-data, {s['inactive']} inactive)"),
        ("Competitor rows (user-supplied)", str(s["competitor_rows"])),
    ]


def md_narrative(model):
    if model["summary"]["flagged"] != 0:
        return []
    return [
        "> **0 flagged campaigns is a clean result, not an error.** No Search campaign spending "
        "at least the minimum this week dropped impression share or jumped in CPC past the "
        "current thresholds. The sensitivity table below shows where flags would start to "
        "appear if the IS-drop threshold were relaxed, and the near-miss list shows the "
        "campaigns closest to the bar.",
    ]


def md_sections(model):
    cur = model["provenance"]["currency"]
    secs = []

    secs.append({
        "title": "IS-drop threshold sensitivity",
        "note": "How many campaigns flag as the impression-share-drop threshold changes "
                "(CPC-jump threshold and minimum spend held at current values).",
        "headers": ["IS drop threshold", "Rank pressure", "Budget capped", "Total"],
        "aligns": ["l", "r", "r", "r"],
        "rows": [[f"{r['is_drop_flag'] * 100:.1f}pp" + (" ← current" if r["is_current"] else ""),
                  r["rank_pressure"], r["budget_capped"], r["total"]] for r in model["sensitivity"]],
    })

    nm = model["near_misses"][:15]
    secs.append({
        "title": "Near misses",
        "note": "Scored, spend-eligible campaigns meeting neither bar yet, ranked by closeness "
                "(1.00 = would flag).",
        "headers": ["Campaign", "Driver", "IS Δ (WoW)", "CPC Δ (WoW)", "Cost this wk", "Closeness"],
        "aligns": ["l", "l", "r", "r", "r", "r"],
        "rows": [[r["campaign"], "IS drop" if r["driver"] == "is_drop" else "CPC jump",
                  _pct(r["is_delta_pp"]), _pct(r["cpc_delta_pct"]),
                  f"{r['cost_this']:,.2f}", f"{r['closeness']:.2f}"] for r in nm],
        "empty": "_None._",
    })

    conc = model["competitor_concentration"]
    comp_rows = [r for r in model["competitors"] if not r.get("is_self")]
    secs.append({
        "title": "Competitor concentration (Auction Insights — user-supplied CSV)",
        "note": ("HHI / effective-N / top-N share of impression share across the non-self "
                 "competitor rows in the Auction Insights export. NOT computed from the API — "
                 "present only when an export was supplied.") if comp_rows else
                "No Auction Insights export was supplied for this run — competitor names, "
                "overlap rate, and position-above rate are never available from the Google "
                "Ads API. Export Campaigns → Auction insights to add this section.",
        "headers": ["Metric", "Value"],
        "aligns": ["l", "r"],
        "rows": ([["Competitor rows", conc["n"]],
                  ["Top-" + str(conc["top_n"]) + " impression-share concentration", _pct(conc["top_share"])],
                  ["HHI (0–10,000)", f"{conc['hhi']:,.1f}"],
                  ["Effective-N competitors", f"{conc['effective_n']:.2f}"]] if comp_rows else []),
        "empty": "_No competitor rows supplied._",
    })

    excluded = [r for r in model["rows"] if r["status"] != "scored"]
    by_status = {}
    for r in excluded:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    label = {"no_prior": "No prior-week data (new/resumed campaign)",
             "no_is": "Impression-share data unavailable ('--' from Google Ads)",
             "inactive": "Inactive both weeks"}
    secs.append({
        "title": "Excluded — campaigns not classified",
        "note": "Every campaign survives into the model with a status; these could not be "
                "scored for rank/budget pressure this run. Nothing is silently dropped.",
        "headers": ["Reason", "Campaigns"],
        "aligns": ["l", "r"],
        "rows": [[label.get(k, k), n] for k, n in sorted(by_status.items(), key=lambda kv: -kv[1])],
        "empty": "_None — every campaign had usable this/prior-week impression-share data._",
    })
    return secs


def md_rows(model):
    """Every campaign with a status — the no-row-loss layer."""
    cur = model["provenance"]["currency"]
    headers = ["Campaign", "Status", f"Cost this wk ({cur})" if cur else "Cost this wk",
               "IS this wk", "IS Δ (WoW)", "Avg CPC Δ (WoW)", "Rank-lost Δ", "Budget-lost Δ", "Block"]
    out = []
    for r in model["rows"]:
        out.append([
            r["campaign"], r["status"].replace("_", " "), f"{r['cost_this']:,.2f}",
            _pct(r.get("impression_share_this")), _pct(r.get("is_delta_pp")),
            _pct(r.get("cpc_delta_pct")), _pct(r.get("rank_lost_delta")),
            _pct(r.get("budget_lost_delta")), r["block"] or "",
        ])
    return {
        "title": "All Search campaigns (every row, with status)",
        "note": "No row loss: every campaign in the pull appears here, scored or held out with "
                "the reason. Sorted by pressure score (highest first).",
        "headers": headers,
        "aligns": ["l", "l", "r", "r", "r", "r", "r", "r", "l"],
        "rows": out,
        "empty": "_No campaigns in the pull._",
    }


# --------------------------------------------------------------------------
# HTML adapters
# --------------------------------------------------------------------------
def in_play(r, params=None):
    """Reachable envelope for the in-Claude tuner's embed (widget_emit applies
    this). Only a scored row can EVER flag or appear in the near-miss list —
    every path requires status=='scored'. Spend-eligibility is NOT filtered
    here (min_cost is itself a tunable control the operator can lower), so
    every scored row stays reachable."""
    return r.get("status") == "scored"


def html_embed(model):
    return {
        "provenance": model["provenance"],
        "params": model["params"],
        "summary": model["summary"],
        "is_drop_ladder": model["is_drop_ladder"],
        "competitors": [{"domain": c.get("domain", ""), "campaign": c.get("campaign", ""),
                         "impression_share": c.get("impression_share"),
                         "overlap_rate": c.get("overlap_rate"),
                         "position_above_rate": c.get("position_above_rate"),
                         "is_self": c.get("is_self", False)} for c in model["competitors"]],
        "competitor_concentration": model["competitor_concentration"],
        "rows": [{
            "campaign": r["campaign"], "campaign_id": r["campaign_id"],
            "cost_this": r["cost_this"], "cost_prior": r["cost_prior"],
            "is_delta_pp": r["is_delta_pp"], "cpc_delta_pct": r["cpc_delta_pct"],
            "rank_lost_delta": r["rank_lost_delta"], "budget_lost_delta": r["budget_lost_delta"],
            "status": r["status"],
        } for r in model["rows"]],
    }


HTML_CONTROLS = [
    {"key": "is_drop_flag", "label": "IS-drop flag threshold", "kind": "slider",
     "min": 0.01, "max": 0.30, "step": 0.01, "sub": "WoW percentage-point drop"},
    {"key": "cpc_jump_flag", "label": "CPC-jump flag threshold", "kind": "slider",
     "min": 0.05, "max": 1.0, "step": 0.05, "sub": "WoW CPC increase"},
    {"key": "min_cost", "label": "Minimum this-week spend", "kind": "number", "sub": "flag eligibility"},
]

HTML_COLUMNS = [
    {"key": "campaign", "label": "Campaign"},
    {"key": "status", "label": "Status", "fmt": "status"},
    {"key": "cost_this", "label": "Cost this wk", "num": True, "fmt": "money"},
    {"key": "is_delta_pp", "label": "IS Δ (WoW)", "num": True, "fmt": "pct"},
    {"key": "cpc_delta_pct", "label": "CPC Δ (WoW)", "num": True, "fmt": "pct"},
    {"key": "block", "label": "Block", "fmt": "block"},
]

HTML_KPIS = [
    {"label": "Rank pressure", "key": "rank_pressure", "cls": "b1"},
    {"label": "Budget capped", "key": "budget_capped", "cls": "b2"},
    {"label": "Flagged", "key": "flagged"},
    {"label": "Flagged spend", "key": "flagged_cost_this", "money": True},
    {"label": "Competitor rows", "key": "competitor_rows"},
]

# Splices _shared/analytics.JS_MIRROR (gxSignals / gxPreScore / gxRoundHalfUp)
# ahead of the skill's classify/summarize wrappers, which mirror
# competitive_core.classify_campaign / classify / summarize exactly (verified
# by the Node-vs-Python gate).
JS_KERNEL = analytics.JS_MIRROR + r"""
classify = function(r,P){
  if(r.status!=="scored") return {block:"", flags:[]};
  var eligible = r.cost_this >= P.min_cost;
  var sigIn = {is_delta_pp: eligible ? r.is_delta_pp : null,
               cpc_delta_pct: eligible ? r.cpc_delta_pct : null};
  var rules = [
    {id:"is_drop", key:"is_delta_pp", op:"le", value: -P.is_drop_flag},
    {id:"cpc_jump", key:"cpc_delta_pct", op:"ge", value: P.cpc_jump_flag}
  ];
  var flags = gxSignals([sigIn], rules)[0];
  var block = "";
  if(flags.length){
    var rankD = r.rank_lost_delta||0, budgetD = r.budget_lost_delta||0;
    block = rankD >= budgetD ? "Rank pressure" : "Budget capped";
  }
  return {block:block, flags:flags};
};
summarize = function(rows,P){
  var flagged=0, rank=0, budget=0, flaggedCost=0;
  rows.forEach(function(r){
    var c = classify(r,P);
    if(c.block){
      flagged++; flaggedCost += r.cost_this;
      if(c.block==="Rank pressure") rank++; else budget++;
    }
  });
  var T=(typeof MODEL!=="undefined"&&MODEL&&MODEL.summary)?MODEL.summary:null;
  var scored=(T&&T.scored!=null)?T.scored:rows.filter(function(r){return r.status==="scored";}).length;
  var campaigns=(T&&T.campaigns!=null)?T.campaigns:rows.length;
  var compRows=(T&&T.competitor_rows!=null)?T.competitor_rows:0;
  return {flagged:flagged, rank_pressure:rank, budget_capped:budget,
          flagged_cost_this: gxRoundHalfUp(flaggedCost,2), scored:scored, campaigns:campaigns,
          competitor_rows: compRows};
};
"""

# Live logic text + sensitivity strip + competitor concentration panel.
JS_EXTRA = r"""
renderExtra = function(host,H){
  function sensitivity(){
    var saved=P.is_drop_flag, out=[];
    MODEL.is_drop_ladder.forEach(function(t){
      P.is_drop_flag=t; var s=summarize(MODEL.rows,P);
      out.push({t:t, rank:s.rank_pressure, budget:s.budget_capped, total:s.flagged,
                cur:Math.abs(t-saved)<1e-9});
    });
    P.is_drop_flag=saved; return out;
  }
  var f=(+P.is_drop_flag*100).toFixed(1), m=(+P.cpc_jump_flag*100).toFixed(1);
  var h='<div class="card"><h2>Flag logic (live)</h2>'+
   '<div class="logic"><b>Rank pressure</b> — campaign spends &ge; min this-week spend, and '+
   '(IS drop &ge; '+f+'pp WoW OR CPC jump &ge; '+m+'% WoW), and the rank-lost-IS delta &ge; the budget-lost-IS delta</div>'+
   '<div class="logic"><b>Budget capped</b> — same flag condition, but the budget-lost-IS delta is larger</div></div>';
  h+='<div class="card sens"><h2>IS-drop threshold sensitivity</h2><div class="note">Flags as the IS-drop threshold changes (other params held current).</div>'+
     '<table><thead><tr><th>Threshold</th><th class="num">Rank</th><th class="num">Budget</th><th class="num">Total</th></tr></thead><tbody>'+
     sensitivity().map(function(r){return '<tr><td class="'+(r.cur?'cur':'')+'">'+(r.t*100).toFixed(1)+'pp'+(r.cur?' ← current':'')+'</td>'+
       '<td class="num">'+r.rank+'</td><td class="num">'+r.budget+'</td><td class="num">'+r.total+'</td></tr>';}).join('')+
     '</tbody></table></div>';
  var comp = (MODEL.competitors||[]).filter(function(c){return !c.is_self;});
  h+='<div class="card"><h2>Competitor concentration (Auction Insights)</h2>';
  if(comp.length){
    var c = MODEL.competitor_concentration;
    h+='<div class="note">User-supplied CSV — never from the API. Top-'+c.top_n+' share '+
       (c.top_share*100).toFixed(1)+'% · HHI '+c.hhi.toFixed(1)+' · Effective-N '+c.effective_n.toFixed(2)+'</div>';
    h+='<table><thead><tr><th>Domain</th><th class="num">Impr. share</th><th class="num">Overlap</th><th class="num">Position above</th></tr></thead><tbody>';
    comp.slice(0,15).forEach(function(c){
      h+='<tr><td>'+H.esc(c.domain)+'</td><td class="num">'+((c.impression_share||0)*100).toFixed(1)+'%</td>'+
         '<td class="num">'+((c.overlap_rate||0)*100).toFixed(1)+'%</td><td class="num">'+((c.position_above_rate||0)*100).toFixed(1)+'%</td></tr>';
    });
    h+='</tbody></table>';
  } else {
    h+='<div class="note">No Auction Insights export supplied for this run.</div>';
  }
  h+='</div>';
  host.innerHTML=h;
};
"""


# --------------------------------------------------------------------------
# Charts — declared here, GENERATED by _shared/render/charts.py (never hand-
# authored). Only fields present in BOTH row shapes (model rows and the html
# embed) are used: cost_this, is_delta_pp, cpc_delta_pct, status, campaign.
# --------------------------------------------------------------------------
_BLOCK_COLORS = {"domain": ["Rank pressure", "Budget capped", "Unflagged"],
                 "range": ["#0369a1", "#7c3aed", "#cbd5e1"]}

CHARTS = [
    {
        "id": "pressure_by_block",
        "title": "This-week spend by pressure block",
        "mark": {"type": "bar"},
        "transform": [
            {"filter": "datum.block != ''"},
            {"aggregate": [{"op": "sum", "field": "cost_this", "as": "spend"},
                           {"op": "count", "as": "campaigns"}],
             "groupby": ["block"]},
        ],
        "encoding": {
            "y": {"field": "block", "type": "nominal", "title": None,
                  "scale": {"domain": ["Rank pressure", "Budget capped"]}},
            "x": {"field": "spend", "type": "quantitative", "title": "This-week spend"},
            "color": {"field": "block", "type": "nominal", "legend": None,
                      "scale": {"domain": ["Rank pressure", "Budget capped"],
                                "range": ["#0369a1", "#7c3aed"]}},
            "tooltip": [{"field": "block", "title": "Block"},
                        {"field": "spend", "title": "Spend", "format": ",.2f"},
                        {"field": "campaigns", "title": "Campaigns"}],
        },
        "height": 120,
        "md": True, "widget": True,
    },
    {
        "id": "is_cpc_scatter",
        "title": "Scored campaigns — WoW impression-share delta vs CPC delta (flagged colored)",
        "mark": {"type": "point"},
        "transform": [
            {"filter": "datum.status == 'scored'"},
            {"calculate": "datum.block != '' ? datum.block : 'Unflagged'", "as": "flag"},
        ],
        "encoding": {
            "x": {"field": "is_delta_pp", "type": "quantitative", "title": "IS Δ (WoW, fraction)"},
            "y": {"field": "cpc_delta_pct", "type": "quantitative", "title": "CPC Δ (WoW, fraction)"},
            "color": {"field": "flag", "type": "nominal", "title": None, "scale": _BLOCK_COLORS},
            "tooltip": [{"field": "campaign", "title": "Campaign"},
                        {"field": "flag", "title": "Block"},
                        {"field": "cost_this", "title": "Cost this wk", "format": ",.2f"},
                        {"field": "is_delta_pp", "title": "IS Δ", "format": ".3f"},
                        {"field": "cpc_delta_pct", "title": "CPC Δ", "format": ".3f"}],
        },
        "height": 280,
        "md": True, "widget": False,
    },
]


# --------------------------------------------------------------------------
# The spec object the toolkit consumes.
# --------------------------------------------------------------------------
SPEC = {
    "slug_prefix": "competitive-pressure",
    "row_noun": "campaigns",
    "title": "Competitive Pressure Filter",
    "about": {
        "summary": "Flags Search campaigns losing auction position: a week-over-week impression-share drop or CPC jump, spending at least the minimum threshold this week, attributed to rank pressure (competitor bids/quality) or a budget cap depending on which loss driver worsened more. The competitor names and their own impression share (Auction Insights) are never available from the Google Ads API — supply that export to see the concentration read.",
        "legend": [
            {"label": "Rank pressure", "desc": "Flagged campaign whose rank-lost impression share worsened more than its budget-lost impression share this week — protect position (Quality Score / bids)."},
            {"label": "Budget capped", "desc": "Flagged campaign whose budget-lost impression share worsened more — a budget decision, not a quality one."},
        ],
    },
    "methodology_ref": "references/competitive-pressure-filter.md",
    "md_params": md_params,
    "md_kpis": md_kpis,
    "md_narrative": md_narrative,
    "md_sections": md_sections,
    "md_rows": md_rows,
    "in_play": in_play,
    "html_embed": html_embed,
    "html_controls": HTML_CONTROLS,
    "html_columns": HTML_COLUMNS,
    "html_kpis": HTML_KPIS,
    "js_kernel": JS_KERNEL,
    "js_extra": JS_EXTRA,
    "charts": CHARTS,
    # xlsx layout is attached in competitive_xlsx_spec to keep this module
    # stdlib-only and import-light; build_competitive_report wires it in for xlsx.
}
