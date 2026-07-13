#!/usr/bin/env python3
# Copyright (c) 2026 Clickt Digital Marketing Inc. All rights reserved.
"""Interactive, self-contained HTML report for shopify-cro-audit (the PRIMARY deliverable).

Ported from meta-ads-audit `scripts/audit_html.py` — bespoke renderer (the CRO audit's
11-step / Funnel-Health-0-150 shape does not fit the generic `_shared/render` row+slider
engine, so — like the ads audits — it ships its own). One `_TEMPLATE` raw string with
inline CSS/JS; the model is embedded as JSON and the whole report is rendered
client-side. ZERO external references: the only third-party bytes are GSAP, inlined
between the `/*__GSAP_JS_BEGIN__*/ … /*__GSAP_JS_END__*/` sentinels (the
self-containment test excises that checksummed region before scanning).

CRO deltas vs the meta renderer:
- Titles/eyebrow/fallbacks say "Shopify CRO Audit"; provenance is `model["meta"]`
  (store_name / store_url / date_range / generated_for_date).
- The gauge is **0-150 Funnel Health**: arc target C*(1-score/150), "out of 150"
  label, count-up to the INT score (the model's score is an integer — Excel
  ROUND(...,0) parity), one grade color per letter A/B/C/D/F.
- `healthOf()` mirrors `audit_model.funnel_health` exactly: mean of rate/bench over
  the MEASURED funnel stages only (read from the Step-1 funnel evidence table),
  x100, capped at 150, Math.round (half-up on the non-negative domain).
- Sections have NO check rows: each renders a run/partial/not_run status banner
  (muted, mirroring the workbook's `notrun_banner_if_needed` wording) plus its
  `evidence` — a LIST of labeled {label, columns, rows} tables. "Read" columns
  render as PASS/FLAG/FAIL-style pills; "Index" columns get 100/70 color coding.
- Findings: Bucket column + LIVE Impact & Ease re-ranking via PRI = i*2 + e and
  the Now/Next/Soon/Later BUCKETS (NO Confidence anywhere — the framework dropped
  it on purpose).
- JS constants: GRADES=[[110,'A'],[90,'B'],[70,'C'],[50,'D'],[0,'F']] is the ONLY
  [N,'X']-shaped literal in the file (BUCKETS uses multi-char strings — safe
  against the GRADES-shape regex in tests); BENCH mirrors audit_model.BENCH.
- Concentration panel ports with weight/outcome labels (JSON keys stay spend/conv;
  verdict key `review_mix` replaces meta's `review_bidding`); NEW CVR Signals
  panel is data-driven from `M.cvr_signals` (site CVR + Wilson CI headline,
  segment z-tests with significance pills, pages raw/shrunk/Wilson-LB with gate
  badges, notes).
- Overview carries the machine-layer line: "N analytics fields machine-computed ·
  M correction(s)" from `M.machine` (applied/corrected lengths).

Design guarantees:
- **White-label:** no logo, no Clickt credit — the report leads with the store's name.
  URL schemes are stripped from the embedded model copy (`https?://` -> bare domain)
  so the rendered file carries no external-reference substrings outside the GSAP
  sentinels; display is unaffected (domains read fine bare).
- **Score parity:** the JS kernel mirrors `audit_model`'s constants verbatim (asserted
  in tests); the gauge shows the Python-authoritative `model.health` so HTML, md, and
  xlsx never disagree by a rounding step.
- **Motion:** GSAP for the score count-up, gauge sweep, and staggered reveals; every call
  is guarded by `prefers-reduced-motion` + `window.gsap` presence, and `animate=False`
  strips GSAP entirely, leaving a fully functional static report.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_VENDOR = _HERE / "vendor"

GSAP_BEGIN = "/*__GSAP_JS_BEGIN__*/"
GSAP_END = "/*__GSAP_JS_END__*/"

# Self-containment scrub: the payload's store_url (and any evidence text) may carry
# URL schemes; the rendered artifact must not (no external-reference substrings
# outside the GSAP sentinels). Bare domains display fine.
_URL_SCHEME = re.compile(r"https?://")


def gsap_blob() -> str:
    """The vendored GSAP core wrapped in sentinels (byte-checksum enforced by tests)."""
    return GSAP_BEGIN + "\n" + (_VENDOR / "gsap.min.js").read_text(encoding="utf-8") + "\n" + GSAP_END


def _esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def render_html(model: dict, *, animate: bool = True) -> str:
    """Render the self-contained interactive report string from a computed model."""
    data = json.dumps(model, ensure_ascii=False, separators=(",", ":"))
    data = _URL_SCHEME.sub("", data).replace("</", "<\\/")
    title = _esc(model.get("meta", {}).get("store_name", "") or "Shopify CRO Audit")
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
# NOTE for editors: no JS literal shaped [<digits>,'<A–F>'] may appear outside
# the GRADES table (bucket data uses multi-char strings — 'Now'/'Next'/'Soon'/
# 'Later' cannot match the single-letter class), and no external reference
# substrings may appear outside the GSAP sentinels.
# ==========================================================================
_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Shopify CRO Audit — /*__TITLE__*/</title>
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
.meta{margin-top:12px;display:flex;flex-wrap:wrap;gap:6px 18px;font-size:13px;color:#C7D6D4;
  align-items:center}
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

/* kpi tiles (coverage) */
.kpis{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
.kpi{border:1px solid var(--line);border-radius:12px;padding:12px 14px;background:var(--card)}
.kpi .m{font-size:12px;color:var(--slate);font-weight:600}
.kpi .v{font-size:22px;font-weight:680;margin:2px 0;font-family:var(--mono)}
.kpi .b{font-size:11px;color:var(--slate)}

/* benchmark bars */
.bars{display:flex;flex-direction:column;gap:9px}
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

/* step status banners (mirror the workbook's notrun banner wording) */
.sbanner{border-radius:12px;padding:12px 16px;font-size:13px;font-weight:600;margin:0 0 14px}
.sb-partial{background:var(--flag-bg);color:var(--flag)}
.sb-na{background:var(--na-bg);color:var(--na)}

/* concentration */
.verdict{border-radius:12px;padding:12px 16px;font-size:13.5px;font-weight:600;margin:14px 0}
.v-fragility{background:var(--fail-bg);color:var(--fail)}
.v-consolidate,.v-review_mix{background:var(--flag-bg);color:var(--flag)}
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
.muted{color:var(--slate)}
.recos{color:var(--ink)}
.wide{overflow-x:auto;border-radius:14px}
.section-head{display:flex;align-items:center;justify-content:space-between;gap:12px;
  flex-wrap:wrap;margin:2px 0 12px}
.section-head h2{font-size:18px}

/* controls */
.controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:2px 0 14px}
.chip{appearance:none;border:1px solid var(--line);background:var(--card);color:var(--slate);
  font:inherit;font-weight:600;font-size:12.5px;padding:5px 11px;border-radius:999px;cursor:pointer}
.chip.on{background:var(--ink);color:var(--card);border-color:var(--ink)}
.whatif{font-size:12.5px;color:var(--slate);margin-left:2px}
.whatif b{color:var(--purple)}
input.num{width:56px;font:inherit;font-family:var(--mono);text-align:center;padding:5px 6px;
  border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink)}
input.num:focus{outline:2px solid var(--accent);outline-offset:1px}
.rank{display:inline-flex;align-items:center;justify-content:center;min-width:26px;height:26px;
  padding:0 7px;border-radius:8px;background:var(--accent);color:#fff;font-weight:700;font-size:13px;
  font-family:var(--mono)}
.pri{font-family:var(--mono);font-weight:680}
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
    <div class="eyebrow">Shopify CRO Audit</div>
    <div class="client" id="clientName"></div>
    <div class="meta" id="metaLine"></div>
  </div>
</header>
<main class="wrap">
  <div class="grid">
    <div class="ov">
      <div class="card gauge-card">
        <div class="glabel">Funnel Health</div>
        <div class="gauge-wrap">
          <svg class="gauge" viewBox="0 0 180 180" aria-hidden="true">
            <circle class="gtrack" cx="90" cy="90" r="70"></circle>
            <circle class="gprog" id="gaugeArc" cx="90" cy="90" r="70"></circle>
          </svg>
          <div class="gcenter">
            <div class="gnum"><span id="gaugeNum">0</span></div>
            <div class="gpct">out of 150</div>
          </div>
        </div>
        <div class="ggrade" id="gaugeGrade">—</div>
      </div>
      <div class="card pad">
        <h3 style="font-size:14px;margin-bottom:12px">Coverage</h3>
        <div class="kpis" id="kpis"></div>
      </div>
    </div>

    <div class="card pad">
      <div class="section-head">
        <h2 style="font-size:16px">Funnel &amp; device vs benchmark</h2>
        <span class="whatif">index · 100 = benchmark</span>
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
/* Constants mirrored VERBATIM from audit_model.py (parity asserted in tests).
   GRADES is the ONLY [N,'X']-shaped literal in this file. */
var GRADES=[[110,'A'],[90,'B'],[70,'C'],[50,'D'],[0,'F']];
var BENCH={atc:7.23,checkout:5.96,cvr:2.99,mobile:2.87,desktop:4.51};
var IMPACT={Critical:9,High:7,Medium:5,Low:3};
var PRI=function(i,e){return i*2+e;};
var BUCKETS=[[24,'Now'],[20,'Next'],[15,'Soon'],[0,'Later']];
var STAGES=['atc','checkout','cvr'];
var reduce = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion:reduce)').matches;
function gsapOn(){ return (typeof window!=='undefined' && window.gsap && !reduce) ? window.gsap : null; }

function esc(s){ s=(s==null?'':''+s); return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function el(id){ return document.getElementById(id); }
function gradeOf(s){ for(var i=0;i<GRADES.length;i++){ if(s>=GRADES[i][0]) return GRADES[i][1]; } return 'F'; }
function bucketOf(p){ for(var i=0;i<BUCKETS.length;i++){ if(p>=BUCKETS[i][0]) return BUCKETS[i][1]; } return BUCKETS[BUCKETS.length-1][1]; }
function funnelTable(){ var s0=(M.sections||[])[0]||{}; return (s0.evidence||[])[0]||null; }
function healthOf(){
  /* Funnel Health 0-150 — byte-consistent with audit_model.funnel_health:
     mean of rate/bench over the MEASURED stages only (blank stages excluded,
     never scored 0), x100, capped at 150, Math.round (half-up — the score is
     never negative, so this matches Excel ROUND / Python _round_half_up). */
  var t = funnelTable();
  if(!t || !(t.rows||[]).length) return {score:null, grade:'—'};
  var sum=0, n=0;
  t.rows.slice(1).forEach(function(r,i){
    var rate=(r||[])[2];
    if(typeof rate==='number' && isFinite(rate) && i<STAGES.length){ sum += rate/BENCH[STAGES[i]]; n++; }
  });
  if(!n) return {score:null, grade:'—'};
  var sc = Math.round(Math.min(150, 100*(sum/n)));
  return {score:sc, grade:gradeOf(sc)};
}

/* ---- palette helpers ---- */
function css(v){ return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); }
function gradeColor(g){ return {A:'--lime',B:'--teal',C:'--purple',D:'--ember',F:'--fail'}[g] || '--teal'; }
function readPill(v){
  if(v==null || v==='') return '';
  var s=''+v;
  var cls = s==='At / above benchmark' ? 'p-PASS'
          : s==='Below benchmark' ? 'p-FLAG'
          : s==='Well below benchmark' ? 'p-FAIL' : 'p-NA';
  return '<span class="pill '+cls+'">'+esc(s)+'</span>';
}
function idxCell(v){
  if(v==null || v==='') return '';
  var n=+v; var col = n>=100? '--pass' : n>=70? '--flag' : '--fail';
  return '<span class="mono" style="color:var('+col+');font-weight:680">'+esc(v)+'</span>';
}
function statusPill(st){
  if(st==='run') return '<span class="pill p-PASS">Run</span>';
  if(st==='partial') return '<span class="pill p-FLAG">Partial</span>';
  return '<span class="pill p-NA">Not run</span>';
}
function statusDot(st){ return st==='run'? '--pass' : st==='partial'? '--flag' : '--na'; }

/* ---- header ---- */
var P = M.meta;
el('clientName').textContent = P.store_name || 'Shopify CRO Audit';
(function(){
  var bits=[];
  if(P.store_url) bits.push('<span>Store <b>'+esc(P.store_url)+'</b></span>');
  if(P.date_range) bits.push('<span>Window <b>'+esc(P.date_range)+'</b></span>');
  if(P.currency) bits.push('<span>Currency <b>'+esc(P.currency)+'</b></span>');
  if(P.generated_for_date) bits.push('<span>Audited <b>'+esc(P.generated_for_date)+'</b></span>');
  el('metaLine').innerHTML = bits.join('');
  el('footL').textContent = (P.n_steps||0)+' steps · '+(P.n_steps_run||0)+' run · '
    +(P.n_findings||0)+' findings · generated '+(P.generated||'');
})();

/* ---- gauge. Python-authoritative INT score → no rounding drift vs xlsx/md.
   Arc target = C*(1-score/150). The final state is written DIRECTLY so it is
   correct even when the motion ticker never runs (reduced-motion, a background
   tab); GSAP then replays it from empty/zero via proxy objects as a pure
   enhancement. ---- */
(function(){
  var score = M.health.score, grade = M.health.grade;
  var arc = el('gaugeArc'), C = 2*Math.PI*70;
  arc.style.strokeDasharray = C;
  var gp = el('gaugeGrade');
  if(score==null){
    arc.style.strokeDashoffset = C;
    el('gaugeNum').textContent = '—';
    gp.textContent = 'No measured stages';
    gp.style.background = css('--na-bg'); gp.style.color = css('--na');
    return;
  }
  var target = C*(1-score/150);
  var col = css(gradeColor(grade)) || css('--teal');
  arc.style.stroke = col;
  gp.textContent = 'Grade '+grade;
  gp.style.background = col; gp.style.color = '#fff';
  arc.style.strokeDashoffset = target;      // robust final state
  el('gaugeNum').textContent = score;        // robust final state (INT)
  var g = gsapOn();
  if(g){
    var a={o:C};
    g.to(a,{o:target,duration:1.1,ease:'power2.out',onUpdate:function(){ arc.style.strokeDashoffset = a.o; }});
    var n={v:0};
    g.to(n,{v:score,duration:1.1,ease:'power2.out',
      onUpdate:function(){ el('gaugeNum').textContent = Math.round(n.v); },
      onComplete:function(){ el('gaugeNum').textContent = score; }});
  }
})();

/* ---- coverage tiles (CRO has no KPI scorecard — steps + findings instead) ---- */
(function(){
  var S = M.summary||{}, B = S.findings_by_bucket||{};
  var tiles = [
    {m:'Steps run', v:(S.n_run||0)+' / '+(P.n_steps||0),
     b:(S.n_partial||0)+' partial · '+(S.n_not_run||0)+' not run'},
    {m:'Findings', v:(P.n_findings||0),
     b:(S.crit||0)+' critical · '+(S.high||0)+' high · '+(S.med||0)+' medium · '+(S.low||0)+' low'},
    {m:'Now / Next', v:(B.Now||0)+' / '+(B.Next||0),
     b:'Soon '+(B.Soon||0)+' · Later '+(B.Later||0)}
  ];
  if(M.machine){
    tiles.push({m:'Machine layer', v:(M.machine.applied||[]).length,
      b:'analytics fields machine-computed · '+(M.machine.corrected||[]).length+' correction(s)'});
  }
  el('kpis').innerHTML = tiles.map(function(k){
    return '<div class="kpi"><div class="m">'+esc(k.m)+'</div><div class="v">'+esc(k.v)+
      '</div><div class="b">'+esc(k.b)+'</div></div>';
  }).join('');
})();

/* ---- benchmark index bars (funnel stages + benched device rows, Step 1) ---- */
function renderBars(){
  var host = el('bars');
  var s0=(M.sections||[])[0]||{}, evs=s0.evidence||[];
  var rows=[];
  [0,1].forEach(function(ti){
    var t=evs[ti]; if(!t) return;
    (t.rows||[]).forEach(function(r){
      var idx=(r||[])[4];
      if(typeof idx==='number' && isFinite(idx)) rows.push({label:r[0], idx:idx, read:r[5]});
    });
  });
  if(!rows.length){ host.innerHTML='<div class="muted">No measured analytics supplied.</div>'; return; }
  host.innerHTML = rows.map(function(b){
    var w = Math.max(0, Math.min(150, b.idx))/150*100;
    var col = b.idx>=100? '--pass' : b.idx>=70? '--flag' : '--fail';
    return '<div class="bar-cell"><div class="bar-lab"><span>'+esc(b.label)+'</span>'+
      '<span class="bar-val">'+esc(b.idx)+'</span></div>'+
      '<div class="bar-track"><div class="bar-fill" style="background:var('+col+')" data-w="'+w.toFixed(2)+'"></div></div></div>';
  }).join('');
  // widths: set final directly (robust even without a live ticker); GSAP replays from 0.
  var fills = host.querySelectorAll('.bar-fill');
  var g = gsapOn();
  fills.forEach(function(f){
    var w = f.getAttribute('data-w');
    f.style.width = w + '%';
    if(g){ var pr={x:0}; g.to(pr,{x:+w,duration:.7,ease:'power2.out',onUpdate:function(){ f.style.width = pr.x + '%'; }}); }
  });
}
renderBars();

/* ---- tabs + panels ---- */
var TABS = [{id:'__ov',label:'Overview'},{id:'__find',label:'Findings'}]
  .concat(M.concentration? [{id:'__conc',label:'Concentration'}] : [])
  .concat(M.cvr_signals? [{id:'__cvr',label:'CVR Signals'}] : [])
  .concat(M.sections.map(function(s,i){
    return {id:'sec'+i, label:s.step+'. '+s.title.replace(/^Step\s*\d+\s*—\s*/,''), section:s};
  }));
var active = '__ov';

function buildTabs(){
  var host = el('tabs'); host.innerHTML='';
  TABS.forEach(function(t){
    var b=document.createElement('button'); b.className='tab'+(t.id===active?' active':'');
    var badge = t.id==='__find' && M.findings.length ? '<span class="badge">'+M.findings.length+'</span>' : '';
    b.innerHTML = esc(t.label) + badge + (t.section? '<span class="dot" style="background:var('+statusDot(t.section.status)+')"></span>':'');
    b.onclick=function(){ show(t.id); };
    host.appendChild(b);
  });
}

/* ---- evidence tables: a LIST of labeled tables per step ---- */
function fmtCell(col, v){
  if(v==null || v==='') return '';
  if(col==='Read') return readPill(v);
  if(col==='Index') return idxCell(v);
  if(typeof v==='number') return '<span class="mono">'+fmtN(v)+'</span>';
  return esc(v);
}
function evTableHTML(t){
  var cols = (t||{}).columns||[];
  if(!cols.length) return '';
  var rows = t.rows||[];
  var body = rows.length ? rows.map(function(r){
      return '<tr>'+ cols.map(function(c,ci){ return '<td>'+fmtCell(c,(r||[])[ci])+'</td>'; }).join('') +'</tr>';
    }).join('') : '<tr><td colspan="'+cols.length+'" class="empty">No rows.</td></tr>';
  return '<div class="card" style="margin-top:16px">'+
    '<div class="pad" style="padding-bottom:10px"><h3 style="font-size:14px">'+esc(t.label||'')+'</h3></div>'+
    '<div class="wide"><table class="tbl"><thead><tr>'+
    cols.map(function(c){ return '<th>'+esc(c)+'</th>'; }).join('')+
    '</tr></thead><tbody>'+body+'</tbody></table></div></div>';
}
function sectionPanelHTML(s){
  var out = '<div class="section-head"><h2>'+esc(s.title)+'</h2>'+statusPill(s.status)+'</div>';
  /* status banners — muted, mirroring build_cro_workbook.notrun_banner_if_needed */
  if(s.status==='partial'){
    out += '<div class="sbanner sb-partial">PARTIAL — limited data provided.'+(s.reason? ' '+esc(s.reason):'')+'</div>';
  } else if(s.status!=='run'){
    out += '<div class="sbanner sb-na">NOT RUN — data not provided.'+(s.reason? ' '+esc(s.reason):'')+'</div>';
  } else if(s.reason){
    out += '<p class="muted" style="margin:0 0 14px;font-size:12.5px">'+esc(s.reason)+'</p>';
  }
  var ev = (s.evidence||[]).map(evTableHTML).join('');
  if(ev){ out += ev; }
  else if(s.step===11){
    out += '<div class="card pad"><p class="muted" style="margin:0">The prioritised findings ARE this step — open the <b>Findings</b> tab to work the roadmap (Priority = Impact × 2 + Ease; Now / Next / Soon / Later).</p></div>';
  } else if(s.status==='run'){
    out += '<div class="card"><div class="empty">No evidence tables supplied for this step.</div></div>';
  }
  return out;
}
function staggerRows(panel){
  var g = gsapOn(); if(!g) return;
  var els = panel.querySelectorAll('tbody tr, .find-row');
  if(els.length) g.from(els,{y:8,opacity:0,duration:.35,stagger:.02,ease:'power1.out'});
}
function overviewHTML(){
  var h = '<div class="card pad"><h2 style="font-size:16px;margin-bottom:6px">How to read this report</h2>'+
    '<p class="muted" style="margin:0">Funnel Health scores the measured funnel stages against FY2025 DTC benchmarks '+
    '(added-to-cart '+BENCH.atc+'% · checkout '+BENCH.checkout+'% · purchase '+BENCH.cvr+'%): '+
    '100 × the mean of rate ÷ benchmark, capped at 150. Grade: A ≥ 110 · B ≥ 90 · C ≥ 70 · D ≥ 50 · else F. '+
    'Each of the 11 method-steps carries a run / partial / not-run status — open a step tab for its evidence. '+
    'Jump to <b>Findings</b> to prioritise the work by <b>Priority = Impact × 2 + Ease</b> '+
    '(Now ≥ 24 · Next ≥ 20 · Soon ≥ 15 · else Later) — adjust Impact and Ease to re-rank live.</p>';
  h += '<p class="muted" style="margin:10px 0 0;font-size:12.5px">'+
    (M.summary.n_run||0)+' of '+(P.n_steps||0)+' steps run · '+(M.summary.n_partial||0)+
    ' partial · '+(M.summary.n_not_run||0)+' not run.</p>';
  if(M.machine){
    h += '<p class="muted" style="margin:10px 0 0;font-size:12.5px">'+
      (M.machine.applied||[]).length+' analytics fields machine-computed · '+
      (M.machine.corrected||[]).length+' correction(s) applied over the transcribed payload.</p>';
  }
  if(M.cvr_signals){
    var st = M.cvr_signals.site||{};
    h += '<p class="muted" style="margin:10px 0 0;font-size:12.5px">CVR significance: site CVR '+
      fmtPct2(st.cvr)+' (95% Wilson CI '+fmtPct2((st.ci||[])[0])+'–'+fmtPct2((st.ci||[])[1])+
      ') — see the <b>CVR Signals</b> tab.</p>';
  }
  if(!M.concentration){
    h += '<p class="muted" style="margin:10px 0 0;font-size:12.5px">Concentration analysis not included — raw pull / CSV files were not provided to the builder.</p>';
  }
  h += '<button class="btn" id="ovOpenFind" style="margin-top:14px">Open Findings ('+M.findings.length+') &rarr;</button></div>';
  return h;
}
function buildPanels(){
  var host = el('panels'); host.innerHTML='';
  TABS.forEach(function(t){
    var d=document.createElement('div'); d.className='panel'+(t.id===active?' active':''); d.id='panel_'+t.id;
    if(t.id==='__ov'){ d.innerHTML = overviewHTML(); d.querySelector('#ovOpenFind').onclick=function(){ show('__find'); }; }
    else if(t.id==='__conc'){ d.innerHTML = concPanelHTML(); }
    else if(t.id==='__cvr'){ d.innerHTML = cvrPanelHTML(); }
    else if(t.id==='__find'){ d.innerHTML = findingsPanelHTML(); }
    else { d.innerHTML = sectionPanelHTML(t.section); }
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
}

/* ---- findings + LIVE Priority = Impact x 2 + Ease (deliberately NOT ICE —
   the framework dropped the third factor; triangulation already encodes it,
   so the ONLY editable inputs are Impact and Ease) ---- */
var ROWS = M.findings.map(function(f){
  var imp=+f.impact; if(!isFinite(imp)||imp<1) imp=IMPACT[f.severity]||5;
  var eas=+f.ease; if(!isFinite(eas)||eas<1) eas=5;
  return {f:f, impact:imp, ease:eas};
});
var fSort = {k:'pri', dir:-1};
var fSev = {}, fBkt = {};
function priVal(r){ return PRI(r.impact, r.ease); }
function findingsRows(){
  var rows = ROWS.filter(function(r){
    if(Object.keys(fSev).length && !fSev[r.f.severity]) return false;
    if(Object.keys(fBkt).length && !fBkt[bucketOf(priVal(r))]) return false;
    return true;
  });
  rows.sort(function(a,b){
    var k=fSort.k, va,vb;
    if(k==='pri' || k==='bucket'){ va=priVal(a); vb=priVal(b); }
    else if(k==='sev'){ va=IMPACT[a.f.severity]||0; vb=IMPACT[b.f.severity]||0; }
    else { va=''+a.f[k]; vb=''+b.f[k]; return fSort.dir*va.localeCompare(vb); }
    return fSort.dir*(va-vb);
  });
  return rows;
}
function findingsPanelHTML(){
  return '<div class="controls"><span class="whatif">Priority = <b>Impact × 2 + Ease</b> · '+
    'buckets: Now ≥ 24 · Next ≥ 20 · Soon ≥ 15 · else Later — edit Impact / Ease to re-rank live.</span></div>'+
    '<div class="controls" id="findFilters"></div>'+
    '<div class="card wide"><table class="tbl sortable"><thead><tr>'+
    '<th style="width:52px">Rank</th><th data-k="title">Finding</th><th data-k="sev">Severity</th>'+
    '<th data-k="bucket">Bucket</th><th style="width:74px">Impact</th><th style="width:74px">Ease</th>'+
    '<th data-k="pri" style="width:80px">Priority</th><th data-k="page">Page</th>'+
    '</tr></thead><tbody id="findBody"></tbody></table></div>';
}
function renderFindings(){
  var body = el('findBody'); if(!body) return;
  var rows = findingsRows();
  if(!rows.length){ body.innerHTML = '<tr><td colspan="8" class="empty">No findings match the current filter.</td></tr>'; return; }
  body.innerHTML = rows.map(function(r,idx){
    var i = ROWS.indexOf(r);
    var pri = priVal(r);
    var srcs = (r.f.step_sources||[]).join(' · ');
    return '<tr class="find-row">'+
      '<td><span class="rank">'+(idx+1)+'</span></td>'+
      '<td><b>'+esc(r.f.title)+'</b><br><span class="muted" style="font-size:12.5px">'+esc(r.f.recommendation||'')+'</span>'+
      (srcs? '<br><span class="muted" style="font-size:11.5px">Sources: '+esc(srcs)+'</span>':'')+'</td>'+
      '<td><span class="sev sev-'+esc(r.f.severity)+'">'+esc(r.f.severity)+'</span></td>'+
      '<td><span class="hzn">'+esc(bucketOf(pri))+'</span></td>'+
      '<td><input class="num" data-i="'+i+'" data-t="impact" type="number" min="1" max="10" value="'+r.impact+'"></td>'+
      '<td><input class="num" data-i="'+i+'" data-t="ease" type="number" min="1" max="10" value="'+r.ease+'"></td>'+
      '<td><span class="pri">'+pri+'</span></td>'+
      '<td class="muted">'+esc(r.f.page||'')+'</td></tr>';
  }).join('');
  body.querySelectorAll('input.num').forEach(function(inp){
    inp.oninput=function(){
      var i=+inp.getAttribute('data-i'), t=inp.getAttribute('data-t');
      var v=Math.max(1,Math.min(10, +inp.value||5)); ROWS[i][t]=v; renderFindings();
    };
  });
}
var findWired=false;
function wireFindings(){
  if(findWired){ renderFindings(); return; } findWired=true;
  var host = el('findFilters');
  host.innerHTML = '<span class="whatif">Severity:</span>';
  ['Critical','High','Medium','Low'].forEach(function(s){
    var b=document.createElement('button'); b.className='chip'; b.textContent=s;
    b.onclick=function(){ if(fSev[s]) delete fSev[s]; else fSev[s]=1; b.classList.toggle('on'); renderFindings(); };
    host.appendChild(b);
  });
  var sp=document.createElement('span'); sp.className='whatif'; sp.textContent='Bucket:'; sp.style.marginLeft='8px'; host.appendChild(sp);
  BUCKETS.forEach(function(bk){
    var h = bk[1];
    var b=document.createElement('button'); b.className='chip'; b.textContent=h;
    b.onclick=function(){ if(fBkt[h]) delete fBkt[h]; else fBkt[h]=1; b.classList.toggle('on'); renderFindings(); };
    host.appendChild(b);
  });
  document.querySelectorAll('#panel___find th[data-k]').forEach(function(th){
    th.onclick=function(){ var k=th.getAttribute('data-k'); if(fSort.k===k) fSort.dir*=-1; else {fSort.k=k; fSort.dir=(k==='pri'||k==='sev'||k==='bucket')?-1:1;} renderFindings(); };
  });
  renderFindings();
}

/* ---- concentration panel (all verdicts/bands precomputed in Python; JSON
   keys stay spend/conv — labels read weight/outcome) ---- */
function fmtN(v){ return (typeof v==='number')? v.toLocaleString('en-US',{maximumFractionDigits:2}) : ''; }
function fmtPct(v){ return (v*100).toFixed(1)+'%'; }
function fmtPct2(v){ return (typeof v==='number' && isFinite(v))? (v*100).toFixed(2)+'%' : '—'; }
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
    '<div class="kpi"><div class="m">Weight HHI</div><div class="v">'+fmtN(dim.spend? dim.spend.hhi:null)+'</div><div class="b">'+bandPill(dim.spend)+'</div></div>'+
    '<div class="kpi"><div class="m">Outcome HHI</div><div class="v">'+fmtN(dim.conv? dim.conv.hhi:null)+'</div><div class="b">'+bandPill(dim.conv)+'</div></div>'+
    '<div class="kpi"><div class="m">Effective-N</div><div class="v">'+fmtN(dim.spend? dim.spend.eff_n:null)+'</div><div class="b">outcome: '+(dim.conv? fmtN(dim.conv.eff_n):'—')+'</div></div>'+
    '<div class="kpi"><div class="m">Gini</div><div class="v">'+fmtN(dim.spend? dim.spend.gini:null)+'</div><div class="b">outcome: '+(dim.conv? fmtN(dim.conv.gini):'—')+'</div></div>'+
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
    '<th>Entity</th><th>Weight</th><th>Outcome</th><th>Weight %</th><th>Outcome %</th><th>ABC</th>'+
    '</tr></thead><tbody>'+rows+'</tbody></table>'+
    '<div class="lz-legend"><span><span class="lz-key"></span>weight</span><span><span class="lz-key k-conv"></span>outcome</span></div></div></div>'+
    (dim.caveat? '<p class="muted" style="margin:12px 0 0;font-size:12.5px">'+esc(dim.caveat)+'</p>':'')+
    '</div>';
}
function concPanelHTML(){
  var C = M.concentration;
  var intro = '<div class="card pad"><h2 style="font-size:16px;margin-bottom:6px">Where weight and outcomes concentrate</h2>'+
    '<p class="muted" style="margin:0">HHI measures concentration on a 0–10,000 scale (merger-guideline bands: below 1,500 unconcentrated · 1,500–2,500 moderate · above 2,500 high). '+
    'Effective-N reads as "the weight behaves as if only N entities exist." Each dimension pairs a weight with its outcome — products: revenue vs orders · landing pages: sessions vs conversions · channels: sessions vs revenue (or conversions) — and the verdict reads the gap between the two. '+
    'Farther below the diagonal on the Lorenz curve = more concentrated.</p></div>';
  var notes = (C.notes||[]).map(function(n){ return '<p class="muted" style="margin:12px 0 0;font-size:12.5px">Note: '+esc(n)+'</p>'; }).join('');
  return intro + C.dimensions.map(concDimHTML).join('') + notes;
}

/* ---- CVR Signals panel (all statistics precomputed in Python; fractions
   rendered x100 here — display only, no math) ---- */
function zTxt(z){ return (z==null)? '—' : (+z).toFixed(2); }
function sigPill(r){
  if(r.z==null) return '<span class="pill p-NA">—</span>';
  return r.significant? '<span class="pill p-FLAG">significant</span>' : '<span class="pill p-NA">ns</span>';
}
function gatePill(g){
  return g? '<span class="pill p-NA">gated</span>' : '<span class="pill p-PASS">ok</span>';
}
function convCell(r){
  return '<span class="mono">'+fmtN(r.conversions)+'</span>'+(r.derived? '<span class="muted">*</span>':'');
}
function segTableHTML(label, rows){
  if(!rows || !rows.length) return '';
  var body = rows.map(function(r){
    return '<tr><td>'+esc(r.name)+'</td><td class="mono">'+fmtN(r.sessions)+'</td>'+
      '<td>'+convCell(r)+'</td><td class="mono">'+fmtPct2(r.cvr)+'</td>'+
      '<td class="mono">'+zTxt(r.z)+'</td><td>'+sigPill(r)+'</td></tr>';
  }).join('');
  return '<div class="card pad" style="margin-top:16px"><div class="section-head"><h2>'+esc(label)+'</h2></div>'+
    '<div class="wide"><table class="tbl"><thead><tr>'+
    '<th>Segment</th><th>Sessions</th><th>Conv</th><th>CVR</th><th>z</th><th>Signal</th>'+
    '</tr></thead><tbody>'+body+'</tbody></table></div></div>';
}
function cvrPanelHTML(){
  var V = M.cvr_signals, S = V.site||{}, PR = V.prior||{}, SG = V.segments||{};
  var ci = S.ci||[];
  var intro = '<div class="card pad"><h2 style="font-size:16px;margin-bottom:6px">CVR Signals — what is statistically real'+
    (V.window? ' <span class="muted" style="font-weight:400;font-size:13px">('+esc(V.window)+')</span>':'')+'</h2>'+
    '<p class="muted" style="margin:0">Wilson intervals bound the site CVR; two-proportion z-tests read each segment against its siblings '+
    '(|z| ≥ 1.96 = significant at 95%); pages below the n* significance gate cannot yet be called losers; '+
    'empirical-Bayes shrinkage pulls thin pages toward the site rate so small samples stop outranking real winners.</p>'+
    '<div class="kpis" style="margin-top:12px">'+
    '<div class="kpi"><div class="m">Site CVR</div><div class="v">'+fmtPct2(S.cvr)+'</div><div class="b">95% Wilson CI '+fmtPct2(ci[0])+' – '+fmtPct2(ci[1])+'</div></div>'+
    '<div class="kpi"><div class="m">Sessions</div><div class="v">'+fmtN(S.sessions)+'</div><div class="b">'+fmtN(S.conversions)+' conversions</div></div>'+
    '<div class="kpi"><div class="m">Significance gate</div><div class="v">n* = '+fmtN(V.min_sessions)+'</div><div class="b">sessions before a zero-conversion page is a confident loser</div></div>'+
    '<div class="kpi"><div class="m">Shrinkage prior</div><div class="v">k = '+fmtN(PR.k)+'</div><div class="b">'+esc(PR.basis||'')+'</div></div>'+
    '</div>'+
    (SG.headline_device_z? '<p class="muted" style="margin:12px 0 0;font-size:12.5px">Mobile vs desktop: z = '+
      zTxt(SG.headline_device_z.z)+' '+(SG.headline_device_z.significant?
      '<span class="pill p-FLAG">significant</span>':'<span class="pill p-NA">ns</span>')+
      ' (positive z = mobile converts higher).</p>':'')+
    '</div>';
  var segs = segTableHTML('Device', SG.device) +
             segTableHTML('Channels', SG.channels) +
             segTableHTML('New vs returning', SG.new_vs_returning);
  var pages = '';
  if((V.pages||[]).length){
    var U = V.pages_universe||{};
    var body = V.pages.map(function(p){
      return '<tr><td>'+esc(p.page)+'</td><td class="mono">'+fmtN(p.sessions)+'</td>'+
        '<td>'+convCell({conversions:p.conversions, derived:p.derived})+'</td>'+
        '<td class="mono">'+fmtPct2(p.cvr_raw)+'</td><td class="mono">'+fmtPct2(p.cvr_shrunk)+'</td>'+
        '<td class="mono">'+fmtPct2(p.wilson_lb)+'</td><td>'+gatePill(p.gated)+'</td></tr>';
    }).join('');
    pages = '<div class="card pad" style="margin-top:16px"><div class="section-head"><h2>Landing pages — raw vs shrunk vs Wilson lower bound</h2>'+
      '<span class="whatif">top '+fmtN(V.pages.length)+' by sessions of '+fmtN(U.n)+' pages · '+fmtN(U.gated_n)+' below the gate</span></div>'+
      '<div class="wide"><table class="tbl"><thead><tr>'+
      '<th>Page</th><th>Sessions</th><th>Conv</th><th>CVR raw</th><th>CVR shrunk</th><th>Wilson LB</th><th>Gate</th>'+
      '</tr></thead><tbody>'+body+'</tbody></table></div></div>';
  }
  var anyDerived = [].concat(SG.device||[], SG.channels||[], SG.new_vs_returning||[], V.pages||[])
    .some(function(r){ return r.derived; });
  var foot = anyDerived? '<p class="muted" style="margin:12px 0 0;font-size:12.5px">* conversion count derived from sessions × CVR (half-up) — the export shipped a rate without a count.</p>' : '';
  var notes = (V.notes||[]).map(function(n){ return '<p class="muted" style="margin:12px 0 0;font-size:12.5px">Note: '+esc(n)+'</p>'; }).join('');
  return intro + segs + pages + foot + notes;
}

/* ---- theme toggle support (host may stamp data-theme) ---- */
buildTabs(); buildPanels(); show('__ov');
})();
</script>
</body>
</html>"""
