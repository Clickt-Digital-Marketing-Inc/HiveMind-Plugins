#!/usr/bin/env python3
"""Render spec for the performance report — adapts perf_core's model to the shared
render toolkit (_shared/render). Stdlib only.

The ROAS-bucket math, the anomaly signals/pre-score, and the spend/conversion
concentration all live once in perf_core (Python) and are mirrored in
`JS_KERNEL` (browser, via `analytics.JS_MIRROR`) — the Node-vs-Python equality
gate keeps them in sync.
"""
from __future__ import annotations

import analytics
from render import model as M  # noqa: E402  (source_label — HM-572 canonical "Data source" line)


def _money(v, cur):
    return f"{float(v or 0):,.2f}" + (f" {cur}" if cur else "")


def _roas(v):
    return "—" if v is None else f"{float(v):.2f}×"


def _pct(v):
    return "—" if v is None else f"{float(v) * 100:.1f}%"


def _pop(v):
    return "—" if v is None else (f"+{v * 100:.0f}%" if v >= 0 else f"{v * 100:.0f}%")


# --------------------------------------------------------------------------
# Markdown adapters
# --------------------------------------------------------------------------
def md_params(model):
    p = model["params"]
    return [
        ("Data source", M.source_label(model["provenance"].get("source"))),
        ("ROAS goal", f"{p['roas_goal']:.2f}×" + M.inline_marker(model, "roas_goal")),
        ("Budget-lost-IS flag", f"{p['budget_lost_is_flag'] * 100:.0f}%"),
        ("Anomaly delta flag", f"{p['delta_flag'] * 100:.0f}%"),
        ("Fix spend floor", _money(p["min_spend"], model["provenance"]["currency"])),
    ]


def md_kpis(model):
    s = model["summary"]
    cur = model["provenance"]["currency"]
    return [
        ("Spend", _money(s["spend"], cur)),
        ("Revenue", _money(s["revenue"], cur)),
        ("ROAS", _roas(s["roas"])),
        ("Conversions", f"{s['conversions']:.2f}"),
        ("CPA", _money(s["cpa"], cur) if s["cpa"] is not None else "—"),
        ("Anomalies", f"{s['anomalies']}"),
        ("Campaigns", f"{s['campaigns']} ({s['scale']} scale · {s['winner']} winner · "
                      f"{s['fix']} fix · {s['hold']} hold · {s['no_value']} no-value)"),
    ]


def md_narrative(model):
    s = model["summary"]
    lines = []
    if s["scale"] > 0:
        lines.append(f"> **{s['scale']} budget-constrained winner(s).** These campaigns clear the ROAS "
                     "goal *and* are losing impression share to budget — the data-backed case for a "
                     "budget increase. See the Budget-increase candidates section.")
    if s["roas"] is None:
        lines.append("> **ROAS unavailable account-wide** — no conversion value is tracked. Reporting "
                     "CPA and volume instead of a fabricated return.")
    if s["anomalies"] > 0:
        lines.append(f"> **{s['anomalies']} campaign(s) flagged for a period-over-period anomaly** "
                     f"(spend/conversions/revenue swung beyond the "
                     f"{model['params']['delta_flag'] * 100:.0f}% delta flag vs the prior period) — "
                     "see the Anomalies section.")
    return lines


def _bucket_rows(model, bucket, sort_key="cost"):
    rs = [r for r in model["rows"] if r.get("bucket") == bucket]
    rs.sort(key=lambda r: r.get(sort_key) or 0, reverse=True)
    return rs


