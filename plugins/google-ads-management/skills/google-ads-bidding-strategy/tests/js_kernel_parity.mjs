// Node-vs-Python kernel parity harness for THIS skill's own js_kernel
// (bidding_spec.JS_KERNEL). Deliberately separate from the shared
// skills/google-ads/tests/run_parity.py + tuner_parity.mjs harness (which is
// a frozen file this skill's build is not allowed to edit during the
// parallel M2 batch — see docs/orchestration.md) — the analytics.JS_MIRROR
// portion of this kernel IS already covered by that shared harness via
// analytics_vectors_bidding.json; this script additionally proves the
// skill-specific classify()/summarize() wrapper around it agrees with
// bidding_core.classify_row/summarize on real rows + several param sets.
//
// Usage: node js_kernel_parity.mjs <fixture.json>
// fixture.json: {"kernel_src": "<the JS_KERNEL text>",
//                "rows": [...], "scenarios": [{"name","params","expected":[...]}]}
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
  return rows.map((r) => classify(r, params));
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
  const got = run(fx.rows, scenario.params);
  scenario.expected.forEach((exp, i) => {
    const g = got[i];
    for (const key of Object.keys(exp)) {
      check(`row ${i} (${fx.rows[i].campaign}) ${key}`, approxEqual(g[key], exp[key]),
            `got=${JSON.stringify(g[key])} want=${JSON.stringify(exp[key])}`);
    }
    check(`row ${i} (${fx.rows[i].campaign}) block == mismatch`, g.block === g.mismatch);
  });
}

console.log();
if (failures) {
  console.log(`FAILED (${failures})`);
  process.exit(1);
}
console.log("ALL TESTS PASSED");
