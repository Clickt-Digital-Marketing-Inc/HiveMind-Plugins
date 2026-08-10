#!/usr/bin/env python3
"""Render spec for the PMax listing-group waste filter — adapts pmax_listing_core's
model to the shared render toolkit (_shared/render). Relies on `analytics` (a
_shared module — callers put `_shared` on sys.path before importing this file).

The classification math lives once in pmax_listing_core (Python) and is mirrored
in `JS_KERNEL` (browser) — the Node-vs-Python equality gate keeps them in sync.
`JS_KERNEL` splices in `analytics.JS_MIRROR` verbatim so the tier-concentration
+ signal math (HM-539) is the same shared primitive on both sides, not a
re-implementation.

Two universes share one engine and one factor slider:
  * partitions (model['rows'])  — the primary, built-in no-row-loss table
  * products   (model['items']) — surfaced live in JS_EXTRA (renderExtra)
"""
from __future__ import annotations

import analytics  # noqa: E402  (_shared module; caller inserts _shared on sys.path)
from render import model as M  # noqa: E402  (source_label — HM-572 canonical "Data source" line)


def _money(v, cur):
    if v is None:
        return ""
    return f"{float(v):,.2f}" + (f" {cur}" if cur else "")


def _int(v):
    return int(v) if float(v).is_integer() else round(v, 2)


# --------------------------------------------------------------------------
# Markdown adapters
# --------------------------------------------------------------------------
def md_params(model):
    p = model["params"]
    f = p["expensiveness_factor"]
    source = model["provenance"].get("source")
    return [
        ("Data source", M.source_label(source)),
        ("Expensiveness factor", f"{f:.2f}"),
        ("Block 1 bar", f"listing-group cost/conv > {f:.2f} × its campaign cost/conv (conv > 0)"),
        ("Block 2 bar", f"listing-group clicks > {f:.2f} × its campaign clicks/conv "
                        "(conv = 0, campaign conv > 0)"),
        ("Tier concentration top-N", str(p["concentration_top_n"])),
        ("Tier signal bar — over-concentrated",
         f"a unit's cost_share of its universe's 30d spend > {p['concentration_share_min']:.2f}"),
        ("Tier signal bar — weak ROAS", f"conv. value / cost < {p['weak_roas_max']:.2f}"),
    ]


def md_kpis(model):
    s = model["summary"]
    i = s["item"]
    cur = model["provenance"]["currency"]
    return [
        ("Partitions — Block 1 (expensive converters)", str(s["block1"])),
        ("Partitions — Block 2 (zero-conv waste)", str(s["block2"])),
        ("Partitions — flagged spend (30d)", _money(s["flagged_spend"], cur)),
        ("Products — Block 1 / Block 2", f"{i['block1']} / {i['block2']}"),
        ("Products — flagged spend (30d)", _money(i["flagged_spend"], cur)),
        ("Partitions — tier signals (concentrated + weak ROAS)", str(s["tier_signals"])),
        ("Partitions — tier signal spend (30d)", _money(s["signal_spend"], cur)),
        ("Products — tier signals (concentrated + weak ROAS)", str(i["tier_signals"])),
        ("Products — tier signal spend (30d)", _money(i["signal_spend"], cur)),
        ("Universe", f"{s['universe']} partitions ({s['scored']} scored, {s['no_benchmark']} "
            f"no-benchmark) · {i['universe']} products ({i['scored']} scored, {i['no_benchmark']} "
            "no-benchmark)"),
    ]


