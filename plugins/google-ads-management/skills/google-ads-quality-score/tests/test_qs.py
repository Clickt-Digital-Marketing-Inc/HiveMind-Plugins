#!/usr/bin/env python3
"""Tests for the Quality Score forensics core + bundle (stdlib only; run directly).

    python3 tests/test_qs.py

Asserts the fixture buckets, the unscored handling, the component-target dropdown
effect, dedupe, an empty edge, and md/html bundle parity + lazy-openpyxl.
Exit 0 = pass, 1 = fail.
"""
import json
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE.parents[2] / "_shared"))

import qs_core as core  # noqa: E402

FIXTURE = HERE / "sample-findings.json"
_failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        _failures.append(name)


def test_fixture_buckets():
    print("test_fixture_buckets")
    m = core.compute_model(core.load_findings(str(FIXTURE)))
    s = m["summary"]
    check("keywords == 8 (no row loss)", s["keywords"] == 8, f"got {s['keywords']}")
    check("scored == 7", s["scored"] == 7, f"got {s['scored']}")
    check("unscored == 1", s["unscored"] == 1, f"got {s['unscored']}")
    check("in_scope == 6", s["in_scope"] == 6, f"got {s['in_scope']}")
    check("lp == 1", s["lp"] == 1, f"got {s['lp']}")
    check("ad_rel == 1", s["ad_rel"] == 1, f"got {s['ad_rel']}")
    check("exp_ctr == 2", s["exp_ctr"] == 2, f"got {s['exp_ctr']}")
    check("critical == 1", s["critical"] == 1, f"got {s['critical']}")
    check("other == 1", s["other"] == 1, f"got {s['other']}")
    # #4 (Critical, 0.625% CTR, 0 conv) and #6 are both low-CTR pause candidates (flag is
    # independent of the bucket).
    check("pause_candidates == 2", s["pause_candidates"] == 2, f"got {s['pause_candidates']}")
    check("avg_qs == 4.0", abs(s["avg_qs"] - 4.0) < 1e-6, f"got {s['avg_qs']}")


def test_dominant_factor():
    print("test_dominant_factor")
    m = core.compute_model(core.load_findings(str(FIXTURE)))
    dom = m["dominant_factor"]
    drag = {d["component"]: d for d in dom["drag"]}
    # Hand-computed from sample-findings.json at default params (qs_low=5,
    # component_target=2): LP drag = #1(500)+#4(800)=1300; AR drag =
    # #2(400)+#4(800)=1200; CTR drag = #3(300)+#4(800)+#6(250)=1350.
    check("LP drag cost == 1300", abs(drag["Landing page"]["cost"] - 1300.0) < 1e-6,
          f"got {drag['Landing page']['cost']}")
    check("AR drag cost == 1200", abs(drag["Ad relevance"]["cost"] - 1200.0) < 1e-6,
          f"got {drag['Ad relevance']['cost']}")
    check("CTR drag cost == 1350", abs(drag["Expected CTR"]["cost"] - 1350.0) < 1e-6,
          f"got {drag['Expected CTR']['cost']}")
    check("LP drag keywords == 2", drag["Landing page"]["keywords"] == 2)
    check("AR drag keywords == 2", drag["Ad relevance"]["keywords"] == 2)
    check("CTR drag keywords == 3", drag["Expected CTR"]["keywords"] == 3)
    check("Expected CTR is dominant", dom["dominant_component"] == "Expected CTR",
          f"got {dom['dominant_component']!r}")
    check("only Expected CTR flagged worst_factor",
          [d["component"] for d in dom["drag"] if "worst_factor" in d["flags"]] == ["Expected CTR"])
    # top_share = 1350/3850 (half-up 4dp) == 0.3506; summary carries it *100, 2dp.
    check("summary.dominant_share_pct == 35.06", abs(m["summary"]["dominant_share_pct"] - 35.06) < 1e-6,
          f"got {m['summary']['dominant_share_pct']}")
    check("summary.dominant_component == Expected CTR",
          m["summary"]["dominant_component"] == "Expected CTR")
    # location: dominant (Expected CTR) below-target cost sits in ad groups
    # "Program Gamma" (550: #3 300 + #6 250) and "Generic" (800: #4) -> top-3
    # share is 100% of the (only two) ad groups' cost.
    loc_by_ag = {r["ad_group"]: r for r in dom["location_rows"]}
    check("location has 2 ad groups", len(dom["location_rows"]) == 2, f"got {len(dom['location_rows'])}")
    check("Program Gamma location cost == 550", abs(loc_by_ag["Program Gamma"]["cost"] - 550.0) < 1e-6)
    check("Generic location cost == 800", abs(loc_by_ag["Generic"]["cost"] - 800.0) < 1e-6)
    check("summary.dominant_location_share_pct == 100.0",
          abs(m["summary"]["dominant_location_share_pct"] - 100.0) < 1e-6,
          f"got {m['summary']['dominant_location_share_pct']}")


