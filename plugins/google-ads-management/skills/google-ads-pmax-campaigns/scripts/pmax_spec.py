#!/usr/bin/env python3
"""Render spec for the Performance Max momentum filter — adapts pmax_core's model
to the shared render toolkit (_shared/render). Stdlib only.

The classification math lives once in pmax_core (Python) and is mirrored in
`JS_KERNEL` (browser); the Node-vs-Python equality gate keeps them in sync.

Honest 14-day window labels without touching the frozen toolkit: provenance leaves
window_90d/window_30d empty (so the renderers' hard-coded "90-day"/"30-day" labels
never render) and the real windows are surfaced here — md via `md_params`, html via
the `js_extra` "Comparison windows" panel.
"""
from __future__ import annotations

import pmax_core as core
from render import model as M  # noqa: E402  (source_label — HM-572 canonical "Data source" line)


def _money(v, cur):
    return f"{float(v):,.2f}" + (f" {cur}" if cur else "")


def _n(v):
    f = float(v or 0)
    return int(f) if f.is_integer() else round(f, 2)


def _ratio(v):
    return "—" if v is None else f"{v:.2f}×"


# --------------------------------------------------------------------------
# Markdown adapters
# --------------------------------------------------------------------------
def md_params(model):
    pr, p = model["provenance"], model["params"]
    return [
        ("Last 14 days", pr.get("window_last") or "—"),
        ("Previous 14 days", pr.get("window_prev") or "—"),
        ("Data source", M.source_label(pr.get("source"))),
        ("Thresholds", f"ROAS up > {p['roas_up_multiple']:.2f}× prev · "
                       f"ROAS down < {p['roas_down_multiple']:.2f}× prev · "
                       f"min spend/window {p['min_cost']:.2f}"),
        ("Diagnostic thresholds", f"asset-group concentration ≥ {p['concentration_top_share_threshold'] * 100:.0f}% "
                                  f"of a campaign's spend in one group (2+ active) · "
                                  f"PMax/Search cannibalization ≥ {p['cannibalization_share_threshold'] * 100:.0f}% "
                                  f"PMax share of paired spend"),
    ]


def md_kpis(model):
    s = model["summary"]
    cur = model["provenance"]["currency"]
    return [
        ("Block 1 — scaling winners", str(s["block1"])),
        ("Block 2 — declining losers", str(s["block2"])),
        ("Winner spend (last 14d)", _money(s["winners_spend"], cur)),
        ("Loser spend (last 14d)", _money(s["losers_spend"], cur)),
        ("Universe", f"{s['universe']} Pmax campaigns ({s['scored']} active, "
                     f"{s['no_activity']} no-activity)"),
    ]


def md_narrative(model):
    if model["summary"]["total"] != 0:
        return []
    return [
        "> **0 / 0 is a valid result, not an error.** Under the rule as written no Performance Max "
        "campaign both moved its conversions and swung its ROAS past the bar (up > "
        f"{model['params']['roas_up_multiple']:.2f}× or down < {model['params']['roas_down_multiple']:.2f}× "
        "the prior 14 days). The sensitivity tables below show where winners/losers would start to "
        "appear if the ROAS bars were relaxed, and the near-miss lists show the campaigns closest to "
        "the bar. A steady account is a good thing — present it honestly rather than forcing hits.",
    ]


def _block_table(model, block, title, action):
    cur = model["provenance"]["currency"]
    rows = [r for r in model["rows"] if r["block"] == block]
    return {
        "title": title,
        "note": action,
        "headers": ["Campaign", "Conv (prev → last)", "ROAS (prev → last)", "ROAS ×",
                    f"Spend last ({cur})" if cur else "Spend last"],
        "aligns": ["l", "r", "r", "r", "r"],
        "rows": [[r["campaign"], f"{_n(r['conv_prev'])} → {_n(r['conv_last'])}",
                  f"{r['roas_prev']:.2f} → {r['roas_last']:.2f}", _ratio(r["roas_ratio"]),
                  f"{r['cost_last']:,.2f}"] for r in rows],
        "empty": "_None at the current thresholds._",
    }


