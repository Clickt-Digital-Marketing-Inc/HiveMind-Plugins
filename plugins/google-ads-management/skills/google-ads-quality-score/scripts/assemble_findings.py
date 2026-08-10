#!/usr/bin/env python3
"""Assemble the Quality Score findings JSON from a saved raw GAQL pull (script-only).

The transcription firewall for this skill: the keyword_view pull is saved
verbatim to a file (auto-saved by the harness when large, copied verbatim
when small) and THIS script — never the model — turns it into the findings
JSON. Metric values go raw file -> parser -> findings without ever passing
through a token stream, and control totals are embedded as
meta.reconciliation so qs_core hard-fails if the findings are later edited
or were produced any other way.

Usage:
    python3 assemble_findings.py \
        --keywords tool-results/keywords.txt \
        --client-name "Acme Corp" --account-id 123-456-7890 --currency CAD \
        --period "last 30 days" \
        -o findings.json

Aggregates rows by (ad_group_id, keyword, match_type) — the same key qs_core
dedupes by — summing impressions/clicks/cost/conversions; the quality score
and the triad ratings are point-in-time and taken from the first occurrence,
exactly as the core's dedupe does. quality_score 0/null/absent = UNSCORED
(kept as null, never a literal 0).

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
import qs_core as core      # noqa: E402  (owns the reconcile contract)

# metrics.ctr is in the documented pull but not required here — CTR is always
# recomputed from the summed clicks/impressions. The quality_score + triad
# fields are also NOT required per-row: 0/null/ABSENT all mean UNSCORED (too
# little data), and unset fields may be omitted from the saved rows entirely.
KEYWORDS_FIELDS = ("campaign.name", "ad_group.id", "ad_group.name",
                   "ad_group_criterion.keyword.text",
                   "ad_group_criterion.keyword.match_type",
                   "metrics.impressions", "metrics.clicks",
                   "metrics.cost_micros", "metrics.conversions")
QS_FIELD = "ad_group_criterion.quality_info.quality_score"
LP_FIELD = "ad_group_criterion.quality_info.post_click_quality_score"
AR_FIELD = "ad_group_criterion.quality_info.creative_quality_score"
CTRQ_FIELD = "ad_group_criterion.quality_info.search_predicted_ctr"

# SKILL.md "Pull the data" #2 (search terms, low-CTR drag) and #4 (ads/RSA
# assets, ad-relevance matrix) are prose-only pulls with no findings
# assembler of their own — these two constants exist purely to bind the
# documented field lists to code per HM-606
# (skills/google-ads/tests/test_gaql_schema.py); nothing here imports them.
SEARCH_TERMS_FIELDS = ("campaign.id", "campaign.name", "ad_group.id", "ad_group.name",
                       "search_term_view.search_term", "segments.keyword.info.text",
                       "segments.keyword.info.match_type", "metrics.impressions",
                       "metrics.clicks", "metrics.ctr", "metrics.cost_micros",
                       "metrics.conversions")
AD_ASSETS_FIELDS = ("campaign.id", "campaign.name", "ad_group.id", "ad_group.name",
                    "ad_group_ad.ad.id", "ad_group_ad.ad_strength",
                    "ad_group_ad.ad.responsive_search_ad.headlines",
                    "ad_group_ad.ad.responsive_search_ad.descriptions")

# Control totals verified by qs_core.load_findings on every build; the
# contract (which arrays, which fields) is owned by the core.
RECONCILE_ARRAYS = core.RECONCILE_ARRAYS


def _key(ad_group_id, keyword, match_type):
    return (ad_group_id, str(keyword or ""), str(match_type or "").upper())


def _qs(v):
    """1–10 stays an int; 0/null/absent/garbage = unscored (None)."""
    try:
        q = int(float(v))
    except (TypeError, ValueError):
        return None
    return q if q > 0 else None


def assemble(keywords_path: str, meta: dict) -> dict:
    rows = G.load_rows(keywords_path, require_fields=KEYWORDS_FIELDS)

    # Aggregate by the core's dedupe key (a segment such as device can split a
    # key into several raw rows; sums are preserved, QS/ratings point-in-time).
    merged: dict = {}
    order: list = []
    for r in rows:
        mt = str(r.get("ad_group_criterion.keyword.match_type") or "").upper()
        k = _key(r.get("ad_group.id"), r.get("ad_group_criterion.keyword.text"), mt)
        if k not in merged:
            merged[k] = {"ad_group_id": r.get("ad_group.id"),
                         "ad_group": r.get("ad_group.name") or "",
                         "campaign": r.get("campaign.name") or "",
                         "keyword": r.get("ad_group_criterion.keyword.text") or "",
                         "match_type": mt,
                         "quality_score": _qs(r.get(QS_FIELD)),
                         "landing_page_exp": str(r.get(LP_FIELD) or ""),
                         "ad_relevance": str(r.get(AR_FIELD) or ""),
                         "expected_ctr": str(r.get(CTRQ_FIELD) or ""),
                         "impressions": 0.0, "clicks": 0.0, "cost": 0.0,
                         "conversions": 0.0}
            order.append(k)
        m = merged[k]
        m["impressions"] += G.num(r.get("metrics.impressions"))
        m["clicks"] += G.num(r.get("metrics.clicks"))
        m["cost"] += G.micros(r.get("metrics.cost_micros"))
        m["conversions"] += G.num(r.get("metrics.conversions"))
    keywords = []
    for k in order:
        m = merged[k]
        m["cost"] = round(m["cost"], 6)
        keywords.append(m)

    findings = {"meta": meta, "params": {}, "keywords": keywords}
    findings["meta"]["reconciliation"] = R.build(
        findings, RECONCILE_ARRAYS, raw_stamps=[G.file_stamp(keywords_path)])
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description="Assemble the Quality Score findings JSON "
                                             "from a saved raw GAQL pull.")
    ap.add_argument("--keywords", required=True,
                    help="raw keyword_view + QS triad (30d) results file")
    ap.add_argument("--client-name", required=True)
    ap.add_argument("--account-id", required=True)
    ap.add_argument("--currency", required=True)
    ap.add_argument("--period", required=True,
                    help='window label, e.g. "last 30 days" — the window used in the GAQL condition')
    ap.add_argument("--generated", default=None,
                    help="report date (YYYY-MM-DD); defaults to today — pass the "
                         "original date when re-assembling for byte-identical output")
    ap.add_argument("-o", "--output", required=True, help="findings JSON output path")
    args = ap.parse_args()

    meta = {"client_name": args.client_name, "account_id": args.account_id,
            "currency": args.currency, "period": args.period,
            "generated": args.generated or datetime.date.today().isoformat(),
            "source": "mcp"}
    try:
        findings = assemble(args.keywords, meta)
    except (G.RawResultError, OSError) as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return 1

    Path(args.output).write_text(json.dumps(findings, ensure_ascii=False, indent=1))
    rec = findings["meta"]["reconciliation"]
    kw = rec["keywords"]
    unscored = sum(1 for k in findings["keywords"] if k["quality_score"] is None)
    print(f"Wrote {args.output}")
    print(f"  keywords: {kw['rows']} ({unscored} unscored; cost {kw['sums']['cost']:,.2f} "
          f"{args.currency}, clicks {kw['sums']['clicks']:,.0f})")
    print("  reconciliation totals embedded — the builder verifies them on every run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
