#!/usr/bin/env python3
"""Render spec for the product-segments filter — adapts product_filter_core's
model to the shared render toolkit (_shared/render). Stdlib only.

The classification math lives once in product_filter_core (Python) and is
mirrored in `JS_KERNEL` (browser); the two must compute byte-identical results
(Node-vs-Python parity gate). The xlsx formulas (product_filter_xlsx_spec)
mirror the same logic a third time.
"""
from __future__ import annotations

import product_filter_core as core  # recommendations() — presentation over the model, no new math
from render import model as M  # noqa: E402  (source_label — HM-572 canonical "Data source" line)


def _money(v, cur):
    return f"{float(v):,.2f}" + (f" {cur}" if cur else "")


def _n(v):
    """Int when integral else 2dp — for conversions/impressions display."""
    f = float(v or 0)
    return int(f) if f.is_integer() else round(f, 2)


# --------------------------------------------------------------------------
# Markdown adapters
# --------------------------------------------------------------------------
def md_params(model):
    p = model["params"]
    pr = model["provenance"]
    return [
        ("Segment thresholds",
         f"surge > {p['surge_multiple']:.2f}× prev-14d conv · "
         f"decline < {p['decline_multiple']:.2f}× prev-14d conv · "
         f"zombie cost > {p['zombie_cost_min']:g} & conv ≤ {p['zombie_conv_max']:g} (30d)"),
        ("14-day window", pr.get("window_14d") or "—"),
        ("Previous 14-day window", pr.get("window_prev14d") or "—"),
        ("Data source", M.source_label(pr.get("source"))),
    ]


def md_kpis(model):
    s = model["summary"]
    cur = model["provenance"]["currency"]
    return [
        ("Zombie (wasted spend)", str(s["zombie"])),
        ("Zombie wasted cost (30d)", _money(s["zombie_wasted_cost"], cur)),
        ("Surging", str(s["surging"])),
        ("Declining", str(s["declining"])),
        ("Universe", f"{s['universe']} products ({s['scored']} scored, "
                     f"{s['inactive']} inactive, {s['no_merchant']} no-merchant)"),
    ]


def md_narrative(model):
    if model["summary"]["flagged"] != 0:
        return []
    return [
        "> **No products flagged is a clean result, not an error.** Under the rule as written, no "
        "product is both spending with zero conversions (and still in the feed), surging past "
        f"{model['params']['surge_multiple']:.2f}×, or collapsing below "
        f"{model['params']['decline_multiple']:.2f}× its prior pace. The sensitivity tables below "
        "show where products would start to qualify if the multipliers were relaxed.",
    ]


def md_recommendations_section(model):
    """The advisor output contract's Critical -> High -> Medium recommendations,
    each row citing the model's own numbers (product_filter_core.recommendations),
    as a table so it renders identically wherever md_sections lands (md + the
    xlsx Sensitivity snapshot)."""
    recs = core.recommendations(model)
    rows = [[r["severity"], r["action"], r["why"], r["worklist"]] for r in recs]
    return {
        "title": "Recommendations (Critical → High → Medium)",
        "note": "Every action cites the model's own numbers above — see the full per-product "
                "table below for complete detail. Worklist CSVs are offered alongside this report; "
                "apply manually in the Shopping/PMax listing groups (not a Google Ads Editor import).",
        "headers": ["Severity", "Recommended action", "Why (model numbers)", "Worklist"],
        "aligns": ["l", "l", "l", "l"],
        "rows": rows,
        "empty": "_No products flagged this run — a clean result, not an omission "
                 "(see the sensitivity tables below for near-misses)._",
    }


