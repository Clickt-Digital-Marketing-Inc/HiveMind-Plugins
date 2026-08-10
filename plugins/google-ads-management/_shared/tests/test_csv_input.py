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
    # Encoding pinned: the locale fixtures below carry NBSP / narrow-NBSP and
    # csv_input reads with utf-8-sig — a platform-default encoding here would
    # write a different file, or raise, on a non-utf-8 machine (HM-778).
    p.write_text(text, encoding="utf-8")
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


# A Google Ads UI export from an fr/de-locale account: no-break-space
# thousands groups (U+00A0 on the money column, U+202F — the group separator
# current CLDR gives fr-FR — on the counts), comma decimals, and a percent
# column with a no-break space before the sign. Before HM-778 EVERY numeric
# cell here parsed to 0.0 with no CsvInputError, and reconcile.build derived
# its control totals from the same zeroed rows, so reconcile.verify passed on
# a $0 account. This fixture exists to be able to express that failure: strip
# the NBSPs out of it and it stops testing anything.
_LOCALE_CSV = (
    "Search term,Campaign,Cost,Clicks,Conversions,CTR\n"
    'chaussures acme,Marque,"1 234,56","2 048","12,5","3,5 %"\n'
    'bottes pas cher,Generique,"987,00","1 024","0","2,1 %"\n'
    # The summary row the fr UI writes below the data: the label is localized
    # too, and fr spaces the colon. Its cells are real numbers now, so a
    # filter that only knows "total:" leaks the row in and DOUBLES every
    # control total below (build and verify would agree on the inflated sum).
    'Total : tous les termes,,"2 221,56","3 072","12,5","2,8 %"\n'
)

# The same leak in German, where the label never matched at all.
_LOCALE_CSV_DE = (
    "Search term,Campaign,Cost,Clicks,Conversions,CTR\n"
    'acme schuhe,Marke,"1.234,56","2 048","12,5","3,5 %"\n'
    'Gesamt: Konto,,"1.234,56","2 048","12,5","3,5 %"\n'
)


