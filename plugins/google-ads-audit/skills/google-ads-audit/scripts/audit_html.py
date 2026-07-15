#!/usr/bin/env python3
# Copyright (c) 2026 Clickt Digital Marketing Inc. All rights reserved.
"""Interactive, self-contained HTML report for google-ads-audit (the PRIMARY deliverable).

Bespoke renderer (the audit's `sections/checks/findings` + Health-Score shape does not
fit the generic `_shared/render` row+slider engine, so — like cm3 — it ships its own).
One `_TEMPLATE` raw string with inline CSS/JS; the model is embedded as JSON and the whole
report is rendered client-side. ZERO external references: the only third-party bytes are
GSAP, inlined between the `/*__GSAP_JS_BEGIN__*/ … /*__GSAP_JS_END__*/` sentinels (the
self-containment test excises that checksummed region before scanning).

Design guarantees:
- **White-label:** no logo, no Clickt credit — the report leads with the client's name.
- **Score parity:** the JS kernel mirrors `audit_model`'s constants verbatim (asserted in
  tests); the Health-Score *gauge* shows the Python-authoritative `model.health` so HTML,
  md, and xlsx never disagree by a rounding step. The business-model toggle is a labelled
  view filter that never moves the gauge.
- **Motion:** GSAP for the score count-up, gauge sweep, and staggered reveals; every call is
  guarded by `prefers-reduced-motion` + `window.gsap` presence, and `animate=False` strips
  GSAP entirely, leaving a fully functional static report.
"""
from __future__ import annotations

import json
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_VENDOR = _HERE / "vendor"

GSAP_BEGIN = "/*__GSAP_JS_BEGIN__*/"
GSAP_END = "/*__GSAP_JS_END__*/"


def gsap_blob() -> str:
    """The vendored GSAP core wrapped in sentinels (byte-checksum enforced by tests)."""
    return GSAP_BEGIN + "\n" + (_VENDOR / "gsap.min.js").read_text(encoding="utf-8") + "\n" + GSAP_END


def _esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def render_html(model: dict, *, animate: bool = True) -> str:
    """Render the self-contained interactive report string from a computed model."""
    data = json.dumps(model, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    title = _esc(model.get("provenance", {}).get("client_name", "") or "Google Ads Audit")
    html = _TEMPLATE.replace("/*__TITLE__*/", title).replace("__DATA__", data)
    if animate:
        html = html.replace("/*__GSAP__*/", gsap_blob())
    else:
        # Strip the whole GSAP <script> so a static report carries zero GSAP bytes.
        html = html.replace('<script>/*__GSAP__*/</script>\n', "").replace("/*__GSAP__*/", "")
    return html


def build_html(model: dict, path, *, animate: bool = True) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_html(model, animate=animate), encoding="utf-8")


# ==========================================================================
# The template. Markers: /*__TITLE__*/, __DATA__ (JSON), /*__GSAP__*/.
# ==========================================================================
_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Google Ads Audit — /*__TITLE__*/</title>
<style>
:root{
  --teal:#1F7A82; --teal-deep:#0F4A52; --abyss:#07262B; --teal-100:#97C4BD;
  --lime:#B4E01F; --lime-700:#3F5410; --lime-50:#EEF7D2;
  --purple:#897B9E; --purple-700:#2B2236;
  --ember:#F86B3C;
  --ink:#0B0F0E; --offwhite:#EEF1F3; --slate:#5C6470;
  --card:#FFFFFF; --bg:#F3F4F6; --line:rgba(11,15,14,.10); --line-2:rgba(11,15,14,.06);
  --font:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --mono:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  --chrome:var(--abyss); --accent:var(--teal);
  --pass:var(--lime-700); --pass-bg:var(--lime-50);
  --flag:#8A6D00; --flag-bg:#FBF0CC;
  --fail:#B23A16; --fail-bg:#FBE1D8;
  --na:var(--slate); --na-bg:#ECEEF0;
  --shadow:0 1px 2px rgba(11,15,14,.06),0 8px 24px rgba(11,15,14,.06);
}
@media (prefers-color-scheme:dark){:root{
  --ink:#EEF1F3; --offwhite:#0B0F0E; --card:#0F1A1C; --bg:#081113; --slate:#9AA4AE;
  --line:rgba(238,241,243,.12); --line-2:rgba(238,241,243,.07);
  --pass:#B4E01F; --pass-bg:rgba(180,224,31,.12);
  --flag:#E7C453; --flag-bg:rgba(231,196,83,.12);
  --fail:#FF8A64; --fail-bg:rgba(248,107,60,.14);
  --na:#9AA4AE; --na-bg:rgba(154,164,174,.14);
  --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.4);
}}
:root[data-theme="dark"]{
  --ink:#EEF1F3; --offwhite:#0B0F0E; --card:#0F1A1C; --bg:#081113; --slate:#9AA4AE;
  --line:rgba(238,241,243,.12); --line-2:rgba(238,241,243,.07);
  --pass:#B4E01F; --pass-bg:rgba(180,224,31,.12); --flag:#E7C453; --flag-bg:rgba(231,196,83,.12);
  --fail:#FF8A64; --fail-bg:rgba(248,107,60,.14); --na:#9AA4AE; --na-bg:rgba(154,164,174,.14);
}
:root[data-theme="light"]{
  --ink:#0B0F0E; --offwhite:#EEF1F3; --card:#FFFFFF; --bg:#F3F4F6; --slate:#5C6470;
  --line:rgba(11,15,14,.10);
  --pass:var(--lime-700); --pass-bg:var(--lime-50); --flag:#8A6D00; --flag-bg:#FBF0CC;
  --fail:#B23A16; --fail-bg:#FBE1D8; --na:var(--slate); --na-bg:#ECEEF0;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--font);
  font-size:15px;line-height:1.5;-webkit-font-smoothing:antialiased}
