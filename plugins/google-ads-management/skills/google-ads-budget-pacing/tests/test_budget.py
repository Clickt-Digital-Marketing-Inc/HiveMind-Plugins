#!/usr/bin/env python3
"""Tests for the budget & pacing core + bundle (stdlib only; run directly).

    python3 tests/test_budget.py

Asserts the fixture buckets/pacing, no-row-loss, the no-budget path, an empty
edge, and md/html bundle parity + lazy-openpyxl. Exit 0 = pass, 1 = fail.
"""
import json
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE.parents[2] / "_shared"))

import budget_core as core  # noqa: E402

FIXTURE = HERE / "sample-findings.json"
_failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        _failures.append(name)


def test_fixture_buckets_and_pacing():
    print("test_fixture_buckets_and_pacing")
    m = core.compute_model(core.load_findings(str(FIXTURE)))
    s = m["summary"]
    check("campaigns == 6 (no row loss)", s["campaigns"] == 6, f"got {s['campaigns']}")
    check("kill == 1", s["kill"] == 1, f"got {s['kill']}")
    check("raise == 1", s["raise_"] == 1, f"got {s['raise_']}")
    check("rank_limited == 1", s["rank_limited"] == 1, f"got {s['rank_limited']}")
    check("low_budget == 1", s["low_budget"] == 1, f"got {s['low_budget']}")
    check("ok == 1", s["ok"] == 1, f"got {s['ok']}")
    check("no_budget == 1", s["no_budget"] == 1, f"got {s['no_budget']}")
    check("mtd_spend == 5120", abs(s["mtd_spend"] - 5120.0) < 1e-6, f"got {s['mtd_spend']}")
    check("expected_mtd == 15000", abs(s["expected_mtd"] - 15000.0) < 1e-6, f"got {s['expected_mtd']}")
    check("pace_ratio == 0.34", abs(s["pace_ratio"] - 0.34) < 1e-6, f"got {s['pace_ratio']}")
    check("pace_verdict == under", s["pace_verdict"] == "under", s["pace_verdict"])


def test_concentration_and_pace_prescore():
    print("test_concentration_and_pace_prescore")
    m = core.compute_model(core.load_findings(str(FIXTURE)))
    s = m["summary"]
    # concentration: top-3 by window cost over [4000,2000,1500,800,600,500] (desc), total 9400
    check("conc_top_share == 0.7979", abs(s["conc_top_share"] - 0.7979) < 1e-9, s["conc_top_share"])
    check("conc_hhi == 2659.6", abs(s["conc_hhi"] - 2659.6) < 1e-6, s["conc_hhi"])
    check("conc_effective_n == 3.76", abs(s["conc_effective_n"] - 3.76) < 1e-6, s["conc_effective_n"])
    check("conc_top3_pct == 79.8", abs(s["conc_top3_pct"] - 79.8) < 1e-9, s["conc_top3_pct"])
    # per-campaign pace: days_elapsed=15 -> confidence "high" whenever mtd_spend >= target_cpa (50);
    # every fixture campaign clears that floor.
    check("all rows have pace_confidence == high",
          all(r["pace_confidence"] == "high" for r in m["rows"]))
    check("over_pace == 0, under_pace == 5", s["over_pace"] == 0 and s["under_pace"] == 5,
          f"over={s['over_pace']} under={s['under_pace']}")
    check("off_pace_high_conf == 5", s["off_pace_high_conf"] == 5, s["off_pace_high_conf"])
    brand = next(r for r in m["rows"] if r["campaign"] == "S | Brand")
    # 2200 / (300 * 15) = 0.4889 -> _r2 -> 0.49
    check("S | Brand campaign_pace_ratio == 0.49", abs(brand["campaign_pace_ratio"] - 0.49) < 1e-9,
          brand["campaign_pace_ratio"])
    check("S | Brand pace_verdict == under", brand["pace_verdict"] == "under", brand["pace_verdict"])
    # flags: under_pace (ratio<0.85) + constrained (blis 0.25>0.10) -> weights 1.0+1.5=2.5
    check("S | Brand pace_flags == {under_pace, constrained}",
          set(brand["pace_flags"]) == {"under_pace", "constrained"}, brand["pace_flags"])
    check("S | Brand pace_score == 2.5", abs(brand["pace_score"] - 2.5) < 1e-9, brand["pace_score"])
    nb = next(r for r in m["rows"] if r["status"] == "no_budget")
    check("no_budget row: campaign_pace_ratio is None", nb["campaign_pace_ratio"] is None)
    check("no_budget row: pace_verdict == n/a", nb["pace_verdict"] == "n/a", nb["pace_verdict"])


