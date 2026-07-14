#!/usr/bin/env python3
"""Quality Score forensics report — multi-format deliverable builder (thin CLI).

Reads a findings JSON (schema authoritative in
`references/quality-score-report.md`) and emits the standard analytical bundle
via the shared toolkit (`_shared/render`): md, interactive html, formula xlsx.

Usage:
    python3 build_qs_report.py --input findings.json --outdir artifacts \\
        --brand "Acme Corp" --formats md,html,xlsx

Exit codes: 0 success, 1 usage/validation error, 2 build error.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PLUGIN_ROOT / "_shared"))

import qs_core as core            # noqa: E402
import qs_spec as spec_mod        # noqa: E402
from render import build_bundle   # noqa: E402
from widget_emit import emit_widget  # noqa: E402

SKILL_NAME = "google-ads-quality-score"


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the Quality Score forensics bundle.")
    ap.add_argument("--input", required=True)
    ap.add_argument("--outdir", default="artifacts")
    ap.add_argument("--brand", default="")
    ap.add_argument("--formats", default="md,html,xlsx",
                    help="comma list of md,html,xlsx (use '' to emit only the widget JSON)")
    ap.add_argument("--no-normalize", dest="normalize", action="store_false", default=True)
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
        import qs_xlsx_spec as xspec
        spec["xlsx"] = xspec.XLSX

    written = []
    if formats:
        try:
            written = build_bundle(model, spec, args.outdir, formats=formats,
                                   brand=args.brand, normalize=args.normalize,
                                   charts=args.charts)
        except SystemExit as e:
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
    print(f"Built {len(written)} artifact(s) in {args.outdir}/:")
    for p in written:
        print(f"  - {p.name}")
    print(f"scored={s['scored']} avg_qs={s['avg_qs']} in_scope={s['in_scope']}  "
          f"LP={s['lp']} AdRel={s['ad_rel']} ExpCTR={s['exp_ctr']} Critical={s['critical']} "
          f"pause={s['pause_candidates']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
