#!/usr/bin/env python3
"""Assemble the account-health findings JSON from saved raw GAQL pulls (script-only).

The transcription firewall for this skill: the four `search_search` pulls
are saved verbatim to files (auto-saved by the harness when large, copied
verbatim when small) and THIS script — never the model — turns them into the
findings JSON. Metric values go raw file -> parser -> findings without ever
passing through a token stream, and control totals are embedded as
meta.reconciliation so health_core hard-fails if the findings are later
edited or were produced any other way.

Usage:
    python3 assemble_findings.py \
        --keywords tool-results/keywords.txt \
        --adgroup-perf tool-results/adgroup_perf.txt \
        --campaigns tool-results/campaigns.txt \
        --negatives tool-results/negatives.txt \
        --client-name "Acme Corp" --account-id 123-456-7890 --currency CAD \
        --window-30d "2026-06-06 to 2026-07-05" \
        -o findings.json

Pass the SAME dates used in the GAQL conditions for the window label.

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
import health_core as core  # noqa: E402  (owns the reconcile contract)

# Row shapes required in each raw pull (dotted GAQL field names, exactly as
# requested — see references/account-health-filter.md for the full queries).
KEYWORDS_FIELDS = ("campaign.id", "ad_group.id")
ADGROUP_PERF_FIELDS = ("campaign.id", "campaign.name", "ad_group.id", "ad_group.name",
                       "metrics.clicks", "metrics.impressions")
CAMPAIGNS_FIELDS = ("campaign.id", "campaign.name", "campaign.status",
                    "campaign.advertising_channel_type", "campaign.bidding_strategy_type",
                    "metrics.conversions", "metrics.cost_micros")
NEGATIVES_FIELDS = ("campaign.id",)

RECONCILE_ARRAYS = core.RECONCILE_ARRAYS


def _agkey(campaign_id, ad_group_id):
    return (str(campaign_id), str(ad_group_id))


def assemble(keywords_path: str, adgroup_perf_path: str, campaigns_path: str,
            negatives_path: str, meta: dict) -> dict:
    kw_rows = G.load_rows(keywords_path, require_fields=KEYWORDS_FIELDS)
    perf_rows = G.load_rows(adgroup_perf_path, require_fields=ADGROUP_PERF_FIELDS)
    camp_rows = G.load_rows(campaigns_path, require_fields=CAMPAIGNS_FIELDS)
    neg_rows = G.load_rows(negatives_path, require_fields=NEGATIVES_FIELDS)

    # keyword_count per (campaign, ad_group) — one raw row per enabled,
    # non-negative keyword (the pull should already filter type=KEYWORD,
    # negative=false, status=ENABLED; this just counts rows per ad group).
    kw_count: dict = {}
    for r in kw_rows:
        k = _agkey(r.get("campaign.id"), r.get("ad_group.id"))
        kw_count[k] = kw_count.get(k, 0) + 1

    # ad_group perf (clicks/impressions, summed defensively across any
    # segment split) — one raw row per ad group normally.
    perf: dict = {}
    order: list = []
    for r in perf_rows:
        k = _agkey(r.get("campaign.id"), r.get("ad_group.id"))
        if k not in perf:
            perf[k] = {"campaign_id": r.get("campaign.id"), "campaign": r.get("campaign.name", ""),
                       "ad_group_id": r.get("ad_group.id"), "ad_group": r.get("ad_group.name", ""),
                       "clicks": 0.0, "impressions": 0.0}
            order.append(k)
        perf[k]["clicks"] += G.num(r.get("metrics.clicks"))
        perf[k]["impressions"] += G.num(r.get("metrics.impressions"))

    # union of keys from both pulls (no-row-loss: a keyword-only or
    # perf-only ad group still gets a row, with the missing side at 0).
    all_keys = list(order)
    for k in kw_count:
        if k not in perf:
            all_keys.append(k)

    ad_groups = []
    for k in all_keys:
        p = perf.get(k, {"campaign_id": k[0], "campaign": "", "ad_group_id": k[1], "ad_group": "",
                         "clicks": 0.0, "impressions": 0.0})
        # An ad group can appear in the keywords pull but not the ad-group-perf
        # pull (e.g. zero impressions in the window) — carry the name through
        # with a fallback label rather than leaving the sprawl table blank.
        campaign_name = p["campaign"] or f"(name unavailable — id {p['campaign_id']})"
        ad_group_name = p["ad_group"] or f"(name unavailable — id {p['ad_group_id']})"
        ad_groups.append({
            "campaign_id": p["campaign_id"], "campaign": campaign_name,
            "ad_group_id": p["ad_group_id"], "ad_group": ad_group_name,
            "keyword_count": kw_count.get(k, 0),
            "clicks": round(p["clicks"], 6), "impressions": round(p["impressions"], 6),
        })

    # negative_count per campaign, from ALL raw negative rows (raw universe —
    # this dict is the reconciliation source of truth for the negatives
    # total, not the post-join campaigns array below).
    neg_count: dict = {}
    for r in neg_rows:
        cid = str(r.get("campaign.id"))
        neg_count[cid] = neg_count.get(cid, 0) + 1
    negatives_raw_total = sum(neg_count.values())  # == len(neg_rows)

    campaigns = []
    camp_ids = set()
    for r in camp_rows:
        cid = str(r.get("campaign.id"))
        camp_ids.add(cid)
        campaigns.append({
            "campaign_id": cid, "campaign": r.get("campaign.name", ""),
            "status": r.get("campaign.status", ""),
            "channel_type": r.get("campaign.advertising_channel_type", ""),
            "bidding_strategy_type": r.get("campaign.bidding_strategy_type", ""),
            "conversions_30d": round(G.num(r.get("metrics.conversions")), 6),
            # 30d window spend — drives campaign liveness (HM-603). Micros -> unit.
            "cost": round(G.num(r.get("metrics.cost_micros")) / 1e6, 6),
            "negative_count": neg_count.get(cid, 0),
        })

    # Negatives that reference a campaign id absent from the campaigns pull
    # (e.g. REMOVED campaigns, excluded by pull 3's `status != 'REMOVED'`
    # condition) — no-row-loss: these are never silently dropped, they are
    # counted separately and status-tagged so the control total (below)
    # covers the ENTIRE raw negatives universe, not just the joined subset.
    orphan_ids = sorted((cid for cid in neg_count if cid not in camp_ids), key=lambda c: (len(c), c))
    orphan_count = sum(neg_count[cid] for cid in orphan_ids)
    if orphan_ids:
        sys.stderr.write(
            f"NOTE: {len(orphan_ids)} campaign id(s) in the negatives pull are absent from "
            f"the campaigns pull — {orphan_count} negative(s) excluded from active-structure "
            f"totals, counted in orphan_negatives instead "
            f"({', '.join(orphan_ids)})\n")

    orphan_negatives = {
        "count": orphan_count,
        "campaign_ids": orphan_ids,
        "status": "out_of_scope",  # removed/out-of-scope campaigns — never scored
    }

    findings = {"meta": meta, "params": {}, "ad_groups": ad_groups, "campaigns": campaigns,
                "orphan_negatives": orphan_negatives}
    findings["meta"]["reconciliation"] = R.build(
        findings, RECONCILE_ARRAYS,
        raw_stamps=[G.file_stamp(p) for p in
                    (keywords_path, adgroup_perf_path, campaigns_path, negatives_path)],
        raw_totals={"negatives": negatives_raw_total})
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description="Assemble account-health findings JSON "
                                             "from saved raw GAQL pulls.")
    ap.add_argument("--keywords", required=True, help="raw ad_group_criterion (KEYWORD, enabled, non-negative) results file")
    ap.add_argument("--adgroup-perf", required=True, help="raw ad_group performance (30d clicks/impressions) results file")
    ap.add_argument("--campaigns", required=True, help="raw campaign structure+status+bidding+conversions(30d) results file")
    ap.add_argument("--negatives", required=True, help="raw campaign_criterion (KEYWORD, negative) results file")
    ap.add_argument("--client-name", required=True)
    ap.add_argument("--account-id", required=True)
    ap.add_argument("--currency", required=True)
    ap.add_argument("--window-30d", required=True, help='e.g. "2026-06-06 to 2026-07-05" — the dates used in the GAQL BETWEEN')
    ap.add_argument("--generated", default=None,
                    help="report date (YYYY-MM-DD); defaults to today — pass the "
                         "original date when re-assembling for byte-identical output")
    ap.add_argument("-o", "--output", required=True, help="findings JSON output path")
    args = ap.parse_args()

    meta = {"client_name": args.client_name, "account_id": args.account_id,
            "currency": args.currency, "window_30d": args.window_30d, "source": "mcp",
            "generated": args.generated or datetime.date.today().isoformat()}
    try:
        findings = assemble(args.keywords, args.adgroup_perf, args.campaigns, args.negatives, meta)
    except (G.RawResultError, OSError) as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return 1

    Path(args.output).write_text(json.dumps(findings, ensure_ascii=False, indent=1))
    rec = findings["meta"]["reconciliation"]
    ag, cp = rec["ad_groups"], rec["campaigns"]
    print(f"Wrote {args.output}")
    print(f"  ad_groups: {ag['rows']} (keywords {ag['sums']['keyword_count']:,.0f}, "
          f"impressions {ag['sums']['impressions']:,.0f}, clicks {ag['sums']['clicks']:,.0f})")
    print(f"  campaigns: {cp['rows']} (negatives {cp['sums']['negative_count']:,.0f}, "
          f"conversions(30d) {cp['sums']['conversions_30d']:,.2f})")
    orphan = findings["orphan_negatives"]
    print(f"  negatives (raw universe): {rec['raw_totals']['negatives']:,.0f} "
          f"(orphan_negatives: {orphan['count']} across {len(orphan['campaign_ids'])} "
          f"out-of-scope campaign id(s))")
    print("  reconciliation totals embedded — the builder verifies them on every run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
