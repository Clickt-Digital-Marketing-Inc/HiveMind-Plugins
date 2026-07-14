#!/usr/bin/env python3
"""Tests for the shared CSV manual-input path (stdlib only; run directly).

    python3 _shared/tests/test_csv_input.py

Covers csv_input (column-map validation, alias/suffix header matching,
defensive header scan over title rows, Total-row drop, typed conversion,
missing/ambiguous/empty errors) and — the core acceptance — that a fixture
CSV assembles to a findings dict IDENTICAL in shape to the same data
assembled through the MCP path (gaql_raw + reconcile).
Exit 0 = all pass, 1 = a failure.
"""
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHARED = HERE.parent
sys.path.insert(0, str(SHARED))

import csv_input as C   # noqa: E402
import gaql_raw as G    # noqa: E402
import reconcile as R   # noqa: E402

_failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        _failures.append(name)


def _write(td, name, text):
    p = Path(td) / name
    p.write_text(text)
    return str(p)


def _raises(fn, *args, **kw):
    """Run fn; return the CsvInputError message or None if it didn't raise."""
    try:
        fn(*args, **kw)
        return None
    except C.CsvInputError as e:
        return str(e)


# ---------------------------------------------------------------- fixtures

COLUMN_MAP = {
    "term":        {"aliases": ["Search term", "Search terms"], "type": "str"},
    "campaign":    {"aliases": ["Campaign", "Campaign name"], "type": "str"},
    "cost":        {"aliases": ["Cost"], "type": "num"},
    "clicks":      {"aliases": ["Clicks", "Interactions"], "type": "num"},
    "conversions": {"aliases": ["Conversions", "Conv."], "type": "num"},
    "ctr":         {"aliases": ["CTR", "Interaction rate"], "type": "pct"},
}
REQUIRED = ("term", "campaign", "cost", "clicks", "conversions")
RECONCILE_SPEC = {"array": "search_terms",
                  "sums": ["cost", "clicks", "conversions"]}
META = {"client_name": "Acme Corp", "account_id": "123-456-7890",
        "currency": "CAD", "window_90d": "2026-04-07 to 2026-07-05",
        "generated": "2026-07-12"}

# The same three rows expressed as (a) a verbatim MCP raw pull and (b) a
# Google Ads UI CSV export. cost_micros/1e6 == the CSV Cost column.
_MCP_RAW = {"result": [
    {"campaign.name": "Brand", "search_term_view.search_term": "acme shoes",
     "metrics.cost_micros": 1_500_000, "metrics.clicks": 30,
     "metrics.conversions": 2.0, "metrics.ctr": 0.035},
    {"campaign.name": "Generic", "search_term_view.search_term": "cheap boots",
     "metrics.cost_micros": 12_340_000, "metrics.clicks": 55,
     "metrics.conversions": 0.0, "metrics.ctr": 0.021},
    {"campaign.name": "Generic", "search_term_view.search_term": "boot repair",
     "metrics.cost_micros": 250_000, "metrics.clicks": 4,
     "metrics.conversions": 1.0, "metrics.ctr": 0.08},
]}
_MCP_FIELDS = ("campaign.name", "search_term_view.search_term",
               "metrics.cost_micros", "metrics.clicks", "metrics.conversions",
               "metrics.ctr")

# UI export quirks on purpose: title rows above the header, currency-suffixed
# Cost header, thousands comma, percent CTR, an extra (unmapped) column, and
# a Total summary row.
_UI_CSV = """Search terms report
"April 7, 2026 - July 5, 2026"
Search term,Match type,Campaign,Cost (CAD),Clicks,Conversions,CTR
acme shoes,Phrase,Brand,1.50,30,2.0,3.5%
cheap boots,Broad,Generic,"12.34",55,0,2.1%
boot repair,Broad,Generic,0.25,4,1,8%
Total: search terms,,,14.09,89,3,
"""


def _assemble_mcp(td) -> dict:
    """Mini MCP-path assembler — the same discipline as a skill's
    assemble_findings.py (gaql_raw.load_rows -> transform -> reconcile.build)."""
    raw_path = _write(td, "terms_raw.txt", json.dumps(_MCP_RAW))
    rows = []
    for r in G.load_rows(raw_path, require_fields=_MCP_FIELDS):
        rows.append({"term": r["search_term_view.search_term"],
                     "campaign": r["campaign.name"],
                     "cost": G.micros(r["metrics.cost_micros"]),
                     "clicks": G.num(r["metrics.clicks"]),
                     "conversions": G.num(r["metrics.conversions"]),
                     "ctr": G.num(r["metrics.ctr"])})
    findings = {"meta": dict(META, source="mcp"), "params": {},
                "search_terms": rows}
    findings["meta"]["reconciliation"] = R.build(
        findings, {"search_terms": RECONCILE_SPEC["sums"]},
        raw_stamps=[G.file_stamp(raw_path)])
    return findings


