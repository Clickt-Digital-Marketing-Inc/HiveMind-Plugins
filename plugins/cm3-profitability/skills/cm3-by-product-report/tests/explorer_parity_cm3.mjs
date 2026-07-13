// explorer_parity_cm3.mjs — JS<->Python parity for the cm3 HTML explorer rollups.
//
// Usage:  node explorer_parity_cm3.mjs <explorer.html> <expected.json>
//
// Loads the (chartless) explorer under jsdom and asserts the live JS kernel
// rollupData(dim) deep-equals the Python compute() rollups at the report
// defaults and at each cumulative tuned scenario:
//   - By Campaign / By Vendor: a flat {rows:[...]} bucket list;
//   - By Category / By Product Type: {levels:[{level, rows:[...]}]} (L1..L5).
// Every bucket is compared on name + order + all numeric fields (n, impr,
// clicks, conv, cost, rev, roas, cm3, cm3%, share, and vendor COGS%) to 1e-6.
//
// Dev-only: requires `npm install` here (jsdom). The plugin never runs this.
import fs from "node:fs";
import { JSDOM, VirtualConsole } from "jsdom";

const [, , htmlPath, expectedPath] = process.argv;
if (!htmlPath || !expectedPath) {
  console.error("usage: node explorer_parity_cm3.mjs <explorer.html> <expected.json>");
  process.exit(2);
}
const html = fs.readFileSync(htmlPath, "utf8");
const expected = JSON.parse(fs.readFileSync(expectedPath, "utf8"));

const jsErrs = [];
const vc = new VirtualConsole();
vc.on("jsdomError", (e) => jsErrs.push(String(e && (e.message || e))));
const dom = new JSDOM(html, { runScripts: "dangerously", virtualConsole: vc });
const { window } = dom;

let fail = 0;
const assert = (c, m) => { if (!c) { fail++; console.log("  FAIL: " + m); } };
const NUM = ["n", "impr", "clicks", "conv", "cost", "rev", "roas", "cm3", "cm3_pct", "share", "vcogs"];
const eqNum = (a, b) => {
  if (a == null && b == null) return true;
  if (a == null || b == null) return false;
  return Math.abs(a - b) < 1e-6;
};
const evalJSON = (expr) => JSON.parse(window.eval("JSON.stringify(" + expr + ")"));

assert(window.eval("typeof rollupData") === "function", "rollupData kernel present");
assert(jsErrs.length === 0, "no jsdom errors on load: " + jsErrs.slice(0, 2).join(" | "));

function cmpRows(label, jsRows, pyRows) {
  assert(jsRows.length === pyRows.length, `${label}: row count JS ${jsRows.length} == PY ${pyRows.length}`);
  const n = Math.min(jsRows.length, pyRows.length);
  for (let i = 0; i < n; i++) {
    const j = jsRows[i], p = pyRows[i];
    assert(String(j.name) === String(p.name), `${label}[${i}]: name JS "${j.name}" == PY "${p.name}"`);
    for (const k of NUM) {
      if (!(k in p)) continue;
      assert(eqNum(j[k], p[k]), `${label}[${i}].${k}: JS ${j[k]} == PY ${p[k]}`);
    }
  }
}
function cmpDim(scenario, dim, py) {
  const js = evalJSON(`rollupData("${dim}")`);
  if (py.rows) {
    cmpRows(`${scenario}/${dim}`, js.rows, py.rows);
  } else {
    assert(js.levels.length === py.levels.length,
      `${scenario}/${dim}: level count JS ${js.levels.length} == PY ${py.levels.length}`);
    const n = Math.min(js.levels.length, py.levels.length);
    for (let i = 0; i < n; i++) {
      assert(js.levels[i].level === py.levels[i].level, `${scenario}/${dim}: level[${i}] number`);
      cmpRows(`${scenario}/${dim}/L${py.levels[i].level}`, js.levels[i].rows, py.levels[i].rows);
    }
  }
}

// Default parameters.
for (const dim of ["camp", "ven", "cat", "pt"]) cmpDim("default", dim, expected.default[dim]);

// Cumulative tuned scenarios — mutate P directly (JS units are fractions) and re-check.
for (const st of expected.steps) {
  window.eval(`P.${st.key} = ${st.value}`);
  for (const dim of ["camp", "ven", "cat", "pt"]) cmpDim(`step:${st.key}=${st.value}`, dim, st.rollups[dim]);
}

if (fail) { console.log(`FAIL — ${fail} parity mismatch(es)`); process.exit(1); }
console.log("OK — explorer rollups: JS rollupData == Python compute() at default + "
  + expected.steps.length + " tuned scenarios (camp/ven/cat/pt · names+order+numerics to 1e-6).");
