#!/usr/bin/env python3
"""Assemble the product-segments findings JSON — script-only, either input path.

The transcription firewall for this skill: metric values go file -> parser ->
findings without ever passing through a token stream, and control totals are
embedded as meta.reconciliation so product_filter_core hard-fails if the
findings are later edited or were produced any other way. Two input paths,
ONE join algorithm (`product_filter_core.merge_product_windows`) so they can
never disagree — the skill's core cannot tell them apart except by the honest
`meta.source` label:

MCP path — the three saved raw `shopping_performance_view` pulls (auto-saved
by the harness when large, copied verbatim when small):
    python3 assemble_findings.py \
        --products-30d tool-results/p30.txt \
        --products-14d tool-results/p14.txt \
        --products-prev14d tool-results/prev14.txt \
        --client-name "Acme Corp" --account-id 123-456-7890 --currency CAD \
        --window-30d "2026-05-28 to 2026-06-26" \
        --window-14d "2026-06-13 to 2026-06-26" \
        --window-prev14d "2026-05-30 to 2026-06-12" \
        -o findings.json

CSV path — three Google Ads UI "Products" report exports at the same three
date ranges (column_map documented in
references/product-segments-filter.md#csv-manual-input-path):
    python3 assemble_findings.py \
        --csv-30d products_30d.csv --csv-14d products_14d.csv \
        --csv-prev14d products_prev14d.csv \
        --client-name "Acme Corp" --account-id 123-456-7890 --currency CAD \
        --window-30d "2026-05-28 to 2026-06-26" \
        --window-14d "2026-06-13 to 2026-06-26" \
        --window-prev14d "2026-05-30 to 2026-06-12" \
        -o findings.json

Pass the SAME dates used in the GAQL BETWEEN conditions / CSV export range for
the window labels. Both paths aggregate every pull per product_item_id — the
same key product_filter_core dedupes by — summing metrics across
campaigns/channels, unioning the channel set, and taking the merchant id from
the most recent window the product appears in (the 14d pull, else the 30d
pull). Products missing from a window default that window's metrics to 0; the
union of all three pulls survives.

Exit codes: 0 success, 1 usage/validation error.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parents[2]
sys.path.insert(0, str(PLUGIN_ROOT / "_shared"))

import csv_input as C       # noqa: E402
import gaql_raw as G        # noqa: E402
import reconcile as R       # noqa: E402

sys.path.insert(0, str(HERE))
import product_filter_core as core  # noqa: E402  (owns the reconcile contract + the merge join)

P30_FIELDS = ("segments.product_item_id", "segments.product_title",
              "segments.product_merchant_id", "campaign.advertising_channel_type",
              "metrics.conversions", "metrics.cost_micros", "metrics.impressions")
P14_FIELDS = ("segments.product_item_id", "segments.product_merchant_id",
              "metrics.conversions", "metrics.impressions")
PREV14_FIELDS = ("segments.product_item_id", "metrics.conversions", "metrics.impressions")

# Control totals verified by product_filter_core.load_findings on every build;
# the contract (which arrays, which fields) is owned by the core.
RECONCILE_ARRAYS = core.RECONCILE_ARRAYS


def _mid(row: dict) -> str:
    v = row.get("segments.product_merchant_id")
    return "" if v is None else str(v).strip()


def assemble(p30_path: str, p14_path: str, prev14_path: str, meta: dict) -> dict:
    """MCP path: three saved raw shopping_performance_view pulls -> findings."""
    r30 = G.load_rows(p30_path, require_fields=P30_FIELDS)
    r14 = G.load_rows(p14_path, require_fields=P14_FIELDS)
    rprev = G.load_rows(prev14_path, require_fields=PREV14_FIELDS)

    rows30 = [{"product_item_id": r.get("segments.product_item_id"),
              "product_title": r.get("segments.product_title"),
              "merchant_id": _mid(r),
              "channel": r.get("campaign.advertising_channel_type"),
              "conversions": G.num(r.get("metrics.conversions")),
              "cost": G.micros(r.get("metrics.cost_micros")),
              "impressions": G.num(r.get("metrics.impressions"))} for r in r30]
    rows14 = [{"product_item_id": r.get("segments.product_item_id"),
              "merchant_id": _mid(r),
              "conversions": G.num(r.get("metrics.conversions")),
              "impressions": G.num(r.get("metrics.impressions"))} for r in r14]
    rowsprev = [{"product_item_id": r.get("segments.product_item_id"),
                "conversions": G.num(r.get("metrics.conversions")),
                "impressions": G.num(r.get("metrics.impressions"))} for r in rprev]

    products = core.merge_product_windows(rows30, rows14, rowsprev)
    meta = dict(meta)
    meta.setdefault("source", "mcp")  # canonical live-pull token (HM-540/HM-572)
    findings = {"meta": meta, "params": {}, "products": products}
    findings["meta"]["reconciliation"] = R.build(
        findings, RECONCILE_ARRAYS,
        raw_stamps=[G.file_stamp(p) for p in (p30_path, p14_path, prev14_path)])
    return findings


# --------------------------------------------------------------------------
# CSV path — three Google Ads UI "Products" report exports at the 30d / 14d /
# prev-14d date ranges, column-mapped through the shared csv_input firewall
# and joined by the SAME merge_product_windows core.merge_product_windows
# uses for the MCP path. One entry per logical field the merge expects;
# aliases cover the header spellings the Google Ads UI "Products" report may
# export. Documented authoritatively in
# references/product-segments-filter.md#csv-manual-input-path.
# --------------------------------------------------------------------------
CSV_COLUMN_MAP = {
    "product_item_id": {"aliases": ["Item ID", "Item Id", "Product ID", "Product Id"], "type": "str"},
    "product_title":   {"aliases": ["Item title", "Product title", "Product Title", "Title"], "type": "str"},
    "merchant_id":     {"aliases": ["Merchant Center ID", "Merchant Center Id", "Merchant ID"], "type": "str"},
    "channel":         {"aliases": ["Campaign type", "Advertising channel type"], "type": "str"},
    "conversions":     {"aliases": ["Conversions", "Conv."], "type": "num"},
    "cost":            {"aliases": ["Cost"], "type": "num"},
    "impressions":     {"aliases": ["Impr.", "Impressions"], "type": "num"},
}
# Merchant id is REQUIRED on the 14d export (not just the 30d one): the merge
# always adopts the 14d pull's merchant_id value for a product that appears
# there (even blank), so a 14d export missing that column would silently
# blank every such product's merchant id instead of raising — require the
# column so a bad export fails loudly at assembly time, not with a silently
# wrong Zombie count.
CSV_REQUIRED_30D = ("product_item_id", "conversions", "cost", "impressions")
CSV_REQUIRED_14D = ("product_item_id", "merchant_id", "conversions", "impressions")
CSV_REQUIRED_PREV14D = ("product_item_id", "conversions", "impressions")


def assemble_csv(csv_30d: str, csv_14d: str, csv_prev14d: str, meta: dict) -> dict:
    """CSV path: three Google Ads UI 'Products' report exports -> findings.

    `load_csv_rows` already returns rows keyed by the LOGICAL field names in
    CSV_COLUMN_MAP, so they feed merge_product_windows unchanged — no
    per-window normalization needed (unlike the MCP path's dotted GAQL keys)."""
    rows30, stamp30 = C.load_csv_rows(csv_30d, CSV_COLUMN_MAP, CSV_REQUIRED_30D)
    rows14, stamp14 = C.load_csv_rows(csv_14d, CSV_COLUMN_MAP, CSV_REQUIRED_14D)
    rowsprev, stampprev = C.load_csv_rows(csv_prev14d, CSV_COLUMN_MAP, CSV_REQUIRED_PREV14D)

    products = core.merge_product_windows(rows30, rows14, rowsprev)
    meta = dict(meta)
    meta.setdefault("source", "user_csv")
    findings = {"meta": meta, "params": {}, "products": products}
    findings["meta"]["reconciliation"] = R.build(
        findings, RECONCILE_ARRAYS, raw_stamps=[stamp30, stamp14, stampprev])
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description="Assemble product-segments findings JSON "
                                             "from saved raw GAQL pulls OR three Google Ads UI CSV exports.")
    mcp_grp = ap.add_argument_group("MCP path — saved raw shopping_performance_view pulls")
    mcp_grp.add_argument("--products-30d", help="raw shopping_performance_view 30d results file")
    mcp_grp.add_argument("--products-14d", help="raw shopping_performance_view last-14d results file")
    mcp_grp.add_argument("--products-prev14d", help="raw shopping_performance_view previous-14d results file")
    csv_grp = ap.add_argument_group("CSV path — Google Ads UI 'Products' report exports")
    csv_grp.add_argument("--csv-30d", help="Products report CSV export, 30-day range")
    csv_grp.add_argument("--csv-14d", help="Products report CSV export, last-14-day range")
    csv_grp.add_argument("--csv-prev14d", help="Products report CSV export, previous-14-day range")
    ap.add_argument("--client-name", required=True)
    ap.add_argument("--account-id", required=True)
    ap.add_argument("--currency", required=True)
    ap.add_argument("--window-30d", required=True, help='e.g. "2026-05-28 to 2026-06-26" — the dates used in the GAQL BETWEEN / CSV export range')
    ap.add_argument("--window-14d", required=True)
    ap.add_argument("--window-prev14d", required=True)
    ap.add_argument("--generated", default=None,
                    help="report date (YYYY-MM-DD); defaults to today — pass the "
                         "original date when re-assembling for byte-identical output")
    ap.add_argument("-o", "--output", required=True, help="findings JSON output path")
    args = ap.parse_args()

    mcp_args = (args.products_30d, args.products_14d, args.products_prev14d)
    csv_args = (args.csv_30d, args.csv_14d, args.csv_prev14d)
    has_mcp, has_csv = any(mcp_args), any(csv_args)
    if has_mcp and has_csv:
        sys.stderr.write("ERROR: pass either the MCP flags (--products-30d/-14d/-prev14d) "
                         "or the CSV flags (--csv-30d/-14d/-prev14d), not both.\n")
        return 1
    if has_mcp and not all(mcp_args):
        sys.stderr.write("ERROR: MCP path needs all three of --products-30d/-14d/-prev14d.\n")
        return 1
    if has_csv and not all(csv_args):
        sys.stderr.write("ERROR: CSV path needs all three of --csv-30d/-14d/-prev14d.\n")
        return 1
    if not has_mcp and not has_csv:
        sys.stderr.write("ERROR: pass either the MCP flags (--products-30d/-14d/-prev14d) "
                         "or the CSV flags (--csv-30d/-14d/-prev14d).\n")
        return 1

    meta = {"client_name": args.client_name, "account_id": args.account_id,
            "currency": args.currency, "window_30d": args.window_30d,
            "window_14d": args.window_14d, "window_prev14d": args.window_prev14d,
            "generated": args.generated or datetime.date.today().isoformat()}
    try:
        if has_csv:
            findings = assemble_csv(args.csv_30d, args.csv_14d, args.csv_prev14d, meta)
        else:
            findings = assemble(args.products_30d, args.products_14d,
                                args.products_prev14d, meta)
    except (G.RawResultError, C.CsvInputError, OSError) as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return 1

    Path(args.output).write_text(json.dumps(findings, ensure_ascii=False, indent=1))
    rec = findings["meta"]["reconciliation"]
    pr = rec["products"]
    print(f"Wrote {args.output}  (source: {findings['meta']['source']})")
    print(f"  products: {pr['rows']} (30d cost {pr['sums']['cost_30d']:,.2f} {args.currency}, "
          f"30d conversions {pr['sums']['conversions_30d']:,.2f})")
    print("  reconciliation totals embedded — the builder verifies them on every run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
