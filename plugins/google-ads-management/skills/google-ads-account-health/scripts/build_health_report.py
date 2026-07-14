#!/usr/bin/env python3
"""Account-health checks — multi-format deliverable builder (thin CLI).

Reads a findings JSON (schema is authoritative in
`references/account-health-filter.md`) and emits the REDUCED analytical
bundle via the shared render toolkit (`_shared/render`):

  md   — narrative report (provenance, per-check sections, the "top
         structural fixes" ranked list, a full no-row-loss table). Zero deps.
  xlsx — the tunable Controls + Live-checks workbook (needs openpyxl;
         LibreOffice-normalized so it opens in Excel). THIS is the
         interactive surface for this skill — no HTML explorer is emitted:
         five heterogeneous, different-grain checks read poorly as one wide
         interactive table (sanctioned reduced bundle, HM-545).

Plus the skill-specific action_plan.md / renaming.md / pause_list.csv
artifacts (health_artifacts.py) — not part of the generic render toolkit.

All formats share one scoring engine (health_core), so they can never
disagree. The render config lives in health_spec (+ health_xlsx_spec).

Usage:
    python3 build_health_report.py --input findings.json --outdir artifacts \\
        --brand "Acme Corp" --formats md,xlsx

Exit codes: 0 success, 1 usage/validation error, 2 build error.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parents[2]            # .../plugins/google-ads-management
sys.path.insert(0, str(PLUGIN_ROOT / "_shared"))  # the render toolkit + analytics/reconcile
sys.path.insert(0, str(HERE))            # health_core / health_spec / health_artifacts

import health_core as core               # noqa: E402
import health_spec as spec_mod           # noqa: E402
import health_artifacts as artifacts     # noqa: E402
from render import build_bundle, model as rmodel  # noqa: E402

ALLOWED_FORMATS = ("md", "xlsx")   # no "html" — reduced bundle, see module docstring


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the account-health deliverable bundle.")
    ap.add_argument("--input", required=True, help="findings JSON")
    ap.add_argument("--outdir", default="artifacts", help="output directory (default: artifacts)")
    ap.add_argument("--brand", default="", help="client/brand name (used for slug/title if meta omits it)")
    ap.add_argument("--formats", default="md,xlsx",
                    help="comma list of md,xlsx (use '' to emit only the skill-specific artifacts)")
    ap.add_argument("--no-normalize", dest="normalize", action="store_false", default=True,
                    help="skip LibreOffice xlsx normalization (file may need Repair in Excel-for-Mac)")
    ap.add_argument("--no-charts", dest="charts", action="store_false", default=True,
                    help="skip the declared Vega-Lite chart (static SVG in the md)")
    ap.add_argument("--no-artifacts", dest="write_artifacts", action="store_false", default=True,
                    help="skip the action_plan/renaming/pause_list artifacts")
    args = ap.parse_args()

    formats = [f.strip().lower() for f in args.formats.split(",") if f.strip()]
    unknown = [f for f in formats if f not in ALLOWED_FORMATS]
    if unknown:
        sys.stderr.write(f"ERROR: unknown format(s) for this reduced bundle: {', '.join(unknown)} "
                         f"(allowed: {', '.join(ALLOWED_FORMATS)} — no HTML explorer, see module docstring)\n")
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
            "scripts/assemble_findings.py (or the CSV path) instead of writing the JSON by hand.\n")
    model = core.compute_model(findings)

    spec = dict(spec_mod.SPEC)
    if not args.charts:
        spec.pop("charts", None)
    if "xlsx" in formats:
        import health_xlsx_spec as xspec  # stdlib data; openpyxl stays inside render.xlsx
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

    if args.write_artifacts:
        stem = rmodel.stem(model, spec, args.brand)
        try:
            written += artifacts.write_artifacts(model, stem, args.outdir)
        except Exception as e:
            sys.stderr.write(f"ERROR: skill-specific artifacts failed: {e}\n")
            return 2

    s = model["summary"]
    print(f"Built {len(written)} artifact(s) in {args.outdir}/:")
    for p in written:
        print(f"  - {p.name}")
    by_check = ", ".join(f"{model['check_labels'][c]}={s['by_check'][c]['flagged']}/{s['by_check'][c]['universe']}"
                         for c in model["checks"])
    print(f"Total flagged={s['total_flagged']}/{s['universe']}  "
          f"(Critical={s['by_severity']['Critical']} High={s['by_severity']['High']} "
          f"Medium={s['by_severity']['Medium']})")
    print(f"  {by_check}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
