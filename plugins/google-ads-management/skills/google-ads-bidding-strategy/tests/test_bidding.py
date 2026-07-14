#!/usr/bin/env python3
"""Tests for the bidding-strategy Data Maturity Score core (stdlib only; run directly).

    python3 tests/test_bidding.py

Asserts the documented fixture result, no-row-loss, dedupe, the empty-universe
edge, the automation-gate priority rule, MCP-vs-CSV identical-model parity,
and the bundle md/html parity + lazy-import invariants. Exit 0 = all pass,
1 = a failure.
"""
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE.parents[2] / "_shared"))  # the shared render toolkit

import bidding_core as core  # noqa: E402

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
    check("universe == 7 (no rows dropped)", s["universe"] == 7, f"got {s['universe']}")
    check("scored == 5", s["scored"] == 5, f"got {s['scored']}")
    check("no_spend == 1", s["no_spend"] == 1, f"got {s['no_spend']}")
    check("unsupported_strategy == 1", s["unsupported_strategy"] == 1, f"got {s['unsupported_strategy']}")
    check("over_automated_under_data == 1", s["over_automated_under_data"] == 1)
    check("over_automated == 1", s["over_automated"] == 1)
    check("under_automated == 1", s["under_automated"] == 1)
    check("aligned == 2", s["aligned"] == 2)
    check("total_mismatched == 3", s["total_mismatched"] == 3)
    check("avg_maturity_score == 58.0", abs(s["avg_maturity_score"] - 58.0) < 1e-6, f"got {s['avg_maturity_score']}")
    check("critical_spend == 900.0", abs(s["critical_spend"] - 900.0) < 1e-6)
    n_input = len(core.load_findings(str(FIXTURE))["campaigns"])
    check("rows preserved == input campaigns", len(model["rows"]) == n_input,
          f"{len(model['rows'])} vs {n_input}")


def test_specific_rows():
    print("test_specific_rows")
    model = core.compute_model(core.load_findings(str(FIXTURE)))
    by_id = {r["campaign_id"]: r for r in model["rows"]}
    r1 = by_id["1001"]
    check("1001 maturity == 94.0", abs(r1["maturity_score"] - 94.0) < 1e-6, f"got {r1['maturity_score']}")
    check("1001 Under-automated", r1["mismatch"] == "Under-automated")
    check("1001 confidence measured", r1["confidence"] == "measured")
    r4 = by_id["1004"]
    check("1004 Over-automated (under-data) — priority over plain gap",
          r4["mismatch"] == "Over-automated (under-data)")
    check("1004 confidence assumed (no judgment supplied)", r4["confidence"] == "assumed")
    r7 = by_id["1007"]
    check("1007 under_data true but NOT flagged (Manual CPC, tier 0 — not automated)",
          r7["under_data"] is True and r7["mismatch"] == "")
    check("1007 confidence partial (only value_score supplied)", r7["confidence"] == "partial")
    r6 = by_id["1006"]
    check("1006 unsupported_strategy held out, not classified",
          r6["status"] == "unsupported_strategy" and r6["mismatch"] == "" and r6["maturity_score"] is None)
    r5 = by_id["1005"]
    check("1005 no_spend held out, not classified",
          r5["status"] == "no_spend" and r5["maturity_score"] is None)


def test_empty_universe():
    print("test_empty_universe")
    f = {"meta": {}, "campaigns": []}
    model = core.compute_model(f)
    s = model["summary"]
    check("empty -> universe 0", s["universe"] == 0)
    check("empty -> all mismatch counts 0",
          s["over_automated_under_data"] == 0 and s["over_automated"] == 0 and s["under_automated"] == 0)
    check("empty -> gate_sensitivity computed without crash",
          len(model["gate_sensitivity"]) == len(core.GATE_LADDER))
    check("empty -> borderline is empty list", model["borderline"] == [])


