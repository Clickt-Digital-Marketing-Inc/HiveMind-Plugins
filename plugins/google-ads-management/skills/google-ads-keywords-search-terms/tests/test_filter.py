#!/usr/bin/env python3
"""Tests for the search-term waste-filter core (stdlib only; run directly).

    python3 tests/test_filter.py

Asserts the documented fixture result, no-row-loss, dedupe, the empty-universe
edge, and fractional-conversion handling. Exit 0 = all pass, 1 = a failure.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE.parents[2] / "_shared"))  # the shared render toolkit

import waste_filter_core as core  # noqa: E402

FIXTURE = HERE / "sample-findings.json"
_failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        _failures.append(name)


def test_fixture_counts():
    print("test_fixture_counts")
    model = core.compute_model(core.load_findings(str(FIXTURE)))
    s = model["summary"]
    check("block1 == 1", s["block1"] == 1, f"got {s['block1']}")
    check("block2 == 1", s["block2"] == 1, f"got {s['block2']}")
    check("no_benchmark == 1", s["no_benchmark"] == 1, f"got {s['no_benchmark']}")
    check("universe == 8 (no rows dropped)", s["universe"] == 8, f"got {s['universe']}")
    check("scored == 7", s["scored"] == 7, f"got {s['scored']}")
    check("wasted == 230.0", abs(s["wasted"] - 230.0) < 1e-6, f"got {s['wasted']}")
    # every input term survives into the model
    n_terms = len(core.load_findings(str(FIXTURE))["search_terms"])
    check("rows preserved == input terms", len(model["rows"]) == n_terms, f"{len(model['rows'])} vs {n_terms}")


def test_no_benchmark_row_present():
    print("test_no_benchmark_row_present")
    model = core.compute_model(core.load_findings(str(FIXTURE)))
    nb = [r for r in model["rows"] if r["status"] == "no_benchmark"]
    check("no_benchmark row kept with status", len(nb) == 1)
    check("no_benchmark row has empty block", nb and nb[0]["block"] == "")


def test_empty_universe():
    print("test_empty_universe")
    f = {"meta": {}, "benchmarks": [{"campaign_id": 1, "campaign": "X", "ctr": 0.1, "cost": 100.0, "conversions": 10.0}],
         "search_terms": []}
    model = core.compute_model(f)
    s = model["summary"]
    check("empty → universe 0", s["universe"] == 0)
    check("empty → block1/2 == 0", s["block1"] == 0 and s["block2"] == 0)
    check("empty → sensitivity computed without crash", len(model["sensitivity"]) == len(core.COST_LADDER))


def test_dedupe_by_key():
    print("test_dedupe_by_key")
    # same (campaign, ad_group, term, match_type) twice → one merged row, summed metrics
    f = {"meta": {}, "benchmarks": [{"campaign_id": 1, "campaign": "X", "ctr": 0.10, "cost": 1000.0, "conversions": 100.0}],
         "search_terms": [
             {"campaign_id": 1, "campaign": "X", "ad_group": "g", "term": "dup", "match_type": "PHRASE",
              "impressions": 500, "clicks": 5, "ctr": 0.01, "cost": 20.0, "conversions_90d": 0, "conversions_30d": 0},
             {"campaign_id": 1, "campaign": "X", "ad_group": "g", "term": "dup", "match_type": "PHRASE",
              "impressions": 500, "clicks": 5, "ctr": 0.01, "cost": 20.0, "conversions_90d": 0, "conversions_30d": 0},
         ]}
    model = core.compute_model(f)
    rows = model["rows"]
    check("duplicate key merged to one row", len(rows) == 1, f"got {len(rows)}")
    check("merged cost summed (40.0)", rows and abs(rows[0]["cost"] - 40.0) < 1e-6, f"got {rows[0]['cost'] if rows else None}")
    check("merged ctr recomputed (10/1000=0.01)", rows and abs(rows[0]["ctr"] - 0.01) < 1e-9)


def test_fractional_conv30_blocks_block2():
    print("test_fractional_conv30_blocks_block2")
    # converted earlier (conv90>0), tiny 30d conversion (0.5) → NOT cold → not Block 2 at default max=0
    f = {"meta": {}, "benchmarks": [{"campaign_id": 1, "campaign": "X", "ctr": 0.10, "cost": 1000.0, "conversions": 100.0}],
         "search_terms": [
             {"campaign_id": 1, "campaign": "X", "ad_group": "g", "term": "warm", "match_type": "NEAR_PHRASE",
              "impressions": 4000, "clicks": 40, "ctr": 0.01, "cost": 200.0, "conversions_90d": 3, "conversions_30d": 0.5},
         ]}
    s = core.compute_model(f)["summary"]
    check("fractional conv30 (0.5) keeps it out of Block 2", s["block2"] == 0, f"got {s['block2']}")
    # but with conv30 == 0 it WOULD be Block 2 (sanity)
    f["search_terms"][0]["conversions_30d"] = 0
    s2 = core.compute_model(f)["summary"]
    check("conv30==0 → Block 2 == 1 (sanity)", s2["block2"] == 1, f"got {s2['block2']}")


def test_sensitivity_and_near_miss_shapes():
    print("test_sensitivity_and_near_miss_shapes")
    model = core.compute_model(core.load_findings(str(FIXTURE)))
    sens = model["sensitivity"]
    check("sensitivity has a row per ladder step", len(sens) == len(core.COST_LADDER))
    check("exactly one sensitivity row flagged current", sum(1 for r in sens if r["is_current"]) == 1)
    # near-miss entries expose the qualify-if threshold
    nm = model["near_misses_block1"]
    check("near_misses_block1 entries carry qualify_if_cost_multiple_le",
          all("qualify_if_cost_multiple_le" in r for r in nm))


def test_assemble_findings_from_raw():
    print("test_assemble_findings_from_raw")
    import tempfile
    import assemble_findings as A
    raw90 = {"result": [
        {"campaign.id": 1, "campaign.name": "C", "ad_group.name": "g",
         "search_term_view.search_term": "t1", "segments.search_term_match_type": "PHRASE",
         "metrics.conversions": 0, "metrics.clicks": 5, "metrics.impressions": 100,
         "metrics.cost_micros": 2_000_000},
        # same dedupe key split across raw rows (e.g. by a segment) -> must merge
        {"campaign.id": 1, "campaign.name": "C", "ad_group.name": "g",
         "search_term_view.search_term": "t1", "segments.search_term_match_type": "PHRASE",
         "metrics.conversions": 1, "metrics.clicks": 5, "metrics.impressions": 100,
         "metrics.cost_micros": 1_000_000},
        # EXACT row -> dropped defensively (excluded at source by the pull)
        {"campaign.id": 1, "campaign.name": "C", "ad_group.name": "g",
         "search_term_view.search_term": "tx", "segments.search_term_match_type": "EXACT",
         "metrics.conversions": 0, "metrics.clicks": 1, "metrics.impressions": 10,
         "metrics.cost_micros": 500_000},
    ]}
    raw30 = {"result": [
        {"campaign.id": 1, "ad_group.name": "g", "search_term_view.search_term": "t1",
         "segments.search_term_match_type": "PHRASE", "metrics.conversions": 0.5},
    ]}
    bench = {"result": [
        {"campaign.id": 1, "campaign.name": "C", "metrics.ctr": 0.1,
         "metrics.cost_micros": 100_000_000, "metrics.conversions": 10},
    ]}
    meta = {"client_name": "T", "account_id": "1", "currency": "CAD",
            "window_90d": "w90", "window_30d": "w30", "generated": "2026-07-06"}
    with tempfile.TemporaryDirectory() as td:
        p90 = Path(td) / "t90.txt"; p90.write_text(json.dumps(raw90))
        p30 = Path(td) / "t30.txt"; p30.write_text(json.dumps(raw30))
        pb = Path(td) / "b.txt"; pb.write_text(json.dumps(bench))
        f = A.assemble(str(p90), str(p30), str(pb), dict(meta))
        terms = f["search_terms"]
        check("split key merged into one row", len(terms) == 1, f"{len(terms)}")
        t = terms[0]
        check("merged sums correct",
              t["impressions"] == 200 and t["clicks"] == 10 and abs(t["cost"] - 3.0) < 1e-9
              and t["conversions_90d"] == 1 and t["conversions_30d"] == 0.5)
        check("ctr recomputed from sums", abs(t["ctr"] - 0.05) < 1e-12)
        check("benchmark micros converted", abs(f["benchmarks"][0]["cost"] - 100.0) < 1e-9)
        rec = f["meta"]["reconciliation"]
        check("reconciliation embedded with raw stamps",
              rec["search_terms"]["rows"] == 1 and len(rec.get("raw_files", [])) == 3)
        # the assembled findings load clean through the core's verification...
        fp = Path(td) / "findings.json"; fp.write_text(json.dumps(f))
        core.load_findings(str(fp))
        check("assembled findings pass core verification", True)
        # ...and a hand-edit is a hard load failure
        f["search_terms"][0]["cost"] += 500
        fp.write_text(json.dumps(f))
        try:
            core.load_findings(str(fp)); ok = False
        except core.FindingsError:
            ok = True
        check("hand-edited findings rejected by core", ok)


def test_bundle_md_html_parity_and_lazy():
    print("test_bundle_md_html_parity_and_lazy")
    import re
    import tempfile
    import waste_filter_spec as spec_mod
    from render import build_bundle
    from render import charts as C
    model = core.compute_model(core.load_findings(str(FIXTURE)))
    n = len(model["rows"])
    with tempfile.TemporaryDirectory() as td:
        written = build_bundle(model, dict(spec_mod.SPEC), td, formats=("md", "html"))
        md = next(Path(td).glob("*.md")).read_text()
        html = next(Path(td).glob("*_explorer.html")).read_text()
        svgs = sorted(p.name for p in written if p.suffix == ".svg")
    # md carries every row (no-row-loss layer); html embeds every row
    rows_blk = md.split("## All loose-match terms")[1].splitlines()
    md_rows = [ln for ln in rows_blk if ln.startswith("| ") and not ln.startswith("| Search term")]
    embedded = json.loads(re.search(r"^const MODEL = (.+);$", html, re.M).group(1))
    html_rows = len(embedded["rows"])
    check("md row table has every term", len(md_rows) == n, f"{len(md_rows)} vs {n}")
    check("html embeds every term", html_rows == n, f"{html_rows} vs {n}")
    # self-containment: the only opaque region allowed is the vendored chart
    # runtime, and only byte-equal to the committed, checksummed vendor files.
    blob = C.vendor_blob()
    check("explorer embeds the verified vendor runtime", blob in html)
    stripped = html.replace(blob, "")
    check("html is self-contained outside the verified vendor blob",
          len(re.findall(r"https?://|<link|src=|cdn", stripped)) == 0)
    # declared charts render as static SVGs and are referenced from the md
    check("both chart svgs written", svgs == ["ctr_cost_scatter.svg", "waste_by_block.svg"], svgs)
    check("md has a Charts section", "## Charts" in md)
    check("md references charts relatively", "_charts/waste_by_block.svg)" in md)
    check("explorer embeds the chart specs", "const CHARTS = " in html)
    check("building md/html did not import openpyxl", "openpyxl" not in sys.modules)


def test_term_ngrams():
    print("test_term_ngrams")
    check("unigrams + bigrams, sorted",
          core.term_ngrams("cheap brand thing") ==
          ["brand", "brand thing", "cheap", "cheap brand", "thing"])
    check("single word -> one unigram, no bigram", core.term_ngrams("thing") == ["thing"])
    check("repeated word deduped per term",
          core.term_ngrams("free free shipping") == ["free", "free free", "free shipping", "shipping"])
    check("empty term -> empty list", core.term_ngrams("") == [])
    check("whitespace/case normalized",
          core.term_ngrams("  Cheap   BRAND ") == ["brand", "cheap", "cheap brand"])


def test_waste_ngrams_and_advisor_summary():
    print("test_waste_ngrams_and_advisor_summary")
    model = core.compute_model(core.load_findings(str(FIXTURE)))
    ng = model["ngrams"]
    # Block 1 term "cheap brand thing" ($30) + Block 2 term "old converter gone
    # cold" ($200) are the only two qualifying rows on the fixture.
    top_by_ngram = {e["ngram"]: e for e in ng["top"]}
    check("n-gram from the Block 1 term present", "cheap" in top_by_ngram)
    check("n-gram cost == the qualifying term's cost",
          top_by_ngram["cheap"]["cost"] == 30.0, f"got {top_by_ngram.get('cheap')}")
    check("bigram present", "gone cold" in top_by_ngram)
    check("no n-gram from a non-qualifying term ('good brand term' unflagged)",
          "good" not in top_by_ngram)
    conc = ng["concentration"]
    check("concentration carries the standard shape",
          {"n", "n_nonzero", "top_n", "total", "top_share", "hhi", "effective_n"} <= set(conc))
    check("concentration total == sum of every n-gram's cost",
          abs(conc["total"] - sum(e["cost"] for e in ng["top"])) < 1e-6,
          f"conc total {conc['total']} vs sum {sum(e['cost'] for e in ng['top'])}")

    summary = core.advisor_summary(model)
    check("advisor summary cites Block 1 term + cost", "cheap brand thing" in summary and "30.00" in summary)
    check("advisor summary cites Block 2 term + cost", "old converter gone cold" in summary and "200.00" in summary)
    check("advisor summary cites total wasted spend", "230.00" in summary)
    check("advisor summary offers the Editor CSVs", "make_editor_csv.py" in summary)

    # 0/0 clean-result branch — empty universe never qualifies.
    empty = core.compute_model({"meta": {}, "benchmarks": [], "search_terms": []})
    clean_summary = core.advisor_summary(empty)
    check("0/0 advisor summary is the clean-result message, no term citations",
          "clean result" in clean_summary and "\"" not in clean_summary.split("===")[-1])


def main():
    for t in (test_fixture_counts, test_no_benchmark_row_present, test_empty_universe,
              test_dedupe_by_key, test_fractional_conv30_blocks_block2,
              test_sensitivity_and_near_miss_shapes, test_assemble_findings_from_raw,
              test_bundle_md_html_parity_and_lazy, test_term_ngrams,
              test_waste_ngrams_and_advisor_summary):
        t()
    print()
    if _failures:
        print(f"FAILED ({len(_failures)}): {', '.join(_failures)}")
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