def md_sections(model):
    cur = model["provenance"]["currency"]
    secs = []

    top = sorted([r for r in model["rows"] if r["value"] is not None],
                 key=lambda r: r["value"] or 0, reverse=True)[:10]
    secs.append({
        "title": "Top campaigns by revenue",
        "headers": ["Campaign", f"Revenue ({cur})", f"Spend ({cur})", "ROAS", "Conv", "Bucket"],
        "aligns": ["l", "r", "r", "r", "r", "l"],
        "rows": [[r["campaign"], f"{r['value']:,.2f}", f"{r['cost']:,.2f}", _roas(r["roas"]),
                  f"{r['conversions']:.1f}", r["bucket"]] for r in top],
        "empty": "_No campaigns with tracked revenue._",
    })

    secs.append({
        "title": "Budget-increase candidates (Scale)",
        "note": "Clear the ROAS goal and are losing impression share to budget — scale these.",
        "headers": ["Campaign", "ROAS", f"Spend ({cur})", "Budget-lost IS", "Spend Δ"],
        "aligns": ["l", "r", "r", "r", "r"],
        "rows": [[r["campaign"], _roas(r["roas"]), f"{r['cost']:,.2f}", _pct(r["budget_lost_is"]),
                  _pop(r["spend_delta"])] for r in _bucket_rows(model, "Scale")],
        "empty": "_None — no goal-clearing campaign is budget-throttled._",
    })

    secs.append({
        "title": "ROAS laggards (Fix)",
        "note": "Below the ROAS goal at/above the spend floor — fix before scaling.",
        "headers": ["Campaign", "ROAS", f"Spend ({cur})", f"Revenue ({cur})", "Conv", "ROAS Δ vs prior"],
        "aligns": ["l", "r", "r", "r", "r", "r"],
        "rows": [[r["campaign"], _roas(r["roas"]), f"{r['cost']:,.2f}",
                  f"{(r['value'] or 0):,.2f}", f"{r['conversions']:.1f}", _pop(r["value_delta"])]
                 for r in _bucket_rows(model, "Fix")],
        "empty": "_None._",
    })

    vis = [r for r in model["rows"] if r["budget_lost_is"] is not None and r["budget_lost_is"] > 0]
    vis.sort(key=lambda r: r["budget_lost_is"], reverse=True)
    secs.append({
        "title": "Visibility — impression share lost to budget",
        "note": "Where more budget would buy more of the auction (rank-lost IS is a quality/bid issue "
                "instead). Null for PMax/Display.",
        "headers": ["Campaign", "Search IS", "Budget-lost IS", "Rank-lost IS", f"Spend ({cur})"],
        "aligns": ["l", "r", "r", "r", "r"],
        "rows": [[r["campaign"], _pct(r["search_is"]), _pct(r["budget_lost_is"]),
                  _pct(r["rank_lost_is"]), f"{r['cost']:,.2f}"] for r in vis[:15]],
        "empty": "_No budget-lost impression share reported._",
    })

    secs.append({
        "title": "ROAS-goal sensitivity",
        "note": "How the Scale / Winner / Fix counts move as the ROAS goal changes.",
        "headers": ["ROAS goal", "Scale", "Winner", "Fix"],
        "aligns": ["l", "r", "r", "r"],
        "rows": [[f"{r['roas_goal']:.1f}×" + (" ← current" if r["is_current"] else ""),
                  r["scale"], r["winner"], r["fix"]] for r in model["goal_sensitivity"]],
    })

    anomalous = sorted([r for r in model["rows"] if r.get("flags")],
                       key=lambda r: r.get("pre_score", 0), reverse=True)
    secs.append({
        "title": "Anomalies (period-over-period)",
        "note": f"Campaigns whose spend, conversions, or revenue swung beyond the "
                f"{model['params']['delta_flag'] * 100:.0f}% delta flag vs the prior period. "
                "Sorted by anomaly score (weighted: conversion/revenue drops outweigh spend swings). "
                "A campaign with no prior-period data is never flagged.",
        "headers": ["Campaign", "Score", "Flags", "Spend Δ", "Conv Δ", "Value Δ"],
        "aligns": ["l", "r", "l", "r", "r", "r"],
        "rows": [[r["campaign"], f"{r['pre_score']:.2f}", ", ".join(r["flags"]),
                  _pop(r["spend_delta"]), _pop(r["conv_delta"]), _pop(r["value_delta"])]
                 for r in anomalous],
        "empty": "_No anomalies at the current delta flag._",
    })

    conc = model["concentration"]

    def _conc_row(label, c):
        return [label, f"{c['top_share'] * 100:.1f}%", f"{c['hhi']:.1f}", f"{c['effective_n']:.2f}"]

    secs.append({
        "title": "Concentration — spend & conversions (top 3 campaigns)",
        "note": "How concentrated spend/conversions are across the top 3 campaigns. A high top-3 "
                "share / HHI (or a low effective-N) signals reliance on a small number of campaigns — "
                "a concentration risk worth diversifying.",
        "headers": ["Metric", "Top-3 share", "HHI (0–10,000)", "Effective-N"],
        "aligns": ["l", "r", "r", "r"],
        "rows": [_conc_row("Spend", conc["spend"]), _conc_row("Conversions", conc["conversions"])],
    })
    return secs


