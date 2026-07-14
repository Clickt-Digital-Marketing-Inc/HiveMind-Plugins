#!/usr/bin/env python3
"""Generic self-contained HTML explorer renderer (stdlib only).

render_html(model, spec) -> str  (one file: inline CSS+JS, data embedded as
JSON, ZERO external references — no http(s), <link>, src=, or CDN).

The engine owns the chrome and a generic render loop; the skill supplies the
compute kernel as a JS string so it matches the Python model exactly:

  spec['html_embed'](model) -> dict        # the JSON embedded in the page
  spec['html_controls']     -> [control]   # optional; sliders/number/multi
  spec['html_columns']      -> [column]    # the rows-table columns
  spec['html_kpis']         -> [kpi]       # {label, key} over the summary object
  spec['js_kernel']         -> str         # assigns classify(r,P) & summarize(rows,P)
  spec['js_extra']          -> str         # optional: assigns renderExtra(host,H)

A skill with no controls/kernel still gets a valid static explorer: KPIs read
straight off MODEL.summary and the table shows every row with a status badge.

Charts: when the spec declares `spec['charts']` (see render/charts.py), the page
additionally inlines the vendored Vega/Vega-Lite runtime and the generated chart
specs; the charts re-derive from the same recomputed rows as the table on every
control change. With no charts declared the output is byte-identical to the
chartless renderer (the chart hooks are stripped, not left empty).

control = {key,label,kind:"slider"|"number"|"multi", ...}
  slider: {min,max,step,sub}   number: {min,step}
  multi : {param_key, options:[[label,value],...]}  # param holds a list
column = {key,label,num?:bool,fmt?:"money"|"pct"|"int"|"num"|"block"|"status"|"text"}
kpi    = {label,key,cls?:"b1"|"b2"|""}
"""
from __future__ import annotations

import json

from . import charts as C
from . import model as M

# Chart hooks added to the template; stripped whole when no charts are declared
# so a chartless render stays byte-identical to the pre-chart renderer.
_VENDOR_LINE = "<script>/*__VENDOR__*/</script>\n"
_CHARTS_CARD_LINE = ('    <div class="card" id="chartsCard"><h2>Charts (live)</h2>'
                     '<div id="charts"></div></div>\n')
_CHARTS_JS_LINE = "/*__CHARTS__*/\n"

# Injected only when charts are declared. Runs at the end of the main script:
# builds one live view per spec (all reading the named dataset "rows"), then
# chains chart refresh onto the existing renderAll() recompute loop. The rows
# pushed to the charts pass through the same classify(r,P) as the table, so the
# live charts and the static SVGs agree at the default parameters.
_CHARTS_JS = """\
const chartViews = [];
function chartRows(){return (MODEL.rows||[]).map(r=>Object.assign({},r,classify(r,P)));}
(function(){const host=document.getElementById("charts");CHARTS.forEach((sp,i)=>{const box=el("div",{class:"chart",id:"chart_"+i});box.style.margin="0 0 14px";host.appendChild(box);chartViews.push(vlEmbed(box,sp));const s=box.querySelector("svg");if(s){s.style.overflow="visible";s.style.maxWidth="100%";}});})();
function renderCharts(){const rows=chartRows();chartViews.forEach(v=>v.change("rows",vega.changeset().remove(()=>true).insert(rows)).run());}
const __renderAllBase=renderAll;renderAll=function(){__renderAllBase();renderCharts();};
renderCharts();"""


