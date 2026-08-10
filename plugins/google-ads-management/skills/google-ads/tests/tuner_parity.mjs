// tuner_parity.mjs — JS<->Python parity check for one assembled tuner widget.
//
// Usage:  node tuner_parity.mjs <widget.html> <expected.json>
//         node tuner_parity.mjs --analytics <expected.json>
//
// --analytics mode (HM-532): <expected.json> is the output of
// `_compute_expected.py --analytics` — {js_mirror, cases[]}. The runner
// evaluates the canonical _shared/analytics.py JS_MIRROR string and replays
// every case (concentration / signals / pre_score), deep-asserting the JS
// results equal the Python-computed expected values.
//
// Loads the assembled show_widget fragment under jsdom, then asserts:
//   1. the live JS kernel `summarize(MODEL.rows, P)` at default params deep-equals
//      both the embedded Python summary (MODEL.summary) and expected.default;
//   2. driving the chosen control (selected by key via SPEC.controls order, so we
//      never have to edit explorer-widget.html) re-tunes P and the JS summary then
//      equals expected.tuned (computed in Python) and actually changed a KPI;
//   3. the Save button emits a sendPrompt carrying the tuned params, targeting
//      raw/reports/<filename_stem>.md, with "do not propose_note".
//   4. (optional, when expected.multi_tune is set) on a FRESH widget instance,
//      unchecking one option of a checkbox-group ("multi") control re-tunes the
//      array param P[key] and the live JS summary still equals Python's
//      expected.multi_tuned, a KPI moved, and Save carries the reduced list.
//
// expected.json (written by run_parity.py): {skill, kpi_keys[], default{}, tuned{},
//   tune_key, tune_value, filename_stem, kpi_map{}, multi_tune?{key,drop},
//   multi_scope?[], multi_tuned?{}}. kpi_map maps a KPI's spec key (the JS-side
//   key) to the Python summary key when a skill names them differently (e.g.
//   keywords: b1->block1); absent/identity for skills that share key names.
//
// Dev-only: requires `npm install` in this dir (jsdom). The plugin never runs this.
import fs from "node:fs";
import { JSDOM } from "jsdom";

const [, , htmlPath, expectedPath] = process.argv;
if (!htmlPath || !expectedPath) {
  console.error("usage: node tuner_parity.mjs <widget.html>|--analytics <expected.json>");
  process.exit(2);
}