def md_narrative(model):
    s = model["summary"]
    out = []
    # Empty-universe root cause (HM-599): a feedless lead-gen account legitimately
    # returns zero listing-group partitions AND zero products — that is not missing
    # data, it is the honest shape of the account. Say so plainly instead of letting
    # a silent 0/0 read as "nothing found" or "the pull failed". The campaign
    # benchmark table (model['benchmarks']) still renders — it comes from campaign-
    # level metrics, independent of any retail feed.
    if s["universe"] == 0 and s["item"]["universe"] == 0:
        out.append(
            "> **No retail listing groups returned — this account has no Merchant Center feed "
            "/ runs lead-gen PMax.** There are zero listing-group partitions and zero products to "
            "filter, so nothing was dropped and nothing was fabricated — the campaign benchmark "
            "table below (30-day cost/clicks/conversions per campaign) still renders for context, "
            "since it comes from campaign-level metrics rather than a retail feed.")
        return out
    if s["total"] != 0 or s["item"]["total"] != 0:
        return out
    f = model["params"]["expensiveness_factor"]
    out.append(
        f"> **0 / 0 is a clean result, not an error.** At the {f:.2f}× expensiveness factor, no "
        "listing group or product converts above its campaign's cost/conversion (Block 1) or burns "
        "more clicks than its campaign needs per conversion while never converting (Block 2). The "
        "sensitivity tables below show where flags would start to appear if the factor were "
        "relaxed, and the near-miss lists show the units closest to the bar.")
    return out


def _sensitivity_section(sens, title, note):
    return {
        "title": title,
        "note": note,
        "headers": ["Expensiveness factor", "Block 1", "Block 2", "Total"],
        "aligns": ["l", "r", "r", "r"],
        "rows": [[f"{r['factor']:.2f}" + (" ← current" if r["is_current"] else ""),
                  r["block1"], r["block2"], r["total"]] for r in sens],
    }


def _near_miss_section(nm, block, cur, label_name):
    nm = nm[:15]
    if block == "Block 1":
        headers = [label_name, "Campaign", f"Cost ({cur})" if cur else "Cost", "Cost/conv",
                   "Campaign cost/conv", "Qualifies if factor ≤", "Now?"]
        aligns = ["l", "l", "r", "r", "r", "r", "l"]
        rows = [[r["label"], r["campaign"], f"{r['cost']:,.2f}",
                 _money(r["lg_cpa"], ""), _money(r["camp_cpa"], ""),
                 f"{r['qualify_if_factor_le']:.2f}",
                 "yes" if r["currently_qualifies"] else "no"] for r in nm]
    else:
        headers = [label_name, "Campaign", "Clicks", "Campaign clicks/conv",
                   "Qualifies if factor ≤", "Now?"]
        aligns = ["l", "l", "r", "r", "r", "l"]
        rows = [[r["label"], r["campaign"], _int(r["clicks"]),
                 (f"{r['camp_clicks_per_conv']:.2f}" if r["camp_clicks_per_conv"] is not None else ""),
                 f"{r['qualify_if_factor_le']:.2f}",
                 "yes" if r["currently_qualifies"] else "no"] for r in nm]
    return {
        "title": f"Near misses — {block}",
        "note": "Units on the right side of the conversion split, ranked by closeness to the bar.",
        "headers": headers, "aligns": aligns, "rows": rows, "empty": "_None._",
    }


def _excluded_section(rows, cur, unit_word):
    nb = [r for r in rows if r["status"] == "no_benchmark"]
    by_camp = {}
    for r in nb:
        by_camp[r["campaign"]] = by_camp.get(r["campaign"], 0) + 1
    return {
        "title": f"Excluded — campaigns with no usable benchmark ({unit_word})",
        "note": ("These campaigns had 0 conversions (30d), so cost/conv and clicks/conv are "
                 f"undefined and their {unit_word} cannot be scored. Listed so nothing is dropped."),
        "headers": ["Campaign", f"{unit_word.capitalize()} held out"],
        "aligns": ["l", "r"],
        "rows": [[camp, n] for camp, n in sorted(by_camp.items(), key=lambda kv: -kv[1])],
        "empty": f"_None — every {unit_word[:-1]}'s campaign had conversions in the 30-day window._",
    }