def _asset_group_concentration_section(model):
    cur = model["provenance"]["currency"]
    p = model["params"]
    rows = model.get("asset_group_concentration") or []
    return {
        "title": "Asset-group concentration",
        "note": (f"Share of last-window spend in each PMax campaign's single largest asset "
                 f"group. Flagged (risk) at ≥ {p['concentration_top_share_threshold'] * 100:.0f}% "
                 "with 2+ active asset groups — see references/pmax-momentum-filter.md."),
        "headers": ["Campaign", "Active/Total groups", "Top group share", "HHI", "Effective N",
                    f"Spend ({cur})" if cur else "Spend", "Risk"],
        "aligns": ["l", "r", "r", "r", "r", "r", "l"],
        "rows": [[r["campaign"], f"{r['asset_groups_active']}/{r['asset_groups']}",
                  f"{r['top_share'] * 100:.1f}%", f"{r['hhi']:.1f}", f"{r['effective_n']:.2f}",
                  f"{r['cost']:,.2f}", "yes" if r["risk"] else "no"] for r in rows],
        "empty": "_No asset-group breakdown pulled this run._",
    }


def _cannibalization_section(model):
    p = model["params"]
    rows = model.get("cannibalization") or []
    return {
        "title": "PMax vs Search cannibalization signal (heuristic)",
        "note": (f"Name-theme overlap between active PMax campaigns and Search campaigns "
                 "(token match — not verified keyword/audience overlap). Flagged (risk) when "
                 f"the PMax campaign's share of the paired last-window spend is ≥ "
                 f"{p['cannibalization_share_threshold'] * 100:.0f}% and combined spend clears "
                 "the floor — see references/pmax-momentum-filter.md."),
        "headers": ["PMax campaign", "Matched Search campaign(s)", "PMax spend", "Search spend",
                    "PMax share", "Risk"],
        "aligns": ["l", "l", "r", "r", "r", "l"],
        "rows": [[r["campaign"], ", ".join(r["matched_search_campaigns"]),
                  f"{r['pmax_cost_last']:,.2f}", f"{r['search_cost_last']:,.2f}",
                  (f"{r['pmax_theme_share'] * 100:.1f}%" if r["pmax_theme_share"] is not None else "—"),
                  "yes" if r["risk"] else "no"] for r in rows],
        "empty": "_No PMax campaign shares a name-theme with an active Search campaign this run._",
    }


def _recommendations_section(model):
    recs = model.get("recommendations") or []
    return {
        "title": "Advisor recommendations",
        "note": "Prioritized Critical → High → Medium; every figure is read off this model — "
                "see google-ads-foundation's advisor output contract.",
        "headers": ["Severity", "Recommendation", "Why (model numbers)", "Action", "Artifact"],
        "aligns": ["l", "l", "l", "l", "l"],
        "rows": [[r["severity"], r["title"], r["detail"], r["action"], r["artifact"]] for r in recs],
        "empty": "_No concentration or cannibalization risk flagged at the current thresholds._",
    }


