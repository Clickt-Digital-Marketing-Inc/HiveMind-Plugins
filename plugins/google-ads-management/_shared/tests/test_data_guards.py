#!/usr/bin/env python3
"""Tests for the data-transcription guards (stdlib only; run directly).

    python3 _shared/tests/test_data_guards.py

Covers gaql_raw (verbatim raw-results parsing: observed format, bare array,
concatenated documents, wrong-file detection, hand-edit detection) and
reconcile (control totals: build, verify, tolerance, tamper, absent block).
Exit 0 = all pass, 1 = a failure.
"""
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHARED = HERE.parent
sys.path.insert(0, str(SHARED))

import gaql_raw as G   # noqa: E402
import reconcile as R  # noqa: E402

_failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        _failures.append(name)


def _write(td, name, text):
    p = Path(td) / name
    p.write_text(text)
    return str(p)


_ROWS = [{"campaign.id": 1, "metrics.cost_micros": 1_500_000, "metrics.clicks": 3},
         {"campaign.id": 2, "metrics.cost_micros": 250_000, "metrics.clicks": 1}]


def test_gaql_raw_formats():
    print("test_gaql_raw_formats")
    with tempfile.TemporaryDirectory() as td:
        # the observed MCP format: {"result": [...]} (verified live 2026-07-06)
        p = _write(td, "a.txt", json.dumps({"result": _ROWS}))
        check("observed format parsed", G.load_rows(p) == _ROWS)
        # bare array
        p = _write(td, "b.txt", json.dumps(_ROWS))
        check("bare array parsed", G.load_rows(p) == _ROWS)
        # several concatenated documents (manually paginated pull)
        p = _write(td, "c.txt", json.dumps({"result": _ROWS[:1]}) + "\n" + json.dumps({"result": _ROWS[1:]}))
        check("concatenated documents parsed", G.load_rows(p) == _ROWS)
        # wrong file for the pull
        p = _write(td, "d.txt", json.dumps({"result": _ROWS}))
        try:
            G.load_rows(p, require_fields=("metrics.conversions",)); ok = False
        except G.RawResultError:
            ok = True
        check("wrong-query file rejected via require_fields", ok)
        # hand-edited / truncated file
        p = _write(td, "e.txt", '{"result": [{"campaign.id": 1')
        try:
            G.load_rows(p); ok = False
        except G.RawResultError:
            ok = True
        check("malformed file rejected", ok)
        check("micros converts", G.micros(1_500_000) == 1.5)


def _findings():
    return {"meta": {}, "search_terms": [{"cost": 1.5, "clicks": 3}, {"cost": 0.25, "clicks": 1}],
            "benchmarks": [{"cost": 10.0, "conversions": 2.0}]}


_ARRAYS = {"search_terms": ["cost", "clicks"], "benchmarks": ["cost", "conversions"]}


def test_reconcile_roundtrip():
    print("test_reconcile_roundtrip")
    f = _findings()
    f["meta"]["reconciliation"] = R.build(f, _ARRAYS)
    R.verify(f, _ARRAYS)  # must not raise
    check("build -> verify roundtrip clean", True)
    check("rows counted", f["meta"]["reconciliation"]["search_terms"]["rows"] == 2)
    check("sums computed", f["meta"]["reconciliation"]["search_terms"]["sums"]["cost"] == 1.75)


def test_reconcile_catches_tampering():
    print("test_reconcile_catches_tampering")
    for mutate, why in (
        (lambda f: f["search_terms"][0].__setitem__("cost", 501.5), "edited value"),
        (lambda f: f["search_terms"].pop(), "dropped row"),
        (lambda f: f["search_terms"].append({"cost": 9.0, "clicks": 1}), "invented row"),
        (lambda f: f["benchmarks"][0].__setitem__("conversions", 3.0), "edited benchmark"),
    ):
        f = _findings()
        f["meta"]["reconciliation"] = R.build(f, _ARRAYS)
        mutate(f)
        try:
            R.verify(f, _ARRAYS); ok = False
        except R.ReconciliationError:
            ok = True
        check(f"{why} detected", ok)


def test_reconcile_tolerance_and_absence():
    print("test_reconcile_tolerance_and_absence")
    f = _findings()
    f["meta"]["reconciliation"] = R.build(f, _ARRAYS)
    # float64 sum-order drift far below a cent must not false-positive
    f["search_terms"][0]["cost"] += 1e-10
    R.verify(f, _ARRAYS)
    check("sub-cent float drift tolerated", True)
    # absent block is a no-op here (builders warn; verification can't run)
    R.verify(_findings(), _ARRAYS)
    check("absent reconciliation is not an error at verify()", True)


def main():
    for t in (test_gaql_raw_formats, test_reconcile_roundtrip,
              test_reconcile_catches_tampering, test_reconcile_tolerance_and_absence):
        t()
    print()
    if _failures:
        print(f"FAILED ({len(_failures)}): {', '.join(_failures)}")
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
