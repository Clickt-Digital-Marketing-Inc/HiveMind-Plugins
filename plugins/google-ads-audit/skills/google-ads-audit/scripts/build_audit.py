#!/usr/bin/env python3
# Copyright (c) 2026 Clickt Digital Marketing Inc. All rights reserved.
"""Build the Google Ads audit deliverable bundle from a findings JSON file.

Emits the interactive **HTML** (primary), a **markdown** record, and the formula-driven
**xlsx** backup — all from one computed model — into a user-chosen directory. The tool
owns the filenames (`ads-audit_{slug}_{date}.{html,md,xlsx}`); the caller picks only the
directory (`--outdir`). The SKILL.md prompts the user for that directory at runtime.

Usage:
    python3 build_audit.py --input findings.json --outdir ~/Downloads --brand "Acme Corp"
    python3 build_audit.py --input findings.json --outdir ./out --formats html,md
    python3 build_audit.py --check ads-audit_acme_2026-06-24.xlsx      # validate an xlsx

Exit codes: 0 success, 1 usage/validation error, 2 build error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import audit_model
import audit_html
import audit_md
import concentration as conc_mod
import manual_csv
import prescore as prescore_mod

# Dotted fields each raw pull must carry (validates "right file for the pull").
_REQ_CAMPAIGNS = ["campaign.name", "metrics.cost_micros", "metrics.conversions"]
_REQ_KEYWORDS = ["ad_group_criterion.keyword.text", "ad_group_criterion.keyword.match_type",
                 "metrics.cost_micros", "metrics.conversions"]
_REQ_SEARCH_TERMS = ["search_term_view.search_term", "metrics.cost_micros",
                     "metrics.conversions"]
_RAW_DIR_NAMES = {"campaigns": "campaigns.json", "keywords": "keywords.json",
                  "search_terms": "search_terms.json"}
_CSV_DIR_NAMES = {"campaigns": "campaigns.csv", "keywords": "keywords.csv",
                  "search_terms": "search_terms.csv"}
_CSV_ADAPTERS = {"campaigns": manual_csv.campaigns_rows,
                 "keywords": manual_csv.keywords_rows,
                 "search_terms": manual_csv.search_terms_rows}


def _load_input_rows(args) -> tuple[dict, dict, dict] | None:
    """Resolve and parse the raw-MCP files or manual UI CSVs (mutually
    exclusive; the caller validates) into the dotted-key rows shared by the
    Concentration report and the pre-scorer. Explicit flags win over the dir
    convenience. Returns (rows, files, windows) or None when nothing given.
    windows carries per-key labels only on the CSV path (each file's own
    date-range line); the raw path's labels come from findings meta."""
    use_csv = any([args.csv_campaigns, args.csv_keywords, args.csv_search_terms,
                   args.csv_dir])
    paths = ({"campaigns": args.csv_campaigns, "keywords": args.csv_keywords,
              "search_terms": args.csv_search_terms} if use_csv else
             {"campaigns": args.raw_campaigns, "keywords": args.raw_keywords,
              "search_terms": args.raw_search_terms})
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
                sys.stderr.write(f"note: {p} not found — {key} dimension skipped.\n")
    if not any(paths.values()):
        return None
    rows: dict[str, list | None] = {"campaigns": None, "keywords": None, "search_terms": None}
    files: dict[str, dict | None] = {}
    windows: dict[str, str] = {}
    req = {"campaigns": _REQ_CAMPAIGNS, "keywords": _REQ_KEYWORDS,
           "search_terms": _REQ_SEARCH_TERMS}
    for key, path in paths.items():
        if not path:
            files[key] = None
            continue
        if use_csv:
            rows[key], meta = _CSV_ADAPTERS[key](path)
            if meta.get("date_range"):
                windows[key] = meta["date_range"]
        else:
            rows[key] = conc_mod.load_rows(path, require_fields=req[key])
        files[key] = conc_mod.file_stamp(path)
    return rows, files, windows


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the Google Ads audit bundle (html + md + xlsx).")
    ap.add_argument("--input", help="findings JSON path")
    ap.add_argument("--outdir", default=".", help="output directory (default: current dir)")
    ap.add_argument("--brand", help="client/brand name override (leads the report)")
    ap.add_argument("--formats", default="html,md,xlsx",
                    help="comma list of html,md,xlsx (default: all three)")
    ap.add_argument("--no-animate", action="store_true", help="build the HTML without GSAP motion")
    ap.add_argument("--raw-campaigns", help="saved raw campaigns search_search result JSON")
    ap.add_argument("--raw-keywords", help="saved raw keyword_view search_search result JSON")
    ap.add_argument("--raw-search-terms", help="saved raw search_term_view search_search result JSON")
    ap.add_argument("--raw-dir", help="directory holding campaigns.json / keywords.json / "
                                      "search_terms.json (missing files skipped)")
    ap.add_argument("--csv-campaigns", help="Google Ads UI Campaign report .csv (no-MCP path)")
    ap.add_argument("--csv-keywords", help="Google Ads UI Search keyword report .csv (no-MCP path)")
    ap.add_argument("--csv-search-terms", help="Google Ads UI Search terms report .csv (no-MCP path)")
    ap.add_argument("--csv-dir", help="directory holding campaigns.csv / keywords.csv / "
                                      "search_terms.csv UI exports (missing files skipped)")
    ap.add_argument("--no-prescore", action="store_true",
                    help="skip the deterministic pre-scorer (machine-scored checks)")
    ap.add_argument("--prescore-only", action="store_true",
                    help="print the machine-scored results JSON and exit (no findings needed)")
    ap.add_argument("--business-model", choices=["Lead Gen", "Ecommerce"],
                    help="benchmark band for --prescore-only (else findings meta wins)")
    ap.add_argument("--check", metavar="XLSX", help="structurally validate an existing xlsx and exit")
    args = ap.parse_args()

    # --check delegates to the workbook's own quality gate.
    if args.check:
        try:
            import generate_workbook
        except SystemExit:
            return 2
        return generate_workbook.check(Path(args.check))

    if not args.input and not args.prescore_only:
        sys.stderr.write("ERROR: --input findings.json is required "
                         "(or use --check / --prescore-only).\n")
        return 1

    findings: dict = {}
    input_path = None
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
                      ("--raw-keywords", args.raw_keywords),
                      ("--raw-search-terms", args.raw_search_terms),
                      ("--csv-campaigns", args.csv_campaigns),
                      ("--csv-keywords", args.csv_keywords),
                      ("--csv-search-terms", args.csv_search_terms)):
        if val and not Path(val).is_file():
            sys.stderr.write(f"ERROR: {flag} file not found: {val}\n")
            return 1
    raw_given = any([args.raw_campaigns, args.raw_keywords, args.raw_search_terms, args.raw_dir])
    csv_given = any([args.csv_campaigns, args.csv_keywords, args.csv_search_terms, args.csv_dir])
    if raw_given and csv_given:
        sys.stderr.write("ERROR: use either --raw-* (MCP result files) or --csv-* "
                         "(UI exports), not both.\n")
        return 1
    meta = findings.get("meta", {})
    conc = pres = None
    try:
        loaded = _load_input_rows(args)
    except (conc_mod.RawResultError, manual_csv.ManualCsvError) as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return 1
    if loaded:
        rows, files, windows = loaded
        if not csv_given:  # raw path: window labels come from findings meta
            windows = {"90d": meta.get("date_range", ""),
                       "30d": meta.get("search_terms_range", "")}
        conc = conc_mod.compute_concentration(
            campaign_rows=rows["campaigns"], keyword_rows=rows["keywords"],
            search_term_rows=rows["search_terms"], files=files, windows=windows)
        if not args.no_prescore:
            bm = args.business_model or meta.get("business_model", "")
            targets = {k: meta[k] for k in ("target_cpa", "target_roas") if meta.get(k)}
            pres = prescore_mod.compute_prescore(
                campaign_rows=rows["campaigns"], keyword_rows=rows["keywords"],
                search_term_rows=rows["search_terms"],
                business_model=bm, targets=targets)

    if args.prescore_only:
        if pres is None:
            sys.stderr.write("ERROR: --prescore-only needs --raw-* or --csv-* inputs "
                             "(and not --no-prescore).\n")
            return 1
        print(json.dumps(pres, indent=2, ensure_ascii=False))
        return 0

    findings, pres_block, plog = prescore_mod.merge_into_findings(findings, pres)
    for line in plog:
        sys.stderr.write(line + "\n")

    brand = args.brand or ""
    model = audit_model.compute_model(findings, brand=brand, concentration=conc,
                                      prescore=pres_block)
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
            import generate_workbook  # lazy: md/html need no openpyxl
        except SystemExit:
            sys.stderr.write("WARNING: openpyxl missing — skipped the xlsx backup "
                             "(install with: python3 -m pip install --user openpyxl).\n")
        else:
            p = outdir / f"{stem}.xlsx"
            rc = generate_workbook.build(input_path, p, brand or None, concentration=conc,
                                         findings_data=findings)
            if rc == 0 and generate_workbook.check(p) == 0:
                written["xlsx"] = str(p.resolve())
            else:
                sys.stderr.write("ERROR: xlsx build or quality-gate failed.\n")
                return 2

    # human-readable summary
    H = model["health"]
    S = model["summary"]
    print(f"Health Score: {H['score']} / 100 — Grade {H['grade']} "
          f"({S['n_pass']} pass / {S['n_flag']} flag / {S['n_fail']} fail / {S['n_na']} n/a)")
    print(f"Findings: {model['provenance']['n_findings']} "
          f"({S['crit']} critical · {S['high']} high · {S['med']} medium · {S['low']} low)")
    for fmt in ("html", "md", "xlsx"):
        if fmt in written:
            label = "→ open this" if fmt == "html" else ""
            print(f"  {fmt:4} {written[fmt]} {label}".rstrip())

    # machine-readable final line (SKILL.md parses this)
    print(json.dumps({**written, "score": H["score"], "grade": H["grade"],
                      "prescore_corrections": len(pres_block["corrected"]) if pres_block else 0,
                      "outdir": str(outdir.resolve())}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