def test_dominant_factor_clean_when_no_in_scope():
    print("test_dominant_factor_clean_when_no_in_scope")
    f = {"meta": {}, "keywords": [
        {"ad_group_id": 1, "ad_group": "AG", "campaign": "C", "keyword": "k",
         "match_type": "EXACT", "quality_score": 9, "landing_page_exp": "AVERAGE",
         "ad_relevance": "AVERAGE", "expected_ctr": "AVERAGE",
         "impressions": 100, "clicks": 5, "cost": 50, "conversions": 2},
    ]}
    m = core.compute_model(f)
    dom = m["dominant_factor"]
    check("no dominant component when nothing in scope", dom["dominant_component"] == "")
    check("all drag costs zero", all(d["cost"] == 0.0 for d in dom["drag"]))
    check("dominant_share_pct == 0", m["summary"]["dominant_share_pct"] == 0.0)
    check("location empty", dom["location_rows"] == [])


def test_dominant_factor_three_way_tie():
    print("test_dominant_factor_three_way_tie")
    # One keyword per component, identical cost -> all three components tie
    # for worst. Ties must be flagged HONESTLY (all three get 'worst_factor')
    # but the single dominant_component label must resolve deterministically
    # in declared component order (Landing page wins). Cross-verified against
    # the JS mirror (node) and the xlsx SUMPRODUCT/IF formulas (LibreOffice
    # recalculated) during manual review — this is the Python-side pin.
    f = {"meta": {}, "keywords": [
        {"ad_group_id": 1, "ad_group": "AG1", "campaign": "C", "keyword": "k1", "match_type": "EXACT",
         "quality_score": 3, "landing_page_exp": "BELOW_AVERAGE", "ad_relevance": "AVERAGE",
         "expected_ctr": "AVERAGE", "impressions": 500, "clicks": 20, "cost": 100, "conversions": 1},
        {"ad_group_id": 2, "ad_group": "AG2", "campaign": "C", "keyword": "k2", "match_type": "EXACT",
         "quality_score": 3, "landing_page_exp": "AVERAGE", "ad_relevance": "BELOW_AVERAGE",
         "expected_ctr": "AVERAGE", "impressions": 500, "clicks": 20, "cost": 100, "conversions": 1},
        {"ad_group_id": 3, "ad_group": "AG3", "campaign": "C", "keyword": "k3", "match_type": "EXACT",
         "quality_score": 3, "landing_page_exp": "AVERAGE", "ad_relevance": "AVERAGE",
         "expected_ctr": "BELOW_AVERAGE", "impressions": 500, "clicks": 20, "cost": 100, "conversions": 1},
    ]}
    m = core.compute_model(f)
    dom = m["dominant_factor"]
    check("tie resolves to Landing page (declared order wins)",
          dom["dominant_component"] == "Landing page", dom["dominant_component"])
    check("all three components flagged worst_factor (honest tie)",
          all("worst_factor" in d["flags"] for d in dom["drag"]),
          [(d["component"], d["flags"]) for d in dom["drag"]])
    check("dominant_share_pct == 33.33 (1 of 3 equal shares)",
          abs(m["summary"]["dominant_share_pct"] - 33.33) < 1e-6)
    check("location restricted to the dominant (LP-only) ad group",
          dom["location_rows"] == [{"ad_group": "AG1", "cost": 100.0, "keywords": 1}],
          dom["location_rows"])


def test_provenance_source_defaults_mcp():
    print("test_provenance_source_defaults_mcp")
    m = core.compute_model(core.load_findings(str(FIXTURE)))
    check("provenance.source defaults to 'mcp'", m["provenance"]["source"] == "mcp",
          f"got {m['provenance'].get('source')!r}")
    f2 = core.load_findings(str(FIXTURE))
    f2["meta"] = dict(f2["meta"], source="user_csv")
    m2 = core.compute_model(f2)
    check("provenance.source surfaces user_csv", m2["provenance"]["source"] == "user_csv")