def render_html(model: dict, spec: dict) -> str:
    M.require_model(model)
    M.require_spec(spec)
    embed = (spec.get("html_embed") or (lambda m: {
        "provenance": m["provenance"], "params": m["params"],
        "summary": m["summary"], "rows": m["rows"]}))(model)
    embed.setdefault("provenance", model["provenance"])
    embed.setdefault("params", model["params"])
    embed.setdefault("summary", model["summary"])

    spec_js = {
        "title": spec["title"],
        "controls": spec.get("html_controls", []),
        "columns": spec.get("html_columns", []),
        "kpis": spec.get("html_kpis", []),
        "window_labels": list(spec.get("window_labels", ("90-day window", "30-day window"))),
    }
    # Escape "</" so an embedded data string (e.g. a search term) can never close
    # the <script> element early — keeps the one-file document well-formed.
    model_json = json.dumps(embed, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    spec_json = json.dumps(spec_js, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    kernel = spec.get("js_kernel", "")
    extra = spec.get("js_extra", "")

    html = _TEMPLATE
    html = html.replace("/*__TITLE__*/", _esc_html(spec["title"]))
    html = html.replace("/*__MODEL__*/", "const MODEL = " + model_json + ";")
    html = html.replace("/*__SPEC__*/", "const SPEC = " + spec_json + ";")
    html = html.replace("/*__KERNEL__*/", kernel or "")
    html = html.replace("/*__EXTRA__*/", extra or "")
    if spec.get("charts"):
        html = html.replace("/*__VENDOR__*/", C.vendor_blob())
        html = html.replace("/*__CHARTS__*/",
                            "const CHARTS = " + C.charts_json(spec) + ";\n" + _CHARTS_JS)
    else:
        html = html.replace(_VENDOR_LINE, "")
        html = html.replace(_CHARTS_CARD_LINE, "")
        html = html.replace(_CHARTS_JS_LINE, "")
    return html


def _esc_html(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


# The page. The only dynamic insertions are the four /*__…__*/ markers above,
# all of which are inline script/text — nothing is fetched over the network.
_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>/*__TITLE__*/</title>
<style>
:root{--ink:#0B0F0E;--ink-2:#14191A;--slate:#5C6470;--mist:#E7EAED;--cloud:#F3F4F6;--white:#FFFFFF;--offwhite:#EEF1F3;--line:rgba(11,15,14,.10);--line-strong:rgba(11,15,14,.18);--surface:#DAE9E6;--tint:#97C4BD;--sage:#5BA89A;--teal:#1F7A82;--teal-deep:#0F4A52;--abyss:#07262B;--ember:#F86B3C;--accent:#1F7A82;--accent-soft:rgba(31,122,130,.12);--font:"Inter",system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;--mono:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace}
*{box-sizing:border-box}body{margin:0;font:14px/1.55 var(--font);background:var(--cloud);color:var(--ink);-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
input,select,button{accent-color:var(--teal)}
header{background:var(--abyss);color:var(--offwhite);padding:clamp(18px,3.5vw,30px) clamp(16px,4vw,34px)}
header h1{margin:0 0 8px;font-size:19px;font-weight:700;letter-spacing:-.02em;text-wrap:balance}
.prov{display:flex;flex-wrap:wrap;gap:5px 16px;font-family:var(--mono);font-size:11px;letter-spacing:.02em;color:var(--tint)}
.prov b{color:var(--offwhite);font-weight:500}
.wrap{width:100%;max-width:1240px;margin:0 auto;padding:18px clamp(14px,4vw,28px) 56px}
.grid{display:grid;grid-template-columns:minmax(0,1fr);gap:16px}
.grid.nocontrols{grid-template-columns:minmax(0,1fr)}
.grid>*{min-width:0}
@media(min-width:960px){.grid{grid-template-columns:minmax(300px,340px) minmax(0,1fr)}.grid.nocontrols{grid-template-columns:minmax(0,1fr)}}
.card{background:var(--white);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin-bottom:16px;box-shadow:0 1px 2px rgba(11,15,14,.04)}
.card h2{margin:0 0 14px;font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--slate);font-weight:500}
#controls{display:grid;grid-template-columns:repeat(auto-fit,minmax(188px,1fr));gap:14px 18px;align-items:start}
label.ctl{display:block;margin:0}
label.ctl .lab{display:flex;justify-content:space-between;align-items:center;gap:8px;font-weight:600;margin-bottom:6px;font-size:13px}
label.ctl .val{display:inline-block;min-width:2.5em;padding:1px 8px;border-radius:999px;background:var(--accent-soft);color:var(--teal-deep);font-weight:600;font-size:12px;font-variant-numeric:tabular-nums;text-align:center;line-height:1.5}
label.ctl .note{margin-top:6px}
input[type=range]{-webkit-appearance:none;appearance:none;width:100%;height:18px;margin:4px 0;background:transparent;cursor:pointer}
input[type=range]::-webkit-slider-runnable-track{height:6px;border-radius:999px;background:linear-gradient(90deg,var(--teal) 0 calc(var(--p,0)*1%),var(--mist) calc(var(--p,0)*1%) 100%)}
input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;width:16px;height:16px;margin-top:-5px;border-radius:50%;background:var(--white);border:2px solid var(--teal);box-shadow:0 1px 2px rgba(11,15,14,.3);transition:box-shadow .15s,transform .15s}
input[type=range]::-moz-range-track{height:6px;border-radius:999px;background:var(--mist)}
input[type=range]::-moz-range-progress{height:6px;border-radius:999px;background:var(--teal)}
input[type=range]::-moz-range-thumb{width:16px;height:16px;border:2px solid var(--teal);border-radius:50%;background:var(--white);box-shadow:0 1px 2px rgba(11,15,14,.3);transition:box-shadow .15s,transform .15s}
input[type=range]:hover::-webkit-slider-thumb{transform:scale(1.08)}input[type=range]:hover::-moz-range-thumb{transform:scale(1.08)}
input[type=range]:active::-webkit-slider-thumb{transform:scale(1.12)}input[type=range]:active::-moz-range-thumb{transform:scale(1.12)}
input[type=range]:focus{outline:none}
input[type=range]:focus-visible::-webkit-slider-thumb{box-shadow:0 0 0 4px rgba(31,122,130,.3)}
input[type=range]:focus-visible::-moz-range-thumb{box-shadow:0 0 0 4px rgba(31,122,130,.3)}
input[type=number],select{height:32px;padding:0 9px;border:1px solid var(--line-strong);border-radius:8px;background:var(--white);color:var(--ink);font:inherit;font-size:13px;line-height:32px;transition:border-color .15s,box-shadow .15s}
input[type=number]{width:88px;font-variant-numeric:tabular-nums}
input[type=number]:focus,select:focus{outline:none;border-color:var(--teal);box-shadow:0 0 0 3px rgba(31,122,130,.18)}
.mt{display:flex;flex-wrap:wrap;gap:8px;margin-top:6px}
.mt label{position:relative;margin:0;font-weight:500;cursor:pointer}
.mt label input{position:absolute;opacity:0;width:0;height:0}
.mt label span{display:inline-block;padding:4px 12px;border-radius:999px;border:1px solid var(--line-strong);background:var(--white);color:var(--slate);font-size:12.5px;line-height:1.4;user-select:none;transition:background .15s,border-color .15s,color .15s}
.mt label:hover span{border-color:var(--teal)}
.mt label input:checked+span{background:var(--surface);border-color:var(--teal);color:var(--teal-deep);font-weight:600}
.mt label input:focus-visible+span{box-shadow:0 0 0 3px rgba(31,122,130,.3)}
:focus-visible{outline:2px solid var(--teal);outline-offset:2px}
th:focus-visible{outline-offset:-2px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(132px,1fr));gap:12px}
.kpi{background:var(--cloud);border:1px solid var(--line);border-radius:10px;padding:11px 13px}
.kpi .n{font-size:24px;font-weight:700;font-variant-numeric:tabular-nums;color:var(--ink);line-height:1.1}
.kpi .l{display:block;margin-top:3px;font-family:var(--mono);font-size:10px;color:var(--slate);text-transform:uppercase;letter-spacing:.05em}
.kpi.b1 .n{color:var(--teal)}.kpi.b2 .n{color:#b0431e}
table{width:100%;border-collapse:collapse;font-size:12.5px;background:var(--white)}
th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{position:sticky;top:0;background:var(--cloud);cursor:pointer;user-select:none;font-family:var(--mono);font-size:10.5px;text-transform:uppercase;letter-spacing:.04em;color:var(--slate);font-weight:500;z-index:1}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
td:first-child:not(.num){white-space:normal;min-width:150px;max-width:300px}
.tablewrap{max-height:460px;overflow:auto;border:1px solid var(--line);border-radius:10px}
.badge{display:inline-block;padding:1px 8px;border-radius:999px;font-size:11px;font-weight:600;font-variant-numeric:tabular-nums}
.badge.b1{background:var(--surface);color:var(--teal-deep)}.badge.b2{background:rgba(248,107,60,.15);color:#9a3a1c}
.badge.nb{background:#f6ead2;color:#7a4a0b}.badge.no{background:var(--mist);color:#3c4350}
.badge.scale{background:rgba(91,168,154,.22);color:#0f5a4a}.badge.winner{background:var(--surface);color:var(--teal-deep)}
.badge.fix{background:#fbe9e7;color:#a3261f}.badge.hold{background:var(--mist);color:#3c4350}
tr.qual{background:var(--accent-soft)}
.sens td.cur{font-weight:700;color:var(--teal)}
.note{color:var(--slate);font-size:12px}
.logic{font-size:12.5px;color:var(--ink-2);background:var(--accent-soft);border:1px solid var(--line);padding:10px 12px;border-radius:8px;margin:8px 0}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px}
@media(prefers-reduced-motion:reduce){*{transition:none!important;scroll-behavior:auto!important}}
</style></head>
<body>
<header><h1 id="title"></h1><div class="prov" id="prov"></div></header>
<div class="wrap">
<div class="grid" id="grid">
  <div id="left">
    <div class="card" id="controlsCard"><h2>Parameters</h2><div id="controls"></div></div>
    <div class="card" id="multiCard" style="display:none"><h2>In scope</h2><div class="mt" id="multi"></div></div>
  </div>
  <div id="right">
    <div class="card"><h2>Results (live)</h2><div class="kpis" id="kpis"></div><div id="logic"></div></div>
    <div class="card" id="chartsCard"><h2>Charts (live)</h2><div id="charts"></div></div>
    <div id="extra"></div>
    <div class="card"><h2>Rows</h2>
      <div class="row"><label><input type="checkbox" id="qualonly"> qualifying only</label>
        <span class="note" id="tcount"></span></div>
      <div class="tablewrap"><table><thead id="thead"></thead><tbody id="tbody"></tbody></table></div>
    </div>
  </div>
</div></div>
<script>/*__VENDOR__*/</script>
<script>
/*__MODEL__*/
/*__SPEC__*/
const CUR = (MODEL.provenance && MODEL.provenance.currency) || "";
const P = Object.assign({}, MODEL.params || {});

// ---- shared helpers exposed to the skill kernel/extra (object H) ----
const money = v => (v==null?"":Number(v).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2}) + (CUR?(" "+CUR):""));
const pct = v => (v==null?"":(Number(v)*100).toFixed(2)+"%");
const fmtN = v => (v==null?"":Number(v).toLocaleString());
const esc = s => String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function el(tag,attrs,html){const e=document.createElement(tag); if(attrs)for(const k in attrs)e.setAttribute(k,attrs[k]); if(html!=null)e.innerHTML=html; return e;}
const H = {money,pct,fmtN,esc,el};

// ---- skill compute kernel (assigns classify & summarize); defaults if absent ----
let classify = (r,P) => ({block:"", status:r.status});
let summarize = (rows,P) => MODEL.summary || {};
let renderExtra = null;
/*__KERNEL__*/
/*__EXTRA__*/

const hasControls = (SPEC.controls && SPEC.controls.length) > 0;
let sortKey = null, sortDir = -1;

function renderProv(){
  const pr=MODEL.provenance||{};
  document.getElementById("title").textContent = SPEC.title;
  const wl=SPEC.window_labels||["90-day window","30-day window"];
  const bits=[`<span><b>${esc(pr.client_name||"")}</b> ${esc(pr.account_id||"")}</span>`,
    `<span>Currency <b>${esc(CUR||"—")}</b></span>`];
  if(pr.window_90d) bits.push(`<span>${esc(wl[0])} <b>${esc(pr.window_90d)}</b></span>`);
  if(pr.window_30d) bits.push(`<span>${esc(wl[1])} <b>${esc(pr.window_30d)}</b></span>`);
  bits.push(`<span>Generated <b>${esc(pr.generated||"—")}</b></span>`);
  bits.push(`<span>Rows <b>${(MODEL.rows||[]).length}</b></span>`);
  document.getElementById("prov").innerHTML = bits.join("");
}
function renderControls(){
  if(!hasControls){
    document.getElementById("controlsCard").style.display="none";
    document.getElementById("grid").classList.add("nocontrols");
    return;
  }
  const host=document.getElementById("controls"); host.innerHTML="";
  const setP=(r,c)=>{const span=(c.max-c.min)||1; r.style.setProperty('--p',(((+r.value)-c.min)/span)*100);};
  let multi=null;
  SPEC.controls.forEach(c=>{
    if(c.kind==="slider"){
      const w=el("label",{class:"ctl"});
      w.innerHTML=`<span class="lab">${esc(c.label)} <span class="val" id="v_${c.key}">${(+P[c.key]).toFixed(2)}</span></span>`;
      const r=el("input",{type:"range",min:c.min,max:c.max,step:c.step,value:P[c.key]});
      setP(r,c);
      r.oninput=()=>{P[c.key]=parseFloat(r.value); document.getElementById("v_"+c.key).textContent=(+P[c.key]).toFixed(2); setP(r,c); renderAll();};
      w.appendChild(r); if(c.sub) w.appendChild(el("div",{class:"note"},c.sub)); host.appendChild(w);
    } else if(c.kind==="number"){
      const w=el("label",{class:"ctl"}); w.innerHTML=`<span class="lab">${esc(c.label)}</span>`;
      const n=el("input",{type:"number",min:(c.min!=null?c.min:0),step:(c.step!=null?c.step:1),value:P[c.key]});
      n.oninput=()=>{P[c.key]=parseFloat(n.value||"0"); renderAll();};
      w.appendChild(n); host.appendChild(w);
    } else if(c.kind==="select"){
      const w=el("label",{class:"ctl"}); w.innerHTML=`<span class="lab">${esc(c.label)}</span>`;
      const sel=el("select");
      (c.options||[]).forEach(([lab,val])=>{const o=el("option"); o.value=String(val); o.textContent=lab;
        if(String(P[c.key])===String(val)) o.selected=true; sel.appendChild(o);});
      sel.onchange=()=>{const raw=sel.value, n=Number(raw);
        P[c.key]=(c.numeric!==false && raw!=="" && !isNaN(n))?n:raw; renderAll();};
      w.appendChild(sel); if(c.sub) w.appendChild(el("div",{class:"note"},c.sub)); host.appendChild(w);
    } else if(c.kind==="multi"){ multi=c; }
  });
  if(multi){
    document.getElementById("multiCard").style.display="";
    const mh=document.getElementById("multi"); mh.innerHTML="";
    multi.options.forEach(([label,val])=>{
      const w=el("label"); const cb=el("input",{type:"checkbox"});
      if((P[multi.param_key]||[]).includes(val)) cb.checked=true;
      cb.onchange=()=>{const s=new Set(P[multi.param_key]||[]); cb.checked?s.add(val):s.delete(val); P[multi.param_key]=[...s]; renderAll();};
      w.appendChild(cb); w.appendChild(el("span",null,esc(label))); mh.appendChild(w);
    });
  }
}
function renderKpis(){
  const S=summarize(MODEL.rows,P);
  document.getElementById("kpis").innerHTML = (SPEC.kpis||[]).map(k=>{
    let v=S[k.key]; if(k.money) v=money(v);
    return `<div class="kpi ${k.cls||""}"><div class="n">${v==null?"—":v}</div><div class="l">${esc(k.label)}</div></div>`;
  }).join("");
}
function fmtCell(r,col,c){
  const v=r[col.key];
  switch(col.fmt){
    case "money": return money(v);
    case "pct": return pct(v);
    case "int": return fmtN(v);
    case "num": return (v==null?"":Number(v).toFixed(2));
    case "status": return badge(r.status,c.block);
    case "block": return c.block?`<span class="badge ${blockClass(c.block)}">${esc(c.block)}</span>`:"";
    default: return esc(v);
  }
}
function blockClass(label){
  return {"Block 1":"b1","Block 2":"b2","Scale":"scale","Winner":"winner","Fix":"fix","Hold":"hold",
    "Kill":"fix","Raise":"scale","Rank-limited":"b2","Low budget":"hold","OK":"no",
    "Landing page":"fix","Ad relevance":"b2","Expected CTR":"hold","Critical":"fix","Other":"no",
    "Zombie":"fix","Surging":"scale","Declining":"nb"}[label]||"no";
}
function badge(status,block){
  if(block) return '<span class="badge '+blockClass(block)+'">'+esc(block)+'</span>';
  if(status&&status!=="scored"&&status!=="measured") return '<span class="badge nb">'+esc(status.replace("_"," "))+'</span>';
  return '<span class="badge no">'+esc(status||"")+'</span>';
}
function renderTable(){
  const cols=SPEC.columns||[];
  if(sortKey==null){ const mc=cols.find(c=>c.num); sortKey=mc?mc.key:(cols[0]&&cols[0].key); }
  const qualonly=document.getElementById("qualonly").checked;
  let rows=(MODEL.rows||[]).map(r=>({r,c:classify(r,P)}));
  if(qualonly) rows=rows.filter(x=>x.c.block);
  rows.sort((a,b)=>{
    let av=(sortKey==="block")?a.c.block:a.r[sortKey], bv=(sortKey==="block")?b.c.block:b.r[sortKey];
    if(typeof av==="string"||typeof bv==="string") return sortDir*String(av==null?"":av).localeCompare(String(bv==null?"":bv));
    return sortDir*((av||0)-(bv||0));
  });
  document.getElementById("thead").innerHTML="<tr>"+cols.map(c=>
    `<th class="${c.num?'num':''}" data-k="${c.key}">${esc(c.label)}${sortKey===c.key?(sortDir<0?' ▾':' ▴'):''}</th>`).join("")+"</tr>";
  document.getElementById("tbody").innerHTML=rows.map(({r,c})=>
    `<tr class="${c.block?'qual':''}">`+cols.map(col=>
      `<td class="${col.num?'num':''}">${fmtCell(r,col,c)}</td>`).join("")+"</tr>").join("");
  document.getElementById("tcount").textContent=`${rows.length} shown of ${(MODEL.rows||[]).length}`;
  document.querySelectorAll("#thead th").forEach(th=>th.onclick=()=>{
    const k=th.dataset.k; if(sortKey===k)sortDir*=-1; else{sortKey=k;sortDir=-1;} renderTable();});
}
function renderExtraHost(){
  const host=document.getElementById("extra"); if(!renderExtra){host.innerHTML="";return;} renderExtra(host,H);
}
function renderAll(){renderKpis();renderExtraHost();renderTable();}
renderProv();renderControls();
document.getElementById("qualonly").onchange=renderTable;
renderAll();
/*__CHARTS__*/
</script>
</body></html>
"""