def md_rows(model):
    cur = model["provenance"]["currency"]
    headers = ["Campaign", "Channel", "Status", "Liveness", "Impr", "Clicks", "CTR",
               f"Spend ({cur})" if cur else "Spend", "Conv", f"Revenue ({cur})" if cur else "Revenue",
               "ROAS", "Budget-lost IS", "Spend Δ", "Bucket"]
    out = []
    for r in model["rows"]:
        out.append([
            r["campaign"], r["channel"], r["status"].replace("_", " "),
            r["liveness"].replace("_", " "),
            int(r["impressions"]) if float(r["impressions"]).is_integer() else round(r["impressions"], 2),
            int(r["clicks"]) if float(r["clicks"]).is_integer() else round(r["clicks"], 2),
            f"{r['ctr'] * 100:.2f}%", f"{r['cost']:,.2f}", f"{r['conversions']:.2f}",
            "" if r["value"] is None else f"{r['value']:,.2f}", _roas(r["roas"]),
            _pct(r["budget_lost_is"]), _pop(r["spend_delta"]), r["bucket"] or "",
        ])
    return {
        "title": "All campaigns (every row, with status)",
        "note": "No row loss: every campaign in the window appears here (with its liveness band). "
                "Sorted by spend (highest first).",
        "headers": headers,
        "aligns": ["l", "l", "l", "l", "r", "r", "r", "r", "r", "r", "r", "r", "r", "l"],
        "rows": out,
        "empty": "_No campaigns in the window._",
    }


# --------------------------------------------------------------------------
# HTML adapters
# --------------------------------------------------------------------------
def html_embed(model):
    return {
        "provenance": model["provenance"],
        "params": model["params"],
        "summary": model["summary"],
        "roas_ladder": model["roas_ladder"],
        "concentration": model["concentration"],
        "rows": [{
            "campaign": r["campaign"], "channel": r["channel"], "status": r["status"],
            "liveness": r["liveness"], "liveness_note": r.get("liveness_note", ""),
            "impr": r["impressions"], "clicks": r["clicks"], "ctr": r["ctr"],
            "cost": r["cost"], "conv": r["conversions"], "value": r["value"], "roas": r["roas"],
            "budget_lost_is": r["budget_lost_is"], "search_is": r["search_is"],
            "spend_delta": r["spend_delta"], "conv_delta": r["conv_delta"],
            "value_delta": r["value_delta"],
        } for r in model["rows"]],
    }


HTML_CONTROLS = [
    {"key": "roas_goal", "label": "ROAS goal", "kind": "slider",
     "min": 1, "max": 10, "step": 0.5, "sub": "conversions value ÷ spend"},
    {"key": "budget_lost_is_flag", "label": "Budget-lost-IS flag", "kind": "slider",
     "min": 0.0, "max": 0.5, "step": 0.05, "sub": "throttled above this share"},
    {"key": "delta_flag", "label": "Anomaly delta flag", "kind": "slider",
     "min": 0.05, "max": 1.0, "step": 0.05, "sub": "period-over-period swing that flags an anomaly"},
    {"key": "min_spend", "label": "Fix spend floor", "kind": "number"},
]

HTML_COLUMNS = [
    {"key": "campaign", "label": "Campaign"},
    {"key": "channel", "label": "Channel"},
    {"key": "status", "label": "Status", "fmt": "status"},
    {"key": "liveness", "label": "Liveness", "fmt": "status"},
    {"key": "impr", "label": "Impr", "num": True, "fmt": "int"},
    {"key": "ctr", "label": "CTR", "num": True, "fmt": "pct"},
    {"key": "cost", "label": "Spend", "num": True, "fmt": "money"},
    {"key": "conv", "label": "Conv", "num": True, "fmt": "num"},
    {"key": "value", "label": "Revenue", "num": True, "fmt": "money"},
    {"key": "roas", "label": "ROAS", "num": True, "fmt": "num"},
    {"key": "budget_lost_is", "label": "Budget-lost IS", "num": True, "fmt": "pct"},
    {"key": "bucket", "label": "Bucket", "fmt": "block"},
]

HTML_KPIS = [
    {"label": "ROAS goal", "key": "roas_goal"},
    {"label": "Spend", "key": "spend", "money": True},
    {"label": "Revenue", "key": "revenue", "money": True},
    {"label": "ROAS", "key": "roas"},
    {"label": "Conversions", "key": "conversions"},
    {"label": "Scale", "key": "scale", "cls": "b1"},
    {"label": "Fix", "key": "fix", "cls": "b2"},
    {"label": "Anomalies", "key": "anomalies", "cls": "b2"},
]

