#!/usr/bin/env python3
"""Render spec for the conversions & tracking advisor — adapts
conv_tracking_core's model to the shared render toolkit (_shared/render).
Stdlib only (analytics.JS_MIRROR is a plain string, no import needed here).

The classification math lives once in conv_tracking_core (Python) and is
mirrored in `JS_KERNEL` (browser) — the Node-vs-Python equality gate keeps
them in sync for the PRIMARY tunable dataset (campaign CVR/CTR trend, i.e.
model['rows']). The config-health checklist and the manual EC/Consent-Mode
rows are static secondary datasets (model['config_rows'] / ['manual_rows']) —
presented in the md report and the xlsx Snapshot tab, not live-tunable.
"""
from __future__ import annotations

import conv_tracking_core as core
from render import model as M  # noqa: E402  (source_label — HM-572 canonical "Data source" line)


def _money(v, cur):
    return f"{float(v):,.2f}" + (f" {cur}" if cur else "")


def _pct(v):
    return "—" if v is None else f"{float(v) * 100:.2f}%"


# --------------------------------------------------------------------------
# Markdown adapters
# --------------------------------------------------------------------------
def md_params(model):
    p = model["params"]
    return [
        ("Data source", M.source_label(model["provenance"].get("source"))),
        ("CVR drop threshold", f"{p['cvr_drop_pct']:.0%} relative drop vs. prior window"),
        ("Volume floor", f"{p['min_conv_30d']:.0f} conversions (current window)"),
        ("CTR held/up factor", f"{p['ctr_factor']:.2f} × prior-window CTR"),
        ("Below-account-CVR factor", f"{p['cvr_factor']:.2f} × account avg CVR"),
    ]


def md_kpis(model):
    s = model["summary"]
    return [
        ("Config actions — flagged / total", f"{s['config_flagged']} / {s['config_actions']}"),
        ("No primary conversion action",
         "YES — tracking is broken" if s["config_no_primary_action"] else "no"),
        ("Campaigns — Critical / High / Watch", f"{s['critical']} / {s['high']} / {s['watch']}"),
        ("Landing-page-suspect campaigns", str(s["landing_page_suspect"])),
        ("Manual checks (Enhanced Conversions / Consent Mode)",
         f"{s['manual_user_confirmed']} confirmed via CSV, {s['manual_not_confirmed']} not confirmed"),
    ]


def md_narrative(model):
    out = []
    s = model["summary"]
    if s["config_no_primary_action"]:
        out.append(
            "> **Critical — no ENABLED primary-for-goal conversion action.** Automated bidding has "
            "nothing reliable to optimize toward. Fix this before touching bids or enabling Target "
            "CPA/ROAS.")
    if s["config_flagged"] == 0 and s["critical"] == 0 and s["high"] == 0:
        out.append(
            "> **Clean config + trend read.** Every conversion action passes the config-health "
            "checks and no campaign shows a Critical/High CVR anomaly this window. A clean result "
            "is a valid outcome, not a bug — the sensitivity table below still shows where a "
            "stricter drop threshold would surface a Watch-tier campaign.")
    return out


