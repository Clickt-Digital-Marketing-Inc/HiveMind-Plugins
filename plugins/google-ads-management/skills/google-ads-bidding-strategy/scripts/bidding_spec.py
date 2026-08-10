#!/usr/bin/env python3
"""Render spec for the bidding-strategy Data Maturity Score — adapts
bidding_core's model to the shared render toolkit (_shared/render). Stdlib only.

The scoring/classification math lives once in bidding_core (Python) and is
mirrored in `JS_KERNEL` (browser) via the shared `analytics.JS_MIRROR` —
the Node-vs-Python parity gate (`_shared/tests/analytics_vectors_bidding.json`
+ `skills/google-ads/tests/run_parity.py analytics-primitives`, plus this
skill's own `tests/js_kernel_parity.py`) keeps them in sync.
"""
from __future__ import annotations

import bidding_core as core  # noqa: E402  (puts _shared on sys.path)
import analytics  # noqa: E402  (_shared/analytics.py; sys.path set by bidding_core)
from render import model as M  # noqa: E402  (source_label — HM-572 canonical "Data source" line)


def _money(v, cur):
    return f"{float(v):,.2f}" + (f" {cur}" if cur else "")


# --------------------------------------------------------------------------
# Markdown adapters
# --------------------------------------------------------------------------
def md_params(model):
    p = model["params"]
    return [
        ("Data source", M.source_label(model["provenance"].get("source"))),
        ("Volume component", f"saturates to 100 at {p['conv_target']:.0f} conversions/30d "
            f"(weight {p['volume_weight']:.2f})"),
        ("Value-variance / tracking-confidence", f"assumed {p['assumed_value_score']:.0f} / "
            f"{p['assumed_tracking_score']:.0f} when not supplied (weights {p['value_weight']:.2f} / "
            f"{p['tracking_weight']:.2f})"
            + M.inline_marker(model, "assumed_value_score") + M.inline_marker(model, "assumed_tracking_score")),
        ("Band edges", " · ".join(f"{p[f'band_edge_{i}']:.0f}" for i in (1, 2, 3, 4))
            + "  (Manual → Enhanced CPC → Target CPA → Target ROAS → + Exploration)"),
        ("Automation gate", f"conv30 < {p['conv_gate']:.0f} + any automated strategy = "
            "Over-automated (under-data)"),
        ("Tier-gap threshold", f"±{p['tier_gap_threshold']:.0f} tier(s) before a plain mismatch fires"),
    ]


def md_kpis(model):
    s = model["summary"]
    cur = model["provenance"]["currency"]
    return [
        ("Over-automated (under-data)", str(s["over_automated_under_data"])),
        ("Over-automated", str(s["over_automated"])),
        ("Under-automated", str(s["under_automated"])),
        ("Aligned", str(s["aligned"])),
        ("Avg Data Maturity Score (scored)", f"{s['avg_maturity_score']:.2f}"),
        ("Spend on under-data automation", _money(s["critical_spend"], cur)),
        ("Universe", f"{s['universe']} campaigns ({s['scored']} scored, {s['no_spend']} no-spend, "
            f"{s['unsupported_strategy']} unsupported strategy)"),
        ("Top-3 spend share", f"{s['spend_top3_share'] * 100:.2f}%  (HHI {s['spend_hhi']:.1f}, "
            f"effective N {s['spend_effective_n']:.2f})"),
    ]


def md_narrative(model):
    if model["summary"]["total_mismatched"] != 0:
        return []
    return [
        "> **No mismatches is a clean result, not an error.** Every scored campaign's current "
        "bidding strategy sits within the tier-gap threshold of what its Data Maturity Score "
        "supports. The gate-sensitivity table below shows how the automation-data gate would need "
        "to move before a mismatch would appear, and the borderline list shows the campaigns "
        "closest to a tier boundary.",
    ]


