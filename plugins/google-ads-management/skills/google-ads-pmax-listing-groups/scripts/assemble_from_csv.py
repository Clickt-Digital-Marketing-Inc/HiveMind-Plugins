#!/usr/bin/env python3
"""Assemble the PMax listing-group findings JSON from user-supplied Google Ads
UI CSV exports — the CSV twin of assemble_findings.py (the MCP path). See the
dual-input contract in
`../../google-ads-foundation/references/artifact-formats.md` and this skill's
"CSV input path" section in `references/pmax-listing-waste-filter.md`.

Three UI exports (the campaign benchmarks export is always required; at least
one of listing-groups/products must also be given — same rule as the MCP path):

  --campaigns       Campaigns view (report filtered/segmented to Performance
                     Max campaigns only), last 30 days -> the campaign
                     benchmark universe (same role as GAQL pull 3).
  --listing-groups  Performance Max > Asset groups > "Listing groups" view,
                     last 30 days -> the partition universe (GAQL pulls 1+2
                     combined). A flat UI export has no case_value structure,
                     so `dimension` is left blank on this path — the exported
                     "Listing group" column text IS the label (the
                     "Brand: Nike"-style prefix only exists on the MCP path,
                     which derives it from `case_value.*`).
  --products        Shopping/PMax "Product performance" view (Insights &
                     reports), last 30 days -> the product universe (GAQL
                     pull 4), filtered to campaigns present in --campaigns.

Google Ads UI exports carry no numeric campaign id, so the campaign NAME is
used as `campaign_id` on this path — a stable join key as long as campaign
names are unique in the account (the same convention `campaign` display text
already relies on). Never mix MCP-path and CSV-path rows in one findings file.

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

import csv_input as CI             # noqa: E402
import reconcile as R              # noqa: E402

sys.path.insert(0, str(HERE))
import pmax_listing_core as core   # noqa: E402  (owns the reconcile contract)

# Column-mapping contract (see _shared/csv_input.py / artifact-formats.md):
# one entry per logical field the skill's findings rows carry, with every
# header spelling the Google Ads UI export may use. Aliases picked from the
# standard Google Ads UI report columns (Impr., Conv. value, etc.); if a real
# export uses a different spelling, add the alias + a fixture test and log
# the lesson in the project's Lessons Log.
BENCH_COLUMN_MAP = {
    "campaign":    {"aliases": ["Campaign"], "type": "str"},
    "clicks":      {"aliases": ["Clicks"], "type": "num"},
    "cost":        {"aliases": ["Cost"], "type": "num"},
    "conversions": {"aliases": ["Conversions"], "type": "num"},
}

LISTING_GROUP_COLUMN_MAP = {
    "campaign":          {"aliases": ["Campaign"], "type": "str"},
    "asset_group":       {"aliases": ["Asset group", "Ad group"], "type": "str"},
    "listing_group":     {"aliases": ["Listing group", "Product group"], "type": "str"},
    "impressions":       {"aliases": ["Impr."], "type": "num"},
    "clicks":            {"aliases": ["Clicks"], "type": "num"},
    "cost":              {"aliases": ["Cost"], "type": "num"},
    "conversions":       {"aliases": ["Conversions"], "type": "num"},
    "conversions_value": {"aliases": ["Conv. value", "Conversion value"], "type": "num"},
}

PRODUCT_COLUMN_MAP = {
    "campaign":          {"aliases": ["Campaign"], "type": "str"},
    "item_id":           {"aliases": ["Item ID", "Item Id", "Product ID"], "type": "str"},
    "title":             {"aliases": ["Item title", "Product title", "Title"], "type": "str"},
    "impressions":       {"aliases": ["Impr."], "type": "num"},
    "clicks":            {"aliases": ["Clicks"], "type": "num"},
    "cost":              {"aliases": ["Cost"], "type": "num"},
    "conversions":       {"aliases": ["Conversions"], "type": "num"},
    "conversions_value": {"aliases": ["Conv. value", "Conversion value"], "type": "num"},
}

# Control totals verified by pmax_listing_core.load_findings on every build;
# the contract (which arrays, which fields) is owned by the core — identical
# to the MCP path's RECONCILE_ARRAYS.
RECONCILE_ARRAYS = core.RECONCILE_ARRAYS


def _assemble_benchmarks(csv_path: str):
    rows, stamp = CI.load_csv_rows(
        csv_path, BENCH_COLUMN_MAP,
        required_fields=("campaign", "clicks", "cost", "conversions"))
    merged: dict = {}
    order: list = []
    for r in rows:
        cid = r["campaign"]
        if cid not in merged:
            merged[cid] = {"campaign_id": cid, "campaign": cid,
                           "clicks": 0.0, "cost": 0.0, "conversions": 0.0}
            order.append(cid)
        b = merged[cid]
        b["clicks"] += r["clicks"]
        b["cost"] += r["cost"]
        b["conversions"] += r["conversions"]
    return [merged[k] for k in order], stamp


def _assemble_listing_groups(csv_path: str):
    rows, stamp = CI.load_csv_rows(
        csv_path, LISTING_GROUP_COLUMN_MAP,
        required_fields=("campaign", "asset_group", "listing_group", "cost", "conversions"))
    merged: dict = {}
    order: list = []
    for r in rows:
        k = (r["campaign"], r["asset_group"], r["listing_group"])
        if k not in merged:
            merged[k] = {"campaign_id": r["campaign"], "campaign": r["campaign"],
                         "asset_group_id": r["asset_group"], "asset_group": r["asset_group"],
                         # a flat UI export has no listing-group-filter id or
                         # case_value dimension — the label text is the identity.
                         "listing_group_id": "", "listing_group": r["listing_group"],
                         "dimension": "",
                         "impressions": 0.0, "clicks": 0.0, "cost": 0.0,
                         "conversions": 0.0, "conversions_value": 0.0}
            order.append(k)
        m = merged[k]
        m["impressions"] += r.get("impressions", 0.0)
        m["clicks"] += r.get("clicks", 0.0)
        m["cost"] += r.get("cost", 0.0)
        m["conversions"] += r.get("conversions", 0.0)
        m["conversions_value"] += r.get("conversions_value", 0.0)
    return [merged[k] for k in order], stamp


def _assemble_products(csv_path: str, pmax_names: set):
    rows, stamp = CI.load_csv_rows(
        csv_path, PRODUCT_COLUMN_MAP,
        required_fields=("campaign", "item_id", "cost", "conversions"))
    merged: dict = {}
    order: list = []
    dropped = 0
    for r in rows:
        if r["campaign"] not in pmax_names:
            dropped += 1
            continue
        k = (r["campaign"], r["item_id"])
        if k not in merged:
            merged[k] = {"campaign_id": r["campaign"], "campaign": r["campaign"],
                         "item_id": r["item_id"], "title": r.get("title", "") or r["item_id"],
                         "impressions": 0.0, "clicks": 0.0, "cost": 0.0,
                         "conversions": 0.0, "conversions_value": 0.0}
            order.append(k)
        m = merged[k]
        if not m["title"]:
            m["title"] = r.get("title", "") or r["item_id"]
        m["impressions"] += r.get("impressions", 0.0)
        m["clicks"] += r.get("clicks", 0.0)
        m["cost"] += r.get("cost", 0.0)
        m["conversions"] += r.get("conversions", 0.0)
        m["conversions_value"] += r.get("conversions_value", 0.0)
    if dropped:
        sys.stderr.write(f"NOTE: dropped {dropped} product rows whose campaign is not in the "
                         "--campaigns export's PMax set (not a PMax campaign in this pull)\n")
    return [merged[k] for k in order], stamp


def assemble(bench_path: str, lg_path: str | None, products_path: str | None,
            meta: dict) -> dict:
    meta = dict(meta)
    meta.setdefault("source", "user_csv")   # honest data-source label (HM-539)
    findings = {"meta": meta, "params": {}}

    benchmarks, bench_stamp = _assemble_benchmarks(bench_path)
    findings["benchmarks"] = benchmarks
    pmax_names = {b["campaign_id"] for b in benchmarks}
    stamps = [bench_stamp]

    if lg_path:
        listing_groups, lg_stamp = _assemble_listing_groups(lg_path)
        findings["listing_groups"] = listing_groups
        stamps.append(lg_stamp)
    if products_path:
        products, pr_stamp = _assemble_products(products_path, pmax_names)
        findings["products"] = products
        stamps.append(pr_stamp)

    findings["meta"]["reconciliation"] = R.build(findings, RECONCILE_ARRAYS, raw_stamps=stamps)
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Assemble the PMax listing-group findings JSON from user-supplied "
                    "Google Ads UI CSV exports (the CSV twin of assemble_findings.py).")
    ap.add_argument("--campaigns", required=True,
                    help="Campaigns view CSV export (PMax only), last 30 days")
    ap.add_argument("--listing-groups", default=None,
                    help="PMax listing-groups view CSV export, last 30 days")
    ap.add_argument("--products", default=None,
                    help="Shopping/PMax product performance CSV export, last 30 days")
    ap.add_argument("--client-name", required=True)
    ap.add_argument("--account-id", required=True)
    ap.add_argument("--currency", required=True)
    ap.add_argument("--window-30d", required=True,
                    help='e.g. "2026-06-06 to 2026-07-05" — the 30-day export range')
    ap.add_argument("--generated", default=None,
                    help="report date (YYYY-MM-DD); defaults to today")
    ap.add_argument("-o", "--output", required=True, help="findings JSON output path")
    args = ap.parse_args()

    if not args.listing_groups and not args.products:
        sys.stderr.write("ERROR: provide at least one universe: --listing-groups "
                         "and/or --products\n")
        return 1

    meta = {"client_name": args.client_name, "account_id": args.account_id,
            "currency": args.currency, "window_30d": args.window_30d,
            "generated": args.generated or datetime.date.today().isoformat()}
    try:
        findings = assemble(args.campaigns, args.listing_groups, args.products, meta)
    except (CI.CsvInputError, OSError) as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return 1

    Path(args.output).write_text(json.dumps(findings, ensure_ascii=False, indent=1))
    rec = findings["meta"]["reconciliation"]
    bm = rec["benchmarks"]
    print(f"Wrote {args.output}  (source: user_csv)")
    print(f"  benchmarks: {bm['rows']} campaigns (cost {bm['sums']['cost']:,.2f} {args.currency})")
    if "listing_groups" in rec:
        lg = rec["listing_groups"]
        print(f"  listing_groups: {lg['rows']} partitions (cost {lg['sums']['cost']:,.2f} {args.currency})")
    if "products" in rec:
        pr = rec["products"]
        print(f"  products: {pr['rows']} items (cost {pr['sums']['cost']:,.2f} {args.currency})")
    print("  reconciliation totals embedded — the builder verifies them on every run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