def _full_units_section(rows, cur, title, label_name, with_group):
    headers = [label_name, "Campaign"]
    aligns = ["l", "l"]
    if with_group:
        headers.append("Asset group"); aligns.append("l")
    headers += ["Status", "Impr", "Clicks", f"Cost ({cur})" if cur else "Cost", "Conv",
                "Cost/conv", "Block"]
    aligns += ["l", "r", "r", "r", "r", "r", "l"]
    out = []
    for r in rows:
        row = [r["label"], r["campaign"]]
        if with_group:
            row.append(r["group"])
        row += [
            "scored" if r["status"] == "scored" else "no benchmark",
            _int(r["impressions"]), _int(r["clicks"]), f"{r['cost']:,.2f}", f"{r['conv']:.2f}",
            (_money(r["lg_cpa"], "") if r["lg_cpa"] is not None else "—"), r["block"] or "",
        ]
        out.append(row)
    return {
        "title": title,
        "note": "No row loss: every unit appears, scored or held out as no-benchmark. "
                "Sorted by cost (highest first).",
        "headers": headers, "aligns": aligns, "rows": out,
        "empty": "_No units in this universe._",
    }


def _recommendations_section(model):
    recs = model.get("recommendations") or []
    return {
        "title": "Prioritized recommendations",
        "note": "Critical → High → Medium, every figure traceable to the model in this report. "
                "This skill has no Editor apply-CSV — PMax listing-group/product exclusions are "
                "manual in the Google Ads web UI; the flagged rows below ARE the worklist.",
        "headers": ["Severity", "Recommendation", "Apply"],
        "aligns": ["l", "l", "l"],
        "rows": [[r["severity"], r["text"], r["artifact"]] for r in recs],
        "empty": "_Clean result — no Critical, High, or Medium items at the current thresholds._",
    }


def _concentration_section(model):
    s = model["summary"]
    i = s["item"]

    def row(name, c):
        return [name, c["n"], c["top_n"], f"{c['top_share'] * 100:.1f}%", f"{c['hhi']:.1f}",
                f"{c['effective_n']:.2f}"]

    return {
        "title": "Tier concentration (30d spend)",
        "note": "How concentrated 30-day spend is within each universe — top-N share, the "
                "Herfindahl-Hirschman Index (0–10,000; higher = more concentrated), and the "
                "effective number of equally-weighted units the concentration implies.",
        "headers": ["Universe", "Units", "Top-N", "Top-N share", "HHI", "Effective N"],
        "aligns": ["l", "r", "r", "r", "r", "r"],
        "rows": [row("Partitions", s["concentration"]), row("Products", i["concentration"])],
    }


def _tier_signal_section(rows, cur, unit_word, label_name):
    flagged = sorted((r for r in rows if r.get("tier_signal")), key=lambda r: -r["cost"])[:15]
    return {
        "title": f"Tier signals — {unit_word} (spend concentrated in a weak-ROAS tier)",
        "note": "Both fire on these rows: the unit's share of its universe's 30d spend exceeds "
                "the concentration bar AND its ROAS (conv. value / cost) is below the weak-ROAS "
                "bar — independent of the expensiveness-factor blocks above.",
        "headers": [label_name, "Campaign", f"Cost ({cur})" if cur else "Cost", "Spend share", "ROAS"],
        "aligns": ["l", "l", "r", "r", "r"],
        "rows": [[r["label"], r["campaign"], f"{r['cost']:,.2f}", f"{r['cost_share'] * 100:.1f}%",
                 (f"{r['roas']:.2f}" if r["roas"] is not None else "—")] for r in flagged],
        "empty": "_None — no unit is both over-concentrated and weak on ROAS._",
    }


def md_sections(model):
    cur = model["provenance"]["currency"]
    secs = []
    # --- advisor: recommendations first (lead with what to do), then the model ---
    secs.append(_recommendations_section(model))
    secs.append(_concentration_section(model))
    # --- partitions ---
    secs.append(_tier_signal_section(model["rows"], cur, "partitions", "Listing group"))
    secs.append(_sensitivity_section(
        model["sensitivity"], "Partition sensitivity",
        "How many listing-group partitions qualify as the expensiveness factor changes."))
    secs.append(_near_miss_section(model["near_misses_block1"], "Block 1", cur, "Listing group"))
    secs.append(_near_miss_section(model["near_misses_block2"], "Block 2", cur, "Listing group"))
    secs.append(_excluded_section(model["rows"], cur, "partitions"))
    # --- products (the item no-row-loss layer lives here) ---
    if model["summary"].get("has_items"):
        secs.append(_full_units_section(
            model["items"], cur, "Products — every item (with status)", "Product", with_group=False))
        secs.append(_tier_signal_section(model["items"], cur, "products", "Product"))
        secs.append(_sensitivity_section(
            model["item_sensitivity"], "Product sensitivity",
            "How many products qualify as the expensiveness factor changes."))
        secs.append(_near_miss_section(model["item_near_misses_block1"], "Block 1", cur, "Product"))
        secs.append(_near_miss_section(model["item_near_misses_block2"], "Block 2", cur, "Product"))
        secs.append(_excluded_section(model["items"], cur, "products"))
    return secs


