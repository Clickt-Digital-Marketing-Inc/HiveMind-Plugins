#!/usr/bin/env python3
"""Assemble the waste-filter findings JSON from saved raw GAQL pulls (script-only).

The transcription firewall for this skill: the three search_search pulls are
saved verbatim to files (auto-saved by the harness when large, copied verbatim
when small) and THIS script — never the model — turns them into the findings
JSON. Metric values go raw file -> parser -> findings without ever passing
through a token stream, and control totals are embedded as
meta.reconciliation so waste_filter_core hard-fails if the findings are later
edited or were produced any other way.

Usage:
    python3 assemble_findings.py \
        --terms-90d tool-results/terms90.txt \
        --terms-30d tool-results/terms30.txt \
        --benchmarks tool-results/bench.txt \
        --client-name "Acme Corp" --account-id 123-456-7890 --currency CAD \
        --window-90d "2026-04-07 to 2026-07-05" \
        --window-30d "2026-06-06 to 2026-07-05" \
        -o findings.json

Pass the SAME dates used in the GAQL conditions for the window labels.
Aggregates 90d rows by (campaign_id, ad_group, term, match_type) — the same
key waste_filter_core dedupes by — joins the 30d converted set on that key,
and drops any EXACT rows defensively (the pulls exclude them at source).

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
import csv_input as C       # noqa: E402  (the CSV twin of gaql_raw — dual input, HM-534)

sys.path.insert(0, str(HERE))
import waste_filter_core as core  # noqa: E402  (owns the reconcile contract)

# metrics.ctr is in the documented pull but not required here — CTR is always
# recomputed from the summed clicks/impressions so segment splits stay honest.
TERMS_90D_FIELDS = ("campaign.id", "campaign.name", "ad_group.name",
                    "search_term_view.search_term", "segments.search_term_match_type",
                    "metrics.conversions", "metrics.clicks", "metrics.impressions",
                    "metrics.cost_micros")
TERMS_30D_FIELDS = ("campaign.id", "ad_group.name", "search_term_view.search_term",
                    "segments.search_term_match_type", "metrics.conversions")
BENCH_FIELDS = ("campaign.id", "campaign.name", "metrics.ctr",
                "metrics.cost_micros", "metrics.conversions")

# SKILL.md "Pull the data" #2/#3 (basic SQR audit + monthly keyword analysis)
# are prose-only pulls with no findings assembler of their own — these two
# constants exist purely to bind the documented field lists to code per
# HM-606 (skills/google-ads/tests/test_gaql_schema.py); nothing here imports
# them.
NEGATIVES_FIELDS = ("campaign.id", "campaign.name", "campaign_criterion.keyword.text",
                    "campaign_criterion.keyword.match_type", "campaign_criterion.type",
                    "campaign_criterion.negative")
KEYWORD_QS_FIELDS = ("ad_group.id", "ad_group.name", "campaign.id", "campaign.name",
                     "ad_group_criterion.keyword.text", "ad_group_criterion.keyword.match_type",
                     "ad_group_criterion.quality_info.quality_score",
                     "metrics.impressions", "metrics.clicks", "metrics.ctr",
                     "metrics.average_cpc", "metrics.cost_micros", "metrics.conversions",
                     "metrics.conversions_value")

# Control totals verified by waste_filter_core.load_findings on every build;
# the contract (which arrays, which fields) is owned by the core.
RECONCILE_ARRAYS = core.RECONCILE_ARRAYS


def _key(campaign_id, ad_group, term, match_type):
    return (campaign_id, str(ad_group or ""), str(term or ""), str(match_type or "").upper())


# ---------------------------------------------------------------------------
# CSV manual-input path (dual input — google-ads-foundation/references/
# artifact-formats.md). Google Ads UI exports: "Insights & reports -> Search
# terms" (twice — once for the 90d window, once for the 30d window with
# conversions filtered/sorted so only converters need be kept) for the term
# CSVs, and "Campaigns" for the benchmark CSV. Column headers are the UI's
# default report column names; add an alias + a fixture test if a real export
# uses a different spelling (see the Lessons Log convention).
# ---------------------------------------------------------------------------
# "Campaign ID" is OPTIONAL: the UI export has no numeric campaign id by
# default, but the operator can add the column. When present it is used as
# the join key (byte-identical to the MCP path's campaign.id); when absent,
# the campaign NAME is the join key instead — honest about what a plain
# export actually contains, and correct unless two campaigns share a name.
TERMS_COLUMN_MAP = {
    "campaign_id": {"aliases": ["Campaign ID", "Campaign Id"], "type": "num"},
    "campaign":    {"aliases": ["Campaign", "Campaign name"], "type": "str"},
    "ad_group":    {"aliases": ["Ad group", "Ad group name"], "type": "str"},
    "term":        {"aliases": ["Search term", "Search terms"], "type": "str"},
    "match_type":  {"aliases": ["Match type"], "type": "str"},
    "impressions": {"aliases": ["Impr.", "Impr", "Impressions"], "type": "num"},
    "clicks":      {"aliases": ["Clicks", "Interactions"], "type": "num"},
    "cost":        {"aliases": ["Cost"], "type": "num"},
    "conversions": {"aliases": ["Conversions"], "type": "num"},
}
REQUIRED_TERMS_90D_CSV = ("campaign", "ad_group", "term", "match_type",
                          "impressions", "clicks", "cost", "conversions")
REQUIRED_TERMS_30D_CSV = ("campaign", "ad_group", "term", "match_type", "conversions")

BENCH_COLUMN_MAP = {
    "campaign_id": {"aliases": ["Campaign ID", "Campaign Id"], "type": "num"},
    "campaign":    {"aliases": ["Campaign", "Campaign name"], "type": "str"},
    "ctr":         {"aliases": ["CTR"], "type": "pct"},
    "cost":        {"aliases": ["Cost"], "type": "num"},
    "conversions": {"aliases": ["Conversions"], "type": "num"},
}
REQUIRED_BENCH_CSV = ("campaign", "ctr", "cost", "conversions")

# The Google Ads UI's "Match type" report label -> the GAQL enum
# waste_filter_core expects (segments.search_term_match_type). Add an entry +
# a fixture test if a real export uses a spelling not covered here.
MATCH_TYPE_UI_MAP = {
    "broad match": "BROAD", "broad": "BROAD",
    "phrase match": "PHRASE", "phrase": "PHRASE",
    "exact match": "EXACT", "exact": "EXACT",
    "exact match (close variant)": "NEAR_EXACT", "close variant": "NEAR_EXACT",
    "near exact": "NEAR_EXACT",
    "phrase match (close variant)": "NEAR_PHRASE", "near phrase": "NEAR_PHRASE",
    "ai max": "AI_MAX", "ai. max": "AI_MAX",
}


def _map_match_type(v) -> str:
    return MATCH_TYPE_UI_MAP.get(str(v or "").strip().lower(), str(v or "").strip().upper())


def _row_campaign_id(row: dict):
    """Numeric Campaign ID when the export carried one (matches the MCP path's
    campaign.id byte-for-byte); otherwise the campaign name as a stable join
    key — the CSV path is honest about what a plain UI export contains.
    Assumes the "Campaign ID" column, when present in the export, is
    populated on every row (true for a real Google Ads UI export — it is a
    non-nullable system field); a spreadsheet hand-edited to blank some IDs
    while keeping others would silently fall back to the name key per row,
    which could split one campaign across two join keys."""
    cid = row.get("campaign_id")
    if cid:
        try:
            return int(cid)
        except (TypeError, ValueError):
            pass
    return row.get("campaign", "")


def assemble_csv(terms90_path: str, terms30_path: str, bench_path: str, meta: dict) -> dict:
    """CSV twin of assemble() — same aggregation/dedupe/join, sourced from
    three Google Ads UI exports instead of three saved raw MCP pulls. Numbers
    never pass through the model: _shared/csv_input.load_csv_rows parses the
    files, this function only aggregates/joins the typed rows it returns."""
    t90, stamp90 = C.load_csv_rows(terms90_path, TERMS_COLUMN_MAP, REQUIRED_TERMS_90D_CSV)
    t30, stamp30 = C.load_csv_rows(terms30_path, TERMS_COLUMN_MAP, REQUIRED_TERMS_30D_CSV)
    bench_rows, stampb = C.load_csv_rows(bench_path, BENCH_COLUMN_MAP, REQUIRED_BENCH_CSV)

    conv30: dict = {}
    for r in t30:
        mt = _map_match_type(r.get("match_type"))
        if mt == "EXACT":
            continue
        k = _key(_row_campaign_id(r), r.get("ad_group"), r.get("term"), mt)
        conv30[k] = conv30.get(k, 0.0) + float(r.get("conversions") or 0)

    merged: dict = {}
    order: list = []
    dropped_exact = 0
    for r in t90:
        mt = _map_match_type(r.get("match_type"))
        if mt == "EXACT":
            dropped_exact += 1
            continue
        cid = _row_campaign_id(r)
        k = _key(cid, r.get("ad_group"), r.get("term"), mt)
        if k not in merged:
            merged[k] = {"campaign_id": cid, "campaign": r.get("campaign", ""),
                         "ad_group": r.get("ad_group", ""), "term": r.get("term", ""),
                         "match_type": mt, "impressions": 0.0, "clicks": 0.0,
                         "cost": 0.0, "conversions_90d": 0.0}
            order.append(k)
        m = merged[k]
        m["impressions"] += float(r.get("impressions") or 0)
        m["clicks"] += float(r.get("clicks") or 0)
        m["cost"] += float(r.get("cost") or 0)
        m["conversions_90d"] += float(r.get("conversions") or 0)
    search_terms = []
    for k in order:
        m = merged[k]
        m["ctr"] = (m["clicks"] / m["impressions"]) if m["impressions"] else 0.0
        m["cost"] = round(m["cost"], 6)
        m["conversions_30d"] = round(conv30.get(k, 0.0), 6)
        search_terms.append(m)

    benchmarks = [{"campaign_id": _row_campaign_id(r), "campaign": r.get("campaign", ""),
                  "ctr": float(r.get("ctr") or 0),
                  "cost": round(float(r.get("cost") or 0), 6),
                  "conversions": float(r.get("conversions") or 0)}
                 for r in bench_rows]

    if dropped_exact:
        sys.stderr.write(f"NOTE: dropped {dropped_exact} EXACT-match rows from the 90d CSV "
                         "(filter the export to loose match, or leave them — they are excluded here)\n")

    meta = dict(meta)
    meta.setdefault("source", "user_csv")
    findings = {"meta": meta, "params": {}, "benchmarks": benchmarks, "search_terms": search_terms}
    findings["meta"]["reconciliation"] = R.build(
        findings, RECONCILE_ARRAYS, raw_stamps=[stamp90, stamp30, stampb])
    return findings


def assemble(terms90_path: str, terms30_path: str, bench_path: str, meta: dict) -> dict:
    t90 = G.load_rows(terms90_path, require_fields=TERMS_90D_FIELDS)
    t30 = G.load_rows(terms30_path, require_fields=TERMS_30D_FIELDS)
    bench_rows = G.load_rows(bench_path, require_fields=BENCH_FIELDS)

    # 30d converted set: conversions summed per dedupe key.
    conv30: dict = {}
    for r in t30:
        if str(r.get("segments.search_term_match_type", "")).upper() == "EXACT":
            continue
        k = _key(r.get("campaign.id"), r.get("ad_group.name"),
                 r.get("search_term_view.search_term"),
                 r.get("segments.search_term_match_type"))
        conv30[k] = conv30.get(k, 0.0) + G.num(r.get("metrics.conversions"))

    # 90d universe aggregated by the same key (segments can split a key into
    # several raw rows; sums are preserved, CTR recomputed from the sums).
    merged: dict = {}
    order: list = []
    dropped_exact = 0
    for r in t90:
        mt = str(r.get("segments.search_term_match_type", "")).upper()
        if mt == "EXACT":
            dropped_exact += 1
            continue
        k = _key(r.get("campaign.id"), r.get("ad_group.name"),
                 r.get("search_term_view.search_term"), mt)
        if k not in merged:
            merged[k] = {"campaign_id": r.get("campaign.id"),
                         "campaign": r.get("campaign.name", ""),
                         "ad_group": r.get("ad_group.name", ""),
                         "term": r.get("search_term_view.search_term", ""),
                         "match_type": mt,
                         "impressions": 0.0, "clicks": 0.0, "cost": 0.0,
                         "conversions_90d": 0.0}
            order.append(k)
        m = merged[k]
        m["impressions"] += G.num(r.get("metrics.impressions"))
        m["clicks"] += G.num(r.get("metrics.clicks"))
        m["cost"] += G.micros(r.get("metrics.cost_micros"))
        m["conversions_90d"] += G.num(r.get("metrics.conversions"))
    search_terms = []
    for k in order:
        m = merged[k]
        m["ctr"] = (m["clicks"] / m["impressions"]) if m["impressions"] else 0.0
        m["cost"] = round(m["cost"], 6)
        m["conversions_30d"] = round(conv30.get(k, 0.0), 6)
        search_terms.append(m)

    benchmarks = [{"campaign_id": r.get("campaign.id"),
                   "campaign": r.get("campaign.name", ""),
                   "ctr": G.num(r.get("metrics.ctr")),
                   "cost": round(G.micros(r.get("metrics.cost_micros")), 6),
                   "conversions": G.num(r.get("metrics.conversions"))}
                  for r in bench_rows]

    if dropped_exact:
        sys.stderr.write(f"NOTE: dropped {dropped_exact} EXACT-match raw rows "
                         "(the pull should exclude them at source)\n")

    meta = dict(meta)
    meta.setdefault("source", "mcp")  # canonical live-pull token (HM-572)
    findings = {"meta": meta, "params": {},
                "benchmarks": benchmarks, "search_terms": search_terms}
    findings["meta"]["reconciliation"] = R.build(
        findings, RECONCILE_ARRAYS,
        raw_stamps=[G.file_stamp(p) for p in (terms90_path, terms30_path, bench_path)])
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Assemble waste-filter findings JSON from saved raw GAQL pulls "
                    "(MCP path) or from three Google Ads UI CSV exports (CSV path). "
                    "Pass exactly one set of the two input groups below.")
    mcp = ap.add_argument_group("MCP path — saved raw search_search pulls")
    mcp.add_argument("--terms-90d", help="raw search_term_view 90d results file")
    mcp.add_argument("--terms-30d", help="raw search_term_view 30d (conversions>0) results file")
    mcp.add_argument("--benchmarks", help="raw campaign benchmarks 90d results file")
    csvg = ap.add_argument_group("CSV path — Google Ads UI exports (no MCP required)")
    csvg.add_argument("--csv-terms-90d", help="'Search terms' report CSV export, 90d window")
    csvg.add_argument("--csv-terms-30d", help="'Search terms' report CSV export, 30d window "
                                              "(conversions > 0 rows)")
    csvg.add_argument("--csv-benchmarks", help="'Campaigns' report CSV export, 90d window")
    ap.add_argument("--client-name", required=True)
    ap.add_argument("--account-id", required=True)
    ap.add_argument("--currency", required=True)
    ap.add_argument("--window-90d", required=True, help='e.g. "2026-04-07 to 2026-07-05" — the dates used in the GAQL BETWEEN (or the CSV export range)')
    ap.add_argument("--window-30d", required=True)
    ap.add_argument("--generated", default=None,
                    help="report date (YYYY-MM-DD); defaults to today — pass the "
                         "original date when re-assembling for byte-identical output")
    ap.add_argument("-o", "--output", required=True, help="findings JSON output path")
    args = ap.parse_args()

    mcp_given = (args.terms_90d, args.terms_30d, args.benchmarks)
    csv_given = (args.csv_terms_90d, args.csv_terms_30d, args.csv_benchmarks)
    use_mcp = all(mcp_given)
    use_csv = all(csv_given)
    if use_mcp == use_csv:   # neither complete, or both complete — ambiguous
        sys.stderr.write(
            "ERROR: pass exactly one complete input set — either all three of "
            "--terms-90d/--terms-30d/--benchmarks (MCP path) or all three of "
            "--csv-terms-90d/--csv-terms-30d/--csv-benchmarks (CSV path).\n")
        return 1

    meta = {"client_name": args.client_name, "account_id": args.account_id,
            "currency": args.currency, "window_90d": args.window_90d,
            "window_30d": args.window_30d,
            "generated": args.generated or datetime.date.today().isoformat()}
    try:
        if use_mcp:
            findings = assemble(args.terms_90d, args.terms_30d, args.benchmarks, meta)
        else:
            findings = assemble_csv(args.csv_terms_90d, args.csv_terms_30d,
                                    args.csv_benchmarks, meta)
    except (G.RawResultError, C.CsvInputError, OSError) as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return 1

    Path(args.output).write_text(json.dumps(findings, ensure_ascii=False, indent=1))
    rec = findings["meta"]["reconciliation"]
    st, bm = rec["search_terms"], rec["benchmarks"]
    print(f"Wrote {args.output}")
    print(f"  search_terms: {st['rows']} (cost {st['sums']['cost']:,.2f} {args.currency}, "
          f"clicks {st['sums']['clicks']:,.0f})")
    print(f"  benchmarks:   {bm['rows']} campaigns (cost {bm['sums']['cost']:,.2f} {args.currency})")
    print(f"  source: {findings['meta']['source']}")
    print("  reconciliation totals embedded — the builder verifies them on every run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
