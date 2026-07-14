#!/usr/bin/env python3
"""Assemble the competitive-pressure findings JSON — dual input (script-only).

Own-side (this-week / prior-week campaign performance) is the transcription
firewall over saved GAQL pulls: the two `search_search` results are saved
verbatim to files and THIS script — never the model — turns them into the
findings JSON. Metric values go raw file -> parser -> findings without ever
passing through a token stream, and control totals are embedded as
meta.reconciliation so competitive_core hard-fails if the findings are later
edited or were produced any other way.

The competitor payload is NOT available via the Google Ads API (Auction
Insights). It arrives ONLY via a user-supplied CSV export, optional
`--auction-insights`. Competitor rows carry the SAME transcription-firewall +
reconciliation discipline through `_shared/csv_input.load_csv_rows` +
`reconcile.build` (the multi-array pattern — this script merges the CSV rows
into the same findings dict as the MCP campaigns array, so it calls the two
primitives directly rather than the single-array `assemble_from_csv` wrapper).

Usage:
    python3 assemble_findings.py \
        --this tool-results/campaigns_this.txt \
        --prior tool-results/campaigns_prior.txt \
        --auction-insights auction_insights_export.csv \
        --client-name "Acme Corp" --account-id 123-456-7890 --currency CAD \
        --window-this "2026-07-06 to 2026-07-12" \
        --window-prior "2026-06-29 to 2026-07-05" \
        -o findings.json

`--auction-insights` is optional — omit it for an MCP-only own-side run (the
own-side model is identical either way; only the competitor rows differ).

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

import gaql_raw as G                  # noqa: E402
import reconcile as R                 # noqa: E402
from csv_input import load_csv_rows, CsvInputError  # noqa: E402

sys.path.insert(0, str(HERE))
import competitive_core as core       # noqa: E402  (owns the reconcile contract)

CAMPAIGN_FIELDS = ("campaign.id", "campaign.name", "campaign.advertising_channel_type",
                   "metrics.cost_micros", "metrics.clicks", "metrics.impressions",
                   "metrics.conversions", "metrics.search_impression_share",
                   "metrics.search_rank_lost_impression_share",
                   "metrics.search_budget_lost_impression_share")

# The Google Ads UI "Auction insights" export. Column spelling varies by
# locale/version — add aliases (+ a fixture) rather than guessing.
COLUMN_MAP = {
    "domain": {"aliases": ["Display URL domain", "Domain"], "type": "str"},
    "campaign": {"aliases": ["Campaign"], "type": "str"},
    "impression_share": {"aliases": ["Impr. share", "Impression share"], "type": "pct"},
    "overlap_rate": {"aliases": ["Overlap rate"], "type": "pct"},
    "position_above_rate": {"aliases": ["Position above rate", "Outranking share"], "type": "pct"},
    "top_of_page_rate": {"aliases": ["Top of page rate"], "type": "pct"},
}
CSV_REQUIRED_FIELDS = ("domain", "impression_share")

RECONCILE_ARRAYS = core.RECONCILE_ARRAYS


def _share(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _aggregate(rows: list) -> dict:
    """One row per campaign.id -> summed cost/clicks/impressions/conversions;
    the last non-null impression-share-style value wins (a plain campaign-
    resource pull over a date range returns one already-aggregated row per
    campaign, so this loop runs once per campaign in practice; the merge stays
    defensive against an accidentally segmented pull)."""
    agg: dict = {}
    order: list = []
    for r in rows:
        if str(r.get("campaign.advertising_channel_type", "")).upper() != "SEARCH":
            continue
        cid = r.get("campaign.id")
        if cid not in agg:
            agg[cid] = {"campaign_id": cid, "campaign": r.get("campaign.name", ""),
                        "cost": 0.0, "clicks": 0.0, "impressions": 0.0, "conversions": 0.0,
                        "impression_share": None, "rank_lost_is": None, "budget_lost_is": None}
            order.append(cid)
        a = agg[cid]
        a["cost"] += G.micros(r.get("metrics.cost_micros"))
        a["clicks"] += G.num(r.get("metrics.clicks"))
        a["impressions"] += G.num(r.get("metrics.impressions"))
        a["conversions"] += G.num(r.get("metrics.conversions"))
        for key, field in (("impression_share", "metrics.search_impression_share"),
                           ("rank_lost_is", "metrics.search_rank_lost_impression_share"),
                           ("budget_lost_is", "metrics.search_budget_lost_impression_share")):
            v = _share(r.get(field))
            if v is not None:
                a[key] = v
    for cid in order:
        a = agg[cid]
        a["cost"] = round(a["cost"], 6)
        a["avg_cpc"] = round(a["cost"] / a["clicks"], 6) if a["clicks"] else 0.0
    return agg


def assemble(this_path: str, prior_path: str, meta: dict,
             auction_insights_path: str | None = None) -> dict:
    this_rows = G.load_rows(this_path, require_fields=CAMPAIGN_FIELDS)
    prior_rows = G.load_rows(prior_path, require_fields=CAMPAIGN_FIELDS)
    this_agg = _aggregate(this_rows)
    prior_agg = _aggregate(prior_rows)

    order = list(this_agg.keys())
    for cid in prior_agg:
        if cid not in this_agg:
            order.append(cid)   # campaign ran prior week only (e.g. paused since) -> no-row-loss

    campaigns = []
    for cid in order:
        t = this_agg.get(cid)
        p = prior_agg.get(cid)
        campaigns.append({
            "campaign_id": cid, "campaign": (t or p)["campaign"],
            "cost_this": (t or {}).get("cost", 0.0), "clicks_this": (t or {}).get("clicks", 0.0),
            "impressions_this": (t or {}).get("impressions", 0.0),
            "conversions_this": (t or {}).get("conversions", 0.0),
            "avg_cpc_this": (t or {}).get("avg_cpc", 0.0),
            "impression_share_this": (t or {}).get("impression_share"),
            "rank_lost_is_this": (t or {}).get("rank_lost_is"),
            "budget_lost_is_this": (t or {}).get("budget_lost_is"),
            "cost_prior": (p or {}).get("cost", 0.0), "clicks_prior": (p or {}).get("clicks", 0.0),
            "impressions_prior": (p or {}).get("impressions", 0.0),
            "conversions_prior": (p or {}).get("conversions", 0.0),
            "avg_cpc_prior": (p or {}).get("avg_cpc", 0.0),
            "impression_share_prior": (p or {}).get("impression_share"),
            "rank_lost_is_prior": (p or {}).get("rank_lost_is"),
            "budget_lost_is_prior": (p or {}).get("budget_lost_is"),
            "has_prior": p is not None,
        })

    raw_stamps = [G.file_stamp(this_path), G.file_stamp(prior_path)]
    competitors: list = []
    if auction_insights_path:
        # CsvInputError propagates to the caller (main() reports it and exits 1) —
        # no wrapping needed here.
        competitors, stamp = load_csv_rows(auction_insights_path, COLUMN_MAP, CSV_REQUIRED_FIELDS)
        raw_stamps.append(stamp)
        meta["auction_insights_source"] = "user_csv"
    else:
        meta["auction_insights_source"] = ""
    meta["source"] = "mcp"

    findings = {"meta": meta, "params": {}, "campaigns": campaigns, "competitors": competitors}
    findings["meta"]["reconciliation"] = R.build(findings, RECONCILE_ARRAYS, raw_stamps=raw_stamps)
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description="Assemble competitive-pressure findings JSON "
                                             "from saved raw GAQL pulls + an optional Auction "
                                             "Insights CSV export.")
    ap.add_argument("--this", required=True, help="raw campaign results, this-week window")
    ap.add_argument("--prior", required=True, help="raw campaign results, prior-week window")
    ap.add_argument("--auction-insights", default=None,
                    help="Auction Insights CSV export (competitor rows; user-supplied, "
                         "NOT available via the API) — omit for an MCP-only own-side run")
    ap.add_argument("--client-name", required=True)
    ap.add_argument("--account-id", required=True)
    ap.add_argument("--currency", required=True)
    ap.add_argument("--window-this", required=True,
                    help='e.g. "2026-07-06 to 2026-07-12" — the dates used in the GAQL BETWEEN')
    ap.add_argument("--window-prior", required=True)
    ap.add_argument("--generated", default=None,
                    help="report date (YYYY-MM-DD); defaults to today")
    ap.add_argument("-o", "--output", required=True, help="findings JSON output path")
    args = ap.parse_args()

    meta = {"client_name": args.client_name, "account_id": args.account_id,
            "currency": args.currency, "window_this": args.window_this,
            "window_prior": args.window_prior,
            "generated": args.generated or datetime.date.today().isoformat()}
    try:
        findings = assemble(args.this, args.prior, meta, args.auction_insights)
    except (G.RawResultError, CsvInputError, OSError) as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return 1

    Path(args.output).write_text(json.dumps(findings, ensure_ascii=False, indent=1))
    rec = findings["meta"]["reconciliation"]
    c = rec["campaigns"]
    print(f"Wrote {args.output}")
    print(f"  campaigns: {c['rows']} (cost this-week {c['sums']['cost_this']:,.2f} {args.currency}, "
          f"cost prior-week {c['sums']['cost_prior']:,.2f} {args.currency})")
    print(f"  competitors: {rec['competitors']['rows']} "
          f"({'from Auction Insights CSV — user-supplied' if args.auction_insights else 'none (MCP-only run)'})")
    print("  reconciliation totals embedded — the builder verifies them on every run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
