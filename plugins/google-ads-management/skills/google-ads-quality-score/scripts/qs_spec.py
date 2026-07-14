#!/usr/bin/env python3
"""Render spec for the Quality Score forensics report — adapts qs_core's model to
the shared render toolkit (_shared/render). Stdlib only.

The bucket math lives once in qs_core (Python) and is mirrored in `JS_KERNEL`
(browser) — the Node-vs-Python equality gate keeps them in sync.
"""
from __future__ import annotations

import analytics
import qs_core as core
from render import model as M  # noqa: E402  (source_label — HM-572 canonical "Data source" line)

_LABEL = core._RANK_LABEL


def _money(v, cur):
    return "—" if v is None else f"{float(v):,.2f}" + (f" {cur}" if cur else "")


def _qs(v):
    return "unscored" if v is None else str(v)


def md_params(model):
    p = model["params"]
    tgt = _LABEL.get(p["component_target"], str(p["component_target"]))
    src = model["provenance"].get("source")
    return [
        ("QS-low threshold", f"< {p['qs_low_threshold']}"),
        ("Component target", f"≥ {tgt} (below = bottleneck)"),
        ("Low-CTR pause", f"impr ≥ {p['pause_min_impr']} · CTR < {p['pause_max_ctr'] * 100:.1f}% · 0 conv"),
        ("Data source", M.source_label(src, csv_label="user-supplied CSV export")),
    ]


def md_kpis(model):
    s = model["summary"]
    cur = model["provenance"]["currency"]
    return [
        ("Keywords", f"{s['keywords']} ({s['scored']} scored, {s['unscored']} unscored)"),
        ("Average QS", "—" if s["avg_qs"] is None else f"{s['avg_qs']:.2f}"),
        ("Low-QS (in scope)", str(s["in_scope"])),
        ("By component", f"{s['lp']} LP · {s['ad_rel']} ad-rel · {s['exp_ctr']} exp-CTR · "
                         f"{s['critical']} critical · {s['other']} other"),
        ("Low-CTR pause candidates", str(s["pause_candidates"])),
        ("Spend on low-QS keywords", _money(s["wasted_low_qs_cost"], cur)),
    ]


def md_narrative(model):
    s = model["summary"]
    dom = model["dominant_factor"]
    lines = []
    if dom["dominant_component"]:
        conc = dom["concentration"]
        loc = dom["location"]
        where = (f" — {loc['top_share'] * 100:.1f}% of that sits in the top "
                 f"{loc['top_n']} ad group(s)" if loc.get("n") else "")
        lines.append(
            f"> **{dom['dominant_component']} is the dominant QS drag** — "
            f"{s['dominant_share_pct']:.1f}% of the "
            f"{_money(sum(d['cost'] for d in dom['drag']), model['provenance']['currency'])} "
            f"below-target spend sits in this one component (HHI {conc['hhi']:.1f}, effective "
            f"{conc['effective_n']:.2f} of 3 components){where}. Fix this lever first.")
    if s["critical"] > 0:
        lines.append(f"> **{s['critical']} keyword(s) with all three components below target** — the "
                     "worst QS drag. Rebuild the ad group (tighter theme, matching RSAs, better LP).")
    if s["pause_candidates"] > 0:
        lines.append(f"> **{s['pause_candidates']} low-CTR pause candidate(s)** (impressions but ~no "
                     "clicks, 0 conversions) — pausing them lifts Expected CTR with no lost value.")
    lines.append("> **Landing page experience is MANUAL.** A BELOW-AVERAGE landing-page component "
                 "points at the page, but Core Web Vitals / page speed are not in this MCP — confirm "
                 "in Search Console → Page Experience / PageSpeed (LCP > 2.5s, CLS > 0.1). Flag, don't fake.")
    return lines


def _bucket(model, b):
    rs = [r for r in model["rows"] if r.get("bucket") == b]
    rs.sort(key=lambda r: -r["cost"])
    return rs


def _kw_rows(rows):
    return [[r["keyword"], r["ad_group"], _qs(r["qs"]), _LABEL[r["lp"]], _LABEL[r["ar"]],
             _LABEL[r["ctr_q"]], f"{r['cost']:,.2f}"] for r in rows]


