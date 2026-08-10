#!/usr/bin/env python3
"""Assemble the applied-audience findings JSON from saved raw GAQL pulls
(script-only — the transcription firewall for this skill's MCP path).

THREE raw pulls, saved verbatim (auto-saved by the harness when large, copied
verbatim when small) and THIS script — never the model — turns them into the
'audiences' findings array. Metric values go raw file -> parser -> findings
without ever passing through a token stream; control totals are embedded as
meta.reconciliation so audience_core hard-fails if the findings are later
edited or were produced any other way.

Two-pull, honest-granularity design (HM-602): `ad_group_criterion` exposes
ZERO `metrics.*` fields (metadata-confirmed live 2026-07-16 — see
tests/test_assemble_findings.py and references/audience-targeting-filter.md
for the full story). A single combined identity+metrics pull against
`ad_group_criterion`, as this script used to attempt, is REJECTED OUTRIGHT by
the live Google Ads API. So identity and metrics are two separate pulls,
joined here by `ad_group.id` — and because the join key is the AD GROUP (the
only grain the API's audience-metrics view supports), metrics are honestly
AD-GROUP-LEVEL: every USER_LIST criterion attached to the same ad group
shares the same cost/clicks/impressions/conversions figures. The API cannot
attribute performance to one user list among several sharing an ad group.

Pull 1 — applied-audience criteria (IDENTITY ONLY, no metrics):
    resource: ad_group_criterion
    fields:   campaign.name, ad_group.name, ad_group.id,
              ad_group_criterion.type, ad_group_criterion.user_list.user_list,
              ad_group_criterion.bid_modifier, ad_group_criterion.status,
              ad_group_criterion.negative
    condition: ad_group_criterion.type = 'USER_LIST'

Pull 2 — ad-group-level audience metrics (metadata-confirmed selectable on
this resource; `ad_group_criterion.user_list.user_list` is NOT joinable onto
this view in this MCP's GAQL implementation — verified live, see the
reference doc):
    resource: ad_group_audience_view
    fields:   campaign.id, campaign.name, ad_group.id, ad_group.name,
              metrics.impressions, metrics.clicks, metrics.cost_micros,
              metrics.conversions
    condition: segments.date BETWEEN '<window start>' AND '<window end>'

Pull 3 — user_list names/types (a third query; GAQL cannot join user_list's
own name/type fields into the ad_group_criterion query above):
    resource: user_list
    fields:   user_list.id, user_list.name, user_list.type

A criteria row whose ad_group.id has no matching row in pull 2 (no recorded
audience-view activity for that ad group in the window) is NEVER dropped: it
carries `metrics_status = "manual"` and null metric values — audience_core
stamps it `status = "manual"` (never scored, consistent with how this skill
already treats first-party-readiness gaps: represent by status, don't drop).

List membership size and Customer Match match rate are NEVER pulled here —
those are API-blind (see google-ads-foundation/references/artifact-formats.md,
"What the MCP cannot return") and arrive only via the first-party CSV path
(scripts/audience_csv.py).

Usage:
    python3 assemble_findings.py \
        --criteria tool-results/criteria.txt \
        --metrics tool-results/audience_metrics.txt \
        --user-lists tool-results/user_lists.txt \
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

import gaql_raw as G        # noqa: E402
import reconcile as R       # noqa: E402

sys.path.insert(0, str(HERE))
import audience_core as core  # noqa: E402  (owns the reconcile contract)

# Pull 1 — identity only. No metrics.* — ad_group_criterion cannot carry them
# (metadata-confirmed: zero metrics.* fields in this resource's selectable
# list — see the module docstring and references/audience-targeting-filter.md).
CRITERIA_FIELDS = ("campaign.name", "ad_group.name", "ad_group.id",
                   "ad_group_criterion.type", "ad_group_criterion.user_list.user_list",
                   "ad_group_criterion.bid_modifier", "ad_group_criterion.status",
                   "ad_group_criterion.negative")
# Pull 2 — ad-group-level metrics (ad_group_audience_view). Joined onto pull 1
# by ad_group.id in assemble() below — the only grain this view supports for
# this join (metadata-confirmed live 2026-07-16).
METRICS_FIELDS = ("ad_group.id", "metrics.impressions", "metrics.clicks",
                  "metrics.cost_micros", "metrics.conversions")
# Pull 3 — user-list identity (name/type resolution).
USERLIST_FIELDS = ("user_list.id", "user_list.name", "user_list.type")
# "Campaign types" pull — SKILL.md documents this as a `campaign` structure
# query used conversationally (spot PMax campaigns needing signals/brand
# exclusions, brand Search campaigns to protect), never scored — no findings
# assembler consumes it. Binds the field list to code per HM-606
# (skills/google-ads/tests/test_gaql_schema.py); nothing here imports it.
CAMPAIGN_TYPE_FIELDS = ("campaign.id", "campaign.name", "campaign.status",
                        "campaign.advertising_channel_type",
                        "campaign.advertising_channel_sub_type")

RECONCILE_ARRAYS = {"audiences": core.RECONCILE_ARRAYS["audiences"]}


def _list_id(resource: str) -> str:
    resource = str(resource or "")
    return resource.rsplit("/", 1)[-1] if resource else ""


def _ad_group_id(row: dict) -> str:
    return str(row.get("ad_group.id") or "").strip()


def _build_metrics_lookup(metrics_rows: list) -> dict:
    """ad_group.id -> summed {impressions, clicks, cost, conversions}.

    Summed (not overwritten) defensively in case the raw pull carries more
    than one row per ad group (e.g. a segmented pull saved into one file) —
    this script never requests segments.* for pull 2, so normally one row per
    ad group, but summing is the honest, no-row-loss behavior either way."""
    lookup: dict = {}
    for r in metrics_rows:
        agid = _ad_group_id(r)
        if not agid:
            continue
        m = lookup.setdefault(agid, {"impressions": 0.0, "clicks": 0.0,
                                     "cost": 0.0, "conversions": 0.0})
        m["impressions"] += G.num(r.get("metrics.impressions"))
        m["clicks"] += G.num(r.get("metrics.clicks"))
        m["cost"] += G.micros(r.get("metrics.cost_micros"))
        m["conversions"] += G.num(r.get("metrics.conversions"))
    return lookup


def assemble(criteria_path: str, metrics_path: str, userlists_path: str, meta: dict) -> dict:
    crit_rows = G.load_rows(criteria_path, require_fields=CRITERIA_FIELDS)
    metrics_rows = G.load_rows(metrics_path, require_fields=METRICS_FIELDS)
    ul_rows = G.load_rows(userlists_path, require_fields=USERLIST_FIELDS)

    ul_lookup: dict = {}
    for r in ul_rows:
        lid = str(r.get("user_list.id") or "")
        if lid:
            ul_lookup[lid] = {"name": r.get("user_list.name") or "",
                              "type": r.get("user_list.type") or ""}

    metrics_lookup = _build_metrics_lookup(metrics_rows)

    audiences = []
    skipped_non_userlist = 0
    joined = 0
    unjoined = 0
    for r in crit_rows:
        if str(r.get("ad_group_criterion.type", "")).upper() != "USER_LIST":
            skipped_non_userlist += 1
            continue  # defensive; the pull's condition should already filter
        lid = _list_id(r.get("ad_group_criterion.user_list.user_list"))
        ul = ul_lookup.get(lid, {})
        bm = r.get("ad_group_criterion.bid_modifier")
        agid = _ad_group_id(r)
        m = metrics_lookup.get(agid)
        row = {
            "campaign": r.get("campaign.name", ""),
            "ad_group": r.get("ad_group.name", ""),
            "list_name": ul.get("name") or (f"List {lid}" if lid else "(unnamed list)"),
            "list_type": ul.get("type") or "",
            "bid_modifier": (G.num(bm) if bm is not None else 1.0),
            "criterion_status": str(r.get("ad_group_criterion.status", "") or "").upper(),
            "negative": bool(r.get("ad_group_criterion.negative", False)),
        }
        if m is not None:
            row.update({
                "impressions": m["impressions"], "clicks": m["clicks"],
                "cost": round(m["cost"], 6), "conversions": round(m["conversions"], 6),
                "metrics_status": "joined",
            })
            joined += 1
        else:
            # No ad_group_audience_view activity for this ad group in the
            # window — never fabricate a zero; carry null metrics + status
            # "manual" so audience_core represents (never drops) the row.
            row.update({
                "impressions": None, "clicks": None, "cost": None, "conversions": None,
                "metrics_status": "manual",
            })
            unjoined += 1
        audiences.append(row)

    if skipped_non_userlist:
        sys.stderr.write(f"NOTE: skipped {skipped_non_userlist} non-USER_LIST raw row(s) "
                         "(the pull's condition should exclude them at source)\n")
    if unjoined:
        sys.stderr.write(
            f"NOTE: {unjoined} of {joined + unjoined} applied-audience criteria have no matching "
            "ad_group_audience_view row for their ad group in this window — carried as "
            "status='manual' (no fabricated zero), never dropped.\n")

    findings = {"meta": meta, "params": {}, "audiences": audiences}
    findings["meta"]["reconciliation"] = R.build(
        findings, RECONCILE_ARRAYS,
        raw_stamps=[G.file_stamp(p) for p in (criteria_path, metrics_path, userlists_path)])
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description="Assemble applied-audience findings JSON "
                                             "from saved raw GAQL pulls (two-pull, "
                                             "ad-group-level metrics — see module docstring).")
    ap.add_argument("--criteria", required=True, help="raw ad_group_criterion (USER_LIST) results file "
                    "(identity only — no metrics.*)")
    ap.add_argument("--metrics", required=True, help="raw ad_group_audience_view results file "
                    "(ad-group-level metrics; joined onto --criteria by ad_group.id)")
    ap.add_argument("--user-lists", required=True, help="raw user_list (id/name/type) results file")
    ap.add_argument("--client-name", required=True)
    ap.add_argument("--account-id", required=True)
    ap.add_argument("--currency", required=True)
    ap.add_argument("--window-30d", required=True, help='e.g. "2026-06-06 to 2026-07-05" — the '
                    "segments.date window used in the metrics pull")
    ap.add_argument("--generated", default=None,
                    help="report date (YYYY-MM-DD); defaults to today — pass the "
                         "original date when re-assembling for byte-identical output")
    ap.add_argument("-o", "--output", required=True, help="findings JSON output path")
    args = ap.parse_args()

    meta = {"client_name": args.client_name, "account_id": args.account_id,
            "currency": args.currency, "window_30d": args.window_30d,
            "source": "mcp",  # canonical live-pull token (HM-572)
            # Honest granularity label (HM-602): ad_group_audience_view is the
            # only grain the API's audience-metrics view supports for this
            # join — metrics are shared across every USER_LIST criterion on
            # the same ad group, never attributed to one list alone.
            "metrics_granularity": "ad_group_level",
            "generated": args.generated or datetime.date.today().isoformat()}
    try:
        findings = assemble(args.criteria, args.metrics, args.user_lists, meta)
    except (G.RawResultError, OSError) as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return 1

    Path(args.output).write_text(json.dumps(findings, ensure_ascii=False, indent=1))
    rec = findings["meta"]["reconciliation"]["audiences"]
    joined_n = sum(1 for a in findings["audiences"] if a["metrics_status"] == "joined")
    manual_n = len(findings["audiences"]) - joined_n
    print(f"Wrote {args.output}")
    print(f"  audiences: {rec['rows']} ({joined_n} with ad-group-level metrics, {manual_n} manual — "
          f"no ad_group_audience_view activity in the window) "
          f"(cost {rec['sums']['cost']:,.2f} {args.currency}, "
          f"clicks {rec['sums']['clicks']:,.0f}, conversions {rec['sums']['conversions']:,.2f})")
    print("  reconciliation totals embedded — the builder verifies them on every run")
    print("  NOTE: metrics are AD-GROUP-LEVEL — the Google Ads API cannot attribute "
          "impressions/clicks/cost/conversions to one user list among several sharing an ad group.")
    print("  NOTE: no first-party readiness data in this file — pass --first-party-csv "
          "to build_audience_report.py to add Customer Match / Enhanced Conversions / "
          "Consent Mode readiness (always user-supplied, never from this MCP).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