def test_dedupe_by_campaign_id():
    print("test_dedupe_by_campaign_id")
    f = {"meta": {}, "campaigns": [
        {"campaign_id": "1", "campaign": "X", "bidding_strategy_type": "MANUAL_CPC",
         "conv30": 10, "cost": 100.0, "value": 0.0},
        {"campaign_id": "1", "campaign": "X", "bidding_strategy_type": "MANUAL_CPC",
         "conv30": 5, "cost": 50.0, "value": 0.0},
    ]}
    model = core.compute_model(f)
    rows = model["rows"]
    check("duplicate campaign_id merged to one row", len(rows) == 1, f"got {len(rows)}")
    check("merged cost summed (150.0)", rows and abs(rows[0]["cost"] - 150.0) < 1e-6)
    check("merged conv30 summed (15.0)", rows and abs(rows[0]["conv30"] - 15.0) < 1e-6)


def test_automation_gate_priority():
    print("test_automation_gate_priority")
    # under-data + automated -> Critical, even when the plain tier-gap alone
    # would not have crossed tier_gap_threshold.
    f = {"meta": {}, "campaigns": [
        {"campaign_id": "1", "campaign": "X", "bidding_strategy_type": "ENHANCED_CPC",
         "conv30": 5, "cost": 200.0, "value": 0.0},
    ]}
    model = core.compute_model(f)
    r = model["rows"][0]
    check("under-data automated campaign flagged Critical",
          r["mismatch"] == "Over-automated (under-data)", r["mismatch"])
    # same campaign but on Manual CPC (tier 0, not automated) -> never Critical
    f["campaigns"][0]["bidding_strategy_type"] = "MANUAL_CPC"
    model2 = core.compute_model(f)
    r2 = model2["rows"][0]
    check("under-data but NOT automated -> not flagged", r2["mismatch"] == "", r2["mismatch"])


def test_strategy_normalization_mcp_and_ui_labels():
    print("test_strategy_normalization_mcp_and_ui_labels")
    check("GAQL enum normalizes", core.normalize_strategy("TARGET_CPA") == "TARGET_CPA")
    check("UI export label normalizes to the same token",
          core.normalize_strategy("Target CPA") == "TARGET_CPA")
    check("both map to the same tier",
          core.STRATEGY_TIERS[core.normalize_strategy("TARGET_CPA")]
          == core.STRATEGY_TIERS[core.normalize_strategy("Target CPA")] == 2)
    check("unrecognized strategy -> None (unsupported)",
          core.strategy_tier(core.normalize_strategy("Portfolio Bidding Strategy"), False) is None)
    check("Target ROAS + ai_max -> tier 4",
          core.strategy_tier("TARGET_ROAS", True) == 4)
    check("Target ROAS without ai_max -> tier 3",
          core.strategy_tier("TARGET_ROAS", False) == 3)


def test_gate_sensitivity_and_borderline_shapes():
    print("test_gate_sensitivity_and_borderline_shapes")
    model = core.compute_model(core.load_findings(str(FIXTURE)))
    sens = model["gate_sensitivity"]
    check("gate_sensitivity has a row per ladder step", len(sens) == len(core.GATE_LADDER))
    check("exactly one gate_sensitivity row flagged current", sum(1 for r in sens if r["is_current"]) == 1)
    check("gate_sensitivity counts never exceed scored campaigns",
          all(r["over_automated_under_data"] <= model["summary"]["scored"] for r in sens))
    # a wide-open gate (conv_gate == the ladder max) can only ever flag as many
    # or more under-data campaigns than the current (narrower) gate — monotonic.
    by_gate = {r["conv_gate"]: r["over_automated_under_data"] for r in sens}
    widest, current = max(by_gate), model["params"]["conv_gate"]
    check("widening the gate never REDUCES the under-data flag count",
          by_gate[widest] >= by_gate.get(current, 0))

    bl = model["borderline"]
    n_scored = model["summary"]["scored"]
    check("borderline has one entry per scored campaign", len(bl) == n_scored, f"{len(bl)} vs {n_scored}")
    check("borderline sorted ascending by distance-to-edge",
          all(bl[i]["distance_to_edge"] <= bl[i + 1]["distance_to_edge"] for i in range(len(bl) - 1)))
    check("borderline entries carry distance_to_edge", all("distance_to_edge" in r for r in bl))
    check("borderline top_n respected", len(core.borderline(model["rows"], model["params"], top_n=2)) == 2)