def md_sections(model):
    cur = model["provenance"]["currency"]
    secs = [
        _block_table(model, "Block 1", "Scaling winners (Block 1)",
                     "Conversions up and ROAS surged past the up-bar — candidates to scale budget."),
        _block_table(model, "Block 2", "Declining losers (Block 2)",
                     "Conversions down and ROAS collapsed past the down-bar — investigate, restructure or cut."),
        {
            "title": "ROAS-up sensitivity (Block 1)",
            "note": "Scaling winners as the up-multiple changes (other params held current).",
            "headers": ["ROAS up ×", "Block 1"],
            "aligns": ["l", "r"],
            "rows": [[f"{r['multiple']:.2f}" + (" ← current" if r["is_current"] else ""), r["block1"]]
                     for r in model["sensitivity_up"]],
        },
        {
            "title": "ROAS-down sensitivity (Block 2)",
            "note": "Declining losers as the down-multiple changes (other params held current).",
            "headers": ["ROAS down ×", "Block 2"],
            "aligns": ["l", "r"],
            "rows": [[f"{r['multiple']:.2f}" + (" ← current" if r["is_current"] else ""), r["block2"]]
                     for r in model["sensitivity_down"]],
        },
    ]
    nm1 = model["near_misses_block1"][:15]
    secs.append({
        "title": "Near misses — Block 1 (would scale if up-bar lower)",
        "note": "Conversions up + spend over the floor, ranked by ROAS momentum; qualifies for any up-multiple ≤ the value shown.",
        "headers": ["Campaign", "ROAS (prev → last)", "Qualifies if up × ≤", "Now?"],
        "aligns": ["l", "r", "r", "l"],
        "rows": [[r["campaign"], f"{r['roas_prev']:.2f} → {r['roas_last']:.2f}",
                  _ratio(r["qualify_if_up_multiple_le"]), "yes" if r["currently_qualifies"] else "no"]
                 for r in nm1],
        "empty": "_None._",
    })
    nm2 = model["near_misses_block2"][:15]
    secs.append({
        "title": "Near misses — Block 2 (would flag if down-bar higher)",
        "note": "Conversions down + prior spend over the floor, steepest decline first; qualifies for any down-multiple ≥ the value shown.",
        "headers": ["Campaign", "ROAS (prev → last)", "Qualifies if down × ≥", "Now?"],
        "aligns": ["l", "r", "r", "l"],
        "rows": [[r["campaign"], f"{r['roas_prev']:.2f} → {r['roas_last']:.2f}",
                  _ratio(r["qualify_if_down_multiple_ge"]), "yes" if r["currently_qualifies"] else "no"]
                 for r in nm2],
        "empty": "_None._",
    })
    na = [r for r in model["rows"] if r["status"] == "no_activity"]
    secs.append({
        "title": "No-activity campaigns (held out)",
        "note": "Enabled Pmax campaigns with no impressions in either window — no trend to evaluate. "
                "Listed so nothing is silently dropped.",
        "headers": ["Campaign"],
        "aligns": ["l"],
        "rows": [[r["campaign"]] for r in na],
        "empty": "_None — every Pmax campaign served in at least one window._",
    })
    secs.append(_asset_group_concentration_section(model))
    secs.append(_cannibalization_section(model))
    secs.append(_recommendations_section(model))
    return secs


def md_rows(model):
    """Every Pmax campaign with both windows + status + signal (the no-row-loss
    layer)."""
    cur = model["provenance"]["currency"]
    headers = ["Campaign", "Status", "Impr last", f"Cost last ({cur})" if cur else "Cost last",
               "Conv last", "ROAS last", "Impr prev", f"Cost prev ({cur})" if cur else "Cost prev",
               "Conv prev", "ROAS prev", "ROAS ×", "Signal"]
    out = []
    for r in model["rows"]:
        out.append([
            r["campaign"], "active" if r["status"] == "scored" else "no activity",
            _n(r["impr_last"]), f"{r['cost_last']:,.2f}", _n(r["conv_last"]), f"{r['roas_last']:.2f}",
            _n(r["impr_prev"]), f"{r['cost_prev']:,.2f}", _n(r["conv_prev"]), f"{r['roas_prev']:.2f}",
            _ratio(r["roas_ratio"]), r["block"] or "",
        ])
    return {
        "title": "All Performance Max campaigns (every row, with status)",
        "note": "No row loss: every campaign appears here, classified or held out as no-activity. "
                "Sorted by last-window spend (highest first).",
        "headers": headers,
        "aligns": ["l", "l", "r", "r", "r", "r", "r", "r", "r", "r", "r", "l"],
        "rows": out,
        "empty": "_No Performance Max campaigns in the windows._",
    }


