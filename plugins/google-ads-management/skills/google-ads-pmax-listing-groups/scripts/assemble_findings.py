#!/usr/bin/env python3
"""Assemble the PMax listing-group findings JSON from saved raw GAQL pulls (script-only).

The transcription firewall for this skill: the four search_search pulls are
saved verbatim to files (auto-saved by the harness when large, copied verbatim
when small) and THIS script — never the model — turns them into the findings
JSON. Metric values go raw file -> parser -> findings without ever passing
through a token stream, and control totals are embedded as meta.reconciliation
so pmax_listing_core hard-fails if the findings are later edited or were
produced any other way.

Usage:
    python3 assemble_findings.py \
        --listing-groups tool-results/lg.txt --labels tool-results/labels.txt \
        --benchmarks tool-results/bench.txt --products tool-results/prod.txt \
        --client-name "Acme Corp" --account-id 123-456-7890 --currency CAD \
        --window-30d "2026-06-06 to 2026-07-05" \
        -o findings.json

Pass the window label matching the pulls' LAST_30_DAYS range (ends yesterday).
`--listing-groups`/`--labels` travel together (the labels pull carries NO
metrics — it only names each partition, joined on the listing-group-filter
resource name); `--products` is optional. At least one universe must be given.
Aggregates by the same keys pmax_listing_core dedupes by — one row per
partition / per (campaign, item) — so the core's dedupe is a no-op, and keeps
only product rows whose campaign is in the PMax benchmark set
(shopping_performance_view spans legacy Shopping too).

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

import gaql_raw as G                 # noqa: E402
import reconcile as R                # noqa: E402

sys.path.insert(0, str(HERE))
import pmax_listing_core as core     # noqa: E402  (owns the reconcile contract)

LG_FIELDS = ("campaign.id", "campaign.name", "asset_group.id", "asset_group.name",
             "asset_group_product_group_view.asset_group_listing_group_filter",
             "metrics.impressions", "metrics.clicks", "metrics.conversions",
             "metrics.conversions_value", "metrics.cost_micros")
# The labels pull is structural (no metrics, no date): only resource_name is on
# every row; the case_value.* sub-fields appear only where populated.
LABEL_FIELDS = ("asset_group_listing_group_filter.resource_name",)
BENCH_FIELDS = ("campaign.id", "campaign.name", "metrics.clicks",
                "metrics.conversions", "metrics.cost_micros")
PRODUCT_FIELDS = ("campaign.id", "campaign.name", "segments.product_item_id",
                  "metrics.impressions", "metrics.clicks", "metrics.conversions",
                  "metrics.conversions_value", "metrics.cost_micros")

# Control totals verified by pmax_listing_core.load_findings on every build;
# the contract (which arrays, which fields) is owned by the core.
RECONCILE_ARRAYS = core.RECONCILE_ARRAYS

_CASE = "asset_group_listing_group_filter.case_value."
# (case_value sub-field, dimension, label prefix) in check order; the populated
# sub-field names the partition, e.g. "Brand: Nike" / "Item ID: ABC123".
_DIMENSIONS = (
    ("product_brand.value", "product_brand", "Brand"),
    ("product_item_id.value", "product_item_id", "Item ID"),
    ("product_type.value", "product_type", "Type"),
    ("product_category.category_id", "product_category", "Category"),
    ("product_condition.condition", "product_condition", "Condition"),
    ("product_channel.channel", "product_channel", "Channel"),
    ("product_custom_attribute.value", "product_custom_attribute", "Custom attribute"),
)


def _label_of(row: dict) -> tuple:
    """(label, dimension) from a label row's populated case_value sub-field.
    A node with NO case_value is the catch-all -> ("", "") and the core renders
    it as 'Everything else'."""
    for suffix, dim, prefix in _DIMENSIONS:
        v = row.get(_CASE + suffix)
        if v not in (None, ""):
            return f"{prefix}: {v}", dim
    return "", ""


def _filter_id(resource_name) -> str:
    """`customers/<cid>/assetGroupListingGroupFilters/<asset_group>~<id>` ->
    the `<asset_group>~<id>` tail."""
    return str(resource_name or "").rsplit("/", 1)[-1]


def _assemble_benchmarks(bench_path: str) -> list:
    """One row per campaign (aggregated defensively across any split), cost
    converted from micros."""
    merged: dict = {}
    order: list = []
    for r in G.load_rows(bench_path, require_fields=BENCH_FIELDS):
        cid = r.get("campaign.id")
        if cid not in merged:
            merged[cid] = {"campaign_id": cid, "campaign": r.get("campaign.name", ""),
                           "clicks": 0.0, "cost": 0.0, "conversions": 0.0}
            order.append(cid)
        b = merged[cid]
        b["clicks"] += G.num(r.get("metrics.clicks"))
        b["cost"] += G.micros(r.get("metrics.cost_micros"))
        b["conversions"] += G.num(r.get("metrics.conversions"))
    for cid in order:
        merged[cid]["cost"] = round(merged[cid]["cost"], 6)
    return [merged[cid] for cid in order]


def _assemble_listing_groups(lg_path: str, labels_path: str) -> list:
    """One row per partition: metrics from pull 1 aggregated by
    (campaign, asset group, filter resource name) — the label pull contributes
    structure (label + dimension), never reconciled sums."""
    labels: dict = {}
    for r in G.load_rows(labels_path, require_fields=LABEL_FIELDS):
        labels[r.get("asset_group_listing_group_filter.resource_name")] = _label_of(r)
    merged: dict = {}
    order: list = []
    unlabeled = 0
    for r in G.load_rows(lg_path, require_fields=LG_FIELDS):
        res = r.get("asset_group_product_group_view.asset_group_listing_group_filter")
        if res in labels:
            label, dim = labels[res]
        else:
            label, dim = "", ""   # keep the metrics; never drop a partition
            unlabeled += 1
        k = (r.get("campaign.id"), str(r.get("asset_group.name") or ""), res)
        if k not in merged:
            merged[k] = {"campaign_id": r.get("campaign.id"),
                         "campaign": r.get("campaign.name", ""),
                         "asset_group_id": str(r.get("asset_group.id", "")),
                         "asset_group": r.get("asset_group.name", ""),
                         "listing_group_id": _filter_id(res),
                         "listing_group": label, "dimension": dim,
                         "impressions": 0.0, "clicks": 0.0, "cost": 0.0,
                         "conversions": 0.0, "conversions_value": 0.0}
            order.append(k)
        m = merged[k]
        m["impressions"] += G.num(r.get("metrics.impressions"))
        m["clicks"] += G.num(r.get("metrics.clicks"))
        m["cost"] += G.micros(r.get("metrics.cost_micros"))
        m["conversions"] += G.num(r.get("metrics.conversions"))
        m["conversions_value"] += G.num(r.get("metrics.conversions_value"))
    for k in order:
        merged[k]["cost"] = round(merged[k]["cost"], 6)
    if unlabeled:
        sys.stderr.write(f"NOTE: {unlabeled} listing-group metric rows had no matching "
                         "label row — kept with an empty label (rendered 'Everything "
                         "else'); check the labels file covers the same asset groups\n")
    return [merged[k] for k in order]


def _assemble_products(products_path: str, pmax_ids: set) -> list:
    """One row per (campaign, item id), kept only for campaigns in the PMax
    benchmark set (shopping_performance_view spans legacy Shopping too)."""
    merged: dict = {}
    order: list = []
    dropped_non_pmax = 0
    for r in G.load_rows(products_path, require_fields=PRODUCT_FIELDS):
        cid = r.get("campaign.id")
        if cid not in pmax_ids:
            dropped_non_pmax += 1
            continue
        item = str(r.get("segments.product_item_id") or "")
        k = (cid, item)
        if k not in merged:
            merged[k] = {"campaign_id": cid, "campaign": r.get("campaign.name", ""),
                         "item_id": item,
                         "title": str(r.get("segments.product_title") or ""),
                         "impressions": 0.0, "clicks": 0.0, "cost": 0.0,
                         "conversions": 0.0, "conversions_value": 0.0}
            order.append(k)
        m = merged[k]
        if not m["title"]:
            m["title"] = str(r.get("segments.product_title") or "")
        m["impressions"] += G.num(r.get("metrics.impressions"))
        m["clicks"] += G.num(r.get("metrics.clicks"))
        m["cost"] += G.micros(r.get("metrics.cost_micros"))
        m["conversions"] += G.num(r.get("metrics.conversions"))
        m["conversions_value"] += G.num(r.get("metrics.conversions_value"))
    for k in order:
        merged[k]["cost"] = round(merged[k]["cost"], 6)
    if dropped_non_pmax:
        sys.stderr.write(f"NOTE: dropped {dropped_non_pmax} shopping_performance_view "
                         "rows from non-PMax campaigns (not in the benchmarks pull's "
                         "PMax set)\n")
    return [merged[k] for k in order]


def assemble(lg_path, labels_path, bench_path, products_path, meta: dict) -> dict:
    meta = dict(meta)
    meta.setdefault("source", "mcp")   # canonical live-pull token (HM-539/HM-572)
    findings = {"meta": meta, "params": {},
                "benchmarks": _assemble_benchmarks(bench_path)}
    pmax_ids = {b["campaign_id"] for b in findings["benchmarks"]}
    if lg_path:
        findings["listing_groups"] = _assemble_listing_groups(lg_path, labels_path)
    if products_path:
        findings["products"] = _assemble_products(products_path, pmax_ids)
    raw_paths = [p for p in (lg_path, labels_path, bench_path, products_path) if p]
    findings["meta"]["reconciliation"] = R.build(
        findings, RECONCILE_ARRAYS,
        raw_stamps=[G.file_stamp(p) for p in raw_paths])
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description="Assemble the PMax listing-group findings "
                                             "JSON from saved raw GAQL pulls.")
    ap.add_argument("--listing-groups", default=None,
                    help="raw asset_group_product_group_view 30d results file")
    ap.add_argument("--labels", default=None,
                    help="raw asset_group_listing_group_filter (structural) results file — "
                         "required with --listing-groups")
    ap.add_argument("--benchmarks", required=True,
                    help="raw PMax campaign benchmarks 30d results file")
    ap.add_argument("--products", default=None,
                    help="raw shopping_performance_view 30d results file (optional)")
    ap.add_argument("--client-name", required=True)
    ap.add_argument("--account-id", required=True)
    ap.add_argument("--currency", required=True)
    ap.add_argument("--window-30d", required=True,
                    help='e.g. "2026-06-06 to 2026-07-05" — the LAST_30_DAYS range (ends yesterday)')
    ap.add_argument("--generated", default=None,
                    help="report date (YYYY-MM-DD); defaults to today — pass the "
                         "original date when re-assembling for byte-identical output")
    ap.add_argument("-o", "--output", required=True, help="findings JSON output path")
    args = ap.parse_args()

    if not args.listing_groups and not args.products:
        sys.stderr.write("ERROR: provide at least one universe: --listing-groups "
                         "(with --labels) and/or --products\n")
        return 1
    if bool(args.listing_groups) != bool(args.labels):
        sys.stderr.write("ERROR: --listing-groups and --labels must be provided together "
                         "(the labels pull names each partition)\n")
        return 1

    meta = {"client_name": args.client_name, "account_id": args.account_id,
            "currency": args.currency, "window_30d": args.window_30d,
            "generated": args.generated or datetime.date.today().isoformat()}
    try:
        findings = assemble(args.listing_groups, args.labels, args.benchmarks,
                            args.products, meta)
    except (G.RawResultError, OSError) as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return 1

    Path(args.output).write_text(json.dumps(findings, ensure_ascii=False, indent=1))
    rec = findings["meta"]["reconciliation"]
    lg, pr, bm = rec["listing_groups"], rec["products"], rec["benchmarks"]
    print(f"Wrote {args.output}")
    print(f"  listing_groups: {lg['rows']} partitions (cost {lg['sums']['cost']:,.2f} {args.currency})")
    print(f"  products:       {pr['rows']} items (cost {pr['sums']['cost']:,.2f} {args.currency})")
    print(f"  benchmarks:     {bm['rows']} campaigns (cost {bm['sums']['cost']:,.2f} {args.currency})")
    print("  reconciliation totals embedded — the builder verifies them on every run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