def test_mcp_vs_csv_identical_model():
    print("test_mcp_vs_csv_identical_model")
    import assemble_findings as A
    meta = {"client_name": "Acme Corp", "account_id": "123-456-7890", "currency": "CAD",
            "window_30d": "2026-06-06 to 2026-07-05", "generated": "2026-07-12"}
    raw = {"result": [
        {"campaign.id": 501, "campaign.name": "Brand", "campaign.bidding_strategy_type": "TARGET_CPA",
         "metrics.conversions": 45.0, "metrics.cost_micros": 900_000_000, "metrics.conversions_value": 0.0},
        {"campaign.id": 502, "campaign.name": "Generic", "campaign.bidding_strategy_type": "MANUAL_CPC",
         "metrics.conversions": 3.0, "metrics.cost_micros": 40_000_000, "metrics.conversions_value": 0.0},
    ]}
    ui_csv = ("Campaign,Campaign ID,Bid strategy type,Conversions,Cost\n"
              "Brand,501,Target CPA,45,900.00\n"
              "Generic,502,Manual CPC,3,40.00\n")
    with tempfile.TemporaryDirectory() as td:
        raw_path = Path(td) / "campaigns_raw.txt"
        raw_path.write_text(json.dumps(raw))
        mcp_findings = A.assemble_mcp(str(raw_path), dict(meta), {})

        csv_path = Path(td) / "export.csv"
        csv_path.write_text(ui_csv)
        csv_findings = A.assemble_csv(str(csv_path), dict(meta), {})

        check("same top-level keys", sorted(mcp_findings) == sorted(csv_findings))
        check("mcp source labeled 'mcp'", mcp_findings["meta"]["source"] == "mcp")
        check("csv source labeled 'user_csv'", csv_findings["meta"]["source"] == "user_csv")

        mcp_model = core.compute_model(mcp_findings)
        csv_model = core.compute_model(csv_findings)

        # "bidding_strategy" is intentionally excluded from the equality check: the
        # GAQL enum ("TARGET_CPA") and the Google Ads UI export label ("Target CPA")
        # are different verbatim strings by design — normalize_strategy() is what
        # makes them equivalent, and "bidding_strategy_norm" (compared below) proves
        # it. Every DERIVED/classified field (status, tiers, maturity, mismatch,
        # confidence, and the raw metric values) must still be byte-identical.
        def _classified(row):
            return {k: v for k, v in row.items() if k != "bidding_strategy"}

        check("identical row count", len(mcp_model["rows"]) == len(csv_model["rows"]) == 2)
        for m_row, c_row in zip(sorted(mcp_model["rows"], key=lambda r: r["campaign_id"]),
                                sorted(csv_model["rows"], key=lambda r: r["campaign_id"])):
            check(f"row {m_row['campaign_id']} identical across MCP/CSV (modulo the raw "
                  "strategy-label spelling)", _classified(m_row) == _classified(c_row),
                  f"mcp={m_row!r} csv={c_row!r}")
        check("identical summary", mcp_model["summary"] == csv_model["summary"],
              f"mcp={mcp_model['summary']!r} csv={csv_model['summary']!r}")
        # findings pass the same reconciliation verification on both paths
        mcp_path = Path(td) / "mcp.json"; mcp_path.write_text(json.dumps(mcp_findings))
        csv_findings_path = Path(td) / "csv.json"; csv_findings_path.write_text(json.dumps(csv_findings))
        core.load_findings(str(mcp_path))
        core.load_findings(str(csv_findings_path))
        check("both findings pass core.load_findings verification", True)