def md_sections(model):
    cur = model["provenance"]["currency"]
    secs = []

    secs.append({
        "title": "Automation-gate sensitivity",
        "note": "How the under-data automation flag count changes as the conversion gate moves "
                "(all other params held at current values).",
        "headers": ["Conv/30d gate", "Over-automated (under-data)", "Total mismatched"],
        "aligns": ["l", "r", "r"],
        "rows": [[f"{r['conv_gate']:.0f}" + (" ← current" if r["is_current"] else ""),
                  r["over_automated_under_data"], r["total_mismatched"]]
                 for r in model["gate_sensitivity"]],
    })

    bl = model["borderline"][:15]
    secs.append({
        "title": "Borderline campaigns",
        "note": "Scored campaigns whose Data Maturity Score sits closest to a tier boundary — "
                "watch these even when not currently flagged.",
        "headers": ["Campaign", "Maturity score", "Distance to edge", "Current strategy",
                    "Recommended strategy", "Mismatch"],
        "aligns": ["l", "r", "r", "l", "l", "l"],
        "rows": [[r["campaign"], f"{r['maturity_score']:.2f}", f"{r['distance_to_edge']:.2f}",
                  r["current_label"], r["recommended_label"], r["mismatch"] or "Aligned"]
                 for r in bl],
        "empty": "_No scored campaigns._",
    })

    no_spend = [r for r in model["rows"] if r["status"] == "no_spend"]
    secs.append({
        "title": "Excluded — no spend in window",
        "note": "These campaigns had 0 cost in the pulled window, so bidding-strategy fit cannot "
                "be assessed. Listed here so nothing is silently dropped.",
        "headers": ["Campaign", "Bidding strategy"],
        "aligns": ["l", "l"],
        "rows": [[r["campaign"], r["bidding_strategy"] or "—"] for r in no_spend],
        "empty": "_None — every campaign had spend in the window._",
    })

    unsupported = [r for r in model["rows"] if r["status"] == "unsupported_strategy"]
    secs.append({
        "title": "Excluded — unsupported bidding strategy",
        "note": "This model doesn't map every Google Ads bidding strategy to a maturity tier "
                "(e.g. Commission, Target Impression Share). Held out rather than misclassified.",
        "headers": ["Campaign", "Bidding strategy", f"Cost ({cur})" if cur else "Cost"],
        "aligns": ["l", "l", "r"],
        "rows": [[r["campaign"], r["bidding_strategy"] or "—", f"{r['cost']:,.2f}"]
                 for r in unsupported],
        "empty": "_None — every campaign's strategy maps to a tier._",
    })
    return secs


def md_rows(model):
    """Every campaign with a status — the no-row-loss layer."""
    cur = model["provenance"]["currency"]
    headers = ["Campaign", "Status", "Liveness", "Bidding strategy", "Conv 30d",
               f"Cost ({cur})" if cur else "Cost",
               "Maturity score", "Confidence", "Recommended strategy", "Mismatch"]
    out = []
    for r in model["rows"]:
        out.append([
            r["campaign"], r["status"].replace("_", " "), r["liveness"].replace("_", " "),
            r["bidding_strategy"] or "—",
            f"{r['conv30']:.2f}", f"{r['cost']:,.2f}",
            (f"{r['maturity_score']:.2f}" if r["maturity_score"] is not None else "—"),
            r["confidence"] if r["status"] == "scored" else "n/a",
            r["recommended_label"] or "—", r["mismatch"] or ("—" if r["status"] == "scored" else ""),
        ])
    return {
        "title": "All campaigns (every row, with status)",
        "note": "No row loss: every campaign in the pulled/exported universe appears here (with its "
                "liveness band), scored or held out with a reason. Sorted by cost (highest first).",
        "headers": headers,
        "aligns": ["l", "l", "l", "l", "r", "r", "r", "l", "l", "l"],
        "rows": out,
        "empty": "_No campaigns in the universe._",
    }


