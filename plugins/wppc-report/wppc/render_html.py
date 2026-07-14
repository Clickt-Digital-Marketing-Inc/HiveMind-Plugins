"""Self-contained interactive HTML explorer for the wPPC report — the primary output.

Mirrors the google-ads-audit `audit_html.py` discipline: one `_TEMPLATE` raw string
with inline CSS/JS, the computed ``model`` embedded as JSON, the whole report rendered
client-side. Every number is READ from the model — the client re-derives nothing.

Self-containment (asserted by tests): the ONLY third-party bytes are two checksummed,
sentinel-wrapped regions —
  * the Vega/Vega-Lite chart runtime, from ``charts.vendor_blob()``, between
    ``/*__VENDOR_JS_BEGIN__*/ … /*__VENDOR_JS_END__*/``; and
  * GSAP, from ``gsap_blob()``, between ``/*__GSAP_JS_BEGIN__*/ … /*__GSAP_JS_END__*/``.
Outside those two regions there is NO ``http(s)://``, ``<link``, ``src=`` or ``cdn``.

Motion: all GSAP-referencing code lives in the animate-only ``/*__ANIM__*/`` block and
the GSAP library in the ``/*__GSAP__*/`` block. ``animate=False`` strips BOTH, so the
static report carries ZERO GSAP bytes (not even the token "gsap") while staying fully
functional — the base client sets every final state directly.

White-label: no vendor name, no logo — the report leads with the platform data.
"""

from __future__ import annotations

from pathlib import Path

from . import charts as _charts

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


def _chart_payload(model: dict) -> list:
    """Per-chart render payload for the client: id, title, built spec, and the
    chart's OWN rows (derived_weights from weights_table, the rest from segments).

    The specs are BUILT in Python (build_vl_spec) — the browser only draws them —
    so the live charts and the static md SVGs come from one declaration."""
    charts = model.get("charts", {})
    decls = charts.get("declarations", [])
    row_source = charts.get("row_source", {})
    out = []
    for decl in decls:
        rows_key = row_source.get(decl["id"], "segments")
        out.append({
            "id": decl["id"],
            "title": decl["title"],
            "spec": _charts.build_vl_spec(decl),
            "rows": model.get(rows_key, []),
        })
    return out


def render_html(model: dict, *, animate: bool = True) -> str:
    """Render the self-contained interactive report string from a computed model."""
    data = _charts.canonical_json(model)
    charts_js = _charts.canonical_json(_chart_payload(model))
    vendor = _charts.vendor_blob()
    title = _esc(model.get("provenance", {}).get("platform", "") or "wPPC Report")

    html = (_TEMPLATE
            .replace("/*__TITLE__*/", title)
            .replace("/*__VENDOR__*/", vendor)
            .replace("__CHARTS__", charts_js)
            .replace("__DATA__", data))

    if animate:
        html = html.replace("/*__GSAP__*/", gsap_blob()).replace("/*__ANIM__*/", _ANIM_JS)
    else:
        # Strip both animate-only <script> blocks so the static report carries
        # zero GSAP bytes (and not even the token "gsap").
        html = (html
                .replace("<script>/*__GSAP__*/</script>\n", "")
                .replace("<script>/*__ANIM__*/</script>\n", "")
                .replace("/*__GSAP__*/", "")
                .replace("/*__ANIM__*/", ""))
    return html


def build_html(model: dict, path, *, animate: bool = True) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_html(model, animate=animate), encoding="utf-8")


# ==========================================================================
# Animate-only JS (injected at /*__ANIM__*/ ONLY when animate=True). Every line
# references window.gsap, so it must never leak into a static (animate=False)
# render — which is why it lives here and not in the base client below.
# ==========================================================================
_ANIM_JS = r"""(function(){
  "use strict";
  var reduce = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion:reduce)').matches;
  var g = (typeof window !== 'undefined' && window.gsap && !reduce) ? window.gsap : null;
  if(!g) return;                       // library absent or reduced-motion: base render already final
  // Count-up the decision-lens numbers from 0 to their final (already-shown) value.
  document.querySelectorAll('.dl-num').forEach(function(node){
    var end = +node.getAttribute('data-v') || 0, o = {v:0};
    g.to(o,{v:end,duration:.8,ease:'power2.out',
      onUpdate:function(){ node.textContent = Math.round(o.v); },
      onComplete:function(){ node.textContent = end; }});
  });
  // Staggered reveal of the segment rows and chart cards.
  var rows = document.querySelectorAll('#segBody tr');
  if(rows.length) g.from(rows,{y:8,opacity:0,duration:.3,stagger:.015,ease:'power1.out'});
  var cards = document.querySelectorAll('.chart-card');
  if(cards.length) g.from(cards,{y:10,opacity:0,duration:.4,stagger:.06,ease:'power1.out'});
})();"""


