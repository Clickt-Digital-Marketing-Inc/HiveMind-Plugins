#!/usr/bin/env python3
"""Render spec for the search-term waste filter — adapts waste_filter_core's
model to the shared render toolkit (_shared/render). Stdlib only.

The classification math lives once in waste_filter_core (Python) and is mirrored
in `JS_KERNEL` (browser) — the Node-vs-Python equality gate keeps them in sync.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parents[2]
if str(PLUGIN_ROOT / "_shared") not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT / "_shared"))

import analytics  # noqa: E402  (JS_MIRROR spliced into JS_KERNEL below)
import waste_filter_core as core  # noqa: E402
from render import model as M  # noqa: E402  (source_label — HM-572 canonical "Data source" line)


def _money(v, cur):
    return f"{float(v):,.2f}" + (f" {cur}" if cur else "")


# --------------------------------------------------------------------------
# Markdown adapters
# --------------------------------------------------------------------------
# Honest data-source label — every format (md, html, xlsx) surfaces this per
# the dual-input contract (google-ads-foundation/references/artifact-formats.md
# "Honesty" — CSV-sourced findings must never be presented as an API pull).
# The live-pull entry is the canonical HM-572 token/label (_shared/render/model.py);
# kept as a local dict (rather than inlining M.source_label everywhere) because
# waste_filter_xlsx_spec.py also looks up SOURCE_LABELS directly by key.
SOURCE_LABELS = {
    M.LIVE_PULL_SOURCE: M.LIVE_PULL_LABEL,
    "user_csv": "User-supplied CSV export (Google Ads UI)",
}


def md_params(model):
    p = model["params"]
    src = model["provenance"].get("source", M.LIVE_PULL_SOURCE)
    return [
        ("Thresholds", f"CTR factor {p['ctr_factor']:.2f} · cost multiple {p['cost_multiple']:.2f} · "
            f"B1 max conv90 {p['block1_max_conv_90d']} · B2 min conv90 {p['block2_min_conv_90d']} · "
            f"B2 max conv30 {p['block2_max_conv_30d']}"),
        ("Match types in scope", f"{', '.join(p['match_types_in_scope'])} (Exact excluded at source)"),
        ("Data source", SOURCE_LABELS.get(src, src)),
    ]


def md_kpis(model):
    s = model["summary"]
    cur = model["provenance"]["currency"]
    return [
        ("Block 1 (never-converted waste)", str(s["block1"])),
        ("Block 2 (decaying converters)", str(s["block2"])),
        ("Wasted spend of qualifying", _money(s["wasted"], cur)),
        ("Universe", f"{s['universe']} loose-match terms ({s['scored']} scored, "
            f"{s['no_benchmark']} no-benchmark)"),
    ]


def md_narrative(model):
    if model["summary"]["total"] != 0:
        return []
    return [
        "> **0 / 0 is a clean result, not an error.** Under the rule as written, no loose-match "
        "term out-spends 2.5× its campaign's cost/conversion while *also* under-indexing on CTR. "
        "The sensitivity table below shows where qualifiers would start to appear if the cost "
        "multiple were relaxed, and the near-miss lists show the terms closest to the bar.",
    ]


def md_sections(model):
    cur = model["provenance"]["currency"]
    secs = []

    secs.append({
        "title": "Threshold sensitivity",
        "note": "How many terms qualify as the cost multiple changes (all other conditions held at "
                "current values).",
        "headers": ["Cost multiple", "Block 1", "Block 2", "Total"],
        "aligns": ["l", "r", "r", "r"],
        "rows": [[f"{r['cost_multiple']:.2f}" + (" ← current" if r["is_current"] else ""),
                  r["block1"], r["block2"], r["total"]] for r in model["sensitivity"]],
    })

    for blk, key in (("Block 1", "near_misses_block1"), ("Block 2", "near_misses_block2")):
        nm = model[key][:15]
        secs.append({
            "title": f"Near misses — {blk}",
            "note": "Terms meeting every condition except (possibly) the cost bar, ranked by closeness.",
            "headers": [f"Search term", "Campaign", f"Cost ({cur})", "Campaign cost/conv",
                        "Qualifies if cost-multiple ≤", "Now?"],
            "aligns": ["l", "l", "r", "r", "r", "l"],
            "rows": [[r["term"], r["campaign"], f"{r['cost']:,.2f}", f"{r['camp_cpa']:,.2f}",
                      f"{r['qualify_if_cost_multiple_le']:.2f}",
                      "yes" if r["currently_qualifies"] else "no"] for r in nm],
            "empty": "_None._",
        })

    ng = model["ngrams"]
    conc = ng["concentration"]
    secs.append({
        "title": "Top wasteful n-grams",
        "note": (f"Unigrams + adjacent bigrams from Block 1/2 term text, ranked by total wasted "
                 f"spend across occurrences (a term contributes to several n-grams; a token's "
                 f"cost sums every qualifying term that carries it). Top {min(5, conc['n'])} "
                 f"n-grams carry {conc['top_share'] * 100:.1f}% of the n-gram-weighted waste "
                 f"(HHI {conc['hhi']:.1f}, effective N {conc['effective_n']:.2f})."),
        "headers": ["N-gram", f"Wasted spend ({cur})" if cur else "Wasted spend", "Terms"],
        "aligns": ["l", "r", "r"],
        "rows": [[g["ngram"], f"{g['cost']:,.2f}", g["terms"]] for g in ng["top"]],
        "empty": "_None — no term currently qualifies as waste._",
    })

    nb = [r for r in model["rows"] if r["status"] == "no_benchmark"]
    by_camp = {}
    for r in nb:
        by_camp[r["campaign"]] = by_camp.get(r["campaign"], 0) + 1
    secs.append({
        "title": "Excluded — campaigns with no usable benchmark",
        "note": ("These campaigns had 0 conversions (90d), so cost/conversion is undefined and their "
                 "terms cannot be scored. Listed here so nothing is silently dropped."),
        "headers": ["Campaign", "Terms held out"],
        "aligns": ["l", "r"],
        "rows": [[camp, n] for camp, n in sorted(by_camp.items(), key=lambda kv: -kv[1])],
        "empty": "_None — every term's campaign had conversions in the 90-day window._",
    })
    return secs


def md_rows(model):
    """Every loose-match term with a status — the no-row-loss layer for the md
    (the CSV used to carry this; the bundle is md+html+xlsx only now)."""
    cur = model["provenance"]["currency"]
    headers = ["Search term", "Campaign", "Ad group", "Match", "Status", "Impr", "Clicks",
               "CTR", f"Cost ({cur})" if cur else "Cost", "Conv 90d", "Conv 30d", "Block"]
    out = []
    for r in model["rows"]:
        out.append([
            r["term"], r["campaign"], r["ad_group"], r["match_type"],
            "scored" if r["status"] == "scored" else "no benchmark",
            int(r["impressions"]) if float(r["impressions"]).is_integer() else round(r["impressions"], 2),
            int(r["clicks"]) if float(r["clicks"]).is_integer() else round(r["clicks"], 2),
            f"{r['ctr'] * 100:.2f}%", f"{r['cost']:,.2f}",
            f"{r['conv90']:.2f}", f"{r['conv30']:.2f}", r["block"] or "",
        ])
    return {
        "title": "All loose-match terms (every row, with status)",
        "note": "No row loss: every term in the universe appears here, scored or held out as "
                "no-benchmark. Sorted by cost (highest first).",
        "headers": headers,
        "aligns": ["l", "l", "l", "l", "l", "r", "r", "r", "r", "r", "r", "l"],
        "rows": out,
        "empty": "_No terms in the universe._",
    }


# --------------------------------------------------------------------------
# HTML adapters
# --------------------------------------------------------------------------
def in_play(r, params=None):
    """Reachable envelope for the in-Claude tuner's embed (widget_emit applies this).

    Only a scored row whose CTR is below `cap × camp_ctr` can EVER be a Block 1/2
    flag, appear in a near-miss list, or move the sensitivity ladder — every one of
    those paths requires `ctr < ctr_factor × camp_ctr`. The cap is the LOOSER of the
    slider's max (1.0) and the model's starting `ctr_factor`: the slider only lets
    the operator *lower* ctr_factor (max 1.0), so `max(1.0, ctr_factor)` bounds every
    reachable state even if a findings JSON starts ctr_factor above 1.0. Match-type is
    deliberately NOT filtered (the match-types control can re-add a type); the
    param-independent counts (universe/scored/no_benchmark) come from the embedded
    full-model summary. The full universe still flows to md/html/xlsx via build_bundle,
    untouched — this only sizes the widget embed.
    """
    if r.get("status") != "scored" or not r.get("camp_ctr"):
        return False
    try:
        cap = max(1.0, float((params or {}).get("ctr_factor", 1.0) or 1.0))
    except (TypeError, ValueError):
        cap = 1.0
    return r["ctr"] < cap * r["camp_ctr"]


def html_embed(model):
    return {
        "provenance": model["provenance"],
        "params": model["params"],
        "summary": model["summary"],
        "match_types": model["match_types"],
        "cost_ladder": model["cost_ladder"],
        "rows": [{
            "campaign": r["campaign"], "ad_group": r["ad_group"], "term": r["term"],
            "mt": r["match_type"], "impr": r["impressions"], "clicks": r["clicks"],
            "ctr": r["ctr"], "cost": r["cost"], "conv90": r["conv90"], "conv30": r["conv30"],
            "camp_ctr": r["camp_ctr"], "camp_cpa": r["camp_cpa"], "status": r["status"],
        } for r in model["rows"]],
    }


HTML_CONTROLS = [
    {"key": "ctr_factor", "label": "CTR threshold factor", "kind": "slider",
     "min": 0.05, "max": 1, "step": 0.05, "sub": "× campaign CTR"},
    {"key": "cost_multiple", "label": "Cost multiple", "kind": "slider",
     "min": 0.25, "max": 3, "step": 0.25, "sub": "× campaign cost/conv"},
    {"key": "block1_max_conv_90d", "label": "Block 1 · max conv (90d)", "kind": "number"},
    {"key": "block2_min_conv_90d", "label": "Block 2 · min conv (90d)", "kind": "number"},
    {"key": "block2_max_conv_30d", "label": "Block 2 · max conv (30d)", "kind": "number"},
    {"key": "match_types_in_scope", "label": "Match types", "kind": "multi",
     "param_key": "match_types_in_scope",
     "options": [[lbl, en] for lbl, en in core.MATCH_TYPES]},
]

HTML_COLUMNS = [
    {"key": "term", "label": "Search term"},
    {"key": "campaign", "label": "Campaign"},
    {"key": "mt", "label": "Match"},
    {"key": "status", "label": "Status", "fmt": "status"},
    {"key": "impr", "label": "Impr", "num": True, "fmt": "int"},
    {"key": "clicks", "label": "Clicks", "num": True, "fmt": "int"},
    {"key": "ctr", "label": "CTR", "num": True, "fmt": "pct"},
    {"key": "cost", "label": "Cost", "num": True, "fmt": "money"},
    {"key": "conv90", "label": "Conv90", "num": True, "fmt": "num"},
    {"key": "conv30", "label": "Conv30", "num": True, "fmt": "num"},
    {"key": "block", "label": "Block", "fmt": "block"},
]

HTML_KPIS = [
    {"label": "Block 1", "key": "b1", "cls": "b1"},
    {"label": "Block 2", "key": "b2", "cls": "b2"},
    {"label": "Total", "key": "total"},
    {"label": "Wasted spend", "key": "wasted", "money": True},
    {"label": "No benchmark", "key": "no_benchmark"},
]

# Mirrors waste_filter_core.classify_row / summarize / term_ngrams /
# waste_ngrams exactly. `analytics.JS_MIRROR` (gxConcentration/gxRoundHalfUp/
# etc — HM-532) is spliced in verbatim first since gxWasteNgrams below calls
# gxConcentration; the shared analytics-primitives parity gate covers that
# part, and this skill's own tests/ngram_js_parity.mjs covers term_ngrams /
# waste_ngrams against waste_filter_core's Python (both default + tuned).
JS_KERNEL = analytics.JS_MIRROR + r"""
classify = function(r,P){
  if(r.status!=="scored") return {block:"", in_scope:null, ctr_pass:null, cost_pass:null};
  const scope=new Set(P.match_types_in_scope);
  const in_scope=scope.has(r.mt);
  const ctr_pass=r.ctr < P.ctr_factor*r.camp_ctr;
  const cost_pass=r.cost > P.cost_multiple*r.camp_cpa;
  let block="";
  if(in_scope && ctr_pass && cost_pass){
    if(r.conv90 <= P.block1_max_conv_90d) block="Block 1";
    else if(r.conv90 > P.block2_min_conv_90d && r.conv30 <= P.block2_max_conv_30d) block="Block 2";
  }
  return {block,in_scope,ctr_pass,cost_pass};
};
summarize = function(rows,P){
  let b1=0,b2=0,wasted=0;
  rows.forEach(r=>{const c=classify(r,P);
    if(c.block==="Block 1"){b1++;wasted+=r.cost} else if(c.block==="Block 2"){b2++;wasted+=r.cost}});
  // Block/wasted are param-dependent -> recomputed from the embedded rows (every
  // flaggable row is in the in-play envelope, so these are exact even when trimmed).
  // The counts are param-INDEPENDENT -> read them from the embedded full-model
  // summary so they stay honest under a trimmed embed (fall back to row-derived
  // when no summary is embedded, e.g. an untrimmed default lambda).
  const T=(typeof MODEL!=="undefined"&&MODEL&&MODEL.summary)?MODEL.summary:null;
  const nb=(T&&T.no_benchmark!=null)?T.no_benchmark:rows.filter(r=>r.status!=="scored").length;
  const uni=(T&&T.universe!=null)?T.universe:rows.length;
  const sc=(T&&T.scored!=null)?T.scored:(rows.length-rows.filter(r=>r.status!=="scored").length);
  return {b1,b2,total:b1+b2,wasted:Math.round(wasted*100)/100,universe:uni,scored:sc,no_benchmark:nb};
};
function gxTermNgrams(term){
  var words=String(term||"").trim().toLowerCase().split(/\s+/).filter(Boolean);
  var set={};
  words.forEach(function(w){set[w]=1;});
  for(var i=0;i<words.length-1;i++){set[words[i]+" "+words[i+1]]=1;}
  return Object.keys(set).sort();
}
function gxWasteNgrams(rows,P){
  var agg={};
  rows.forEach(function(r){
    var c=classify(r,P);
    if(c.block!=="Block 1"&&c.block!=="Block 2") return;
    gxTermNgrams(r.term).forEach(function(g){
      if(!agg[g]) agg[g]={ngram:g,cost:0,terms:0};
      agg[g].cost+=r.cost; agg[g].terms+=1;
    });
  });
  var rowsArr=Object.keys(agg).map(function(k){return agg[k];});
  var top=rowsArr.slice().sort(function(a,b){
    if(b.cost!==a.cost) return b.cost-a.cost;
    return a.ngram<b.ngram?-1:(a.ngram>b.ngram?1:0);
  }).slice(0,15).map(function(e){return {ngram:e.ngram,cost:Math.round(e.cost*100)/100,terms:e.terms};});
  var conc=gxConcentration(rowsArr,"cost",5);
  return {top:top,concentration:conc};
}
"""

# Live logic text + sensitivity strip + near-miss panels (recompute on every change).
JS_EXTRA = r"""
renderExtra = function(host,H){
  const SRC_LABELS={mcp:"Google Ads API (live pull)",user_csv:"User-supplied CSV export (Google Ads UI)"};
  function dataSourceLabel(){
    const srcKey=(MODEL.provenance&&MODEL.provenance.source)||"mcp";
    return SRC_LABELS[srcKey]||srcKey;
  }
  function sensitivity(){
    const saved=P.cost_multiple,out=[];
    MODEL.cost_ladder.forEach(m=>{P.cost_multiple=m; const s=summarize(MODEL.rows,P);
      out.push({m,b1:s.b1,b2:s.b2,total:s.total,cur:Math.abs(m-saved)<1e-9})});
    P.cost_multiple=saved; return out;
  }
  function nearMisses(block){
    const sc=new Set(P.match_types_in_scope),pool=[];
    MODEL.rows.forEach(r=>{
      if(r.status!=="scored"||!sc.has(r.mt)) return;
      if(!(r.ctr < P.ctr_factor*r.camp_ctr)) return;
      if(block==="Block 1"){ if(!(r.conv90<=P.block1_max_conv_90d)) return; }
      else { if(!(r.conv90>P.block2_min_conv_90d && r.conv30<=P.block2_max_conv_30d)) return; }
      const x = r.camp_cpa? r.cost/r.camp_cpa : 0;
      pool.push({r,x,now:r.cost > P.cost_multiple*r.camp_cpa});
    });
    pool.sort((a,b)=>b.x-a.x); return pool.slice(0,15);
  }
  const f=(+P.ctr_factor).toFixed(2), m=(+P.cost_multiple).toFixed(2);
  let h='<div class="card"><h2>Block logic (live)</h2>'+
   `<div class="logic"><b>Block 1</b> — conv(90d) ≤ ${P.block1_max_conv_90d} · match in scope · CTR &lt; ${f} × campaign CTR · cost &gt; ${m} × campaign cost/conv</div>`+
   `<div class="logic"><b>Block 2</b> — conv(90d) &gt; ${P.block2_min_conv_90d} · conv(30d) ≤ ${P.block2_max_conv_30d} · match in scope · CTR &lt; ${f} × campaign CTR · cost &gt; ${m} × campaign cost/conv</div>`+
   `<div class="note" style="margin-top:8px">Data source: ${H.esc(dataSourceLabel())}</div></div>`;
  h+='<div class="card sens"><h2>Threshold sensitivity</h2><div class="note">Qualifiers as the cost multiple changes (other params held current).</div>'+
     '<table><thead><tr><th>Cost ×</th><th class="num">Block 1</th><th class="num">Block 2</th><th class="num">Total</th></tr></thead><tbody>'+
     sensitivity().map(r=>`<tr><td class="${r.cur?'cur':''}">${r.m.toFixed(2)}${r.cur?' ← current':''}</td><td class="num ${r.cur?'cur':''}">${r.b1}</td><td class="num">${r.b2}</td><td class="num">${r.total}</td></tr>`).join("")+
     '</tbody></table></div>';
  h+='<div class="card"><h2>Near misses</h2><div class="note">Meet every condition except (maybe) the cost bar — closest first.</div>';
  [["Block 1"],["Block 2"]].forEach(([blk])=>{
    const nm=nearMisses(blk);
    h+=`<div class="note" style="margin-top:8px"><b>${blk}</b></div>`;
    if(!nm.length){h+='<div class="note">None.</div>';return;}
    h+='<table><thead><tr><th>Term</th><th>Campaign</th><th class="num">Cost</th><th class="num">Qual if ×≤</th><th>Now</th></tr></thead><tbody>';
    nm.forEach(({r,x,now})=>{h+=`<tr><td>${H.esc(r.term)}</td><td>${H.esc(r.campaign)}</td><td class="num">${H.money(r.cost)}</td><td class="num">${x.toFixed(2)}</td><td>${now?'yes':'no'}</td></tr>`;});
    h+='</tbody></table>';
  });
  h+='</div>';
  const wn=gxWasteNgrams(MODEL.rows,P);
  h+='<div class="card"><h2>Top wasteful n-grams</h2><div class="note">Unigrams + adjacent bigrams from Block 1/2 term text, ranked by total wasted spend across occurrences.</div>';
  if(!wn.top.length){h+='<div class="note">None — no term currently qualifies as waste.</div>';}
  else{
    const c=wn.concentration;
    h+=`<div class="note">Top ${Math.min(5,c.n)} n-grams carry ${(c.top_share*100).toFixed(1)}% of the n-gram-weighted waste (HHI ${c.hhi.toFixed(1)}, effective N ${c.effective_n.toFixed(2)}).</div>`;
    h+='<table><thead><tr><th>N-gram</th><th class="num">Wasted spend</th><th class="num">Terms</th></tr></thead><tbody>';
    wn.top.forEach(e=>{h+=`<tr><td>${H.esc(e.ngram)}</td><td class="num">${H.money(e.cost)}</td><td class="num">${e.terms}</td></tr>`;});
    h+='</tbody></table>';
  }
  h+='</div>';
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
# row shapes (model rows and the html embed): cost, ctr, camp_ctr, camp_cpa,
# status, term, block.
# --------------------------------------------------------------------------
_FLAG_COLORS = {"domain": ["Block 1", "Block 2", "Unflagged"],
                "range": ["#0369a1", "#7c3aed", "#cbd5e1"]}  # match the b1/b2 badges

CHARTS = [
    {
        "id": "waste_by_block",
        "title": "Wasted spend by block",
        "mark": {"type": "bar"},
        "transform": [
            {"filter": "datum.block != ''"},
            {"aggregate": [{"op": "sum", "field": "cost", "as": "spend"},
                           {"op": "count", "as": "terms"}],
             "groupby": ["block"]},
        ],
        "encoding": {
            "y": {"field": "block", "type": "nominal", "title": None,
                  "scale": {"domain": ["Block 1", "Block 2"]}},
            "x": {"field": "spend", "type": "quantitative", "title": "Wasted spend"},
            "color": {"field": "block", "type": "nominal", "legend": None,
                      "scale": {"domain": ["Block 1", "Block 2"],
                                "range": ["#0369a1", "#7c3aed"]}},
            "tooltip": [{"field": "block", "title": "Block"},
                        {"field": "spend", "title": "Spend", "format": ",.2f"},
                        {"field": "terms", "title": "Terms"}],
        },
        "height": 120,
        "md": True, "widget": True,
    },
    {
        "id": "ctr_cost_scatter",
        "title": "Scored terms — relative CTR vs relative cost (flagged terms colored)",
        "mark": {"type": "point"},
        "transform": [
            {"filter": "datum.status == 'scored' && datum.camp_ctr > 0 && datum.camp_cpa > 0"},
            {"calculate": "datum.ctr / datum.camp_ctr", "as": "rel_ctr"},
            {"calculate": "datum.cost / datum.camp_cpa", "as": "rel_cost"},
            {"calculate": "datum.block != '' ? datum.block : 'Unflagged'", "as": "flag"},
        ],
        "encoding": {
            "x": {"field": "rel_ctr", "type": "quantitative", "title": "CTR ÷ campaign CTR"},
            "y": {"field": "rel_cost", "type": "quantitative", "title": "Cost ÷ campaign cost/conv"},
            "color": {"field": "flag", "type": "nominal", "title": None, "scale": _FLAG_COLORS},
            "tooltip": [{"field": "term", "title": "Term"},
                        {"field": "flag", "title": "Block"},
                        {"field": "cost", "title": "Cost", "format": ",.2f"},
                        {"field": "rel_ctr", "title": "CTR ÷ camp", "format": ".2f"},
                        {"field": "rel_cost", "title": "Cost ÷ camp CPA", "format": ".2f"}],
        },
        "height": 280,
        "md": True, "widget": False,
    },
]


# --------------------------------------------------------------------------
# The spec object the toolkit consumes.
# --------------------------------------------------------------------------
SPEC = {
    "slug_prefix": "search-term-waste",
    "row_noun": "search terms",
    "title": "Search-Term Waste Filter",
    "about": {
        "summary": "Finds loose-match search terms draining spend: cost well above the campaign's own cost/conversion and a click-through rate well under the campaign average. The Cost multiple and CTR factor set how strict those two bars are — raise the cost multiple and lower the CTR factor to flag only the worst offenders. Terms in campaigns with no conversions in 90 days are held out as 'no benchmark'.",
        "legend": [
            {"label": "Block 1", "desc": "Never-converted waste — at most the Block-1 max conversions in 90d, yet cost > (cost multiple × campaign cost/conv) and CTR < (CTR factor × campaign CTR)."},
            {"label": "Block 2", "desc": "Decaying converter — converted in 90d but at/under the Block-2 max in the recent 30d, and still trips the same cost and CTR bars."},
        ],
    },
    "methodology_ref": "references/search-term-waste-filter.md",
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
    # xlsx layout is attached in waste_filter_xlsx_spec to keep this module
    # stdlib-only and import-light; build_waste_filter wires it in for xlsx.
}