# Mirrors perf_core.classify_row / annotate_anomalies / summarize exactly
# (Node-vs-Python verified). The anomaly signals/pre-score/concentration math
# is the shared _shared/analytics.py kernel — spliced in verbatim (never
# re-derived) so the JS_MIRROR-vs-Python parity gate covers it too.
JS_KERNEL = analytics.JS_MIRROR + r"""
var ANOMALY_WEIGHTS = {spend_spike:2.0, spend_drop:1.5, conv_drop:2.5, value_drop:2.0};
function anomalyRules(P){
  return [
    {id:"spend_spike", key:"spend_delta", op:"gt", value:P.delta_flag},
    {id:"spend_drop", key:"spend_delta", op:"lt", value:-P.delta_flag},
    {id:"conv_drop", key:"conv_delta", op:"lt", value:-P.delta_flag},
    {id:"value_drop", key:"value_delta", op:"lt", value:-P.delta_flag},
  ];
}
classify = function(r,P){
  // Liveness gate (HM-603): a dormant campaign is never bucketed or flagged —
  // mirrors perf_core.classify_row / annotate_anomalies. `liveness` is a static
  // embedded field (not tuning-dependent), so the kernel only READS it.
  if(r.liveness==="dormant"){ return {block:"", flags:[], pre_score:0}; }
  let block="";
  if(r.status==="measured" && r.roas!==null){
    if(r.roas >= P.roas_goal){
      block=(r.budget_lost_is!==null && r.budget_lost_is > P.budget_lost_is_flag)?"Scale":"Winner";
    } else {
      block=(r.cost >= P.min_spend)?"Fix":"Hold";
    }
  }
  const flags=gxSignals([r], anomalyRules(P))[0];
  const pre_score=gxPreScore({flags:flags}, ANOMALY_WEIGHTS);
  return {block:block, flags:flags, pre_score:pre_score};
};
summarize = function(rows,P){
  let spend=0,value=0,conv=0,clicks=0,impr=0,scale=0,winner=0,fix=0,hold=0,nv=0,anomalies=0;
  rows.forEach(r=>{
    spend+=r.cost; conv+=r.conv; clicks+=r.clicks; impr+=r.impr;
    if(r.value!==null) value+=r.value;
    if(r.status==="no_value") nv++;
    const c=classify(r,P), b=c.block;
    if(b==="Scale")scale++; else if(b==="Winner")winner++; else if(b==="Fix")fix++; else if(b==="Hold")hold++;
    if(c.flags.length)anomalies++;
  });
  return {campaigns:rows.length, spend:Math.round(spend*100)/100, revenue:Math.round(value*100)/100,
    conversions:Math.round(conv*100)/100, roas:spend?Math.round(value/spend*100)/100:null,
    cpa:conv?Math.round(spend/conv*100)/100:null, ctr:impr?clicks/impr:0,
    scale, winner, fix, hold, no_value:nv, anomalies, roas_goal:P.roas_goal||null};
};
"""

