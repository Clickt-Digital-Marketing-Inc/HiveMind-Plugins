#!/usr/bin/env python3
"""Turn a JSON list of recommendation rows into a Google Ads Editor-importable CSV.

The Google Ads MCP is read-only, so every google-ads-* skill delivers its changes as a CSV the
user imports through Google Ads Editor (Account -> Make multiple changes / paste, or CSV import).
This generator keeps the column headers correct and consistent across skills.

Usage
-----
    python make_editor_csv.py --type negative_keywords --in recs.json --out negatives.csv
    cat recs.json | python make_editor_csv.py --type budget_changes > budget.csv

Input JSON: a list of objects. Keys are matched case-insensitively and ignore spaces/underscores,
so {"campaign": "...", "negative_keyword": "..."} and {"Campaign": "...", "Negative Keyword": "..."}
both work. Unknown keys are ignored; missing columns are written blank.

See ../references/artifact-formats.md for the column spec of each type.
"""
import argparse
import csv
import json
import sys

# type -> ordered output columns
SCHEMAS = {
    "negative_keywords": ["Campaign", "Ad Group", "Negative Keyword", "Match Type"],
    "add_keywords": ["Campaign", "Ad Group", "Keyword", "Match Type", "Max CPC"],
    "bid_adjustments": [
        "Campaign", "Ad Group", "Keyword", "Match Type", "Max CPC", "Bid Adjustment", "Level"
    ],
    "budget_changes": [
        "Campaign", "Current Daily Budget", "Proposed Daily Budget", "Change %", "Reason"
    ],
    "pause_list": ["Campaign", "Ad Group", "Entity Type", "Entity", "Reason"],
    # Product-segments worklist (Shopping/PMax). NOTE: product-level exclusions are
    # NOT cleanly Editor-importable — this is a prioritized MANUAL worklist for the
    # listing groups, not an Editor paste file. See ../references/artifact-formats.md.
    "product_actions": [
        "Segment", "Product Item ID", "Product Title", "Merchant ID",
        "30d Cost", "Conv 14d", "Conv Prev 14d", "Action", "Reason"
    ],
}


def _norm(key):
    """Normalize a key for fuzzy matching: lowercase, drop spaces/underscores."""
    return "".join(ch for ch in str(key).lower() if ch.isalnum())


def _row_to_columns(row, columns):
    """Map an input dict onto the schema columns using fuzzy key matching."""
    norm_lookup = {_norm(k): v for k, v in row.items()}
    out = {}
    for col in columns:
        out[col] = norm_lookup.get(_norm(col), "")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--type", required=True, choices=sorted(SCHEMAS),
                    help="Artifact type (determines CSV columns).")
    ap.add_argument("--in", dest="infile", default=None,
                    help="Input JSON file (list of row objects). Reads stdin if omitted.")
    ap.add_argument("--out", dest="outfile", default=None,
                    help="Output CSV path. Writes stdout if omitted.")
    args = ap.parse_args()

    raw = open(args.infile, encoding="utf-8").read() if args.infile else sys.stdin.read()
    try:
        rows = json.loads(raw)
    except json.JSONDecodeError as e:
        sys.exit(f"Invalid JSON input: {e}")
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        sys.exit("Input must be a JSON list of objects (or a single object).")

    columns = SCHEMAS[args.type]
    out_fh = open(args.outfile, "w", newline="", encoding="utf-8") if args.outfile else sys.stdout
    writer = csv.DictWriter(out_fh, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        if not isinstance(row, dict):
            sys.exit("Each row must be a JSON object.")
        writer.writerow(_row_to_columns(row, columns))
    if args.outfile:
        out_fh.close()
        print(f"Wrote {len(rows)} row(s) to {args.outfile}", file=sys.stderr)


if __name__ == "__main__":
    main()
