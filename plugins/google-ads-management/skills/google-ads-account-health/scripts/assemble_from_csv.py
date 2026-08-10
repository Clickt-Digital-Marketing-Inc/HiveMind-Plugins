#!/usr/bin/env python3
"""Assemble the account-health findings JSON from a user-supplied CSV export —
the manual-input twin of assemble_findings.py (dual-input contract, HM-534).

Two Google Ads UI exports, joined by campaign/ad-group NAME (a CSV export
carries no numeric IDs unless the user adds an ID column, so name is the
join key on this path — health_core never assumes IDs are numeric).
`_shared/csv_input.load_csv_rows` parses each file (never the model); this
script merges them and embeds `meta.reconciliation` exactly like the MCP
assembler, so `health_core.load_findings` re-verifies the totals on load.

Two columns per CSV are NOT standard Google Ads UI report columns — the UI
has no single report exposing ad-group keyword counts or campaign negative
counts — so this path asks the user to hand-add them (documented in
references/account-health-filter.md). Honest by construction: a missing
column raises CsvInputError naming exactly what's absent.

Usage:
    python3 assemble_from_csv.py \
        --adgroups-csv "Ad groups.csv" --campaigns-csv "Campaigns.csv" \
        --client-name "Acme Corp" --account-id 123-456-7890 --currency CAD \
        --window-30d "2026-06-06 to 2026-07-05" \
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

import csv_input as C       # noqa: E402
import reconcile as R       # noqa: E402

sys.path.insert(0, str(HERE))
import health_core as core  # noqa: E402  (owns the reconcile contract)

ADGROUPS_COLUMN_MAP = {
    "campaign": {"aliases": ["Campaign"], "type": "str"},
    "ad_group": {"aliases": ["Ad group"], "type": "str"},
    "clicks": {"aliases": ["Clicks"], "type": "num"},
    "impressions": {"aliases": ["Impr.", "Impressions"], "type": "num"},
    "keyword_count": {"aliases": ["Ad group keywords (enabled)"], "type": "num"},
}
ADGROUPS_REQUIRED = ("campaign", "ad_group", "clicks", "impressions", "keyword_count")

CAMPAIGNS_COLUMN_MAP = {
    "campaign": {"aliases": ["Campaign"], "type": "str"},
    "status": {"aliases": ["Campaign state", "Status"], "type": "str"},
    "channel_type": {"aliases": ["Campaign type"], "type": "str"},
    "bidding_strategy_type": {"aliases": ["Bid strategy type"], "type": "str"},
    "conversions_30d": {"aliases": ["Conversions"], "type": "num"},
    "negative_count": {"aliases": ["Campaign negative keywords"], "type": "num"},
    # 30d window spend — drives campaign liveness (HM-603). Optional: legacy
    # exports without a Cost column degrade to 0 spend (liveness then keys off
    # status alone), never a hard failure.
    "cost": {"aliases": ["Cost"], "type": "num"},
}
CAMPAIGNS_REQUIRED = ("campaign", "status", "channel_type", "bidding_strategy_type",
                      "conversions_30d", "negative_count")

RECONCILE_ARRAYS = core.RECONCILE_ARRAYS

# Google Ads campaign-type UI labels -> the advertising_channel_type enum
# health_core expects (only PERFORMANCE_MAX/SEARCH matter to the checks;
# anything else passes through uppercased+underscored as a best effort).
_CHANNEL_ALIASES = {"PERFORMANCE MAX": "PERFORMANCE_MAX", "SEARCH": "SEARCH",
                    "DISPLAY": "DISPLAY", "VIDEO": "VIDEO", "DEMAND GEN": "DEMAND_GEN"}


def _channel_type(v: str) -> str:
    u = str(v or "").strip().upper()
    return _CHANNEL_ALIASES.get(u, u.replace(" ", "_"))


def _status(v: str) -> str:
    u = str(v or "").strip().upper()
    return "ENABLED" if u in ("ENABLED", "ELIGIBLE") else u


def assemble(adgroups_csv: str, campaigns_csv: str, meta: dict) -> dict:
    ag_rows, ag_stamp = C.load_csv_rows(adgroups_csv, ADGROUPS_COLUMN_MAP, ADGROUPS_REQUIRED)
    camp_rows, camp_stamp = C.load_csv_rows(campaigns_csv, CAMPAIGNS_COLUMN_MAP, CAMPAIGNS_REQUIRED)

    ad_groups = [{
        "campaign_id": r["campaign"], "campaign": r["campaign"],
        "ad_group_id": r["ad_group"], "ad_group": r["ad_group"],
        "keyword_count": r["keyword_count"], "clicks": r["clicks"], "impressions": r["impressions"],
    } for r in ag_rows]

    campaigns = [{
        "campaign_id": r["campaign"], "campaign": r["campaign"],
        "status": _status(r["status"]), "channel_type": _channel_type(r["channel_type"]),
        "bidding_strategy_type": str(r["bidding_strategy_type"] or "").strip().upper().replace(" ", "_"),
        "conversions_30d": r["conversions_30d"], "negative_count": r["negative_count"],
        "cost": r.get("cost", 0.0) or 0.0,
    } for r in camp_rows]

    meta = dict(meta)
    meta.setdefault("source", "user_csv")
    findings = {"meta": meta, "params": {}, "ad_groups": ad_groups, "campaigns": campaigns}
    findings["meta"]["reconciliation"] = R.build(
        findings, RECONCILE_ARRAYS, raw_stamps=[ag_stamp, camp_stamp])
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description="Assemble account-health findings JSON "
                                             "from a user-supplied Google Ads UI CSV export.")
    ap.add_argument("--adgroups-csv", required=True,
                    help="Ad groups report export, with a hand-added 'Ad group keywords (enabled)' column")
    ap.add_argument("--campaigns-csv", required=True,
                    help="Campaigns report export, with a hand-added 'Campaign negative keywords' column")
    ap.add_argument("--client-name", required=True)
    ap.add_argument("--account-id", required=True)
    ap.add_argument("--currency", required=True)
    ap.add_argument("--window-30d", required=True, help='e.g. "2026-06-06 to 2026-07-05" — the export date range')
    ap.add_argument("--generated", default=None,
                    help="report date (YYYY-MM-DD); defaults to today")
    ap.add_argument("-o", "--output", required=True, help="findings JSON output path")
    args = ap.parse_args()

    meta = {"client_name": args.client_name, "account_id": args.account_id,
            "currency": args.currency, "window_30d": args.window_30d,
            "generated": args.generated or datetime.date.today().isoformat()}
    try:
        findings = assemble(args.adgroups_csv, args.campaigns_csv, meta)
    except (C.CsvInputError, OSError) as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return 1

    Path(args.output).write_text(json.dumps(findings, ensure_ascii=False, indent=1))
    rec = findings["meta"]["reconciliation"]
    ag, cp = rec["ad_groups"], rec["campaigns"]
    print(f"Wrote {args.output}  (source=user_csv)")
    print(f"  ad_groups: {ag['rows']} (keywords {ag['sums']['keyword_count']:,.0f}, "
          f"impressions {ag['sums']['impressions']:,.0f}, clicks {ag['sums']['clicks']:,.0f})")
    print(f"  campaigns: {cp['rows']} (negatives {cp['sums']['negative_count']:,.0f}, "
          f"conversions(30d) {cp['sums']['conversions_30d']:,.2f})")
    print("  reconciliation totals embedded — the builder verifies them on every run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
