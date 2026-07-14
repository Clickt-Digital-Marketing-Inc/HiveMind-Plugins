#!/usr/bin/env python3
"""Build / check the search-term waste-filter workbook (.xlsx) — thin wrapper.

The workbook is rendered by the shared toolkit (`_shared/render/xlsx.py`) from
the waste-filter model (`waste_filter_core`) and the xlsx layout
(`waste_filter_xlsx_spec`). This file is just the CLI; the dependency-free
primaries (md, html) come from build_waste_filter.py.

Sheets: Controls (tunable params + self-rewriting logic + live COUNTIF/SUMIF +
campaign benchmarks) · Live filter (every term + Status; scored rows carry
formulas referencing the Controls cells) · Sensitivity (static snapshot).

Excel-compatibility: the file is normalized through LibreOffice (`soffice`) by
default so it opens in Excel; if soffice is missing the build FAILS (exit 2).
Use --no-normalize to override. Real-Excel open is not verified here.

Usage:
    python3 build_search_term_filter_workbook.py --input findings.json \\
        --output "search-term-waste-acme-2026-06-26.xlsx" --brand "Acme Corp"
    python3 build_search_term_filter_workbook.py --check --input <file>.xlsx

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

import waste_filter_core as core            # noqa: E402
import waste_filter_spec as spec_mod        # noqa: E402
import waste_filter_xlsx_spec as xspec      # noqa: E402


def _spec() -> dict:
    s = dict(spec_mod.SPEC)
    s["xlsx"] = xspec.XLSX
    return s


def main() -> int:
    ap = argparse.ArgumentParser(description="Build / check the search-term waste-filter .xlsx.")
    ap.add_argument("--input", required=True, help="findings JSON (build) or .xlsx (with --check)")
    ap.add_argument("--output", help="output .xlsx path (build mode)")
    ap.add_argument("--brand", default="", help="client/brand name for the title")
    ap.add_argument("--check", action="store_true", help="structurally validate an existing workbook")
    ap.add_argument("--normalize", dest="normalize", action="store_true", default=True,
                    help="normalize via LibreOffice for Excel compatibility (default on)")
    ap.add_argument("--no-normalize", dest="normalize", action="store_false",
                    help="skip normalization (file is valid but may need 'Repair' in Excel-for-Mac)")
    args = ap.parse_args()

    from render import xlsx as xlsxmod  # openpyxl lives here, imported only now

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
    print(f"  universe={stats['universe']}  scored={stats['scored']}  no_benchmark={stats['no_benchmark']}")
    print(f"  at current params -> Block1={stats['block1']}  Block2={stats['block2']}  wasted={stats['wasted']}")
    print(f"  normalized via LibreOffice: {'yes' if args.normalize else 'no (--no-normalize)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