def md_sections(model):
    cur = model["provenance"]["currency"]
    secs = [md_recommendations_section(model)]

    secs.append({
        "title": "Surge sensitivity",
        "note": "How many products qualify as SURGING as the surge multiple changes "
                "(decline/zombie held current).",
        "headers": ["Surge ×", "Surging", "Zombie", "Declining"],
        "aligns": ["l", "r", "r", "r"],
        "rows": [[f"{r['multiple']:.2f}" + (" ← current" if r["is_current"] else ""),
                  r["surging"], r["zombie"], r["declining"]] for r in model["sensitivity_surge"]],
    })
    secs.append({
        "title": "Decline sensitivity",
        "note": "How many products qualify as DECLINING as the decline multiple changes "
                "(surge/zombie held current).",
        "headers": ["Decline ×", "Declining", "Zombie", "Surging"],
        "aligns": ["l", "r", "r", "r"],
        "rows": [[f"{r['multiple']:.2f}" + (" ← current" if r["is_current"] else ""),
                  r["declining"], r["zombie"], r["surging"]] for r in model["sensitivity_decline"]],
    })

    inactive = [r for r in model["rows"] if r["status"] == "inactive"]
    secs.append({
        "title": "Excluded — inactive products (no spend, no impressions)",
        "note": "Zero cost AND zero impressions in every window, so there is nothing to score. "
                "Listed here so nothing is silently dropped.",
        "headers": ["Product", "Item ID", "Merchant ID"],
        "aligns": ["l", "l", "l"],
        "rows": [[r["product_title"], r["product_item_id"], r["merchant_id"] or "—"]
                 for r in inactive],
        "empty": "_None — every product had some spend or impressions in the windows._",
    })
    return secs


def md_rows(model):
    """Every product with a status + segment — the no-row-loss layer for the md."""
    cur = model["provenance"]["currency"]
    headers = ["Product", "Item ID", "Merchant", "Channels", "Status",
               f"Cost 30d ({cur})" if cur else "Cost 30d",
               "Conv 30d", "Conv prev-14d", "Conv 14d", "Impr 14d", "Segment"]
    out = []
    for r in model["rows"]:
        out.append([
            r["product_title"], r["product_item_id"], r["merchant_id"] or "—",
            ", ".join(r.get("channels") or []) or "—", r["status"],
            f"{r['cost_30d']:,.2f}", f"{r['conversions_30d']:.2f}",
            f"{r['conversions_prev14d']:.2f}", f"{r['conversions_14d']:.2f}",
            _n(r["impressions_14d"]), r["segment"] or "",
        ])
    return {
        "title": "All products (every row, with status)",
        "note": "No row loss: every product in the universe appears here — scored (Zombie / "
                "Surging / Declining / blank) or held out as inactive. Sorted by 30-day cost (highest "
                "first).",
        "headers": headers,
        "aligns": ["l", "l", "l", "l", "l", "r", "r", "r", "r", "r", "l"],
        "rows": out,
        "empty": "_No products in the universe._",
    }


# --------------------------------------------------------------------------
# HTML adapters
# --------------------------------------------------------------------------
def in_play(r, params=None):
    """Reachable envelope for the in-Claude tuner's embed (widget_emit applies this).

    Only `scored` products are ever classified into a segment — `inactive` products
    (zero cost AND zero impressions in every window) can never be Zombie/Surging/
    Declining and never move the sensitivity ladders, so the live preview embeds only
    scored rows (drops the inactive long tail). This skill has no near-miss panel, so
    `scored` is a complete envelope. The param-independent counts (universe/scored/
    inactive/no_merchant) come from the embedded full-model summary; the full universe
    still flows to md/html/xlsx via build_bundle, untouched.
    """
    return r.get("status") == "scored"


def html_embed(model):
    return {
        "provenance": model["provenance"],
        "params": model["params"],
        "summary": model["summary"],
        "surge_ladder": model["surge_ladder"],
        "decline_ladder": model["decline_ladder"],
        "rows": [{
            "product_title": r["product_title"], "product_item_id": r["product_item_id"],
            "merchant_id": r["merchant_id"], "status": r["status"],
            "cost_30d": r["cost_30d"], "conversions_30d": r["conversions_30d"],
            "impressions_30d": r["impressions_30d"],
            "conversions_14d": r["conversions_14d"], "impressions_14d": r["impressions_14d"],
            "conversions_prev14d": r["conversions_prev14d"],
            "impressions_prev14d": r["impressions_prev14d"],
        } for r in model["rows"]],
    }