def test_pace_kernel_js_parity_over_pacing():
    """The shared parity harness (skills/google-ads/tests/run_parity.py) drives
    budget-pacing with exactly one tune (min_budget_multiple=50 on this fixture),
    which never pushes a row's campaign_pace_ratio over 1+pacing_tolerance — so the
    JS<->Python pace() kernel's "over" branch is unproven by that gate on this
    fixture. Cross-check it directly here: a synthetic over-pacing row, evaluated
    through budget_spec.JS_KERNEL's pace(r,P) under Node, must match
    budget_core.add_pace's Python computation exactly. Skips (not fails) when
    `node` isn't on PATH — this repo's other Node-dependent checks are dev-only."""
    print("test_pace_kernel_js_parity_over_pacing")
    import shutil
    import subprocess
    if shutil.which("node") is None:
        check("node on PATH (skipped -- unavailable in this environment)", True)
        return
    sys.path.insert(0, str(HERE.parent / "scripts"))
    import budget_spec  # noqa: PLC0415

    embedded_row = {"campaign": "Over", "daily_budget": 100.0, "mtd_spend": 3000.0,
                    "cost": 3000.0, "conv": 0, "budget_lost_is": 0.20, "rank_lost_is": 0.0,
                    "status": "measured"}
    params = dict(core.DEFAULT_PARAMS, days_elapsed=15, target_cpa=50.0)
    py_row = {**embedded_row, "conversions": embedded_row["conv"]}
    del py_row["conv"]
    py_paced = core.add_pace([py_row], params)[0]

    js = (budget_spec.JS_KERNEL
          + f"\nvar r = {json.dumps(embedded_row)};\n"
            f"var P = {json.dumps(params)};\n"
            "console.log(JSON.stringify(pace(r, P)));\n")
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    check("node eval of JS_KERNEL succeeded", out.returncode == 0, out.stderr)
    if out.returncode != 0:
        return
    js_pace = json.loads(out.stdout.strip())
    check("JS pace.verdict == 'over' (row is actually over-pacing)",
          js_pace["verdict"] == "over", js_pace["verdict"])
    check("JS pace.ratio == Python campaign_pace_ratio",
          abs(js_pace["ratio"] - py_paced["campaign_pace_ratio"]) < 1e-9,
          (js_pace["ratio"], py_paced["campaign_pace_ratio"]))
    check("JS pace.verdict == Python pace_verdict",
          js_pace["verdict"] == py_paced["pace_verdict"],
          (js_pace["verdict"], py_paced["pace_verdict"]))
    check("JS pace.confidence == Python pace_confidence",
          js_pace["confidence"] == py_paced["pace_confidence"])
    check("JS pace.flags == Python pace_flags (over_pace, constrained, zero_conv)",
          set(js_pace["flags"]) == set(py_paced["pace_flags"]) == {"over_pace", "constrained", "zero_conv"},
          (js_pace["flags"], py_paced["pace_flags"]))
    check("JS pace.score == Python pace_score == 4.5",
          abs(js_pace["score"] - py_paced["pace_score"]) < 1e-9 and abs(py_paced["pace_score"] - 4.5) < 1e-9,
          (js_pace["score"], py_paced["pace_score"]))


def test_advisor_shortlist():
    print("test_advisor_shortlist")
    m = core.compute_model(core.load_findings(str(FIXTURE)))
    adv = m["advisor"]
    check("advisor.fund has the Raise campaign", [r["campaign"] for r in adv["fund"]] == ["S | Brand"])
    check("advisor.fund proposed_budget is +20% capped",
          abs(adv["fund"][0]["proposed_budget"] - 360.0) < 1e-9, adv["fund"][0]["proposed_budget"])
    check("advisor.trim has the Kill campaign", any(r["campaign"] == "S | Junk" and r["source"] == "kill"
                                                     for r in adv["trim"]))
    # nobody in the fixture is both over-pacing AND CPA above target (over_pace count is 0), so
    # the delta trim group is empty — assert the union is exactly the Kill list on this fixture.
    check("advisor.trim == Kill only on this fixture (0 over-pacing rows)",
          [r["source"] for r in adv["trim"]] == ["kill"], adv["trim"])


