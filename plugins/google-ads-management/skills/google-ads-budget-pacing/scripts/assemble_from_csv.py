#!/usr/bin/env python3
"""Assemble the budget & pacing findings JSON from user-supplied Google Ads UI
CSV exports — the CSV twin of assemble_findings.py (HM-535 dual-input parity).

The transcription firewall for the CSV path: numbers go file -> _shared/csv_input
parser -> findings without ever passing through a token stream, exactly like the
MCP path. Two exports are needed (the same two windows the MCP pulls cover):

  --window  a Campaigns report for the reporting window (e.g. last 30 days) with
            Campaign, Campaign type, Cost, Conversions, Budget, and the two
            Search-lost-IS columns.
  --mtd     a Campaigns report for month-to-date (date range = this month) with
            Campaign, Cost.

Usage:
    python3 assemble_from_csv.py \
        --window campaigns_last30.csv --mtd campaigns_mtd.csv \
        --client-name "Acme Corp" --account-id 123-456-7890 --currency CAD \
        --period "last 30 days" \
        --monthly-goal 30000 --days-elapsed 15 --days-in-month 30 \
        -o findings.json

Joins the two exports on the Campaign name (UI exports don't carry a numeric
campaign id) — one findings row per campaign name in the window export, exactly
what budget_core expects. `daily_budget` and the two lost-IS columns preserve the
MCP path's null semantics: a blank/dash/"Shared"-style cell is missing data
(-> no daily_budget key -> status "no_budget" in the core; lost-IS -> null), NOT
zero — `csv_input`'s generic "num"/"pct" coercion would default absent cells to
0.0, so those three fields are read as raw strings here and parsed by hand.

Exit codes: 0 success, 1 usage/validation error.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parents[2]
sys.path.insert(0, str(PLUGIN_ROOT / "_shared"))

import csv_input as C           # noqa: E402
import reconcile as R           # noqa: E402

sys.path.insert(0, str(HERE))
import budget_core as core      # noqa: E402  (owns the reconcile contract)

# Window export: one row per campaign for the reporting window. daily_budget and
# the two lost-IS columns are read as "str" (not "num"/"pct") so a blank/dash/
# "Shared"-only cell is distinguishable from an explicit 0 — see module docstring.
WINDOW_COLUMN_MAP = {
    "campaign": {"aliases": ["Campaign"], "type": "str"},
    "channel": {"aliases": ["Campaign type", "Campaign Type", "Advertising channel type"],
                "type": "str"},
    "cost": {"aliases": ["Cost"], "type": "num"},
    "conversions": {"aliases": ["Conversions"], "type": "num"},
    "daily_budget": {"aliases": ["Budget", "Daily budget", "Budget amount"], "type": "str"},
    "search_budget_lost_is": {"aliases": ["Search lost IS (budget)",
                                          "Search Impr. share lost to budget",
                                          "Search budget lost IS"], "type": "str"},
    "search_rank_lost_is": {"aliases": ["Search lost IS (rank)",
                                        "Search Impr. share lost to rank",
                                        "Search rank lost IS"], "type": "str"},
}
WINDOW_REQUIRED = ("campaign", "cost", "conversions")

# Month-to-date export: same report, date range = this month, Cost only.
MTD_COLUMN_MAP = {
    "campaign": {"aliases": ["Campaign"], "type": "str"},
    "mtd_spend": {"aliases": ["Cost"], "type": "num"},
}
MTD_REQUIRED = ("campaign", "mtd_spend")

# Cell values meaning "absent" — mirrors _shared/csv_input.py's _ABSENT set (kept
# local: a small, stable, documented convention rather than importing a private
# helper across the module boundary).
_ABSENT = {"", "-", "--", "—", "–"}


def _num_or_none(v):
    """Raw UI cell -> float, or None when absent/unparseable (missing, not zero).

    Tolerates thousands commas, a trailing '%' (the lost-IS columns render as
    percentages in the UI export), and a defensive currency prefix ('CA$300.00',
    '$5') -- mirrors _shared/csv_input.py's "num" coercion, minus the absent-cell
    default (this helper returns None, not 0.0, so a missing daily_budget cell
    stays "no budget data" rather than becoming a false $0). A non-numeric cell
    (e.g. a shared-budget campaign showing "Shared") is also None, never a crash."""
    s = str(v or "").strip()
    if s in _ABSENT:
        return None
    s = s.replace(",", "").replace(" ", " ").strip().rstrip("%").strip()
    s = re.sub(r"^[A-Za-z]{0,3}\$", "", s)
    try:
        x = float(s)
    except ValueError:
        return None
    return x


def _pct_or_none(v):
    """Percent-scale raw cell -> fraction, or None when absent (mirrors
    csv_input._pct's percent/fraction rule, but preserves None for missing)."""
    x = _num_or_none(v)
    if x is None:
        return None
    return x / 100.0 if ("%" in str(v) or x > 1) else x


def assemble(window_csv: str, mtd_csv: str, meta: dict) -> dict:
    window_rows, window_stamp = C.load_csv_rows(window_csv, WINDOW_COLUMN_MAP, WINDOW_REQUIRED)
    mtd_rows, mtd_stamp = C.load_csv_rows(mtd_csv, MTD_COLUMN_MAP, MTD_REQUIRED)

    mtd: dict = {}
    for r in mtd_rows:
        name = r["campaign"]
        mtd[name] = mtd.get(name, 0.0) + r["mtd_spend"]

    campaigns = []
    seen = set()
    for r in window_rows:
        name = r["campaign"]
        if not name or name in seen:
            continue   # a window export is one row per campaign already; guard dup headers
        seen.add(name)
        c = {"campaign_id": name, "campaign": name, "channel": r.get("channel", "")}
        daily = _num_or_none(r.get("daily_budget"))
        if daily is not None:
            c["daily_budget"] = daily
        c.update({"cost": r["cost"], "mtd_spend": mtd.get(name, 0.0),
                  "conversions": r["conversions"],
                  "search_budget_lost_is": _pct_or_none(r.get("search_budget_lost_is")),
                  "search_rank_lost_is": _pct_or_none(r.get("search_rank_lost_is"))})
        campaigns.append(c)

    missing_mtd = [n for n in mtd if n not in seen]
    if missing_mtd:
        sys.stderr.write(f"NOTE: {len(missing_mtd)} campaign(s) in the MTD export are "
                         f"absent from the window export — ignored "
                         f"({', '.join(sorted(missing_mtd))})\n")

    findings = {"meta": dict(meta, source="user_csv"), "params": {}, "campaigns": campaigns}
    findings["meta"]["reconciliation"] = R.build(
        findings, core.RECONCILE_ARRAYS, raw_stamps=[window_stamp, mtd_stamp])
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Assemble the budget & pacing findings JSON from Google Ads UI CSV exports.")
    ap.add_argument("--window", required=True,
                    help="Campaigns report CSV for the reporting window (e.g. last 30 days)")
    ap.add_argument("--mtd", required=True,
                    help="Campaigns report CSV for month-to-date (date range = this month)")
    ap.add_argument("--client-name", required=True)
    ap.add_argument("--account-id", required=True)
    ap.add_argument("--currency", required=True)
    ap.add_argument("--period", required=True,
                    help='window label, e.g. "last 30 days" — the window used in the CSV export')
    ap.add_argument("--monthly-goal", type=float, default=0.0,
                    help="account monthly spend goal (ask the user; 0/omitted => pacing reads n/a)")
    ap.add_argument("--days-elapsed", type=int, required=True,
                    help="days of the month elapsed at the report date")
    ap.add_argument("--days-in-month", type=int, required=True)
    ap.add_argument("--generated", default=None,
                    help="report date (YYYY-MM-DD); defaults to today")
    ap.add_argument("-o", "--output", required=True, help="findings JSON output path")
    args = ap.parse_args()

    meta = {"client_name": args.client_name, "account_id": args.account_id,
            "currency": args.currency, "period": args.period,
            "generated": args.generated or datetime.date.today().isoformat(),
            "monthly_goal": args.monthly_goal, "days_elapsed": args.days_elapsed,
            "days_in_month": args.days_in_month}
    try:
        findings = assemble(args.window, args.mtd, meta)
    except (C.CsvInputError, OSError) as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return 1

    Path(args.output).write_text(json.dumps(findings, ensure_ascii=False, indent=1))
    rec = findings["meta"]["reconciliation"]
    cp = rec["campaigns"]
    no_budget = sum(1 for c in findings["campaigns"] if "daily_budget" not in c)
    print(f"Wrote {args.output}")
    print(f"  campaigns: {cp['rows']} ({no_budget} without budget data; "
          f"cost {cp['sums']['cost']:,.2f} {args.currency}, "
          f"MTD {cp['sums']['mtd_spend']:,.2f}, "
          f"conversions {cp['sums']['conversions']:,.2f})")
    print("  meta.source=user_csv — reconciliation totals embedded (verified on every build)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