# ==========================================================================
# The template. Markers: /*__TITLE__*/, __DATA__, __CHARTS__ (JSON), /*__VENDOR__*/,
# /*__GSAP__*/, /*__ANIM__*/.
# ==========================================================================
_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>wPPC Report — /*__TITLE__*/</title>
<style>
:root{
  --teal:#1F7A82; --teal-deep:#0F4A52; --abyss:#07262B; --teal-100:#97C4BD;
  --lime:#B4E01F; --lime-700:#3F5410; --lime-50:#EEF7D2;
  --purple:#897B9E; --ember:#F86B3C;
  --ink:#0B0F0E; --slate:#5C6470;
  --card:#FFFFFF; --bg:#F3F4F6; --line:rgba(11,15,14,.10); --line-2:rgba(11,15,14,.06);
  --font:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --mono:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  --accent:var(--teal);
  --pass:var(--lime-700); --pass-bg:var(--lime-50);
  --fail:#B23A16; --fail-bg:#FBE1D8;
  --na:var(--slate); --na-bg:#ECEEF0;
  --shadow:0 1px 2px rgba(11,15,14,.06),0 8px 24px rgba(11,15,14,.06);
}
@media (prefers-color-scheme:dark){:root{
  --ink:#EEF1F3; --card:#0F1A1C; --bg:#081113; --slate:#9AA4AE;
  --line:rgba(238,241,243,.12); --line-2:rgba(238,241,243,.07);
  --pass:#B4E01F; --pass-bg:rgba(180,224,31,.12);
  --fail:#FF8A64; --fail-bg:rgba(248,107,60,.14);
  --na:#9AA4AE; --na-bg:rgba(154,164,174,.14);
  --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.4);
}}
:root[data-theme="dark"]{
  --ink:#EEF1F3; --card:#0F1A1C; --bg:#081113; --slate:#9AA4AE;
  --line:rgba(238,241,243,.12); --line-2:rgba(238,241,243,.07);
  --pass:#B4E01F; --pass-bg:rgba(180,224,31,.12);
  --fail:#FF8A64; --fail-bg:rgba(248,107,60,.14); --na:#9AA4AE; --na-bg:rgba(154,164,174,.14);
}
:root[data-theme="light"]{
  --ink:#0B0F0E; --card:#FFFFFF; --bg:#F3F4F6; --slate:#5C6470;
  --line:rgba(11,15,14,.10); --line-2:rgba(11,15,14,.06);
  --pass:var(--lime-700); --pass-bg:var(--lime-50);
  --fail:#B23A16; --fail-bg:#FBE1D8; --na:var(--slate); --na-bg:#ECEEF0;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--font);
  font-size:15px;line-height:1.5;-webkit-font-smoothing:antialiased}
.wrap{max-width:1120px;margin:0 auto;padding:0 20px 64px}
h1,h2,h3{margin:0;font-weight:650;letter-spacing:-.01em}
.mono{font-family:var(--mono);font-variant-numeric:tabular-nums}
header{background:linear-gradient(160deg,var(--abyss),var(--teal-deep));color:#EEF1F3;
  border-radius:0 0 20px 20px;box-shadow:var(--shadow)}
.hd{max-width:1120px;margin:0 auto;padding:34px 20px 30px}
.eyebrow{text-transform:uppercase;letter-spacing:.16em;font-size:11px;font-weight:600;
  color:var(--teal-100);margin-bottom:10px}
