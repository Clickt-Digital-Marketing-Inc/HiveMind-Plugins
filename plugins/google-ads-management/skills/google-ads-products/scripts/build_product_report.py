#!/usr/bin/env python3
"""Product-segments filter — multi-format deliverable builder (thin CLI).

Reads a findings JSON (schema is authoritative in
`references/product-segments-filter.md`) and emits the standard analytical
bundle via the shared render toolkit (`_shared/render`):

  md   — narrative report (provenance, headline, the clean-result framing,
         surge/decline sensitivity, excluded-inactive list, full per-product
         table with status + segment). Zero deps.
  html — a self-contained interactive explorer: surge/decline sliders + zombie
         floors + live sensitivity strips, recomputing in any browser. No
         install, no cloud, no Excel. The interactive primary.
  xlsx — the tunable Controls + Live-products + Sensitivity workbook (needs
         openpyxl; LibreOffice-normalized so it opens in Excel).

It also writes three action WORKLISTS (Zombie / Surging / Declining) unless
--no-worklists. These are PRIORITIZED MANUAL worklists for the Shopping/PMax
listing groups — product-level exclusions are not cleanly Google Ads
Editor-importable, so they are not Editor paste files.

All formats share one classification engine (product_filter_core), so they can
never disagree. The render config lives in product_filter_spec.

Usage:
    python3 build_product_report.py --input findings.json --outdir artifacts \\
        --brand "Acme Corp" --formats md,html,xlsx

Exit codes: 0 success, 1 usage/validation error, 2 build error.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parents[2]            # .../plugins/google-ads-management
sys.path.insert(0, str(HERE))            # product_filter_core / product_filter_spec
sys.path.insert(0, str(PLUGIN_ROOT / "_shared"))                       # the render toolkit
sys.path.insert(0, str(PLUGIN_ROOT / "skills" / "google-ads-foundation" / "scripts"))  # make_editor_csv

import product_filter_core as core       # noqa: E402
import product_filter_spec as spec_mod    # noqa: E402
from render import build_bundle, model as rmodel  # noqa: E402
from widget_emit import emit_widget       # noqa: E402

SKILL_NAME = "google-ads-products"

# segment -> (worklist file suffix, Action text, Reason text)
_WORKLISTS = {
    "Zombie": ("zombie", "Exclude / pause",
               "Spending with zero conversions over 30 days while still in the merchant feed."),
    "Surging": ("surging", "Scale budget / priority",
                "Conversions accelerating versus the previous 14 days."),
    "Declining": ("declining", "Investigate feed / price / stock",
                  "Conversions collapsing versus the previous 14 days."),
}


def _write_worklists(model: dict, outdir: str, stem: str) -> list:
    """Write one action-worklist CSV per segment via the foundation schema.
    Returns the paths written. Honest: these are MANUAL worklists, not Editor
    imports (product-level exclusions are managed in listing groups, not by a
    generic Editor CSV)."""
    import make_editor_csv as mk
    cols = mk.SCHEMAS["product_actions"]
    out = Path(outdir)
    written = []
    for seg, (suffix, action, reason) in _WORKLISTS.items():
        rows = [r for r in model["rows"] if r.get("segment") == seg]
        recs = [{
            "Segment": seg,
            "Product Item ID": r["product_item_id"],
            "Product Title": r["product_title"],
            "Merchant ID": r["merchant_id"],
            "30d Cost": round(r["cost_30d"], 2),
            "Conv 14d": round(r["conversions_14d"], 2),
            "Conv Prev 14d": round(r["conversions_prev14d"], 2),
            "Action": action,
            "Reason": reason,
        } for r in rows]
        path = out / f"{stem}_{suffix}_worklist.csv"
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            for rec in recs:
                w.writerow(mk._row_to_columns(rec, cols))
        written.append((path, len(recs)))
    return written


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the product-segments deliverable bundle.")
    ap.add_argument("--input", required=True, help="findings JSON")
    ap.add_argument("--outdir", default="artifacts", help="output directory (default: artifacts)")
    ap.add_argument("--brand", default="", help="client/brand name (used for slug/title if meta omits it)")
    ap.add_argument("--formats", default="md,html,xlsx",
                    help="comma list of md,html,xlsx (use '' to emit only the widget JSON)")
    ap.add_argument("--no-normalize", dest="normalize", action="store_false", default=True,
                    help="skip LibreOffice xlsx normalization (file may need Repair in Excel-for-Mac)")
    ap.add_argument("--no-charts", dest="charts", action="store_false", default=True,
                    help="skip the declared Vega-Lite charts (static SVGs + live explorer charts)")
    ap.add_argument("--no-worklists", dest="worklists", action="store_false", default=True,
                    help="skip the per-segment action-worklist CSVs")
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
        import product_filter_xlsx_spec as xspec  # stdlib data; openpyxl stays inside render.xlsx
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

    worklists = []
    if formats and args.worklists:
        try:
            stem = rmodel.stem(model, spec, args.brand)
            worklists = _write_worklists(model, args.outdir, stem)
        except Exception as e:
            sys.stderr.write(f"ERROR: worklist write failed: {e}\n")
            return 2

    s = model["summary"]
    cur = model["provenance"]["currency"]
    print(f"Built {len(written)} artifact(s) in {args.outdir}/:")
    for p in written:
        print(f"  - {p.name}")
    for path, n in worklists:
        print(f"  - {path.name}  ({n} row(s))")
    print(f"Zombie={s['zombie']}  Surging={s['surging']}  Declining={s['declining']}  "
          f"wasted={rmodel.money(s['zombie_wasted_cost'], cur)}  "
          f"universe={s['universe']} (scored {s['scored']}, inactive {s['inactive']}, "
          f"no-merchant {s['no_merchant']})")

    # Advisor loop (references/artifact-formats.md#advisor-output-contract): emit
    # (above) -> hero HTML explorer -> these Critical/High/Medium recommendations,
    # every figure citing the model just computed -> offer the worklist CSVs.
    if formats:
        recs = core.recommendations(model)
        print()
        print("Recommendations (Critical -> High -> Medium):")
        if not recs:
            print("  (none — a clean result: no zombie/surging/declining products this run)")
        for r in recs:
            print(f"  [{r['severity']}] {r['action']}")
            print(f"      why: {r['why']}")
            if r.get("examples"):
                print(f"      top: {'; '.join(r['examples'])}")
        if worklists:
            print()
            print("Worklist CSVs offered (prioritized MANUAL worklists — apply in the "
                  "Shopping/PMax listing groups; not a Google Ads Editor import):")
            for path, n in worklists:
                print(f"  - {path.name}  ({n} row(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