def test_locale_number_formats():
    """HM-778: fr/de number formatting parses to real values, not silent 0.0.

    Also hard-asserts, on top of `check()`: this file's checks only accumulate
    into `_failures` (honest under `main()`, green under a bare pytest
    collection), and a regression test for a silent-zeroing bug must be red
    under every runner.
    """
    print("test_locale_number_formats")
    _before = len(_failures)

    # -- the issue's named criterion, and the rest of the no-break-space family
    check("NBSP thousands + dot decimal (the HM-778 case)",
          C._num("1 234.56") == 1234.56, repr(C._num("1 234.56")))
    check("NBSP thousands + comma decimal (fr money)",
          C._num("1 234,56") == 1234.56, repr(C._num("1 234,56")))
    check("narrow NBSP thousands (U+202F, current fr-FR group separator)",
          C._num("1 234,56") == 1234.56, repr(C._num("1 234,56")))
    check("thin space thousands (U+2009)",
          C._num("1 234,56") == 1234.56, repr(C._num("1 234,56")))
    check("plain space thousands",
          C._num("1 234,56") == 1234.56, repr(C._num("1 234,56")))
    check("NBSP in a count column",
          C._num("2 048") == 2048.0, repr(C._num("2 048")))
    check("dot-grouped comma-decimal money (de)",
          C._num("1.234,56") == 1234.56, repr(C._num("1.234,56")))
    check("negative keeps its sign",
          C._num("-1 234,56") == -1234.56, repr(C._num("-1 234,56")))
    check("fr percent cell -> fraction",
          abs(C._pct("12,3 %") - 0.123) < 1e-12, repr(C._pct("12,3 %")))

    # -- en forms this module already handled: unchanged, or the fix regressed
    for raw, want in (("1,234.56", 1234.56), ("5,000", 5000.0),
                      ("1,234,567", 1234567.0), ("CA$1,023.31", 1023.31),
                      ("$5", 5.0), ("12.3%", 12.3), ("1.234", 1.234),
                      ("--", 0.0), ("", 0.0)):
        check(f"en form unchanged: {raw!r} -> {want}", C._num(raw) == want,
              repr(C._num(raw)))
    check("en percent -> fraction unchanged",
          abs(C._pct("12.3%") - 0.123) < 1e-12, repr(C._pct("12.3%")))
    # Documented, deliberate limitation (see _clean_separators / HM-785):
    # a dot-grouped de integer is read as an en decimal.
    check("dot-only stays the en decimal reading (documented limitation)",
          C._num("1.234") == 1.234, repr(C._num("1.234")))

    # -- separator/currency shapes the first pass got wrong (R17 gate findings)
    check("comma decimal with 3+ places is a decimal, not a group (fr CVR)",
          C._num("1,2345") == 1.2345, repr(C._num("1,2345")))
    check("comma decimal with 4 places after a group-sized head",
          C._num("1234,5678") == 1234.5678, repr(C._num("1234,5678")))
    check("a single ',' + exactly 3 digits stays the en group reading",
          C._num("1,234") == 1234.0, repr(C._num("1,234")))
    check("two or more dots is unambiguously grouping, not a parse failure",
          C._num("1.234.567") == 1234567.0, repr(C._num("1.234.567")))
    check("three dot groups too",
          C._num("12.345.678") == 12345678.0, repr(C._num("12.345.678")))
    check("euro prefix (the very locales this fix targets)",
          C._num("\u20ac1 234,56") == 1234.56, repr(C._num("\u20ac1 234,56")))
    check("euro suffix",
          C._num("1 234,56 \u20ac") == 1234.56, repr(C._num("1 234,56 \u20ac")))
    check("pound prefix",
          C._num("\u00a31,234.56") == 1234.56, repr(C._num("\u00a31,234.56")))

    # -- _pct's unsigned branch. `_num` no longer strips the comma, so '0,9'
    # is 0.9 and takes the already-a-fraction branch exactly as its en twin
    # '0.9' does (pre-HM-778 it parsed as 9.0 and came back 0.09). That is a
    # real output change on such cells, and the intended one: pin both.
    check("pct: unsigned comma-decimal below 1 is already a fraction",
          C._pct("0,9") == 0.9, repr(C._pct("0,9")))
    check("pct: its en twin reads identically",
          C._pct("0.9") == 0.9, repr(C._pct("0.9")))

    # -- parse_num is the public form skills reuse instead of cloning it
    check("parse_num(default=None): absent stays missing, not a false 0.0",
          C.parse_num("--", None) is None and C.parse_num("", None) is None,
          repr(C.parse_num("--", None)))
    check("parse_num(default=None): unparseable ('Shared') stays missing",
          C.parse_num("Shared", None) is None, repr(C.parse_num("Shared", None)))
    check("parse_num(default=None): locale cells parse exactly like _num",
          C.parse_num("1 234,56", None) == C._num("1 234,56") == 1234.56,
          repr(C.parse_num("1 234,56", None)))
    check("parse_num's default default is the 'num' column default (0.0)",
          C.parse_num("--") == 0.0, repr(C.parse_num("--")))

    # -- end to end: the export must assemble to real values AND real totals
    with tempfile.TemporaryDirectory() as td:
        rows, findings = C.assemble_from_csv(
            _write(td, "fr_export.csv", _LOCALE_CSV), COLUMN_MAP, REQUIRED,
            RECONCILE_SPEC, meta=dict(META))
        check("locale export: both rows kept", len(rows) == 2, repr(rows))
        check("locale export: NBSP money parsed",
              [r["cost"] for r in rows] == [1234.56, 987.0], repr(rows))
        check("locale export: NBSP counts parsed",
              [r["clicks"] for r in rows] == [2048.0, 1024.0], repr(rows))
        check("locale export: comma-decimal conversions parsed",
              [r["conversions"] for r in rows] == [12.5, 0.0], repr(rows))
        check("locale export: percent column -> fraction",
              abs(rows[0]["ctr"] - 0.035) < 1e-12, repr(rows[0]["ctr"]))
        check("locale export: no numeric cell silently zeroed",
              all(r[f] > 0 for r in rows for f in ("cost", "clicks")),
              repr(rows))
        rec = findings["meta"]["reconciliation"]["search_terms"]
        check("locale export: control totals are the real totals",
              abs(rec["sums"]["cost"] - 2221.56) < 1e-9
              and abs(rec["sums"]["clicks"] - 3072.0) < 1e-9, repr(rec))
        R.verify(findings, {"search_terms": RECONCILE_SPEC["sums"]})
        check("locale export: findings pass reconcile.verify", True)

        rows_de, findings_de = C.assemble_from_csv(
            _write(td, "de_export.csv", _LOCALE_CSV_DE), COLUMN_MAP, REQUIRED,
            RECONCILE_SPEC, meta=dict(META))
        check("de export: the 'Gesamt: ...' summary row is dropped",
              len(rows_de) == 1, repr(rows_de))
        check("de export: control totals are not doubled by a leaked total row",
              abs(findings_de["meta"]["reconciliation"]["search_terms"]
                  ["sums"]["cost"] - 1234.56) < 1e-9,
              repr(findings_de["meta"]["reconciliation"]))

    new = _failures[_before:]
    assert not new, ("HM-778 locale parsing regressed: " + ", ".join(new))


