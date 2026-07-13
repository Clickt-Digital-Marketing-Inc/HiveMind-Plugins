#!/usr/bin/env python3
# Copyright (c) 2026 Clickt Digital Marketing Inc. All rights reserved.
"""Build the Meta Ads audit deliverable bundle from a findings JSON payload.

Emits the interactive **HTML** (primary), a **markdown** record, and the
formula-driven **xlsx** backup — all from one computed model — into a
user-chosen directory. The tool owns the filenames
(`meta-audit_{slug}_{date}.{html,md,xlsx}`); the caller picks only the
directory (`--outdir`). The bundle is also copied to ~/Downloads unless
`--no-downloads` is given. The SKILL.md prompts the user for the directory
at runtime.

Raw inputs (either family, never both):
  --raw-*  saved Meta Ads MCP tool results (see references/raw-pulls.md)
  --csv-*  Meta Ads Manager UI exports (see references/manual-exports.md)

Usage:
    python3 build_audit.py --input findings.json --outdir ~/Downloads --brand "Acme Corp"
    python3 build_audit.py --input findings.json --outdir ./out --raw-dir ./pulls
    python3 build_audit.py --prescore-only --raw-dir ./pulls --business-model "Lead Gen"
    python3 build_audit.py --check meta-audit_acme_2026-06-24.xlsx   # validate an xlsx

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
import creative_signals as cs_mod
import manual_csv
import meta_rows
import prescore as prescore_mod

# --raw-dir / --csv-dir convenience filenames (missing files are skipped).
_RAW_DIR_NAMES = {"campaigns": "campaigns.json", "adsets": "adsets.json",
                  "ads": "ads.json", "adsets_7d": "adsets_7d.json",
                  "datasets": "datasets.json",
                  "dataset_quality": "dataset_quality.json"}
_CSV_DIR_NAMES = {"campaigns": "campaigns.csv", "adsets": "adsets.csv",
                  "ads": "ads.csv"}
# meta_rows.load_rows level per raw entity input (adsets_7d is an adset pull).
_RAW_LEVELS = {"campaigns": "campaign", "adsets": "adset", "ads": "ad",
               "adsets_7d": "adset"}
_CSV_ADAPTERS = {"campaigns": manual_csv.campaigns_rows,
                 "adsets": manual_csv.adsets_rows,
                 "ads": manual_csv.ads_rows}
# input key -> concentration windows= dimension key (CSV path labels).
_CSV_WINDOW_DIMS = {"campaigns": "campaigns", "adsets": "ad_sets", "ads": "ads"}
_ENTITY_KEYS = ("campaigns", "adsets", "ads")


def _load_input_rows(args) -> tuple[dict, dict, dict] | None:
    """Resolve and parse the raw-MCP files or manual UI CSVs (mutually
    exclusive; the caller validates) into normalized canonical rows shared by
    the Concentration report, the Creative Signals block and the pre-scorer.
    Explicit flags win over the dir convenience. Returns
    (rows, files, windows) or None when nothing was given.

    rows carries all six input keys (None where absent): campaigns / adsets /
    ads / adsets_7d entity row lists plus datasets (deduped list) and
    dataset_quality ({channel: [events]}) — the latter two raw-path only.
    windows carries per-dimension labels only on the CSV path (each file's own
    date range); the raw path's labels come from findings meta. CR-07's
    window mode needs no plumbing here — prescore derives window_days from
    the rows' own date_start/date_stop."""
    use_csv = any([args.csv_campaigns, args.csv_adsets, args.csv_ads,
                   args.csv_dir])
    if use_csv:
        paths = {"campaigns": args.csv_campaigns, "adsets": args.csv_adsets,
                 "ads": args.csv_ads}
    else:
        paths = {"campaigns": args.raw_campaigns, "adsets": args.raw_adsets,
                 "ads": args.raw_ads, "adsets_7d": args.raw_adsets_7d,
                 "datasets": args.raw_datasets,
                 "dataset_quality": args.raw_dataset_quality}
    dir_arg = args.csv_dir if use_csv else args.raw_dir
    dir_names = _CSV_DIR_NAMES if use_csv else _RAW_DIR_NAMES
    if dir_arg:
        d = Path(dir_arg).expanduser()
        for key, fname in dir_names.items():
            if paths[key]:
                continue
            p = d / fname
            if p.is_file():
                paths[key] = str(p)
            else:
                sys.stderr.write(f"note: {p} not found — {key} input skipped.\n")
    if not any(paths.values()):
        return None
    rows: dict[str, object] = {k: None for k in _RAW_DIR_NAMES}
    files: dict[str, dict] = {}
    windows: dict[str, str] = {}
    for key in sorted(paths):
        path = paths[key]
        if not path:
            continue
        if use_csv:
            rows[key], fmeta = _CSV_ADAPTERS[key](path)
            if fmeta.get("window"):
                windows[_CSV_WINDOW_DIMS[key]] = fmeta["window"]
        elif key == "datasets":
            rows[key] = meta_rows.load_datasets(path)
        elif key == "dataset_quality":
            rows[key] = meta_rows.load_dataset_quality(path)
        else:
            rows[key] = meta_rows.load_rows(path, level=_RAW_LEVELS[key])
        files[key] = meta_rows.file_stamp(path)
    if windows.get("campaigns"):  # objectives dimension shares the campaigns pull
        windows.setdefault("objectives", windows["campaigns"])
    return rows, files, windows


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Build the Meta Ads audit bundle (html + md + xlsx).")
    ap.add_argument("--input", help="findings JSON path (audit payload)")
    ap.add_argument("--outdir", default=".", help="output directory (default: current dir)")
    ap.add_argument("--brand", help="client/brand name override (leads the report)")
    ap.add_argument("--formats", default="html,md,xlsx",
                    help="comma list of html,md,xlsx (default: all three)")
    ap.add_argument("--no-animate", action="store_true",
                    help="build the HTML without GSAP motion")
    ap.add_argument("--raw-campaigns", help="saved campaign-level ads_get_ad_entities result JSON")
    ap.add_argument("--raw-adsets", help="saved adset-level ads_get_ad_entities result JSON")
    ap.add_argument("--raw-ads", help="saved ad-level ads_get_ad_entities result JSON")
    ap.add_argument("--raw-adsets-7d", help="saved 7-day adset-level pull (unlocks CR-07 true bands)")
    ap.add_argument("--raw-datasets", help="saved ads_get_datasets result JSON (DI-01)")
    ap.add_argument("--raw-dataset-quality", help="saved ads_get_dataset_quality result JSON (DI-04)")
    ap.add_argument("--raw-dir", help="directory holding campaigns.json / adsets.json / ads.json / "
                                      "adsets_7d.json / datasets.json / dataset_quality.json "
                                      "(missing files skipped)")
    ap.add_argument("--csv-campaigns", help="Meta Ads Manager Campaigns export .csv (no-MCP path)")
    ap.add_argument("--csv-adsets", help="Meta Ads Manager Ad sets export .csv (no-MCP path)")
    ap.add_argument("--csv-ads", help="Meta Ads Manager Ads export .csv (no-MCP path)")
    ap.add_argument("--csv-dir", help="directory holding campaigns.csv / adsets.csv / ads.csv "
                                      "UI exports (missing files skipped)")
    ap.add_argument("--no-prescore", action="store_true",
                    help="skip the deterministic pre-scorer (machine-scored checks)")
    ap.add_argument("--prescore-only", action="store_true",
                    help="print the machine-scored results JSON and exit (no findings needed)")
    ap.add_argument("--business-model", choices=["Lead Gen", "Ecommerce"],
                    help="benchmark band for the pre-scorer (else findings meta wins)")
    ap.add_argument("--no-downloads", action="store_true",
                    help="skip the courtesy copy of the bundle to ~/Downloads")
    ap.add_argument("--check", metavar="XLSX",
                    help="structurally validate an existing xlsx and exit")
    args = ap.parse_args()

    # --check delegates to the workbook's own quality gate.
    if args.check:
        try:
            import build_audit_xlsx  # lazy: exits 2 at import when openpyxl missing
        except SystemExit:
            return 2
        return build_audit_xlsx.check(Path(args.check).expanduser())

    if not args.input and not args.prescore_only:
        sys.stderr.write("ERROR: --input findings.json is required "
                         "(or use --check / --prescore-only).\n")
        return 1

    findings: dict = {}
    if args.input:
        input_path = Path(args.input)
        if not input_path.is_file():
            sys.stderr.write(f"ERROR: input not found: {input_path}\n")
            return 1
        try:
            findings = json.loads(input_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            sys.stderr.write(f"ERROR: {args.input} is not valid JSON: {e}\n")
            return 1

    # Explicit input-file flags are strict: a named file must exist and parse.
    for flag, val in (("--raw-campaigns", args.raw_campaigns),
                      ("--raw-adsets", args.raw_adsets),
                      ("--raw-ads", args.raw_ads),
                      ("--raw-adsets-7d", args.raw_adsets_7d),
                      ("--raw-datasets", args.raw_datasets),
                      ("--raw-dataset-quality", args.raw_dataset_quality),
                      ("--csv-campaigns", args.csv_campaigns),
                      ("--csv-adsets", args.csv_adsets),
                      ("--csv-ads", args.csv_ads)):
        if val and not Path(val).is_file():
            sys.stderr.write(f"ERROR: {flag} file not found: {val}\n")
            return 1
    raw_given = any([args.raw_campaigns, args.raw_adsets, args.raw_ads,
                     args.raw_adsets_7d, args.raw_datasets,
                     args.raw_dataset_quality, args.raw_dir])
    csv_given = any([args.csv_campaigns, args.csv_adsets, args.csv_ads,
                     args.csv_dir])
    if raw_given and csv_given:
        sys.stderr.write("ERROR: use either --raw-* (MCP result files) or "
                         "--csv-* (UI exports), not both.\n")
        return 1

    meta = findings.get("meta", {}) or {}
    conc = cs = pres = None
    try:
        loaded = _load_input_rows(args)
    except (meta_rows.RawResultError, manual_csv.ManualCsvError) as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return 1
    if loaded:
        rows, files, windows = loaded
        if not csv_given:  # raw path: window labels come from findings meta
            wmeta = dict(meta.get("windows", {}) or {})
            windows = {k: wmeta[k] for k in ("structure", "creative")
                       if wmeta.get(k)}
        if any(rows[k] is not None for k in _ENTITY_KEYS):
            conc = conc_mod.compute_concentration(
                campaign_rows=rows["campaigns"], adset_rows=rows["adsets"],
                ad_rows=rows["ads"], windows=windows or None, files=files)
            if rows["ads"] is not None:
                cs = cs_mod.compute_creative_signals(
                    rows["ads"], rows["adsets"],
                    ref_date=meta.get("generated_for_date") or None)
        if not args.no_prescore:
            bm = args.business_model or meta.get("business_model", "")
            pres = prescore_mod.compute_prescore(
                campaign_rows=rows["campaigns"], adset_rows=rows["adsets"],
                ad_rows=rows["ads"], adset7_rows=rows["adsets_7d"],
                datasets=rows["datasets"],
                dataset_quality=rows["dataset_quality"],
                business_model=bm,
                generated_for_date=meta.get("generated_for_date") or None,
                creative_signals=cs)

    if args.prescore_only:
        if pres is None:
            sys.stderr.write("ERROR: --prescore-only needs --raw-* or --csv-* "
                             "inputs (and not --no-prescore).\n")
            return 1
        print(json.dumps(pres, indent=2, ensure_ascii=False))
        return 0

    findings, pres_block, plog = prescore_mod.merge_into_findings(findings, pres)
    for line in plog:
        sys.stderr.write(line + "\n")

    brand = args.brand or ""
    model = audit_model.compute_model(findings, brand=brand, concentration=conc,
                                      prescore=pres_block, creative_signals=cs)
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
            import build_audit_xlsx  # lazy: md/html need no openpyxl
        except SystemExit:
            sys.stderr.write("WARNING: openpyxl missing — skipped the xlsx backup "
                             "(install with: python3 -m pip install --user "
                             "'openpyxl>=3.1').\n")
        else:
            p = outdir / f"{stem}.xlsx"
            try:
                wb = build_audit_xlsx.build(findings, concentration=conc,
                                            creative_signals=cs)
                wb.save(p)
            except Exception as e:  # noqa: BLE001 — exit 2 per contract
                sys.stderr.write(f"ERROR: xlsx build failed: {e}\n")
                return 2
            if build_audit_xlsx.check(p) == 0:
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
    print(f"Health Score: {H['score']} / 100 — Grade {H['grade']} "
          f"({S['n_pass']} pass / {S['n_flag']} flag / {S['n_fail']} fail / "
          f"{S['n_na']} n/a)")
    print(f"Findings: {M['n_findings']} "
          f"({S['crit']} critical · {S['high']} high · {S['med']} medium · "
          f"{S['low']} low)")
    for fmt in ("html", "md", "xlsx"):
        if fmt in written:
            label = "→ open this" if fmt == "html" else ""
            print(f"  {fmt:4} {written[fmt]} {label}".rstrip())
    if copies:
        print("Copied to ~/Downloads: "
              + ", ".join(Path(c).name for c in copies))

    # machine-readable final line (SKILL.md parses this)
    print(json.dumps({"outputs": written, "health": H["score"],
                      "grade": H["grade"], "checks": M["n_checks"],
                      "findings": M["n_findings"],
                      "prescore_corrections":
                          len(pres_block["corrected"]) if pres_block else 0},
                     separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