def md_rows(model):
    """Every listing-group partition with a status — the primary no-row-loss layer."""
    cur = model["provenance"]["currency"]
    return _full_units_section(
        model["rows"], cur, "All listing-group partitions (every row, with status)",
        "Listing group", with_group=True)


# --------------------------------------------------------------------------
# HTML adapters
# --------------------------------------------------------------------------
def _embed_rows(rows):
    return [{
        "campaign": r["campaign"], "group": r["group"], "label": r["label"],
        "dimension": r["dimension"], "code": r["code"],
        "impressions": r["impressions"], "clicks": r["clicks"], "ctr": r["ctr"],
        "cost": r["cost"], "conv": r["conv"], "value": r["value"], "roas": r["roas"],
        "lg_cpa": r["lg_cpa"], "camp_cpa": r["camp_cpa"],
        "camp_clicks_per_conv": r["camp_clicks_per_conv"],
        "cost_share": r["cost_share"], "signal_flags": r["signal_flags"],
        "tier_signal": r["tier_signal"], "status": r["status"],
    } for r in rows]


def html_embed(model):
    return {
        "provenance": model["provenance"],
        "params": model["params"],
        "summary": model["summary"],
        "factor_ladder": model["factor_ladder"],
        "rows": _embed_rows(model["rows"]),
        "items": _embed_rows(model["items"]),
        "recommendations": model["recommendations"],
    }


HTML_CONTROLS = [
    {"key": "expensiveness_factor", "label": "Expensiveness factor", "kind": "slider",
     "min": 0.5, "max": 2.0, "step": 0.25, "sub": "× campaign cost/conv (B1) and clicks/conv (B2)"},
]

HTML_COLUMNS = [
    {"key": "label", "label": "Listing group"},
    {"key": "campaign", "label": "Campaign"},
    {"key": "group", "label": "Asset group"},
    {"key": "dimension", "label": "Dimension"},
    {"key": "status", "label": "Status", "fmt": "status"},
    {"key": "impressions", "label": "Impr", "num": True, "fmt": "int"},
    {"key": "clicks", "label": "Clicks", "num": True, "fmt": "int"},
    {"key": "cost", "label": "Cost", "num": True, "fmt": "money"},
    {"key": "conv", "label": "Conv", "num": True, "fmt": "num"},
    {"key": "lg_cpa", "label": "Cost/conv", "num": True, "fmt": "money"},
    {"key": "cost_share", "label": "Spend share", "num": True, "fmt": "pct"},
    {"key": "roas", "label": "ROAS", "num": True, "fmt": "num"},
    {"key": "block", "label": "Block", "fmt": "block"},
]

HTML_KPIS = [
    {"label": "Block 1 (expensive conv.)", "key": "block1", "cls": "b1"},
    {"label": "Block 2 (zero-conv waste)", "key": "block2", "cls": "b2"},
    {"label": "Total flagged", "key": "total"},
    {"label": "Flagged spend", "key": "flagged_spend", "money": True},
    {"label": "Tier signals (concentrated + weak ROAS)", "key": "tier_signals"},
    {"label": "Tier signal spend", "key": "signal_spend", "money": True},
    {"label": "No benchmark", "key": "no_benchmark"},
]