def md_sections(model):
    secs = []

    # Config-health checklist (secondary dataset — every conversion_action row).
    cflags = ", ".join(f"**{fid}** — {label}" for fid, label in core.CONFIG_FLAG_LABELS)
    secs.append({
        "title": "Conversion-action config health",
        "note": f"Every ENABLED conversion action, pass/flag verdict. Flags: {cflags}.",
        "headers": ["Action", "Category", "Counting", "Attribution", "Primary?", "Conv (30d)",
                    "Verdict", "Flags"],
        "aligns": ["l", "l", "l", "l", "l", "r", "l", "l"],
        "rows": [[r["name"], r["category"], r["counting_type"], r["attribution_model"],
                  "yes" if r["primary_for_goal"] else "no", f"{r['conversions_30d']:.2f}",
                  r["verdict"], ", ".join(r["flags"]) or "—"] for r in model["config_rows"]],
        "empty": "_No conversion actions returned — tracking cannot be verified._",
    })

    # Manual EC / Consent Mode checks — never implied as an API confirmation.
    secs.append({
        "title": "Enhanced Conversions / Consent Mode (manual)",
        "note": ("The Google Ads API does not expose these — every row here is either **user_csv** "
                 "(confirmed from a UI export) or **not_confirmed** (no export supplied). Never "
                 "read a not_confirmed row as an API result."),
        "headers": ["Check", "Value", "Source", "Note"],
        "aligns": ["l", "l", "l", "l"],
        "rows": [[r["check"], r["value"], r["data_source"], r.get("note", "")]
                 for r in model["manual_rows"]],
        "empty": "_No manual checks supplied._",
    })

    # Trend threshold sensitivity.
    secs.append({
        "title": "CVR-drop threshold sensitivity",
        "note": "Campaigns qualifying Critical/High/Watch as the CVR-drop threshold changes "
                "(other params held at current values).",
        "headers": ["CVR drop threshold", "Critical", "High", "Watch"],
        "aligns": ["l", "r", "r", "r"],
        "rows": [[f"{r['cvr_drop_pct']:.0%}" + (" ← current" if r["is_current"] else ""),
                  r["critical"], r["high"], r["watch"]] for r in model["sensitivity"]],
    })

    # No-benchmark campaigns (excluded from scoring, never dropped).
    nb = [r for r in model["rows"] if r["status"] == "no_benchmark"]
    secs.append({
        "title": "Excluded — campaigns with no prior-window benchmark",
        "note": "0 clicks in the prior window means the CVR/CTR comparison is undefined; these "
                "campaigns are listed here so nothing is silently dropped.",
        "headers": ["Campaign", "Clicks (current)", "Conversions (current)"],
        "aligns": ["l", "r", "r"],
        "rows": [[r["campaign"], f"{r['clicks_curr']:.0f}", f"{r['conversions_curr']:.2f}"] for r in nb],
        "empty": "_None — every campaign had clicks in the prior window._",
    })
    return secs


def md_rows(model):
    """Every campaign in the trend universe with a status — the no-row-loss
    layer for the md."""
    cur = model["provenance"]["currency"]
    headers = ["Campaign", "Status", "Tier", "CTR (curr)", "CTR (prior)", "CVR (curr)",
               "CVR (prior)", f"Cost ({cur})" if cur else "Cost", "Conv (curr)", "Flags"]
    out = []
    for r in model["rows"]:
        out.append([
            r["campaign"], r["status"], r["tier"] or "—",
            f"{r['ctr_curr'] * 100:.2f}%", _pct(r["ctr_prior"]),
            f"{r['cvr_curr'] * 100:.2f}%", _pct(r["cvr_prior"]),
            f"{r['cost_curr']:,.2f}", f"{r['conversions_curr']:.2f}",
            ", ".join(r["flags"]) or "—",
        ])
    return {
        "title": "All campaigns — CVR/CTR trend (every row, with status)",
        "note": "No row loss: every campaign in the universe appears here, scored or held out as "
                "no-benchmark. Sorted by current-window cost (highest first).",
        "headers": headers,
        "aligns": ["l", "l", "l", "r", "r", "r", "r", "r", "r", "l"],
        "rows": out,
        "empty": "_No campaigns in the trend universe._",
    }


# --------------------------------------------------------------------------
# HTML adapters (primary/tunable dataset only: model['rows'] = trend)
# --------------------------------------------------------------------------
def in_play(r, params=None):
    """Reachable envelope for the in-Claude tuner's embed: a row can only
    ever earn a flag (and therefore a tier) when it is status='scored' — a
    no_benchmark row never fires any relative rule regardless of the sliders.
    """
    return r.get("status") == "scored"


def html_embed(model):
    return {
        "provenance": model["provenance"],
        "params": model["params"],
        "summary": model["summary"],
        "config_rows": model["config_rows"],
        "manual_rows": model["manual_rows"],
        "drop_ladder": model["drop_ladder"],
        "rows": [{
            "campaign": r["campaign"], "status": r["status"],
            "ctr_curr": r["ctr_curr"], "cvr_curr": r["cvr_curr"],
            "ctr_prior": r["ctr_prior"], "cvr_prior": r["cvr_prior"],
            "cost_curr": r["cost_curr"], "conversions_curr": r["conversions_curr"],
            "account_avg_cvr": r["account_avg_cvr"],
        } for r in model["rows"]],
    }