def test_advisor_over_pace_trim_delta():
    """The fixture never produces an over-pacing row (test_advisor_shortlist proves
    trim == Kill-only there), so build_advisor's "over_pace" trim branch — over-pacing
    with CPA above target, distinct from the Kill 3x rule — needs its own synthetic
    case. Also proves the branch's exclusions: a Raise-bucket row (cpa<=target by
    definition) never qualifies, and an over-pacing row with cpa<=target doesn't
    either (only "over" AND "cpa>target" together trigger it)."""
    print("test_advisor_over_pace_trim_delta")
    params = dict(core.DEFAULT_PARAMS, target_cpa=50.0, days_elapsed=15, days_in_month=30)
    rows = core.classify([
        # over-pacing, CPA above target, some conversions (not the 3x-rule Kill path)
        {"campaign_id": 1, "campaign": "Over & Bleeding", "channel": "SEARCH",
         "daily_budget": 100.0, "cost": 900.0, "mtd_spend": 3000.0, "conversions": 10,
         "cpa": 90.0, "budget_lost_is": 0.0, "rank_lost_is": 0.0, "status": "measured"},
        # over-pacing but CPA AT/UNDER target — should NOT be trimmed by this rule
        {"campaign_id": 2, "campaign": "Over & Efficient", "channel": "SEARCH",
         "daily_budget": 100.0, "cost": 900.0, "mtd_spend": 3000.0, "conversions": 30,
         "cpa": 30.0, "budget_lost_is": 0.0, "rank_lost_is": 0.0, "status": "measured"},
        # on-track, unrelated
        {"campaign_id": 3, "campaign": "Steady", "channel": "SEARCH",
         "daily_budget": 1000.0, "cost": 500.0, "mtd_spend": 500.0, "conversions": 10,
         "cpa": 50.0, "budget_lost_is": 0.0, "rank_lost_is": 0.0, "status": "measured"},
    ], params)
    paced = core.add_pace(rows, params)
    check("Over & Bleeding is pace_verdict == over",
          next(r for r in paced if r["campaign"] == "Over & Bleeding")["pace_verdict"] == "over")
    adv = core.build_advisor(paced, params)
    trim_names = {r["campaign"] for r in adv["trim"]}
    check("advisor.trim includes the over-pacing + CPA-above-target row",
          "Over & Bleeding" in trim_names, trim_names)
    check("advisor.trim excludes the over-pacing + CPA-AT-target row",
          "Over & Efficient" not in trim_names, trim_names)
    check("advisor.trim excludes the on-track row", "Steady" not in trim_names, trim_names)
    row = next(r for r in adv["trim"] if r["campaign"] == "Over & Bleeding")
    check("trim reason cites the model's CPA and target numbers",
          "90.00" in row["reason"] and "50.00" in row["reason"], row["reason"])
    check("trim entry source == 'over_pace' (distinct from the Kill 3x rule)",
          row["source"] == "over_pace", row["source"])


def test_csv_path_identical_to_mcp():
    print("test_csv_path_identical_to_mcp")
    import assemble_from_csv as ACSV
    meta = {"client_name": "Demo Co", "account_id": "444-555-6666", "currency": "USD",
            "period": "last 30 days", "generated": "2026-06-26",
            "monthly_goal": 30000, "days_elapsed": 15, "days_in_month": 30}
    window = str(HERE / "sample-window.csv")
    mtd = str(HERE / "sample-mtd.csv")
    csv_findings = ACSV.assemble(window, mtd, dict(meta))
    check("csv findings stamp meta.source == user_csv", csv_findings["meta"]["source"] == "user_csv")
    check("csv findings carry reconciliation", bool(csv_findings["meta"].get("reconciliation")))

    m_mcp = core.compute_model(core.load_findings(str(FIXTURE)))
    m_csv = core.compute_model(csv_findings)

    def norm(m):
        rows = [dict(r) for r in m["rows"]]
        for r in rows:
            r.pop("campaign_id", None)   # CSV path uses the campaign name as the id (honest; no
        return {"summary": m["summary"], "rows": rows, "advisor": m["advisor"],
                "goal_sensitivity": m["goal_sensitivity"]}   # numeric id in a UI export)

    a, b = norm(m_mcp), norm(m_csv)
    check("MCP-vs-CSV summary identical", a["summary"] == b["summary"], (a["summary"], b["summary"]))
    check("MCP-vs-CSV rows identical", a["rows"] == b["rows"])
    check("MCP-vs-CSV advisor identical", a["advisor"] == b["advisor"])
    check("MCP-vs-CSV goal_sensitivity identical", a["goal_sensitivity"] == b["goal_sensitivity"])

    # a hand-edit is a hard load failure on the CSV path too (same reconcile.verify gate)
    csv_findings["campaigns"][0]["mtd_spend"] += 500
    import json, tempfile
    with tempfile.TemporaryDirectory() as td:
        fp = Path(td) / "csv-findings.json"
        fp.write_text(json.dumps(csv_findings))
        try:
            core.load_findings(str(fp)); ok = False
        except core.FindingsError:
            ok = True
        check("hand-edited CSV-path findings rejected by core", ok)


