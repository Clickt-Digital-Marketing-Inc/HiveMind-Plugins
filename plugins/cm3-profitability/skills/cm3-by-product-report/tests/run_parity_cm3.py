#!/usr/bin/env python3
"""Standalone JS<->Python parity check for the cm3-by-product in-Claude tuner.

Builds the tuner fragment from the fixture CSV via `cm3_by_product.py --emit-widget`,
computes the Python `compute()` summary at default + two cumulative tuned scenarios
(a band cutoff, then a cost assumption), and runs `tuner_parity_cm3.mjs` to assert the
widget's live JS kernel matches Python at each point and the Save/Export prompts are
correct.

This is the cm3 analogue of the bundle skills' run_parity.py, kept standalone because
cm3 is bespoke: flat layout, a `--csv`/`--output-*` builder (not `--input/--formats`),
and its own widget renderer (cm3_html.build_widget_fragment, not _shared).

Dev-only: needs `npm install` in this dir (jsdom). The plugin never runs this.
Run: python3 tests/run_parity_cm3.py
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(SKILL))

import cm3_by_product as cm3   # noqa: E402
import cm3_html               # noqa: E402

PY = sys.executable
NODE = "node"
SAMPLE = HERE / "sample-shopping.csv"

# Defaults must mirror cm3_by_product.main()'s inputs.setdefault() block.
BASE_INPUTS = {
    "cogs_pct": 65, "ship_pct": 20, "proc_pct": 2.9, "fixed_costs": 0,
    "band_exc": 0.10, "band_high": 0.05, "band_avg": 0.00, "band_low": -0.25,
}
# tuner control key -> (inputs key, scale to apply to the control's JS value)
CTRL_TO_INPUT = {
    "cogs": ("cogs_pct", 100), "ship": ("ship_pct", 100), "proc": ("proc_pct", 100),
    "fixed": ("fixed_costs", 1),
    "exc": ("band_exc", 1), "high": ("band_high", 1), "avg": ("band_avg", 1), "low": ("band_low", 1),
}
# Cumulative tunes: a cutoff first, then a cost assumption — both non-vacuous on the fixture.
STEPS = [("exc", 0.05), ("ship", 0.30)]


def summary_for(inputs: dict) -> dict:
    products, _, _ = cm3.parse_csv(str(SAMPLE))
    ctx = cm3.compute(products, dict(inputs))
    return cm3_html._widget_summary(ctx)


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        widget = Path(td) / "widget.html"
        r = subprocess.run(
            [PY, str(SKILL / "cm3_by_product.py"), "--csv", str(SAMPLE),
             "--brand", "Abes College", "--emit-widget", str(widget)],
            capture_output=True, text=True)
        if r.returncode != 0:
            sys.stderr.write(r.stderr)
            print("FAIL — emit-widget failed")
            return 1

        html = widget.read_text(encoding="utf-8")
        m = re.search(r'<script id="cx-data"[^>]*>(.*?)</script>', html, re.S)
        if not m:
            print("FAIL — no embedded cx-data model in the fragment")
            return 1
        model = json.loads(m.group(1).replace("<\\/", "</"))
        stem = model["save"]["filename_stem"]

        default = summary_for(BASE_INPUTS)
        cur = dict(BASE_INPUTS)
        steps = []
        for key, val in STEPS:
            ik, scale = CTRL_TO_INPUT[key]
            cur[ik] = val * scale
            steps.append({"key": key, "value": val, "summary": summary_for(cur)})

        expected = {
            "skill": "cm3-by-product",
            "kpi_keys": list(default.keys()),
            "default": default,
            "steps": steps,
            "filename_stem": stem,
        }
        expf = Path(td) / "expected.json"
        expf.write_text(json.dumps(expected), encoding="utf-8")

        r = subprocess.run([NODE, str(HERE / "tuner_parity_cm3.mjs"), str(widget), str(expf)],
                           capture_output=True, text=True, cwd=str(HERE))
        sys.stdout.write(r.stdout)
        sys.stderr.write(r.stderr)
        return r.returncode


if __name__ == "__main__":
    sys.exit(main())