def _dominant_sections(model):
    """The dominant-QS-factor concentration — by component, then where the
    dominant component's drag concentrates across ad groups. Leads the
    section list (the advisor loop presents this finding first)."""
    cur = model["provenance"]["currency"]
    dom = model["dominant_factor"]
    conc, loc = dom["concentration"], dom["location"]
    secs = [{
        "title": "Dominant QS-factor concentration — by component",
        "note": (f"Below-target cost attributable to each component (a Critical keyword counts "
                 f"toward all three). Dominant: **{dom['dominant_component'] or '—'}** "
                 f"(top-1 share {conc['top_share'] * 100:.1f}% · HHI {conc['hhi']:.1f} · "
                 f"effective {conc['effective_n']:.2f} of 3)."),
        "headers": ["Component", f"Below-target cost ({cur})", "Keywords", "Share", "Worst factor?"],
        "aligns": ["l", "r", "r", "r", "l"],
        "rows": [[d["component"], f"{d['cost']:,.2f}", d["keywords"], f"{d['share'] * 100:.1f}%",
                  "worst" if "worst_factor" in d["flags"] else ""] for d in dom["drag"]],
        "empty": "_None._",
    }]
    if dom["dominant_component"]:
        secs.append({
            "title": f"Where {dom['dominant_component']} concentrates (by ad group)",
            "note": (f"Ad groups carrying the {dom['dominant_component']}-driven below-target cost "
                     f"(top-{loc['top_n']} share {loc['top_share'] * 100:.1f}% · HHI {loc['hhi']:.1f})."),
            "headers": ["Ad group", f"Cost ({cur})", "Keywords",
                       f"Share of {dom['dominant_component']} cost"],
            "aligns": ["l", "r", "r", "r"],
            "rows": [[r["ad_group"], f"{r['cost']:,.2f}", r["keywords"],
                      f"{(r['cost'] / dom['dominant_cost'] * 100 if dom['dominant_cost'] else 0):.1f}%"]
                     for r in dom["location_rows"]],
            "empty": "_None._",
        })
    return secs


def md_sections(model):
    cur = model["provenance"]["currency"]
    hdr = ["Keyword", "Ad group", "QS", "Landing page", "Ad relevance", "Expected CTR", f"Cost ({cur})"]
    al = ["l", "l", "r", "l", "l", "l", "r"]
    secs = list(_dominant_sections(model))
    for b, title, note in [
        ("Critical", "Critical — all three components below target",
         "Rebuild the ad group: tighter theme, RSAs that echo the keywords, and a better landing page."),
        ("Expected CTR", "Expected CTR is the bottleneck",
         "Tighten match types / intent, pause low-CTR keywords, and rewrite RSAs for relevance."),
        ("Ad relevance", "Ad relevance is the bottleneck",
         "Make headlines contain the ad group's exact keyword phrases; split broad ad groups."),
        ("Landing page", "Landing page experience is the bottleneck (MANUAL to confirm)",
         "Check page speed / Core Web Vitals (not in MCP) and message-match the landing page."),
        ("Other", "Low QS, no single component below target",
         "QS is low but the triad is at/above target — watch; often resolves with volume."),
    ]:
        secs.append({"title": title, "note": note, "headers": hdr, "aligns": al,
                     "rows": _kw_rows(_bucket(model, b)), "empty": "_None._"})

    pause = [r for r in model["rows"] if r.get("pause")]
    pause.sort(key=lambda r: -r["impressions"])
    secs.append({
        "title": "Low-CTR pause candidates",
        "note": "Impressions but ~no clicks and 0 conversions — pause to lift Expected CTR.",
        "headers": ["Keyword", "Ad group", "QS", "Impr", "CTR", f"Cost ({cur})"],
        "aligns": ["l", "l", "r", "r", "r", "r"],
        "rows": [[r["keyword"], r["ad_group"], _qs(r["qs"]), int(r["impressions"]),
                  f"{r['ctr'] * 100:.2f}%", f"{r['cost']:,.2f}"] for r in pause],
        "empty": "_None._",
    })

    secs.append({
        "title": "QS-threshold sensitivity",
        "note": "In-scope and Critical counts as the QS-low threshold changes.",
        "headers": ["QS-low threshold", "In scope", "Critical"],
        "aligns": ["l", "r", "r"],
        "rows": [[f"< {r['qs_low']}" + (" ← current" if r["is_current"] else ""),
                  r["in_scope"], r["critical"]] for r in model["threshold_sensitivity"]],
    })
    return secs