# --------------------------------------------------------------------------
# HTML adapters
# --------------------------------------------------------------------------
def in_play(r, params=None):
    """Reachable envelope for the in-Claude tuner's embed: every 'scored' row
    could become any mismatch state (or aligned) under some reachable param
    combination — there is no cheaper param-independent filter than status
    itself, so the envelope is exactly the scored rows. no_spend /
    unsupported_strategy rows can never be classified regardless of tuning."""
    return r.get("status") == "scored"


def html_embed(model):
    return {
        "provenance": model["provenance"],
        "params": model["params"],
        "summary": model["summary"],
        "tier_labels": model["tier_labels"],
        "gate_ladder": model["gate_ladder"],
        "rows": [{
            "campaign": r["campaign"], "status": r["status"],
            "liveness": r["liveness"], "liveness_note": r.get("liveness_note", ""),
            "bidding_strategy": r["bidding_strategy"], "current_tier": r["current_tier"],
            "current_label": r["current_label"], "conv30": r["conv30"], "cost": r["cost"],
            "value_score": r["value_score"], "tracking_score": r["tracking_score"],
            "confidence": r["confidence"],
        } for r in model["rows"]],
    }


HTML_CONTROLS = [
    {"key": "conv_target", "label": "Volume saturation (conv/30d)", "kind": "slider",
     "min": 5, "max": 100, "step": 5, "sub": "conv30 at which the volume component reaches 100"},
    {"key": "conv_gate", "label": "Automation data gate (conv/30d)", "kind": "slider",
     "min": 5, "max": 100, "step": 5, "sub": "below this + automated bidding = Critical flag"},
    {"key": "tier_gap_threshold", "label": "Tier-gap flag threshold", "kind": "number",
     "min": 0, "step": 1, "sub": "tiers of difference before flagging a mismatch"},
    {"key": "band_edge_1", "label": "Band edge 1 — Manual → Enhanced CPC", "kind": "number", "min": 0, "step": 1},
    {"key": "band_edge_2", "label": "Band edge 2 — Enhanced CPC → Target CPA", "kind": "number", "min": 0, "step": 1},
    {"key": "band_edge_3", "label": "Band edge 3 — Target CPA → Target ROAS", "kind": "number", "min": 0, "step": 1},
    {"key": "band_edge_4", "label": "Band edge 4 — Target ROAS → + Exploration", "kind": "number", "min": 0, "step": 1},
    {"key": "volume_weight", "label": "Volume weight", "kind": "number", "min": 0, "step": 0.05},
    {"key": "value_weight", "label": "Value-variance weight", "kind": "number", "min": 0, "step": 0.05},
    {"key": "tracking_weight", "label": "Tracking-confidence weight", "kind": "number", "min": 0, "step": 0.05},
    {"key": "assumed_value_score", "label": "Assumed value-variance score (no data)", "kind": "number",
     "min": 0, "max": 100, "step": 5},
    {"key": "assumed_tracking_score", "label": "Assumed tracking-confidence score (no data)", "kind": "number",
     "min": 0, "max": 100, "step": 5},
]

HTML_COLUMNS = [
    {"key": "campaign", "label": "Campaign"},
    {"key": "status", "label": "Status", "fmt": "status"},
    {"key": "liveness", "label": "Liveness", "fmt": "status"},
    {"key": "bidding_strategy", "label": "Bidding strategy"},
    {"key": "current_label", "label": "Current tier"},
    {"key": "conv30", "label": "Conv30", "num": True, "fmt": "num"},
    {"key": "cost", "label": "Cost", "num": True, "fmt": "money"},
    {"key": "maturity_score", "label": "Maturity score", "num": True, "fmt": "num"},
    {"key": "recommended_label", "label": "Recommended tier"},
    {"key": "confidence", "label": "Confidence"},
    {"key": "mismatch", "label": "Mismatch", "fmt": "block"},
]