// ── analytics-primitives mode (HM-532) ─────────────────────────────────────
if (htmlPath === "--analytics") {
  const exp = JSON.parse(fs.readFileSync(expectedPath, "utf8"));
  // Evaluate the canonical JS mirror in an isolated function scope and pull
  // out the three kernels — the exact string skills splice into js_kernel.
  const lib = new Function(
    exp.js_mirror +
    "\n;return {concentration: gxConcentration, signals: gxSignals, preScore: gxPreScore, segmentLiveness: gxSegmentLiveness};"
  )();
  let aFail = 0;
  const numEq = (a, b) =>
    typeof a === "number" && typeof b === "number"
      ? Math.abs(a - b) < 1e-9
      : a === b;
  const deepEq = (a, b) => {
    if (Array.isArray(a) && Array.isArray(b))
      return a.length === b.length && a.every((v, i) => deepEq(v, b[i]));
    if (a && b && typeof a === "object" && typeof b === "object") {
      const ka = Object.keys(a).sort(), kb = Object.keys(b).sort();
      return deepEq(ka, kb) && ka.every((k) => deepEq(a[k], b[k]));
    }
    return numEq(a, b);
  };
  for (const c of exp.cases) {
    let got;
    if (c.fn === "concentration")
      got = lib.concentration(c.args.rows, c.args.value_key, c.args.top_n ?? 3);
    else if (c.fn === "signals") got = lib.signals(c.args.rows, c.args.rules);
    else if (c.fn === "pre_score") got = lib.preScore(c.args.row, c.args.weights);
    else if (c.fn === "segment_liveness")
      got = lib.segmentLiveness(c.args.rows, c.args.status_key, c.args.spend_key,
                                c.args.prior_spend_key ?? null);
    else { aFail++; console.log(`  FAIL: unknown fn '${c.fn}' (${c.file}#${c.i})`); continue; }
    if (!deepEq(got, c.expected)) {
      aFail++;
      console.log(`  FAIL: ${c.fn} ${c.file}#${c.i}: JS ${JSON.stringify(got)} != Python ${JSON.stringify(c.expected)}`);
    }
  }
  if (aFail === 0) {
    console.log(`  OK — analytics-primitives: ${exp.cases.length} vectors, JS_MIRROR == Python _shared/analytics.py`);
    process.exit(0);
  }
  console.log(`  ${aFail} failure(s) for analytics-primitives`);
  process.exit(1);
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
const kpiMap = expected.kpi_map || {};
const pk = (k) => kpiMap[k] || k;   // KPI spec key (JS side) -> Python summary key

// --- kernel present ---
assert(window.eval("typeof summarize") === "function", "JS kernel summarize present");

// --- default parity: JS == embedded Python == expected.default ---
const embedded = evalJSON("MODEL.summary");
const jsDefault = evalJSON("summarize(MODEL.rows, P)");
for (const k of kpiKeys) {
  assert(eqVal(jsDefault[k], embedded[pk(k)]),
    `default JS[${k}]=${jsDefault[k]} == embedded Python[${pk(k)}]=${embedded[pk(k)]}`);
  assert(eqVal(jsDefault[k], expected.default[pk(k)]),
    `default JS[${k}]=${jsDefault[k]} == expected.default[${pk(k)}]=${expected.default[pk(k)]}`);
}

// --- locate the control by key (via SPEC.controls order) and tune it ---
const ctlKeys = evalJSON("(SPEC.controls||[]).map(c=>c.key)");
const idx = ctlKeys.indexOf(expected.tune_key);
assert(idx >= 0, `control '${expected.tune_key}' present in SPEC.controls`);
const ctlDiv = doc.querySelectorAll("#gx-controls .gx-ctl")[idx];
const input = ctlDiv && ctlDiv.querySelector("input, select");
assert(!!input, `rendered input for control '${expected.tune_key}'`);
if (input) {
  input.value = String(expected.tune_value);
  const evName = input.tagName === "SELECT" ? "change" : "input";
  input.dispatchEvent(new window.Event(evName, { bubbles: true }));
}

// readout-span parity (sliders only have a gv_<key> span): integers read clean, fractionals 2dp —
// guards the 1b12e63 fix against a toFixed(0) regression.
const gv = doc.getElementById("gv_" + expected.tune_key);
if (gv) {
  const n = Number(expected.tune_value);
  const want = Number.isInteger(n) ? String(n) : n.toFixed(2);
  assert(gv.textContent === want, `slider readout gv_${expected.tune_key}='${gv.textContent}' == '${want}'`);
}

// --- tuned parity: JS == expected.tuned, and a KPI actually moved ---
const jsTuned = evalJSON("summarize(MODEL.rows, P)");
let changed = false;
for (const k of kpiKeys) {
  assert(eqVal(jsTuned[k], expected.tuned[pk(k)]),
    `tuned JS[${k}]=${jsTuned[k]} == expected.tuned[${pk(k)}]=${expected.tuned[pk(k)]}`);
  if (!eqVal(jsTuned[k], jsDefault[k])) changed = true;
}
assert(changed, `tuning '${expected.tune_key}'=${expected.tune_value} changed at least one KPI (non-vacuous)`);

// --- Save -> direct-write prompt ---
doc.getElementById("gx-save").dispatchEvent(new window.Event("click", { bubbles: true }));
assert(lastPrompt !== null, "Save fired sendPrompt");
const p = lastPrompt || "";
assert(p.includes("raw/reports/"), "prompt targets raw/reports/");
assert(p.includes(expected.filename_stem + ".md"), `prompt names ${expected.filename_stem}.md`);
assert(/do not propose_note/i.test(p), "prompt says do not propose_note");
assert(p.includes(`"${expected.tune_key}"`) && p.includes(String(expected.tune_value)),
  `prompt carries tuned param ${expected.tune_key}=${expected.tune_value}`);

// --- multi-select ("multi") control parity (optional) ---
// A checkbox-group control holds an ARRAY param. Unchecking one option must
// re-tune P[key] to the reduced list and the live JS recompute must still match
// Python. Runs on a FRESH widget instance so P starts at defaults (the scalar
// tune above already mutated P on the first instance).
if (expected.multi_tune) {
  const mKey = expected.multi_tune.key, mDrop = expected.multi_tune.drop;
  let mPrompt = null;
  const dom2 = new JSDOM(`<!DOCTYPE html><html><body>${fragment}</body></html>`, {
    runScripts: "dangerously",
    beforeParse(w) { w.sendPrompt = (t) => { mPrompt = t; }; },
  });
  const w2 = dom2.window, d2 = w2.document;
  const evalJSON2 = (expr) => JSON.parse(w2.eval("JSON.stringify(" + expr + ")"));

  const mDefault = evalJSON2("summarize(MODEL.rows, P)");

  // locate the multi control (by key, via SPEC.controls order) and its checkboxes
  const mIdx = evalJSON2("(SPEC.controls||[]).map(c=>c.key)").indexOf(mKey);
  assert(mIdx >= 0, `multi control '${mKey}' present in SPEC.controls`);
  const mDiv = d2.querySelectorAll("#gx-controls .gx-ctl")[mIdx];
  const boxes = mDiv ? [...mDiv.querySelectorAll('input[type="checkbox"]')] : [];
  assert(boxes.length > 0, `multi control '${mKey}' rendered a checkbox group`);
  const target = boxes.find((cb) => cb.value === mDrop);
  assert(!!target, `checkbox for option '${mDrop}' rendered`);
  assert(!target || target.checked, `option '${mDrop}' checked by default`);
  if (target) {
    target.checked = false;
    target.dispatchEvent(new w2.Event("change", { bubbles: true }));
  }

  // tuned parity: JS == expected.multi_tuned, and a KPI actually moved
  const mTuned = evalJSON2("summarize(MODEL.rows, P)");
  let mChanged = false;
  for (const k of kpiKeys) {
    assert(eqVal(mTuned[k], expected.multi_tuned[pk(k)]),
      `multi JS[${k}]=${mTuned[k]} == expected.multi_tuned[${pk(k)}]=${expected.multi_tuned[pk(k)]}`);
    if (!eqVal(mTuned[k], mDefault[k])) mChanged = true;
  }
  assert(mChanged, `unchecking '${mDrop}' changed at least one KPI (non-vacuous)`);

  // P[key] is now the reduced array, and Save carries it (the dropped enum is gone)
  assert(JSON.stringify(evalJSON2("P[" + JSON.stringify(mKey) + "]")) === JSON.stringify(expected.multi_scope),
    `P.${mKey} re-tuned to reduced scope ${JSON.stringify(expected.multi_scope)}`);
  d2.getElementById("gx-save").dispatchEvent(new w2.Event("click", { bubbles: true }));
  assert(mPrompt !== null && !(mPrompt || "").includes(`"${mDrop}"`),
    `Save prompt carries reduced scope (dropped "${mDrop}")`);
}

// --- bounded-embed ("trim") parity (optional, HM-339) ---
// On a FRESH instance (P at defaults), assert the widget embedded only the in-play
// envelope yet reproduces the full model: honest universe count, sensitivity ladder,
// and near-miss containment — all recomputed live from the trimmed embed.
if (expected.trim) {
  const dom3 = new JSDOM(`<!DOCTYPE html><html><body>${fragment}</body></html>`, {
    runScripts: "dangerously",
    beforeParse(w) { w.sendPrompt = () => {}; },
  });
  const w3 = dom3.window, d3 = w3.document;
  const ev3 = (e) => JSON.parse(w3.eval("JSON.stringify(" + e + ")"));
  const embedded = ev3("MODEL.rows.length"), total = ev3("MODEL.total_rows");
  assert(total === expected.universe_total, `total_rows=${total} == universe=${expected.universe_total}`);
  assert(embedded < total, `embed trimmed: rows=${embedded} < universe=${total}`);
  assert(ev3("summarize(MODEL.rows, P).universe") === expected.universe_total,
    `summarize.universe=${ev3("summarize(MODEL.rows, P).universe")} == ${expected.universe_total} (authoritative count)`);
  const prov = d3.getElementById("gx-prov").textContent;
  assert(prov.includes(total.toLocaleString()), `provenance shows full universe ${total.toLocaleString()}`);
  // sensitivity ladder recomputed from the trimmed embed == full-model ladder
  for (const pt of (expected.sensitivity || [])) {
    w3.eval("P.cost_multiple=" + pt.cost_multiple);
    const t = ev3("summarize(MODEL.rows, P).total");
    assert(t === pt.total, `sensitivity@${pt.cost_multiple}: trimmed total=${t} == full=${pt.total}`);
  }
  // every full-model near-miss term must survive into the trimmed embed
  const terms = new Set(ev3("MODEL.rows.map(r=>r.term)"));
  const missing = (expected.near_miss_terms || []).filter((t) => !terms.has(t));
  assert(missing.length === 0,
    `all ${(expected.near_miss_terms || []).length} near-miss terms present in trimmed embed `
    + `(missing ${missing.length}${missing.length ? ": " + missing.slice(0, 3).join(", ") : ""})`);
}

if (fail === 0) {
  const mNote = expected.multi_tune ? " (+ multi-control toggle)" : "";
  const tNote = expected.trim ? " (+ bounded-embed trim)" : "";
  console.log(`  OK — ${expected.skill}: default+tuned JS<->Python parity${mNote}${tNote}, Save prompt correct`);
  process.exit(0);
} else {
  console.log(`  ${fail} failure(s) for ${expected.skill}`);
  process.exit(1);
}
