#!/usr/bin/env python3
"""Budget & pacing report — multi-format deliverable builder (thin CLI).

Reads a findings JSON (schema authoritative in
`references/budget-pacing-report.md`) and emits the standard analytical bundle
via the shared toolkit (`_shared/render`): md, interactive html, formula xlsx.

Usage:
    python3 build_budget_report.py --input findings.json --outdir artifacts \\
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

import budget_core as core         # noqa: E402
import budget_spec as spec_mod     # noqa: E402
from render import build_bundle, model as rmodel  # noqa: E402
from widget_emit import emit_widget  # noqa: E402

SKILL_NAME = "google-ads-budget-pacing"


def print_advisor(model: dict) -> None:
    """The advisor loop's "recommend" step (google-ads-foundation/references/
    artifact-formats.md): after the bundle is emitted, print the prioritized
    reallocation shortlist, every figure traced to the model just built —
    never re-narrated from raw findings."""
    adv = model["advisor"]
    cur = model["provenance"]["currency"]
    s = model["summary"]
    print()
    print("ADVISOR — reallocation shortlist "
          f"(spend concentration top-3 {s['conc_top3_pct']:.1f}% · HHI {s['conc_hhi']:.1f} · "
          f"{s['off_pace_high_conf']} campaign(s) off-pace at high confidence)")
    print(f"  Fund — Raise candidates, budget-constrained winners (<= +20% per step):")
    if not adv["fund"]:
        print("    None at the current thresholds.")
    else:
        for r in adv["fund"]:
            print(f"    - {r['campaign']}: {r['daily_budget']:,.2f} -> {r['proposed_budget']:,.2f} "
                  f"{cur} — {r['reason']}")
    print(f"  Trim — Kill (3x rule) + over-pacing above target CPA:")
    if not adv["trim"]:
        print("    None at the current thresholds.")
    else:
        for r in adv["trim"]:
            print(f"    - {r['campaign']}: spend {r['cost']:,.2f} {cur} — {r['reason']}")
    print("  Apply via make_editor_csv.py --type budget_changes (fund) / pause_list (trim).")


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the budget & pacing bundle.")
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
    rmodel.print_warnings(rmodel.require_meta_source(model))
    if model["params"].get("monthly_goal"):
        rmodel.print_warnings(rmodel.require_assumptions(model, ["monthly_goal"]))

    spec = dict(spec_mod.SPEC)
    if not args.charts:
        spec.pop("charts", None)  # keeps charts out of the bundle AND the widget emit
    if "xlsx" in formats:
        import budget_xlsx_spec as xspec
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
    cur = model["provenance"]["currency"]
    print(f"Built {len(written)} artifact(s) in {args.outdir}/:")
    for p in written:
        print(f"  - {p.name}")
    print(f"MTD={rmodel.money(s['mtd_spend'], cur)} pace={s['pace_ratio']} ({s['pace_verdict']})  "
          f"Kill={s['kill']} Raise={s['raise_']} Rank={s['rank_limited']} Low={s['low_budget']}")
    if formats:   # nothing to advise about on a widget-only (--emit-widget) run
        print_advisor(model)
    return 0


if __name__ == "__main__":
    sys.exit(main())
