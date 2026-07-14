#!/usr/bin/env python3
"""Assemble PMax momentum findings from user-supplied Google Ads UI CSV exports
(the manual-input twin of assemble_findings.py / the MCP path).

Dual-input contract (google-ads-foundation/references/artifact-formats.md): the
CSV path must yield an IDENTICAL findings/model shape to the MCP path — pmax_core
cannot tell them apart except by the honest `meta.source = "user_csv"` label.
Uses the shared `_shared/csv_input.py` module (never hand-parses a CSV), so the
transcription-firewall + reconciliation discipline is the same on both paths.

One COLUMN_MAP covers all four possible exports this skill accepts (the two
campaign-level momentum windows, the asset-group breakdown, and the Search
snapshot) — each export only needs to carry the columns relevant to it; unmapped
optional columns are simply absent from the parsed rows.

Ask the user, in the Google Ads UI, for:
  - Campaigns report, filtered to Performance Max + Enabled, for the LAST 14-day
    window -> --last-window-csv (required)
  - the same report for the PREVIOUS 14-day window -> --prev-window-csv (required)
  - (M1.4, optional) Asset groups report for the same last-14-day window, with
    the "Asset group" and "Asset group ID" columns added -> --asset-groups-csv
  - (M1.4, optional) Campaigns report filtered to Search + Enabled, same last-14-
    day window -> --search-campaigns-csv
Every export needs "Campaign ID" added as a column (Columns -> Modify columns)
so campaign identity matches the GAQL path's campaign.id.

Usage:
    python3 assemble_findings_csv.py \
        --last-window-csv last14.csv --prev-window-csv prev14.csv \
        --client-name "Acme Corp" --account-id 123-456-7890 --currency CAD \
        --window-last "2026-06-22 to 2026-07-05" \
        --window-prev "2026-06-08 to 2026-06-21" \
        -o findings.json

    # with the optional M1.4 structural exports:
    python3 assemble_findings_csv.py \
        --last-window-csv last14.csv --prev-window-csv prev14.csv \
        --asset-groups-csv asset_groups.csv --search-campaigns-csv search14.csv \
        --client-name "Acme Corp" --account-id 123-456-7890 --currency CAD \
        --window-last "2026-06-22 to 2026-07-05" --window-prev "2026-06-08 to 2026-06-21" \
        -o findings.json

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

import csv_input as CSV     # noqa: E402
import gaql_raw as G        # noqa: E402
import reconcile as R       # noqa: E402

sys.path.insert(0, str(HERE))
import pmax_core as core    # noqa: E402  (owns the reconcile contract)

# The skill's own column_map (dual-input checklist, artifact-formats.md): one
# entry per logical field, aliases covering the Google Ads UI export spellings.
# Campaign-level exports (last/prev/search) only need the first block; the
# asset-group export additionally needs asset_group_id/asset_group.
COLUMN_MAP = {
    "campaign_id":       {"aliases": ["Campaign ID", "Campaign Id"], "type": "num"},
    "campaign":          {"aliases": ["Campaign", "Campaign name"], "type": "str"},
    "impressions":       {"aliases": ["Impr.", "Impressions"], "type": "num"},
    "clicks":            {"aliases": ["Clicks", "Interactions"], "type": "num"},
    "cost":              {"aliases": ["Cost"], "type": "num"},
    "conversions":       {"aliases": ["Conversions", "Conv."], "type": "num"},
    "conversions_value": {"aliases": ["Conv. value", "Conversion value", "Total conv. value"], "type": "num"},
    "asset_group_id":    {"aliases": ["Asset group ID", "Asset Group ID"], "type": "num"},
    "asset_group":       {"aliases": ["Asset group", "Asset group name"], "type": "str"},
}

CAMPAIGN_FIELDS = ("campaign_id", "campaign", "impressions", "clicks", "cost",
                   "conversions", "conversions_value")
ASSET_GROUP_FIELDS = CAMPAIGN_FIELDS + ("asset_group_id", "asset_group")
_SUMS = ["cost", "clicks", "impressions", "conversions", "conversions_value"]


def _campaign_rows(csv_path: str) -> tuple[list, dict]:
    return CSV.load_csv_rows(csv_path, COLUMN_MAP, required_fields=CAMPAIGN_FIELDS)


def _asset_group_rows(csv_path: str) -> tuple[list, dict]:
    return CSV.load_csv_rows(csv_path, COLUMN_MAP, required_fields=ASSET_GROUP_FIELDS)


def assemble(*, last_csv: str, prev_csv: str, meta: dict,
            asset_groups_csv: str | None = None,
            search_csv: str | None = None) -> dict:
    last_rows, last_stamp = _campaign_rows(last_csv)
    prev_rows, prev_stamp = _campaign_rows(prev_csv)
    findings = {"meta": dict(meta), "params": {},
                "last_window": last_rows, "prev_window": prev_rows}
    arrays = dict(core.RECONCILE_ARRAYS)
    stamps = [last_stamp, prev_stamp]
    if asset_groups_csv:
        ag_rows, ag_stamp = _asset_group_rows(asset_groups_csv)
        findings["asset_groups"] = ag_rows
        arrays["asset_groups"] = core.RECONCILE_ARRAYS_OPTIONAL["asset_groups"]
        stamps.append(ag_stamp)
    if search_csv:
        sc_rows, sc_stamp = _campaign_rows(search_csv)
        findings["search_campaigns"] = sc_rows
        arrays["search_campaigns"] = core.RECONCILE_ARRAYS_OPTIONAL["search_campaigns"]
        stamps.append(sc_stamp)
    findings["meta"].setdefault("source", "user_csv")
    findings["meta"]["reconciliation"] = R.build(findings, arrays, raw_stamps=stamps)
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description="Assemble the PMax momentum findings "
                                             "JSON from user-supplied Google Ads UI CSV exports.")
    ap.add_argument("--last-window-csv", required=True)
    ap.add_argument("--prev-window-csv", required=True)
    ap.add_argument("--asset-groups-csv", default=None,
                    help="M1.4 (optional): Asset groups export for the last 14 days")
    ap.add_argument("--search-campaigns-csv", default=None,
                    help="M1.4 (optional): Search-campaigns export for the last 14 days")
    ap.add_argument("--client-name", required=True)
    ap.add_argument("--account-id", required=True)
    ap.add_argument("--currency", required=True)
    ap.add_argument("--window-last", required=True)
    ap.add_argument("--window-prev", required=True)
    ap.add_argument("--generated", default=None)
    ap.add_argument("-o", "--output", required=True, help="findings JSON output path")
    args = ap.parse_args()

    meta = {"client_name": args.client_name, "account_id": args.account_id,
            "currency": args.currency, "window_last": args.window_last,
            "window_prev": args.window_prev,
            "generated": args.generated or datetime.date.today().isoformat()}
    try:
        findings = assemble(last_csv=args.last_window_csv, prev_csv=args.prev_window_csv,
                            meta=meta, asset_groups_csv=args.asset_groups_csv,
                            search_csv=args.search_campaigns_csv)
    except (CSV.CsvInputError, OSError) as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return 1

    Path(args.output).write_text(json.dumps(findings, ensure_ascii=False, indent=1))
    rec = findings["meta"]["reconciliation"]
    lw, pw = rec["last_window"], rec["prev_window"]
    print(f"Wrote {args.output}  (source: user_csv)")
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
        print(f"  search_campaigns: {sc['rows']} campaigns (cost {sc['sums']['cost']:,.2f} {args.currency})")
    print("  reconciliation totals embedded — the builder verifies them on every run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
