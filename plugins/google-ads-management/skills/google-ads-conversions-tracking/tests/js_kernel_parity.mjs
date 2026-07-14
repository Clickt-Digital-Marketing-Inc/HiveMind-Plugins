// Node-vs-Python kernel parity harness for THIS skill's own js_kernel
// (conv_tracking_spec.JS_KERNEL). Deliberately separate from the shared
// skills/google-ads/tests/run_parity.py + tuner_parity.mjs harness (which
// drives the widget-tuner --emit-widget path used by the 7 M1 skills) — this
// skill's classify()/summarize() wrapper is exercised directly, mirroring
// google-ads-bidding-strategy/tests/js_kernel_parity.mjs.
//
// Usage: node js_kernel_parity.mjs <fixture.json>
// fixture.json: {"kernel_src": "<the JS_KERNEL text>",
//                "rows": [...],
//                "scenarios": [{"name","params","expected":[...],
//                               "expected_summary": {...}}]}
// Exit 0 = all pass, 1 = a failure.
import fs from "node:fs";

const [, , fixturePath] = process.argv;
if (!fixturePath) {
  console.error("usage: node js_kernel_parity.mjs <fixture.json>");
  process.exit(2);
}
const fx = JSON.parse(fs.readFileSync(fixturePath, "utf8"));

function run(rows, params) {
  let classify, summarize;
  // Direct eval (not indirect) — resolves the pre-declared `let` bindings
  // above via the lexical scope chain, exactly like the real explorer
  // template's inline <script> does with /*__KERNEL__*/.
  // eslint-disable-next-line no-eval
  eval(fx.kernel_src);
  return { classified: rows.map((r) => classify(r, params)), summary: summarize(rows, params) };
}

let failures = 0;
function check(name, cond, detail) {
  console.log(`  ${cond ? "PASS" : "FAIL"}  ${name}` + (detail && !cond ? `  — ${detail}` : ""));
  if (!cond) failures++;
}

function approxEqual(a, b) {
  if (typeof a === "number" && typeof b === "number") return Math.abs(a - b) < 1e-6;
  return JSON.stringify(a) === JSON.stringify(b);
}

for (const scenario of fx.scenarios) {
  console.log(`scenario: ${scenario.name}`);
  const { classified, summary } = run(fx.rows, scenario.params);
  scenario.expected.forEach((exp, i) => {
    const g = classified[i];
    for (const key of Object.keys(exp)) {
      check(`row ${i} (${fx.rows[i].campaign}) ${key}`, approxEqual(g[key], exp[key]),
            `got=${JSON.stringify(g[key])} want=${JSON.stringify(exp[key])}`);
    }
    check(`row ${i} (${fx.rows[i].campaign}) block == tier`, g.block === g.tier);
  });
  if (scenario.expected_summary) {
    for (const key of Object.keys(scenario.expected_summary)) {
      check(`summary.${key}`, approxEqual(summary[key], scenario.expected_summary[key]),
            `got=${JSON.stringify(summary[key])} want=${JSON.stringify(scenario.expected_summary[key])}`);
    }
  }
}

console.log();
if (failures) {
  console.log(`FAILED (${failures})`);
  process.exit(1);
}
console.log("ALL TESTS PASSED");