.wrap{max-width:1080px;margin:0 auto;padding:0 20px 64px}
a{color:var(--teal)}
h1,h2,h3{margin:0;font-weight:650;letter-spacing:-.01em}
.mono{font-family:var(--mono);font-variant-numeric:tabular-nums}

/* header */
header{background:linear-gradient(160deg,var(--abyss),var(--teal-deep));color:#EEF1F3;
  border-radius:0 0 20px 20px;box-shadow:var(--shadow)}
.hd{max-width:1080px;margin:0 auto;padding:34px 20px 30px}
.eyebrow{text-transform:uppercase;letter-spacing:.16em;font-size:11px;font-weight:600;
  color:var(--teal-100);margin-bottom:10px}
.client{font-size:30px;font-weight:680;line-height:1.15}
.meta{margin-top:12px;display:flex;flex-wrap:wrap;gap:6px 18px;font-size:13px;color:#C7D6D4}
.meta b{color:#EEF1F3;font-weight:600}

/* overview */
.grid{display:grid;gap:16px;margin-top:22px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;
  box-shadow:var(--shadow)}
.pad{padding:20px 22px}
.ov{display:grid;grid-template-columns:minmax(240px,300px) 1fr;gap:16px}
@media (max-width:760px){.ov{grid-template-columns:1fr}}

/* gauge */
.gauge-card{display:flex;flex-direction:column;align-items:center;justify-content:center;
  gap:6px;padding:24px}
.gauge-wrap{position:relative;width:180px;height:180px}
svg.gauge{width:180px;height:180px;display:block}
.gtrack{fill:none;stroke:var(--line);stroke-width:14}
.gprog{fill:none;stroke:var(--accent);stroke-width:14;stroke-linecap:round;
  transform:rotate(-90deg);transform-origin:90px 90px;transition:stroke .4s}
.gcenter{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;
  justify-content:center;gap:2px}
.gnum{font-size:44px;font-weight:720;line-height:1;font-family:var(--mono);
  font-variant-numeric:tabular-nums}
.gpct{font-size:13px;color:var(--slate)}
.ggrade{margin-top:8px;font-weight:700;font-size:15px;padding:4px 16px;border-radius:999px}
.glabel{font-size:12px;text-transform:uppercase;letter-spacing:.14em;color:var(--slate)}

/* kpi scorecard */
.kpis{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
.kpi{border:1px solid var(--line);border-radius:12px;padding:12px 14px;background:var(--card)}
.kpi .m{font-size:12px;color:var(--slate);font-weight:600}
.kpi .v{font-size:22px;font-weight:680;margin:2px 0;font-family:var(--mono)}
.kpi .b{font-size:11px;color:var(--slate)}

/* section bars */
.bars{display:flex;flex-direction:column;gap:9px}
.bar-row{display:grid;grid-template-columns:1fr 46px;align-items:center;gap:12px;font-size:13px}
.bar-track{height:9px;border-radius:6px;background:var(--line-2);overflow:hidden;position:relative}
.bar-fill{height:100%;border-radius:6px;width:0;transition:width .2s}
.bar-lab{display:flex;justify-content:space-between;margin-bottom:4px;font-size:12.5px}
.bar-cell{display:block}
.bar-val{text-align:right;font-family:var(--mono);font-weight:600;font-size:13px}

/* pills */
.pill{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:650;
  white-space:nowrap;line-height:1.7}
.p-PASS{background:var(--pass-bg);color:var(--pass)}
.p-FLAG{background:var(--flag-bg);color:var(--flag)}
.p-FAIL{background:var(--fail-bg);color:var(--fail)}
.p-NA{background:var(--na-bg);color:var(--na)}
.sev{font-weight:650;font-size:12px}
.sev-Critical{color:var(--fail)} .sev-High{color:var(--ember)}
.sev-Medium{color:var(--purple)} .sev-Low{color:var(--slate)}

/* concentration */
.verdict{border-radius:12px;padding:12px 16px;font-size:13.5px;font-weight:600;margin:14px 0}
.v-fragility{background:var(--fail-bg);color:var(--fail)}
.v-consolidate,.v-review_bidding{background:var(--flag-bg);color:var(--flag)}
.v-diversified{background:var(--pass-bg);color:var(--pass)}
.v-no_conv_signal,.v-insufficient{background:var(--na-bg);color:var(--na)}
.lorenz-wrap{display:flex;gap:20px;align-items:flex-start;flex-wrap:wrap;margin-top:14px}
svg.lorenz{width:200px;height:200px;flex:none}
.lz-diag{stroke:var(--line);stroke-width:1.5;stroke-dasharray:4 4}
.lz-spend{fill:none;stroke:var(--teal);stroke-width:2.5}
.lz-conv{fill:none;stroke:var(--purple);stroke-width:2.5;stroke-dasharray:6 4}
.lz-frame{fill:none;stroke:var(--line);stroke-width:1}
.lz-legend{font-size:12px;color:var(--slate);display:flex;gap:14px;margin-top:6px}
.lz-key{display:inline-block;width:18px;height:0;border-top:2.5px solid var(--teal);
  vertical-align:middle;margin-right:5px}
.lz-key.k-conv{border-top-style:dashed;border-top-color:var(--purple)}

/* tabs */
.tabs{position:sticky;top:0;z-index:5;background:var(--bg);padding:14px 0 8px;
  margin-top:8px;display:flex;flex-wrap:wrap;gap:4px}
.tab .badge{display:inline-block;margin-left:6px;min-width:18px;padding:1px 6px;border-radius:9px;
  font-size:11px;font-weight:700;background:var(--ember);color:#fff;line-height:1.5;vertical-align:1px}
.btn{appearance:none;border:0;background:var(--teal);color:#fff;font:inherit;font-weight:650;
  font-size:13.5px;padding:9px 16px;border-radius:10px;cursor:pointer}
.btn:hover{background:var(--teal-deep)}
.tab{appearance:none;border:0;background:transparent;color:var(--slate);font:inherit;
  font-weight:600;font-size:13.5px;padding:8px 14px;border-radius:10px;cursor:pointer;
  white-space:nowrap;position:relative}
.tab:hover{color:var(--ink);background:var(--card)}
.tab.active{color:var(--ink);background:var(--card);box-shadow:var(--shadow)}
.tab .dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-left:7px;
  vertical-align:middle}
.panel{display:none}
.panel.active{display:block}

/* tables */
.tbl{width:100%;border-collapse:collapse;font-size:13.5px}
.tbl th{text-align:left;font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;
  color:var(--slate);font-weight:650;padding:8px 10px;border-bottom:1px solid var(--line);
  position:sticky;top:0;background:var(--card);cursor:default}
.tbl.sortable th[data-k]{cursor:pointer;user-select:none}
.tbl.sortable th[data-k]:hover{color:var(--ink)}
.tbl td{padding:10px;border-bottom:1px solid var(--line-2);vertical-align:top}
.tbl tr:last-child td{border-bottom:0}
.chk-id{font-family:var(--mono);font-size:12px;color:var(--slate)}
.chk-name{font-weight:600}
.muted{color:var(--slate)}
.recos{color:var(--ink)}
.wide{overflow-x:auto;border-radius:14px}
.section-head{display:flex;align-items:center;justify-content:space-between;gap:12px;
  flex-wrap:wrap;margin:2px 0 12px}
.section-head h2{font-size:18px}
.section-score{font-family:var(--mono);font-weight:680;font-size:15px}

/* controls */
.controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:2px 0 14px}
.seg{display:inline-flex;background:var(--card);border:1px solid var(--line);border-radius:10px;
  overflow:hidden}
.seg button{appearance:none;border:0;background:transparent;color:var(--slate);font:inherit;
  font-weight:600;font-size:13px;padding:7px 13px;cursor:pointer}
.seg button.on{background:var(--accent);color:#fff}
.chip{appearance:none;border:1px solid var(--line);background:var(--card);color:var(--slate);
  font:inherit;font-weight:600;font-size:12.5px;padding:5px 11px;border-radius:999px;cursor:pointer}
.chip.on{background:var(--ink);color:var(--card);border-color:var(--ink)}
.whatif{font-size:12.5px;color:var(--slate);margin-left:2px}
.whatif b{color:var(--purple)}
label.fld{font-size:12.5px;color:var(--slate);display:inline-flex;align-items:center;gap:6px}
input.num{width:56px;font:inherit;font-family:var(--mono);text-align:center;padding:5px 6px;
  border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink)}
input.num:focus{outline:2px solid var(--accent);outline-offset:1px}
.rank{display:inline-flex;align-items:center;justify-content:center;min-width:26px;height:26px;
  padding:0 7px;border-radius:8px;background:var(--accent);color:#fff;font-weight:700;font-size:13px;
  font-family:var(--mono)}
.ice{font-family:var(--mono);font-weight:680}
.hzn{font-family:var(--mono);font-size:12px;color:var(--slate)}
.empty{color:var(--slate);padding:20px;text-align:center}
footer{margin-top:34px;padding-top:16px;border-top:1px solid var(--line);color:var(--slate);
  font-size:12px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px}
@media (prefers-reduced-motion:reduce){*{transition:none !important;animation:none !important}}
</style>
</head>
<body>
<header>
  <div class="hd">
    <div class="eyebrow">Google Ads Account Audit</div>
    <div class="client" id="clientName"></div>
    <div class="meta" id="metaLine"></div>
  </div>
</header>
<main class="wrap">
  <div class="grid">
    <div class="ov">
      <div class="card gauge-card">
        <div class="glabel">Health Score</div>
        <div class="gauge-wrap">
          <svg class="gauge" viewBox="0 0 180 180" aria-hidden="true">
            <circle class="gtrack" cx="90" cy="90" r="70"></circle>
            <circle class="gprog" id="gaugeArc" cx="90" cy="90" r="70"></circle>
          </svg>
          <div class="gcenter">
            <div class="gnum"><span id="gaugeNum">0</span></div>
            <div class="gpct">out of 100</div>
          </div>
        </div>
        <div class="ggrade" id="gaugeGrade">—</div>
      </div>
      <div class="card pad">
        <h3 style="font-size:14px;margin-bottom:12px">KPI scorecard</h3>
        <div class="kpis" id="kpis"></div>
      </div>
    </div>

    <div class="card pad">
      <div class="section-head">
        <h2 style="font-size:16px">Score by area</h2>
        <div class="controls" style="margin:0">
          <span class="whatif">View:</span>
          <div class="seg" id="bmToggle"></div>
          <span class="whatif" id="whatif"></span>
        </div>
      </div>
      <div class="bars" id="bars"></div>
    </div>
  </div>

  <nav class="tabs" id="tabs"></nav>
  <div id="panels"></div>

  <footer>
    <span id="footL"></span>
    <span>Self-contained · recomputes in your browser</span>
  </footer>
</main>

<script id="data" type="application/json">__DATA__</script>
<script>/*__GSAP__*/</script>
<script>
(function(){
"use strict";
var M = JSON.parse(document.getElementById('data').textContent);
var SEV_W = {Critical:5, High:3, Medium:1.5, Low:0.5};
var FLAG  = {PASS:1, FLAG:0.5, FAIL:0};
/* No IMPACT mirror: Python seeds f.impact from SEVERITY_IMPACT into the blob, so
   the sort reads it like iceVal does. One fewer copy of the kernel to drift. */
var GRADES= [[90,'A'],[75,'B'],[60,'C'],[40,'D'],[0,'F']];
var reduce = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion:reduce)').matches;
function gsapOn(){ return (typeof window!=='undefined' && window.gsap && !reduce) ? window.gsap : null; }

function esc(s){ s=(s==null?'':''+s); return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function el(id){ return document.getElementById(id); }
function gradeOf(s){ for(var i=0;i<GRADES.length;i++){ if(s>=GRADES[i][0]) return GRADES[i][1]; } return 'F'; }
function scoreCheck(c){ if(!(c.result in FLAG)) return null; var w=SEV_W[c.severity]||0; return {e:FLAG[c.result]*w,p:w}; }
function healthOf(checksPredicate){
  var e=0,p=0;
  M.sections.forEach(function(s){ s.checks.forEach(function(c){
    if(checksPredicate && !checksPredicate(c)) return;
    var r=scoreCheck(c); if(r){ e+=r.e; p+=r.p; }
  });});
  /* Nothing scoreable -> not scored, mirroring compute_model. Filtering to a
     business model with no applicable checks must not report a confident 0/F. */
  if(!p) return {score:null, grade:null};
  var sc = Math.round(e/p*1000)/10;
  return {score:sc, grade:gradeOf(sc)};
}

/* ---- palette helpers ---- */
function css(v){ return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); }
function gradeColor(g){ return {A:'--lime',B:'--lime',C:'--teal',D:'--ember',F:'--ember'}[g] || '--teal'; }
function pillClass(r){ return r==='N/A' ? 'p-NA' : ('p-'+r); }

/* ---- header ---- */
var P = M.provenance;
el('clientName').textContent = P.client_name || 'Google Ads Audit';
(function(){
  var bits=[];
  if(P.account_id) bits.push('<span>Account <b>'+esc(P.account_id)+'</b></span>');
  if(P.date_range) bits.push('<span><b>'+esc(P.date_range)+'</b></span>');
  if(P.currency) bits.push('<span>Currency <b>'+esc(P.currency)+'</b></span>');
  if(P.business_model) bits.push('<span>Model <b>'+esc(P.business_model)+'</b></span>');
  if(P.audit_date) bits.push('<span>Audited <b>'+esc(P.audit_date)+'</b></span>');
  el('metaLine').innerHTML = bits.join('');
  el('footL').textContent = (P.n_checks||0)+' checks · '+(P.n_findings||0)+' findings · generated '+(P.generated||'');
})();

/* ---- gauge. Python-authoritative value → no rounding drift vs xlsx/md.
   The final state is written DIRECTLY so it is correct even when the motion
   ticker never runs (reduced-motion, a background tab); GSAP then replays it
   from empty/zero via proxy objects as a pure enhancement. ---- */
(function(){
  var score = M.health.score, grade = M.health.grade;
  /* score is null when no check was scoreable. Say "not scored" — an empty arc
     labelled 0/F would assert a verdict the evidence never supported. */
  var scored = score != null;
  var arc = el('gaugeArc'), C = 2*Math.PI*70, target = C*(1-(scored?score:0)/100);
  arc.style.strokeDasharray = C;
  var col = scored ? (css(gradeColor(grade)) || css('--teal')) : css('--slate');
  arc.style.stroke = col;
  var gp = el('gaugeGrade');
  gp.textContent = scored ? 'Grade '+grade : 'Not scored';
  gp.style.background = col; gp.style.color = '#fff';
  arc.style.strokeDashoffset = target;      // robust final state
  el('gaugeNum').textContent = scored ? score : '—';   // robust final state
  var g = gsapOn();
  if(g && scored){
    var a={o:C};
    g.to(a,{o:target,duration:1.1,ease:'power2.out',onUpdate:function(){ arc.style.strokeDashoffset = a.o; }});
    var n={v:0};
    g.to(n,{v:score,duration:1.1,ease:'power2.out',
      onUpdate:function(){ el('gaugeNum').textContent = Math.round(n.v*10)/10; },
      onComplete:function(){ el('gaugeNum').textContent = score; }});
  }
})();

/* ---- KPI scorecard ---- */
(function(){
  var host = el('kpis');
  if(!M.kpis.length){ host.innerHTML='<div class="muted">No KPI scorecard supplied.</div>'; return; }
  host.innerHTML = M.kpis.map(function(k){
    var v = (k.unit==='$'? '$':'') + esc(k.value) + (k.unit==='%'? '%':'');
    return '<div class="kpi"><div class="m">'+esc(k.metric)+
      ' <span class="pill '+pillClass(k.flag)+'" style="font-size:10px;padding:1px 7px">'+esc(k.flag)+'</span></div>'+
      '<div class="v">'+v+'</div><div class="b">'+esc(k.benchmark||'')+(k.notes?' · '+esc(k.notes):'')+'</div></div>';
  }).join('');
})();

/* ---- business-model toggle + section bars ---- */
var BM = 'Both';
function inScope(c){ return BM==='Both' || c.applies_to==='Both' || c.applies_to===BM; }
function renderBars(){
  var host = el('bars');
  host.innerHTML = M.sections.map(function(s){
    var pct = sectionPct(s);
    var w = pct==null? 0 : pct;
    var col = pct==null? '--slate' : (pct>=75?'--lime':pct>=50?'--teal':pct>=25?'--purple':'--ember');
    return '<div class="bar-cell"><div class="bar-lab"><span>'+esc(s.title)+'</span>'+
      '<span class="bar-val">'+(pct==null?'—':pct)+'</span></div>'+
      '<div class="bar-track"><div class="bar-fill" style="background:var('+col+')" data-w="'+w+'"></div></div></div>';
  }).join('');
  // widths: set final directly (robust even without a live ticker); GSAP replays from 0.
  var fills = host.querySelectorAll('.bar-fill');
  var g = gsapOn();
  fills.forEach(function(f){
    var w = f.getAttribute('data-w');
    f.style.width = w + '%';
    if(g){ var pr={x:0}; g.to(pr,{x:+w,duration:.7,ease:'power2.out',onUpdate:function(){ f.style.width = pr.x + '%'; }}); }
  });
  // what-if in-scope score
  var wf = el('whatif');
  if(BM==='Both'){ wf.innerHTML=''; }
  else { var h = healthOf(inScope);
         wf.innerHTML = 'what-if, '+esc(BM)+'-applicable checks only: '+
           (h.score==null ? '<b>not scored</b> (no applicable check is scoreable)'
                          : '<b>'+h.score+'</b> ('+h.grade+')'); }
}
function sectionPct(s){
  /* Read, do not recompute: the model already carries score_pct. Re-deriving it
     here rounds with Math.round (half-up) where Python used round() (banker's) and
     Excel uses ROUND (half-away-from-zero) — three runtimes, three rules — so a
     section landing on a .x5 boundary showed 6.3 here and 6.2 in the md/xlsx.
     Same reason the gauge reads M.health.score instead of calling healthOf(). */
  return s.score_pct;
}
(function(){
  var host = el('bmToggle');
  ['Both','Lead Gen','Ecommerce'].forEach(function(m){
    var b=document.createElement('button'); b.textContent=m; if(m==='Both') b.className='on';
    b.onclick=function(){ BM=m; host.querySelectorAll('button').forEach(function(x){x.classList.remove('on');}); b.classList.add('on'); renderBars(); renderActiveSection(); };
    host.appendChild(b);
  });
  renderBars();
})();

/* ---- tabs + section panels ---- */
var TABS = [{id:'__ov',label:'Overview'},{id:'__find',label:'Findings'}]
  .concat(M.concentration? [{id:'__conc',label:'Concentration'}] : [])
  .concat(M.sections.map(function(s,i){
  return {id:'sec'+i, label:s.title.replace(/^\d+\.\s*/,''), section:s};
}));
var active = '__ov';

function sevDot(s){
  var fails = s.checks.filter(function(c){return c.result==='FAIL';}).length;
  var flags = s.checks.filter(function(c){return c.result==='FLAG';}).length;
  if(fails) return '--fail'; if(flags) return '--flag'; return '--pass';
}
function buildTabs(){
  var host = el('tabs'); host.innerHTML='';
  TABS.forEach(function(t){
    var b=document.createElement('button'); b.className='tab'+(t.id===active?' active':'');
    var badge = t.id==='__find' && M.findings.length ? '<span class="badge">'+M.findings.length+'</span>' : '';
    b.innerHTML = esc(t.label) + badge + (t.section? '<span class="dot" style="background:var('+sevDot(t.section)+')"></span>':'');
    b.onclick=function(){ show(t.id); };
    host.appendChild(b);
  });
}
function checkRow(c){
  var applies = c.applies_to||'Both';
  var dim = inScope(c)? '' : ' style="opacity:.4"';
  return '<tr'+dim+'>'+
    '<td><span class="chk-id">'+esc(c.id)+'</span><br><span class="chk-name">'+esc(c.name)+'</span></td>'+
    '<td class="muted">'+esc(c.verify)+'</td>'+
    '<td class="muted">'+esc(applies)+'</td>'+
    '<td><span class="sev sev-'+esc(c.severity)+'">'+esc(c.severity)+'</span></td>'+
    '<td><span class="pill '+pillClass(c.result)+'">'+esc(c.result)+'</span></td>'+
    '<td>'+esc(c.observed)+'</td>'+
    '<td class="recos">'+esc(c.recommendation||'')+'</td></tr>';
}
function sectionPanelHTML(s,i){
  var pct = sectionPct(s);
  return '<div class="section-head"><h2>'+esc(s.title)+'</h2>'+
    '<span class="section-score">'+(pct==null?'n/a':pct+' / 100')+'</span></div>'+
    '<div class="card wide"><table class="tbl"><thead><tr>'+
    '<th>Check</th><th>What to verify</th><th>Applies</th><th>Severity</th><th>Result</th><th>Observed</th><th>Recommendation</th>'+
    '</tr></thead><tbody id="secbody'+i+'">'+ s.checks.map(checkRow).join('') +'</tbody></table></div>';
}
function renderActiveSection(){
  // re-render whichever section panel is visible so the business-model dim updates
  TABS.forEach(function(t,idx){
    if(t.section && t.id===active){
      var body = document.querySelector('#panel_'+t.id+' tbody');
      if(body) body.innerHTML = t.section.checks.map(checkRow).join('');
    }
  });
}
function staggerRows(panel){
  var g = gsapOn(); if(!g) return;
  var els = panel.querySelectorAll('tbody tr, .find-row');
  if(els.length) g.from(els,{y:8,opacity:0,duration:.35,stagger:.02,ease:'power1.out'});
}
function buildPanels(){
  var host = el('panels'); host.innerHTML='';
  TABS.forEach(function(t,i){
    var d=document.createElement('div'); d.className='panel'+(t.id===active?' active':''); d.id='panel_'+t.id;
    if(t.id==='__ov'){ d.innerHTML = '<div class="card pad"><h2 style="font-size:16px;margin-bottom:6px">How to read this report</h2><p class="muted" style="margin:0">Each area is scored PASS / FLAG / FAIL / N-A weighted by severity; the Health Score is the weighted percentage of points earned. Open a tab to see every check, or jump to <b>Findings</b> to prioritise the work by ICE (Impact × Confidence × Ease) — adjust Confidence and Ease to re-rank live.</p>'+(M.prescore? '<p class="muted" style="margin:10px 0 0;font-size:12.5px">'+M.prescore.applied.length+' of '+M.provenance.n_checks+' checks machine-scored deterministically from the data files'+(M.prescore.corrected.length? ' · '+M.prescore.corrected.length+' correction(s) applied over the drafted findings':'')+'.</p>' : '')+(M.concentration? '' : '<p class="muted" style="margin:10px 0 0;font-size:12.5px">Concentration analysis not included — raw pull files were not provided to the builder.</p>')+'<button class="btn" id="ovOpenFind" style="margin-top:14px">Open Findings ('+M.findings.length+') &rarr;</button></div>'; d.querySelector('#ovOpenFind').onclick=function(){ show('__find'); }; }
    else if(t.id==='__conc'){ d.innerHTML = concPanelHTML(); }
    else if(t.id==='__find'){ d.innerHTML = findingsPanelHTML(); }
    else { d.innerHTML = sectionPanelHTML(t.section, i); }
    host.appendChild(d);
  });
}
function show(id){
  active = id;
  document.querySelectorAll('.tab').forEach(function(b,i){ b.classList.toggle('active', TABS[i].id===id); });
  document.querySelectorAll('.panel').forEach(function(p){ p.classList.toggle('active', p.id==='panel_'+id); });
  var panel = el('panel_'+id);
  if(id==='__find'){ wireFindings(); }
  if(panel) staggerRows(panel);
  if(panel && panel.querySelector('table')) renderActiveSection();
}

/* ---- findings + live ICE ---- */
var ICE = M.findings.map(function(f){ return {f:f, conf:5, ease:5}; });
var fSort = {k:'ice', dir:-1};
var fSev = {}, fHzn = {};
function iceVal(r){ return (r.f.impact||0) * r.conf * r.ease; }
function findingsRows(){
  var rows = ICE.filter(function(r){
    if(Object.keys(fSev).length && !fSev[r.f.severity]) return false;
    if(Object.keys(fHzn).length && !fHzn[String(r.f.horizon)]) return false;
    return true;
  });
  rows.sort(function(a,b){
    var k=fSort.k, va,vb;
    if(k==='ice'){ va=iceVal(a); vb=iceVal(b); }
    else if(k==='sev'){ va=a.f.impact||0; vb=b.f.impact||0; }
    else if(k==='hzn'){ va=+a.f.horizon||999; vb=+b.f.horizon||999; }
    else { va=''+a.f[k]; vb=''+b.f[k]; return fSort.dir*va.localeCompare(vb); }
    return fSort.dir*(va-vb);
  });
  return rows;
}
/* ---- concentration panel (all verdicts/bands precomputed in Python) ---- */
function fmtN(v){ return (typeof v==='number')? v.toLocaleString('en-US',{maximumFractionDigits:2}) : ''; }
function fmtPct(v){ return (v*100).toFixed(1)+'%'; }
function bandPill(m){
  if(!m) return '<span class="pill p-NA">no signal</span>';
  var cls = m.band==='high'? 'p-FAIL' : (m.band==='moderate'? 'p-FLAG' : 'p-PASS');
  return '<span class="pill '+cls+'">'+esc(m.band)+'</span>';
}
function lorenzSVG(lz){
  if(!lz || !lz.spend) return '';
  function path(pts){
    return pts.map(function(p,i){
      var x = 20 + p[0]*200, y = 220 - p[1]*200;
      return (i? 'L':'M') + x.toFixed(1) + ' ' + y.toFixed(1);
    }).join(' ');
  }
  var s = '<svg class="lorenz" viewBox="0 0 240 240" role="img" aria-label="Lorenz curve">'+
    '<rect class="lz-frame" x="20" y="20" width="200" height="200"/>'+
    '<line class="lz-diag" x1="20" y1="220" x2="220" y2="20"/>'+
    '<path class="lz-spend" d="'+path(lz.spend)+'"/>';
  if(lz.conv) s += '<path class="lz-conv" d="'+path(lz.conv)+'"/>';
  return s+'</svg>';
}
function concDimHTML(dim){
  var kpis = '<div class="kpis" style="margin-top:12px">'+
    '<div class="kpi"><div class="m">Spend HHI</div><div class="v">'+fmtN(dim.spend? dim.spend.hhi:null)+'</div><div class="b">'+bandPill(dim.spend)+'</div></div>'+
    '<div class="kpi"><div class="m">Conversions HHI</div><div class="v">'+fmtN(dim.conv? dim.conv.hhi:null)+'</div><div class="b">'+bandPill(dim.conv)+'</div></div>'+
    '<div class="kpi"><div class="m">Effective-N</div><div class="v">'+fmtN(dim.spend? dim.spend.eff_n:null)+'</div><div class="b">conversions: '+(dim.conv? fmtN(dim.conv.eff_n):'—')+'</div></div>'+
    '<div class="kpi"><div class="m">Gini</div><div class="v">'+fmtN(dim.spend? dim.spend.gini:null)+'</div><div class="b">conversions: '+(dim.conv? fmtN(dim.conv.gini):'—')+'</div></div>'+
    '<div class="kpi"><div class="m">Entities</div><div class="v">'+fmtN(dim.n_entities)+'</div><div class="b">'+fmtN(dim.n_rows_raw)+' raw rows</div></div></div>';
  var rows = (dim.top||[]).map(function(t){
    return '<tr><td>'+esc(t.name)+'</td><td class="mono">'+fmtN(t.spend)+'</td><td class="mono">'+fmtN(t.conv)+'</td>'+
      '<td class="mono">'+fmtPct(t.spend_share)+'</td><td class="mono">'+fmtPct(t.conv_share)+'</td><td>'+esc(t.abc)+'</td></tr>';
  }).join('');
  if(dim.tail){
    rows += '<tr><td class="muted">… plus '+fmtN(dim.tail.n)+' more (tail)</td><td class="mono">'+fmtN(dim.tail.spend)+'</td>'+
      '<td class="mono">'+fmtN(dim.tail.conv)+'</td><td class="mono">'+fmtPct(dim.tail.spend_share)+'</td><td></td><td></td></tr>';
  }
  return '<div class="card pad" style="margin-top:16px">'+
    '<div class="section-head"><h2>'+esc(dim.label)+(dim.window? ' <span class="muted" style="font-weight:400;font-size:13px">('+esc(dim.window)+')</span>':'')+'</h2>'+bandPill(dim.spend)+'</div>'+
    '<div class="verdict v-'+esc(dim.verdict_key)+'">'+esc(dim.verdict)+'</div>'+
    kpis+
    '<div class="lorenz-wrap">'+lorenzSVG(dim.lorenz)+
    '<div style="flex:1;min-width:280px"><table class="tbl"><thead><tr>'+
    '<th>Entity</th><th>Spend</th><th>Conv</th><th>Spend %</th><th>Conv %</th><th>ABC</th>'+
    '</tr></thead><tbody>'+rows+'</tbody></table>'+
    '<div class="lz-legend"><span><span class="lz-key"></span>spend</span><span><span class="lz-key k-conv"></span>conversions</span></div></div></div>'+
    (dim.caveat? '<p class="muted" style="margin:12px 0 0;font-size:12.5px">'+esc(dim.caveat)+'</p>':'')+
    '</div>';
}
function concPanelHTML(){
  var C = M.concentration;
  var intro = '<div class="card pad"><h2 style="font-size:16px;margin-bottom:6px">Where spend and conversions concentrate</h2>'+
    '<p class="muted" style="margin:0">HHI measures concentration on a 0–10,000 scale (merger-guideline bands: below 1,500 unconcentrated · 1,500–2,500 moderate · above 2,500 high). '+
    'Effective-N reads as "spend behaves as if only N entities exist." The verdict compares spend vs conversion concentration — the gap between the two is the action signal. '+
    'Farther below the diagonal on the Lorenz curve = more concentrated.</p></div>';
  var notes = (C.notes||[]).map(function(n){ return '<p class="muted" style="margin:12px 0 0;font-size:12.5px">Note: '+esc(n)+'</p>'; }).join('');
  return intro + C.dimensions.map(concDimHTML).join('') + notes;
}

function findingsPanelHTML(){
  return '<div class="controls">'+
    '<label class="fld">Default confidence <input class="num" id="defConf" type="number" min="1" max="10" value="5"></label>'+
    '<label class="fld">Default ease <input class="num" id="defEase" type="number" min="1" max="10" value="5"></label>'+
    '<span style="flex:1"></span></div>'+
    '<div class="controls" id="findFilters"></div>'+
    '<div class="card wide"><table class="tbl sortable"><thead><tr>'+
    '<th style="width:52px">Rank</th><th data-k="title">Finding</th><th data-k="sev">Severity</th>'+
    '<th data-k="hzn">Horizon</th><th style="width:74px">Conf</th><th style="width:74px">Ease</th>'+
    '<th data-k="ice" style="width:70px">ICE</th><th data-k="section">Area</th>'+
    '</tr></thead><tbody id="findBody"></tbody></table></div>';
}
function renderFindings(){
  var body = el('findBody'); if(!body) return;
  var rows = findingsRows();
  if(!rows.length){ body.innerHTML = '<tr><td colspan="8" class="empty">No findings match the current filter.</td></tr>'; return; }
  body.innerHTML = rows.map(function(r,idx){
    var i = ICE.indexOf(r);
    return '<tr class="find-row">'+
      '<td><span class="rank">'+(idx+1)+'</span></td>'+
      '<td><b>'+esc(r.f.title)+'</b><br><span class="muted" style="font-size:12.5px">'+esc(r.f.recommendation||'')+'</span></td>'+
      '<td><span class="sev sev-'+esc(r.f.severity)+'">'+esc(r.f.severity)+'</span></td>'+
      '<td><span class="hzn">'+esc(r.f.horizon)+'d</span></td>'+
      '<td><input class="num" data-i="'+i+'" data-t="conf" type="number" min="1" max="10" value="'+r.conf+'"></td>'+
      '<td><input class="num" data-i="'+i+'" data-t="ease" type="number" min="1" max="10" value="'+r.ease+'"></td>'+
      '<td><span class="ice">'+iceVal(r)+'</span></td>'+
      '<td class="muted">'+esc(r.f.section||'')+'</td></tr>';
  }).join('');
  body.querySelectorAll('input.num').forEach(function(inp){
    inp.oninput=function(){
      var i=+inp.getAttribute('data-i'), t=inp.getAttribute('data-t');
      var v=Math.max(1,Math.min(10, +inp.value||5)); ICE[i][t]=v; renderFindings();
    };
  });
}
var findWired=false;
function wireFindings(){
  if(findWired) return; findWired=true;
  var host = el('findFilters');
  host.innerHTML = '<span class="whatif">Severity:</span>';
  ['Critical','High','Medium','Low'].forEach(function(s){
    var b=document.createElement('button'); b.className='chip'; b.textContent=s;
    b.onclick=function(){ if(fSev[s]) delete fSev[s]; else fSev[s]=1; b.classList.toggle('on'); renderFindings(); };
    host.appendChild(b);
  });
  var sp=document.createElement('span'); sp.className='whatif'; sp.textContent='Horizon:'; sp.style.marginLeft='8px'; host.appendChild(sp);
  ['30','60','90'].forEach(function(h){
    var b=document.createElement('button'); b.className='chip'; b.textContent=h+'d';
    b.onclick=function(){ if(fHzn[h]) delete fHzn[h]; else fHzn[h]=1; b.classList.toggle('on'); renderFindings(); };
    host.appendChild(b);
  });
  el('defConf').oninput=function(){ var v=Math.max(1,Math.min(10,+this.value||5)); ICE.forEach(function(r){r.conf=v;}); renderFindings(); };
  el('defEase').oninput=function(){ var v=Math.max(1,Math.min(10,+this.value||5)); ICE.forEach(function(r){r.ease=v;}); renderFindings(); };
  document.querySelectorAll('#panel___find th[data-k]').forEach(function(th){
    th.onclick=function(){ var k=th.getAttribute('data-k'); if(fSort.k===k) fSort.dir*=-1; else {fSort.k=k; fSort.dir=(k==='ice'||k==='sev')?-1:1;} renderFindings(); };
  });
  renderFindings();
}

/* ---- theme toggle support (host may stamp data-theme) ---- */
buildTabs(); buildPanels(); show('__ov');
})();
</script>
</body>
</html>"""