JS_EXTRA = r"""
renderExtra = function(host,H){
  function sens(){
    const saved=P.roas_goal,out=[];
    MODEL.roas_ladder.forEach(g=>{P.roas_goal=g; const s=summarize(MODEL.rows,P);
      out.push({g,scale:s.scale,winner:s.winner,fix:s.fix,cur:Math.abs(g-saved)<1e-9})});
    P.roas_goal=saved; return out;
  }
  const scale=MODEL.rows.filter(r=>classify(r,P).block==="Scale").sort((a,b)=>(b.cost||0)-(a.cost||0));
  let h='<div class="card"><h2>Budget-increase candidates (Scale)</h2>'+
        '<div class="note">Clear the ROAS goal and losing impression share to budget.</div>';
  if(!scale.length){h+='<div class="note">None at the current goal.</div>';}
  else{
    h+='<table><thead><tr><th>Campaign</th><th class="num">ROAS</th><th class="num">Spend</th><th class="num">Budget-lost IS</th></tr></thead><tbody>';
    scale.forEach(r=>{h+=`<tr><td>${H.esc(r.campaign)}</td><td class="num">${r.roas.toFixed(2)}×</td><td class="num">${H.money(r.cost)}</td><td class="num">${(r.budget_lost_is*100).toFixed(1)}%</td></tr>`;});
    h+='</tbody></table>';
  }
  h+='</div><div class="card sens"><h2>ROAS-goal sensitivity</h2>'+
     '<table><thead><tr><th>Goal</th><th class="num">Scale</th><th class="num">Winner</th><th class="num">Fix</th></tr></thead><tbody>'+
     sens().map(r=>`<tr><td class="${r.cur?'cur':''}">${r.g.toFixed(1)}×${r.cur?' ← current':''}</td><td class="num ${r.cur?'cur':''}">${r.scale}</td><td class="num">${r.winner}</td><td class="num">${r.fix}</td></tr>`).join("")+
     '</tbody></table></div>';

  // Anomalies (live — recomputed from classify(r,P) on every param change,
  // so the anomaly delta-flag slider re-tunes this card in place).
  const anomRows=MODEL.rows.map(r=>Object.assign({},r,classify(r,P))).filter(r=>r.flags.length>0)
    .sort((a,b)=>b.pre_score-a.pre_score);
  const pop=v=>v==null?"—":((v>=0?"+":"")+(v*100).toFixed(0)+"%");
  h+='<div class="card"><h2>Anomalies (live)</h2>'+
     `<div class="note">Period-over-period swings beyond the delta flag (${(P.delta_flag*100).toFixed(0)}%). `+
     'A campaign with no prior-period data is never flagged.</div>';
  if(!anomRows.length){h+='<div class="note">None at the current delta flag.</div>';}
  else{
    h+='<table><thead><tr><th>Campaign</th><th class="num">Score</th><th>Flags</th><th class="num">Spend Δ</th><th class="num">Conv Δ</th><th class="num">Value Δ</th></tr></thead><tbody>';
    anomRows.slice(0,20).forEach(r=>{h+=`<tr><td>${H.esc(r.campaign)}</td><td class="num">${r.pre_score.toFixed(2)}</td>`+
      `<td>${H.esc(r.flags.join(", "))}</td><td class="num">${pop(r.spend_delta)}</td>`+
      `<td class="num">${pop(r.conv_delta)}</td><td class="num">${pop(r.value_delta)}</td></tr>`;});
    h+='</tbody></table>';
  }
  h+='</div>';

  // Concentration (static — top_n is fixed, not a tunable control, so this
  // card reads MODEL.concentration as computed once by the Python model).
  const cs=MODEL.concentration||{};
  const concRow=(label,c)=>c?`<tr><td>${label}</td><td class="num">${(c.top_share*100).toFixed(1)}%</td><td class="num">${c.hhi.toFixed(1)}</td><td class="num">${c.effective_n.toFixed(2)}</td></tr>`:"";
  h+='<div class="card"><h2>Concentration — top 3 campaigns</h2>'+
     '<div class="note">Reliance on a small number of campaigns for spend/conversions — a high '+
     'top-3 share/HHI (or a low effective-N) is a concentration risk.</div>'+
     '<table><thead><tr><th></th><th class="num">Top-3 share</th><th class="num">HHI</th><th class="num">Effective-N</th></tr></thead><tbody>'+
     concRow("Spend",cs.spend)+concRow("Conversions",cs.conversions)+
     '</tbody></table></div>';

  host.innerHTML=h;
};
"""


# --------------------------------------------------------------------------
# Charts — declared here, GENERATED by _shared/render/charts.py (never hand-
# authored). One declaration drives both paths: the static SVGs shipped with
# the md/widget (rendered by vl-convert at the model's default params) and the
# live explorer charts (vendored Vega-Lite re-deriving from the classify(r,P)-
# augmented rows on every slider move). All aggregation lives in the Vega-Lite
# `transform` below — shared verbatim — and only uses fields present in BOTH
# row shapes (the chart_rows-adapted model rows and the html embed): campaign,
# cost, value, roas, status, block. The kernel's classify returns `block` while
# the Python rows carry `bucket`, so chart_rows mirrors the live augmentation
# by copying bucket -> block for the static render path.
# --------------------------------------------------------------------------
# Bucket colors match the explorer badges (blockClass in _shared/render/html.py):
# Scale -> scale (green), Winner -> winner (blue), Fix -> fix (red),
# Hold -> hold (slate).
_BUCKET_DOMAIN = ["Scale", "Winner", "Fix", "Hold"]
_BUCKET_COLORS = {"domain": _BUCKET_DOMAIN,
                  "range": ["#15803d", "#0369a1", "#b91c1c", "#475569"]}


