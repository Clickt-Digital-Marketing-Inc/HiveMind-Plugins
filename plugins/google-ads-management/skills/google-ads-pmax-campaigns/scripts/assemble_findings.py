#!/usr/bin/env python3
"""Assemble the PMax momentum findings JSON from saved raw GAQL pulls (script-only).

The transcription firewall for this skill: the two campaign pulls (last 14 days
and the previous 14 days) are saved verbatim to files (auto-saved by the harness
when large, copied verbatim when small) and THIS script — never the model —
turns them into the findings JSON. Metric values go raw file -> parser ->
findings without ever passing through a token stream, and control totals are
embedded as meta.reconciliation so pmax_core hard-fails if the findings are
later edited or were produced any other way.

Usage:
    python3 assemble_findings.py \
        --last-window tool-results/last14.txt \
        --prev-window tool-results/prev14.txt \
        --client-name "Acme Corp" --account-id 123-456-7890 --currency CAD \
        --window-last "2026-06-22 to 2026-07-05" \
        --window-prev "2026-06-08 to 2026-06-21" \
        -o findings.json

    # M1.4 — optional asset-group + Search-campaign structural pulls (both are
    # single-window snapshots at the LAST 14-day range, not last/prev pairs):
    python3 assemble_findings.py \
        --last-window tool-results/last14.txt --prev-window tool-results/prev14.txt \
        --asset-groups tool-results/asset_groups_last14.txt \
        --search-campaigns tool-results/search_last14.txt \
        --client-name "Acme Corp" --account-id 123-456-7890 --currency CAD \
        --window-last "2026-06-22 to 2026-07-05" --window-prev "2026-06-08 to 2026-06-21" \
        -o findings.json

Pass the SAME dates used in the GAQL BETWEEN conditions for the window labels.
Aggregates each window's rows by campaign.id — the same key pmax_core sums each
window by — so the core's dedupe guard is a no-op on assembled output. Converts
cost_micros to currency; conversions_value is NOT micros and is passed through.
--asset-groups additionally aggregates by (campaign.id, asset_group.id); see
references/pmax-momentum-filter.md '#asset-group-concentration' and
'#cannibalization-heuristic' for the GAQL pulls.

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

import gaql_raw as G        # noqa: E402
import reconcile as R       # noqa: E402

sys.path.insert(0, str(HERE))
import pmax_core as core    # noqa: E402  (owns the reconcile contract)

WINDOW_FIELDS = ("campaign.id", "campaign.name", "metrics.impressions",
                 "metrics.clicks", "metrics.cost_micros", "metrics.conversions",
                 "metrics.conversions_value")
ASSET_GROUP_FIELDS = ("campaign.id", "campaign.name", "asset_group.id",
                      "asset_group.name", "metrics.impressions", "metrics.clicks",
                      "metrics.cost_micros", "metrics.conversions",
                      "metrics.conversions_value")

# Control totals verified by pmax_core.load_findings on every build;
# the contract (which arrays, which fields) is owned by the core.
RECONCILE_ARRAYS = core.RECONCILE_ARRAYS
RECONCILE_ARRAYS_OPTIONAL = core.RECONCILE_ARRAYS_OPTIONAL


def _window_rows(path: str) -> list:
    """One row per campaign for one window (sums preserved across any segment
    split, matching pmax_core._index_window), cost converted from micros."""
    merged: dict = {}
    order: list = []
    for r in G.load_rows(path, require_fields=WINDOW_FIELDS):
        cid = r.get("campaign.id")
        if cid not in merged:
            merged[cid] = {"campaign_id": cid,
                           "campaign": r.get("campaign.name", ""),
                           "impressions": 0.0, "clicks": 0.0, "cost": 0.0,
                           "conversions": 0.0, "conversions_value": 0.0}
            order.append(cid)
        m = merged[cid]
        if not m["campaign"]:
            m["campaign"] = r.get("campaign.name", "")
        m["impressions"] += G.num(r.get("metrics.impressions"))
        m["clicks"] += G.num(r.get("metrics.clicks"))
        m["cost"] += G.micros(r.get("metrics.cost_micros"))
        m["conversions"] += G.num(r.get("metrics.conversions"))
        m["conversions_value"] += G.num(r.get("metrics.conversions_value"))
    for cid in order:
        merged[cid]["cost"] = round(merged[cid]["cost"], 6)
    return [merged[cid] for cid in order]


def _asset_group_rows(path: str) -> list:
    """One row per (campaign.id, asset_group.id) — the M1.4 structural pull for
    asset_group_concentration. Sums preserved across any segment split, keyed
    the same way pmax_core._index_asset_groups groups by."""
    merged: dict = {}
    order: list = []
    for r in G.load_rows(path, require_fields=ASSET_GROUP_FIELDS):
        key = (r.get("campaign.id"), r.get("asset_group.id"))
        if key not in merged:
            merged[key] = {"campaign_id": r.get("campaign.id"),
                           "campaign": r.get("campaign.name", ""),
                           "asset_group_id": r.get("asset_group.id"),
                           "asset_group": r.get("asset_group.name", ""),
                           "impressions": 0.0, "clicks": 0.0, "cost": 0.0,
                           "conversions": 0.0, "conversions_value": 0.0}
            order.append(key)
        m = merged[key]
        if not m["campaign"]:
            m["campaign"] = r.get("campaign.name", "")
        if not m["asset_group"]:
            m["asset_group"] = r.get("asset_group.name", "")
        m["impressions"] += G.num(r.get("metrics.impressions"))
        m["clicks"] += G.num(r.get("metrics.clicks"))
        m["cost"] += G.micros(r.get("metrics.cost_micros"))
        m["conversions"] += G.num(r.get("metrics.conversions"))
        m["conversions_value"] += G.num(r.get("metrics.conversions_value"))
    for key in order:
        merged[key]["cost"] = round(merged[key]["cost"], 6)
    return [merged[key] for key in order]


def assemble(last_path: str, prev_path: str, meta: dict, *,
            asset_groups_path: str | None = None,
            search_campaigns_path: str | None = None) -> dict:
    findings = {"meta": meta, "params": {},
                "last_window": _window_rows(last_path),
                "prev_window": _window_rows(prev_path)}
    arrays = dict(RECONCILE_ARRAYS)
    stamps = [G.file_stamp(p) for p in (last_path, prev_path)]
    if asset_groups_path:
        findings["asset_groups"] = _asset_group_rows(asset_groups_path)
        arrays["asset_groups"] = RECONCILE_ARRAYS_OPTIONAL["asset_groups"]
        stamps.append(G.file_stamp(asset_groups_path))
    if search_campaigns_path:
        findings["search_campaigns"] = _window_rows(search_campaigns_path)
        arrays["search_campaigns"] = RECONCILE_ARRAYS_OPTIONAL["search_campaigns"]
        stamps.append(G.file_stamp(search_campaigns_path))
    findings["meta"]["reconciliation"] = R.build(findings, arrays, raw_stamps=stamps)
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description="Assemble the PMax momentum findings "
                                             "JSON from saved raw GAQL pulls.")
    ap.add_argument("--last-window", required=True, help="raw campaign results file for the last 14 days")
    ap.add_argument("--prev-window", required=True, help="raw campaign results file for the previous 14 days")
    ap.add_argument("--asset-groups", default=None,
                    help="M1.4 (optional): raw asset_group results file for the last 14 days "
                         "(campaign.id, asset_group.id breakdown) — powers asset-group concentration")
    ap.add_argument("--search-campaigns", default=None,
                    help="M1.4 (optional): raw Search-campaign results file for the last 14 days "
                         "(same shape as --last-window) — powers the cannibalization signal")
    ap.add_argument("--client-name", required=True)
    ap.add_argument("--account-id", required=True)
    ap.add_argument("--currency", required=True)
    ap.add_argument("--window-last", required=True, help='e.g. "2026-06-22 to 2026-07-05" — the dates used in the GAQL BETWEEN')
    ap.add_argument("--window-prev", required=True)
    ap.add_argument("--generated", default=None,
                    help="report date (YYYY-MM-DD); defaults to today — pass the "
                         "original date when re-assembling for byte-identical output")
    ap.add_argument("-o", "--output", required=True, help="findings JSON output path")
    args = ap.parse_args()

    meta = {"client_name": args.client_name, "account_id": args.account_id,
            "currency": args.currency, "window_last": args.window_last,
            "window_prev": args.window_prev,
            "generated": args.generated or datetime.date.today().isoformat()}
    try:
        findings = assemble(args.last_window, args.prev_window, meta,
                            asset_groups_path=args.asset_groups,
                            search_campaigns_path=args.search_campaigns)
    except (G.RawResultError, OSError) as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return 1

    Path(args.output).write_text(json.dumps(findings, ensure_ascii=False, indent=1))
    rec = findings["meta"]["reconciliation"]
    lw, pw = rec["last_window"], rec["prev_window"]
    print(f"Wrote {args.output}")
    print(f"  last_window: {lw['rows']} campaigns (cost {lw['sums']['cost']:,.2f} {args.currency}, "
          f"conv {lw['sums']['conversions']:,.1f})")
    print(f"  prev_window: {pw['rows']} campaigns (cost {pw['sums']['cost']:,.2f} {args.currency}, "
          f"conv {pw['sums']['conversions']:,.1f})")
    if "asset_groups" in rec:
        ag = rec["asset_groups"]
        print(f"  asset_groups: {ag['rows']} (campaign, asset group) rows "
              f"(cost {ag['sums']['cost']:,.2f} {args.currency})")
    if "search_campaigns" in rec:
        sc = rec["search_campaigns"]
        print(f"  search_campaigns: {sc['rows']} campaigns "
              f"(cost {sc['sums']['cost']:,.2f} {args.currency})")
    print("  reconciliation totals embedded — the builder verifies them on every run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
