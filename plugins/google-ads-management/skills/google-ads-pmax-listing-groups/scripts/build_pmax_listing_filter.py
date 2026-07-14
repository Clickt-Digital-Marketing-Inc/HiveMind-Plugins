#!/usr/bin/env python3
"""PMax listing-group waste filter — multi-format deliverable builder (thin CLI).

Reads a findings JSON (schema is authoritative in
`references/pmax-listing-waste-filter.md`) and emits the standard analytical
bundle via the shared render toolkit (`_shared/render`):

  md   — narrative report (provenance, headline, the 0/0-is-clean story,
         partition + product sensitivity, near-misses, excluded campaigns,
         and full per-unit tables — no row loss in either universe). Zero deps.
  html — a self-contained interactive explorer: one Expensiveness-factor slider
         driving BOTH the partition table and the products panel, live, in any
         browser. No install, no cloud, no Excel. The interactive primary.
  xlsx — the tunable Controls + Live-filter (partitions) + Sensitivity workbook
         with a products snapshot (needs openpyxl; LibreOffice-normalized).

All formats share one classification engine (pmax_listing_core), so they can
never disagree. The render config lives in pmax_listing_spec / pmax_listing_xlsx_spec.

Usage:
    python3 build_pmax_listing_filter.py --input findings.json --outdir artifacts \\
        --brand "Acme Shop" --formats md,html
    python3 build_pmax_listing_filter.py --input findings.json --outdir artifacts \\
        --formats md,html,xlsx

Exit codes: 0 success, 1 usage/validation error, 2 build error.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parents[2]            # .../plugins/google-ads-management
sys.path.insert(0, str(HERE))            # pmax_listing_core / pmax_listing_spec
sys.path.insert(0, str(PLUGIN_ROOT / "_shared"))  # the render toolkit

import pmax_listing_core as core         # noqa: E402
import pmax_listing_spec as spec_mod     # noqa: E402
from render import build_bundle, model as rmodel  # noqa: E402
from widget_emit import emit_widget      # noqa: E402

SKILL_NAME = "google-ads-pmax-listing-groups"


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the PMax listing-group waste-filter bundle.")
    ap.add_argument("--input", required=True, help="findings JSON")
    ap.add_argument("--outdir", default="artifacts", help="output directory (default: artifacts)")
    ap.add_argument("--brand", default="", help="client/brand name (used for slug/title if meta omits it)")
    ap.add_argument("--formats", default="md,html,xlsx",
                    help="comma list of md,html,xlsx (use '' to emit only the widget JSON)")
    ap.add_argument("--no-normalize", dest="normalize", action="store_false", default=True,
                    help="skip LibreOffice xlsx normalization (file may need Repair in Excel-for-Mac)")
    ap.add_argument("--no-charts", dest="charts", action="store_false", default=True,
                    help="skip the declared Vega-Lite charts (static SVGs + live explorer charts)")
    ap.add_argument("--emit-widget", dest="emit_widget", default=None,
                    help="also write the in-Claude tuner's data JSON to this path")
    args = ap.parse_args()

    formats = [f.strip().lower() for f in args.formats.split(",") if f.strip()]
    unknown = [f for f in formats if f not in ("md", "html", "xlsx")]
    if unknown:
        sys.stderr.write(f"ERROR: unknown format(s): {', '.join(unknown)}\n")
        return 1

    try:
        findings = core.load_findings(args.input)
    except core.FindingsError as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return 1
    if not (findings.get("meta") or {}).get("reconciliation"):
        sys.stderr.write(
            "WARN: findings carry no reconciliation totals — data transcription is "
            "UNVERIFIED. Assemble findings from the saved raw pulls with "
            "scripts/assemble_findings.py instead of writing the JSON by hand.\n")
    model = core.compute_model(findings)

    spec = dict(spec_mod.SPEC)
    if not args.charts:
        spec.pop("charts", None)  # keeps charts out of the bundle AND the widget emit
    if "xlsx" in formats:
        import pmax_listing_xlsx_spec as xspec  # stdlib data; openpyxl stays inside render.xlsx
        spec["xlsx"] = xspec.XLSX

    written = []
    if formats:
        try:
            written = build_bundle(model, spec, args.outdir, formats=formats,
                                   brand=args.brand, normalize=args.normalize,
                                   charts=args.charts)
        except SystemExit as e:               # xlsx normalize hard-fail
            return int(e.code) if e.code else 0
        except Exception as e:
            sys.stderr.write(f"ERROR: build failed: {e}\n")
            return 2

    if args.emit_widget:
        try:
            emit_widget(model, spec, args.brand, args.emit_widget, skill_name=SKILL_NAME)
            print(f"Wrote widget data {args.emit_widget}")
        except Exception as e:
            sys.stderr.write(f"ERROR: widget emit failed: {e}\n")
            return 2

    s = model["summary"]
    i = s["item"]
    cur = model["provenance"]["currency"]
    print(f"Built {len(written)} artifact(s) in {args.outdir}/:")
    for p in written:
        print(f"  - {p.name}")
    print(f"Partitions: Block 1={s['block1']}  Block 2={s['block2']}  "
          f"flagged={rmodel.money(s['flagged_spend'], cur)}  "
          f"universe={s['universe']} (scored {s['scored']}, no-benchmark {s['no_benchmark']})")
    print(f"Products:   Block 1={i['block1']}  Block 2={i['block2']}  "
          f"flagged={rmodel.money(i['flagged_spend'], cur)}  "
          f"universe={i['universe']} (scored {i['scored']}, no-benchmark {i['no_benchmark']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