def chart_rows(model):
    """Static chart data: model rows with the live kernel's field name (`block`)
    mirrored from the Python `bucket`, so one transform serves both paths."""
    return [dict(r, block=r["bucket"]) for r in model["rows"]]


CHARTS = [
    {
        "id": "spend_by_bucket",
        "title": "Spend by ROAS bucket",
        "mark": {"type": "bar"},
        "transform": [
            {"filter": "datum.block != ''"},
            {"aggregate": [{"op": "sum", "field": "cost", "as": "spend"},
                           {"op": "count", "as": "campaigns"}],
             "groupby": ["block"]},
        ],
        "encoding": {
            "y": {"field": "block", "type": "nominal", "title": None,
                  "scale": {"domain": _BUCKET_DOMAIN}},
            "x": {"field": "spend", "type": "quantitative", "title": "Spend"},
            "color": {"field": "block", "type": "nominal", "legend": None,
                      "scale": _BUCKET_COLORS},
            "tooltip": [{"field": "block", "title": "Bucket"},
                        {"field": "spend", "title": "Spend", "format": ",.2f"},
                        {"field": "campaigns", "title": "Campaigns"}],
        },
        "height": 140,
        "md": True, "widget": False,
    },
    {
        "id": "spend_by_campaign",
        "title": "Spend by campaign (top 12)",
        "mark": {"type": "bar"},
        "transform": [
            {"window": [{"op": "rank", "as": "spend_rank"}],
             "sort": [{"field": "cost", "order": "descending"}]},
            {"filter": "datum.spend_rank <= 12"},
        ],
        "encoding": {
            "y": {"field": "campaign", "type": "nominal", "title": None, "sort": "-x"},
            "x": {"field": "cost", "type": "quantitative", "title": "Spend"},
            "tooltip": [{"field": "campaign", "title": "Campaign"},
                        {"field": "cost", "title": "Spend", "format": ",.2f"}],
        },
        "height": 280,
        "md": True, "widget": True,
    },
    {
        "id": "revenue_spend_scatter",
        "title": "Campaigns — revenue vs spend (tracked-value only)",
        "mark": {"type": "point"},
        "transform": [
            {"filter": "datum.status == 'measured' && datum.roas != null"},
        ],
        "encoding": {
            "x": {"field": "cost", "type": "quantitative", "title": "Spend"},
            "y": {"field": "value", "type": "quantitative", "title": "Revenue"},
            "tooltip": [{"field": "campaign", "title": "Campaign"},
                        {"field": "cost", "title": "Spend", "format": ",.2f"},
                        {"field": "value", "title": "Revenue", "format": ",.2f"},
                        {"field": "roas", "title": "ROAS", "format": ".2f"}],
        },
        "height": 280,
        "md": True, "widget": False,
    },
]


SPEC = {
    "slug_prefix": "performance-report",
    "row_noun": "campaigns",
    "title": "Performance Report",
    "about": {
        "summary": "Classifies campaigns by ROAS against your goal so you know where to add budget and where to fix efficiency. Set the ROAS goal and the impression-share-lost flag (what counts as budget-throttled); the Fix floor keeps tiny laggards out of the Fix list.",
        "legend": [
            {"label": "Scale", "desc": "Clears the ROAS goal and is losing impression share to budget — add budget."},
            {"label": "Winner", "desc": "Clears the goal and isn't budget-throttled — performing well as-is."},
            {"label": "Fix", "desc": "Below goal with spend ≥ the Fix floor — a material laggard needing efficiency work."},
            {"label": "Hold", "desc": "Below goal but under the spend floor — monitor, don't act yet."},
        ],
    },
    "methodology_ref": "references/performance-report.md",
    "window_labels": ("Period", "Prior period"),
    "md_params": md_params,
    "md_kpis": md_kpis,
    "md_narrative": md_narrative,
    "md_sections": md_sections,
    "md_rows": md_rows,
    "html_embed": html_embed,
    "html_controls": HTML_CONTROLS,
    "html_columns": HTML_COLUMNS,
    "html_kpis": HTML_KPIS,
    "js_kernel": JS_KERNEL,
    "js_extra": JS_EXTRA,
    "charts": CHARTS,
    "chart_rows": chart_rows,
}