def test_assemble_findings_from_raw_and_judgment():
    print("test_assemble_findings_from_raw_and_judgment")
    import assemble_findings as A
    raw = {"result": [
        # same campaign split across two raw rows (e.g. by a segment) -> must merge
        {"campaign.id": 9, "campaign.name": "Split", "campaign.bidding_strategy_type": "TARGET_ROAS",
         "campaign.ai_max_setting.enable_ai_max": True,
         "metrics.conversions": 20.0, "metrics.cost_micros": 300_000_000, "metrics.conversions_value": 900.0},
        {"campaign.id": 9, "campaign.name": "Split", "campaign.bidding_strategy_type": "TARGET_ROAS",
         "metrics.conversions": 10.0, "metrics.cost_micros": 100_000_000, "metrics.conversions_value": 100.0},
    ]}
    meta = {"client_name": "T", "account_id": "1", "currency": "CAD",
            "window_30d": "w30", "generated": "2026-07-12"}
    with tempfile.TemporaryDirectory() as td:
        raw_path = Path(td) / "c.txt"; raw_path.write_text(json.dumps(raw))
        judgment_path = Path(td) / "j.json"
        judgment_path.write_text(json.dumps({"9": {"value_variance_score": 80, "tracking_confidence_score": 75}}))
        judgment = A._load_judgment(str(judgment_path))
        f = A.assemble_mcp(str(raw_path), dict(meta), judgment)
        camps = f["campaigns"]
        check("split campaign_id merged into one findings row", len(camps) == 1, f"{len(camps)}")
        c = camps[0]
        check("merged sums correct",
              abs(c["conv30"] - 30.0) < 1e-9 and abs(c["cost"] - 400.0) < 1e-9
              and abs(c["value"] - 1000.0) < 1e-9)
        check("judgment overlay applied", c["value_score"] == 80 and c["tracking_score"] == 75)
        rec = f["meta"]["reconciliation"]
        check("reconciliation embedded with raw stamp",
              rec["campaigns"]["rows"] == 1 and len(rec.get("raw_files", [])) == 1)
        fp = Path(td) / "findings.json"; fp.write_text(json.dumps(f))
        core.load_findings(str(fp))
        check("assembled findings pass core verification", True)
        # a hand-edit is a hard load failure
        f["campaigns"][0]["cost"] += 500
        fp.write_text(json.dumps(f))
        try:
            core.load_findings(str(fp)); ok = False
        except core.FindingsError:
            ok = True
        check("hand-edited findings rejected by core", ok)


def test_bundle_md_html_parity_and_lazy():
    print("test_bundle_md_html_parity_and_lazy")
    import re
    import bidding_spec as spec_mod
    from render import build_bundle
    from render import charts as C
    model = core.compute_model(core.load_findings(str(FIXTURE)))
    n = len(model["rows"])
    with tempfile.TemporaryDirectory() as td:
        written = build_bundle(model, dict(spec_mod.SPEC), td, formats=("md", "html"))
        md = next(Path(td).glob("*.md")).read_text()
        html = next(Path(td).glob("*_explorer.html")).read_text()
        svgs = sorted(p.name for p in written if p.suffix == ".svg")
    rows_blk = md.split("## All campaigns")[1].splitlines()
    md_rows = [ln for ln in rows_blk if ln.startswith("| ") and not ln.startswith("| Campaign")]
    embedded = json.loads(re.search(r"^const MODEL = (.+);$", html, re.M).group(1))
    html_rows = len(embedded["rows"])
    check("md row table has every campaign", len(md_rows) == n, f"{len(md_rows)} vs {n}")
    # build_bundle's standalone explorer always embeds the FULL model — the
    # in_play envelope only trims the --emit-widget tuner embed (see
    # widget_emit.emit_widget), not this html.
    check("html embeds every campaign (standalone explorer is untrimmed)", html_rows == n,
          f"{html_rows} vs {n}")
    blob = C.vendor_blob()
    check("explorer embeds the verified vendor runtime", blob in html)
    stripped = html.replace(blob, "")
    check("html is self-contained outside the verified vendor blob",
          len(re.findall(r"https?://|<link|src=|cdn", stripped)) == 0)
    check("both chart svgs written",
          svgs == sorted(["maturity_vs_conv30.svg", "mismatch_by_category.svg"]), svgs)
    check("md has a Charts section", "## Charts" in md)
    check("explorer embeds the chart specs", "const CHARTS = " in html)
    check("building md/html did not import openpyxl", "openpyxl" not in sys.modules)


def main():
    for t in (test_fixture_counts, test_specific_rows, test_empty_universe,
              test_dedupe_by_campaign_id, test_automation_gate_priority,
              test_strategy_normalization_mcp_and_ui_labels,
              test_gate_sensitivity_and_borderline_shapes,
              test_mcp_vs_csv_identical_model, test_assemble_findings_from_raw_and_judgment,
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