# Mirrors pmax_listing_core.classify_row / summarize exactly (verified by the
# Node-vs-Python gate). Assigns the engine's `classify` and `summarize`.
# analytics.JS_MIRROR is spliced in verbatim so the tier-concentration + signal
# math (gxConcentration / gxSignals, HM-539) is the shared primitive, not a
# re-implementation — the parity gate (run_parity.py analytics-primitives)
# holds this string equal to _shared/analytics.py on shared vectors.
JS_KERNEL = analytics.JS_MIRROR + r"""
classify = function(r,P){
  if(r.status!=="scored") return {block:"", cpa_pass:null, clicks_pass:null};
  const f=P.expensiveness_factor;
  const cpa_pass = (r.conv>0 && r.lg_cpa!=null && r.lg_cpa > f*r.camp_cpa);
  const clicks_pass = (r.conv===0 && r.camp_clicks_per_conv!=null && r.clicks > f*r.camp_clicks_per_conv);
  let block="";
  if(r.conv>0){ if(cpa_pass) block="Block 1"; }
  else { if(clicks_pass) block="Block 2"; }
  return {block,cpa_pass,clicks_pass};
};
// Tier concentration + signal (HM-539): cost_share is this row's share of the
// FULL row set's total cost (no-row-loss — every row counts, scored or not);
// tier_signal fires when over_concentrated AND weak_roas both fire. Mirrors
// pmax_listing_core.annotate_signals exactly, via the shared gxSignals rule engine.
function pmaxTierRows(rows,P){
  var total=0; rows.forEach(function(r){ total+=r.cost; });
  var withShare = rows.map(function(r){
    var rr=Object.assign({},r); rr.cost_share = total>0 ? r.cost/total : 0.0; return rr;
  });
  var rules=[
    {id:"over_concentrated", key:"cost_share", op:"gt", value:P.concentration_share_min},
    {id:"weak_roas", key:"roas", op:"lt", value:P.weak_roas_max},
  ];
  var flagsList = gxSignals(withShare, rules);
  return withShare.map(function(r,i){
    r.signal_flags = flagsList[i];
    r.tier_signal = flagsList[i].indexOf("over_concentrated")!==-1 && flagsList[i].indexOf("weak_roas")!==-1;
    return r;
  });
}
summarize = function(rows,P){
  let b1=0,b2=0,flagged=0,nb=0;
  rows.forEach(r=>{const c=classify(r,P); if(r.status!=="scored")nb++;
    if(c.block==="Block 1"){b1++;flagged+=r.cost} else if(c.block==="Block 2"){b2++;flagged+=r.cost}});
  const tiered = pmaxTierRows(rows,P);
  let tierCount=0, tierSpend=0;
  tiered.forEach(r=>{ if(r.tier_signal){ tierCount++; tierSpend+=r.cost; } });
  const conc = gxConcentration(rows,"cost",P.concentration_top_n);
  return {block1:b1,block2:b2,total:b1+b2,flagged_spend:Math.round(flagged*100)/100,
          universe:rows.length,scored:rows.length-nb,no_benchmark:nb,
          tier_signals:tierCount,signal_spend:Math.round(tierSpend*100)/100,
          concentration:conc};
};
"""

