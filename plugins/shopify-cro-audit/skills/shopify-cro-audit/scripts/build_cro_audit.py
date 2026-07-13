#!/usr/bin/env python3
# Copyright (c) 2026 Clickt Digital Marketing Inc. All rights reserved.
"""Build the Shopify CRO audit deliverable bundle from a findings JSON payload.

Emits the interactive **HTML** (primary), a **markdown** record, and the
formula-driven **xlsx** backup — all from one computed model — into a
user-chosen directory. The tool owns the filenames
(`cro-audit_{slug}_{date}.{html,md,xlsx}`); the caller picks only the
directory (`--outdir`). The bundle is also copied to ~/Downloads unless
`--no-downloads` is given. The SKILL.md prompts the user for the directory
at runtime.

Deterministic inputs (the two families COMBINE — GA4 has no MCP and the
Shopify MCP has no session CSVs, so GA4 exports + Shopify MCP pulls are a
legitimate pairing; machine.py owns the per-field source precedence):
  --raw-*  saved Shopify MCP tool results (see references/shopify-pulls.md)
  --csv-*  GA4 / Shopify admin UI exports  (see references/data-intake.md)

The machine layer (machine.py) assembles the payload's entire Step-1
`analytics` block from those inputs and REPLACES the transcribed values at
build time (corrections logged to stderr). Its fraction-unit universes also
feed the Concentration and CVR Signals report blocks, so `--no-machine`
(skip machine compute + merge) skips those panels too — they are computed
from the deterministic inputs, never from the payload.

Usage:
    python3 build_cro_audit.py --input cro-payload.json --outdir ~/Downloads --brand "Acme Corp"
    python3 build_cro_audit.py --input cro-payload.json --outdir ./out --raw-dir ./pulls --csv-dir ./exports
    python3 build_cro_audit.py --machine-only --raw-dir ./pulls
    python3 build_cro_audit.py --check cro-audit_acme_2026-07-12.xlsx   # validate an xlsx

Exit codes: 0 success, 1 usage/validation error, 2 build error.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import audit_model
import audit_html
import audit_md
import concentration as conc_mod
import cvr_signals as cvr_mod
import machine as machine_mod
import manual_csv
import shopify_rows

# Explicit flag -> canonical --csv-dir filename (manual_csv.ADAPTERS keys).
_CSV_FLAGS = (
    ("--csv-landing", "csv_landing", "ga4-landing.csv"),
    ("--csv-funnel", "csv_funnel", "ga4-funnel.csv"),
    ("--csv-device", "csv_device", "ga4-device.csv"),
    ("--csv-channels", "csv_channels", "ga4-channels.csv"),
    ("--csv-new-returning", "csv_new_returning", "ga4-new-returning.csv"),
    ("--csv-conversion", "csv_conversion", "shopify-conversion.csv"),
    ("--csv-sales-product", "csv_sales_product", "shopify-sales-product.csv"),
    ("--csv-traffic-source", "csv_traffic_source", "shopify-traffic-source.csv"),
    ("--csv-shopify-landing", "csv_shopify_landing", "shopify-landing.csv"),
    ("--csv-customers", "csv_customers", "shopify-customers.csv"),
    ("--csv-aov", "csv_aov", "shopify-aov.csv"),
)
# Explicit flag -> --raw-dir key (file = key + ".json"; CONTRACTS §4).
# orders / products are shape-pin/optional inputs: loaded + validated here,
# never fed to machine.py (which ignores them by design).
_RAW_FLAGS = (
    ("--raw-shop-info", "raw_shop_info", "shop_info"),
    ("--raw-funnel", "raw_funnel", "analytics_funnel"),
    ("--raw-device", "raw_device", "analytics_device"),
    ("--raw-referrer", "raw_referrer", "analytics_referrer"),
    ("--raw-landing", "raw_landing", "analytics_landing"),
    ("--raw-products", "raw_products", "analytics_products"),
    ("--raw-totals", "raw_totals", "analytics_totals"),
    ("--raw-customers", "raw_customers", "analytics_customers"),
    ("--raw-orders", "raw_orders", "orders"),
    ("--raw-products-catalog", "raw_products_catalog", "products"),
)
_OPTIONAL_RAW_KEYS = ("orders", "products")


def _resolve_paths(args, flags, dir_arg, suffix: str) -> dict:
    """{canonical key: path} from explicit flags (win) + the dir convenience
    (missing files skipped with a stderr note). Deterministic order."""
    paths: dict[str, str] = {}
    for _flag, attr, key in flags:
        v = getattr(args, attr)
        if v:
            paths[key] = str(Path(v).expanduser())
    if dir_arg:
        d = Path(dir_arg).expanduser()
        for _flag, _attr, key in flags:
            if key in paths:
                continue
            p = d / (key if key.endswith(".csv") else key + suffix)
            if p.is_file():
                paths[key] = str(p)
            else:
                sys.stderr.write(f"note: {p} not found — {key} input skipped.\n")
    return paths


def _load_csv_inputs(csv_paths: dict) -> dict:
    """Parse each export through its manual_csv adapter -> the
    machine.compute_machine inputs['csv'] mapping {filename: (data, meta)}.
    Sorted iteration (deterministic); a bad file raises ManualCsvError loudly."""
    out: dict = {}
    for key in sorted(csv_paths):
        out[key] = manual_csv.ADAPTERS[key](csv_paths[key])
    return out


def _cvr_funnel(funnel_u: dict | None) -> dict | None:
    """Fraction funnel universe -> the cvr_signals site-totals row
    ({name, sessions, conversions?, cvr?} — the universe's purchase_sessions
    key is the conversions count; counts win over the shipped rate)."""
    if not funnel_u:
        return None
    row: dict = {"name": "site", "sessions": funnel_u.get("sessions", 0)}
    if funnel_u.get("purchase_sessions") is not None:
        row["conversions"] = funnel_u["purchase_sessions"]
    if funnel_u.get("cvr") is not None:
        row["cvr"] = funnel_u["cvr"]
    return row


def _report_blocks(machine: dict | None) -> tuple[dict | None, dict | None]:
    """(concentration, cvr_signals) from the machine assembly's full
    fraction-unit universes (machine.py's designed hand-off — full-universe
    math before any bounded embed). None machine -> (None, None)."""
    if machine is None:
        return None, None
    U = machine.get("universes") or {}
    windows = machine.get("windows") or {}
    stamps = machine.get("stamps") or {}
    conc = conc_mod.compute_concentration(
        product_rows=U.get("products"), page_rows=U.get("pages"),
        channel_rows=U.get("channels"), windows=windows,
        files=stamps or None)
    cvr = cvr_mod.compute_cvr_signals(
        funnel=_cvr_funnel(U.get("funnel")), device_rows=U.get("device"),
        channel_rows=U.get("channels"), nvr=U.get("nvr"),
        page_rows=U.get("pages"),
        window=windows.get("funnel") or windows.get("default") or None)
    return conc, cvr


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Build the Shopify CRO audit bundle (html + md + xlsx).")
    ap.add_argument("--input", help="findings JSON path (CRO audit payload)")
    ap.add_argument("--outdir", default=".", help="output directory (default: current dir)")
    ap.add_argument("--brand", help="client/brand name override (leads the report)")
    ap.add_argument("--formats", default="html,md,xlsx",
                    help="comma list of html,md,xlsx (default: all three)")
    ap.add_argument("--no-animate", action="store_true",
                    help="build the HTML without GSAP motion")
    for flag, _attr, key in _RAW_FLAGS:
        ap.add_argument(flag, help=f"saved Shopify MCP result JSON ({key}.json)")
    ap.add_argument("--raw-dir", help="directory holding shop_info.json / analytics_funnel.json / "
                                      "analytics_device.json / analytics_referrer.json / "
                                      "analytics_landing.json / analytics_products.json / "
                                      "analytics_totals.json / analytics_customers.json / "
                                      "orders.json / products.json (missing files skipped)")
    for flag, _attr, key in _CSV_FLAGS:
        ap.add_argument(flag, help=f"GA4/Shopify UI export ({key})")
    ap.add_argument("--csv-dir", help="directory holding the canonical ga4-*.csv / shopify-*.csv "
                                      "exports (missing files skipped; combines with --raw-*)")
    ap.add_argument("--no-machine", action="store_true",
                    help="skip the machine layer (no analytics assembly, no merge — "
                         "the Concentration / CVR Signals panels are skipped too)")
    ap.add_argument("--machine-only", action="store_true",
                    help="print the {machine, cvr_signals, concentration} JSON and exit "
                         "(no findings payload needed)")
    ap.add_argument("--no-downloads", action="store_true",
                    help="skip the courtesy copy of the bundle to ~/Downloads")
    ap.add_argument("--check", metavar="XLSX",
                    help="structurally validate an existing xlsx and exit")
    args = ap.parse_args()

    # --check delegates to the workbook's own quality gate.
    if args.check:
        try:
            import build_cro_workbook  # lazy: exits 2 at import when openpyxl missing
        except SystemExit:
            return 2
        return build_cro_workbook.check(Path(args.check).expanduser())

    if not args.input and not args.machine_only:
        sys.stderr.write("ERROR: --input cro-payload.json is required "
                         "(or use --check / --machine-only).\n")
        return 1

    payload: dict = {}
    if args.input:
        input_path = Path(args.input).expanduser()
        if not input_path.is_file():
            sys.stderr.write(f"ERROR: input not found: {input_path}\n")
            return 1
        try:
            payload = json.loads(input_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            sys.stderr.write(f"ERROR: {args.input} is not valid JSON: {e}\n")
            return 1

    # Explicit input-file flags are strict: a named file must exist and parse.
    for flag, attr, _key in _CSV_FLAGS + _RAW_FLAGS:
        val = getattr(args, attr)
        if val and not Path(val).expanduser().is_file():
            sys.stderr.write(f"ERROR: {flag} file not found: {val}\n")
            return 1
    for flag, val in (("--raw-dir", args.raw_dir), ("--csv-dir", args.csv_dir)):
        if val and not Path(val).expanduser().is_dir():
            sys.stderr.write(f"ERROR: {flag} not found or not a directory: {val}\n")
            return 1

    # ---- load the deterministic inputs (csv + raw legitimately combine) -----
    machine = conc = cvr = None
    try:
        csv_paths = _resolve_paths(args, _CSV_FLAGS, args.csv_dir, ".csv")
        raw_paths = _resolve_paths(args, _RAW_FLAGS, args.raw_dir, ".json")
        # orders/products: optional shape-pin inputs — validate loudly, report,
        # and keep them OUT of the machine inputs (machine.py ignores them).
        for key, loader, noun in (("orders", shopify_rows.load_orders, "orders"),
                                  ("products", shopify_rows.load_products,
                                   "products")):
            p = raw_paths.pop(key, None)
            if p:
                n = len(loader(p))
                sys.stderr.write(f"note: {Path(p).name} — {n} {noun} loaded "
                                 f"(shape-pin input; not used in computed "
                                 f"blocks).\n")
        csv_in = _load_csv_inputs(csv_paths)
        if (csv_in or raw_paths) and not args.no_machine:
            machine = machine_mod.compute_machine(
                {"csv": csv_in, "raw": raw_paths})
        conc, cvr = _report_blocks(machine)
    except (shopify_rows.RawResultError, manual_csv.ManualCsvError,
            machine_mod.MachineError) as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return 1

    if args.machine_only:
        if machine is None:
            sys.stderr.write("ERROR: --machine-only needs --raw-* or --csv-* "
                             "analytics inputs (and not --no-machine).\n")
            return 1
        print(json.dumps({"machine": machine, "cvr_signals": cvr,
                          "concentration": conc},
                         indent=2, ensure_ascii=False))
        return 0

    # ---- machine merge: computed analytics REPLACE the transcribed values ---
    merged, machine_block, mlog = machine_mod.merge_into_payload(payload, machine)
    for line in mlog:
        sys.stderr.write(line + "\n")

    brand = args.brand or ""
    model = audit_model.compute_model(merged, brand=brand, concentration=conc,
                                      cvr_signals=cvr, machine=machine_block)
    stem = audit_model.stem(model, brand)
    outdir = Path(args.outdir).expanduser()
    outdir.mkdir(parents=True, exist_ok=True)

    formats = [f.strip().lower() for f in args.formats.split(",") if f.strip()]
    written: dict[str, str] = {}

    if "html" in formats:
        p = outdir / f"{stem}.html"
        audit_html.build_html(model, p, animate=not args.no_animate)
        written["html"] = str(p.resolve())

    if "md" in formats:
        p = outdir / f"{stem}.md"
        audit_md.build_markdown(model, p)
        written["md"] = str(p.resolve())

    if "xlsx" in formats:
        try:
            import build_cro_workbook  # lazy: md/html need no openpyxl
        except SystemExit:
            sys.stderr.write("WARNING: openpyxl missing — skipped the xlsx backup "
                             "(install with: python3 -m pip install --user "
                             "'openpyxl>=3.1').\n")
        else:
            p = outdir / f"{stem}.xlsx"
            try:
                wb = build_cro_workbook.build(merged, concentration=conc,
                                              cvr_signals=cvr)
                wb.save(p)
            except Exception as e:  # noqa: BLE001 — exit 2 per contract
                sys.stderr.write(f"ERROR: xlsx build failed: {e}\n")
                return 2
            if build_cro_workbook.check(p) == 0:
                written["xlsx"] = str(p.resolve())
            else:
                sys.stderr.write("ERROR: xlsx quality-gate failed.\n")
                return 2

    # courtesy copy of the bundle to ~/Downloads (skippable; no-op when the
    # outdir already IS ~/Downloads or the folder does not exist)
    copies: list[str] = []
    if written and not args.no_downloads:
        downloads = Path.home() / "Downloads"
        if downloads.is_dir() and downloads.resolve() != outdir.resolve():
            for fmt in ("html", "md", "xlsx"):
                if fmt in written:
                    src = Path(written[fmt])
                    dst = downloads / src.name
                    shutil.copy2(src, dst)
                    copies.append(str(dst))

    # human-readable summary
    H = model["health"]
    S = model["summary"]
    M = model["meta"]
    score_disp = "n/a" if H["score"] is None else H["score"]
    grade_disp = H["grade"] if H["grade"] else "n/a"
    print(f"Funnel Health: {score_disp} / {H['max']} — Grade {grade_disp} "
          f"({S['n_run']} run / {S['n_partial']} partial / "
          f"{S['n_not_run']} not run of {M['n_steps']} steps)")
    print(f"Findings: {M['n_findings']} "
          f"({S['crit']} critical · {S['high']} high · {S['med']} medium · "
          f"{S['low']} low)")
    if machine_block:
        print(f"Machine layer: {len(machine_block.get('applied') or [])} "
              f"analytics fields machine-computed · "
              f"{len(machine_block.get('corrected') or [])} correction(s)")
    for fmt in ("html", "md", "xlsx"):
        if fmt in written:
            label = "→ open this" if fmt == "html" else ""
            print(f"  {fmt:4} {written[fmt]} {label}".rstrip())
    if copies:
        print("Copied to ~/Downloads: "
              + ", ".join(Path(c).name for c in copies))

    # machine-readable final line (SKILL.md parses this)
    print(json.dumps({"outputs": written, "health": H["score"],
                      "grade": H["grade"], "findings": M["n_findings"],
                      "machine_corrections":
                          len(machine_block["corrected"]) if machine_block
                          else 0},
                     separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
