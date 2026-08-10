#!/usr/bin/env python3
"""Assemble the budget & pacing findings JSON from saved raw GAQL pulls (script-only).

The transcription firewall for this skill: the three search_search pulls are
saved verbatim to files (auto-saved by the harness when large, copied verbatim
when small) and THIS script — never the model — turns them into the findings
JSON. Metric values go raw file -> parser -> findings without ever passing
through a token stream, and control totals are embedded as
meta.reconciliation so budget_core hard-fails if the findings are later
edited or were produced any other way.

Usage:
    python3 assemble_findings.py \
        --performance tool-results/perf30.txt \
        --budgets tool-results/budgets.txt \
        --mtd tool-results/mtd.txt \
        --client-name "Acme Corp" --account-id 123-456-7890 --currency CAD \
        --period "last 30 days" \
        --monthly-goal 30000 --days-elapsed 15 --days-in-month 30 \
        -o findings.json

Aggregates performance rows by campaign.id — one findings row per campaign,
exactly what budget_core expects — summing cost/conversions (name, channel and
the lost-IS fractions are point-in-time, taken from the first occurrence),
then joins daily_budget (budgets pull) and mtd_spend (THIS_MONTH pull) on the
same id. Campaigns absent from the budgets pull get NO daily_budget key ->
status "no_budget" in the core. Lost-IS absent/null (PMax/Display) passes
through as null.

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

import gaql_raw as G          # noqa: E402
import reconcile as R         # noqa: E402
from render import model as Rm  # noqa: E402  (meta.assumptions — HM-604)

sys.path.insert(0, str(HERE))
import budget_core as core    # noqa: E402  (owns the reconcile contract)

# The two lost-IS fields are in the documented pull but NOT required per-row:
# they are null for PMax/Display and may be omitted from saved rows entirely —
# absent passes through as null (the core never IS-buckets those campaigns).
PERF_FIELDS = ("campaign.id", "campaign.name", "campaign.advertising_channel_type",
               "campaign.status", "metrics.cost_micros", "metrics.conversions")
BLIS_FIELD = "metrics.search_budget_lost_impression_share"
RLIS_FIELD = "metrics.search_rank_lost_impression_share"
# campaign_budget.explicitly_shared is in the documented pull but unused here.
BUDGET_FIELDS = ("campaign.id", "campaign_budget.amount_micros")
MTD_FIELDS = ("campaign.id", "metrics.cost_micros")

# Control totals verified by budget_core.load_findings on every build; the
# contract (which arrays, which fields) is owned by the core.
RECONCILE_ARRAYS = core.RECONCILE_ARRAYS


def _frac(v):
    """0–1 impression-share fraction, or None when null/absent (PMax/Display)."""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def assemble(perf_path: str, budgets_path: str, mtd_path: str, meta: dict) -> dict:
    perf = G.load_rows(perf_path, require_fields=PERF_FIELDS)
    budget_rows = G.load_rows(budgets_path, require_fields=BUDGET_FIELDS)
    mtd_rows = G.load_rows(mtd_path, require_fields=MTD_FIELDS)

    # daily budget per campaign id (first occurrence wins).
    budgets: dict = {}
    for r in budget_rows:
        cid = r.get("campaign.id")
        if cid not in budgets:
            budgets[cid] = G.micros(r.get("campaign_budget.amount_micros"))

    # month-to-date spend per campaign id (summed).
    mtd: dict = {}
    for r in mtd_rows:
        cid = r.get("campaign.id")
        mtd[cid] = mtd.get(cid, 0.0) + G.micros(r.get("metrics.cost_micros"))

    # Performance aggregated to one row per campaign (a segment could split a
    # campaign into several raw rows; sums are preserved, name/channel/IS are
    # point-in-time from the first occurrence).
    merged: dict = {}
    order: list = []
    for r in perf:
        cid = r.get("campaign.id")
        if cid not in merged:
            merged[cid] = {"campaign_id": cid,
                           "campaign": r.get("campaign.name") or "",
                           "channel": r.get("campaign.advertising_channel_type") or "",
                           # campaign.status (ENABLED/PAUSED/REMOVED) — point-in-
                           # time from the first occurrence, like name/channel.
                           # Feeds liveness (HM-603); non-numeric, so it is not a
                           # reconciled field.
                           "campaign_status": r.get("campaign.status") or "",
                           "cost": 0.0, "conversions": 0.0,
                           "search_budget_lost_is": _frac(r.get(BLIS_FIELD)),
                           "search_rank_lost_is": _frac(r.get(RLIS_FIELD))}
            order.append(cid)
        m = merged[cid]
        m["cost"] += G.micros(r.get("metrics.cost_micros"))
        m["conversions"] += G.num(r.get("metrics.conversions"))

    campaigns = []
    for cid in order:
        m = merged[cid]
        c = {"campaign_id": m["campaign_id"], "campaign": m["campaign"],
             "channel": m["channel"], "campaign_status": m["campaign_status"]}
        if cid in budgets:
            c["daily_budget"] = round(budgets[cid], 6)
        c.update({"cost": round(m["cost"], 6),
                  "mtd_spend": round(mtd.get(cid, 0.0), 6),
                  "conversions": m["conversions"],
                  "search_budget_lost_is": m["search_budget_lost_is"],
                  "search_rank_lost_is": m["search_rank_lost_is"]})
        campaigns.append(c)

    for label, ids in (("budgets", [c for c in budgets if c not in merged]),
                       ("MTD", [c for c in mtd if c not in merged])):
        if ids:
            sys.stderr.write(f"NOTE: {len(ids)} campaign id(s) in the {label} pull are "
                             f"absent from the performance pull — ignored "
                             f"({', '.join(str(i) for i in ids)})\n")

    findings = {"meta": meta, "params": {}, "campaigns": campaigns}
    findings["meta"]["reconciliation"] = R.build(
        findings, RECONCILE_ARRAYS,
        raw_stamps=[G.file_stamp(p) for p in (perf_path, budgets_path, mtd_path)])
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description="Assemble the budget & pacing findings "
                                             "JSON from saved raw GAQL pulls.")
    ap.add_argument("--performance", required=True,
                    help="raw campaign performance + impression share (30d) results file")
    ap.add_argument("--budgets", required=True,
                    help="raw campaign daily-budgets results file")
    ap.add_argument("--mtd", required=True,
                    help="raw month-to-date spend (THIS_MONTH) results file")
    ap.add_argument("--client-name", required=True)
    ap.add_argument("--account-id", required=True)
    ap.add_argument("--currency", required=True)
    ap.add_argument("--period", required=True,
                    help='window label, e.g. "last 30 days" — the window used in the GAQL condition')
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
                    help="report date (YYYY-MM-DD); defaults to today — pass the "
                         "original date when re-assembling for byte-identical output")
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
        findings = assemble(args.performance, args.budgets, args.mtd, meta)
    except (G.RawResultError, OSError) as e:
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
    print("  reconciliation totals embedded — the builder verifies them on every run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
