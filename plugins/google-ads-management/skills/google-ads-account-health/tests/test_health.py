#!/usr/bin/env python3
"""Tests for the account-health core + builder (stdlib only; run directly).

    python3 tests/test_health.py

Asserts the documented fixture scoring, no-row-loss, nullable-column
handling (per-check fields null on rows the check doesn't apply to),
MCP-vs-CSV model parity, bundle emit (md + xlsx, no HTML), and the xlsx
recalc matching the Python model. Exit 0 = all pass, 1 = a failure.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
SHARED = HERE.parents[2] / "_shared"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SHARED))

import health_core as core          # noqa: E402
import health_artifacts as artifacts  # noqa: E402
import assemble_from_csv as csv_assembler  # noqa: E402

sys.path.insert(0, str(SHARED))
import csv_input as csv_input_mod   # noqa: E402

FIXTURE_MCP = HERE / "sample-findings.json"
FIXTURE_CSV = HERE / "sample-findings-csv.json"
_failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        _failures.append(name)


def test_fixture_scoring():
    print("test_fixture_scoring")
    model = core.compute_model(core.load_findings(str(FIXTURE_MCP)))
    s = model["summary"]
    check("universe == 12", s["universe"] == 12, f"got {s['universe']}")
    check("total_flagged == 5", s["total_flagged"] == 5, f"got {s['total_flagged']}")
    check("by_severity Critical=1/High=3/Medium=1",
          s["by_severity"] == {"Critical": 1, "High": 3, "Medium": 1}, f"got {s['by_severity']}")
    check("structural_score == 31.5", abs(s["structural_score"] - 31.5) < 1e-6, f"got {s['structural_score']}")
    by_check = s["by_check"]
    check("sprawl 1/3", by_check["sprawl"] == {"universe": 3, "flagged": 1})
    check("no_negatives 1/2 (Search-only)", by_check["no_negatives"] == {"universe": 2, "flagged": 1})
    check("automation_no_data 1/3", by_check["automation_no_data"] == {"universe": 3, "flagged": 1})
    check("naming 1/3", by_check["naming"] == {"universe": 3, "flagged": 1})
    check("pmax_cannibalization 1/1", by_check["pmax_cannibalization"] == {"universe": 1, "flagged": 1})


def test_top_fixes_ranking():
    print("test_top_fixes_ranking")
    model = core.compute_model(core.load_findings(str(FIXTURE_MCP)))
    tf = model["top_fixes"]
    check("5 flagged rows in top_fixes", len(tf) == 5, f"got {len(tf)}")
    got_order = [(r["check"], r["pre_score"]) for r in tf]
    want_order = [("automation_no_data", 9.0), ("no_negatives", 7.0),
                  ("pmax_cannibalization", 6.5), ("sprawl", 6.0), ("naming", 3.0)]
    check("ranked by pre_score desc", got_order == want_order, f"got {got_order}")


def test_no_row_loss():
    print("test_no_row_loss")
    findings = core.load_findings(str(FIXTURE_MCP))
    model = core.compute_model(findings)
    # 3 ad_group rows (sprawl) + 3 campaigns * 3 checks (no_negatives/automation/naming,
    # but no_negatives only for Search) + 1 pmax row for the PMax campaign
    n_ag = len(findings["ad_groups"])
    n_camp = len(findings["campaigns"])
    n_search = sum(1 for c in findings["campaigns"] if c["channel_type"] == "SEARCH")
    n_pmax = sum(1 for c in findings["campaigns"] if c["channel_type"] == "PERFORMANCE_MAX")
    expected = n_ag + (n_camp * 2) + n_search + n_pmax   # automation+naming for every campaign
    check("row count matches every (check, entity) pair", len(model["rows"]) == expected,
          f"got {len(model['rows'])}, expected {expected}")
    for i, r in enumerate(model["rows"]):
        check(f"row {i} has a status", "status" in r and r["status"] in ("scored", "config", "manual"))
        check(f"row {i} has pre_score", "pre_score" in r and isinstance(r["pre_score"], float))
        check(f"row {i} has is_flagged", "is_flagged" in r and isinstance(r["is_flagged"], bool))


def test_nullable_columns():
    print("test_nullable_columns")
    model = core.compute_model(core.load_findings(str(FIXTURE_MCP)))
    sprawl_rows = [r for r in model["rows"] if r["check"] == "sprawl"]
    other_fields = ("negative_count", "bidding_strategy_type", "conversions_30d",
                    "name_pattern_ok", "pmax_present", "brand_present", "has_brand_exclusion")
    for r in sprawl_rows:
        check("sprawl row has keyword_count", r["keyword_count"] is not None)
        check("sprawl row has ad_group_ctr", r["ad_group_ctr"] is not None)
        for f in other_fields:
            check(f"sprawl row's '{f}' is null (doesn't apply)", r[f] is None)

    pmax_rows = [r for r in model["rows"] if r["check"] == "pmax_cannibalization"]
    for r in pmax_rows:
        check("pmax row has pmax_present", r["pmax_present"] is not None)
        check("pmax row's has_brand_exclusion is ALWAYS None (never API-confirmable)",
              r["has_brand_exclusion"] is None)
        check("pmax row status == 'manual'", r["status"] == "manual")

    naming_rows = [r for r in model["rows"] if r["check"] == "naming"]
    for r in naming_rows:
        check("naming row status == 'config'", r["status"] == "config")

    scored_checks = ("sprawl", "no_negatives", "automation_no_data")
    for r in model["rows"]:
        if r["check"] in scored_checks:
            check(f"{r['check']} row status == 'scored'", r["status"] == "scored")


def test_sprawl_requires_both_conditions():
    print("test_sprawl_requires_both_conditions")
    model = core.compute_model(core.load_findings(str(FIXTURE_MCP)))
    core_row = next(r for r in model["rows"] if r["check"] == "sprawl" and r["entity_name"] == "Core")
    check("Core ad group (25 kw, 10% CTR) is NOT flagged — healthy CTR", not core_row["is_flagged"])
    check("Core ad group has the sprawl_size sub-signal (partial, not enough alone)",
          "sprawl_size" in core_row["flags"] and "sprawl_low_ctr" not in core_row["flags"])
    check("Core ad group pre_score is 0 when not flagged", core_row["pre_score"] == 0.0)


def test_mcp_csv_parity():
    print("test_mcp_csv_parity")
    m1 = core.compute_model(core.load_findings(str(FIXTURE_MCP)))
    m2 = core.compute_model(core.load_findings(str(FIXTURE_CSV)))
    check("MCP and CSV summaries are identical", m1["summary"] == m2["summary"],
          f"mcp={m1['summary']} csv={m2['summary']}")
    check("MCP meta.source == 'mcp'", m1["provenance"]["source"] == "mcp")
    check("CSV meta.source == 'user_csv'", m2["provenance"]["source"] == "user_csv")
    mcp_scores = sorted(r["pre_score"] for r in m1["rows"])
    csv_scores = sorted(r["pre_score"] for r in m2["rows"])
    check("MCP and CSV produce the same pre_score multiset", mcp_scores == csv_scores)


def test_empty_universe():
    print("test_empty_universe")
    f = {"meta": {}, "ad_groups": [], "campaigns": []}
    model = core.compute_model(f)
    s = model["summary"]
    check("empty -> universe 0", s["universe"] == 0)
    check("empty -> total_flagged 0", s["total_flagged"] == 0)
    check("empty -> top_fixes empty", model["top_fixes"] == [])


def test_reconciliation_hard_fails_on_tamper():
    print("test_reconciliation_hard_fails_on_tamper")
    data = json.loads(FIXTURE_MCP.read_text())
    data["campaigns"][0]["negative_count"] = 999   # tamper after the fact
    tmp = Path(tempfile.mkstemp(suffix=".json")[1])
    tmp.write_text(json.dumps(data))
    try:
        raised = False
        try:
            core.load_findings(str(tmp))
        except core.FindingsError:
            raised = True
        check("tampered findings raise FindingsError on load", raised)
    finally:
        tmp.unlink()


def test_bundle_emit_and_xlsx_recalc():
    print("test_bundle_emit_and_xlsx_recalc")
    import subprocess
    tmp = Path(tempfile.mkdtemp())
    try:
        r = subprocess.run([sys.executable, str(SCRIPTS / "build_health_report.py"),
                            "--input", str(FIXTURE_MCP), "--outdir", str(tmp),
                            "--brand", "Acme Corp", "--formats", "md,xlsx"],
                           capture_output=True, text=True)
        check("builder exits 0", r.returncode == 0, r.stderr)
        md_files = list(tmp.glob("*.md"))
        xlsx_files = list(tmp.glob("*.xlsx"))
        html_files = list(tmp.glob("*.html"))
        check("md report emitted", any("account-health" in p.name and "_action_plan" not in p.name
                                       and "_renaming" not in p.name for p in md_files))
        check("xlsx emitted", len(xlsx_files) == 1, f"got {[p.name for p in xlsx_files]}")
        check("NO html explorer emitted (reduced bundle)", len(html_files) == 0, f"got {html_files}")
        check("action_plan.md emitted", any(p.name.endswith("_action_plan.md") for p in md_files))
        check("renaming.md emitted", any(p.name.endswith("_renaming.md") for p in md_files))
        check("pause_list.csv emitted", any(p.name.endswith("_pause_list.csv") for p in tmp.glob("*.csv")))

        if xlsx_files:
            import health_xlsx_spec as xspec
            from render.xlsx import check_workbook
            rc = check_workbook(str(xlsx_files[0]), {"xlsx": xspec.XLSX})
            check("xlsx passes structural check_workbook", rc == 0)

            from openpyxl import load_workbook
            wb = load_workbook(str(xlsx_files[0]), data_only=True)
            c = wb["Controls"]
            model = core.compute_model(core.load_findings(str(FIXTURE_MCP)))
            s = model["summary"]
            check("xlsx C39 (total flagged) matches model", c["C39"].value == s["total_flagged"],
                  f"xlsx={c['C39'].value} model={s['total_flagged']}")
            check("xlsx C40 (universe) matches model", c["C40"].value == s["universe"],
                  f"xlsx={c['C40'].value} model={s['universe']}")
            check("xlsx C34 (sprawl flagged) matches model",
                  c["C34"].value == s["by_check"]["sprawl"]["flagged"])
            check("xlsx C38 (pmax flagged) matches model",
                  c["C38"].value == s["by_check"]["pmax_cannibalization"]["flagged"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_reject_html_format():
    print("test_reject_html_format")
    import subprocess
    tmp = Path(tempfile.mkdtemp())
    try:
        r = subprocess.run([sys.executable, str(SCRIPTS / "build_health_report.py"),
                            "--input", str(FIXTURE_MCP), "--outdir", str(tmp),
                            "--formats", "html"], capture_output=True, text=True)
        check("builder rejects --formats html (reduced bundle has no HTML spec)", r.returncode == 1)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_action_plan_artifacts():
    print("test_action_plan_artifacts")
    model = core.compute_model(core.load_findings(str(FIXTURE_MCP)))
    plan = artifacts.action_plan_md(model)
    check("action plan mentions Critical section", "## Critical" in plan)
    check("action plan mentions the automation fix", "Automation without data" in plan)
    rows = artifacts.pause_list_rows(model)
    check("pause_list has exactly the 1 flagged sprawl ad group", len(rows) == 1, f"got {len(rows)}")
    check("pause_list row names the right ad group", rows[0]["Ad Group"] == "Generic - CRM")
    renaming = artifacts.renaming_md(model)
    check("renaming worklist names the PMax campaign", "Shopping PMax Everything" in renaming)
    check("renaming worklist does NOT invent a compliant name",
          "confirm" in renaming.lower())


def test_csv_missing_column_raises():
    print("test_csv_missing_column_raises")
    tmp = Path(tempfile.mkdtemp())
    try:
        bad_csv = tmp / "adgroups_missing_keywords.csv"
        bad_csv.write_text("Campaign,Ad group,Clicks,Impr.\n"
                           "NonBrand_US_Search_CRM_2026,Generic - CRM,40,4000\n")  # no keyword-count column
        raised = False
        try:
            csv_assembler.assemble(str(bad_csv), str(HERE / "campaigns-export.csv"),
                                   {"client_name": "X", "account_id": "1", "currency": "USD",
                                    "window_30d": "a to b"})
        except csv_input_mod.CsvInputError as e:
            raised = True
            check("error names the missing column", "keyword" in str(e).lower(), str(e))
        check("missing 'Ad group keywords (enabled)' column raises CsvInputError", raised)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_invalid_naming_regex_raises():
    print("test_invalid_naming_regex_raises")
    findings = json.loads(FIXTURE_MCP.read_text())
    findings["params"] = {"naming_regex": "("}   # unbalanced paren — invalid regex
    raised = False
    try:
        core.compute_model(findings)
    except core.FindingsError as e:
        raised = True
        check("error names the bad regex", "naming_regex" in str(e), str(e))
    check("invalid naming_regex raises a clear FindingsError (not a bare re.error)", raised)


def main() -> int:
    test_fixture_scoring()
    test_top_fixes_ranking()
    test_no_row_loss()
    test_nullable_columns()
    test_sprawl_requires_both_conditions()
    test_mcp_csv_parity()
    test_empty_universe()
    test_reconciliation_hard_fails_on_tamper()
    test_csv_missing_column_raises()
    test_invalid_naming_regex_raises()
    test_action_plan_artifacts()
    test_bundle_emit_and_xlsx_recalc()
    test_reject_html_format()
    print()
    if _failures:
        print(f"{len(_failures)} FAILURE(S): " + ", ".join(_failures))
        return 1
    print("All tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
