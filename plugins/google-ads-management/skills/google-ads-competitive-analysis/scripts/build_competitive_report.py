#!/usr/bin/env python3
"""Competitive-pressure filter — multi-format deliverable builder (thin CLI).

Reads a findings JSON (schema is authoritative in
`references/competitive-pressure-filter.md`) and emits the standard analytical
bundle via the shared render toolkit (`_shared/render`):

  md   — narrative report (provenance, headline, the 0-flagged-is-clean story,
         sensitivity table, near-misses, competitor concentration, excluded
         campaigns). Zero deps.
  html — a self-contained interactive explorer: sliders + sensitivity strip +
         competitor concentration panel, recomputing live in any browser. No
         install, no cloud, no Excel. The interactive primary.
  xlsx — the tunable Controls + Live-pressure + Snapshot workbook (needs
         openpyxl; LibreOffice-normalized so it opens in Excel).

All formats share one classification engine (competitive_core), so they can
never disagree. The competitive-pressure render config lives in
competitive_spec.

Usage:
    python3 build_competitive_report.py --input findings.json --outdir artifacts \\
        --brand "Acme Corp" --formats md,html
    python3 build_competitive_report.py --input findings.json --outdir artifacts \\
        --formats md,html,xlsx

Exit codes: 0 success, 1 usage/validation error, 2 build error.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parents[2]            # .../plugins/google-ads-management
sys.path.insert(0, str(HERE))            # competitive_core / competitive_spec
sys.path.insert(0, str(PLUGIN_ROOT / "_shared"))  # the render toolkit

import competitive_core as core          # noqa: E402
import competitive_spec as spec_mod      # noqa: E402
from render import build_bundle, model as rmodel  # noqa: E402
from widget_emit import emit_widget      # noqa: E402

SKILL_NAME = "google-ads-competitive-analysis"


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the competitive-pressure filter deliverable bundle.")
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
        import competitive_xlsx_spec as xspec  # stdlib data; openpyxl stays inside render.xlsx
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
    cur = model["provenance"]["currency"]
    print(f"Built {len(written)} artifact(s) in {args.outdir}/:")
    for p in written:
        print(f"  - {p.name}")
    print(f"Rank pressure={s['rank_pressure']}  Budget capped={s['budget_capped']}  "
          f"flagged spend={rmodel.money(s['flagged_cost_this'], cur)}  "
          f"campaigns={s['campaigns']} (scored {s['scored']})  "
          f"competitor rows={s['competitor_rows']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
