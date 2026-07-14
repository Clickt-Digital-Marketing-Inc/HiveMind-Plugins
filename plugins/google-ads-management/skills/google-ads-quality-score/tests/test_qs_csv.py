#!/usr/bin/env python3
"""Tests for the Quality Score CSV manual-input path (stdlib only; run directly).

    python3 tests/test_qs_csv.py

Covers assemble_findings_csv.py's COLUMN_MAP (aliases, typed conversion, the
match-type/ad_group_id normalizations the CSV path needs that the MCP path
doesn't) and — the core acceptance for HM-541's dual-input requirement — that
a UI CSV export and an equivalent MCP raw pull compute an IDENTICAL model
(rows' observable fields + summary + dominant_factor) through qs_core.

Exit 0 = all pass, 1 = a failure.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE.parents[2] / "_shared"))

import assemble_findings as MCP        # noqa: E402
import assemble_findings_csv as CSV    # noqa: E402
import qs_core as core                 # noqa: E402
from csv_input import CsvInputError    # noqa: E402

_failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        _failures.append(name)


def _write(td, name, text):
    p = Path(td) / name
    p.write_text(text)
    return str(p)


# Three keywords across two ad groups: one clean scored keyword, one unscored
# keyword ("--" cells in the UI), one out-of-scope (QS >= threshold) keyword —
# exercises dedupe-key equivalence, unscored handling, and out-of-scope rows
# on both paths.
_MCP_RAW = {"result": [
    {"campaign.name": "C1", "ad_group.id": 101, "ad_group.name": "AG1",
     "ad_group_criterion.keyword.text": "buy shoes",
     "ad_group_criterion.keyword.match_type": "PHRASE",
     "ad_group_criterion.quality_info.quality_score": 3,
     "ad_group_criterion.quality_info.post_click_quality_score": "BELOW_AVERAGE",
     "ad_group_criterion.quality_info.creative_quality_score": "AVERAGE",
     "ad_group_criterion.quality_info.search_predicted_ctr": "AVERAGE",
     "metrics.impressions": 1000, "metrics.clicks": 20,
     "metrics.cost_micros": 200_000_000, "metrics.conversions": 1},
    {"campaign.name": "C1", "ad_group.id": 101, "ad_group.name": "AG1",
     "ad_group_criterion.keyword.text": "cheap boots",
     "ad_group_criterion.keyword.match_type": "BROAD",
     "metrics.impressions": 50, "metrics.clicks": 0,
     "metrics.cost_micros": 10_000_000, "metrics.conversions": 0},
    {"campaign.name": "C1", "ad_group.id": 202, "ad_group.name": "AG2",
     "ad_group_criterion.keyword.text": "premium sneakers",
     "ad_group_criterion.keyword.match_type": "EXACT",
     "ad_group_criterion.quality_info.quality_score": 6,
     "ad_group_criterion.quality_info.post_click_quality_score": "AVERAGE",
     "ad_group_criterion.quality_info.creative_quality_score": "AVERAGE",
     "ad_group_criterion.quality_info.search_predicted_ctr": "AVERAGE",
     "metrics.impressions": 500, "metrics.clicks": 100,
     "metrics.cost_micros": 300_000_000, "metrics.conversions": 10},
]}

# The same three keywords as a Google Ads UI "Keywords" export (title row,
# human match-type labels, "--" for the unscored row's diagnostic cells,
# thousands separator, a Total row) — realistic UI-export quirks on purpose.
_UI_CSV = """Keywords report
"April 7, 2026 - July 5, 2026"
Keyword,Match type,Ad group,Campaign,Quality Score,Landing page exp.,Ad relevance,Expected CTR,Impr.,Clicks,Cost,Conversions
buy shoes,Phrase match,AG1,C1,3,Below average,Average,Average,"1,000",20,200.00,1
cheap boots,Broad match,AG1,C1,--,--,--,--,50,0,10.00,0
premium sneakers,Exact match,AG2,C1,6,Average,Average,Average,500,100,300.00,10
Total: keywords,,,,,,,,,,,510.00,11
"""

_META = {"client_name": "Acme Corp", "account_id": "123-456-7890", "currency": "CAD",
        "period": "last 30 days", "generated": "2026-07-12"}


def _rows_stripped(model):
    """Observable row fields, minus ad_group_id — the CSV path's synthetic
    id (the ad-group NAME) is structurally different from the MCP path's
    internal numeric id by design (the UI export exposes no id). Grouping
    behaviour is asserted separately (same dominant_factor location rows,
    same row count per ad group)."""
    keep = ("keyword", "ad_group", "campaign", "match_type", "qs", "lp", "ar", "ctr_q",
            "status", "impressions", "clicks", "cost", "conversions", "ctr", "bucket", "pause")
    return [{k: r[k] for k in keep} for r in model["rows"]]


def test_column_map_aliases_and_types():
    print("test_column_map_aliases_and_types")
    with tempfile.TemporaryDirectory() as td:
        csv_path = _write(td, "export.csv", _UI_CSV)
        findings = CSV.assemble_csv(csv_path, dict(_META))
        kws = findings["keywords"]
        check("3 rows parsed (title rows + Total row handled)", len(kws) == 3, f"{len(kws)}")
        check("thousands-comma impressions parsed", kws[0]["impressions"] == 1000.0,
              f"{kws[0]['impressions']}")
        check("match type normalized 'Phrase match' -> 'PHRASE'",
              kws[0]["match_type"] == "PHRASE", kws[0]["match_type"])
        check("match type normalized 'Broad match' -> 'BROAD'",
              kws[1]["match_type"] == "BROAD", kws[1]["match_type"])
        check("match type normalized 'Exact match' -> 'EXACT'",
              kws[2]["match_type"] == "EXACT", kws[2]["match_type"])
        check("'--' quality score parsed to 0.0 (unscored)", kws[1]["quality_score"] == 0.0,
              kws[1]["quality_score"])
        check("'--' landing_page_exp parsed to '' (absent)", kws[1]["landing_page_exp"] == "",
              repr(kws[1]["landing_page_exp"]))
        check("ad_group_id synthesized from ad group name",
              kws[0]["ad_group_id"] == "AG1" and kws[2]["ad_group_id"] == "AG2",
              [k["ad_group_id"] for k in kws])
        check("meta.source == user_csv", findings["meta"]["source"] == "user_csv")
        check("reconciliation embedded", bool(findings["meta"].get("reconciliation")))


def test_missing_required_column_raises():
    print("test_missing_required_column_raises")
    broken = _UI_CSV.replace("Conversions", "Something else")
    with tempfile.TemporaryDirectory() as td:
        try:
            CSV.assemble_csv(_write(td, "a.csv", broken), dict(_META))
            ok = False
        except CsvInputError as e:
            ok = "conversions" in str(e)
        check("missing required column raises CsvInputError naming the field", ok)


def test_csv_matches_mcp_model():
    print("test_csv_matches_mcp_model")
    with tempfile.TemporaryDirectory() as td:
        raw_path = _write(td, "kw_raw.txt", json.dumps(_MCP_RAW))
        mcp_findings = MCP.assemble(raw_path, dict(_META, source="mcp"))
        csv_path = _write(td, "export.csv", _UI_CSV)
        csv_findings = CSV.assemble_csv(csv_path, dict(_META))

        check("both findings have 3 keyword rows",
              len(mcp_findings["keywords"]) == 3 == len(csv_findings["keywords"]))
        check("mcp source label is 'mcp'", mcp_findings["meta"]["source"] == "mcp")
        check("csv source label is 'user_csv'", csv_findings["meta"]["source"] == "user_csv")

        # compute_model takes a findings dict directly (no file round-trip needed
        # here); load_findings is only for the file+reconciliation-verify path,
        # exercised separately below.
        mcp_model = core.compute_model(mcp_findings)
        csv_model = core.compute_model(csv_findings)

        check("identical observable rows (ad_group_id excluded — see docstring)",
              _rows_stripped(mcp_model) == _rows_stripped(csv_model),
              f"mcp={_rows_stripped(mcp_model)!r}\ncsv={_rows_stripped(csv_model)!r}")

        ms, cs = mcp_model["summary"], csv_model["summary"]
        for key in ("keywords", "scored", "unscored", "in_scope", "avg_qs", "lp", "ad_rel",
                    "exp_ctr", "critical", "other", "pause_candidates", "wasted_low_qs_cost",
                    "dominant_component", "dominant_share_pct", "dominant_location_share_pct"):
            check(f"summary.{key} identical", ms[key] == cs[key], f"mcp={ms[key]!r} csv={cs[key]!r}")

        md, cd = mcp_model["dominant_factor"], csv_model["dominant_factor"]
        check("dominant_factor.dominant_component identical",
              md["dominant_component"] == cd["dominant_component"])
        check("dominant_factor.concentration identical", md["concentration"] == cd["concentration"])
        check("dominant_factor.location identical", md["location"] == cd["location"])
        # location_rows carry the ad-group NAME on both paths (MCP's is the
        # human label, CSV's is also the name doubling as its id) — these
        # should match exactly since the fixture's ad group names are unique.
        check("dominant_factor.location_rows identical", md["location_rows"] == cd["location_rows"],
              f"mcp={md['location_rows']!r}\ncsv={cd['location_rows']!r}")

        # both findings pass the core's own reconciliation verification when
        # loaded from disk exactly like a real build would.
        mcp_path = _write(td, "mcp_findings.json", json.dumps(mcp_findings))
        csv_findings_path = _write(td, "csv_findings.json", json.dumps(csv_findings))
        core.compute_model(core.load_findings(mcp_path))
        core.compute_model(core.load_findings(csv_findings_path))
        check("both findings pass core.load_findings reconciliation verification", True)


def main():
    for t in (test_column_map_aliases_and_types, test_missing_required_column_raises,
              test_csv_matches_mcp_model):
        t()
    print()
    if _failures:
        print(f"FAILED ({len(_failures)}): {', '.join(_failures)}")
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