def md_rows(model):
    cur = model["provenance"]["currency"]
    headers = ["Keyword", "Ad group", "Match", "Status", "QS", "Landing page", "Ad relevance",
               "Expected CTR", "Impr", "CTR", f"Cost ({cur})" if cur else "Cost", "Conv", "Bucket", "Pause?"]
    out = []
    for r in model["rows"]:
        out.append([
            r["keyword"], r["ad_group"], r["match_type"], r["status"], _qs(r["qs"]),
            _LABEL[r["lp"]], _LABEL[r["ar"]], _LABEL[r["ctr_q"]],
            int(r["impressions"]) if float(r["impressions"]).is_integer() else round(r["impressions"], 2),
            f"{r['ctr'] * 100:.2f}%", f"{r['cost']:,.2f}", f"{r['conversions']:.1f}",
            r["bucket"] or "", "pause" if r.get("pause") else "",
        ])
    return {
        "title": "All keywords (every row, with status)",
        "note": "No row loss: every keyword appears here. Unscored keywords (too little data) are "
                "kept separate, never averaged in. Sorted by QS (lowest first).",
        "headers": headers,
        "aligns": ["l", "l", "l", "l", "r", "l", "l", "l", "r", "r", "r", "r", "l", "l"],
        "rows": out,
        "empty": "_No keywords._",
    }


# --------------------------------------------------------------------------
def html_embed(model):
    return {
        "provenance": model["provenance"],
        "params": model["params"],
        "summary": model["summary"],
        "target_options": model["target_options"],
        "rows": [{
            "keyword": r["keyword"], "ad_group": r["ad_group"], "ad_group_id": r["ad_group_id"],
            "mt": r["match_type"],
            "status": r["status"], "qs": r["qs"], "lp": r["lp"], "ar": r["ar"], "ctr_q": r["ctr_q"],
            "lp_l": _LABEL[r["lp"]], "ar_l": _LABEL[r["ar"]], "ctr_l": _LABEL[r["ctr_q"]],
            "impr": r["impressions"], "ctr": r["ctr"], "cost": r["cost"], "conv": r["conversions"],
        } for r in model["rows"]],
    }


HTML_CONTROLS = [
    {"key": "qs_low_threshold", "label": "QS-low threshold (<)", "kind": "slider",
     "min": 2, "max": 8, "step": 1, "sub": "keywords below this QS are in scope"},
    {"key": "component_target", "label": "Component target", "kind": "select",
     "options": core.TARGET_OPTIONS, "sub": "a component below this rating is the bottleneck"},
    {"key": "pause_min_impr", "label": "Pause · min impressions", "kind": "number"},
    {"key": "pause_max_ctr", "label": "Pause · max CTR (e.g. 0.01)", "kind": "number"},
]

HTML_COLUMNS = [
    {"key": "keyword", "label": "Keyword"},
    {"key": "ad_group", "label": "Ad group"},
    {"key": "status", "label": "Status", "fmt": "status"},
    {"key": "qs", "label": "QS", "num": True, "fmt": "num"},
    {"key": "lp_l", "label": "Landing page"},
    {"key": "ar_l", "label": "Ad relevance"},
    {"key": "ctr_l", "label": "Expected CTR"},
    {"key": "impr", "label": "Impr", "num": True, "fmt": "int"},
    {"key": "ctr", "label": "CTR", "num": True, "fmt": "pct"},
    {"key": "cost", "label": "Cost", "num": True, "fmt": "money"},
    {"key": "bucket", "label": "Bucket", "fmt": "block"},
]

HTML_KPIS = [
    {"label": "Scored", "key": "scored"},
    {"label": "Avg QS", "key": "avg_qs"},
    {"label": "In scope", "key": "in_scope"},
    {"label": "Critical", "key": "critical", "cls": "b2"},
    {"label": "Pause cand.", "key": "pause_candidates", "cls": "b1"},
    {"label": "Unscored", "key": "unscored"},
    {"label": "Dominant factor", "key": "dominant_component"},
    {"label": "Dominant share", "key": "dominant_share_pct", "cls": "b2"},
    {"label": "Dominant location share", "key": "dominant_location_share_pct"},
]