def test_comma_three_digit_decimals():
    """HM-794: a single comma + exactly 3 fractional digits is a decimal wherever
    it is DECIDABLE, not a blanket en thousands group.

    R17 (573dbee) already fixed the >3-fractional-digit case ('1,2345' -> 1.2345)
    by grouping only on `,\\d{3}$`. That guard was still too wide: it grouped
    '0,125' -> 125.0 and '1 234,125' -> 1234125.0, inflating fr/de decimal
    columns 1000x while reconcile.verify still passed on the inflated rows (the
    silent-agreement mode HM-778 fixed for the under-read direction). This pins
    the two decidable fixes, the boundaries around them, and the ONE irreducible
    ambiguous core that stays the en reading (HM-785). Hard-asserts, like the
    HM-778 test, so it is red under every runner.
    """
    print("test_comma_three_digit_decimals")
    _before = len(_failures)

    # -- DECIDABLE decimals the pre-HM-794 guard mis-grouped
    check("leading zero -> decimal (no locale groups a value < 1000)",
          C._num("0,125") == 0.125, repr(C._num("0,125")))
    check("leading zero, 4 fractional -> decimal",
          C._num("0,1234") == 0.1234, repr(C._num("0,1234")))
    check(">=4 leading digits -> decimal, not a 1000x group",
          C._num("1234,125") == 1234.125, repr(C._num("1234,125")))
    check("5 leading digits -> decimal",
          C._num("12345,678") == 12345.678, repr(C._num("12345,678")))
    # fr/de space-grouped decimal: parse_num strips the space (incl. the NBSP
    # family) BEFORE _clean_separators, leaving a >=4-digit head -> decidable.
    for label, sep in (("plain space", " "), ("NBSP U+00A0", " "),
                       ("narrow NBSP U+202F", " "),
                       ("thin space U+2009", " ")):
        cell = f"1{sep}234,125"
        check(f"space-grouped fr decimal ({label}) -> 1234.125",
              C._num(cell) == 1234.125, repr(C._num(cell)))

    # -- the ONE irreducible ambiguous core: stays the en group reading (HM-785)
    check("irreducible core '1,234' stays the en group reading (1234)",
          C._num("1,234") == 1234.0, repr(C._num("1,234")))
    check("3-leading-digit core '123,456' stays the en group reading",
          C._num("123,456") == 123456.0, repr(C._num("123,456")))
    check("2-leading-digit core '10,500' stays the en group reading",
          C._num("10,500") == 10500.0, repr(C._num("10,500")))

    # -- BOUNDARIES (move the constant and one of these flips):
    #    frac-length: '1,56' (2) decimal | '1,234' (3) group | '1,2345' (4) dec
    check("boundary frac<3: '1,56' -> 1.56 (decimal)",
          C._num("1,56") == 1.56, repr(C._num("1,56")))
    check("boundary frac>3: '1,2345' -> 1.2345 (decimal, R17)",
          C._num("1,2345") == 1.2345, repr(C._num("1,2345")))
    #    head-length: '999,456' (3) group | '1000,456' (4) decimal
    check("boundary head=3: '999,456' -> 999456.0 (en group core)",
          C._num("999,456") == 999456.0, repr(C._num("999,456")))
    check("boundary head=4: '1000,456' -> 1000.456 (decimal)",
          C._num("1000,456") == 1000.456, repr(C._num("1000,456")))
    #    leading-zero: '0,456' decimal | '1,456' group
    check("boundary leading-zero: '0,456' -> 0.456 (decimal)",
          C._num("0,456") == 0.456, repr(C._num("0,456")))

    # -- multi-comma stays unambiguous grouping (guarded by the count==1 gate)
    check("two commas still group ('1,234,567')",
          C._num("1,234,567") == 1234567.0, repr(C._num("1,234,567")))

    # -- end to end: an fr export whose money column is space-grouped WITH 3
    # decimals ('1 234,125') and whose conv-rate is a leading-zero fraction
    # ('0,125') must assemble to the REAL values, and reconcile.verify must pass
    # on the real (un-inflated) totals. Pre-HM-794 cost read 1234125.0.
    cmap = {"term": {"aliases": ["Search term"], "type": "str"},
            "campaign": {"aliases": ["Campaign"], "type": "str"},
            "cost": {"aliases": ["Cost"], "type": "num"},
            "conversions": {"aliases": ["Conversions"], "type": "num"}}
    req = ("term", "campaign", "cost", "conversions")
    spec = {"array": "rows", "sums": ["cost", "conversions"]}
    fr = ("Search term,Campaign,Cost,Conversions\n"
          'chaussures,Marque,"1 234,125","0,125"\n'
          'bottes,Generique,"12 345,678","1,5"\n')
    with tempfile.TemporaryDirectory() as td:
        rows, findings = C.assemble_from_csv(_write(td, "fr.csv", fr), cmap,
                                             req, spec, meta=dict(META))
        check("fr 3-decimal money not inflated 1000x",
              [r["cost"] for r in rows] == [1234.125, 12345.678], repr(rows))
        check("fr leading-zero conv rate is a fraction",
              rows[0]["conversions"] == 0.125, repr(rows[0]["conversions"]))
        rec = findings["meta"]["reconciliation"]["rows"]["sums"]
        check("reconcile totals are the real (un-inflated) totals",
              abs(rec["cost"] - 13579.803) < 1e-9, repr(rec))
        R.verify(findings, {"rows": spec["sums"]})
        check("fr export findings pass reconcile.verify", True)

    new = _failures[_before:]
    assert not new, ("HM-794 comma-decimal parsing regressed: " + ", ".join(new))


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


# ── the pytest binding (added by HM-791; the checks above are untouched) ────
# check() only APPENDS to _failures, so under pytest every test_* function
# above passes whatever it observed. Defined LAST so pytest (definition order)
# runs it after them, and it is what actually makes a failed check red here.
# See also ../conftest.py for the order/selection-independent guard.
def test_no_check_failures():
    assert not _failures, (
        f"{len(_failures)} failed check(s): " + ", ".join(_failures)
    )


def main():
    for t in (test_csv_matches_mcp_shape, test_aliased_headers,
              test_missing_columns, test_ambiguous_columns,
              test_empty_and_missing_file, test_extra_columns_and_total_rows,
              test_typed_conversion, test_locale_number_formats,
              test_comma_three_digit_decimals, test_contract_validation):
        t()
    print()
    if _failures:
        print(f"FAILED ({len(_failures)}): {', '.join(_failures)}")
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
