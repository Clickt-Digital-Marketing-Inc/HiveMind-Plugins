#!/usr/bin/env python3
"""Assemble the applied-audience findings JSON from saved raw GAQL pulls
(script-only — the transcription firewall for this skill's MCP path).

Two raw pulls, saved verbatim (auto-saved by the harness when large, copied
verbatim when small) and THIS script — never the model — turns them into the
'audiences' findings array. Metric values go raw file -> parser -> findings
without ever passing through a token stream; control totals are embedded as
meta.reconciliation so audience_core hard-fails if the findings are later
edited or were produced any other way.

Pull 1 — applied-audience criteria:
    resource: ad_group_criterion
    fields:   campaign.name, ad_group.name, ad_group_criterion.type,
              ad_group_criterion.user_list.user_list,
              ad_group_criterion.bid_modifier, ad_group_criterion.status,
              ad_group_criterion.negative, metrics.impressions,
              metrics.clicks, metrics.cost_micros, metrics.conversions
    condition: ad_group_criterion.type = 'USER_LIST'

Pull 2 — user_list names/types (a second query; GAQL cannot join user_list's
own name/type fields into the ad_group_criterion query above):
    resource: user_list
    fields:   user_list.id, user_list.name, user_list.type

List membership size and Customer Match match rate are NEVER pulled here —
those are API-blind (see google-ads-foundation/references/artifact-formats.md,
"What the MCP cannot return") and arrive only via the first-party CSV path
(scripts/audience_csv.py).

Usage:
    python3 assemble_findings.py \
        --criteria tool-results/criteria.txt \
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

CRITERIA_FIELDS = ("campaign.name", "ad_group.name", "ad_group_criterion.type",
                   "ad_group_criterion.user_list.user_list", "ad_group_criterion.bid_modifier",
                   "ad_group_criterion.status", "ad_group_criterion.negative",
                   "metrics.impressions", "metrics.clicks", "metrics.cost_micros",
                   "metrics.conversions")
USERLIST_FIELDS = ("user_list.id", "user_list.name", "user_list.type")

RECONCILE_ARRAYS = {"audiences": core.RECONCILE_ARRAYS["audiences"]}


def _list_id(resource: str) -> str:
    resource = str(resource or "")
    return resource.rsplit("/", 1)[-1] if resource else ""


def assemble(criteria_path: str, userlists_path: str, meta: dict) -> dict:
    crit_rows = G.load_rows(criteria_path, require_fields=CRITERIA_FIELDS)
    ul_rows = G.load_rows(userlists_path, require_fields=USERLIST_FIELDS)

    ul_lookup: dict = {}
    for r in ul_rows:
        lid = str(r.get("user_list.id") or "")
        if lid:
            ul_lookup[lid] = {"name": r.get("user_list.name") or "",
                              "type": r.get("user_list.type") or ""}

    audiences = []
    skipped_non_userlist = 0
    for r in crit_rows:
        if str(r.get("ad_group_criterion.type", "")).upper() != "USER_LIST":
            skipped_non_userlist += 1
            continue  # defensive; the pull's condition should already filter
        lid = _list_id(r.get("ad_group_criterion.user_list.user_list"))
        ul = ul_lookup.get(lid, {})
        bm = r.get("ad_group_criterion.bid_modifier")
        audiences.append({
            "campaign": r.get("campaign.name", ""),
            "ad_group": r.get("ad_group.name", ""),
            "list_name": ul.get("name") or (f"List {lid}" if lid else "(unnamed list)"),
            "list_type": ul.get("type") or "",
            "bid_modifier": (G.num(bm) if bm is not None else 1.0),
            "criterion_status": str(r.get("ad_group_criterion.status", "") or "").upper(),
            "negative": bool(r.get("ad_group_criterion.negative", False)),
            "impressions": G.num(r.get("metrics.impressions")),
            "clicks": G.num(r.get("metrics.clicks")),
            "cost": round(G.micros(r.get("metrics.cost_micros")), 6),
            "conversions": G.num(r.get("metrics.conversions")),
        })

    if skipped_non_userlist:
        sys.stderr.write(f"NOTE: skipped {skipped_non_userlist} non-USER_LIST raw row(s) "
                         "(the pull's condition should exclude them at source)\n")

    findings = {"meta": meta, "params": {}, "audiences": audiences}
    findings["meta"]["reconciliation"] = R.build(
        findings, RECONCILE_ARRAYS,
        raw_stamps=[G.file_stamp(p) for p in (criteria_path, userlists_path)])
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description="Assemble applied-audience findings JSON "
                                             "from saved raw GAQL pulls.")
    ap.add_argument("--criteria", required=True, help="raw ad_group_criterion (USER_LIST) results file")
    ap.add_argument("--user-lists", required=True, help="raw user_list (id/name/type) results file")
    ap.add_argument("--client-name", required=True)
    ap.add_argument("--account-id", required=True)
    ap.add_argument("--currency", required=True)
    ap.add_argument("--window-30d", required=True, help='e.g. "2026-06-06 to 2026-07-05" — the '
                    "metrics.date window used in the criteria pull")
    ap.add_argument("--generated", default=None,
                    help="report date (YYYY-MM-DD); defaults to today — pass the "
                         "original date when re-assembling for byte-identical output")
    ap.add_argument("-o", "--output", required=True, help="findings JSON output path")
    args = ap.parse_args()

    meta = {"client_name": args.client_name, "account_id": args.account_id,
            "currency": args.currency, "window_30d": args.window_30d,
            "source": "mcp",  # canonical live-pull token (HM-572)
            "generated": args.generated or datetime.date.today().isoformat()}
    try:
        findings = assemble(args.criteria, args.user_lists, meta)
    except (G.RawResultError, OSError) as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return 1

    Path(args.output).write_text(json.dumps(findings, ensure_ascii=False, indent=1))
    rec = findings["meta"]["reconciliation"]["audiences"]
    print(f"Wrote {args.output}")
    print(f"  audiences: {rec['rows']} (cost {rec['sums']['cost']:,.2f} {args.currency}, "
          f"clicks {rec['sums']['clicks']:,.0f}, conversions {rec['sums']['conversions']:,.2f})")
    print("  reconciliation totals embedded — the builder verifies them on every run")
    print("  NOTE: no first-party readiness data in this file — pass --first-party-csv "
          "to build_audience_report.py to add Customer Match / Enhanced Conversions / "
          "Consent Mode readiness (always user-supplied, never from this MCP).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
