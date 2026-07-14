#!/usr/bin/env python3
"""Assemble the Quality Score findings JSON from a user-supplied CSV export.

The CSV twin of `assemble_findings.py` — the manual-input path for when the
Google Ads MCP is unreachable or the user simply has an export in hand. Same
findings/model shape and reconciliation discipline, this time sourced from a
Google Ads UI **Keywords** report (the Keywords page, with the Quality Score
diagnostic columns — Quality Score / Landing page exp. / Ad relevance /
Expected CTR — added) instead of a live `keyword_view` GAQL pull. Uses the
shared `_shared/csv_input.py` manual-input firewall: the file is parsed
verbatim into typed rows, never through the model's token stream. See
`references/quality-score-report.md` ("Dual input") for the export
instructions and `../google-ads-foundation/references/artifact-formats.md`
for the general MCP-or-CSV contract.

Two normalizations the UI export needs that a live GAQL pull doesn't:
  - Match type: the UI shows "Broad match" / "Phrase match" / "Exact match"
    (a human label); the model expects the GAQL enum token ("BROAD" etc.).
  - ad_group_id: the UI export has no internal ad-group id (only the name).
    The model dedupes/groups by ad_group_id, so the CSV path uses the ad
    group NAME as a stand-in id — unique within an account for all practical
    purposes, and honestly the best the manual export can offer.

Usage:
    python3 assemble_findings_csv.py \
        --csv export.csv \
        --client-name "Acme Corp" --account-id 123-456-7890 --currency CAD \
        --period "last 30 days" \
        -o findings.json

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

from csv_input import CsvInputError, assemble_from_csv   # noqa: E402

sys.path.insert(0, str(HERE))
import qs_core as core      # noqa: E402  (owns the reconcile contract)

# One entry per logical field the findings "keywords" rows carry
# (qs_core.build_rows reads: ad_group, campaign, keyword, match_type,
# quality_score, landing_page_exp, ad_relevance, expected_ctr, impressions,
# clicks, cost, conversions). "0/--/blank" QS and triad cells all mean
# UNSCORED / unknown — the same honest treatment as the MCP path.
COLUMN_MAP = {
    "keyword":          {"aliases": ["Keyword", "Search keyword"], "type": "str"},
    "match_type":       {"aliases": ["Match type"], "type": "str"},
    "ad_group":         {"aliases": ["Ad group"], "type": "str"},
    "campaign":         {"aliases": ["Campaign"], "type": "str"},
    "quality_score":    {"aliases": ["Quality Score", "Qual. score", "Quality score"], "type": "num"},
    "landing_page_exp": {"aliases": ["Landing page exp.", "Landing page experience"], "type": "str"},
    "ad_relevance":     {"aliases": ["Ad relevance"], "type": "str"},
    "expected_ctr":     {"aliases": ["Expected CTR", "Exp. CTR", "Expected clickthrough rate (CTR)"],
                          "type": "str"},
    "impressions":      {"aliases": ["Impr.", "Impressions"], "type": "num"},
    "clicks":           {"aliases": ["Clicks", "Interactions"], "type": "num"},
    "cost":             {"aliases": ["Cost"], "type": "num"},
    "conversions":      {"aliases": ["Conversions", "Conv."], "type": "num"},
}
REQUIRED_FIELDS = ("keyword", "ad_group", "campaign", "impressions", "clicks", "cost", "conversions")
RECONCILE_SPEC = {"array": "keywords", "sums": core.RECONCILE_ARRAYS["keywords"]}

_MATCH_SUFFIX = re.compile(r"\s*match\s*$", re.IGNORECASE)


def _norm_match_type(v) -> str:
    """'Broad match' / 'broad' / 'BROAD' -> 'BROAD' — the UI shows the human
    label ('Broad match'); qs_core.build_rows expects the GAQL enum token."""
    return _MATCH_SUFFIX.sub("", str(v or "").strip()).strip().upper()


def assemble_csv(csv_path: str, meta: dict) -> dict:
    rows, findings = assemble_from_csv(
        csv_path, column_map=COLUMN_MAP, required_fields=REQUIRED_FIELDS,
        reconcile_spec=RECONCILE_SPEC, meta=meta)
    for r in rows:
        r["match_type"] = _norm_match_type(r.get("match_type"))
        # the UI export carries no internal ad-group id; the account-unique
        # ad group name stands in so the CSV path dedupes/groups exactly like
        # the MCP path's ad_group_id.
        r["ad_group_id"] = r["ad_group"]
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description="Assemble the Quality Score findings JSON "
                                             "from a user-supplied Google Ads UI CSV export.")
    ap.add_argument("--csv", required=True,
                    help="Keywords export with the Quality Score diagnostic columns added")
    ap.add_argument("--client-name", required=True)
    ap.add_argument("--account-id", required=True)
    ap.add_argument("--currency", required=True)
    ap.add_argument("--period", required=True,
                    help='window label, e.g. "last 30 days" — the date range set in the export')
    ap.add_argument("--generated", default=None,
                    help="report date (YYYY-MM-DD); defaults to today")
    ap.add_argument("-o", "--output", required=True, help="findings JSON output path")
    args = ap.parse_args()

    meta = {"client_name": args.client_name, "account_id": args.account_id,
            "currency": args.currency, "period": args.period,
            "generated": args.generated or datetime.date.today().isoformat()}
    try:
        findings = assemble_csv(args.csv, meta)
    except CsvInputError as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return 1

    Path(args.output).write_text(json.dumps(findings, ensure_ascii=False, indent=1))
    rec = findings["meta"]["reconciliation"]["keywords"]
    unscored = sum(1 for k in findings["keywords"] if not k["quality_score"])
    print(f"Wrote {args.output}")
    print(f"  keywords: {rec['rows']} ({unscored} unscored; cost {rec['sums']['cost']:,.2f} "
          f"{args.currency}, clicks {rec['sums']['clicks']:,.0f})")
    print(f"  meta.source={findings['meta']['source']} — reconciliation totals embedded "
          "(the builder re-verifies them on every run)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