HTML_KPIS = [
    {"label": "Over-automated (under-data)", "key": "over_automated_under_data", "cls": "b2"},
    {"label": "Over-automated", "key": "over_automated"},
    {"label": "Under-automated", "key": "under_automated", "cls": "b1"},
    {"label": "Total mismatched", "key": "total_mismatched"},
    {"label": "Avg maturity score", "key": "avg_maturity_score"},
    {"label": "Spend on under-data automation", "key": "critical_spend", "money": True},
]

# Mirrors bidding_core.classify_row / summarize exactly (verified by the
# Node-vs-Python gate + this skill's own tests/js_kernel_parity.py). Splices
# the shared analytics.JS_MIRROR (gxSignals/gxPreScore/gxConcentration/
# gxRoundHalfUp) verbatim rather than re-writing that math.
JS_KERNEL = analytics.JS_MIRROR + r"""
classify = function(r,P){
  // Liveness gate (HM-603): a dormant campaign (not ENABLED, zero spend in the
  // window) is never scored or flagged — mirrors bidding_core.classify_row and
  // the xlsx Mismatch formula. `liveness` is a static embedded field (not
  // tuning-dependent), so the kernel only READS it.
  if(r.liveness==="dormant") return {maturity_score:null, recommended_tier:null, tier_gap:null,
    mismatch:"", block:"", severity:0, status:r.status};
  if(r.status!=="scored") return {maturity_score:null, recommended_tier:null, tier_gap:null,
    mismatch:"", block:"", severity:0, status:r.status};
  var convTarget = P.conv_target;
  var volume = convTarget<=0 ? 0 : Math.min(100, Math.max(0, 100*r.conv30/convTarget));
  var value = (r.value_score!=null ? r.value_score : P.assumed_value_score);
  var tracking = (r.tracking_score!=null ? r.tracking_score : P.assumed_tracking_score);
  var maturity = gxRoundHalfUp(volume*P.volume_weight + value*P.value_weight + tracking*P.tracking_weight, 2);
  var edges=[P.band_edge_1,P.band_edge_2,P.band_edge_3,P.band_edge_4].slice().sort(function(a,b){return a-b;});
  var tier=0; edges.forEach(function(e){ if(maturity>=e) tier+=1; });
  var current = r.current_tier;
  var gap = current - tier;
  var sigRow = {conv30: r.conv30, tier_gap: gap};
  var rules=[
    {id:"under_data", key:"conv30", op:"lt", value:P.conv_gate},
    {id:"over_automated", key:"tier_gap", op:"gt", value:P.tier_gap_threshold},
    {id:"under_automated", key:"tier_gap", op:"lt", value:-P.tier_gap_threshold}
  ];
  var flags = gxSignals([sigRow], rules)[0];
  var composite=[], mismatch="";
  if(flags.indexOf("under_data")>=0 && current>=1){ composite=["under_data_automated"]; mismatch="Over-automated (under-data)"; }
  else if(flags.indexOf("over_automated")>=0){ composite=["over_automated"]; mismatch="Over-automated"; }
  else if(flags.indexOf("under_automated")>=0){ composite=["under_automated"]; mismatch="Under-automated"; }
  // mirrors bidding_core.SEVERITY_WEIGHTS by hand (not part of analytics.JS_MIRROR
  // — see the comment there); tests/js_kernel_parity.py guards the two staying in sync.
  var weights={under_data_automated:8.0, over_automated:3.0, under_automated:2.0};
  var severity = gxPreScore({flags:composite}, weights);
  return {maturity_score:maturity, recommended_tier:tier, tier_gap:gap, mismatch:mismatch,
    block:mismatch, severity:severity, status:r.status};
};
summarize = function(rows,P){
  var scored=[], noSpendLocal=0, unsupportedLocal=0;
  rows.forEach(function(r){
    if(r.status==="scored") scored.push(r);
    else if(r.status==="no_spend") noSpendLocal++;
    else if(r.status==="unsupported_strategy") unsupportedLocal++;
  });
  var overUd=0, over=0, under=0, aligned=0, maturitySum=0, criticalSpend=0;
  scored.forEach(function(r){
    var c=classify(r,P);
    if(c.mismatch==="Over-automated (under-data)"){overUd++; criticalSpend+=r.cost;}
    else if(c.mismatch==="Over-automated"){over++;}
    else if(c.mismatch==="Under-automated"){under++;}
    else {aligned++;}
    maturitySum += c.maturity_score;
  });
  var conc = gxConcentration(rows, "cost", 3);
  // no_spend/unsupported_strategy are param-INDEPENDENT counts -> read them
  // from the embedded full-model summary so they stay honest under a
  // trimmed widget embed (fall back to row-derived when summary is absent).
  var T=(typeof MODEL!=="undefined"&&MODEL&&MODEL.summary)?MODEL.summary:null;
  var uni=(T&&T.universe!=null)?T.universe:rows.length;
  var ns=(T&&T.no_spend!=null)?T.no_spend:noSpendLocal;
  var us=(T&&T.unsupported_strategy!=null)?T.unsupported_strategy:unsupportedLocal;
  return {universe:uni, scored:scored.length, no_spend:ns, unsupported_strategy:us,
    over_automated_under_data:overUd, over_automated:over, under_automated:under, aligned:aligned,
    total_mismatched: overUd+over+under,
    avg_maturity_score: scored.length ? Math.round((maturitySum/scored.length)*100)/100 : 0,
    critical_spend: Math.round(criticalSpend*100)/100,
    spend_top3_share: conc.top_share, spend_hhi: conc.hhi, spend_effective_n: conc.effective_n};
};
"""

