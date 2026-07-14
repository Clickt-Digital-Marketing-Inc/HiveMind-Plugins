// ngram_js_parity.mjs — this skill's OWN JS<->Python parity check for the
// gxTermNgrams / gxWasteNgrams mirror spliced into waste_filter_spec.JS_KERNEL
// (HM-536). Not the shared hub harness (frozen during the parallel batch —
// see docs/orchestration.md); a standalone check scoped to this skill's
// tests/. No jsdom needed — gxWasteNgrams is pure data (rows array in,
// {top, concentration} out), no DOM involved, so a plain `new Function()` eval
// of the deployed js_kernel string is enough (the same technique
// skills/google-ads/tests/tuner_parity.mjs uses for --analytics mode).
//
// Usage: node ngram_js_parity.mjs <expected.json>
// <expected.json> is the output of _compute_ngram_expected.py.
import fs from "node:fs";

const [, , expPath] = process.argv;
if (!expPath) {
  console.error("usage: node ngram_js_parity.mjs <expected.json>");
  process.exit(2);
}

const exp = JSON.parse(fs.readFileSync(expPath, "utf8"));
const lib = new Function(exp.js_kernel + "\n;return {wasteNgrams: gxWasteNgrams};")();

const numEq = (a, b) =>
  typeof a === "number" && typeof b === "number" ? Math.abs(a - b) < 1e-6 : a === b;
const deepEq = (a, b) => {
  if (Array.isArray(a) && Array.isArray(b))
    return a.length === b.length && a.every((v, i) => deepEq(v, b[i]));
  if (a && b && typeof a === "object" && typeof b === "object") {
    const ka = Object.keys(a).sort(), kb = Object.keys(b).sort();
    return deepEq(ka, kb) && ka.every((k) => deepEq(a[k], b[k]));
  }
  return numEq(a, b);
};

let fail = 0;
const assertEq = (got, want, label) => {
  if (!deepEq(got, want)) {
    fail++;
    console.log(`  FAIL ${label}: JS ${JSON.stringify(got)} != Python ${JSON.stringify(want)}`);
  }
};

const gotDefault = lib.wasteNgrams(exp.rows, exp.params);
assertEq(gotDefault, exp.expected_default, "default params");

const gotTuned = lib.wasteNgrams(exp.rows, exp.tuned_params);
assertEq(gotTuned, exp.expected_tuned, "tuned params");

if (fail === 0) {
  console.log(`  OK — n-gram JS<->Python parity (default + tuned), `
    + `${exp.expected_default.top.length + exp.expected_tuned.top.length} n-gram rows checked`);
  process.exit(0);
}
console.log(`  ${fail} failure(s)`);
process.exit(1);
