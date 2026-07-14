#!/usr/bin/env python3
"""Audience & Targeting advisor — reduced-bundle deliverable builder (thin CLI).

Reads applied-audience findings (from the MCP path's assemble_findings.py, or
straight from a Google Ads UI "Audiences" CSV export) and, optionally, a
first-party readiness CSV (Customer Match / Enhanced Conversions / Consent
Mode v2 / CMP — always user-supplied, never from the MCP), then emits the
skill's REDUCED bundle via the shared render toolkit (_shared/render):

  md   — narrative report (provenance, headline, the priority breakdown, the
         first-party readiness table, the clean-result framing, full
         per-audience table with status/flags/score/priority). Zero deps.
  xlsx — the tunable Controls + Audiences + First-Party Readiness workbook
         (needs openpyxl; LibreOffice-normalized so it opens in Excel).

No HTML explorer — see references/audience-targeting-filter.md for why this
skill's declared/emitted format set is `["md", "xlsx"]` (a deliberately
reduced bundle, not a thin explorer manufactured to claim parity).

It also writes a bid_adjustments Editor CSV for audiences flagged
`wasted_spend` or `high_cpa` (a directionally-justified -20% reduction)
unless --no-worklist. Audiences flagged only paused/no-bid-adjustment/
zero-conversions/low-CTR are NOT auto-written to a CSV — no defensible number
can be assigned without knowing which remarketing tier the list represents
(see SKILL.md's honesty notes); those stay manual recommendations in the
report and the advisor's narration.

Usage:
    # MCP path (applied audiences) + optional first-party CSV
    python3 build_audience_report.py --input findings.json \\
        --first-party-csv first_party.csv --outdir artifacts --brand "Acme Corp"

    # CSV-only path (no MCP)
    python3 build_audience_report.py --audiences-csv audiences.csv \\
        --first-party-csv first_party.csv \\
        --client-name "Acme Corp" --account-id 123-456-7890 --currency CAD \\
        --window-30d "2026-06-06 to 2026-07-05" --outdir artifacts --brand "Acme Corp"

Exit codes: 0 success, 1 usage/validation error, 2 build error.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parents[2]            # .../plugins/google-ads-management
sys.path.insert(0, str(HERE))            # audience_core / audience_spec / audience_csv
sys.path.insert(0, str(PLUGIN_ROOT / "_shared"))                       # the render toolkit
sys.path.insert(0, str(PLUGIN_ROOT / "skills" / "google-ads-foundation" / "scripts"))  # make_editor_csv

import audience_core as core       # noqa: E402
import audience_spec as spec_mod   # noqa: E402
import audience_csv as csvmod      # noqa: E402
from render import build_bundle, model as rmodel  # noqa: E402

SKILL_NAME = "google-ads-audience-targeting"
# Reduced bundle — no HTML explorer. See references/audience-targeting-filter.md.
ALLOWED_FORMATS = ("md", "xlsx")


def _load_input(args) -> dict:
    if args.input and args.audiences_csv:
        sys.stderr.write("ERROR: pass exactly one of --input or --audiences-csv, not both\n")
        sys.exit(1)
    if args.input:
        try:
            return core.load_findings(args.input)
        except core.FindingsError as e:
            sys.stderr.write(f"ERROR: {e}\n")
            sys.exit(1)
    if args.audiences_csv:
        missing = [f for f in ("client_name", "account_id", "currency", "window_30d")
                  if not getattr(args, f)]
        if missing:
            sys.stderr.write("ERROR: --audiences-csv requires --" +
                             ", --".join(m.replace("_", "-") for m in missing) + "\n")
            sys.exit(1)
        meta = {"client_name": args.client_name, "account_id": args.account_id,
                "currency": args.currency, "window_30d": args.window_30d,
                "generated": args.generated or datetime.date.today().isoformat()}
        try:
            findings = csvmod.assemble_audiences_from_csv(args.audiences_csv, meta)
        except csvmod.CsvInputError as e:
            sys.stderr.write(f"ERROR: {e}\n")
            sys.exit(1)
        try:
            return core.verify_findings(findings)
        except core.FindingsError as e:
            sys.stderr.write(f"ERROR: {e}\n")
            sys.exit(1)
    sys.stderr.write("ERROR: pass --input (MCP findings JSON) or --audiences-csv (UI export)\n")
    sys.exit(1)


def _merge_first_party(findings: dict, first_party_csv: str | None) -> dict:
    if first_party_csv:
        meta = {"client_name": findings["meta"].get("client_name", ""),
                "account_id": findings["meta"].get("account_id", ""),
                "currency": findings["meta"].get("currency", ""),
                "generated": findings["meta"].get("generated", "")}
        try:
            fp_findings = csvmod.assemble_first_party_from_csv(first_party_csv, meta)
        except csvmod.CsvInputError as e:
            sys.stderr.write(f"ERROR: {e}\n")
            sys.exit(1)
        findings["first_party"] = fp_findings["first_party"]
        findings["meta"].setdefault("reconciliation", {})
        findings["meta"]["reconciliation"]["first_party"] = fp_findings["meta"]["reconciliation"]["first_party"]
        findings["meta"]["first_party_source"] = "user_csv"
    else:
        findings.setdefault("first_party", [])
        findings["meta"].setdefault("first_party_source", "not_supplied")
    return findings


def _write_bid_adjustments(model: dict, outdir: str, stem: str):
    import make_editor_csv as mk
    cols = mk.SCHEMAS["bid_adjustments"]
    recs = []
    for r in model["rows"]:
        if r["status"] != "scored":
            continue
        flags = set(r.get("flags") or [])
        if not (flags & {"wasted_spend", "high_cpa"}):
            continue
        recs.append({
            "Campaign": r["campaign"], "Ad Group": r["ad_group"], "Keyword": "", "Match Type": "",
            "Max CPC": "", "Bid Adjustment": "-20%", "Level": f"Audience: {r['list_name']}",
        })
    path = Path(outdir) / f"{stem}_bid_adjustments.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for rec in recs:
            w.writerow(mk._row_to_columns(rec, cols))
    return path, len(recs)


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the audience-targeting advisor's reduced bundle.")
    ap.add_argument("--input", default=None, help="applied-audience findings JSON (MCP path)")
    ap.add_argument("--audiences-csv", default=None, help="Google Ads UI Audiences report export (CSV path)")
    ap.add_argument("--client-name", default=None, help="required with --audiences-csv")
    ap.add_argument("--account-id", default=None, help="required with --audiences-csv")
    ap.add_argument("--currency", default=None, help="required with --audiences-csv")
    ap.add_argument("--window-30d", default=None, help="required with --audiences-csv")
    ap.add_argument("--generated", default=None, help="report date (YYYY-MM-DD); defaults to today")
    ap.add_argument("--first-party-csv", default=None,
                    help="first-party readiness CSV (Customer Match / Enhanced Conversions / "
                         "Consent Mode v2 / CMP) — always user-supplied, never from the MCP")
    ap.add_argument("--outdir", default="artifacts", help="output directory (default: artifacts)")
    ap.add_argument("--brand", default="", help="client/brand name (used for slug/title if meta omits it)")
    ap.add_argument("--formats", default="md,xlsx", help="comma list of md,xlsx (reduced bundle — no html)")
    ap.add_argument("--no-normalize", dest="normalize", action="store_false", default=True,
                    help="skip LibreOffice xlsx normalization (file may need Repair in Excel-for-Mac)")
    ap.add_argument("--no-worklist", dest="worklist", action="store_false", default=True,
                    help="skip the bid_adjustments Editor CSV")
    args = ap.parse_args()

    formats = [f.strip().lower() for f in args.formats.split(",") if f.strip()]
    unknown = [f for f in formats if f not in ALLOWED_FORMATS]
    if unknown:
        sys.stderr.write(
            f"ERROR: unsupported format(s) for this reduced-bundle skill: {', '.join(unknown)} "
            f"(declared formats: {', '.join(ALLOWED_FORMATS)} — no HTML explorer; see "
            "references/audience-targeting-filter.md)\n")
        return 1

    findings = _load_input(args)
    findings = _merge_first_party(findings, args.first_party_csv)
    if not (findings.get("meta") or {}).get("reconciliation", {}).get("audiences"):
        sys.stderr.write(
            "WARN: findings carry no reconciliation totals for 'audiences' — data transcription is "
            "UNVERIFIED. Assemble findings from the saved raw pulls with scripts/assemble_findings.py "
            "(or the CSV path) instead of writing the JSON by hand.\n")

    model = core.compute_model(findings)

    spec = dict(spec_mod.SPEC)
    if "xlsx" in formats:
        import audience_xlsx_spec as xspec  # stdlib data; openpyxl stays inside render.xlsx
        spec["xlsx"] = xspec.XLSX

    written = []
    if formats:
        try:
            written = build_bundle(model, spec, args.outdir, formats=formats, brand=args.brand,
                                   normalize=args.normalize, charts=False)
        except SystemExit as e:               # xlsx normalize hard-fail
            return int(e.code) if e.code else 0
        except Exception as e:
            sys.stderr.write(f"ERROR: build failed: {e}\n")
            return 2

    worklist_path, worklist_n = None, 0
    if formats and args.worklist:
        try:
            stem = rmodel.stem(model, spec, args.brand)
            worklist_path, worklist_n = _write_bid_adjustments(model, args.outdir, stem)
        except Exception as e:
            sys.stderr.write(f"ERROR: bid-adjustments CSV write failed: {e}\n")
            return 2

    s = model["summary"]
    cur = model["provenance"]["currency"]
    print(f"Built {len(written)} artifact(s) in {args.outdir}/:")
    for p in written:
        print(f"  - {p.name}")
    if worklist_path:
        print(f"  - {worklist_path.name}  ({worklist_n} row(s))")
    print(f"Applied audiences: {s['total_audiences']} (scored {s['scored']}, excluded {s['excluded']}) — "
          f"Critical={s['critical']} High={s['high']} Medium={s['medium']} Clean={s['clean']}")
    print(f"Flagged spend: {rmodel.money(s['flagged_cost'], cur)}  "
          f"Spend concentration (top-3 share): {s['spend_top3_share'] * 100:.1f}%  "
          f"(HHI {s['spend_hhi']:.0f}, effective-N {s['spend_effective_n']:.2f})")
    print(f"First-party readiness: {s['first_party_total']} item(s) — gaps {s['first_party_gaps']} "
          f"(Critical={s['first_party_critical']} High={s['first_party_high']} "
          f"Medium={s['first_party_medium']}), OK {s['first_party_ok']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