# Mirrors qs_core.classify_row / summarize / component_drag / dominant_factor
# exactly (Node-vs-Python verified). analytics.JS_MIRROR provides gxConcentration
# / gxSignals / gxRoundHalfUp — the same shared primitives qs_core.dominant_factor
# calls, spliced in verbatim rather than re-implemented here.
JS_KERNEL = analytics.JS_MIRROR + r"""
const _COMP=[["lp","Landing page"],["ar","Ad relevance"],["ctr_q","Expected CTR"]];
const _COMP_ORDER={"Landing page":0,"Ad relevance":1,"Expected CTR":2};
const _COMP_KEY={"Landing page":"lp","Ad relevance":"ar","Expected CTR":"ctr_q"};
function _belows(r,t){return _COMP.filter(([k])=>r[k]>0 && r[k]<t).map(([,n])=>n);}
classify = function(r,P){
  const pause = (r.status==="scored" && r.impr>=P.pause_min_impr && r.ctr<P.pause_max_ctr && r.conv===0);
  if(r.status!=="scored" || r.qs>=P.qs_low_threshold) return {block:"", pause};
  const belows=_belows(r,P.component_target);
  if(!belows.length) return {block:"Other", pause};
  if(belows.length===3) return {block:"Critical", pause};
  const ranks={"Landing page":r.lp,"Ad relevance":r.ar,"Expected CTR":r.ctr_q};
  const order={"Landing page":0,"Ad relevance":1,"Expected CTR":2};
  let primary=belows[0];
  belows.forEach(n=>{ if(ranks[n]<ranks[primary] || (ranks[n]===ranks[primary] && order[n]<order[primary])) primary=n; });
  return {block:primary, pause};
};
function componentDrag(rows,P){
  const totals={"Landing page":{component:"Landing page",cost:0,keywords:0},
                "Ad relevance":{component:"Ad relevance",cost:0,keywords:0},
                "Expected CTR":{component:"Expected CTR",cost:0,keywords:0}};
  rows.forEach(r=>{
    if(r.status!=="scored"||r.qs>=P.qs_low_threshold) return;
    _belows(r,P.component_target).forEach(name=>{ totals[name].cost+=r.cost; totals[name].keywords++; });
  });
  return [totals["Landing page"],totals["Ad relevance"],totals["Expected CTR"]];
}
function flagWorst(drag){
  const total=drag.reduce((a,d)=>a+d.cost,0);
  const maxCost=drag.reduce((m,d)=>Math.max(m,d.cost),0);
  const rows=drag.map(d=>Object.assign({},d,
    {share: total>0?gxRoundHalfUp(d.cost/total,2):0, max_cost:maxCost}));
  const flags=gxSignals(rows,[{id:"worst_factor",key:"cost",op:"ge",value_key:"max_cost"}]);
  rows.forEach((d,i)=>{ d.flags=flags[i]; });
  return rows;
}
function dominantFactor(rows,P){
  const drag=flagWorst(componentDrag(rows,P));
  const conc=gxConcentration(drag,"cost",1);
  const flagged=drag.filter(d=>d.flags.includes("worst_factor") && d.cost>0);
  let dominantName="";
  flagged.forEach(d=>{ if(dominantName===""||_COMP_ORDER[d.component]<_COMP_ORDER[dominantName]) dominantName=d.component; });
  const domKey=_COMP_KEY[dominantName];
  const byAg={}, agOrder=[];
  if(domKey){
    rows.forEach(r=>{
      if(r.status!=="scored"||r.qs>=P.qs_low_threshold) return;
      if(!(r[domKey]>0 && r[domKey]<P.component_target)) return;
      const key=r.ad_group_id;
      if(!(key in byAg)){ byAg[key]={ad_group:r.ad_group,cost:0,keywords:0}; agOrder.push(key); }
      byAg[key].cost+=r.cost; byAg[key].keywords++;
    });
  }
  const locRows=agOrder.map(k=>byAg[k]).sort((a,b)=>b.cost-a.cost);
  const loc=gxConcentration(locRows,"cost",3);
  const domRow=drag.find(d=>d.component===dominantName);
  return {drag, dominant_component:dominantName, dominant_cost:domRow?domRow.cost:0,
          concentration:conc, location:loc, location_rows:locRows};
}
function _r2(x){return Math.round(x*100)/100;}
summarize = function(rows,P){
  const B={"Landing page":0,"Ad relevance":0,"Expected CTR":0,"Critical":0,"Other":0};
  let scored=0,unscored=0,inscope=0,qsum=0,pause=0,wasted=0;
  rows.forEach(r=>{
    if(r.status==="scored"){scored++; qsum+=r.qs; if(r.qs<P.qs_low_threshold){inscope++; wasted+=r.cost;}}
    else unscored++;
    const c=classify(r,P);
    if(c.block in B) B[c.block]++;
    if(c.pause) pause++;
  });
  const dom=dominantFactor(rows,P);
  return {keywords:rows.length, scored, unscored, in_scope:inscope,
    avg_qs:scored?_r2(qsum/scored):null,
    lp:B["Landing page"], ad_rel:B["Ad relevance"], exp_ctr:B["Expected CTR"],
    critical:B["Critical"], other:B["Other"], pause_candidates:pause, wasted_low_qs_cost:_r2(wasted),
    dominant_component:dom.dominant_component,
    dominant_share_pct:gxRoundHalfUp(dom.concentration.top_share*100,2),
    dominant_location_share_pct:gxRoundHalfUp(dom.location.top_share*100,2)};
};
"""

