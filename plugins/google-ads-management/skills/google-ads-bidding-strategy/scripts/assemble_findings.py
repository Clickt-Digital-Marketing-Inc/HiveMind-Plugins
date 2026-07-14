#!/usr/bin/env python3
"""Assemble the bidding-strategy findings JSON — the dual MCP/CSV firewall.

Either input path is script-only: metric values go raw-file/CSV -> parser ->
findings JSON without ever passing through a token stream, and control totals
are embedded as meta.reconciliation so bidding_core hard-fails if the findings
are later edited or were produced any other way. Both paths yield an
IDENTICAL findings/model shape — bidding_core cannot tell them apart except by
the honest meta.source label ("mcp" / "user_csv").

MCP path (one search_search pull covers structure + 30d performance):
    python3 assemble_findings.py \
        --campaigns tool-results/campaigns.txt \
        --client-name "Acme Corp" --account-id 123-456-7890 --currency CAD \
        --window-30d "2026-06-06 to 2026-07-05" \
        -o findings.json

CSV path (a Google Ads UI "Campaigns" report export):
    python3 assemble_findings.py \
        --csv export.csv \
        --client-name "Acme Corp" --account-id 123-456-7890 --currency CAD \
        --window-30d "2026-06-06 to 2026-07-05" \
        -o findings.json

Either path accepts an OPTIONAL --judgment file: a small JSON object the
operator supplies by hand — `{"<campaign_id>": {"value_variance_score": 0-100,
"tracking_confidence_score": 0-100}}` — for the two Data-Maturity components
neither the MCP nor a UI export can supply. Never invent these numbers in
conversation; they are judgment inputs the OPERATOR types into that file
(still assembled by this script, never hand-edited into findings.json), and
campaigns without a judgment entry fall back to the model's tunable
neutral-assumption params with an honest "assumed"/"partial" confidence flag.

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
import csv_input as C         # noqa: E402

sys.path.insert(0, str(HERE))
import bidding_core as core   # noqa: E402  (owns the reconcile contract)

CAMPAIGN_FIELDS = ("campaign.id", "campaign.name", "campaign.bidding_strategy_type",
                   "metrics.conversions", "metrics.cost_micros")

RECONCILE_ARRAYS = core.RECONCILE_ARRAYS

# The CSV twin of CAMPAIGN_FIELDS — a Google Ads UI "Campaigns" report export.
# ai_max_enabled has no UI-export column (Smart Bidding Exploration is only
# confirmable via the MCP structure pull) — the CSV path never assumes it on.
COLUMN_MAP = {
    "campaign_id":           {"aliases": ["Campaign ID"], "type": "str"},
    "campaign":               {"aliases": ["Campaign"], "type": "str"},
    "bidding_strategy_type":  {"aliases": ["Bid strategy type", "Bidding strategy type"], "type": "str"},
    "conv30":                 {"aliases": ["Conversions"], "type": "num"},
    "cost":                   {"aliases": ["Cost"], "type": "num"},
    "value":                  {"aliases": ["Conv. value", "Conversion value", "All conv. value"], "type": "num"},
}
REQUIRED_FIELDS = ("campaign_id", "campaign", "bidding_strategy_type", "conv30", "cost")
RECONCILE_SPEC = {"array": "campaigns", "sums": RECONCILE_ARRAYS["campaigns"]}


def _load_judgment(path: str | None) -> dict:
    if not path:
        return {}
    try:
        data = json.loads(Path(path).read_text())
    except FileNotFoundError as e:
        raise SystemExit(f"ERROR: judgment file not found: {path}") from e
    except json.JSONDecodeError as e:
        raise SystemExit(f"ERROR: judgment file is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise SystemExit("ERROR: judgment file must be a JSON object of "
                         "{campaign_id: {value_variance_score, tracking_confidence_score}}")
    return {str(k): v for k, v in data.items()}


def assemble_mcp(campaigns_path: str, meta: dict, judgment: dict) -> dict:
    rows = G.load_rows(campaigns_path, require_fields=CAMPAIGN_FIELDS)
    # Merge by campaign_id first: a raw pull can legitimately split one
    # campaign across several rows (e.g. by an implicit segment), and the
    # attributes (name/strategy/ai_max) are campaign-level so they must agree
    # across the split — metrics are summed, never double-counted.
    merged: dict = {}
    order: list = []
    for r in rows:
        cid = str(r.get("campaign.id"))
        if cid not in merged:
            merged[cid] = {
                "campaign_id": cid, "campaign": r.get("campaign.name", ""),
                "bidding_strategy_type": r.get("campaign.bidding_strategy_type", ""),
                "ai_max_enabled": bool(r.get("campaign.ai_max_setting.enable_ai_max", False)),
                "conv30": 0.0, "cost": 0.0, "value": 0.0,
            }
            order.append(cid)
        m = merged[cid]
        m["conv30"] += G.num(r.get("metrics.conversions"))
        m["cost"] += G.micros(r.get("metrics.cost_micros"))
        m["value"] += G.num(r.get("metrics.conversions_value"))
        if not m["campaign"] and r.get("campaign.name"):
            m["campaign"] = r["campaign.name"]
        if not m["bidding_strategy_type"] and r.get("campaign.bidding_strategy_type"):
            m["bidding_strategy_type"] = r["campaign.bidding_strategy_type"]
        if r.get("campaign.ai_max_setting.enable_ai_max"):
            m["ai_max_enabled"] = True

    campaigns = []
    for cid in order:
        m = merged[cid]
        j = judgment.get(cid) or {}
        m["cost"] = round(m["cost"], 6)
        m["value_score"] = j.get("value_variance_score")
        m["tracking_score"] = j.get("tracking_confidence_score")
        campaigns.append(m)

    meta = dict(meta, source="mcp")
    findings = {"meta": meta, "params": {}, "campaigns": campaigns}
    findings["meta"]["reconciliation"] = R.build(
        findings, RECONCILE_ARRAYS, raw_stamps=[G.file_stamp(campaigns_path)])
    return findings


def assemble_csv(csv_path: str, meta: dict, judgment: dict) -> dict:
    rows, findings = C.assemble_from_csv(csv_path, COLUMN_MAP, REQUIRED_FIELDS,
                                         RECONCILE_SPEC, meta=dict(meta))
    for r in rows:
        j = judgment.get(str(r.get("campaign_id"))) or {}
        r["ai_max_enabled"] = False   # never assumed on from a UI export — see module docstring
        r["value_score"] = j.get("value_variance_score")
        r["tracking_score"] = j.get("tracking_confidence_score")
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Assemble bidding-strategy findings JSON from an MCP raw pull or a CSV export.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--campaigns", help="raw campaign search_search results file (MCP path)")
    src.add_argument("--csv", help="Google Ads UI 'Campaigns' report export (CSV path)")
    ap.add_argument("--judgment", default=None,
                    help="optional JSON {campaign_id: {value_variance_score, "
                         "tracking_confidence_score}} — operator-supplied judgment inputs")
    ap.add_argument("--client-name", required=True)
    ap.add_argument("--account-id", required=True)
    ap.add_argument("--currency", required=True)
    ap.add_argument("--window-30d", required=True, help='e.g. "2026-06-06 to 2026-07-05"')
    ap.add_argument("--generated", default=None,
                    help="report date (YYYY-MM-DD); defaults to today")
    ap.add_argument("-o", "--output", required=True, help="findings JSON output path")
    args = ap.parse_args()

    meta = {"client_name": args.client_name, "account_id": args.account_id,
            "currency": args.currency, "window_30d": args.window_30d,
            "generated": args.generated or datetime.date.today().isoformat()}
    judgment = _load_judgment(args.judgment)

    try:
        if args.campaigns:
            findings = assemble_mcp(args.campaigns, meta, judgment)
        else:
            findings = assemble_csv(args.csv, meta, judgment)
    except (G.RawResultError, C.CsvInputError, OSError) as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return 1

    Path(args.output).write_text(json.dumps(findings, ensure_ascii=False, indent=1))
    rec = findings["meta"]["reconciliation"]["campaigns"]
    print(f"Wrote {args.output}  (source: {findings['meta']['source']})")
    print(f"  campaigns: {rec['rows']} (cost {rec['sums']['cost']:,.2f} {args.currency}, "
          f"conv30 {rec['sums']['conv30']:,.2f})")
    print("  reconciliation totals embedded — the builder verifies them on every run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
