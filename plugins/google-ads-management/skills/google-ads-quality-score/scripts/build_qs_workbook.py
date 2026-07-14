#!/usr/bin/env python3
"""Build / check the Quality Score forensics workbook (.xlsx) — thin wrapper.

Rendered by the shared toolkit (`_shared/render/xlsx.py`) from the QS model
(`qs_core`) and the xlsx layout (`qs_xlsx_spec`).

Usage:
    python3 build_qs_workbook.py --input findings.json --output report.xlsx --brand "Acme"
    python3 build_qs_workbook.py --check --input report.xlsx

Exit codes: 0 success, 1 usage/validation error, 2 build/normalization error.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PLUGIN_ROOT / "_shared"))

import qs_core as core         # noqa: E402
import qs_spec as spec_mod     # noqa: E402
import qs_xlsx_spec as xspec   # noqa: E402


def _spec() -> dict:
    s = dict(spec_mod.SPEC)
    s["xlsx"] = xspec.XLSX
    return s


def main() -> int:
    ap = argparse.ArgumentParser(description="Build / check the Quality Score forensics .xlsx.")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output")
    ap.add_argument("--brand", default="")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--normalize", dest="normalize", action="store_true", default=True)
    ap.add_argument("--no-normalize", dest="normalize", action="store_false")
    args = ap.parse_args()

    from render import xlsx as xlsxmod

    if args.check:
        return xlsxmod.check_workbook(args.input, _spec())
    if not args.output:
        sys.stderr.write("ERROR: --output is required in build mode\n"); return 1
    try:
        findings = core.load_findings(args.input)
    except core.FindingsError as e:
        sys.stderr.write(f"ERROR: {e}\n"); return 1
    model = core.compute_model(findings)
    stats = xlsxmod.build_xlsx(model, _spec(), args.output, brand=args.brand, normalize=args.normalize)
    print(f"SAVED: {args.output}")
    print(f"  scored={stats['scored']} in_scope={stats['in_scope']} LP={stats['lp']} "
          f"AdRel={stats['ad_rel']} ExpCTR={stats['exp_ctr']} Critical={stats['critical']} "
          f"pause={stats['pause_candidates']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