JS_EXTRA = r"""
renderExtra = function(host,H){
  function sens(){
    const saved=P.qs_low_threshold,out=[];
    for(let t=2;t<=8;t++){P.qs_low_threshold=t; const s=summarize(MODEL.rows,P);
      out.push({t,inscope:s.in_scope,crit:s.critical,cur:t===saved});}
    P.qs_low_threshold=saved; return out;
  }
  const dom=dominantFactor(MODEL.rows,P);
  const dataSource=(MODEL.provenance&&MODEL.provenance.source)||"mcp";
  const srcLabel=dataSource==="user_csv"?"user-supplied CSV export":"Google Ads API (live pull)";
  let h='<div class="card"><h2>Dominant QS factor</h2>';
  if(!dom.dominant_component){
    h+='<div class="note">No component is below target at the current thresholds — clean.</div>';
  } else {
    h+=`<div class="logic"><b>${H.esc(dom.dominant_component)}</b> is the dominant QS drag — `+
       `${(dom.concentration.top_share*100).toFixed(1)}% of below-target spend (HHI ${dom.concentration.hhi.toFixed(1)}, `+
       `effective ${dom.concentration.effective_n.toFixed(2)} of 3 components). `+
       (dom.location_rows.length?`Concentrates ${(dom.location.top_share*100).toFixed(1)}% in the top ${dom.location.top_n} ad group(s).`:"")+
       '</div>';
    h+='<table><thead><tr><th>Component</th><th class="num">Cost</th><th class="num">Keywords</th><th class="num">Share</th></tr></thead><tbody>'+
       dom.drag.map(d=>`<tr><td>${H.esc(d.component)}${d.flags.includes("worst_factor")?" ★":""}</td><td class="num">${H.money(d.cost)}</td><td class="num">${H.fmtN(d.keywords)}</td><td class="num">${(d.share*100).toFixed(1)}%</td></tr>`).join("")+
       '</tbody></table>';
  }
  h+=`<div class="note">Data source: ${H.esc(srcLabel)}</div></div>`;
  h+='<div class="card"><h2>Landing page experience is manual</h2>'+
        '<div class="logic">A BELOW-AVERAGE landing-page component is a pointer, not proof — Core Web Vitals / page speed are not in this MCP. Confirm in Search Console → Page Experience / PageSpeed (LCP &gt; 2.5s, CLS &gt; 0.1).</div></div>';
  const pause=MODEL.rows.filter(r=>classify(r,P).pause).sort((a,b)=>(b.impr||0)-(a.impr||0));
  h+='<div class="card"><h2>Low-CTR pause candidates</h2>';
  if(!pause.length){h+='<div class="note">None at the current thresholds.</div>';}
  else{h+='<table><thead><tr><th>Keyword</th><th>Ad group</th><th class="num">Impr</th><th class="num">CTR</th></tr></thead><tbody>';
    pause.slice(0,20).forEach(r=>{h+=`<tr><td>${H.esc(r.keyword)}</td><td>${H.esc(r.ad_group)}</td><td class="num">${H.fmtN(r.impr)}</td><td class="num">${(r.ctr*100).toFixed(2)}%</td></tr>`;});
    h+='</tbody></table>';}
  h+='</div><div class="card sens"><h2>QS-threshold sensitivity</h2>'+
     '<table><thead><tr><th>QS &lt;</th><th class="num">In scope</th><th class="num">Critical</th></tr></thead><tbody>'+
     sens().map(r=>`<tr><td class="${r.cur?'cur':''}">${r.t}${r.cur?' ← current':''}</td><td class="num ${r.cur?'cur':''}">${r.inscope}</td><td class="num">${r.crit}</td></tr>`).join("")+
     '</tbody></table></div>';
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
# qs, status, cost, block. The kernel's classify returns `block` while the
# Python rows carry `bucket`, so CHART_ROWS mirrors the live augmentation by
# copying bucket -> block for the static render path.
# --------------------------------------------------------------------------
# Bucket colors match the explorer badges (blockClass in _shared/render/html.py):
# Critical/Landing page -> fix (red), Ad relevance -> b2 (purple),
# Expected CTR -> hold (slate), Other -> neutral grey.
_BUCKET_DOMAIN = ["Critical", "Landing page", "Ad relevance", "Expected CTR", "Other"]
_BUCKET_COLORS = {"domain": _BUCKET_DOMAIN,
                  "range": ["#b91c1c", "#b91c1c", "#7c3aed", "#475569", "#cbd5e1"]}


def chart_rows(model):
    """Static chart data: model rows with the live kernel's field name (`block`)
    mirrored from the Python `bucket`, so one transform serves both paths."""
    return [dict(r, block=r["bucket"]) for r in model["rows"]]


CHARTS = [
    {
        "id": "spend_by_bucket",
        "title": "Spend on low-QS keywords by bottleneck bucket",
        "mark": {"type": "bar"},
        "transform": [
            {"filter": "datum.block != ''"},
            {"aggregate": [{"op": "sum", "field": "cost", "as": "spend"},
                           {"op": "count", "as": "keywords"}],
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
                        {"field": "keywords", "title": "Keywords"}],
        },
        "height": 160,
        "md": True, "widget": True,
    },
    {
        "id": "qs_distribution",
        "title": "Quality Score distribution (scored keywords)",
        "mark": {"type": "bar"},
        "transform": [
            {"filter": "datum.status == 'scored'"},
            {"aggregate": [{"op": "count", "as": "keywords"}], "groupby": ["qs"]},
        ],
        "encoding": {
            "x": {"field": "qs", "type": "ordinal", "title": "Quality Score (1–10)",
                  "scale": {"domain": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]}},
            "y": {"field": "keywords", "type": "quantitative", "title": "Keywords",
                  "axis": {"tickMinStep": 1}},
            "tooltip": [{"field": "qs", "title": "QS"},
                        {"field": "keywords", "title": "Keywords"}],
        },
        "height": 220,
        "md": True, "widget": False,
    },
]


SPEC = {
    "slug_prefix": "quality-score",
    "row_noun": "keywords",
    "title": "Quality Score Forensics",
    "about": {
        "summary": "Sorts low-Quality-Score keywords by which of the three QS components is dragging the score down, so you fix the right lever. The QS threshold sets which keywords count as 'low'; the Component target sets how weak a component must rate to be the bottleneck. The pause settings flag low-CTR, zero-conversion keywords to cut.",
        "legend": [
            {"label": "Expected CTR", "desc": "Expected CTR is the weakest component below target — the ad isn't earning clicks for its position."},
            {"label": "Ad relevance", "desc": "Ad relevance is the weakest — ad copy doesn't match the keyword closely enough."},
            {"label": "Landing page", "desc": "Landing-page experience is the weakest — the page is the bottleneck."},
            {"label": "Critical", "desc": "All three components rate below the target — rebuild the keyword, ad, and page."},
            {"label": "Other", "desc": "Low QS but no single component stands out below the target."},
        ],
    },
    "methodology_ref": "references/quality-score-report.md",
    "window_labels": ("Window", "Scope"),
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