# --------------------------------------------------------------------------
# HTML adapters
# --------------------------------------------------------------------------
def html_embed(model):
    return {
        "provenance": model["provenance"],
        "params": model["params"],
        "summary": model["summary"],
        "up_ladder": model["up_ladder"],
        "down_ladder": model["down_ladder"],
        "asset_group_concentration": model.get("asset_group_concentration") or [],
        "cannibalization": model.get("cannibalization") or [],
        "recommendations": model.get("recommendations") or [],
        "rows": [{
            "campaign": r["campaign"], "status": r["status"],
            "impr_last": r["impr_last"], "cost_last": r["cost_last"], "conv_last": r["conv_last"],
            "roas_last": r["roas_last"], "impr_prev": r["impr_prev"], "cost_prev": r["cost_prev"],
            "conv_prev": r["conv_prev"], "roas_prev": r["roas_prev"], "roas_ratio": r["roas_ratio"],
        } for r in model["rows"]],
    }


HTML_CONTROLS = [
    {"key": "roas_up_multiple", "label": "ROAS up multiple (Block 1)", "kind": "slider",
     "min": 1.0, "max": 3.0, "step": 0.05, "sub": "ROAS(last) > this × ROAS(prev)"},
    {"key": "roas_down_multiple", "label": "ROAS down multiple (Block 2)", "kind": "slider",
     "min": 0.0, "max": 1.0, "step": 0.05, "sub": "ROAS(last) < this × ROAS(prev)"},
    {"key": "min_cost", "label": "Minimum spend per window", "kind": "number",
     "min": 0, "step": 50},
]

HTML_COLUMNS = [
    {"key": "campaign", "label": "Campaign"},
    {"key": "status", "label": "Status", "fmt": "status"},
    {"key": "conv_prev", "label": "Conv prev", "num": True, "fmt": "num"},
    {"key": "conv_last", "label": "Conv last", "num": True, "fmt": "num"},
    {"key": "roas_prev", "label": "ROAS prev", "num": True, "fmt": "num"},
    {"key": "roas_last", "label": "ROAS last", "num": True, "fmt": "num"},
    {"key": "roas_ratio", "label": "ROAS ×", "num": True, "fmt": "num"},
    {"key": "cost_last", "label": "Cost last", "num": True, "fmt": "money"},
    {"key": "block", "label": "Signal", "fmt": "block"},
]

HTML_KPIS = [
    {"label": "Scaling winners", "key": "b1", "cls": "b1"},
    {"label": "Declining losers", "key": "b2", "cls": "b2"},
    {"label": "Total flagged", "key": "total"},
    {"label": "Winner spend", "key": "winners_spend", "money": True},
    {"label": "Loser spend", "key": "losers_spend", "money": True},
]

# Mirrors pmax_core.classify_row / summarize exactly (verified by the Node-vs-Python
# gate). Assigns the engine's `classify` and `summarize`.
JS_KERNEL = r"""
classify = function(r,P){
  if(r.status!=="scored") return {block:"", conv_up:null, roas_up:null, conv_down:null, roas_down:null};
  const up=P.roas_up_multiple, down=P.roas_down_multiple, floor=P.min_cost;
  const conv_up = r.conv_last > r.conv_prev;
  const conv_down = r.conv_last < r.conv_prev;
  const roas_up = r.roas_last > up * r.roas_prev;
  const roas_down = r.roas_last < down * r.roas_prev;
  let block="";
  if(conv_up && roas_up && r.impr_last>0 && r.cost_last>floor) block="Block 1";
  else if(conv_down && roas_down && r.impr_prev>0 && r.cost_prev>floor) block="Block 2";
  return {block, conv_up, roas_up, conv_down, roas_down};
};
summarize = function(rows,P){
  let b1=0,b2=0,winners=0,losers=0,scored=0,na=0,sl=0,sp=0;
  rows.forEach(r=>{const c=classify(r,P);
    if(r.status==="scored") scored++; else na++;
    sl+=r.cost_last; sp+=r.cost_prev;
    if(c.block==="Block 1"){b1++; winners+=r.cost_last;}
    else if(c.block==="Block 2"){b2++; losers+=r.cost_last;}});
  const R=v=>Math.round(v*100)/100;
  return {b1,b2,total:b1+b2,universe:rows.length,scored:scored,no_activity:na,
          winners_spend:R(winners),losers_spend:R(losers),spend_last:R(sl),spend_prev:R(sp)};
};
"""