# Live: block logic, partition sensitivity + near-misses, and the full Products
# panel (KPIs + sensitivity + near-misses + every-item table), all recomputed on
# every factor change from MODEL.items with the same kernel.
JS_EXTRA = r"""
renderExtra = function(host,H){
  function sens(rows){
    const saved=P.expensiveness_factor,out=[];
    MODEL.factor_ladder.forEach(f=>{P.expensiveness_factor=f; const s=summarize(rows,P);
      out.push({f,b1:s.block1,b2:s.block2,total:s.total,cur:Math.abs(f-saved)<1e-9})});
    P.expensiveness_factor=saved; return out;
  }
  function nearMiss(rows,block){
    const f=P.expensiveness_factor,pool=[];
    rows.forEach(r=>{
      if(r.status!=="scored") return;
      let x,now;
      if(block==="Block 1"){ if(!(r.conv>0 && r.camp_cpa)) return; x=r.lg_cpa/r.camp_cpa; now=r.lg_cpa>f*r.camp_cpa; }
      else { if(!(r.conv===0 && r.camp_clicks_per_conv)) return; x=r.clicks/r.camp_clicks_per_conv; now=r.clicks>f*r.camp_clicks_per_conv; }
      pool.push({r,x,now});
    });
    pool.sort((a,b)=>b.x-a.x); return pool.slice(0,15);
  }
  function sensTable(title,note,rows){
    return '<div class="card sens"><h2>'+title+'</h2><div class="note">'+note+'</div>'+
     '<table><thead><tr><th>Factor</th><th class="num">Block 1</th><th class="num">Block 2</th><th class="num">Total</th></tr></thead><tbody>'+
     sens(rows).map(r=>`<tr><td class="${r.cur?'cur':''}">${r.f.toFixed(2)}${r.cur?' ← current':''}</td><td class="num ${r.cur?'cur':''}">${r.b1}</td><td class="num">${r.b2}</td><td class="num">${r.total}</td></tr>`).join("")+
     '</tbody></table></div>';
  }
  function nmBlock(rows,blk){
    const nm=nearMiss(rows,blk);
    let h=`<div class="note" style="margin-top:8px"><b>${blk}</b></div>`;
    if(!nm.length){return h+'<div class="note">None.</div>';}
    if(blk==="Block 1"){
      h+='<table><thead><tr><th>Unit</th><th>Campaign</th><th class="num">Cost</th><th class="num">Cost/conv</th><th class="num">Qual if ≤</th><th>Now</th></tr></thead><tbody>';
      nm.forEach(({r,x,now})=>{h+=`<tr><td>${H.esc(r.label)}</td><td>${H.esc(r.campaign)}</td><td class="num">${H.money(r.cost)}</td><td class="num">${H.money(r.lg_cpa)}</td><td class="num">${x.toFixed(2)}</td><td>${now?'yes':'no'}</td></tr>`;});
    } else {
      h+='<table><thead><tr><th>Unit</th><th>Campaign</th><th class="num">Clicks</th><th class="num">Camp clicks/conv</th><th class="num">Qual if ≤</th><th>Now</th></tr></thead><tbody>';
      nm.forEach(({r,x,now})=>{h+=`<tr><td>${H.esc(r.label)}</td><td>${H.esc(r.campaign)}</td><td class="num">${H.fmtN(r.clicks)}</td><td class="num">${r.camp_clicks_per_conv==null?"":r.camp_clicks_per_conv.toFixed(2)}</td><td class="num">${x.toFixed(2)}</td><td>${now?'yes':'no'}</td></tr>`;});
    }
    return h+'</tbody></table>';
  }
  function badge(r,c){
    if(c.block) return '<span class="badge '+(c.block==="Block 1"?"b1":"b2")+'">'+c.block+'</span>';
    if(r.status!=="scored") return '<span class="badge nb">no benchmark</span>';
    return '<span class="badge no">scored</span>';
  }
  const f=(+P.expensiveness_factor).toFixed(2);
  let h='<div class="card"><h2>Block logic (live)</h2>'+
   `<div class="logic"><b>Block 1 — expensive converters</b> · conversions &gt; 0 · cost/conv &gt; ${f} × campaign cost/conv</div>`+
   `<div class="logic"><b>Block 2 — zero-conversion waste</b> · conversions = 0 · clicks &gt; ${f} × campaign clicks/conv · campaign conversions &gt; 0</div></div>`;
  // concentration + tier signal (HM-539) — independent of the factor slider;
  // recomputed via the same shared analytics primitives (gxConcentration/gxSignals)
  const Spart=summarize(MODEL.rows,P);
  h+='<div class="card"><h2>Tier concentration & signal — partitions</h2>'+
     `<div class="logic">Over-concentrated: a unit's share of 30d spend &gt; ${(+P.concentration_share_min).toFixed(2)} · Weak ROAS: conv. value / cost &lt; ${(+P.weak_roas_max).toFixed(2)} · both firing = tier signal</div>`+
     '<div class="kpis">'+
     `<div class="kpi"><div class="n">${(Spart.concentration.top_share*100).toFixed(1)}%</div><div class="l">Top ${Spart.concentration.top_n} share of spend</div></div>`+
     `<div class="kpi"><div class="n">${Spart.concentration.hhi.toFixed(1)}</div><div class="l">HHI</div></div>`+
     `<div class="kpi"><div class="n">${Spart.concentration.effective_n.toFixed(2)}</div><div class="l">Effective N</div></div>`+
     `<div class="kpi b2"><div class="n">${Spart.tier_signals}</div><div class="l">Tier signals</div></div>`+
     `<div class="kpi"><div class="n">${H.money(Spart.signal_spend)}</div><div class="l">Tier signal spend</div></div>`+
     '</div></div>';
  // partition sensitivity + near-misses
  h+=sensTable("Partition sensitivity","Qualifiers as the factor changes (other params held).",MODEL.rows);
  h+='<div class="card"><h2>Partition near misses</h2><div class="note">Closest to the bar.</div>'+nmBlock(MODEL.rows,"Block 1")+nmBlock(MODEL.rows,"Block 2")+'</div>';
  // products panel
  if(MODEL.items && MODEL.items.length){
    const S=summarize(MODEL.items,P);
    h+='<div class="card"><h2>Products (item-id)</h2>'+
       '<div class="kpis">'+
       `<div class="kpi b1"><div class="n">${S.block1}</div><div class="l">Block 1</div></div>`+
       `<div class="kpi b2"><div class="n">${S.block2}</div><div class="l">Block 2</div></div>`+
       `<div class="kpi"><div class="n">${S.total}</div><div class="l">Total flagged</div></div>`+
       `<div class="kpi"><div class="n">${H.money(S.flagged_spend)}</div><div class="l">Flagged spend</div></div>`+
       `<div class="kpi b2"><div class="n">${S.tier_signals}</div><div class="l">Tier signals</div></div>`+
       `<div class="kpi"><div class="n">${H.money(S.signal_spend)}</div><div class="l">Tier signal spend</div></div>`+
       `<div class="kpi"><div class="n">${S.no_benchmark}</div><div class="l">No benchmark</div></div>`+
       '</div>';
    h+='<div class="tablewrap" style="margin-top:12px"><table><thead><tr><th>Product</th><th>Campaign</th><th>Status</th><th class="num">Impr</th><th class="num">Clicks</th><th class="num">Cost</th><th class="num">Conv</th><th class="num">Cost/conv</th><th>Block</th></tr></thead><tbody>';
    MODEL.items.forEach(r=>{const c=classify(r,P);
      h+=`<tr class="${c.block?'qual':''}"><td>${H.esc(r.label)}</td><td>${H.esc(r.campaign)}</td><td>${badge(r,c)}</td><td class="num">${H.fmtN(r.impressions)}</td><td class="num">${H.fmtN(r.clicks)}</td><td class="num">${H.money(r.cost)}</td><td class="num">${Number(r.conv).toFixed(2)}</td><td class="num">${r.lg_cpa==null?"—":H.money(r.lg_cpa)}</td><td>${c.block?('<span class="badge '+(c.block==="Block 1"?"b1":"b2")+'">'+c.block+'</span>'):''}</td></tr>`;});
    h+='</tbody></table></div>';
    h+=sensTable("Product sensitivity","Qualifiers as the factor changes.",MODEL.items);
    h+='<div style="margin-top:8px"><h2 style="font-size:13px;text-transform:uppercase;letter-spacing:.04em;color:#475569">Product near misses</h2>'+nmBlock(MODEL.items,"Block 1")+nmBlock(MODEL.items,"Block 2")+'</div>';
    h+='</div>';
  }
  host.innerHTML=h;
};
"""