def test_no_budget_not_bucketed():
    print("test_no_budget_not_bucketed")
    m = core.compute_model(core.load_findings(str(FIXTURE)))
    nb = [r for r in m["rows"] if r["status"] == "no_budget"]
    check("one no_budget row", len(nb) == 1)
    check("no_budget row has no bucket", nb and nb[0]["bucket"] == "")


def test_empty():
    print("test_empty")
    m = core.compute_model({"meta": {}, "campaigns": []})
    check("empty -> 0 campaigns", m["summary"]["campaigns"] == 0)
    check("empty -> pacing n/a (no goal)", m["summary"]["pace_verdict"] == "n/a")
    check("empty -> goal sensitivity empty (no goal)", m["goal_sensitivity"] == [])


def test_assemble_findings_from_raw():
    print("test_assemble_findings_from_raw")
    import assemble_findings as A
    perf = {"result": [
        {"campaign.id": 1, "campaign.name": "S | Brand", "campaign.advertising_channel_type": "SEARCH",
         "metrics.cost_micros": 3_000_000_000, "metrics.conversions": 60,
         "metrics.search_budget_lost_impression_share": 0.25,
         "metrics.search_rank_lost_impression_share": 0.05},
        # same campaign split across raw rows (e.g. by a segment) -> must merge:
        # cost/conversions summed, name/channel/IS point-in-time from the first row
        {"campaign.id": 1, "campaign.name": "S | Brand", "campaign.advertising_channel_type": "SEARCH",
         "metrics.cost_micros": 1_000_000_000, "metrics.conversions": 40,
         "metrics.search_budget_lost_impression_share": 0.25,
         "metrics.search_rank_lost_impression_share": 0.05},
        # PMax: lost-IS fields absent entirely -> null pass-through, and it is
        # absent from the budgets pull -> no daily_budget key -> status no_budget
        {"campaign.id": 2, "campaign.name": "PMax | Feed", "campaign.advertising_channel_type": "PERFORMANCE_MAX",
         "metrics.cost_micros": 500_000_000, "metrics.conversions": 10},
    ]}
    budgets = {"result": [
        {"campaign.id": 1, "campaign_budget.amount_micros": 300_000_000,
         "campaign_budget.explicitly_shared": False},
    ]}
    mtd = {"result": [
        {"campaign.id": 1, "metrics.cost_micros": 2_200_000_000},
        {"campaign.id": 2, "metrics.cost_micros": 250_000_000},
    ]}
    meta = {"client_name": "T", "account_id": "1", "currency": "CAD",
            "period": "last 30 days", "generated": "2026-07-06",
            "monthly_goal": 30000, "days_elapsed": 15, "days_in_month": 30}
    with tempfile.TemporaryDirectory() as td:
        pp = Path(td) / "perf.txt"; pp.write_text(json.dumps(perf))
        pb = Path(td) / "budgets.txt"; pb.write_text(json.dumps(budgets))
        pm = Path(td) / "mtd.txt"; pm.write_text(json.dumps(mtd))
        f = A.assemble(str(pp), str(pb), str(pm), dict(meta))
        cs = f["campaigns"]
        check("split campaign merged (3 raw rows -> 2 campaigns)", len(cs) == 2, f"{len(cs)}")
        c1, c2 = cs
        check("merged sums micros-converted",
              abs(c1["cost"] - 4000.0) < 1e-9 and abs(c1["conversions"] - 100) < 1e-9)
        check("daily_budget joined and converted", abs(c1["daily_budget"] - 300.0) < 1e-9)
        check("mtd_spend joined per campaign",
              abs(c1["mtd_spend"] - 2200.0) < 1e-9 and abs(c2["mtd_spend"] - 250.0) < 1e-9)
        check("lost-IS passed through as fractions",
              abs(c1["search_budget_lost_is"] - 0.25) < 1e-12
              and abs(c1["search_rank_lost_is"] - 0.05) < 1e-12)
        check("PMax lost-IS absent -> null",
              c2["search_budget_lost_is"] is None and c2["search_rank_lost_is"] is None)
        check("no budgets row -> no daily_budget key", "daily_budget" not in c2)
        rec = f["meta"]["reconciliation"]
        check("reconciliation embedded with raw stamps",
              rec["campaigns"]["rows"] == 2 and len(rec.get("raw_files", [])) == 3)
        # the assembled findings load clean through the core's verification...
        fp = Path(td) / "findings.json"; fp.write_text(json.dumps(f))
        m = core.compute_model(core.load_findings(str(fp)))
        check("assembled findings pass core verification", True)
        s = m["summary"]
        check("core sees the no_budget campaign", s["no_budget"] == 1, f"got {s['no_budget']}")
        check("core pacing computed from assembled MTD",
              abs(s["mtd_spend"] - 2450.0) < 1e-6, f"got {s['mtd_spend']}")
        # ...and a hand-edit is a hard load failure
        f["campaigns"][0]["mtd_spend"] += 500
        fp.write_text(json.dumps(f))
        try:
            core.load_findings(str(fp)); ok = False
        except core.FindingsError:
            ok = True
        check("hand-edited findings rejected by core", ok)