HTML_CONTROLS = [
    {"key": "cvr_drop_pct", "label": "CVR drop threshold", "kind": "slider",
     "min": 0.05, "max": 0.90, "step": 0.05, "sub": "relative drop vs. prior window"},
    {"key": "min_conv_30d", "label": "Volume floor (conversions)", "kind": "number", "min": 0, "step": 1},
    {"key": "ctr_factor", "label": "CTR held/up factor", "kind": "slider",
     "min": 0.5, "max": 1.5, "step": 0.05, "sub": "× prior-window CTR"},
    {"key": "cvr_factor", "label": "Below-account-CVR factor", "kind": "slider",
     "min": 0.1, "max": 1.0, "step": 0.05, "sub": "× account avg CVR"},
]

HTML_COLUMNS = [
    {"key": "campaign", "label": "Campaign"},
    {"key": "status", "label": "Status", "fmt": "status"},
    {"key": "ctr_curr", "label": "CTR (curr)", "num": True, "fmt": "pct"},
    {"key": "ctr_prior", "label": "CTR (prior)", "num": True, "fmt": "pct"},
    {"key": "cvr_curr", "label": "CVR (curr)", "num": True, "fmt": "pct"},
    {"key": "cvr_prior", "label": "CVR (prior)", "num": True, "fmt": "pct"},
    {"key": "cost_curr", "label": "Cost", "num": True, "fmt": "money"},
    {"key": "conversions_curr", "label": "Conv (curr)", "num": True, "fmt": "num"},
    {"key": "tier", "label": "Tier", "fmt": "block"},
]

HTML_KPIS = [
    {"label": "Critical", "key": "critical", "cls": "b2"},
    {"label": "High", "key": "high", "cls": "b1"},
    {"label": "Watch", "key": "watch"},
    {"label": "Clean", "key": "clean"},
    {"label": "No benchmark", "key": "no_benchmark"},
    {"label": "Landing-page-suspect", "key": "landing_page_suspect"},
]

# Mirrors conv_tracking_core.classify_trend / summarize_trend exactly (verified
# by the Node-vs-Python gate). Splices _shared/analytics.JS_MIRROR verbatim —
# the declarative rules are rebuilt from the live P on every recompute, exactly
# like the Python side rebuilds `_trend_rules(params)`.
JS_KERNEL = core.analytics.JS_MIRROR + r"""
function trendRules(P){
  return [
    {id:"cvr_drop", key:"cvr_curr", op:"le", value_key:"cvr_prior", mult: 1.0 - P.cvr_drop_pct},
    {id:"ctr_held_or_up", key:"ctr_curr", op:"ge", value_key:"ctr_prior", mult: P.ctr_factor},
    {id:"thin_volume", key:"conversions_curr", op:"lt", value: P.min_conv_30d},
    {id:"below_account_cvr", key:"cvr_curr", op:"lt", value_key:"account_avg_cvr", mult: P.cvr_factor},
  ];
}
var TREND_WEIGHTS = {cvr_drop:4.0, landing_page_suspect:6.0, thin_volume:1.0, below_account_cvr:2.0};
function tierOf(status,score){
  if(status!=="scored") return "";
  if(score>=6) return "Critical";
  if(score>=3) return "High";
  if(score>0) return "Watch";
  return "";
}
classify = function(r,P){
  const flagsList = gxSignals([r], trendRules(P));
  let flags = flagsList[0].slice();
  if(flags.indexOf("cvr_drop")>=0 && flags.indexOf("ctr_held_or_up")>=0) flags.push("landing_page_suspect");
  const score = gxPreScore({flags:flags}, TREND_WEIGHTS);
  const tier = tierOf(r.status, score);
  return {flags:flags, score:score, tier:tier, block:tier};
};
summarize = function(rows,P){
  // Critical/High/Watch/Clean/landing_page_suspect are PARAM-DEPENDENT -> always
  // recomputed live from the embedded rows (every row that could ever earn a
  // tier is in the in-play envelope, so this is exact even when trimmed).
  // campaigns/scored/no_benchmark are PARAM-INDEPENDENT -> read from the
  // embedded full-model summary so they stay honest under a trimmed embed
  // (the widget only embeds status=="scored" rows; a no_benchmark row never
  // reaches this function otherwise). Falls back to row-derived counts when
  // no summary is embedded (e.g. an untrimmed default lambda).
  const T=(typeof MODEL!=="undefined"&&MODEL&&MODEL.summary)?MODEL.summary:null;
  let crit=0,high=0,watch=0,lps=0;
  rows.forEach(r=>{
    if(r.status!=="scored") return;
    const c=classify(r,P);
    if(c.tier==="Critical") crit++; else if(c.tier==="High") high++; else if(c.tier==="Watch") watch++;
    if(c.flags.indexOf("landing_page_suspect")>=0) lps++;
  });
  const scored=(T&&T.scored!=null)?T.scored:rows.filter(r=>r.status==="scored").length;
  const nb=(T&&T.no_benchmark!=null)?T.no_benchmark:rows.filter(r=>r.status!=="scored").length;
  const campaigns=(T&&T.campaigns!=null)?T.campaigns:rows.length;
  return {campaigns:campaigns, scored:scored, no_benchmark:nb, critical:crit, high:high,
          watch:watch, clean:scored-crit-high-watch, landing_page_suspect:lps};
};
"""

