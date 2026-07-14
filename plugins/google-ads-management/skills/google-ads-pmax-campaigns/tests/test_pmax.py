#!/usr/bin/env python3
"""Tests for the Performance Max momentum-filter core (stdlib only; run directly).

    python3 tests/test_pmax.py

Asserts the documented fixture result, no-row-loss, the no-activity hold-out, the
empty-universe edge, dedupe-by-campaign, the zero-prior-ROAS new-launch path, the
min-spend floor, sensitivity shapes, and md/html bundle parity + lazy openpyxl.
Exit 0 = all pass, 1 = a failure.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE.parents[2] / "_shared"))  # the shared render toolkit

import pmax_core as core  # noqa: E402

FIXTURE = HERE / "sample-findings-pmax.json"
_failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        _failures.append(name)


def test_fixture_counts():
    print("test_fixture_counts")
    model = core.compute_model(core.load_findings(str(FIXTURE)))
    s = model["summary"]
    check("block1 == 2", s["block1"] == 2, f"got {s['block1']}")
    check("block2 == 1", s["block2"] == 1, f"got {s['block2']}")
    check("universe == 5 (no rows dropped)", s["universe"] == 5, f"got {s['universe']}")
    check("scored == 4", s["scored"] == 4, f"got {s['scored']}")
    check("no_activity == 1", s["no_activity"] == 1, f"got {s['no_activity']}")
    check("winners_spend == 600.0", abs(s["winners_spend"] - 600.0) < 1e-6, f"got {s['winners_spend']}")
    check("losers_spend == 400.0", abs(s["losers_spend"] - 400.0) < 1e-6, f"got {s['losers_spend']}")
    # every distinct campaign across both windows survives into the model
    f = core.load_findings(str(FIXTURE))
    ids = {r["campaign_id"] for r in f["last_window"]} | {r["campaign_id"] for r in f["prev_window"]}
    check("rows preserved == distinct campaigns", len(model["rows"]) == len(ids),
          f"{len(model['rows'])} vs {len(ids)}")
    blocks = {r["campaign"]: r["block"] for r in model["rows"]}
    check("Shopping-Core is Block 1", blocks.get("PMax | Shopping - Core") == "Block 1")
    check("Prospecting is Block 2", blocks.get("PMax - Prospecting") == "Block 2")
    check("Brand Steady is unflagged", blocks.get("PMax - Brand Steady") == "")
    check("New Launch (roas_prev=0) is Block 1", blocks.get("PMax - New Launch") == "Block 1")


def test_no_activity_row_present():
    print("test_no_activity_row_present")
    model = core.compute_model(core.load_findings(str(FIXTURE)))
    na = [r for r in model["rows"] if r["status"] == "no_activity"]
    check("one no_activity row kept", len(na) == 1, f"got {len(na)}")
    check("no_activity row has empty block", na and na[0]["block"] == "")
    check("no_activity row is the Dormant campaign", na and na[0]["campaign"] == "PMax - Dormant")


def test_empty_universe():
    print("test_empty_universe")
    model = core.compute_model({"meta": {}, "last_window": [], "prev_window": []})
    s = model["summary"]
    check("empty -> universe 0", s["universe"] == 0)
    check("empty -> block1/2 == 0", s["block1"] == 0 and s["block2"] == 0)
    check("empty -> sensitivity_up computed", len(model["sensitivity_up"]) == len(core.UP_LADDER))
    check("empty -> sensitivity_down computed", len(model["sensitivity_down"]) == len(core.DOWN_LADDER))


def test_dedupe_by_campaign():
    print("test_dedupe_by_campaign")
    # same campaign_id twice in a window (e.g. a device-segmented export) -> one merged row
    f = {"meta": {}, "last_window": [
            {"campaign_id": 9, "campaign": "Split", "impressions": 600, "clicks": 6, "cost": 30, "conversions": 3, "conversions_value": 300},
            {"campaign_id": 9, "campaign": "Split", "impressions": 400, "clicks": 4, "cost": 20, "conversions": 2, "conversions_value": 200}],
         "prev_window": []}
    model = core.compute_model(f)
    rows = model["rows"]
    check("duplicate campaign merged to one row", len(rows) == 1, f"got {len(rows)}")
    check("merged cost summed (50.0)", rows and abs(rows[0]["cost_last"] - 50.0) < 1e-6, f"got {rows[0]['cost_last'] if rows else None}")
    check("merged conv summed (5.0)", rows and abs(rows[0]["conv_last"] - 5.0) < 1e-6)
    check("merged ROAS recomputed (500/50=10)", rows and abs(rows[0]["roas_last"] - 10.0) < 1e-9, f"got {rows[0]['roas_last'] if rows else None}")


def test_zero_prev_roas():
    print("test_zero_prev_roas")
    # (a) brand-new campaign: no prior window at all, conv up, positive ROAS -> Block 1
    f = {"meta": {}, "last_window": [
            {"campaign_id": 1, "campaign": "New", "impressions": 1000, "clicks": 20, "cost": 80, "conversions": 4, "conversions_value": 400}],
         "prev_window": []}
    s = core.compute_model(f)["summary"]
    check("new launch (roas_prev=0) -> Block 1", s["block1"] == 1, f"got {s['block1']}")
    # (b) prior conversions but zero prior VALUE (roas_prev=0) and conv down -> NOT Block 2
    f2 = {"meta": {}, "last_window": [
            {"campaign_id": 1, "campaign": "Z", "impressions": 1000, "clicks": 20, "cost": 100, "conversions": 2, "conversions_value": 50}],
          "prev_window": [
            {"campaign_id": 1, "campaign": "Z", "impressions": 1200, "clicks": 24, "cost": 100, "conversions": 5, "conversions_value": 0}]}
    s2 = core.compute_model(f2)["summary"]
    check("roas_prev=0 can never be Block 2", s2["block2"] == 0, f"got {s2['block2']}")


def test_min_cost_floor():
    print("test_min_cost_floor")
    # a tiny-spend winner: conv up + ROAS up, but only $5 spent last window
    base = {"meta": {}, "last_window": [
                {"campaign_id": 1, "campaign": "Tiny", "impressions": 200, "clicks": 5, "cost": 5, "conversions": 3, "conversions_value": 90}],
            "prev_window": [
                {"campaign_id": 1, "campaign": "Tiny", "impressions": 180, "clicks": 4, "cost": 6, "conversions": 1, "conversions_value": 6}]}
    s0 = core.compute_model({**base, "params": {"min_cost": 0.0}})["summary"]
    check("min_cost=0 -> tiny winner counts (Block 1)", s0["block1"] == 1, f"got {s0['block1']}")
    s10 = core.compute_model({**base, "params": {"min_cost": 10.0}})["summary"]
    check("min_cost=10 -> tiny winner excluded", s10["block1"] == 0, f"got {s10['block1']}")


def test_sensitivity_shapes():
    print("test_sensitivity_shapes")
    model = core.compute_model(core.load_findings(str(FIXTURE)))
    su, sd = model["sensitivity_up"], model["sensitivity_down"]
    check("sensitivity_up row per ladder step", len(su) == len(core.UP_LADDER))
    check("sensitivity_down row per ladder step", len(sd) == len(core.DOWN_LADDER))
    check("exactly one up step flagged current", sum(1 for r in su if r["is_current"]) == 1)
    check("exactly one down step flagged current", sum(1 for r in sd if r["is_current"]) == 1)
    check("near_misses_block1 carry qualify_if_up_multiple_le",
          all("qualify_if_up_multiple_le" in r for r in model["near_misses_block1"]))


def test_assemble_findings_from_raw():
    print("test_assemble_findings_from_raw")
    import tempfile
    import assemble_findings as A
    raw_last = {"result": [
        {"campaign.id": 1, "campaign.name": "PMax A", "metrics.impressions": 600,
         "metrics.clicks": 6, "metrics.cost_micros": 30_000_000,
         "metrics.conversions": 3, "metrics.conversions_value": 300.0},
        # same campaign split across raw rows (e.g. by a segment) -> must merge
        {"campaign.id": 1, "campaign.name": "PMax A", "metrics.impressions": 400,
         "metrics.clicks": 4, "metrics.cost_micros": 20_000_000,
         "metrics.conversions": 2, "metrics.conversions_value": 200.0},
    ]}
    raw_prev = {"result": [
        {"campaign.id": 1, "campaign.name": "PMax A", "metrics.impressions": 900,
         "metrics.clicks": 9, "metrics.cost_micros": 45_000_000,
         "metrics.conversions": 1, "metrics.conversions_value": 50.0},
        {"campaign.id": 2, "campaign.name": "PMax B", "metrics.impressions": 100,
         "metrics.clicks": 1, "metrics.cost_micros": 5_000_000,
         "metrics.conversions": 0, "metrics.conversions_value": 0},
    ]}
    meta = {"client_name": "T", "account_id": "1", "currency": "CAD",
            "window_last": "wl", "window_prev": "wp", "generated": "2026-07-06"}
    with tempfile.TemporaryDirectory() as td:
        pl = Path(td) / "last.txt"; pl.write_text(json.dumps(raw_last))
        pp = Path(td) / "prev.txt"; pp.write_text(json.dumps(raw_prev))
        f = A.assemble(str(pl), str(pp), dict(meta))
        lw = f["last_window"]
        check("segment-split campaign merged into one row", len(lw) == 1, f"{len(lw)}")
        r = lw[0]
        check("window sums correct + micros converted",
              r["impressions"] == 1000 and r["clicks"] == 10 and abs(r["cost"] - 50.0) < 1e-9
              and r["conversions"] == 5 and r["conversions_value"] == 500.0)
        check("conversions_value passed through un-divided (not micros)",
              abs(f["prev_window"][0]["conversions_value"] - 50.0) < 1e-9)
        check("prev window kept separate (2 campaigns)", len(f["prev_window"]) == 2)
        rec = f["meta"]["reconciliation"]
        check("reconciliation embedded with raw stamps",
              rec["last_window"]["rows"] == 1 and rec["prev_window"]["rows"] == 2
              and len(rec.get("raw_files", [])) == 2)
        # the two windows drive the trend: conv 5 > 1 and ROAS 10 > 1.5 × 1.11 -> Block 1
        model = core.compute_model(f)
        blocks = {r["campaign"]: r["block"] for r in model["rows"]}
        check("assembled windows classify (PMax A is Block 1)",
              blocks.get("PMax A") == "Block 1", f"got {blocks}")
        # the assembled findings load clean through the core's verification...
        fp = Path(td) / "findings.json"; fp.write_text(json.dumps(f))
        core.load_findings(str(fp))
        check("assembled findings pass core verification", True)
        # ...and a hand-edit is a hard load failure
        f["last_window"][0]["cost"] += 500
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
    import pmax_spec as spec_mod
    from render import build_bundle
    from render import charts as C
    model = core.compute_model(core.load_findings(str(FIXTURE)))
    n = len(model["rows"])
    with tempfile.TemporaryDirectory() as td:
        written = build_bundle(model, dict(spec_mod.SPEC), td, formats=("md", "html"))
        md = next(Path(td).glob("*.md")).read_text()
        html = next(Path(td).glob("*_explorer.html")).read_text()
        svgs = sorted(p.name for p in written if p.suffix == ".svg")
    rows_blk = md.split("## All Performance Max campaigns")[1].splitlines()
    md_rows = [ln for ln in rows_blk if ln.startswith("| ") and not ln.startswith("| Campaign")]
    embedded = json.loads(re.search(r"^const MODEL = (.+);$", html, re.M).group(1))
    html_rows = len(embedded["rows"])
    check("md row table has every campaign", len(md_rows) == n, f"{len(md_rows)} vs {n}")
    check("html embeds every campaign", html_rows == n, f"{html_rows} vs {n}")
    # self-containment: the only opaque region allowed is the vendored chart
    # runtime, and only byte-equal to the committed, checksummed vendor files.
    blob = C.vendor_blob()
    check("explorer embeds the verified vendor runtime", blob in html)
    stripped = html.replace(blob, "")
    check("html is self-contained outside the verified vendor blob",
          len(re.findall(r"https?://|<link|src=|cdn", stripped)) == 0)
    # declared charts render as static SVGs and are referenced from the md
    check("both chart svgs written", svgs == ["roas_spend_scatter.svg", "spend_by_signal.svg"], svgs)
    check("md has a Charts section", "## Charts" in md)
    check("md references charts relatively", "_charts/spend_by_signal.svg)" in md)
    check("explorer embeds the chart specs", "const CHARTS = " in html)
    check("pipe in campaign name escaped in md", "PMax \\| Shopping" in md)
    check("building md/html did not import openpyxl", "openpyxl" not in sys.modules)


def test_asset_group_concentration():
    print("test_asset_group_concentration")
    model = core.compute_model(core.load_findings(str(FIXTURE)))
    by_campaign = {r["campaign"]: r for r in model["asset_group_concentration"]}
    check("both campaigns with an asset-group breakdown appear",
          set(by_campaign) == {"PMax | Shopping - Core", "PMax - Brand Steady"}, str(sorted(by_campaign)))

    core_row = by_campaign["PMax | Shopping - Core"]  # 450/40/10 of 500
    check("Shopping-Core n / n_nonzero", core_row["asset_groups"] == 3 and core_row["asset_groups_active"] == 3)
    check("Shopping-Core total cost", abs(core_row["cost"] - 500.0) < 1e-6, str(core_row["cost"]))
    check("Shopping-Core top share (450/500=0.90)", abs(core_row["top_share"] - 0.90) < 1e-9, str(core_row["top_share"]))
    check("Shopping-Core hhi (8168.0)", abs(core_row["hhi"] - 8168.0) < 1e-6, str(core_row["hhi"]))
    check("Shopping-Core effective_n (1.22)", abs(core_row["effective_n"] - 1.22) < 1e-6, str(core_row["effective_n"]))
    check("Shopping-Core flagged concentration_risk (0.90 >= 0.80 default)", core_row["risk"] is True)
    check("Shopping-Core carries the concentration_risk flag id", "concentration_risk" in core_row["flags"])

    steady_row = by_campaign["PMax - Brand Steady"]  # 160/140 of 300
    check("Brand-Steady top share (160/300=0.5333)", abs(steady_row["top_share"] - 0.5333) < 1e-4, str(steady_row["top_share"]))
    check("Brand-Steady NOT flagged (below 0.80 default)", steady_row["risk"] is False)

    # a campaign with only ONE active asset group is never a concentration risk
    # even though its top share is trivially 1.0 (nothing to diversify against).
    single = core.asset_group_concentration(
        [{"campaign_id": 9, "campaign": "Solo", "asset_group_id": 1, "asset_group": "Only", "cost": 100}],
        core.resolve_params(None))
    check("single-asset-group campaign never flags", single[0]["top_share"] == 1.0 and single[0]["risk"] is False,
          str(single[0]))

    # tuning the threshold above 0.90 clears the Shopping-Core flag
    loose = core.asset_group_concentration(
        core.load_findings(str(FIXTURE))["asset_groups"],
        core.resolve_params({"concentration_top_share_threshold": 0.95}))
    check("raising the threshold above top_share clears the flag",
          all(not r["risk"] for r in loose), str(loose))

    # no asset-group breakdown at all -> empty list, not an error
    check("no asset_groups array -> empty list, no crash",
          core.asset_group_concentration([], core.resolve_params(None)) == [])


def test_cannibalization_signal():
    print("test_cannibalization_signal")
    findings = core.load_findings(str(FIXTURE))
    model = core.compute_model(findings)
    by_campaign = {r["campaign"]: r for r in model["cannibalization"]}
    check("only the theme-matched PMax campaign appears (decoy Search campaign excluded)",
          set(by_campaign) == {"PMax - Prospecting"}, str(sorted(by_campaign)))

    row = by_campaign["PMax - Prospecting"]
    check("matched exactly the theme-overlapping Search campaign",
          row["matched_search_campaigns"] == ["Search - Prospecting - NonBrand"], str(row["matched_search_campaigns"]))
    check("pmax_cost_last == 400.0", abs(row["pmax_cost_last"] - 400.0) < 1e-6, str(row["pmax_cost_last"]))
    check("search_cost_last == 200.0", abs(row["search_cost_last"] - 200.0) < 1e-6, str(row["search_cost_last"]))
    check("pmax_theme_share (400/600=0.6667)", abs(row["pmax_theme_share"] - 0.6667) < 1e-4, str(row["pmax_theme_share"]))
    check("flagged cannibalization_risk (0.6667 >= 0.60 default)", row["risk"] is True)
    check("carries the cannibalization_risk flag id", "cannibalization_risk" in row["flags"])

    # a Search campaign with NO shared theme token never pairs with anything
    tokens_widgets = core._theme_tokens("Search - Widgets Generic")
    tokens_shopping_core = core._theme_tokens("PMax | Shopping - Core")
    check("decoy Search campaign shares no theme token with Shopping-Core",
          not (tokens_widgets & tokens_shopping_core), str((tokens_widgets, tokens_shopping_core)))

    # tuning the share threshold above 0.6667 clears the flag; the min_cost floor
    # above the combined spend (600) also clears it
    loose = core.cannibalization(model["rows"], findings["search_campaigns"],
                                 core.resolve_params({"cannibalization_share_threshold": 0.90}))
    check("raising the share threshold clears the flag", all(not r["risk"] for r in loose), str(loose))
    floored = core.cannibalization(model["rows"], findings["search_campaigns"],
                                   core.resolve_params({"cannibalization_min_cost": 1000.0}))
    check("raising the min-cost floor above combined spend clears the flag",
          all(not r["risk"] for r in floored), str(floored))

    # no Search campaigns at all -> empty list, not an error
    check("no search_campaigns array -> empty list, no crash",
          core.cannibalization(model["rows"], [], core.resolve_params(None)) == [])
    # a no_activity (dormant) PMax campaign is never a cannibalization candidate
    dormant_rows = [r for r in model["rows"] if r["status"] != "scored"]
    check("dormant rows never enter cannibalization pairing",
          not any(r["campaign_id"] in {d["campaign_id"] for d in dormant_rows}
                  for r in model["cannibalization"]))


def test_recommendations():
    print("test_recommendations")
    model = core.compute_model(core.load_findings(str(FIXTURE)))
    recs = core.recommendations(model)
    check("exactly 2 recommendations on the fixture", len(recs) == 2, f"got {len(recs)}")
    check("severities are High then Medium (Critical -> High -> Medium order)",
          [r["severity"] for r in recs] == ["High", "Medium"], str([r["severity"] for r in recs]))
    high = recs[0]
    check("High recommendation names the concentrated campaign",
          "PMax | Shopping - Core" in high["title"], high["title"])
    check("High recommendation cites the model's top-share number (90%)", "90%" in high["detail"], high["detail"])
    med = recs[1]
    check("Medium recommendation names the cannibalized campaign",
          "PMax - Prospecting" in med["title"], med["title"])
    check("Medium recommendation cites the matched Search campaign",
          "Search - Prospecting - NonBrand" in med["detail"], med["detail"])
    check("every recommendation names an artifact", all(r["artifact"] for r in recs))

    # a model with nothing flagged -> no recommendations (0/0-is-clean posture)
    clean_model = core.compute_model({"meta": {}, "last_window": [], "prev_window": []})
    check("no risk flags -> empty recommendations", core.recommendations(clean_model) == [])


def test_csv_matches_mcp():
    print("test_csv_matches_mcp")
    import tempfile
    import assemble_findings as AF
    import assemble_findings_csv as ACSV

    raw_last = {"result": [
        {"campaign.id": 1, "campaign.name": "PMax | Shopping - Core", "metrics.impressions": 10000,
         "metrics.clicks": 300, "metrics.cost_micros": 500_000_000,
         "metrics.conversions": 50, "metrics.conversions_value": 5000.0},
        {"campaign.id": 2, "campaign.name": "PMax - Prospecting", "metrics.impressions": 5000,
         "metrics.clicks": 100, "metrics.cost_micros": 400_000_000,
         "metrics.conversions": 10, "metrics.conversions_value": 200.0},
    ]}
    raw_prev = {"result": [
        {"campaign.id": 1, "campaign.name": "PMax | Shopping - Core", "metrics.impressions": 8000,
         "metrics.clicks": 250, "metrics.cost_micros": 480_000_000,
         "metrics.conversions": 30, "metrics.conversions_value": 1440.0},
        {"campaign.id": 2, "campaign.name": "PMax - Prospecting", "metrics.impressions": 6000,
         "metrics.clicks": 120, "metrics.cost_micros": 420_000_000,
         "metrics.conversions": 40, "metrics.conversions_value": 1680.0},
    ]}
    raw_ag = {"result": [
        {"campaign.id": 1, "campaign.name": "PMax | Shopping - Core", "asset_group.id": 101,
         "asset_group.name": "Core Products", "metrics.impressions": 9000, "metrics.clicks": 270,
         "metrics.cost_micros": 450_000_000, "metrics.conversions": 45, "metrics.conversions_value": 4500.0},
        {"campaign.id": 1, "campaign.name": "PMax | Shopping - Core", "asset_group.id": 102,
         "asset_group.name": "Seasonal", "metrics.impressions": 1000, "metrics.clicks": 30,
         "metrics.cost_micros": 50_000_000, "metrics.conversions": 5, "metrics.conversions_value": 500.0},
    ]}
    raw_search = {"result": [
        {"campaign.id": 21, "campaign.name": "Search - Prospecting - NonBrand", "metrics.impressions": 4000,
         "metrics.clicks": 80, "metrics.cost_micros": 200_000_000, "metrics.conversions": 3,
         "metrics.conversions_value": 150.0},
    ]}

    csv_last = ("Campaign ID,Campaign,Impr.,Clicks,Cost,Conversions,Conv. value\n"
               "1,PMax | Shopping - Core,10000,300,500.00,50,5000\n"
               "2,PMax - Prospecting,5000,100,400.00,10,200\n")
    csv_prev = ("Campaign ID,Campaign,Impr.,Clicks,Cost,Conversions,Conv. value\n"
               "1,PMax | Shopping - Core,8000,250,480.00,30,1440\n"
               "2,PMax - Prospecting,6000,120,420.00,40,1680\n")
    csv_ag = ("Campaign ID,Campaign,Asset group ID,Asset group,Impr.,Clicks,Cost,Conversions,Conv. value\n"
             "1,PMax | Shopping - Core,101,Core Products,9000,270,450.00,45,4500\n"
             "1,PMax | Shopping - Core,102,Seasonal,1000,30,50.00,5,500\n")
    csv_search = ("Campaign ID,Campaign,Impr.,Clicks,Cost,Conversions,Conv. value\n"
                 "21,Search - Prospecting - NonBrand,4000,80,200.00,3,150\n")

    meta = {"client_name": "Acme Corp", "account_id": "123-456-7890", "currency": "CAD",
            "window_last": "2026-06-22 to 2026-07-05", "window_prev": "2026-06-08 to 2026-06-21",
            "generated": "2026-07-06"}

    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        (p / "last.txt").write_text(json.dumps(raw_last))
        (p / "prev.txt").write_text(json.dumps(raw_prev))
        (p / "ag.txt").write_text(json.dumps(raw_ag))
        (p / "search.txt").write_text(json.dumps(raw_search))
        mcp_findings = AF.assemble(str(p / "last.txt"), str(p / "prev.txt"), dict(meta),
                                   asset_groups_path=str(p / "ag.txt"),
                                   search_campaigns_path=str(p / "search.txt"))

        (p / "last.csv").write_text(csv_last)
        (p / "prev.csv").write_text(csv_prev)
        (p / "ag.csv").write_text(csv_ag)
        (p / "search.csv").write_text(csv_search)
        csv_findings = ACSV.assemble(last_csv=str(p / "last.csv"), prev_csv=str(p / "prev.csv"),
                                     meta=dict(meta), asset_groups_csv=str(p / "ag.csv"),
                                     search_csv=str(p / "search.csv"))

        (p / "mcp_findings.json").write_text(json.dumps(mcp_findings))
        (p / "csv_findings.json").write_text(json.dumps(csv_findings))
        mcp_loaded = core.load_findings(str(p / "mcp_findings.json"))
        csv_loaded = core.load_findings(str(p / "csv_findings.json"))
        check("mcp findings load clean (reconciliation verified)", True)
        check("csv findings load clean (reconciliation verified)", True)

        check("csv meta.source == user_csv, mcp meta.source unset (defaults to mcp)",
              csv_loaded["meta"]["source"] == "user_csv" and "source" not in mcp_loaded["meta"])

        mcp_model = core.compute_model(mcp_loaded)
        csv_model = core.compute_model(csv_loaded)

        # provenance.source is EXPECTED to differ (that's the honesty contract) —
        # strip it before the identical-model assertion.
        mcp_prov = dict(mcp_model["provenance"]); mcp_prov.pop("source", None)
        csv_prov = dict(csv_model["provenance"]); csv_prov.pop("source", None)
        check("provenance identical apart from source", mcp_prov == csv_prov,
              f"mcp={mcp_prov!r} csv={csv_prov!r}")
        check("rows identical", mcp_model["rows"] == csv_model["rows"])
        check("summary identical", mcp_model["summary"] == csv_model["summary"])
        check("asset_group_concentration identical",
              mcp_model["asset_group_concentration"] == csv_model["asset_group_concentration"])
        check("cannibalization identical", mcp_model["cannibalization"] == csv_model["cannibalization"])
        check("recommendations identical", mcp_model["recommendations"] == csv_model["recommendations"])
        check("MCP path source defaults honestly to 'mcp'", mcp_model["provenance"]["source"] == "mcp")
        check("CSV path source honestly labelled 'user_csv'", csv_model["provenance"]["source"] == "user_csv")


def main():
    for t in (test_fixture_counts, test_no_activity_row_present, test_empty_universe,
              test_dedupe_by_campaign, test_zero_prev_roas, test_min_cost_floor,
              test_sensitivity_shapes, test_assemble_findings_from_raw,
              test_asset_group_concentration, test_cannibalization_signal,
              test_recommendations, test_csv_matches_mcp,
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
