#!/usr/bin/env python3
"""Tests for the competitive-pressure filter (stdlib only; run directly).

    python3 tests/test_competitive.py

Asserts the documented fixture result, no-row-loss, the min-cost eligibility
gate, near-miss shape, competitor concentration, the MCP-only vs CSV-augmented
own-side-model identity, reconciliation, and bundle self-containment. Exit 0 =
all pass, 1 = a failure.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE.parents[2] / "_shared"))  # the shared render toolkit

import competitive_core as core  # noqa: E402
import analytics  # noqa: E402

FIXTURE = HERE / "sample-findings.json"
AI_CSV = HERE / "sample-auction-insights.csv"
_failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        _failures.append(name)


def test_fixture_counts():
    print("test_fixture_counts")
    model = core.compute_model(core.load_findings(str(FIXTURE)))
    s = model["summary"]
    check("campaigns == 7", s["campaigns"] == 7, f"got {s['campaigns']}")
    check("scored == 4 (incl. SmallSpend, which is scored but spend-ineligible)",
          s["scored"] == 4, f"got {s['scored']}")
    check("no_prior == 1", s["no_prior"] == 1, f"got {s['no_prior']}")
    check("no_is == 1", s["no_is"] == 1, f"got {s['no_is']}")
    check("inactive == 1", s["inactive"] == 1, f"got {s['inactive']}")
    check("flagged == 2", s["flagged"] == 2, f"got {s['flagged']}")
    check("rank_pressure == 1", s["rank_pressure"] == 1, f"got {s['rank_pressure']}")
    check("budget_capped == 1", s["budget_capped"] == 1, f"got {s['budget_capped']}")
    check("competitor_rows == 5", s["competitor_rows"] == 5, f"got {s['competitor_rows']}")
    n_in = len(core.load_findings(str(FIXTURE))["campaigns"])
    check("rows preserved == input campaigns (no row loss)", len(model["rows"]) == n_in,
          f"{len(model['rows'])} vs {n_in}")


def test_block_attribution():
    print("test_block_attribution")
    model = core.compute_model(core.load_findings(str(FIXTURE)))
    by_id = {r["campaign_id"]: r for r in model["rows"]}
    check("101 NonBrand -> Rank pressure", by_id[101]["block"] == "Rank pressure", by_id[101]["block"])
    check("102 Brand -> Budget capped", by_id[102]["block"] == "Budget capped", by_id[102]["block"])
    check("103 Generic -> unflagged", by_id[103]["block"] == "", by_id[103]["block"])


def test_min_cost_gate():
    print("test_min_cost_gate")
    model = core.compute_model(core.load_findings(str(FIXTURE)))
    by_id = {r["campaign_id"]: r for r in model["rows"]}
    row = by_id[104]  # SmallSpend — would flag on IS-drop alone but cost_this < min_cost
    check("SmallSpend scored but ineligible", row["status"] == "scored" and not row["eligible"])
    check("SmallSpend not flagged despite huge IS drop", row["block"] == "", row["block"])
    check("SmallSpend absent from near_misses (ineligible, not just unflagged)",
          104 not in {r["campaign_id"] for r in model["near_misses"]})


def test_no_prior_no_is_inactive_kept():
    print("test_no_prior_no_is_inactive_kept")
    model = core.compute_model(core.load_findings(str(FIXTURE)))
    by_id = {r["campaign_id"]: r for r in model["rows"]}
    check("105 New -> no_prior, empty block", by_id[105]["status"] == "no_prior" and by_id[105]["block"] == "")
    check("106 LowData -> no_is, empty block", by_id[106]["status"] == "no_is" and by_id[106]["block"] == "")
    check("107 Paused -> inactive, empty block", by_id[107]["status"] == "inactive" and by_id[107]["block"] == "")


def test_near_miss_shape():
    print("test_near_miss_shape")
    model = core.compute_model(core.load_findings(str(FIXTURE)))
    nm = model["near_misses"]
    check("Generic_US_Search present in near_misses", any(r["campaign_id"] == 103 for r in nm))
    check("near-miss entries carry closeness < 1 (not yet firing)", all(r["closeness"] < 1.0 for r in nm))
    check("near-miss entries carry a driver", all(r["driver"] in ("is_drop", "cpc_jump") for r in nm))


def test_competitor_concentration_matches_analytics():
    print("test_competitor_concentration_matches_analytics")
    findings = core.load_findings(str(FIXTURE))
    model = core.compute_model(findings)
    non_self = [r for r in findings["competitors"] if r["domain"].strip().casefold() != "you"]
    expected = analytics.concentration(non_self, "impression_share", top_n=3)
    got = model["competitor_concentration"]
    check("concentration matches analytics.concentration() directly", got == expected, f"{got} vs {expected}")
    check("You row excluded from concentration (n==4)", got["n"] == 4, f"got {got['n']}")
    comp_rows = model["competitors"]
    check("You row still present in model.competitors (no row loss)",
          any(r["domain"] == "You" and r["is_self"] for r in comp_rows))


def test_sensitivity_ladder_shape():
    print("test_sensitivity_ladder_shape")
    model = core.compute_model(core.load_findings(str(FIXTURE)))
    sens = model["sensitivity"]
    check("sensitivity has a row per ladder step", len(sens) == len(core.IS_DROP_LADDER))
    check("exactly one sensitivity row flagged current", sum(1 for r in sens if r["is_current"]) == 1)
    # a SMALLER is-drop-flag threshold is easier to trip (loosest bar) -> flags >= default;
    # a LARGER threshold is a stricter bar -> flags <= default.
    loosest = min(sens, key=lambda r: r["is_drop_flag"])
    strictest = max(sens, key=lambda r: r["is_drop_flag"])
    default_total = next(r["total"] for r in sens if r["is_current"])
    check("loosest (smallest) IS-drop threshold flags >= default", loosest["total"] >= default_total,
          f"{loosest['total']} vs {default_total}")
    check("strictest (largest) IS-drop threshold flags <= default", strictest["total"] <= default_total,
          f"{strictest['total']} vs {default_total}")


def test_empty_campaigns():
    print("test_empty_campaigns")
    f = {"meta": {}, "campaigns": [], "competitors": []}
    model = core.compute_model(f)
    s = model["summary"]
    check("empty -> campaigns 0", s["campaigns"] == 0)
    check("empty -> flagged 0", s["flagged"] == 0)
    check("empty -> sensitivity computed without crash", len(model["sensitivity"]) == len(core.IS_DROP_LADDER))
    check("empty competitors -> concentration all-zero", model["competitor_concentration"]["hhi"] == 0.0)


def _raw_campaign_rows(prior=False):
    """Synthetic search_search-shaped rows for two campaigns, SEARCH channel."""
    if not prior:
        return {"result": [
            {"campaign.id": 201, "campaign.name": "Alpha", "campaign.advertising_channel_type": "SEARCH",
             "metrics.cost_micros": 300_000_000, "metrics.clicks": 150, "metrics.impressions": 6000,
             "metrics.conversions": 10, "metrics.search_impression_share": 0.35,
             "metrics.search_rank_lost_impression_share": 0.40, "metrics.search_budget_lost_impression_share": 0.05},
            # a DISPLAY-channel row must be dropped defensively by the aggregator
            {"campaign.id": 999, "campaign.name": "Display Only", "campaign.advertising_channel_type": "DISPLAY",
             "metrics.cost_micros": 50_000_000, "metrics.clicks": 5, "metrics.impressions": 500,
             "metrics.conversions": 0, "metrics.search_impression_share": 0.9,
             "metrics.search_rank_lost_impression_share": 0.0, "metrics.search_budget_lost_impression_share": 0.0},
        ]}
    return {"result": [
        {"campaign.id": 201, "campaign.name": "Alpha", "campaign.advertising_channel_type": "SEARCH",
         "metrics.cost_micros": 280_000_000, "metrics.clicks": 140, "metrics.impressions": 5800,
         "metrics.conversions": 9, "metrics.search_impression_share": 0.50,
         "metrics.search_rank_lost_impression_share": 0.20, "metrics.search_budget_lost_impression_share": 0.05},
    ]}


def test_assemble_findings_from_raw():
    print("test_assemble_findings_from_raw")
    import tempfile
    import assemble_findings as A
    meta = {"client_name": "T", "account_id": "1", "currency": "CAD",
            "window_this": "wt", "window_prior": "wp", "generated": "2026-07-12"}
    with tempfile.TemporaryDirectory() as td:
        pt = Path(td) / "this.txt"; pt.write_text(json.dumps(_raw_campaign_rows(prior=False)))
        pp = Path(td) / "prior.txt"; pp.write_text(json.dumps(_raw_campaign_rows(prior=True)))
        f = A.assemble(str(pt), str(pp), dict(meta))
        camps = f["campaigns"]
        check("DISPLAY-channel row dropped, only SEARCH kept", len(camps) == 1, f"{len(camps)}")
        c = camps[0]
        check("cost_this converted from micros", abs(c["cost_this"] - 300.0) < 1e-9)
        check("cost_prior converted from micros", abs(c["cost_prior"] - 280.0) < 1e-9)
        check("avg_cpc_this recomputed from cost/clicks", abs(c["avg_cpc_this"] - 2.0) < 1e-9)
        check("has_prior True (Alpha appeared in both pulls)", c["has_prior"] is True)
        check("competitors empty on an MCP-only run", f["competitors"] == [])
        check("meta.auction_insights_source is empty on an MCP-only run",
              f["meta"]["auction_insights_source"] == "")
        rec = f["meta"]["reconciliation"]
        check("reconciliation embedded with raw stamps",
              rec["campaigns"]["rows"] == 1 and len(rec.get("raw_files", [])) == 2)
        # the assembled findings load clean through the core's verification...
        fp = Path(td) / "findings.json"; fp.write_text(json.dumps(f))
        core.load_findings(str(fp))
        check("assembled findings pass core verification", True)
        # ...and a hand-edit is a hard load failure
        f["campaigns"][0]["cost_this"] += 500
        fp.write_text(json.dumps(f))
        try:
            core.load_findings(str(fp)); ok = False
        except core.FindingsError:
            ok = True
        check("hand-edited findings rejected by core", ok)


def test_csv_augmented_matches_mcp_only_own_side():
    print("test_csv_augmented_matches_mcp_only_own_side")
    import tempfile
    import assemble_findings as A
    meta1 = {"client_name": "T", "account_id": "1", "currency": "CAD",
             "window_this": "wt", "window_prior": "wp", "generated": "2026-07-12"}
    meta2 = dict(meta1)
    with tempfile.TemporaryDirectory() as td:
        pt = Path(td) / "this.txt"; pt.write_text(json.dumps(_raw_campaign_rows(prior=False)))
        pp = Path(td) / "prior.txt"; pp.write_text(json.dumps(_raw_campaign_rows(prior=True)))
        f_mcp_only = A.assemble(str(pt), str(pp), meta1)
        f_csv_aug = A.assemble(str(pt), str(pp), meta2, str(AI_CSV))
        check("own-side campaigns array identical MCP-only vs CSV-augmented",
              f_mcp_only["campaigns"] == f_csv_aug["campaigns"])
        check("CSV-augmented run adds competitor rows", len(f_csv_aug["competitors"]) > 0)
        check("MCP-only run has zero competitor rows", len(f_mcp_only["competitors"]) == 0)
        check("CSV-augmented meta.auction_insights_source == user_csv",
              f_csv_aug["meta"]["auction_insights_source"] == "user_csv")
        check("competitor rows carry status competitor_csv in the model",
              all(r["status"] == "competitor_csv"
                  for r in core.compute_model(f_csv_aug)["competitors"]))
        m1 = core.compute_model(f_mcp_only)
        m2 = core.compute_model(f_csv_aug)
        own_side_1 = [{k: v for k, v in r.items() if k != "flags"} for r in m1["rows"]]
        own_side_2 = [{k: v for k, v in r.items() if k != "flags"} for r in m2["rows"]]
        check("own-side model (summary + rows) identical regardless of competitor CSV",
              own_side_1 == own_side_2 and m1["summary"]["flagged"] == m2["summary"]["flagged"])


def test_bundle_md_html_parity_and_lazy():
    print("test_bundle_md_html_parity_and_lazy")
    import re
    import tempfile
    import competitive_spec as spec_mod
    from render import build_bundle
    from render import charts as C
    model = core.compute_model(core.load_findings(str(FIXTURE)))
    n = len(model["rows"])
    with tempfile.TemporaryDirectory() as td:
        written = build_bundle(model, dict(spec_mod.SPEC), td, formats=("md", "html"))
        md = next(Path(td).glob("*.md")).read_text()
        html = next(Path(td).glob("*_explorer.html")).read_text()
        svgs = sorted(p.name for p in written if p.suffix == ".svg")
    rows_blk = md.split("## All Search campaigns")[1].splitlines()
    md_rows = [ln for ln in rows_blk if ln.startswith("| ") and not ln.startswith("| Campaign")]
    embedded = json.loads(re.search(r"^const MODEL = (.+);$", html, re.M).group(1))
    html_rows = len(embedded["rows"])
    check("md row table has every campaign", len(md_rows) == n, f"{len(md_rows)} vs {n}")
    # the standalone HTML explorer bundle embeds the FULL model untouched — the in_play
    # bounded-embed trim applies only to the in-Claude tuner widget (widget_emit), not here.
    check("html embeds every campaign (bundle path is untrimmed)", html_rows == n, f"{html_rows} vs {n}")
    blob = C.vendor_blob()
    check("explorer embeds the verified vendor runtime", blob in html)
    stripped = html.replace(blob, "")
    check("html is self-contained outside the verified vendor blob",
          len(re.findall(r"https?://|<link|src=|cdn", stripped)) == 0)
    check("both chart svgs written", svgs == ["is_cpc_scatter.svg", "pressure_by_block.svg"], svgs)
    check("md has a Charts section", "## Charts" in md)
    check("explorer embeds the chart specs", "const CHARTS = " in html)
    check("html mentions competitor data honesty", "Auction Insights" in html)
    check("building md/html did not import openpyxl", "openpyxl" not in sys.modules)


def main():
    for t in (test_fixture_counts, test_block_attribution, test_min_cost_gate,
              test_no_prior_no_is_inactive_kept, test_near_miss_shape,
              test_competitor_concentration_matches_analytics, test_sensitivity_ladder_shape,
              test_empty_campaigns, test_assemble_findings_from_raw,
              test_csv_augmented_matches_mcp_only_own_side, test_bundle_md_html_parity_and_lazy):
        t()
    print()
    if _failures:
        print(f"FAILED ({len(_failures)}): {', '.join(_failures)}")
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
