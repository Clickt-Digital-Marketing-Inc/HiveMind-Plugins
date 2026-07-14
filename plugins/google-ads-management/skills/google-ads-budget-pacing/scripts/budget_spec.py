#!/usr/bin/env python3
"""Render spec for the budget & pacing report — adapts budget_core's model to the
shared render toolkit (_shared/render). Stdlib only.

The bucket + pacing math lives once in budget_core (Python) and is mirrored in
`JS_KERNEL` (browser) — the Node-vs-Python equality gate keeps them in sync.
`JS_KERNEL` splices `analytics.JS_MIRROR` verbatim (HM-535's spend-concentration
+ pace-pre-score deepening reuses the same primitives budget_core.py calls), then
layers a `pace(r,P)` + `summarize` that recompute the same concentration/pace
aggregates from the html-embedded rows (field `conv`, not `conversions` — the
html_embed rename).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "_shared"))
import analytics  # noqa: E402  (_shared on sys.path — see above)
from render import model as M  # noqa: E402  (source_label — HM-572 canonical "Data source" line)


def _money(v, cur):
    return "—" if v is None else f"{float(v):,.2f}" + (f" {cur}" if cur else "")


def _pct(v):
    return "—" if v is None else f"{float(v) * 100:.1f}%"


def _ratio(v):
    return "—" if v is None else f"{float(v) * 100:.0f}%"


# --------------------------------------------------------------------------
def md_params(model):
    p = model["params"]
    pr = model["provenance"]
    cur = pr["currency"]
    return [
        ("Data source", M.source_label(pr.get("source"))),
        ("Monthly goal", _money(p["monthly_goal"] or None, cur)),
        ("Target CPA", _money(p["target_cpa"], cur)),
        ("Budget-lost-IS flag", f"{p['budget_lost_is_flag'] * 100:.0f}%"),
        ("Kill / min-budget multiples", f"{p['kill_multiple']:.0f}× / {p['min_budget_multiple']:.0f}×"),
        ("Pacing tolerance", f"±{p['pacing_tolerance'] * 100:.0f}%"),
    ]


def md_kpis(model):
    s = model["summary"]
    cur = model["provenance"]["currency"]
    pace = "—" if s["pace_ratio"] is None else f"{s['pace_ratio'] * 100:.0f}% of expected ({s['pace_verdict']})"
    return [
        ("MTD spend", _money(s["mtd_spend"], cur)),
        ("Expected MTD", _money(s["expected_mtd"], cur)),
        ("Pacing", pace),
        ("Spend (window)", _money(s["spend"], cur)),
        ("CPA", _money(s["cpa"], cur)),
        ("Buckets", f"{s['kill']} kill · {s['raise_']} raise · {s['rank_limited']} rank · "
                    f"{s['low_budget']} low-budget · {s['ok']} ok · {s['no_budget']} no-budget"),
        ("Spend concentration (top-3)", f"{s['conc_top3_pct']:.1f}% · HHI {s['conc_hhi']:.1f} · "
                                        f"Effective N {s['conc_effective_n']:.2f}"),
        ("Pace pre-score", f"{s['over_pace']} over-pace · {s['under_pace']} under-pace · "
                           f"{s['off_pace_high_conf']} off-pace at high confidence"),
    ]


def md_narrative(model):
    s = model["summary"]
    lines = []
    if s["pace_verdict"] == "over":
        lines.append("> **Over-pacing.** MTD spend is running ahead of goal — budgets risk early "
                     "exhaustion. Rein in over-pacing campaigns that are below target efficiency.")
    elif s["pace_verdict"] == "under":
        lines.append("> **Under-pacing.** Spend is behind goal — volume is being left on the table. "
                     "Raise budgets on the constrained winners below (≤ +20% per step).")
    if s["kill"] > 0:
        lines.append(f"> **{s['kill']} kill candidate(s)** burning ≥ the 3× rule with zero conversions "
                     "— stop the bleed first.")
    if s["raise_"] > 0:
        lines.append(f"> **{s['raise_']} budget-constrained winner(s)** — raise budget **≤ +20% per "
                     "step** and re-check in 7–14 days. Do not raise rank-limited campaigns.")
    return lines


def _bucket(model, b, key="cost"):
    rs = [r for r in model["rows"] if r.get("bucket") == b]
    rs.sort(key=lambda r: r.get(key) or 0, reverse=True)
    return rs


def md_sections(model):
    cur = model["provenance"]["currency"]
    p = model["params"]
    secs = []

    secs.append({
        "title": "Raise candidates (budget-constrained winners)",
        "note": "Budget-lost IS over the flag and converting at/under target — raise ≤ +20% per step.",
        "headers": ["Campaign", "Budget-lost IS", f"Daily budget ({cur})", "CPA", f"+20% → ({cur})"],
        "aligns": ["l", "r", "r", "r", "r"],
        "rows": [[r["campaign"], _pct(r["budget_lost_is"]), _money(r["daily_budget"], ""),
                  _money(r["cpa"], ""), _money((r["daily_budget"] or 0) * 1.2, "")]
                 for r in _bucket(model, "Raise", "budget_lost_is")],
        "empty": "_None._",
    })

    secs.append({
        "title": "Kill candidates (3× rule)",
        "note": "Zero conversions and spend ≥ kill-multiple × target CPA — pause to stop the bleed.",
        "headers": ["Campaign", f"Spend ({cur})", "Conv", f"Daily budget ({cur})"],
        "aligns": ["l", "r", "r", "r"],
        "rows": [[r["campaign"], _money(r["cost"], ""), f"{r['conversions']:.0f}",
                  _money(r["daily_budget"], "")] for r in _bucket(model, "Kill")],
        "empty": "_None._",
    })

    secs.append({
        "title": "Rank-limited (do NOT add budget)",
        "note": "Losing impression share to rank, not budget — route to Quality Score / bidding.",
        "headers": ["Campaign", "Rank-lost IS", "CPA", f"Spend ({cur})"],
        "aligns": ["l", "r", "r", "r"],
        "rows": [[r["campaign"], _pct(r["rank_lost_is"]), _money(r["cpa"], ""), _money(r["cost"], "")]
                 for r in _bucket(model, "Rank-limited", "rank_lost_is")],
        "empty": "_None._",
    })

    floor = p["min_budget_multiple"] * p["target_cpa"]
    secs.append({
        "title": "Low daily budget (unstable Smart Bidding)",
        "note": f"Daily budget below {p['min_budget_multiple']:.0f}× target CPA "
                f"({_money(floor, cur)}) — too low for stable delivery.",
        "headers": ["Campaign", f"Daily budget ({cur})", f"Floor ({cur})", "CPA"],
        "aligns": ["l", "r", "r", "r"],
        "rows": [[r["campaign"], _money(r["daily_budget"], ""), _money(floor, ""), _money(r["cpa"], "")]
                 for r in _bucket(model, "Low budget", "daily_budget")],
        "empty": "_None._",
    })

    gs = model["goal_sensitivity"]
    if gs:
        secs.append({
            "title": "Pacing sensitivity (monthly goal)",
            "note": "Pace vs goal as the monthly goal scales around the current value.",
            "headers": [f"Monthly goal ({cur})", "Pace", "Verdict"],
            "aligns": ["l", "r", "l"],
            "rows": [[f"{r['monthly_goal']:,.2f}" + (" ← current" if r["is_current"] else ""),
                      _ratio(r["pace_ratio"]), r["verdict"]] for r in gs],
        })

    paced = [r for r in model["rows"] if r["status"] == "measured"]
    paced.sort(key=lambda r: r.get("pace_score") or 0, reverse=True)
    secs.append({
        "title": "Per-campaign pace pre-score",
        "note": "campaign_pace_ratio = MTD ÷ (daily budget × days elapsed) — how MTD spend "
                "compares to the campaign's own daily budget's implied pace. Confidence is "
                "\"high\" only with ≥7 days elapsed and MTD ≥ target CPA (analytics.signals + "
                "analytics.pre_score over PACE_FLAG_WEIGHTS).",
        "headers": ["Campaign", "Pace ratio", "Verdict", "Confidence", "Flags", "Score"],
        "aligns": ["l", "r", "l", "l", "l", "r"],
        "rows": [[r["campaign"],
                  "—" if r["campaign_pace_ratio"] is None else f"{r['campaign_pace_ratio']:.2f}x",
                  r["pace_verdict"], r["pace_confidence"], ", ".join(r["pace_flags"]) or "—",
                  f"{r['pace_score']:.2f}"] for r in paced],
        "empty": "_No measured campaigns._",
    })

    adv = model["advisor"]
    delta_trim = [r for r in adv["trim"] if r["source"] == "over_pace"]
    secs.append({
        "title": "Advisor — additional trim candidates (over-pacing, CPA above target)",
        "note": "Beyond the Kill (3× rule) list above: campaigns whose per-campaign pace pre-score "
                f"reads \"over\" AND whose CPA sits above target CPA ({_money(p['target_cpa'], cur)}).",
        "headers": ["Campaign", f"Spend ({cur})", "Conv", "Reason"],
        "aligns": ["l", "r", "r", "l"],
        "rows": [[r["campaign"], _money(r["cost"], ""), f"{r['conversions']:.0f}", r["reason"]]
                 for r in delta_trim],
        "empty": "_None._",
    })
    return secs


def md_rows(model):
    cur = model["provenance"]["currency"]
    headers = ["Campaign", "Channel", "Status", f"Daily budget ({cur})" if cur else "Daily budget",
               f"Spend ({cur})" if cur else "Spend", f"MTD ({cur})" if cur else "MTD", "Conv", "CPA",
               "Budget-lost IS", "Rank-lost IS", "Bucket"]
    out = []
    for r in model["rows"]:
        out.append([
            r["campaign"], r["channel"], r["status"].replace("_", " "),
            _money(r["daily_budget"], ""), f"{r['cost']:,.2f}", f"{r['mtd_spend']:,.2f}",
            f"{r['conversions']:.0f}", _money(r["cpa"], ""),
            _pct(r["budget_lost_is"]), _pct(r["rank_lost_is"]), r["bucket"] or "",
        ])
    return {
        "title": "All campaigns (every row, with status)",
        "note": "No row loss: every campaign appears here. Sorted by window spend (highest first).",
        "headers": headers,
        "aligns": ["l", "l", "l", "r", "r", "r", "r", "r", "r", "r", "l"],
        "rows": out,
        "empty": "_No campaigns._",
    }


# --------------------------------------------------------------------------
def html_embed(model):
    return {
        "provenance": model["provenance"],
        "params": model["params"],
        "summary": model["summary"],
        "rows": [{
            "campaign": r["campaign"], "channel": r["channel"], "status": r["status"],
            "daily_budget": r["daily_budget"], "cost": r["cost"], "mtd_spend": r["mtd_spend"],
            "conv": r["conversions"], "cpa": r["cpa"],
            "budget_lost_is": r["budget_lost_is"], "rank_lost_is": r["rank_lost_is"],
        } for r in model["rows"]],
    }


HTML_CONTROLS = [
    {"key": "monthly_goal", "label": "Monthly goal", "kind": "number"},
    {"key": "target_cpa", "label": "Target CPA", "kind": "number"},
    {"key": "budget_lost_is_flag", "label": "Budget/Rank-lost-IS flag", "kind": "slider",
     "min": 0.0, "max": 0.5, "step": 0.05, "sub": "constrained above this share"},
    {"key": "kill_multiple", "label": "Kill multiple (× target CPA)", "kind": "number"},
    {"key": "min_budget_multiple", "label": "Min budget multiple (× target CPA)", "kind": "number"},
    {"key": "pacing_tolerance", "label": "Pacing tolerance (± band)", "kind": "slider",
     "min": 0.0, "max": 0.5, "step": 0.05, "sub": "account AND per-campaign pace verdict"},
]

HTML_COLUMNS = [
    {"key": "campaign", "label": "Campaign"},
    {"key": "channel", "label": "Channel"},
    {"key": "status", "label": "Status", "fmt": "status"},
    {"key": "daily_budget", "label": "Daily budget", "num": True, "fmt": "money"},
    {"key": "cost", "label": "Spend", "num": True, "fmt": "money"},
    {"key": "mtd_spend", "label": "MTD", "num": True, "fmt": "money"},
    {"key": "conv", "label": "Conv", "num": True, "fmt": "num"},
    {"key": "cpa", "label": "CPA", "num": True, "fmt": "money"},
    {"key": "budget_lost_is", "label": "Budget-lost IS", "num": True, "fmt": "pct"},
    {"key": "rank_lost_is", "label": "Rank-lost IS", "num": True, "fmt": "pct"},
    {"key": "bucket", "label": "Bucket", "fmt": "block"},
]

HTML_KPIS = [
    {"label": "MTD spend", "key": "mtd_spend", "money": True},
    {"label": "Expected MTD", "key": "expected_mtd", "money": True},
    {"label": "Spend", "key": "spend", "money": True},
    {"label": "Raise", "key": "raise_", "cls": "b1"},
    {"label": "Kill", "key": "kill", "cls": "b2"},
    {"label": "Low budget", "key": "low_budget"},
    {"label": "Top-3 spend %", "key": "conc_top3_pct"},
    {"label": "Off-pace (high-conf)", "key": "off_pace_high_conf", "cls": "b2"},
]

# Mirrors budget_core.classify_row / summarize / pacing / add_pace / PACE_FLAG_WEIGHTS
# exactly (Node-vs-Python verified). Splices analytics.JS_MIRROR verbatim (per
# _shared/README.md's kernel-mirror contract) for gxConcentration/gxSignals/gxPreScore/
# gxRoundHalfUp, then layers the skill's own classify/pace/summarize on top.
JS_KERNEL = analytics.JS_MIRROR + r"""
classify = function(r,P){
  if(r.status!=="measured") return {block:""};
  const t=P.target_cpa;
  if(r.conv===0 && r.cost >= P.kill_multiple*t) return {block:"Kill"};
  if(r.budget_lost_is!==null && r.budget_lost_is > P.budget_lost_is_flag && r.conv>0 && r.cpa!==null && r.cpa<=t) return {block:"Raise"};
  if(r.rank_lost_is!==null && r.rank_lost_is > P.budget_lost_is_flag) return {block:"Rank-limited"};
  if(r.daily_budget!==null && r.daily_budget < P.min_budget_multiple*t) return {block:"Low budget"};
  return {block:"OK"};
};
function _r2(x){return Math.round(x*100)/100;}
// Mirrors budget_core.PACE_FLAG_WEIGHTS / _pace_rules verbatim. Rules key off "conv"
// (not "conversions") — the embedded row shape (html_embed) renames that field.
var PACE_FLAG_WEIGHTS={over_pace:1.0, under_pace:1.0, constrained:1.5, zero_conv:2.0};
function paceRules(P){
  return [
    {id:"over_pace", key:"campaign_pace_ratio", op:"gt", value:1.0+P.pacing_tolerance},
    {id:"under_pace", key:"campaign_pace_ratio", op:"lt", value:1.0-P.pacing_tolerance},
    {id:"constrained", key:"budget_lost_is", op:"gt", value:P.budget_lost_is_flag},
    {id:"zero_conv", key:"conv", op:"eq", value:0},
  ];
}
// Mirrors budget_core.add_pace exactly (per-row; recomputed live from r + P, same
// as classify() — never read from a pre-computed field on the embedded row).
pace = function(r,P){
  let ratio=null;
  if(r.daily_budget!==null && r.daily_budget>0 && P.days_elapsed){
    ratio=gxRoundHalfUp(r.mtd_spend/(r.daily_budget*P.days_elapsed),2);
  }
  const tol=P.pacing_tolerance;
  const verdict = ratio===null?"n/a":(ratio>1+tol?"over":(ratio<1-tol?"under":"on track"));
  const confidence = (P.days_elapsed>=7 && r.mtd_spend>=P.target_cpa)?"high":"low";
  const rr={campaign_pace_ratio:ratio, budget_lost_is:r.budget_lost_is, conv:r.conv};
  const flags=gxSignals([rr],paceRules(P))[0];
  const score=gxPreScore({flags:flags},PACE_FLAG_WEIGHTS);
  return {ratio, verdict, confidence, flags, score};
};
summarize = function(rows,P){
  let spend=0,conv=0,mtd=0,kill=0,raise_=0,rank=0,low=0,ok=0,nb=0,overPace=0,underPace=0,offPaceHC=0;
  rows.forEach(r=>{
    spend+=r.cost; conv+=r.conv; mtd+=r.mtd_spend;
    const pc=pace(r,P);
    if(pc.verdict==="over")overPace++; else if(pc.verdict==="under")underPace++;
    if((pc.verdict==="over"||pc.verdict==="under") && pc.confidence==="high") offPaceHC++;
    if(r.status==="no_budget"){nb++; return;}
    const b=classify(r,P).block;
    if(b==="Kill")kill++; else if(b==="Raise")raise_++; else if(b==="Rank-limited")rank++;
    else if(b==="Low budget")low++; else if(b==="OK")ok++;
  });
  let expected=null,ratio=null,verdict="n/a";
  if(P.monthly_goal && P.days_in_month){
    expected=P.monthly_goal*(P.days_elapsed/P.days_in_month);
    ratio=expected? mtd/expected : null;
    if(ratio!==null){const tol=P.pacing_tolerance;
      verdict = ratio>1+tol?"over":(ratio<1-tol?"under":"on track");}
  }
  const conc=gxConcentration(rows,"cost",3);
  return {campaigns:rows.length, spend:_r2(spend), conversions:_r2(conv),
    cpa:conv?_r2(spend/conv):null, kill, raise_, rank_limited:rank, low_budget:low, ok, no_budget:nb,
    mtd_spend:_r2(mtd), expected_mtd:expected===null?null:_r2(expected),
    pace_ratio:ratio===null?null:_r2(ratio), pace_verdict:verdict,
    conc_top_share:conc.top_share, conc_hhi:conc.hhi, conc_effective_n:conc.effective_n,
    conc_top3_pct:gxRoundHalfUp(conc.top_share*100,1),
    over_pace:overPace, under_pace:underPace, off_pace_high_conf:offPaceHC};
};
"""

JS_EXTRA = r"""
renderExtra = function(host,H){
  const s=summarize(MODEL.rows,P);
  const paceLine = s.pace_ratio===null? "—" : (Math.round(s.pace_ratio*100)+"% of expected");
  let h='<div class="card"><h2>Pacing</h2><div class="logic"><b>'+paceLine+'</b> · verdict: '+H.esc(s.pace_verdict)+
        ' · MTD '+H.money(s.mtd_spend)+(s.expected_mtd!==null?(' vs expected '+H.money(s.expected_mtd)):'')+
        ' · concentration: top-3 '+s.conc_top3_pct.toFixed(1)+'% · HHI '+s.conc_hhi.toFixed(1)+
        ' · off-pace (high-conf) '+s.off_pace_high_conf+'</div></div>';
  const raise_=MODEL.rows.filter(r=>classify(r,P).block==="Raise").sort((a,b)=>(b.budget_lost_is||0)-(a.budget_lost_is||0));
  h+='<div class="card"><h2>Advisor — fund (Raise, ≤ +20%/step)</h2>';
  if(!raise_.length){h+='<div class="note">None at the current settings.</div>';}
  else{h+='<table><thead><tr><th>Campaign</th><th class="num">Budget-lost IS</th><th class="num">Daily budget</th><th class="num">+20%</th></tr></thead><tbody>';
    raise_.forEach(r=>{h+=`<tr><td>${H.esc(r.campaign)}</td><td class="num">${(r.budget_lost_is*100).toFixed(1)}%</td><td class="num">${H.money(r.daily_budget)}</td><td class="num">${H.money(r.daily_budget*1.2)}</td></tr>`;});
    h+='</tbody></table>';}
  h+='</div>';
  const trim_=MODEL.rows.filter(r=>{
    const b=classify(r,P).block, pc=pace(r,P);
    return b==="Kill" || (pc.verdict==="over" && r.cpa!==null && r.cpa>P.target_cpa);
  }).sort((a,b)=>(b.cost||0)-(a.cost||0));
  h+='<div class="card"><h2>Advisor — trim (Kill / over-pacing above target CPA)</h2>';
  if(!trim_.length){h+='<div class="note">None at the current settings.</div>';}
  else{h+='<table><thead><tr><th>Campaign</th><th class="num">Spend</th><th>Bucket</th><th class="num">Pace score</th></tr></thead><tbody>';
    trim_.forEach(r=>{const b=classify(r,P).block||"over-pace", pc=pace(r,P);
      h+=`<tr><td>${H.esc(r.campaign)}</td><td class="num">${H.money(r.cost)}</td><td>${H.esc(b)}</td><td class="num">${pc.score.toFixed(2)}</td></tr>`;});
    h+='</tbody></table>';}
  h+='</div>';
  host.innerHTML=h;
};
"""


# --------------------------------------------------------------------------
# Charts — declared here, GENERATED by _shared/render/charts.py (never hand-
# authored). One declaration drives both paths: the static SVGs shipped with
# the md/widget (rendered by vl-convert at the model's default params) and the
# live explorer charts (vendored Vega-Lite re-deriving from the classify(r,P)-
# augmented rows on every control change). All aggregation lives in the
# Vega-Lite `transform` below — shared verbatim — and only uses fields present
# in BOTH row shapes (the chart_rows-adapted model rows and the html embed):
# campaign, status, cost, daily_budget, block. The kernel's classify returns
# `block` while the Python rows carry `bucket`, so CHART_ROWS mirrors the live
# augmentation by copying bucket -> block for the static render path.
# NOTE: the model has NO daily time series and no per-row day count, so an
# "average daily cost" chart cannot be derived honestly — the second chart is
# a top-12-by-window-spend bar (VL window rank + filter) colored by bucket,
# with the daily budget carried in the tooltip.
# --------------------------------------------------------------------------
# Bucket colors match the explorer badges (blockClass in _shared/render/html.py):
# Kill -> fix (red), Raise -> scale (green), Rank-limited -> b2 (purple),
# Low budget -> hold (slate), OK -> neutral grey, No budget -> nb (amber).
_BUCKET_DOMAIN = ["Kill", "Raise", "Rank-limited", "Low budget", "OK"]
_BUCKET_RANGE = ["#b91c1c", "#15803d", "#7c3aed", "#475569", "#cbd5e1"]


def chart_rows(model):
    """Static chart data: model rows with the live kernel's field name (`block`)
    mirrored from the Python `bucket`, so one transform serves both paths."""
    return [dict(r, block=r["bucket"]) for r in model["rows"]]


CHARTS = [
    {
        "id": "campaigns_by_bucket",
        "title": "Campaigns by action bucket",
        "mark": {"type": "bar"},
        "transform": [
            {"filter": "datum.block != ''"},
            {"aggregate": [{"op": "count", "as": "campaigns"},
                           {"op": "sum", "field": "cost", "as": "spend"}],
             "groupby": ["block"]},
        ],
        "encoding": {
            "y": {"field": "block", "type": "nominal", "title": None,
                  "scale": {"domain": _BUCKET_DOMAIN}},
            "x": {"field": "campaigns", "type": "quantitative", "title": "Campaigns",
                  "axis": {"tickMinStep": 1}},
            "color": {"field": "block", "type": "nominal", "legend": None,
                      "scale": {"domain": _BUCKET_DOMAIN, "range": _BUCKET_RANGE}},
            "tooltip": [{"field": "block", "title": "Bucket"},
                        {"field": "campaigns", "title": "Campaigns"},
                        {"field": "spend", "title": "Spend (window)", "format": ",.2f"}],
        },
        "height": 160,
        "md": True, "widget": True,
    },
    {
        "id": "top_spend_by_campaign",
        "title": "Top campaigns by window spend — colored by action bucket",
        "mark": {"type": "bar"},
        "transform": [
            {"window": [{"op": "rank", "as": "spend_rank"}],
             "sort": [{"field": "cost", "order": "descending"}]},
            {"filter": "datum.spend_rank <= 12"},
            {"calculate": "datum.block != '' ? datum.block : 'No budget'", "as": "action"},
        ],
        "encoding": {
            "y": {"field": "campaign", "type": "nominal", "title": None, "sort": "-x"},
            "x": {"field": "cost", "type": "quantitative", "title": "Spend (window)"},
            "color": {"field": "action", "type": "nominal", "title": None,
                      "scale": {"domain": _BUCKET_DOMAIN + ["No budget"],
                                "range": _BUCKET_RANGE + ["#b45309"]}},
            "tooltip": [{"field": "campaign", "title": "Campaign"},
                        {"field": "action", "title": "Bucket"},
                        {"field": "cost", "title": "Spend", "format": ",.2f"},
                        {"field": "daily_budget", "title": "Daily budget", "format": ",.2f"}],
        },
        "height": 260,
        "md": True, "widget": False,
    },
]


SPEC = {
    "slug_prefix": "budget-pacing",
    "row_noun": "campaigns",
    "title": "Budget & Pacing",
    "about": {
        "summary": "Prioritizes the next budget move per campaign and tracks month-to-date pace against your monthly goal. Set the Target CPA and Monthly goal; the impression-share-lost flag decides when a campaign counts as constrained, and the Kill / Min-budget multiples set the waste and Smart-Bidding stability floors. Also reads spend concentration (top-3 share / HHI / effective-N) across campaigns and a per-campaign pace pre-score (over/under-pace with confidence) that feeds the Advisor's fund/trim reallocation shortlist.",
        "legend": [
            {"label": "Raise", "desc": "Budget-constrained winner — converting at/under target CPA but losing impression share to budget. Scale ≤ +20% per step."},
            {"label": "Kill", "desc": "Zero conversions and spend ≥ (kill multiple × target CPA). Stop the spend."},
            {"label": "Rank-limited", "desc": "Losing impression share to rank, not budget — a bid/quality problem, so don't add budget."},
            {"label": "Low budget", "desc": "Daily budget below the Smart-Bidding stability floor (min multiple × target CPA)."},
            {"label": "OK", "desc": "None of the above — leave it alone."},
        ],
    },
    "methodology_ref": "references/budget-pacing-report.md",
    "window_labels": ("Window", "As of"),
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