def test_unscored_kept_not_averaged():
    print("test_unscored_kept_not_averaged")
    m = core.compute_model(core.load_findings(str(FIXTURE)))
    un = [r for r in m["rows"] if r["status"] == "unscored"]
    check("one unscored row kept", len(un) == 1)
    check("unscored has no bucket", un and un[0]["bucket"] == "")
    check("unscored qs is None", un and un[0]["qs"] is None)


def test_component_target_dropdown_effect():
    print("test_component_target_dropdown_effect")
    f = core.load_findings(str(FIXTURE))
    base = core.compute_model(f)["summary"]
    # raise target to Above average -> Average components now count as below-target,
    # so more keywords get bucketed / fewer land in "Other".
    f2 = dict(f); f2["params"] = {"component_target": 3}
    hi = core.compute_model(f2)["summary"]
    check("raising target reduces 'Other'", hi["other"] <= base["other"])
    check("raising target grows Critical-ish coverage", hi["critical"] >= base["critical"],
          f"{hi['critical']} vs {base['critical']}")


def test_dedupe_by_key():
    print("test_dedupe_by_key")
    f = {"meta": {}, "keywords": [
        {"ad_group_id": 1, "keyword": "k", "match_type": "PHRASE", "quality_score": 4,
         "landing_page_exp": "BELOW_AVERAGE", "ad_relevance": "AVERAGE", "expected_ctr": "AVERAGE",
         "impressions": 500, "clicks": 5, "cost": 50, "conversions": 1},
        {"ad_group_id": 1, "keyword": "k", "match_type": "PHRASE", "quality_score": 4,
         "landing_page_exp": "BELOW_AVERAGE", "ad_relevance": "AVERAGE", "expected_ctr": "AVERAGE",
         "impressions": 500, "clicks": 5, "cost": 50, "conversions": 1},
    ]}
    m = core.compute_model(f)
    check("dup merged to one row", len(m["rows"]) == 1, f"got {len(m['rows'])}")
    check("cost summed (100)", m["rows"] and abs(m["rows"][0]["cost"] - 100) < 1e-6)


def test_empty():
    print("test_empty")
    m = core.compute_model({"meta": {}, "keywords": []})
    check("empty -> 0 keywords", m["summary"]["keywords"] == 0)
    check("empty -> avg_qs None", m["summary"]["avg_qs"] is None)
    check("sensitivity computed", len(m["threshold_sensitivity"]) == 7)


def test_assemble_findings_from_raw():
    print("test_assemble_findings_from_raw")
    import assemble_findings as A
    raw = {"result": [
        {"campaign.name": "C", "ad_group.id": 1, "ad_group.name": "g",
         "ad_group_criterion.keyword.text": "k1",
         "ad_group_criterion.keyword.match_type": "PHRASE",
         "ad_group_criterion.quality_info.quality_score": 4,
         "ad_group_criterion.quality_info.post_click_quality_score": "BELOW_AVERAGE",
         "ad_group_criterion.quality_info.creative_quality_score": "AVERAGE",
         "ad_group_criterion.quality_info.search_predicted_ctr": "AVERAGE",
         "metrics.impressions": 100, "metrics.clicks": 5,
         "metrics.cost_micros": 2_000_000, "metrics.conversions": 1},
        # same dedupe key split across raw rows (e.g. by a segment) -> must
        # merge: metrics summed, QS/ratings point-in-time from the first row
        {"campaign.name": "C", "ad_group.id": 1, "ad_group.name": "g",
         "ad_group_criterion.keyword.text": "k1",
         "ad_group_criterion.keyword.match_type": "PHRASE",
         "ad_group_criterion.quality_info.quality_score": 4,
         "ad_group_criterion.quality_info.post_click_quality_score": "BELOW_AVERAGE",
         "ad_group_criterion.quality_info.creative_quality_score": "AVERAGE",
         "ad_group_criterion.quality_info.search_predicted_ctr": "AVERAGE",
         "metrics.impressions": 100, "metrics.clicks": 5,
         "metrics.cost_micros": 1_000_000, "metrics.conversions": 0.5},
        # unscored keyword: quality_info fields absent entirely -> qs null
        {"campaign.name": "C", "ad_group.id": 2, "ad_group.name": "h",
         "ad_group_criterion.keyword.text": "k2",
         "ad_group_criterion.keyword.match_type": "BROAD",
         "metrics.impressions": 10, "metrics.clicks": 0,
         "metrics.cost_micros": 500_000, "metrics.conversions": 0},
    ]}
    meta = {"client_name": "T", "account_id": "1", "currency": "CAD",
            "period": "last 30 days", "generated": "2026-07-06"}
    with tempfile.TemporaryDirectory() as td:
        pkw = Path(td) / "kw.txt"; pkw.write_text(json.dumps(raw))
        f = A.assemble(str(pkw), dict(meta))
        kws = f["keywords"]
        check("split key merged (3 raw rows -> 2 keywords)", len(kws) == 2, f"{len(kws)}")
        k = kws[0]
        check("merged sums correct",
              k["impressions"] == 200 and k["clicks"] == 10 and abs(k["cost"] - 3.0) < 1e-9
              and abs(k["conversions"] - 1.5) < 1e-9)
        check("qs + ratings point-in-time from first row",
              k["quality_score"] == 4 and k["landing_page_exp"] == "BELOW_AVERAGE"
              and k["ad_relevance"] == "AVERAGE" and k["expected_ctr"] == "AVERAGE")
        check("absent quality_info -> unscored (qs null)", kws[1]["quality_score"] is None)
        check("unscored cost micros converted", abs(kws[1]["cost"] - 0.5) < 1e-9)
        rec = f["meta"]["reconciliation"]
        check("reconciliation embedded with raw stamp",
              rec["keywords"]["rows"] == 2 and len(rec.get("raw_files", [])) == 1)
        # the assembled findings load clean through the core's verification...
        fp = Path(td) / "findings.json"; fp.write_text(json.dumps(f))
        m = core.compute_model(core.load_findings(str(fp)))
        check("assembled findings pass core verification", True)
        check("core dedupe is a no-op on assembled output", len(m["rows"]) == 2)
        # ...and a hand-edit is a hard load failure
        f["keywords"][0]["cost"] += 500
        fp.write_text(json.dumps(f))
        try:
            core.load_findings(str(fp)); ok = False
        except core.FindingsError:
            ok = True
        check("hand-edited findings rejected by core", ok)


