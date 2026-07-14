#!/usr/bin/env python3
"""Run this skill's own n-gram JS<->Python parity check (HM-536).

    python3 tests/test_ngram_parity.py

Drives _compute_ngram_expected.py (Python side) + ngram_js_parity.mjs (Node
side) across both committed fixtures (the small default fixture and the
large bounded-embed fixture) at default and tuned `cost_multiple`. This is a
standalone check scoped to this skill's own tests/ — NOT an edit to the
shared hub harness (skills/google-ads/tests/run_parity.py + friends are
frozen during the parallel-batch build; see docs/orchestration.md). Requires
`node` on PATH; no npm packages needed (gxWasteNgrams is pure data, no DOM).
Exit 0 = all pass, 1 = a failure, 2 = environment error (node missing).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMPUTE = HERE / "_compute_ngram_expected.py"
PARITY = HERE / "ngram_js_parity.mjs"

CASES = [
    {"id": "sample-findings", "fixture": HERE / "sample-findings.json",
     "tune_key": "cost_multiple", "tune_value": "1.0"},
    {"id": "sample-findings-large", "fixture": HERE / "sample-findings-large.json",
     "tune_key": "cost_multiple", "tune_value": "1.5"},
]


def main() -> int:
    if shutil.which("node") is None:
        print("SKIP — 'node' not found on PATH (n-gram JS<->Python parity needs it)")
        return 2

    fail = 0
    with tempfile.TemporaryDirectory() as td:
        for c in CASES:
            expf = Path(td) / f"{c['id']}.expected.json"
            r = subprocess.run(
                [sys.executable, str(COMPUTE), str(c["fixture"]), c["tune_key"], c["tune_value"]],
                capture_output=True, text=True)
            if r.returncode != 0:
                fail += 1
                print(f"[FAIL   ] {c['id']}  — python expected failed: {r.stderr.strip()}")
                continue
            expf.write_text(r.stdout, encoding="utf-8")

            r = subprocess.run(["node", str(PARITY), str(expf)], capture_output=True, text=True)
            out = (r.stdout + r.stderr).strip()
            if r.returncode == 0:
                print(f"[OK     ] {c['id']}")
                if out:
                    print(out)
            else:
                fail += 1
                print(f"[FAIL   ] {c['id']}")
                if out:
                    print(out)

    print()
    if fail:
        print(f"FAILED ({fail} case(s))")
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