# Comparison-windows panel (honest 14-day labels) + live block logic + the two
# sensitivity strips + near-miss panels. Recompute on every control change.
JS_EXTRA = r"""
renderExtra = function(host,H){
  const pr = MODEL.provenance||{};
  function sensUp(){
    const saved=P.roas_up_multiple,out=[];
    MODEL.up_ladder.forEach(m=>{P.roas_up_multiple=m; const s=summarize(MODEL.rows,P);
      out.push({m,b1:s.b1,cur:Math.abs(m-saved)<1e-9})});
    P.roas_up_multiple=saved; return out;
  }
  function sensDown(){
    const saved=P.roas_down_multiple,out=[];
    MODEL.down_ladder.forEach(m=>{P.roas_down_multiple=m; const s=summarize(MODEL.rows,P);
      out.push({m,b2:s.b2,cur:Math.abs(m-saved)<1e-9})});
    P.roas_down_multiple=saved; return out;
  }
  function nearUp(){
    const floor=P.min_cost,pool=[];
    MODEL.rows.forEach(r=>{ if(r.status!=="scored") return;
      if(!(r.conv_last>r.conv_prev && r.impr_last>0 && r.cost_last>floor)) return;
      const ratio = r.roas_prev>0? r.roas_last/r.roas_prev : null;
      pool.push({r,ratio,now:r.roas_last>P.roas_up_multiple*r.roas_prev}); });
    pool.sort((a,b)=>{const an=a.ratio==null,bn=b.ratio==null; if(an!==bn)return an-bn; return (b.ratio||0)-(a.ratio||0);});
    return pool.slice(0,15);
  }
  function nearDown(){
    const floor=P.min_cost,pool=[];
    MODEL.rows.forEach(r=>{ if(r.status!=="scored") return;
      if(!(r.conv_last<r.conv_prev && r.impr_prev>0 && r.cost_prev>floor)) return;
      const ratio = r.roas_prev>0? r.roas_last/r.roas_prev : null;
      pool.push({r,ratio,now:r.roas_last<P.roas_down_multiple*r.roas_prev}); });
    pool.sort((a,b)=>{const an=a.ratio==null,bn=b.ratio==null; if(an!==bn)return an-bn; return (a.ratio||0)-(b.ratio||0);});
    return pool.slice(0,15);
  }
  const up=(+P.roas_up_multiple).toFixed(2), down=(+P.roas_down_multiple).toFixed(2), floor=H.money(P.min_cost);
  let h='<div class="card"><h2>Comparison windows</h2>'+
    `<div class="logic"><b>Last 14 days</b> — ${H.esc(pr.window_last||"—")}</div>`+
    `<div class="logic"><b>Previous 14 days</b> — ${H.esc(pr.window_prev||"—")}</div></div>`;
  h+='<div class="card"><h2>Block logic (live)</h2>'+
    `<div class="logic"><b>Block 1 — scaling winner</b> — conv(last) &gt; conv(prev) · ROAS(last) &gt; ${up} × ROAS(prev) · impr(last) &gt; 0 · cost(last) &gt; ${floor}</div>`+
    `<div class="logic"><b>Block 2 — declining loser</b> — conv(last) &lt; conv(prev) · ROAS(last) &lt; ${down} × ROAS(prev) · impr(prev) &gt; 0 · cost(prev) &gt; ${floor}</div></div>`;
  h+='<div class="card sens"><h2>ROAS sensitivity</h2>'+
    '<div class="note">How many campaigns flag as each ROAS bar moves (other params held current).</div>'+
    '<div class="row" style="align-items:flex-start;gap:18px">'+
    '<table style="flex:1"><thead><tr><th>Up ×</th><th class="num">Block 1</th></tr></thead><tbody>'+
    sensUp().map(r=>`<tr><td class="${r.cur?'cur':''}">${r.m.toFixed(2)}${r.cur?' ←':''}</td><td class="num ${r.cur?'cur':''}">${r.b1}</td></tr>`).join("")+
    '</tbody></table>'+
    '<table style="flex:1"><thead><tr><th>Down ×</th><th class="num">Block 2</th></tr></thead><tbody>'+
    sensDown().map(r=>`<tr><td class="${r.cur?'cur':''}">${r.m.toFixed(2)}${r.cur?' ←':''}</td><td class="num ${r.cur?'cur':''}">${r.b2}</td></tr>`).join("")+
    '</tbody></table></div></div>';
  h+='<div class="card"><h2>Near misses</h2><div class="note">Meet every condition except (maybe) the ROAS bar.</div>';
  [["Block 1 — would scale",nearUp(),"up × ≤"],["Block 2 — would flag",nearDown(),"down × ≥"]].forEach(([lbl,nm,hint])=>{
    h+=`<div class="note" style="margin-top:8px"><b>${lbl}</b></div>`;
    if(!nm.length){h+='<div class="note">None.</div>';return;}
    h+=`<table><thead><tr><th>Campaign</th><th class="num">ROAS prev→last</th><th class="num">Qual if ${hint}</th><th>Now</th></tr></thead><tbody>`;
    nm.forEach(({r,ratio,now})=>{h+=`<tr><td>${H.esc(r.campaign)}</td><td class="num">${r.roas_prev.toFixed(2)}→${r.roas_last.toFixed(2)}</td><td class="num">${ratio==null?"—":ratio.toFixed(2)}</td><td>${now?'yes':'no'}</td></tr>`;});
    h+='</tbody></table>';
  });
  h+='</div>';
  // M1.4 — asset-group concentration + cannibalization: computed ONCE by
  // Python at build time and embedded on MODEL; this panel only formats and
  // displays that data (no recompute), so it can never drift from the model.
  const agc = MODEL.asset_group_concentration||[];
  h+='<div class="card"><h2>Asset-group concentration</h2>'+
    '<div class="note">Share of last-window spend in the single largest asset group per campaign.</div>';
  if(!agc.length){
    h+='<div class="note">No asset-group breakdown pulled this run.</div>';
  } else {
    h+='<table><thead><tr><th>Campaign</th><th class="num">Active/Total</th><th class="num">Top share</th><th class="num">HHI</th><th class="num">Eff. N</th><th class="num">Spend</th><th>Risk</th></tr></thead><tbody>';
    agc.forEach(r=>{h+=`<tr><td>${H.esc(r.campaign)}</td><td class="num">${r.asset_groups_active}/${r.asset_groups}</td><td class="num">${(r.top_share*100).toFixed(1)}%</td><td class="num">${r.hhi.toFixed(1)}</td><td class="num">${r.effective_n.toFixed(2)}</td><td class="num">${H.money(r.cost)}</td><td>${r.risk?'yes':'no'}</td></tr>`;});
    h+='</tbody></table>';
  }
  h+='</div>';
  const cnb = MODEL.cannibalization||[];
  h+='<div class="card"><h2>PMax vs Search cannibalization signal (heuristic)</h2>'+
    '<div class="note">Name-theme overlap only — not verified keyword/audience overlap.</div>';
  if(!cnb.length){
    h+='<div class="note">No PMax campaign shares a name-theme with an active Search campaign this run.</div>';
  } else {
    h+='<table><thead><tr><th>PMax campaign</th><th>Matched Search campaign(s)</th><th class="num">PMax spend</th><th class="num">Search spend</th><th class="num">PMax share</th><th>Risk</th></tr></thead><tbody>';
    cnb.forEach(r=>{h+=`<tr><td>${H.esc(r.campaign)}</td><td>${H.esc(r.matched_search_campaigns.join(", "))}</td><td class="num">${H.money(r.pmax_cost_last)}</td><td class="num">${H.money(r.search_cost_last)}</td><td class="num">${r.pmax_theme_share==null?"—":(r.pmax_theme_share*100).toFixed(1)+"%"}</td><td>${r.risk?'yes':'no'}</td></tr>`;});
    h+='</tbody></table>';
  }
  h+='</div>';
  const recs = MODEL.recommendations||[];
  h+='<div class="card"><h2>Advisor recommendations</h2>';
  if(!recs.length){
    h+='<div class="note">No concentration or cannibalization risk flagged at the current thresholds.</div>';
  } else {
    recs.forEach(r=>{h+=`<div class="logic"><b>[${H.esc(r.severity)}] ${H.esc(r.title)}</b><br>${H.esc(r.detail)}<br><i>${H.esc(r.action)}</i></div>`;});
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
# row shapes (model rows and the html embed): campaign, status, cost_last,
# roas_last, roas_prev, block.
# --------------------------------------------------------------------------
_FLAG_COLORS = {"domain": ["Block 1", "Block 2", "Unflagged"],
                "range": ["#0369a1", "#7c3aed", "#cbd5e1"]}  # match the b1/b2 badges

CHARTS = [
    {
        "id": "spend_by_signal",
        "title": "Last-14d spend by signal",
        "mark": {"type": "bar"},
        "transform": [
            {"filter": "datum.block != ''"},
            {"aggregate": [{"op": "sum", "field": "cost_last", "as": "spend"},
                           {"op": "count", "as": "campaigns"}],
             "groupby": ["block"]},
        ],
        "encoding": {
            "y": {"field": "block", "type": "nominal", "title": None,
                  "scale": {"domain": ["Block 1", "Block 2"]}},
            "x": {"field": "spend", "type": "quantitative", "title": "Spend (last 14 days)"},
            "color": {"field": "block", "type": "nominal", "legend": None,
                      "scale": {"domain": ["Block 1", "Block 2"],
                                "range": ["#0369a1", "#7c3aed"]}},
            "tooltip": [{"field": "block", "title": "Signal"},
                        {"field": "spend", "title": "Spend (last 14d)", "format": ",.2f"},
                        {"field": "campaigns", "title": "Campaigns"}],
        },
        "height": 120,
        "md": True, "widget": True,
    },
    {
        "id": "roas_spend_scatter",
        "title": "Active campaigns — last-14d ROAS vs spend (flagged campaigns colored)",
        "mark": {"type": "point"},
        "transform": [
            {"filter": "datum.status == 'scored'"},
            {"calculate": "datum.block != '' ? datum.block : 'Unflagged'", "as": "flag"},
        ],
        "encoding": {
            "x": {"field": "cost_last", "type": "quantitative", "title": "Spend (last 14 days)"},
            "y": {"field": "roas_last", "type": "quantitative", "title": "ROAS (last 14 days)"},
            "color": {"field": "flag", "type": "nominal", "title": None, "scale": _FLAG_COLORS},
            "tooltip": [{"field": "campaign", "title": "Campaign"},
                        {"field": "flag", "title": "Signal"},
                        {"field": "cost_last", "title": "Spend (last 14d)", "format": ",.2f"},
                        {"field": "roas_prev", "title": "ROAS prev", "format": ".2f"},
                        {"field": "roas_last", "title": "ROAS last", "format": ".2f"}],
        },
        "height": 280,
        "md": True, "widget": False,
    },
]


# --------------------------------------------------------------------------
# The spec object the toolkit consumes.
# --------------------------------------------------------------------------
SPEC = {
    "slug_prefix": "pmax-momentum",
    "row_noun": "campaigns",
    "title": "Performance Max Momentum",
    "about": {
        "summary": "Compares each Performance Max campaign across two 14-day windows to catch momentum shifts. The ROAS-up and ROAS-down multiples set how big the swing must be to flag, and the minimum spend filters out noise from tiny-spend campaigns.",
        "legend": [
            {"label": "Block 1", "desc": "Scaling winner — conversions up and last-14d ROAS beats (up multiple × prior-14d ROAS). Give it room."},
            {"label": "Block 2", "desc": "Declining loser — conversions down and last-14d ROAS fell below (down multiple × prior-14d ROAS). Investigate."},
        ],
    },
    "methodology_ref": "references/pmax-momentum-filter.md",
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
    # xlsx layout is attached in pmax_xlsx_spec to keep this module stdlib-only;
    # the orchestrators wire it in when xlsx is requested.
}