HTML_CONTROLS = [
    {"key": "surge_multiple", "label": "Surge multiple", "kind": "slider",
     "min": 1.0, "max": 3.0, "step": 0.05, "sub": "× previous-14d conversions"},
    {"key": "decline_multiple", "label": "Decline multiple", "kind": "slider",
     "min": 0.1, "max": 1.0, "step": 0.05, "sub": "× previous-14d conversions"},
    {"key": "zombie_cost_min", "label": "Zombie · min 30d cost floor", "kind": "number",
     "min": 0, "step": 1},
    {"key": "zombie_conv_max", "label": "Zombie · max 30d conversions", "kind": "number",
     "min": 0, "step": 1},
]

# Status is param-independent (data quality) -> plain text. Segment is the LIVE
# classification -> fmt "block" reads the kernel's classify(r,P).block result.
HTML_COLUMNS = [
    {"key": "product_title", "label": "Product"},
    {"key": "product_item_id", "label": "Item ID"},
    {"key": "merchant_id", "label": "Merchant"},
    {"key": "status", "label": "Status"},
    {"key": "cost_30d", "label": "Cost 30d", "num": True, "fmt": "money"},
    {"key": "conversions_30d", "label": "Conv 30d", "num": True, "fmt": "num"},
    {"key": "conversions_prev14d", "label": "Conv prev-14d", "num": True, "fmt": "num"},
    {"key": "conversions_14d", "label": "Conv 14d", "num": True, "fmt": "num"},
    {"key": "impressions_14d", "label": "Impr 14d", "num": True, "fmt": "int"},
    {"key": "block", "label": "Segment", "fmt": "block"},
]

HTML_KPIS = [
    {"label": "Zombie", "key": "zombie", "cls": "b1"},
    {"label": "Zombie wasted $", "key": "zombie_wasted_cost", "money": True},
    {"label": "Surging", "key": "surging", "cls": "b2"},
    {"label": "Declining", "key": "declining"},
    {"label": "Inactive", "key": "inactive"},
]

# Mirrors product_filter_core.classify_row / summarize EXACTLY. Assigns the
# engine's `classify` and `summarize`. `block` aliases `segment` so the generic
# badge / "block"-format / qualifying-only / sort paths in the toolkit work.
JS_KERNEL = r"""
classify = function(r,P){
  if(r.status==="inactive")
    return {block:"", segment:"", is_zombie:null, is_surging:null, is_declining:null};
  var has_m = (r.merchant_id!=null && String(r.merchant_id)!=="");
  var c30=+r.conversions_30d, k30=+r.cost_30d;
  var c14=+r.conversions_14d, p14=+r.conversions_prev14d;
  var is_zombie    = has_m && (c30 <= P.zombie_conv_max) && (k30 > P.zombie_cost_min);
  var is_surging   = (p14 > 0) && (c14 > P.surge_multiple * p14);
  var is_declining = (c14 < P.decline_multiple * p14);
  var segment = is_zombie ? "Zombie" : is_surging ? "Surging" : is_declining ? "Declining" : "";
  return {block:segment, segment:segment, is_zombie:is_zombie,
          is_surging:is_surging, is_declining:is_declining};
};
summarize = function(rows,P){
  var z=0, su=0, d=0, wasted=0, scored=0, inact=0, no_m=0;
  rows.forEach(function(r){
    var c=classify(r,P);
    if(r.status==="scored") scored++; else if(r.status==="inactive") inact++;
    if(r.merchant_id==null || String(r.merchant_id)==="") no_m++;
    if(c.segment==="Zombie"){ z++; wasted += (+r.cost_30d); }
    else if(c.segment==="Surging") su++;
    else if(c.segment==="Declining") d++;
  });
  // Counts are param-independent -> read from the embedded full-model summary so they
  // stay correct under a trimmed (scored-only) embed; fall back to row-derived.
  var T=(typeof MODEL!=="undefined"&&MODEL&&MODEL.summary)?MODEL.summary:null;
  var g=function(k,fb){return (T && T[k]!=null)?T[k]:fb;};
  return {zombie:z, surging:su, declining:d, flagged:z+su+d,
          zombie_wasted_cost: Math.round(wasted*100)/100,
          universe: g("universe", rows.length), scored: g("scored", scored),
          inactive: g("inactive", inact), no_merchant: g("no_merchant", no_m)};
};
"""

