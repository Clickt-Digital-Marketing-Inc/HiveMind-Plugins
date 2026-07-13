// tuner_parity_cm3.mjs — JS<->Python parity for the cm3-by-product in-Claude tuner.
//
// Usage:  node tuner_parity_cm3.mjs <widget.html> <expected.json>
//
// Loads the emitted show_widget fragment under jsdom and asserts:
//   1. the live JS kernel summarize(MODEL.rows,P) at default params deep-equals both
//      the embedded Python summary (MODEL.summary) and expected.default;
//   2. each cumulative tune step (located by key via SPEC.controls order) re-tunes P,
//      the slider readout (gv_<key>) reads cleanly, the JS summary then equals the
//      Python-computed expected summary, and at least one KPI actually moved;
//   3. the Save button emits a sendPrompt carrying the tuned P, targeting
//      raw/reports/<filename_stem>.md, with "do not propose_note";
//   4. the Excel/HTML/PowerPoint export buttons each emit an artifacts/ rebuild prompt.
//
// Dev-only: requires `npm install` here (jsdom). The plugin never runs this.
import fs from "node:fs";
import { JSDOM } from "jsdom";

const [, , htmlPath, expectedPath] = process.argv;
if (!htmlPath || !expectedPath) {
  console.error("usage: node tuner_parity_cm3.mjs <widget.html> <expected.json>");
  process.exit(2);
}
const fragment = fs.readFileSync(htmlPath, "utf8");
const expected = JSON.parse(fs.readFileSync(expectedPath, "utf8"));

let lastPrompt = null;
const dom = new JSDOM(`<!DOCTYPE html><html><body>${fragment}</body></html>`, {
  runScripts: "dangerously",
  beforeParse(window) { window.sendPrompt = (t) => { lastPrompt = t; }; },
});
const { window } = dom;
const doc = window.document;

let fail = 0;
const assert = (cond, msg) => { if (!cond) { fail++; console.log("  FAIL: " + msg); } };
const isNum = (v) => typeof v === "number";
const eqVal = (a, b) => (isNum(a) && isNum(b) ? Math.abs(a - b) < 1e-6 : String(a) === String(b));
const evalJSON = (expr) => JSON.parse(window.eval("JSON.stringify(" + expr + ")"));

const kpiKeys = expected.kpi_keys || [];

// --- kernel present ---
assert(window.eval("typeof summarize") === "function", "JS kernel summarize present");
assert(window.eval("typeof classify") === "function", "JS kernel classify present");

// --- default parity: JS == embedded Python == expected.default ---
const embedded = evalJSON("MODEL.summary");
let jsCur = evalJSON("summarize(MODEL.rows, P)");
for (const k of kpiKeys) {
  assert(eqVal(jsCur[k], embedded[k]),
    `default JS[${k}]=${jsCur[k]} == embedded Python[${k}]=${embedded[k]}`);
  assert(eqVal(jsCur[k], expected.default[k]),
    `default JS[${k}]=${jsCur[k]} == expected.default[${k}]=${expected.default[k]}`);
}

// --- locate controls by key (via SPEC.controls order) and tune them cumulatively ---
const ctlKeys = evalJSON("(SPEC.controls||[]).map(c=>c.key)");
const FRAC = evalJSON("FRAC");   // keys whose readout is a percentage
const pctReadout = (v) => { const n = Math.round(v * 1000) / 10; return (Number.isInteger(n) ? String(n) : n.toFixed(1)) + "%"; };

for (const step of (expected.steps || [])) {
  const idx = ctlKeys.indexOf(step.key);
  assert(idx >= 0, `control '${step.key}' present in SPEC.controls`);
  const ctlDiv = doc.querySelectorAll("#gx-controls .gx-ctl")[idx];
  const input = ctlDiv && ctlDiv.querySelector("input, select");
  assert(!!input, `rendered input for control '${step.key}'`);
  if (input) {
    input.value = String(step.value);
    input.dispatchEvent(new window.Event(input.tagName === "SELECT" ? "change" : "input", { bubbles: true }));
  }
  // readout parity for percentage controls — guards a toFixed/rounding regression.
  const gv = doc.getElementById("gv_" + step.key);
  if (gv && (step.key in FRAC)) {
    assert(gv.textContent === pctReadout(step.value),
      `readout gv_${step.key}='${gv.textContent}' == '${pctReadout(step.value)}'`);
  }
  const jsPrev = jsCur;
  jsCur = evalJSON("summarize(MODEL.rows, P)");
  let moved = false;
  for (const k of kpiKeys) {
    assert(eqVal(jsCur[k], step.summary[k]),
      `after ${step.key}=${step.value} JS[${k}]=${jsCur[k]} == expected[${k}]=${step.summary[k]}`);
    if (!eqVal(jsCur[k], jsPrev[k])) moved = true;
  }
  assert(moved, `tuning '${step.key}'=${step.value} changed at least one KPI (non-vacuous)`);
}

// --- Save -> direct-write prompt ---
doc.getElementById("gx-save").dispatchEvent(new window.Event("click", { bubbles: true }));
assert(lastPrompt !== null, "Save fired sendPrompt");
const p = lastPrompt || "";
assert(p.includes("raw/reports/"), "Save prompt targets raw/reports/");
assert(p.includes(expected.filename_stem + ".md"), `Save prompt names ${expected.filename_stem}.md`);
assert(/do not propose_note/i.test(p), "Save prompt says do not propose_note");
const liveP = evalJSON("P");
assert(p.includes(JSON.stringify(liveP)), "Save prompt carries the tuned params JSON");

// --- Export buttons -> artifacts/ rebuilds ---
for (const [id, fmt] of [["gx-xlsx", "xlsx"], ["gx-html", "html"], ["gx-pptx", "pptx"]]) {
  lastPrompt = null;
  const b = doc.getElementById(id);
  assert(!!b, `export button #${id} present`);
  if (b) {
    b.dispatchEvent(new window.Event("click", { bubbles: true }));
    assert(lastPrompt && lastPrompt.includes("artifacts/"), `#${id} exports into artifacts/`);
    assert(lastPrompt && lastPrompt.includes("as " + fmt), `#${id} requests format ${fmt}`);
  }
}

if (fail === 0) {
  console.log(`  OK — cm3 tuner: default + ${(expected.steps || []).length} tuned step(s) JS<->Python parity, Save + exports correct`);
  process.exit(0);
} else {
  console.log(`  ${fail} failure(s) for cm3 tuner`);
  process.exit(1);
}