def test_bundle_md_html_parity_and_lazy():
    print("test_bundle_md_html_parity_and_lazy")
    import budget_spec
    from render import build_bundle
    from render import charts as C
    m = core.compute_model(core.load_findings(str(FIXTURE)))
    n = len(m["rows"])
    with tempfile.TemporaryDirectory() as td:
        written = build_bundle(m, dict(budget_spec.SPEC), td, formats=("md", "html"))
        md = next(Path(td).glob("*.md")).read_text()
        html = next(Path(td).glob("*_explorer.html")).read_text()
        svgs = sorted(p.name for p in written if p.suffix == ".svg")
    rows_blk = md.split("## All campaigns")[1].splitlines()
    md_rows = [ln for ln in rows_blk if ln.startswith("| ") and not ln.startswith("| Campaign")]
    embedded = json.loads(re.search(r"^const MODEL = (.+);$", html, re.M).group(1))["rows"]
    check("md row table has every campaign", len(md_rows) == n, f"{len(md_rows)} vs {n}")
    check("html embeds every campaign", len(embedded) == n, f"{len(embedded)} vs {n}")
    # self-containment: the only opaque region allowed is the vendored chart
    # runtime, and only byte-equal to the committed, checksummed vendor files.
    blob = C.vendor_blob()
    check("explorer embeds the verified vendor runtime", blob in html)
    stripped = html.replace(blob, "")
    check("html is self-contained outside the verified vendor blob",
          len(re.findall(r"https?://|<link|src=|cdn", stripped)) == 0)
    # declared charts render as static SVGs and are referenced from the md
    check("both chart svgs written",
          svgs == ["campaigns_by_bucket.svg", "top_spend_by_campaign.svg"], svgs)
    check("md has a Charts section", "## Charts" in md)
    check("md references charts relatively", "_charts/campaigns_by_bucket.svg)" in md)
    check("explorer embeds the chart specs", "const CHARTS = " in html)
    check("building md/html did not import openpyxl", "openpyxl" not in sys.modules)


def main():
    for t in (test_fixture_buckets_and_pacing, test_concentration_and_pace_prescore,
              test_pace_kernel_js_parity_over_pacing,
              test_advisor_shortlist, test_advisor_over_pace_trim_delta,
              test_csv_path_identical_to_mcp,
              test_no_budget_not_bucketed, test_empty,
              test_assemble_findings_from_raw, test_bundle_md_html_parity_and_lazy):
        t()
    print()
    if _failures:
        print(f"FAILED ({len(_failures)}): {', '.join(_failures)}")
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