def test_csv_matches_mcp_shape():
    print("test_csv_matches_mcp_shape")
    with tempfile.TemporaryDirectory() as td:
        mcp = _assemble_mcp(td)
        csv_path = _write(td, "export.csv", _UI_CSV)
        rows, csvf = C.assemble_from_csv(csv_path, COLUMN_MAP, REQUIRED,
                                         RECONCILE_SPEC, meta=dict(META))

        check("same top-level keys", sorted(csvf) == sorted(mcp))
        check("rows returned == findings array", rows is csvf["search_terms"])
        check("same row count", len(csvf["search_terms"]) == len(mcp["search_terms"]))
        check("identical row dicts (values + keys)",
              csvf["search_terms"] == mcp["search_terms"],
              f"csv={csvf['search_terms']!r} mcp={mcp['search_terms']!r}")
        rec_c = csvf["meta"]["reconciliation"]["search_terms"]
        rec_m = mcp["meta"]["reconciliation"]["search_terms"]
        check("identical reconciliation totals", rec_c == rec_m,
              f"csv={rec_c!r} mcp={rec_m!r}")
        check("raw file stamped",
              csvf["meta"]["reconciliation"]["raw_files"][0]["file"] == "export.csv")
        # the assembled findings must pass the same verification the cores run
        R.verify(csvf, {"search_terms": RECONCILE_SPEC["sums"]})
        check("csv findings pass reconcile.verify", True)
        check("meta.source labels the manual path",
              csvf["meta"]["source"] == "user_csv")
        check("mcp meta untouched by comparison", mcp["meta"]["source"] == "mcp")


def test_aliased_headers():
    print("test_aliased_headers")
    aliased = _UI_CSV.replace(
        "Search term,Match type,Campaign,Cost (CAD),Clicks,Conversions,CTR",
        "Search terms,Match type,Campaign name,Cost,Interactions,Conv.,Interaction rate")
    with tempfile.TemporaryDirectory() as td:
        rows, f = C.assemble_from_csv(_write(td, "a.csv", aliased), COLUMN_MAP,
                                      REQUIRED, RECONCILE_SPEC, meta=dict(META))
        check("alias headers resolve", len(rows) == 3)
        check("aliased numeric values parsed", rows[1]["cost"] == 12.34)
        check("aliased pct parsed to fraction", rows[0]["ctr"] == 0.035)
        # case/whitespace-insensitive matching
        sloppy = _UI_CSV.replace("Search term,", "  SEARCH  TERM ,")
        rows2, _ = C.assemble_from_csv(_write(td, "b.csv", sloppy), COLUMN_MAP,
                                       REQUIRED, RECONCILE_SPEC, meta=dict(META))
        check("case/whitespace-insensitive header match", len(rows2) == 3)


def test_missing_columns():
    print("test_missing_columns")
    broken = _UI_CSV.replace("Conversions", "Something else")
    with tempfile.TemporaryDirectory() as td:
        msg = _raises(C.assemble_from_csv, _write(td, "a.csv", broken),
                      COLUMN_MAP, REQUIRED, RECONCILE_SPEC, meta=dict(META))
        check("missing column raises", msg is not None)
        check("error names the missing logical field",
              msg is not None and "'conversions'" in msg, msg or "")
        check("error lists the accepted aliases",
              msg is not None and "Conv." in msg, msg or "")


def test_ambiguous_columns():
    print("test_ambiguous_columns")
    dup = _UI_CSV.replace("Cost (CAD),Clicks", "Cost,Cost (CAD),Clicks")
    with tempfile.TemporaryDirectory() as td:
        msg = _raises(C.assemble_from_csv, _write(td, "a.csv", dup),
                      COLUMN_MAP, REQUIRED, RECONCILE_SPEC, meta=dict(META))
        check("duplicate matching columns raise", msg is not None)
        check("error says which field is ambiguous",
              msg is not None and "'cost'" in msg, msg or "")
    # one column matching two logical fields
    cmap = dict(COLUMN_MAP, clicks={"aliases": ["Clicks"], "type": "num"},
                taps={"aliases": ["Clicks"], "type": "num"})
    with tempfile.TemporaryDirectory() as td:
        msg = _raises(C.assemble_from_csv, _write(td, "b.csv", _UI_CSV),
                      cmap, REQUIRED, RECONCILE_SPEC, meta=dict(META))
        check("one column claimed by two fields raises", msg is not None)