# Static secondary panels: config-health checklist, manual EC/Consent-Mode
# checks, and the drop-threshold sensitivity strip. Not live-tunable (the
# config/manual datasets carry no sliders) — re-rendered on every P change
# only so the sensitivity strip tracks the live cvr_drop_pct value.
JS_EXTRA = r"""
renderExtra = function(host,H){
  const cfg = MODEL.config_rows||[], man = MODEL.manual_rows||[], S = MODEL.summary||{};
  let h = '<div class="card"><h2>Conversion-action config health</h2>'+
    `<div class="note">${S.config_flagged||0} flagged of ${S.config_actions||0} actions.`+
    (S.config_no_primary_action?' <b>No ENABLED primary-for-goal action — tracking is broken.</b>':'')+'</div>';
  if(cfg.length){
    h += '<table><thead><tr><th>Action</th><th>Category</th><th>Counting</th><th>Attribution</th>'+
      '<th>Verdict</th><th>Flags</th></tr></thead><tbody>';
    cfg.forEach(r=>{h+=`<tr class="${r.verdict==='flag'?'qual':''}"><td>${H.esc(r.name)}</td>`+
      `<td>${H.esc(r.category)}</td><td>${H.esc(r.counting_type)}</td>`+
      `<td>${H.esc(r.attribution_model)}</td><td>${H.esc(r.verdict)}</td>`+
      `<td>${H.esc((r.flags||[]).join(", "))}</td></tr>`;});
    h += '</tbody></table>';
  } else { h += '<div class="note">No conversion actions returned.</div>'; }
  h += '</div>';

  h += '<div class="card"><h2>Enhanced Conversions / Consent Mode (manual)</h2>'+
    '<div class="note">Never confirmed by the API — user_csv or not_confirmed only.</div>';
  if(man.length){
    h += '<table><thead><tr><th>Check</th><th>Value</th><th>Source</th></tr></thead><tbody>';
    man.forEach(r=>{h+=`<tr><td>${H.esc(r.check)}</td><td>${H.esc(r.value)}</td><td>${H.esc(r.data_source)}</td></tr>`;});
    h += '</tbody></table>';
  } else { h += '<div class="note">None supplied.</div>'; }
  h += '</div>';

  h += '<div class="card sens"><h2>CVR-drop threshold sensitivity</h2>'+
    '<div class="note">Recomputed live at the current CTR/volume/account-CVR params.</div>'+
    '<table><thead><tr><th>Drop threshold</th><th class="num">Critical</th><th class="num">High</th><th class="num">Watch</th></tr></thead><tbody>';
  (MODEL.drop_ladder||[]).forEach(pct=>{
    const p2=Object.assign({},P,{cvr_drop_pct:pct});
    const s=summarize(MODEL.rows,p2);
    const cur=Math.abs(pct-P.cvr_drop_pct)<1e-9;
    h+=`<tr><td class="${cur?'cur':''}">${(pct*100).toFixed(0)}%${cur?' ← current':''}</td>`+
      `<td class="num">${s.critical}</td><td class="num">${s.high}</td><td class="num">${s.watch}</td></tr>`;
  });
  h += '</tbody></table></div>';
  host.innerHTML = h;
};
"""


