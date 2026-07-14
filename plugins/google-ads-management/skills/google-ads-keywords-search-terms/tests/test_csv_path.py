#!/usr/bin/env python3
"""Tests for the CSV dual-input path (stdlib only; run directly).

    python3 tests/test_csv_path.py

The core acceptance (HM-536 / google-ads-foundation dual-input contract): the
SAME data assembled through the MCP path (assemble_findings.assemble, saved
raw search_search pulls) and through the CSV path (assemble_findings.
assemble_csv, three Google Ads UI exports) must yield an IDENTICAL
compute_model() output — the skill's core cannot tell them apart except by
the honest meta.source label. Also covers UI match-type label mapping,
the Campaign-ID-present vs name-fallback join key, and CsvInputError
propagation for a malformed export. Exit 0 = all pass, 1 = a failure.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE.parents[2] / "_shared"))

import assemble_findings as A     # noqa: E402
import csv_input as C             # noqa: E402
import waste_filter_core as core  # noqa: E402

_failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        _failures.append(name)


def _write(td, name, text):
    p = Path(td) / name
    p.write_text(text)
    return str(p)


META = {"client_name": "Acme Corp", "account_id": "123-456-7890", "currency": "USD",
        "window_90d": "2026-04-07 to 2026-07-05", "window_30d": "2026-06-06 to 2026-07-05",
        "generated": "2026-07-06"}

# Two campaigns, three 90d terms (one Block 1 qualifier, one clean), one 30d
# converted row, matching benchmarks — small enough to hand-verify, rich
# enough to exercise dedupe (a term split by device into two raw/CSV rows),
# EXACT-drop, and the join key. Campaign IDs are carried on BOTH paths so the
# join key matches byte-for-byte (the CSV "Campaign ID" column is optional —
# see test_campaign_name_fallback_join for the no-ID case).
_MCP_RAW_90D = {"result": [
    {"campaign.id": 1, "campaign.name": "Generic Search", "ad_group.name": "Generic",
     "search_term_view.search_term": "cheap gadget deal", "segments.search_term_match_type": "PHRASE",
     "metrics.conversions": 0, "metrics.clicks": 30, "metrics.impressions": 3000,
     "metrics.cost_micros": 150_000_000},
    # same key split across two raw rows (e.g. by device) -> must merge
    {"campaign.id": 1, "campaign.name": "Generic Search", "ad_group.name": "Generic",
     "search_term_view.search_term": "cheap gadget deal", "segments.search_term_match_type": "PHRASE",
     "metrics.conversions": 0, "metrics.clicks": 10, "metrics.impressions": 1000,
     "metrics.cost_micros": 30_000_000},
    {"campaign.id": 1, "campaign.name": "Generic Search", "ad_group.name": "Generic",
     "search_term_view.search_term": "solid converting term", "segments.search_term_match_type": "NEAR_EXACT",
     "metrics.conversions": 5, "metrics.clicks": 80, "metrics.impressions": 1000,
     "metrics.cost_micros": 40_000_000},
    # EXACT -> dropped defensively on both paths
    {"campaign.id": 1, "campaign.name": "Generic Search", "ad_group.name": "Generic",
     "search_term_view.search_term": "brand exact junk", "segments.search_term_match_type": "EXACT",
     "metrics.conversions": 0, "metrics.clicks": 1, "metrics.impressions": 10,
     "metrics.cost_micros": 500_000},
]}
_MCP_RAW_30D = {"result": [
    {"campaign.id": 1, "ad_group.name": "Generic", "search_term_view.search_term": "solid converting term",
     "segments.search_term_match_type": "NEAR_EXACT", "metrics.conversions": 2},
]}
_MCP_RAW_BENCH = {"result": [
    {"campaign.id": 1, "campaign.name": "Generic Search", "metrics.ctr": 0.08,
     "metrics.cost_micros": 2_000_000_000, "metrics.conversions": 40},
]}

# The UI CSV twin — with a "Campaign ID" column carrying the SAME id (1) so
# the join key matches the MCP path exactly. UI quirks folded in on purpose:
# a title row, a currency-suffixed Cost header, a percent CTR, an EXACT row
# to be dropped, and a Total summary row.
_CSV_TERMS_90D = """Search terms report
Search term,Match type,Campaign,Campaign ID,Ad group,Impr.,Clicks,Cost (USD),Conversions
cheap gadget deal,Phrase match,Generic Search,1,Generic,3000,30,150.00,0
cheap gadget deal,Phrase match,Generic Search,1,Generic,1000,10,30.00,0
solid converting term,Exact match (close variant),Generic Search,1,Generic,1000,80,40.00,5
brand exact junk,Exact match,Generic Search,1,Generic,10,1,0.50,0
Total: search terms,,,,,5010,121,220.50,5
"""
_CSV_TERMS_30D = """Search terms report
Search term,Match type,Campaign,Campaign ID,Ad group,Conversions
solid converting term,Exact match (close variant),Generic Search,1,Generic,2
"""
_CSV_BENCH = """Campaigns report
Campaign,Campaign ID,CTR,Cost,Conversions
Generic Search,1,8%,2000.00,40
"""


def _mcp_findings(td):
    p90 = _write(td, "t90.txt", json.dumps(_MCP_RAW_90D))
    p30 = _write(td, "t30.txt", json.dumps(_MCP_RAW_30D))
    pb = _write(td, "b.txt", json.dumps(_MCP_RAW_BENCH))
    return A.assemble(p90, p30, pb, dict(META))


def _csv_findings(td, terms90=_CSV_TERMS_90D, terms30=_CSV_TERMS_30D, bench=_CSV_BENCH):
    p90 = _write(td, "terms90.csv", terms90)
    p30 = _write(td, "terms30.csv", terms30)
    pb = _write(td, "bench.csv", bench)
    return A.assemble_csv(p90, p30, pb, dict(META))


def _strip_source(model):
    m = json.loads(json.dumps(model))   # compute_model is JSON-serializable per its docstring
    m["provenance"].pop("source", None)
    return m


def test_csv_matches_mcp_model():
    print("test_csv_matches_mcp_model")
    with tempfile.TemporaryDirectory() as td1, tempfile.TemporaryDirectory() as td2:
        mcp_findings = _mcp_findings(td1)
        csv_findings = _csv_findings(td2)

        check("mcp meta.source == mcp", mcp_findings["meta"]["source"] == "mcp")
        check("csv meta.source == user_csv", csv_findings["meta"]["source"] == "user_csv")

        mcp_model = core.compute_model(mcp_findings)
        csv_model = core.compute_model(csv_findings)
        a, b = _strip_source(mcp_model), _strip_source(csv_model)
        check("csv model identical to mcp model (aside from data source)", a == b,
              f"mcp={json.dumps(a)[:400]}\ncsv={json.dumps(b)[:400]}")
        check("both paths dedupe the split-by-device term",
              any(r["term"] == "cheap gadget deal" and r["clicks"] == 40.0
                  for r in mcp_model["rows"]))
        check("both paths drop the EXACT row (universe == 2, not 3)",
              mcp_model["summary"]["universe"] == 2 == csv_model["summary"]["universe"])
        check("both paths flag the same Block 1 term",
              mcp_model["summary"]["block1"] == 1 == csv_model["summary"]["block1"])
        check("both paths compute the same n-gram concentration",
              mcp_model["ngrams"] == csv_model["ngrams"])


def test_csv_match_type_ui_labels_mapped():
    print("test_csv_match_type_ui_labels_mapped")
    with tempfile.TemporaryDirectory() as td:
        findings = _csv_findings(td)
        mts = {r["match_type"] for r in findings["search_terms"]}
        check("'Phrase match' -> PHRASE", "PHRASE" in mts)
        check("'Exact match (close variant)' -> NEAR_EXACT", "NEAR_EXACT" in mts)
        check("'Exact match' rows dropped (never mapped into search_terms)", "EXACT" not in mts)

        # A dedicated small export covering every mapped UI label, independent
        # of the identical-model fixture above.
        labels = ("Search term,Match type,Campaign,Ad group,Impr.,Clicks,Cost,Conversions\n"
                 "t1,Broad match,C,G,10,1,1.00,0\n"
                 "t2,Phrase match (close variant),C,G,10,1,1.00,0\n"
                 "t3,AI Max,C,G,10,1,1.00,0\n")
        p = _write(td, "labels.csv", labels)
        rows, _ = C.load_csv_rows(p, A.TERMS_COLUMN_MAP, A.REQUIRED_TERMS_90D_CSV)
        mapped = {r["term"]: A._map_match_type(r["match_type"]) for r in rows}
        check("'Broad match' -> BROAD", mapped["t1"] == "BROAD")
        check("'Phrase match (close variant)' -> NEAR_PHRASE", mapped["t2"] == "NEAR_PHRASE")
        check("'AI Max' -> AI_MAX", mapped["t3"] == "AI_MAX")


def test_campaign_name_fallback_join():
    print("test_campaign_name_fallback_join")
    # Strip the "Campaign ID" column entirely -> falls back to campaign NAME
    # as the join key. Model shape must still be internally consistent (every
    # term finds its campaign's benchmark).
    no_id_90 = _CSV_TERMS_90D.replace(",Campaign ID,", ",")\
        .replace(",1,Generic,", ",Generic,")
    no_id_30 = _CSV_TERMS_30D.replace(",Campaign ID,", ",").replace(",1,Generic,", ",Generic,")
    no_id_bench = _CSV_BENCH.replace(",Campaign ID,", ",").replace("Generic Search,1,", "Generic Search,")
    with tempfile.TemporaryDirectory() as td:
        findings = _csv_findings(td, terms90=no_id_90, terms30=no_id_30, bench=no_id_bench)
        check("no Campaign ID column -> falls back to name", "campaign_id" not in findings["search_terms"][0]
              or findings["search_terms"][0]["campaign_id"] == "Generic Search")
        model = core.compute_model(findings)
        check("model still scores every term against its campaign (no orphaned no_benchmark)",
              model["summary"]["scored"] == model["summary"]["universe"] == 2,
              f"got {model['summary']}")


def test_csv_reconciliation_and_bad_export():
    print("test_csv_reconciliation_and_bad_export")
    with tempfile.TemporaryDirectory() as td:
        findings = _csv_findings(td)
        rec = findings["meta"]["reconciliation"]
        check("reconciliation embedded with 3 raw file stamps", len(rec.get("raw_files", [])) == 3)
        fp = Path(td) / "findings.json"
        fp.write_text(json.dumps(findings))
        core.load_findings(str(fp))
        check("csv findings load clean through the core", True)

        broken = _CSV_TERMS_90D.replace("Conversions", "Something else")
        p90 = _write(td, "broken.csv", broken)
        try:
            A.assemble_csv(p90, _write(td, "t30b.csv", _CSV_TERMS_30D),
                           _write(td, "bb.csv", _CSV_BENCH), dict(META))
            ok = False
        except C.CsvInputError as e:
            ok = "conversions" in str(e)
        check("malformed export (missing required column) raises CsvInputError naming the field", ok)


def main():
    for t in (test_csv_matches_mcp_model, test_csv_match_type_ui_labels_mapped,
              test_campaign_name_fallback_join, test_csv_reconciliation_and_bad_export):
        t()
    print()
    if _failures:
        print(f"FAILED ({len(_failures)}): {', '.join(_failures)}")
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