# Live logic text + gate-sensitivity strip (recompute on every change).
JS_EXTRA = r"""
renderExtra = function(host,H){
  function sensitivity(){
    var saved=P.conv_gate, out=[];
    (MODEL.gate_ladder||[]).forEach(function(g){
      P.conv_gate=g;
      var s=summarize(MODEL.rows,P);
      out.push({g:g, overUd:s.over_automated_under_data, total:s.total_mismatched,
                cur:Math.abs(g-saved)<1e-9});
    });
    P.conv_gate=saved; return out;
  }
  var f=(+P.tier_gap_threshold).toFixed(0);
  var h='<div class="card"><h2>Mismatch logic (live)</h2>'+
   '<div class="logic"><b>Over-automated (under-data)</b> — conv(30d) &lt; '+(+P.conv_gate).toFixed(0)+' AND current tier is automated (≥ Enhanced CPC).</div>'+
   '<div class="logic"><b>Over-automated</b> — current tier − recommended tier &gt; '+f+'.</div>'+
   '<div class="logic"><b>Under-automated</b> — current tier − recommended tier &lt; -'+f+'.</div></div>';
  h+='<div class="card sens"><h2>Automation-gate sensitivity</h2><div class="note">Under-data flags as the conversion gate changes (other params held current).</div>'+
     '<table><thead><tr><th>Conv/30d gate</th><th class="num">Over-automated (under-data)</th><th class="num">Total mismatched</th></tr></thead><tbody>'+
     sensitivity().map(function(r){return '<tr><td class="'+(r.cur?'cur':'')+'">'+r.g.toFixed(0)+(r.cur?' ← current':'')+'</td><td class="num '+(r.cur?'cur':'')+'">'+r.overUd+'</td><td class="num">'+r.total+'</td></tr>';}).join("")+
     '</tbody></table></div>';
  host.innerHTML=h;
};
"""


# --------------------------------------------------------------------------
# Charts — declared here, GENERATED by _shared/render/charts.py (never hand-
# authored). One declaration drives both the static SVGs shipped with the
# md/widget and the live explorer charts, re-deriving from the classify(r,P)-
# augmented rows on every control change.
# --------------------------------------------------------------------------
_MISMATCH_COLORS = {
    "domain": ["Over-automated (under-data)", "Over-automated", "Under-automated", "Aligned"],
    "range": ["#9a3a1c", "#b0431e", "#1F7A82", "#cbd5e1"],
}