def test_empty_and_missing_file():
    print("test_empty_and_missing_file")
    with tempfile.TemporaryDirectory() as td:
        msg = _raises(C.assemble_from_csv, _write(td, "a.csv", ""),
                      COLUMN_MAP, REQUIRED, RECONCILE_SPEC, meta=dict(META))
        check("empty file raises", msg is not None and "empty" in msg, msg or "")
        msg = _raises(C.assemble_from_csv, _write(td, "b.csv", "\n\n  \n"),
                      COLUMN_MAP, REQUIRED, RECONCILE_SPEC, meta=dict(META))
        check("whitespace-only file raises", msg is not None)
        msg = _raises(C.assemble_from_csv, str(Path(td) / "nope.csv"),
                      COLUMN_MAP, REQUIRED, RECONCILE_SPEC, meta=dict(META))
        check("missing file raises", msg is not None and "not found" in msg,
              msg or "")


def test_extra_columns_and_total_rows():
    print("test_extra_columns_and_total_rows")
    with tempfile.TemporaryDirectory() as td:
        rows, _ = C.assemble_from_csv(_write(td, "a.csv", _UI_CSV), COLUMN_MAP,
                                      REQUIRED, RECONCILE_SPEC, meta=dict(META))
        check("extra (unmapped) columns ignored",
              all("Match type" not in r and "match_type" not in r for r in rows))
        check("Total summary row dropped", len(rows) == 3)
        check("title rows above header skipped", rows[0]["term"] == "acme shoes")
        # no-row-loss: a real term starting with the word "total" is KEPT —
        # only 'Total: ...' (with colon) summary rows are dropped.
        kept = _UI_CSV.replace("boot repair,", "total gym reviews,")
        rows2, _ = C.assemble_from_csv(_write(td, "b.csv", kept), COLUMN_MAP,
                                       REQUIRED, RECONCILE_SPEC, meta=dict(META))
        check("data row starting with 'total' kept (no-row-loss)",
              len(rows2) == 3 and rows2[2]["term"] == "total gym reviews")


def test_typed_conversion():
    print("test_typed_conversion")
    quirks = ("Search term,Campaign,Cost,Clicks,Conversions,CTR\n"
              'weird spend,Brand,"CA$1,023.31","1,204",--,12.3%\n')
    with tempfile.TemporaryDirectory() as td:
        rows, _ = C.assemble_from_csv(_write(td, "a.csv", quirks), COLUMN_MAP,
                                      REQUIRED, RECONCILE_SPEC, meta=dict(META))
        r = rows[0]
        check("currency prefix + thousands comma", r["cost"] == 1023.31)
        check("thousands comma in count", r["clicks"] == 1204.0)
        check("'--' absent marker -> 0.0", r["conversions"] == 0.0)
        check("percent -> fraction", abs(r["ctr"] - 0.123) < 1e-12)


def test_contract_validation():
    print("test_contract_validation")
    with tempfile.TemporaryDirectory() as td:
        p = _write(td, "a.csv", _UI_CSV)
        msg = _raises(C.assemble_from_csv, p, COLUMN_MAP,
                      ("term", "not_declared"), RECONCILE_SPEC, meta=dict(META))
        check("required field missing from column_map raises",
              msg is not None and "not_declared" in msg, msg or "")
        msg = _raises(C.assemble_from_csv, p, COLUMN_MAP, REQUIRED,
                      {"array": "search_terms", "sums": ["term"]},
                      meta=dict(META))
        check("non-numeric reconcile sum field raises",
              msg is not None and "term" in msg, msg or "")
        msg = _raises(C.assemble_from_csv, p, COLUMN_MAP, REQUIRED, {},
                      meta=dict(META))
        check("empty reconcile_spec raises", msg is not None)
        msg = _raises(C.assemble_from_csv, p, COLUMN_MAP, (), RECONCILE_SPEC,
                      meta=dict(META))
        check("empty required_fields raises", msg is not None)
        cmap = dict(COLUMN_MAP, cost={"aliases": ["Cost"], "type": "money"})
        msg = _raises(C.assemble_from_csv, p, cmap, REQUIRED, RECONCILE_SPEC,
                      meta=dict(META))
        check("unknown type raises", msg is not None and "money" in msg,
              msg or "")


def main():
    for t in (test_csv_matches_mcp_shape, test_aliased_headers,
              test_missing_columns, test_ambiguous_columns,
              test_empty_and_missing_file, test_extra_columns_and_total_rows,
              test_typed_conversion, test_contract_validation):
        t()
    print()
    if _failures:
        print(f"FAILED ({len(_failures)}): {', '.join(_failures)}")
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