# --------------------------------------------------------------------------
# Charts — declared here, GENERATED by _shared/render/charts.py (never hand-
# authored). Row shape used matches BOTH model['rows'] (full) and the html
# embed (trimmed to in-play rows) — only fields present in both are used.
# --------------------------------------------------------------------------
CHARTS = [
    {
        "id": "tier_counts",
        "title": "Campaigns by cost, scored vs. no-benchmark",
        "mark": {"type": "bar"},
        "encoding": {
            "x": {"field": "campaign", "type": "nominal", "title": None, "sort": "-y"},
            "y": {"field": "cost_curr", "type": "quantitative", "title": "Cost (current window)"},
            "color": {"field": "status", "type": "nominal", "title": None,
                      "scale": {"domain": ["scored", "no_benchmark"], "range": ["#1F7A82", "#cbd5e1"]}},
            "tooltip": [{"field": "campaign", "title": "Campaign"},
                        {"field": "cost_curr", "title": "Cost", "format": ",.2f"},
                        {"field": "cvr_curr", "title": "CVR (curr)", "format": ".2%"},
                        {"field": "status", "title": "Status"}],
        },
        "height": 220,
        "md": True, "widget": True,
    },
    {
        "id": "cvr_trend_scatter",
        "title": "Scored campaigns — prior-window CVR vs. current-window CVR",
        "mark": {"type": "point"},
        "transform": [{"filter": "datum.status == 'scored'"}],
        "encoding": {
            "x": {"field": "cvr_prior", "type": "quantitative", "title": "CVR (prior window)"},
            "y": {"field": "cvr_curr", "type": "quantitative", "title": "CVR (current window)"},
            "color": {"field": "cost_curr", "type": "quantitative", "title": "Cost"},
            "tooltip": [{"field": "campaign", "title": "Campaign"},
                        {"field": "cvr_prior", "title": "CVR prior", "format": ".2%"},
                        {"field": "cvr_curr", "title": "CVR current", "format": ".2%"}],
        },
        "height": 260,
        "md": True, "widget": False,
    },
]


# --------------------------------------------------------------------------
# The spec object the toolkit consumes.
# --------------------------------------------------------------------------
SPEC = {
    "slug_prefix": "conv-tracking",
    "row_noun": "campaigns",
    "title": "Conversions & Tracking Advisor",
    "window_labels": ("Current window", "Prior window"),
    "about": {
        "summary": "Two datasets in one advisor: a conversion-action config-health checklist "
                   "(dormant primary actions, mis-set counting, legacy attribution, duplicate "
                   "primary categories) and a per-campaign CVR/CTR trend that flags CVR drops, "
                   "thin conversion volume, and the landing-page-suspect pattern (CVR down while "
                   "CTR holds or improves). Enhanced Conversions / Consent Mode are manual — the "
                   "API cannot confirm them.",
        "legend": [
            {"label": "Critical", "desc": "Score ≥ 6 — CVR dropped AND CTR held/improved "
                                          "(landing-page-suspect), or a heavily-weighted combination."},
            {"label": "High", "desc": "Score ≥ 3 — a clear CVR drop or a below-account-average CVR."},
            {"label": "Watch", "desc": "Score > 0 — a lower-severity flag (e.g. thin volume alone)."},
        ],
    },
    "methodology_ref": "references/conversion-tracking-filter.md",
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
    # xlsx layout is attached in conv_tracking_xlsx_spec to keep this module
    # import-light; build_conv_tracking_report wires it in for xlsx.
}