.client{font-size:30px;font-weight:680;line-height:1.15;text-transform:capitalize}
.meta{margin-top:12px;display:flex;flex-wrap:wrap;gap:6px 18px;font-size:13px;color:#C7D6D4}
.meta b{color:#EEF1F3;font-weight:600}
.grid{display:grid;gap:16px;margin-top:22px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow)}
.pad{padding:20px 22px}
h2.sec{font-size:18px;margin:26px 0 12px}
/* decision lens */
.lens{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
@media (max-width:640px){.lens{grid-template-columns:1fr}}
.lens .cell{border:1px solid var(--line);border-radius:14px;padding:18px 20px;background:var(--card)}
.lens .lab{font-size:12px;text-transform:uppercase;letter-spacing:.12em;color:var(--slate);font-weight:600}
.lens .dl-num{font-size:40px;font-weight:720;font-family:var(--mono);line-height:1.1;margin-top:4px}
.lens .cell.scale{border-top:4px solid var(--pass)}
.lens .cell.cut{border-top:4px solid var(--fail)}
.lens .cell.watch{border-top:4px solid var(--slate)}
.lens .sub{font-size:12px;color:var(--slate);margin-top:2px}
/* controls */
.controls{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:2px 0 14px}
.seg{display:inline-flex;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
.seg button{appearance:none;border:0;background:transparent;color:var(--slate);font:inherit;
  font-weight:600;font-size:12.5px;padding:7px 12px;cursor:pointer}
.seg button.on{background:var(--accent);color:#fff}
label.fld{font-size:12.5px;color:var(--slate);display:inline-flex;align-items:center;gap:6px}
input.txt{font:inherit;padding:6px 10px;border:1px solid var(--line);border-radius:8px;
  background:var(--card);color:var(--ink);min-width:160px}
input.txt:focus{outline:2px solid var(--accent);outline-offset:1px}
.count{font-size:12.5px;color:var(--slate);margin-left:auto}
/* tables */
.wide{overflow-x:auto;border-radius:14px}
.tbl{width:100%;border-collapse:collapse;font-size:13.5px}
.tbl th{text-align:right;font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;
  color:var(--slate);font-weight:650;padding:9px 10px;border-bottom:1px solid var(--line);
  position:sticky;top:0;background:var(--card);white-space:nowrap}
.tbl th:first-child,.tbl td:first-child{text-align:left}
.tbl.sortable th[data-k]{cursor:pointer;user-select:none}
.tbl.sortable th[data-k]:hover{color:var(--ink)}
.tbl th .ar{opacity:.5;font-size:10px;margin-left:3px}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--line-2);text-align:right;
  font-family:var(--mono);font-variant-numeric:tabular-nums;white-space:nowrap}
.tbl td.seg{text-align:left;font-family:var(--font);font-weight:600}
.tbl tr:last-child td{border-bottom:0}
.pill{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:650;line-height:1.7}
.p-scale{background:var(--pass-bg);color:var(--pass)}
.p-cut{background:var(--fail-bg);color:var(--fail)}
.p-watch{background:var(--na-bg);color:var(--na)}
.p-Falling{background:var(--fail-bg);color:var(--fail)}
.stab-Y{color:var(--pass);font-weight:700}
.stab-N{color:var(--slate)}
.cell-mar-pos{background:var(--pass-bg)}
.cell-mar-neg{background:var(--fail-bg)}
.muted{color:var(--slate)}
.empty{color:var(--slate);padding:20px;text-align:center;font-family:var(--font)}
/* weights + self-check */
.two{display:grid;grid-template-columns:1fr 300px;gap:16px}
@media (max-width:820px){.two{grid-template-columns:1fr}}
.sc{border-radius:12px;padding:14px 16px;font-size:13.5px;font-weight:600}
.sc.pass{background:var(--pass-bg);color:var(--pass)}
.sc.fail{background:var(--fail-bg);color:var(--fail)}
/* charts */
.charts{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media (max-width:820px){.charts{grid-template-columns:1fr}}
.chart-card{background:var(--card);border:1px solid var(--line);border-radius:14px;
  box-shadow:var(--shadow);padding:14px 16px;overflow-x:auto}
.chart-card h3{font-size:13.5px;margin-bottom:8px}
.chart-host{min-height:60px}
footer{margin-top:34px;padding-top:16px;border-top:1px solid var(--line);color:var(--slate);
  font-size:12px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px}
@media (prefers-reduced-motion:reduce){*{transition:none !important;animation:none !important}}
</style>
</head>
<body>
<header>
  <div class="hd">
    <div class="eyebrow">Weighted Profit-Per-Click — segment report</div>
    <div class="client" id="platform"></div>
    <div class="meta" id="metaLine"></div>
  </div>
</header>
<main class="wrap">

  <h2 class="sec">Decision lens</h2>
  <div class="lens" id="lens"></div>

  <h2 class="sec">Segments</h2>
  <div class="controls" id="segControls"></div>
  <div class="card wide">
    <table class="tbl sortable" id="segTable">
      <thead><tr id="segHead"></tr></thead>
      <tbody id="segBody"></tbody>
    </table>
  </div>

  <h2 class="sec">Derived weights &amp; self-check</h2>
  <div class="two">
    <div class="card wide"><table class="tbl" id="wTable">
      <thead><tr><th style="text-align:left">Funnel state</th><th>P(purchase|S)</th><th>PE(S)</th><th>w(S) incremental</th></tr></thead>
      <tbody id="wBody"></tbody>
    </table></div>
    <div class="card pad"><div id="selfCheck"></div></div>
  </div>

  <h2 class="sec">Decay</h2>
  <div id="decay"></div>

  <h2 class="sec">Charts</h2>
  <div class="charts" id="charts"></div>

  <footer>
    <span id="footL"></span>
    <span>Self-contained · recomputes in your browser</span>
  </footer>
</main>

<script id="data" type="application/json">__DATA__</script>
<script id="charts-data" type="application/json">__CHARTS__</script>
<script>/*__VENDOR__*/</script>
<script>/*__GSAP__*/</script>
<script>
(function(){
"use strict";
var M = JSON.parse(document.getElementById('data').textContent);
var CH = JSON.parse(document.getElementById('charts-data').textContent);
function el(id){ return document.getElementById(id); }
function esc(s){ s=(s==null?'':''+s); return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function fmt(v,d){ return (v==null)? '—' : Number(v).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d}); }
function fmt0(v){ return (v==null)? '—' : Number(v).toLocaleString('en-US',{maximumFractionDigits:0}); }

/* ---- header ---- */
var P = M.provenance, MD = M.metadata;
el('platform').textContent = P.platform || 'wPPC Report';
(function(){
  var bits = [];
  bits.push('<span>Segments <b>'+esc(P.n_segments)+'</b></span>');
  bits.push('<span>Stabilized <b>'+esc(P.n_stabilized)+'</b></span>');
  bits.push('<span>Baseline wPPC <b>'+fmt(MD.baseline,2)+'</b></span>');
  bits.push('<span>Replacement <b>'+fmt(MD.replacement,2)+'</b></span>');
  bits.push('<span>k <b>'+fmt(MD.k,1)+'</b> ('+esc(P.k_source)+')</span>');
  if(P.generated) bits.push('<span>Generated <b>'+esc(P.generated)+'</b></span>');
  el('metaLine').innerHTML = bits.join('');
  el('footL').textContent = (P.n_segments||0)+' segments · decay '+(P.decay_status||'not-run')+
    ' · incrementality '+(P.incrementality_status||'not-provided')+' · generated '+(P.generated||'');
})();

/* ---- decision lens ---- */
(function(){
  var DL = M.decision_lens;
  var cells = [
    {k:'scale', lab:'Scale', v:DL.scale, sub:'stabilized · MAR &gt; 0'},
    {k:'cut',   lab:'Cut',   v:DL.cut,   sub:'stabilized · MAR &lt; 0'},
    {k:'watch', lab:'Watch', v:DL.watch, sub:'not stabilized, or MAR = 0'}
  ];
  el('lens').innerHTML = cells.map(function(c){
    return '<div class="cell '+c.k+'"><div class="lab">'+c.lab+'</div>'+
      '<div class="dl-num" data-v="'+c.v+'">'+c.v+'</div><div class="sub">'+c.sub+'</div></div>';
  }).join('');
})();

/* ---- conditional cell coloring (matches the xlsx) ---- */
var RED=[248,105,107], YEL=[255,235,132], GRN=[99,190,123];
function _h(c){ return ('0'+c.toString(16)).slice(-2); }
function _mix(a,b,t){ return '#'+_h(Math.round(a[0]+(b[0]-a[0])*t))+_h(Math.round(a[1]+(b[1]-a[1])*t))+_h(Math.round(a[2]+(b[2]-a[2])*t)); }
function plusColor(v){                 // wPPC+ scale 60->100->160 red->yellow->green
  if(v==null) return '';
  if(v<=60) return _mix(RED,RED,0);
  if(v>=160) return _mix(GRN,GRN,0);
  if(v<100) return _mix(RED,YEL,(v-60)/40);
  return _mix(YEL,GRN,(v-100)/60);
}

/* ---- segments table: sortable + filterable ---- */
var COLS = [
  {k:'segment_id', lab:'Segment', t:'s'},
  {k:'clicks', lab:'Clicks', t:'i'},
  {k:'conversions', lab:'Conv', t:'i'},
  {k:'wPPC', lab:'wPPC', t:'n', d:2},
  {k:'wPPC+', lab:'wPPC+', t:'plus'},
  {k:'wPPC_shrunk', lab:'Shrunk', t:'n', d:2},
  {k:'MAR', lab:'MAR', t:'mar', d:2},
  {k:'stabilized', lab:'Stab', t:'stab'},
  {k:'closing_ratio', lab:'Closing', t:'n', d:2},
  {k:'decision', lab:'Decision', t:'dec'}
];
var fStab='', fMar='', fBand='', fSearch='';
var sort={k:'MAR', dir:-1};

function segFilter(s){
  if(fStab && s.stabilized !== fStab) return false;
  if(fMar==='pos' && !(s.MAR>=0)) return false;
  if(fMar==='neg' && !(s.MAR<0)) return false;
  if(fBand==='lt80' && !(s['wPPC+']<80)) return false;
  if(fBand==='mid' && !(s['wPPC+']>=80 && s['wPPC+']<=120)) return false;
  if(fBand==='gt120' && !(s['wPPC+']>120)) return false;
  if(fSearch && (''+s.segment_id).toLowerCase().indexOf(fSearch)<0) return false;
  return true;
}
function segRows(){
  var rows = M.segments.filter(segFilter);
  rows.sort(function(a,b){
    var va=a[sort.k], vb=b[sort.k];
    if(typeof va==='string' || typeof vb==='string'){ return sort.dir*(''+va).localeCompare(''+vb); }
    return sort.dir*((va||0)-(vb||0));
  });
  return rows;
}
function buildHead(){
  el('segHead').innerHTML = COLS.map(function(c){
    var ar = sort.k===c.k ? '<span class="ar">'+(sort.dir<0?'▼':'▲')+'</span>' : '';
    return '<th data-k="'+c.k+'">'+esc(c.lab)+ar+'</th>';
  }).join('');
  el('segHead').querySelectorAll('th[data-k]').forEach(function(th){
    th.onclick=function(){
      var k=th.getAttribute('data-k');
      if(sort.k===k) sort.dir*=-1;
      else { sort.k=k; sort.dir=(k==='segment_id'||k==='stabilized'||k==='decision')?1:-1; }
      buildHead(); renderSeg();
    };
  });
}
function cell(s,c){
  if(c.t==='s') return '<td class="seg">'+esc(s.segment_id)+'</td>';
  if(c.t==='i') return '<td>'+fmt0(s[c.k])+'</td>';
  if(c.t==='n') return '<td>'+fmt(s[c.k],c.d)+'</td>';
  if(c.t==='plus'){ var col=plusColor(s['wPPC+']);
    return '<td style="background:'+col+';color:#0B0F0E">'+fmt0(s['wPPC+'])+'</td>'; }
  if(c.t==='mar'){ var cls = s.MAR<0?'cell-mar-neg':'cell-mar-pos';
    return '<td class="'+cls+'">'+fmt(s.MAR,c.d)+'</td>'; }
  if(c.t==='stab') return '<td class="stab-'+esc(s.stabilized)+'">'+esc(s.stabilized)+'</td>';
  if(c.t==='dec') return '<td><span class="pill p-'+esc(s.decision.toLowerCase())+'">'+esc(s.decision)+'</span></td>';
  return '<td>'+esc(s[c.k])+'</td>';
}
function renderSeg(){
  var rows = segRows();
  var body = el('segBody');
  if(!rows.length){ body.innerHTML = '<tr><td class="empty" colspan="'+COLS.length+'">No segments match the current filter.</td></tr>'; }
  else { body.innerHTML = rows.map(function(s){ return '<tr>'+COLS.map(function(c){return cell(s,c);}).join('')+'</tr>'; }).join(''); }
  var cnt = el('segCount'); if(cnt) cnt.textContent = rows.length+' of '+M.segments.length+' segments';
}
function segButtons(host, label, opts, get, set){
  var wrap = document.createElement('div'); wrap.className='seg';
  opts.forEach(function(o){
    var b=document.createElement('button'); b.textContent=o.lab; if(get()===o.v) b.className='on';
    b.onclick=function(){ set(o.v); wrap.querySelectorAll('button').forEach(function(x){x.classList.remove('on');}); b.classList.add('on'); renderSeg(); };
    wrap.appendChild(b);
  });
  var lab=document.createElement('span'); lab.className='fld'; lab.textContent=label;
  host.appendChild(lab); host.appendChild(wrap);
}
(function(){
  var host = el('segControls');
  segButtons(host,'Stabilized',[{lab:'All',v:''},{lab:'Y',v:'Y'},{lab:'N',v:'N'}],function(){return fStab;},function(v){fStab=v;});
  segButtons(host,'MAR',[{lab:'All',v:''},{lab:'≥0',v:'pos'},{lab:'<0',v:'neg'}],function(){return fMar;},function(v){fMar=v;});
  segButtons(host,'wPPC+ band',[{lab:'All',v:''},{lab:'<80',v:'lt80'},{lab:'80–120',v:'mid'},{lab:'>120',v:'gt120'}],function(){return fBand;},function(v){fBand=v;});
  var sl=document.createElement('label'); sl.className='fld'; sl.innerHTML='Search ';
  var inp=document.createElement('input'); inp.className='txt'; inp.type='text'; inp.placeholder='segment id…';
  inp.oninput=function(){ fSearch=(inp.value||'').toLowerCase().trim(); renderSeg(); };
  sl.appendChild(inp); host.appendChild(sl);
  var cnt=document.createElement('span'); cnt.className='count'; cnt.id='segCount'; host.appendChild(cnt);
})();
buildHead(); renderSeg();

/* ---- derived weights + self-check ---- */
(function(){
  el('wBody').innerHTML = M.weights_table.map(function(w){
    return '<tr><td class="seg">'+esc(w.state)+'</td><td>'+fmt(w.p,6)+'</td><td>'+fmt(w.pe,4)+'</td><td>'+fmt(w.w,4)+'</td></tr>';
  }).join('');
  var S = M.self_check;
  el('selfCheck').innerHTML =
    '<div class="sc '+(S.pass?'pass':'fail')+'">Self-check '+(S.pass?'PASS':'FAIL')+'</div>'+
    '<p class="muted" style="margin:12px 0 0;font-size:12.5px">Telescoped Σ w(click..purchase) = <b>'+fmt(S.telescope_sum,4)+
    '</b> vs CM3_order <b>'+fmt(S.cm3_order,4)+'</b>. The incremental weights telescope to the terminal order value — if they did not, the run would have refused to score.</p>';
})();

/* ---- decay (parallel data; never blended into wPPC+/MAR) ---- */
(function(){
  var D = M.decay || {status:'not-run', rows:[]};
  if(!D.rows || !D.rows.length){
    el('decay').innerHTML = '<div class="card pad muted">decay: '+esc(D.status||'not-run')+' — supply a prior-period export to compute two-period wPPC+ movement.</div>';
    return;
  }
  var head = '<thead><tr><th style="text-align:left">Segment</th><th>wPPC+ prior</th><th>wPPC+ delta</th><th>delta %</th><th>Trend</th></tr></thead>';
  var body = D.rows.map(function(d){
    var pct = (d.delta_pct==null)? '—' : (d.delta_pct*100).toFixed(1)+'%';
    var trendCls = (d.trend==='Falling')? ' class="p-Falling pill"' : '';
    var trend = d.trend? '<span'+trendCls+'>'+esc(d.trend)+'</span>' : '—';
    return '<tr><td class="seg">'+esc(d.segment_id)+'</td><td>'+fmt0(d['wPPC+_prior'])+'</td><td>'+
      (d['wPPC+_delta']==null?'—':(d['wPPC+_delta']>0?'+':'')+fmt0(d['wPPC+_delta']))+'</td><td>'+pct+'</td><td style="text-align:right">'+trend+'</td></tr>';
  }).join('');
  el('decay').innerHTML = '<div class="card wide"><table class="tbl">'+head+'<tbody>'+body+'</tbody></table></div>';
})();

/* ---- charts: draw each embedded spec against its own embedded rows ---- */
(function(){
  var host = el('charts');
  host.innerHTML = CH.map(function(c){
    return '<div class="chart-card"><h3>'+esc(c.title)+'</h3><div class="chart-host" id="chart_'+esc(c.id)+'"></div></div>';
  }).join('');
  CH.forEach(function(c){
    var node = el('chart_'+c.id); if(!node) return;
    try{
      var spec = c.spec; spec.data = {values: c.rows};
      vlEmbed(node, spec);
    }catch(e){ node.innerHTML = '<div class="muted">chart unavailable</div>'; }
  });
})();
})();
</script>
<script>/*__ANIM__*/</script>
</body>
</html>"""