# --------------------------------------------------------------------------
# Charts — declared here, GENERATED by _shared/render/charts.py (never hand-
# authored). One declaration drives both paths: the static SVGs shipped with
# the md/widget (rendered by vl-convert at the model's default params) and the
# live explorer charts (vendored Vega-Lite re-deriving from the classify(r,P)-
# augmented rows on every factor change). Both paths read the PARTITION rows
# (model['rows'] / MODEL.rows) — the products universe is a separate panel and
# is not charted. All aggregation lives in the Vega-Lite `transform` below —
# shared verbatim — and only uses fields present in BOTH row shapes (model rows
# and the html embed): label, campaign, status, cost, value, block.
# --------------------------------------------------------------------------
_FLAG_COLORS = {"domain": ["Block 1", "Block 2", "Unflagged"],
                "range": ["#0369a1", "#7c3aed", "#cbd5e1"]}  # match the b1/b2 badges

CHARTS = [
    {
        "id": "flagged_spend_by_block",
        "title": "Flagged partition spend by block (30d)",
        "mark": {"type": "bar"},
        "transform": [
            {"filter": "datum.block != ''"},
            {"aggregate": [{"op": "sum", "field": "cost", "as": "spend"},
                           {"op": "count", "as": "partitions"}],
             "groupby": ["block"]},
        ],
        "encoding": {
            "y": {"field": "block", "type": "nominal", "title": None,
                  "scale": {"domain": ["Block 1", "Block 2"]}},
            "x": {"field": "spend", "type": "quantitative", "title": "Flagged spend (30d)"},
            "color": {"field": "block", "type": "nominal", "legend": None,
                      "scale": {"domain": ["Block 1", "Block 2"],
                                "range": ["#0369a1", "#7c3aed"]}},
            "tooltip": [{"field": "block", "title": "Block"},
                        {"field": "spend", "title": "Spend (30d)", "format": ",.2f"},
                        {"field": "partitions", "title": "Partitions"}],
        },
        "height": 120,
        "md": True, "widget": True,
    },
    {
        "id": "roas_spend_scatter",
        "title": "Scored partitions — 30-day ROAS vs spend (flagged partitions colored)",
        "mark": {"type": "point"},
        "transform": [
            {"filter": "datum.status == 'scored' && datum.cost > 0"},
            {"calculate": "datum.value / datum.cost", "as": "roas"},
            {"calculate": "datum.block != '' ? datum.block : 'Unflagged'", "as": "flag"},
        ],
        "encoding": {
            "x": {"field": "cost", "type": "quantitative", "title": "Spend (30d)"},
            "y": {"field": "roas", "type": "quantitative", "title": "ROAS (conv. value ÷ cost)"},
            "color": {"field": "flag", "type": "nominal", "title": None, "scale": _FLAG_COLORS},
            "tooltip": [{"field": "label", "title": "Listing group"},
                        {"field": "campaign", "title": "Campaign"},
                        {"field": "flag", "title": "Block"},
                        {"field": "cost", "title": "Spend (30d)", "format": ",.2f"},
                        {"field": "roas", "title": "ROAS", "format": ".2f"}],
        },
        "height": 280,
        "md": True, "widget": False,
    },
]


