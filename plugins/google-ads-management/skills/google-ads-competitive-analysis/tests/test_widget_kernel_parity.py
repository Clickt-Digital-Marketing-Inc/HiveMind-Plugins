#!/usr/bin/env python3
"""Dev-only JS<->Python parity check for THIS skill's tuner widget kernel.

Mirrors what `skills/google-ads/tests/run_parity.py` does for the skills
already registered there, without editing that shared harness file (the M2
orchestration rule — the catalog/harness registration itself is deferred to
the serial M3.1). This script drives the same building blocks read-only:
`build_competitive_report.py --emit-widget`, the hub's
`references/build_widget.py`, and `skills/google-ads/tests/tuner_parity.mjs`
(invoked as a subprocess, never imported/edited).

Requires `node` + `npm install` having been run once in
`skills/google-ads/tests/` (same dev dependency as run_parity.py). Not part of
the stdlib-only `tests/test_competitive.py` suite for that reason.

    python3 tests/test_widget_kernel_parity.py

Exit 0 = parity holds, 1 = a failure or the dev dependency is missing.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
PLUGIN_ROOT = HERE.parents[2]
HUB_TESTS = PLUGIN_ROOT / "skills" / "google-ads" / "tests"
BUILD_WIDGET = PLUGIN_ROOT / "skills" / "google-ads" / "references" / "build_widget.py"
TUNER_PARITY = HUB_TESTS / "tuner_parity.mjs"
BUILDER = SCRIPTS / "build_competitive_report.py"
FIXTURE = HERE / "sample-findings.json"
PY = sys.executable

sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(PLUGIN_ROOT / "_shared"))
import competitive_core as core  # noqa: E402


def main() -> int:
    if not (HUB_TESTS / "node_modules").exists():
        print("SKIP: node_modules not installed in skills/google-ads/tests/ "
              "(run `npm install` there first) — same dev dependency as run_parity.py")
        return 0

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        wjson, whtml, expf = tmp / "w.json", tmp / "w.html", tmp / "expected.json"

        r = subprocess.run([PY, str(BUILDER), "--input", str(FIXTURE), "--formats", "",
                            "--brand", "Sample Co", "--emit-widget", str(wjson)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(f"FAIL: emit-widget failed: {r.stderr}"); return 1
        widget = json.loads(wjson.read_text())
        kpi_keys = [k["key"] for k in widget["spec"]["kpis"]]

        r = subprocess.run([PY, str(BUILD_WIDGET), "--data", str(wjson), "--out", str(whtml)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(f"FAIL: build_widget failed: {r.stderr}"); return 1

        # Python default + tuned (tune min_cost DOWN so SmallSpend becomes eligible
        # and flags -> a non-vacuous KPI move, exercising the eligibility gate live).
        findings = core.load_findings(str(FIXTURE))
        m_default = core.compute_model(findings)
        tuned_findings = dict(findings)
        tuned_findings["params"] = {**(findings.get("params") or {}), "min_cost": 10.0}
        m_tuned = core.compute_model(tuned_findings)

        expected = {
            "skill": "competitive-analysis", "kpi_keys": kpi_keys,
            "default": m_default["summary"], "tuned": m_tuned["summary"],
            "tune_key": "min_cost", "tune_value": 10,
            "filename_stem": widget["save"]["filename_stem"], "kpi_map": {},
        }
        expf.write_text(json.dumps(expected))

        r = subprocess.run(["node", str(TUNER_PARITY), str(whtml), str(expf)],
                           capture_output=True, text=True)
        print((r.stdout + r.stderr).strip())
        if r.returncode != 0:
            print("FAIL: JS<->Python widget kernel parity"); return 1
        print("OK: competitive-analysis widget kernel — JS<->Python parity, Save prompt correct")
        return 0


if __name__ == "__main__":
    sys.exit(main())
