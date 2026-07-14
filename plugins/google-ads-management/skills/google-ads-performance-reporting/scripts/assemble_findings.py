#!/usr/bin/env python3
"""Assemble the performance-report findings JSON from saved raw GAQL pulls (script-only).

The transcription firewall for this skill: the two campaign pulls (reporting
window + prior window, same query) are saved verbatim to files (auto-saved by
the harness when large, copied verbatim when small) and THIS script — never the
model — turns them into the findings JSON. Metric values go raw file -> parser
-> findings without ever passing through a token stream, and control totals are
embedded as meta.reconciliation so perf_core hard-fails if the findings are
later edited or were produced any other way.

Usage:
    python3 assemble_findings.py \
        --campaigns-period tool-results/period.txt \
        --campaigns-prior tool-results/prior.txt \
        --client-name "Acme Corp" --account-id 123-456-7890 --currency CAD \
        --period "2026-06-01 to 2026-06-30" \
        --prior-period "2026-05-01 to 2026-05-31" \
        -o findings.json

Pass the SAME windows used in the GAQL conditions for the period labels.
Aggregates each window per campaign.id — the same key perf_core dedupes by —
and joins the prior window into each campaign's prior_* fields. A campaign
missing from a window defaults that window's metrics to 0 (prior-only campaigns
survive as zero-current rows). Impression-share fields are passed through as
null when the API leaves them unpopulated (PMax/Display) — never coerced to 0.

--no-value-campaigns takes comma-separated campaign ids whose conversion VALUE
is not tracked (e.g. lead-gen): their conversions_value / prior_conversions_value
keys are omitted so perf_core reports them as status="no_value" instead of a
fabricated ROAS of 0. This is a labeling judgment, not a number — the values
themselves still never pass through the model.

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
import perf_core as core    # noqa: E402  (owns the reconcile contract)

# metrics.ctr is in the documented pull but not required here — CTR is always
# recomputed by the core from the summed clicks/impressions. The three
# impression-share fields are requested too but NOT required per-row: the API
# leaves them unpopulated for PMax/Display, so they are read with .get() and
# passed through as null (never coerced to 0).
PERIOD_FIELDS = ("campaign.id", "campaign.name", "campaign.advertising_channel_type",
                 "campaign.status", "metrics.impressions", "metrics.clicks",
                 "metrics.cost_micros", "metrics.conversions", "metrics.conversions_value")
PRIOR_FIELDS = ("campaign.id", "metrics.impressions", "metrics.clicks",
                "metrics.cost_micros", "metrics.conversions", "metrics.conversions_value")
# (raw dotted field, findings key) for the pass-through impression-share fractions
IS_FIELDS = (("metrics.search_impression_share", "search_impression_share"),
             ("metrics.search_budget_lost_impression_share", "search_budget_lost_is"),
             ("metrics.search_rank_lost_impression_share", "search_rank_lost_is"))

# Control totals verified by perf_core.load_findings on every build; the
# contract (which arrays, which fields) is owned by the core.
RECONCILE_ARRAYS = core.RECONCILE_ARRAYS


def _opt(row: dict, field: str):
    """Optional 0-1 fraction: None when unpopulated (PMax/Display), else float."""
    v = row.get(field)
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def assemble(period_path: str, prior_path: str, meta: dict,
             no_value_ids=frozenset()) -> dict:
    cur = G.load_rows(period_path, require_fields=PERIOD_FIELDS)
    prior = G.load_rows(prior_path, require_fields=PRIOR_FIELDS)

    merged: dict = {}
    order: list = []

    def slot(row: dict) -> dict:
        k = row.get("campaign.id")
        if k not in merged:
            merged[k] = {"campaign_id": k,
                         "campaign": str(row.get("campaign.name", "")),
                         "status": str(row.get("campaign.status", "")),
                         "channel": str(row.get("campaign.advertising_channel_type", "")),
                         "impressions": 0.0, "clicks": 0.0, "cost": 0.0,
                         "conversions": 0.0, "conversions_value": 0.0,
                         "search_impression_share": None,
                         "search_budget_lost_is": None,
                         "search_rank_lost_is": None,
                         "prior_cost": 0.0, "prior_conversions": 0.0,
                         "prior_conversions_value": 0.0,
                         "prior_impressions": 0.0, "prior_clicks": 0.0}
            order.append(k)
        return merged[k]

    # Reporting window: additive metrics summed per campaign (the pull is
    # unsegmented, so one raw row per campaign is expected — summing keeps the
    # core's dedupe a no-op either way); IS fractions from the first occurrence.
    for r in cur:
        m = slot(r)
        m["impressions"] += G.num(r.get("metrics.impressions"))
        m["clicks"] += G.num(r.get("metrics.clicks"))
        m["cost"] += G.micros(r.get("metrics.cost_micros"))
        m["conversions"] += G.num(r.get("metrics.conversions"))
        m["conversions_value"] += G.num(r.get("metrics.conversions_value"))
        for raw_f, out_f in IS_FIELDS:
            if m[out_f] is None:
                m[out_f] = _opt(r, raw_f)
    # Prior window joined by campaign.id; prior-only campaigns get a
    # zero-current row (never dropped — their deltas are the story).
    for r in prior:
        m = slot(r)
        m["prior_impressions"] += G.num(r.get("metrics.impressions"))
        m["prior_clicks"] += G.num(r.get("metrics.clicks"))
        m["prior_cost"] += G.micros(r.get("metrics.cost_micros"))
        m["prior_conversions"] += G.num(r.get("metrics.conversions"))
        m["prior_conversions_value"] += G.num(r.get("metrics.conversions_value"))

    campaigns = []
    for k in order:
        m = merged[k]
        m["cost"] = round(m["cost"], 6)
        m["prior_cost"] = round(m["prior_cost"], 6)
        if str(k) in no_value_ids:
            # value not tracked: omit the keys (schema: "omit conversions_value
            # if not tracked") so the core reports status="no_value".
            del m["conversions_value"]
            del m["prior_conversions_value"]
        campaigns.append(m)

    findings = {"meta": meta, "params": {}, "campaigns": campaigns}
    findings["meta"]["reconciliation"] = R.build(
        findings, RECONCILE_ARRAYS,
        raw_stamps=[G.file_stamp(p) for p in (period_path, prior_path)])
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description="Assemble performance-report findings JSON "
                                             "from saved raw GAQL pulls.")
    ap.add_argument("--campaigns-period", required=True, help="raw campaign pull for the reporting window")
    ap.add_argument("--campaigns-prior", required=True, help="raw campaign pull for the prior window (same query)")
    ap.add_argument("--client-name", required=True)
    ap.add_argument("--account-id", required=True)
    ap.add_argument("--currency", required=True)
    ap.add_argument("--period", required=True, help='e.g. "2026-06-01 to 2026-06-30" — the window used in the GAQL conditions')
    ap.add_argument("--prior-period", required=True)
    ap.add_argument("--no-value-campaigns", default="",
                    help="comma-separated campaign ids whose conversion value is NOT "
                         "tracked — their conversions_value keys are omitted (status "
                         "no_value) instead of reporting a fabricated ROAS of 0")
    ap.add_argument("--generated", default=None,
                    help="report date (YYYY-MM-DD); defaults to today — pass the "
                         "original date when re-assembling for byte-identical output")
    ap.add_argument("-o", "--output", required=True, help="findings JSON output path")
    args = ap.parse_args()

    meta = {"client_name": args.client_name, "account_id": args.account_id,
            "currency": args.currency, "period": args.period,
            "prior_period": args.prior_period,
            "generated": args.generated or datetime.date.today().isoformat()}
    no_value_ids = frozenset(s.strip() for s in args.no_value_campaigns.split(",") if s.strip())
    try:
        findings = assemble(args.campaigns_period, args.campaigns_prior, meta,
                            no_value_ids=no_value_ids)
    except (G.RawResultError, OSError) as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return 1

    Path(args.output).write_text(json.dumps(findings, ensure_ascii=False, indent=1))
    rec = findings["meta"]["reconciliation"]
    cm = rec["campaigns"]
    print(f"Wrote {args.output}")
    print(f"  campaigns: {cm['rows']} (spend {cm['sums']['cost']:,.2f} {args.currency}, "
          f"revenue {cm['sums']['conversions_value']:,.2f} {args.currency})")
    if no_value_ids:
        print(f"  no-value campaigns (value keys omitted): {', '.join(sorted(no_value_ids))}")
    print("  reconciliation totals embedded — the builder verifies them on every run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
