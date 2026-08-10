#!/usr/bin/env python3
"""Assemble the conversions & tracking findings JSON — dual input (script-only).

The transcription firewall for this skill: every MCP pull's raw result is
saved verbatim to a file (auto-saved by the harness when large, copied
verbatim when small) and THIS script — never the model — turns those files
into the findings JSON. Metric values go raw file -> parser -> findings
without ever passing through a token stream, and control totals are embedded
as meta.reconciliation so conv_tracking_core hard-fails if the findings are
later edited or were produced any other way.

Two MCP pulls (required):
    --conversion-actions <raw file>   conversion_action config + metrics.all_conversions
                                       (all conversions, incl. secondary actions — the only
                                       conversions metric selectable at the conversion_action
                                       grain) over the current-window date range
    --campaign-curr      <raw file>   per-campaign clicks/impressions/cost/
                                       conversions, current window
    --campaign-prior     <raw file>   same shape, prior comparable window

One optional CSV (manual — Enhanced Conversions / Consent Mode). The Google
Ads API does not expose EC/Consent-Mode configuration confirmation; the CSV
is a small manually-filled export/template with columns Check/Value/Note. If
omitted, two honest "not confirmed via API" rows are still emitted — nothing
is silently skipped.

Usage:
    python3 assemble_findings.py \
        --conversion-actions tool-results/config.txt \
        --campaign-curr tool-results/camp_curr.txt \
        --campaign-prior tool-results/camp_prior.txt \
        --ec-csv enhanced_conversions_export.csv \
        --client-name "Acme Corp" --account-id 123-456-7890 --currency CAD \
        --window-curr "2026-06-13 to 2026-07-12" \
        --window-prior "2026-05-14 to 2026-06-12" \
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

import csv_input as C         # noqa: E402
import gaql_raw as G          # noqa: E402
import reconcile as R         # noqa: E402

sys.path.insert(0, str(HERE))
import conv_tracking_core as core  # noqa: E402  (owns the reconcile contract)

CONFIG_FIELDS = ("conversion_action.id", "conversion_action.name", "conversion_action.status",
                 "conversion_action.type", "conversion_action.category",
                 "conversion_action.primary_for_goal", "conversion_action.counting_type",
                 "conversion_action.attribution_model_settings.attribution_model",
                 "metrics.all_conversions")
CAMPAIGN_FIELDS = ("campaign.id", "campaign.name", "campaign.status", "metrics.clicks",
                   "metrics.impressions", "metrics.cost_micros", "metrics.conversions")

RECONCILE_ARRAYS = core.RECONCILE_ARRAYS

# The manually-filled EC/Consent-Mode export/template — this is NOT a native
# Google Ads UI report (the API/UI has no such export); it is a small
# operator-maintained table (see references/conversion-tracking-filter.md for
# the exact columns to hand the user).
EC_CSV_COLUMN_MAP = {
    "check": {"aliases": ["Check", "Setting"], "type": "str"},
    "value": {"aliases": ["Value", "Status"], "type": "str"},
    "note": {"aliases": ["Note", "Notes"], "type": "str"},
}
EC_REQUIRED_FIELDS = ("check", "value")

DEFAULT_MANUAL_CHECKS = [
    {"check": "Enhanced Conversions", "value": "not confirmed via API",
     "data_source": "not_confirmed", "note": "No --ec-csv supplied — confirm in the UI."},
    {"check": "Consent Mode v2", "value": "not confirmed via API",
     "data_source": "not_confirmed",
     "note": "No manual Consent Mode v2 status supplied — confirm Basic/Advanced consent "
             "signals in Tag Manager or the site's consent banner config."},
]


def _agg_conversion_actions(rows: list) -> list:
    """One row per conversion_action.id (defensive sum of metrics.all_conversions
    in case the pull is segmented); other config fields taken from the first
    occurrence (they don't vary by segment). conversions_30d holds all
    conversions (incl. secondary) — the raw key is consumed directly, no rename."""
    merged: dict = {}
    order: list = []
    for r in rows:
        cid = r.get("conversion_action.id")
        if cid not in merged:
            merged[cid] = {
                "id": cid, "name": r.get("conversion_action.name", ""),
                "status": r.get("conversion_action.status", ""),
                "type": r.get("conversion_action.type", ""),
                "category": r.get("conversion_action.category", ""),
                "primary_for_goal": bool(r.get("conversion_action.primary_for_goal")),
                "counting_type": r.get("conversion_action.counting_type", ""),
                "attribution_model": r.get(
                    "conversion_action.attribution_model_settings.attribution_model", ""),
                "conversions_30d": 0.0,
            }
            order.append(cid)
        merged[cid]["conversions_30d"] += G.num(r.get("metrics.all_conversions"))
    for cid in order:
        merged[cid]["conversions_30d"] = round(merged[cid]["conversions_30d"], 6)
    return [merged[cid] for cid in order]


def _agg_campaigns(rows: list) -> dict:
    """campaign_id -> aggregated metrics dict (defensive sum in case the pull
    is segmented)."""
    merged: dict = {}
    for r in rows:
        cid = r.get("campaign.id")
        if cid not in merged:
            merged[cid] = {"campaign_id": cid, "campaign": r.get("campaign.name", ""),
                           "status": r.get("campaign.status", ""),
                           "clicks": 0.0, "impressions": 0.0, "cost": 0.0, "conversions": 0.0}
        m = merged[cid]
        m["clicks"] += G.num(r.get("metrics.clicks"))
        m["impressions"] += G.num(r.get("metrics.impressions"))
        m["cost"] += G.micros(r.get("metrics.cost_micros"))
        m["conversions"] += G.num(r.get("metrics.conversions"))
    return merged


def _join_campaign_trend(curr: dict, prior: dict) -> list:
    """Union of campaign ids appearing in EITHER window — no-row-loss for a
    campaign that only ran in one of the two windows."""
    out = []
    for cid in sorted(set(curr) | set(prior), key=lambda k: (k is None, k)):
        c, p = curr.get(cid), prior.get(cid)
        name = (c or p)["campaign"]
        # campaign.status is a current campaign attribute (same in both pulls) —
        # take the current window's, falling back to the prior for a campaign that
        # only ran then. Non-numeric, so it stays out of the reconcile totals.
        campaign_status = (c or p).get("status", "")
        out.append({
            "campaign_id": cid, "campaign": name, "campaign_status": campaign_status,
            "clicks_curr": round((c or {}).get("clicks", 0.0), 6),
            "impressions_curr": round((c or {}).get("impressions", 0.0), 6),
            "cost_curr": round((c or {}).get("cost", 0.0), 6),
            "conversions_curr": round((c or {}).get("conversions", 0.0), 6),
            "clicks_prior": round((p or {}).get("clicks", 0.0), 6),
            "impressions_prior": round((p or {}).get("impressions", 0.0), 6),
            "cost_prior": round((p or {}).get("cost", 0.0), 6),
            "conversions_prior": round((p or {}).get("conversions", 0.0), 6),
        })
    return out


def assemble(config_path: str, camp_curr_path: str, camp_prior_path: str,
            ec_csv_path: str | None, meta: dict) -> dict:
    config_rows = G.load_rows(config_path, require_fields=CONFIG_FIELDS)
    curr_rows = G.load_rows(camp_curr_path, require_fields=CAMPAIGN_FIELDS)
    prior_rows = G.load_rows(camp_prior_path, require_fields=CAMPAIGN_FIELDS)

    conversion_actions = _agg_conversion_actions(config_rows)
    campaign_trend = _join_campaign_trend(_agg_campaigns(curr_rows), _agg_campaigns(prior_rows))

    raw_stamps = [G.file_stamp(p) for p in (config_path, camp_curr_path, camp_prior_path)]
    if ec_csv_path:
        rows, stamp = C.load_csv_rows(ec_csv_path, EC_CSV_COLUMN_MAP, EC_REQUIRED_FIELDS)
        manual_checks = [{"check": r.get("check", ""), "value": r.get("value", ""),
                          "data_source": "user_csv", "note": r.get("note", "")} for r in rows]
        raw_stamps.append(stamp)
    else:
        manual_checks = [dict(r) for r in DEFAULT_MANUAL_CHECKS]

    findings = {"meta": meta, "params": {}, "conversion_actions": conversion_actions,
               "campaign_trend": campaign_trend, "manual_checks": manual_checks}
    findings["meta"]["reconciliation"] = R.build(findings, RECONCILE_ARRAYS, raw_stamps=raw_stamps)
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description="Assemble conversions & tracking findings JSON "
                                             "from saved raw GAQL pulls (+ optional EC/Consent-Mode CSV).")
    ap.add_argument("--conversion-actions", required=True,
                    help="raw conversion_action config + metrics.all_conversions results file")
    ap.add_argument("--campaign-curr", required=True, help="raw per-campaign metrics, current window")
    ap.add_argument("--campaign-prior", required=True, help="raw per-campaign metrics, prior window")
    ap.add_argument("--ec-csv", default=None,
                    help="optional Enhanced Conversions / Consent Mode manual export (Check,Value,Note)")
    ap.add_argument("--client-name", required=True)
    ap.add_argument("--account-id", required=True)
    ap.add_argument("--currency", required=True)
    ap.add_argument("--window-curr", required=True, help='e.g. "2026-06-13 to 2026-07-12"')
    ap.add_argument("--window-prior", required=True, help='e.g. "2026-05-14 to 2026-06-12"')
    ap.add_argument("--generated", default=None,
                    help="report date (YYYY-MM-DD); defaults to today — pass the "
                         "original date when re-assembling for byte-identical output")
    ap.add_argument("-o", "--output", required=True, help="findings JSON output path")
    args = ap.parse_args()

    meta = {"client_name": args.client_name, "account_id": args.account_id,
            "currency": args.currency, "window_curr": args.window_curr,
            "window_prior": args.window_prior, "source": "mcp",  # canonical live-pull token (HM-572)
            "generated": args.generated or datetime.date.today().isoformat()}
    try:
        findings = assemble(args.conversion_actions, args.campaign_curr, args.campaign_prior,
                            args.ec_csv, meta)
    except (G.RawResultError, C.CsvInputError, OSError) as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return 1

    Path(args.output).write_text(json.dumps(findings, ensure_ascii=False, indent=1))
    rec = findings["meta"]["reconciliation"]
    ca, ct = rec["conversion_actions"], rec["campaign_trend"]
    print(f"Wrote {args.output}")
    print(f"  conversion_actions: {ca['rows']} (conversions_30d {ca['sums']['conversions_30d']:,.2f})")
    print(f"  campaign_trend:     {ct['rows']} campaigns "
          f"(cost_curr {ct['sums']['cost_curr']:,.2f} {args.currency})")
    print(f"  manual_checks:      {rec['manual_checks']['rows']} row(s) "
          f"({'user_csv' if args.ec_csv else 'not_confirmed default'})")
    print("  reconciliation totals embedded — the builder verifies them on every run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