CHARTS = [
    {
        "id": "mismatch_by_category",
        "title": "Campaigns by mismatch category",
        "mark": {"type": "bar"},
        "transform": [
            {"filter": "datum.status == 'scored'"},
            {"calculate": "datum.mismatch != '' ? datum.mismatch : 'Aligned'", "as": "flag"},
            {"aggregate": [{"op": "count", "as": "campaigns"},
                           {"op": "sum", "field": "cost", "as": "spend"}],
             "groupby": ["flag"]},
        ],
        "encoding": {
            "y": {"field": "flag", "type": "nominal", "title": None,
                  "scale": {"domain": _MISMATCH_COLORS["domain"]}},
            "x": {"field": "campaigns", "type": "quantitative", "title": "Campaigns"},
            "color": {"field": "flag", "type": "nominal", "legend": None, "scale": _MISMATCH_COLORS},
            "tooltip": [{"field": "flag", "title": "Mismatch"},
                        {"field": "campaigns", "title": "Campaigns"},
                        {"field": "spend", "title": "Spend", "format": ",.2f"}],
        },
        "height": 140,
        "md": True, "widget": True,
    },
    {
        "id": "maturity_vs_conv30",
        "title": "Scored campaigns — Data Maturity Score vs conversions (30d)",
        "mark": {"type": "point"},
        "transform": [
            {"filter": "datum.status == 'scored'"},
            {"calculate": "datum.mismatch != '' ? datum.mismatch : 'Aligned'", "as": "flag"},
        ],
        "encoding": {
            "x": {"field": "conv30", "type": "quantitative", "title": "Conversions (30d)"},
            "y": {"field": "maturity_score", "type": "quantitative", "title": "Data Maturity Score"},
            "color": {"field": "flag", "type": "nominal", "title": None, "scale": _MISMATCH_COLORS},
            "tooltip": [{"field": "campaign", "title": "Campaign"},
                        {"field": "flag", "title": "Mismatch"},
                        {"field": "maturity_score", "title": "Maturity score", "format": ".2f"},
                        {"field": "conv30", "title": "Conv30", "format": ".2f"}],
        },
        "height": 280,
        "md": True, "widget": False,
    },
]


# --------------------------------------------------------------------------
# The spec object the toolkit consumes.
# --------------------------------------------------------------------------
SPEC = {
    "slug_prefix": "bidding-strategy-maturity",
    "row_noun": "campaigns",
    "title": "Bidding Strategy — Data Maturity Score",
    "about": {
        "summary": "Scores every campaign's readiness for automated bidding (a 0-100 Data Maturity "
            "Score from conversion volume, value-variance, and tracking-confidence) and compares it "
            "to the bidding strategy actually running. Over-automated means the strategy is more "
            "aggressive than the data supports; under-automated means the data supports more "
            "automation than is switched on. A campaign automating on fewer than the gate's "
            "conversions/30d is flagged Critical regardless of its score.",
        "legend": [
            {"label": "Over-automated (under-data)", "desc": "Running an automated strategy "
             "(Enhanced CPC or above) with conv30 below the automation gate — Critical."},
            {"label": "Over-automated", "desc": "Current tier exceeds the recommended tier by more "
             "than the tier-gap threshold."},
            {"label": "Under-automated", "desc": "Current tier is below the recommended tier by more "
             "than the tier-gap threshold — upside left uncaptured."},
        ],
    },
    "methodology_ref": "references/bidding-strategy-maturity.md",
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
    # xlsx layout is attached in bidding_xlsx_spec to keep this module
    # stdlib-only and import-light; build_bidding_report wires it in for xlsx.
}
