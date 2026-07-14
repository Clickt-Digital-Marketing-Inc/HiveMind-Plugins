#!/usr/bin/env python3
"""Assemble the performance-report findings JSON from user-supplied CSV exports —
the manual-input twin of assemble_findings.py (dual-input contract, HM-534).

Two Google Ads UI **Campaigns** report exports, same columns, one for the
reporting window and one for the prior window (mirroring the MCP path's two
GAQL pulls): Campaigns table -> add columns Impr., Clicks, Cost, Conversions,
Conv. value, Search impr. share, Search lost IS (budget), Search lost IS
(rank) -> Download -> CSV, once per window.

UI exports carry no campaign.id column, so rows are joined by CAMPAIGN NAME
(assumed unique per account — the same assumption the Google Ads UI itself
makes when you search/filter by campaign). `_shared/csv_input.py` is the only
thing that turns the file into typed rows — the model never transcribes the
file's numbers — and control totals are embedded as meta.reconciliation via
the same `perf_core.RECONCILE_ARRAYS` contract the MCP-path assembler uses, so
BOTH paths verify identically and yield an IDENTICAL compute_model() shape
(only the honest meta.source label differs: "user_csv" vs "mcp").

Known CSV-path limitation (say so, never silently coerce): the shared
`csv_input` numeric/pct converters treat an absent cell ('--', blank) as 0.0,
never None. The MCP path instead passes a PMax/Display campaign's Search-IS
fields through as null (never 0) because the API leaves them unpopulated. A
CSV export cannot distinguish "0% impression share" from "not applicable to
this campaign type" — a PMax/Display row's IS columns will read as 0% here,
not "—". Tell the user this when a CSV-assembled report includes PMax/Display
campaigns with search-IS columns.

--no-value-campaigns takes comma-separated CAMPAIGN NAMES (not ids — UI
exports don't carry campaign.id) whose Conv. value is not a tracked revenue
signal; their conversions_value keys are omitted so they land as status
"no_value" instead of a fabricated ROAS, exactly like the MCP path's flag.

Usage:
    python3 assemble_from_csv.py \
        --campaigns-period period.csv --campaigns-prior prior.csv \
        --client-name "Acme Corp" --account-id 123-456-7890 --currency CAD \
        --period "2026-06-01 to 2026-06-30" --prior-period "2026-05-01 to 2026-05-31" \
        --no-value-campaigns "Lead Gen | No Revenue" \
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
sys.path.insert(0, str(HERE))

import csv_input as CI      # noqa: E402
import reconcile as R       # noqa: E402
import perf_core as core    # noqa: E402  (owns the reconcile contract)

# One column_map for both period + prior exports (same UI report, two windows).
# "campaign" anchors the header scan; cost/clicks/conversions are required so a
# genuinely wrong export (missing metrics) fails loudly and names the column.
COLUMN_MAP = {
    "campaign":    {"aliases": ["Campaign", "Campaign name"], "type": "str"},
    "status":      {"aliases": ["Campaign state", "Status"], "type": "str"},
    "channel":     {"aliases": ["Campaign type", "Channel"], "type": "str"},
    "impressions": {"aliases": ["Impr.", "Impressions"], "type": "num"},
    "clicks":      {"aliases": ["Clicks"], "type": "num"},
    "cost":        {"aliases": ["Cost"], "type": "num"},
    "conversions": {"aliases": ["Conversions"], "type": "num"},
    "conversions_value": {"aliases": ["Conv. value", "Conversion value", "All conv. value"],
                          "type": "num"},
    "search_impression_share": {"aliases": ["Search impr. share", "Search IS"], "type": "pct"},
    "search_budget_lost_is": {"aliases": ["Search lost IS (budget)", "Search Lost IS (budget)"],
                              "type": "pct"},
    "search_rank_lost_is": {"aliases": ["Search lost IS (rank)", "Search Lost IS (rank)"],
                            "type": "pct"},
}
REQUIRED_FIELDS = ("campaign", "cost", "clicks", "conversions")


def _slot(merged: dict, order: list, name: str) -> dict:
    if name not in merged:
        merged[name] = {
            "campaign_id": name, "campaign": name, "status": "", "channel": "",
            "impressions": 0.0, "clicks": 0.0, "cost": 0.0,
            "conversions": 0.0, "conversions_value": 0.0,
            "search_impression_share": None, "search_budget_lost_is": None,
            "search_rank_lost_is": None,
            "prior_cost": 0.0, "prior_conversions": 0.0, "prior_conversions_value": 0.0,
            "prior_impressions": 0.0, "prior_clicks": 0.0,
        }
        order.append(name)
    return merged[name]


def assemble(period_path: str, prior_path: str, meta: dict,
             no_value_names=frozenset()) -> dict:
    period_rows, period_stamp = CI.load_csv_rows(period_path, COLUMN_MAP, REQUIRED_FIELDS)
    prior_rows, prior_stamp = CI.load_csv_rows(prior_path, COLUMN_MAP, REQUIRED_FIELDS)
    has_value = any("conversions_value" in r for r in period_rows + prior_rows)
    is_fields = ("search_impression_share", "search_budget_lost_is", "search_rank_lost_is")

    merged: dict = {}
    order: list = []

    for r in period_rows:
        m = _slot(merged, order, r["campaign"])
        m["status"] = r.get("status") or m["status"]
        m["channel"] = r.get("channel") or m["channel"]
        m["impressions"] += r.get("impressions", 0.0)
        m["clicks"] += r.get("clicks", 0.0)
        m["cost"] += r.get("cost", 0.0)
        m["conversions"] += r.get("conversions", 0.0)
        if "conversions_value" in r:
            m["conversions_value"] += r["conversions_value"]
        for f in is_fields:
            if m[f] is None and f in r:
                m[f] = r[f]

    for r in prior_rows:
        m = _slot(merged, order, r["campaign"])
        m["prior_impressions"] += r.get("impressions", 0.0)
        m["prior_clicks"] += r.get("clicks", 0.0)
        m["prior_cost"] += r.get("cost", 0.0)
        m["prior_conversions"] += r.get("conversions", 0.0)
        if "conversions_value" in r:
            m["prior_conversions_value"] += r["conversions_value"]

    campaigns = []
    for name in order:
        m = merged[name]
        if not has_value or name in no_value_names:
            del m["conversions_value"]
            del m["prior_conversions_value"]
        campaigns.append(m)

    findings = {"meta": dict(meta), "params": {}, "campaigns": campaigns}
    findings["meta"].setdefault("source", "user_csv")
    findings["meta"]["reconciliation"] = R.build(
        findings, core.RECONCILE_ARRAYS, raw_stamps=[period_stamp, prior_stamp])
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Assemble performance-report findings JSON from two Google Ads UI "
                    "Campaigns-report CSV exports (reporting window + prior window).")
    ap.add_argument("--campaigns-period", required=True, help="UI export for the reporting window")
    ap.add_argument("--campaigns-prior", required=True, help="UI export for the prior window (same columns)")
    ap.add_argument("--client-name", required=True)
    ap.add_argument("--account-id", required=True)
    ap.add_argument("--currency", required=True)
    ap.add_argument("--period", required=True, help='e.g. "2026-06-01 to 2026-06-30"')
    ap.add_argument("--prior-period", required=True)
    ap.add_argument("--no-value-campaigns", default="",
                    help="comma-separated CAMPAIGN NAMES whose conversion value is NOT a "
                         "tracked revenue signal — their conversions_value keys are omitted "
                         "(status no_value) instead of reporting a fabricated ROAS of 0")
    ap.add_argument("--generated", default=None,
                    help="report date (YYYY-MM-DD); defaults to today")
    ap.add_argument("-o", "--output", required=True, help="findings JSON output path")
    args = ap.parse_args()

    meta = {"client_name": args.client_name, "account_id": args.account_id,
            "currency": args.currency, "period": args.period,
            "prior_period": args.prior_period,
            "generated": args.generated or datetime.date.today().isoformat()}
    no_value_names = frozenset(s.strip() for s in args.no_value_campaigns.split(",") if s.strip())
    try:
        findings = assemble(args.campaigns_period, args.campaigns_prior, meta,
                            no_value_names=no_value_names)
    except CI.CsvInputError as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return 1

    Path(args.output).write_text(json.dumps(findings, ensure_ascii=False, indent=1))
    rec = findings["meta"]["reconciliation"]
    cm = rec["campaigns"]
    print(f"Wrote {args.output}")
    print(f"  source: user_csv (Google Ads UI exports, never an API pull)")
    print(f"  campaigns: {cm['rows']} (spend {cm['sums']['cost']:,.2f} {args.currency}, "
          f"revenue {cm['sums']['conversions_value']:,.2f} {args.currency})")
    if no_value_names:
        print(f"  no-value campaigns (value keys omitted): {', '.join(sorted(no_value_names))}")
    print("  reconciliation totals embedded — the builder verifies them on every run")
    print("  NOTE: Search-IS columns read '0%' for PMax/Display rows in a CSV export (the "
          "UI export cannot express 'not applicable' the way the MCP null pass-through does)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