def test_bundle_md_html_parity_and_lazy():
    print("test_bundle_md_html_parity_and_lazy")
    import qs_spec
    from render import build_bundle
    from render import charts as C
    m = core.compute_model(core.load_findings(str(FIXTURE)))
    n = len(m["rows"])
    with tempfile.TemporaryDirectory() as td:
        written = build_bundle(m, dict(qs_spec.SPEC), td, formats=("md", "html"))
        md = next(Path(td).glob("*.md")).read_text()
        html = next(Path(td).glob("*_explorer.html")).read_text()
        svgs = sorted(p.name for p in written if p.suffix == ".svg")
    rows_blk = md.split("## All keywords")[1].splitlines()
    md_rows = [ln for ln in rows_blk if ln.startswith("| ") and not ln.startswith("| Keyword")]
    embedded = json.loads(re.search(r"^const MODEL = (.+);$", html, re.M).group(1))["rows"]
    check("md row table has every keyword", len(md_rows) == n, f"{len(md_rows)} vs {n}")
    check("html embeds every keyword", len(embedded) == n, f"{len(embedded)} vs {n}")
    # self-containment: the only opaque region allowed is the vendored chart
    # runtime, and only byte-equal to the committed, checksummed vendor files.
    blob = C.vendor_blob()
    check("explorer embeds the verified vendor runtime", blob in html)
    stripped = html.replace(blob, "")
    check("html is self-contained outside the verified vendor blob",
          len(re.findall(r"https?://|<link|src=|cdn", stripped)) == 0)
    # declared charts render as static SVGs and are referenced from the md
    check("both chart svgs written", svgs == ["qs_distribution.svg", "spend_by_bucket.svg"], svgs)
    check("md has a Charts section", "## Charts" in md)
    check("md references charts relatively", "_charts/spend_by_bucket.svg)" in md)
    check("explorer embeds the chart specs", "const CHARTS = " in html)
    check("building md/html did not import openpyxl", "openpyxl" not in sys.modules)


def main():
    for t in (test_fixture_buckets, test_dominant_factor, test_dominant_factor_clean_when_no_in_scope,
              test_dominant_factor_three_way_tie,
              test_provenance_source_defaults_mcp, test_unscored_kept_not_averaged,
              test_component_target_dropdown_effect,
              test_dedupe_by_key, test_empty, test_assemble_findings_from_raw,
              test_bundle_md_html_parity_and_lazy):
        t()
    print()
    if _failures:
        print(f"FAILED ({len(_failures)}): {', '.join(_failures)}")
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
