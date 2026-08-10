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
0.0, so those three fields are read as raw strings here and re-parsed through
`csv_input.parse_num(v, None)`: the same locale-aware parser, None default.

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

import csv_input as C           # noqa: E402
import reconcile as R           # noqa: E402
from render import model as Rm  # noqa: E402  (meta.assumptions — HM-604)

sys.path.insert(0, str(HERE))
import budget_core as core      # noqa: E402  (owns the reconcile contract)

# Window export: one row per campaign for the reporting window. daily_budget and
# the two lost-IS columns are read as "str" (not "num"/"pct") so a blank/dash/
# "Shared"-only cell is distinguishable from an explicit 0 — see module docstring.
WINDOW_COLUMN_MAP = {
    "campaign": {"aliases": ["Campaign"], "type": "str"},
    "channel": {"aliases": ["Campaign type", "Campaign Type", "Advertising channel type"],
                "type": "str"},
    # campaign.status twin (HM-603 liveness): the UI export's "Campaign state"
    # column. Optional — a column-less export omits it (-> ""), which reads as
    # not-ENABLED; a live-spending campaign is then recently_active, still scored.
    "campaign_status": {"aliases": ["Campaign state", "Campaign status", "Status"],
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


def _num_or_none(v):
    """Raw UI cell -> float, or None when absent/unparseable (missing, not zero).

    Delegates to `_shared/csv_input.parse_num` — the ONE number parser — with
    `default=None`, so a missing daily_budget cell stays "no budget data"
    rather than becoming a false $0 and a non-numeric cell (e.g. a
    shared-budget campaign showing "Shared") is None, never a crash. This was
    a local re-derivation until HM-778: the shared parser learned the locale
    number formats and the clone did not, so within ONE findings file the
    "num" columns of an fr/de export parsed correctly while the columns routed
    through here (daily_budget, both lost-IS) came out 100x off or dropped."""
    return C.parse_num(v, None)


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
        c = {"campaign_id": name, "campaign": name, "channel": r.get("channel", ""),
             "campaign_status": r.get("campaign_status") or ""}
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
    ap.add_argument("--monthly-goal-source", choices=("client", "proxy"), default=None,
                    help="basis for --monthly-goal: 'client' if the client stated it directly, "
                         "'proxy' if it is derived (e.g. Sigma of daily budgets x 31) — stamps "
                         "meta.assumptions so every report format marks the goal honestly. "
                         "Omit only when --monthly-goal is 0 (pacing n/a, nothing to label).")
    ap.add_argument("--monthly-goal-note", default="",
                    help="free-text basis note, e.g. 'proxy: Sigma daily budgets x 31 days' "
                         "(required with --monthly-goal-source=proxy)")
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
    if args.monthly_goal_source:
        if args.monthly_goal_source == "proxy" and not args.monthly_goal_note:
            sys.stderr.write("ERROR: --monthly-goal-note is required when "
                             "--monthly-goal-source=proxy\n")
            return 1
        basis = "client_confirmed" if args.monthly_goal_source == "client" else "proxy"
        note = args.monthly_goal_note or (
            "client-confirmed monthly spend goal" if basis == "client_confirmed" else "")
        Rm.add_assumption(meta, "monthly_goal", args.monthly_goal, basis, note)
    elif args.monthly_goal:
        sys.stderr.write(
            "WARN: --monthly-goal was supplied without --monthly-goal-source — the goal's "
            "basis (client-confirmed vs a proxy estimate) is UNVERIFIED and will not carry a "
            "provenance marker. Pass --monthly-goal-source client|proxy.\n")
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