# Live segment-logic text + the three windows + surge/decline sensitivity strips
# (recompute on every slider change via a temporary param swap).
JS_EXTRA = r"""
renderExtra = function(host,H){
  function sens(pkey, ladder){
    var saved=P[pkey], out=[];
    ladder.forEach(function(m){ P[pkey]=m; var s=summarize(MODEL.rows,P);
      out.push({m:m, zombie:s.zombie, surging:s.surging, declining:s.declining,
                cur:Math.abs(m-saved)<1e-9}); });
    P[pkey]=saved; return out;
  }
  var pr=MODEL.provenance||{};
  var sm=(+P.surge_multiple).toFixed(2), dm=(+P.decline_multiple).toFixed(2);
  var h='<div class="card"><h2>Segment logic (live)</h2>'+
    '<div class="logic"><b>Zombie</b> — conversions(30d) ≤ '+P.zombie_conv_max+
      ' AND cost(30d) &gt; '+P.zombie_cost_min+' AND merchant id present (last 14d)</div>'+
    '<div class="logic"><b>Surging</b> — conversions(14d) &gt; '+sm+
      ' × conversions(prev-14d), with prev-14d conversions &gt; 0</div>'+
    '<div class="logic"><b>Declining</b> — conversions(14d) &lt; '+dm+
      ' × conversions(prev-14d)</div>'+
    '<div class="note">Windows — 30d: <b>'+H.esc(pr.window_30d||'—')+
      '</b> · 14d: <b>'+H.esc(pr.window_14d||'—')+
      '</b> · prev-14d: <b>'+H.esc(pr.window_prev14d||'—')+'</b></div></div>';
  h+='<div class="card sens"><h2>Surge sensitivity</h2>'+
     '<div class="note">SURGING count as the surge multiple changes (others held current).</div>'+
     '<table><thead><tr><th>Surge ×</th><th class="num">Surging</th>'+
     '<th class="num">Zombie</th><th class="num">Declining</th></tr></thead><tbody>'+
     sens("surge_multiple",MODEL.surge_ladder).map(function(r){
       return '<tr><td class="'+(r.cur?'cur':'')+'">'+r.m.toFixed(2)+(r.cur?' ← current':'')+
       '</td><td class="num '+(r.cur?'cur':'')+'">'+r.surging+'</td><td class="num">'+r.zombie+
       '</td><td class="num">'+r.declining+'</td></tr>';}).join("")+
     '</tbody></table></div>';
  h+='<div class="card sens"><h2>Decline sensitivity</h2>'+
     '<div class="note">DECLINING count as the decline multiple changes (others held current).</div>'+
     '<table><thead><tr><th>Decline ×</th><th class="num">Declining</th>'+
     '<th class="num">Zombie</th><th class="num">Surging</th></tr></thead><tbody>'+
     sens("decline_multiple",MODEL.decline_ladder).map(function(r){
       return '<tr><td class="'+(r.cur?'cur':'')+'">'+r.m.toFixed(2)+(r.cur?' ← current':'')+
       '</td><td class="num '+(r.cur?'cur':'')+'">'+r.declining+'</td><td class="num">'+r.zombie+
       '</td><td class="num">'+r.surging+'</td></tr>';}).join("")+
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
# row shapes (model rows and the html embed): cost_30d, conversions_30d,
# status, product_title, and segment (the Python rows carry `segment` natively
# and the JS kernel's classify returns it alongside its `block` alias — never
# reference `block`, the Python rows don't have it). Colors match the
# explorer's accents: Zombie = the b1 blue, Surging = the b2 purple (the KPI
# cards), Declining = the shared amber, Unflagged = the neutral grey.
# --------------------------------------------------------------------------
_SEGMENT_COLORS = {"domain": ["Zombie", "Surging", "Declining"],
                   "range": ["#0369a1", "#7c3aed", "#b45309"]}
_FLAG_COLORS = {"domain": ["Zombie", "Surging", "Declining", "Unflagged"],
                "range": ["#0369a1", "#7c3aed", "#b45309", "#cbd5e1"]}

CHARTS = [
    {
        "id": "spend_by_segment",
        "title": "30-day spend by segment",
        "mark": {"type": "bar"},
        "transform": [
            {"filter": "datum.segment != ''"},
            {"aggregate": [{"op": "sum", "field": "cost_30d", "as": "spend"},
                           {"op": "count", "as": "products"}],
             "groupby": ["segment"]},
        ],
        "encoding": {
            "y": {"field": "segment", "type": "nominal", "title": None,
                  "scale": {"domain": ["Zombie", "Surging", "Declining"]}},
            "x": {"field": "spend", "type": "quantitative", "title": "Spend (30d)"},
            "color": {"field": "segment", "type": "nominal", "legend": None,
                      "scale": _SEGMENT_COLORS},
            "tooltip": [{"field": "segment", "title": "Segment"},
                        {"field": "spend", "title": "Spend (30d)", "format": ",.2f"},
                        {"field": "products", "title": "Products"}],
        },
        "height": 140,
        "md": True, "widget": True,
    },
    {
        "id": "cost_conv_scatter",
        "title": "Scored products — 30-day cost vs conversions (segments colored)",
        "mark": {"type": "point"},
        "transform": [
            {"filter": "datum.status == 'scored'"},
            {"calculate": "datum.segment != '' ? datum.segment : 'Unflagged'", "as": "flag"},
        ],
        "encoding": {
            "x": {"field": "conversions_30d", "type": "quantitative", "title": "Conversions (30d)"},
            "y": {"field": "cost_30d", "type": "quantitative", "title": "Cost (30d)"},
            "color": {"field": "flag", "type": "nominal", "title": None, "scale": _FLAG_COLORS},
            "tooltip": [{"field": "product_title", "title": "Product"},
                        {"field": "flag", "title": "Segment"},
                        {"field": "cost_30d", "title": "Cost (30d)", "format": ",.2f"},
                        {"field": "conversions_30d", "title": "Conv (30d)", "format": ".2f"}],
        },
        "height": 280,
        "md": True, "widget": False,
    },
]


# --------------------------------------------------------------------------
# The spec object the toolkit consumes.
# --------------------------------------------------------------------------
SPEC = {
    "slug_prefix": "product-segments",
    "row_noun": "products",
    "title": "Product Segments — Zombie · Surging · Declining",
    "about": {
        "summary": "Segments shopping products by 14-day conversion momentum and spend efficiency. The Surge and Decline multiples set how big a swing counts; the Zombie cost floor and conversion ceiling define wasted spend. Products with no spend and no impressions are held out as inactive.",
        "legend": [
            {"label": "Zombie", "desc": "In the feed and spending (cost > floor) but at most the zombie max conversions in 30d — wasted spend."},
            {"label": "Surging", "desc": "Conversions up — last 14d > (surge multiple × prior 14d). Scale into it."},
            {"label": "Declining", "desc": "Conversions down — last 14d < (decline multiple × prior 14d). Investigate."},
        ],
    },
    "methodology_ref": "references/product-segments-filter.md",
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
    # xlsx layout is attached in product_filter_xlsx_spec to keep this module
    # stdlib-only and import-light; the build CLIs wire it in for xlsx.
}