# --------------------------------------------------------------------------
# The spec object the toolkit consumes.
# --------------------------------------------------------------------------
SPEC = {
    "slug_prefix": "pmax-listing-waste",
    "row_noun": "partitions",
    "title": "PMax Listing-Group Waste Filter",
    "about": {
        "summary": "Flags expensive listing-group partitions (and product items) inside Performance Max, benchmarked against the campaign's own cost/conversion and clicks/conversion. One Expensiveness factor moves both bars — raise it to flag only the most extreme. Independently, a tier signal flags units where 30d spend is concentrated (own share of the universe) AND ROAS is weak — spend sitting in a tier that isn't paying back. Partitions in campaigns with no conversions in 30d are held out as 'no benchmark'.",
        "legend": [
            {"label": "Block 1", "desc": "Expensive converter — converts, but cost/conv > (factor × campaign cost/conv)."},
            {"label": "Block 2", "desc": "Zero-conversion waste — no conversions and clicks > (factor × campaign clicks/conv)."},
            {"label": "Tier signal", "desc": "Over-concentrated (spend share > bar) AND weak ROAS (< bar) — independent of Block 1/2."},
        ],
    },
    "methodology_ref": "references/pmax-listing-waste-filter.md",
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
    # xlsx layout is attached in pmax_listing_xlsx_spec to keep this module
    # stdlib-only and import-light; build_pmax_listing_filter wires it in for xlsx.
}
