#!/usr/bin/env python3
"""Tests for the conversions & tracking advisor core (stdlib only; run directly).

    python3 tests/test_conv_tracking.py

Asserts the documented fixture result, no-row-loss across BOTH datasets, the
honesty posture of the manual EC/Consent-Mode rows, MCP-vs-CSV parity, and the
md/html bundle contract. Exit 0 = all pass, 1 = a failure.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE.parents[2] / "_shared"))  # the shared render toolkit

import conv_tracking_core as core  # noqa: E402

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
    check("campaigns == 6", s["campaigns"] == 6, f"got {s['campaigns']}")
    check("scored == 5", s["scored"] == 5, f"got {s['scored']}")
    check("no_benchmark == 1", s["no_benchmark"] == 1, f"got {s['no_benchmark']}")
    check("critical == 1", s["critical"] == 1, f"got {s['critical']}")
    check("high == 1", s["high"] == 1, f"got {s['high']}")
    check("watch == 2", s["watch"] == 2, f"got {s['watch']}")
    check("clean == 1", s["clean"] == 1, f"got {s['clean']}")
    check("landing_page_suspect == 1", s["landing_page_suspect"] == 1, f"got {s['landing_page_suspect']}")
    check("config_actions == 6", s["config_actions"] == 6, f"got {s['config_actions']}")
    check("config_flagged == 4", s["config_flagged"] == 4, f"got {s['config_flagged']}")
    check("config_no_primary_action is False", s["config_no_primary_action"] is False)
    check("manual_checks == 2", s["manual_checks"] == 2, f"got {s['manual_checks']}")
    check("manual_user_confirmed == 2", s["manual_user_confirmed"] == 2, f"got {s['manual_user_confirmed']}")


def test_no_row_loss_both_datasets():
    print("test_no_row_loss_both_datasets")
    findings = core.load_findings(str(FIXTURE))
    model = core.compute_model(findings)
    check("trend rows preserved (model['rows'])",
          len(model["rows"]) == len(findings["campaign_trend"]),
          f"{len(model['rows'])} vs {len(findings['campaign_trend'])}")
    check("config rows preserved (model['config_rows'])",
          len(model["config_rows"]) == len(findings["conversion_actions"]),
          f"{len(model['config_rows'])} vs {len(findings['conversion_actions'])}")
    check("manual rows preserved (model['manual_rows'])",
          len(model["manual_rows"]) == len(findings["manual_checks"]),
          f"{len(model['manual_rows'])} vs {len(findings['manual_checks'])}")
    check("every trend row carries a status", all("status" in r for r in model["rows"]))
    check("every config row carries status='config'",
          all(r["status"] == "config" for r in model["config_rows"]))
    check("every manual row carries status='manual'",
          all(r["status"] == "manual" for r in model["manual_rows"]))


def test_config_health_flags():
    print("test_config_health_flags")
    model = core.compute_model(core.load_findings(str(FIXTURE)))
    by_id = {r["id"]: r for r in model["config_rows"]}
    check("action 1 (Purchase) passes clean", by_id[1]["verdict"] == "pass", by_id[1]["flags"])
    check("action 2 (dormant + every + legacy + dup) flags all four",
          set(by_id[2]["flags"]) == {"dormant_primary", "every_counting_lead",
                                     "legacy_attribution", "duplicate_primary_category"},
          by_id[2]["flags"])
    check("action 3 flags duplicate_primary_category only", by_id[3]["flags"] == ["duplicate_primary_category"],
          by_id[3]["flags"])
    check("action 4 (non-primary lead, Every-counting) flags every_counting_lead",
          by_id[4]["flags"] == ["every_counting_lead"], by_id[4]["flags"])
    check("action 5 (Page View) passes clean", by_id[5]["verdict"] == "pass", by_id[5]["flags"])
    check("action 6 (legacy linear attribution) flags legacy_attribution",
          by_id[6]["flags"] == ["legacy_attribution"], by_id[6]["flags"])


def test_manual_checks_honesty():
    print("test_manual_checks_honesty")
    model = core.compute_model(core.load_findings(str(FIXTURE)))
    check("manual rows never claim an MCP/API source",
          all(r["data_source"] in ("user_csv", "not_confirmed") for r in model["manual_rows"]))
    # a findings dict with NO manual_checks rows still yields the honest default
    # when built via the assembler (covered in test_assemble_findings_from_raw);
    # here just assert the fixture's CSV-sourced rows are labelled correctly.
    check("fixture manual rows are user_csv", all(r["data_source"] == "user_csv" for r in model["manual_rows"]))


def test_no_benchmark_row_present():
    print("test_no_benchmark_row_present")
    model = core.compute_model(core.load_findings(str(FIXTURE)))
    nb = [r for r in model["rows"] if r["status"] == "no_benchmark"]
    check("exactly one no_benchmark row", len(nb) == 1, f"got {len(nb)}")
    check("no_benchmark row has empty tier", nb and nb[0]["tier"] == "")
    check("no_benchmark row can still carry non-relative flags (thin_volume)",
          nb and "thin_volume" in nb[0]["flags"], nb[0]["flags"] if nb else None)
    check("no_benchmark row never fires a relative (prior-window) flag",
          nb and "cvr_drop" not in nb[0]["flags"] and "ctr_held_or_up" not in nb[0]["flags"])


def test_empty_universe():
    print("test_empty_universe")
    f = {"meta": {}, "conversion_actions": [], "manual_checks": [], "campaign_trend": []}
    model = core.compute_model(f)
    s = model["summary"]
    check("empty -> campaigns 0", s["campaigns"] == 0)
    check("empty -> config_actions 0", s["config_actions"] == 0)
    check("empty -> manual_checks 0", s["manual_checks"] == 0)
    check("empty -> sensitivity computed without crash", len(model["sensitivity"]) == len(core.DROP_LADDER))
    check("empty -> no_primary_action True (vacuously)", s["config_no_primary_action"] is True)


def test_assemble_findings_from_raw():
    print("test_assemble_findings_from_raw")
    import tempfile
    import assemble_findings as A
    config_raw = {"result": [
        {"conversion_action.id": 1, "conversion_action.name": "Purchase", "conversion_action.status": "ENABLED",
         "conversion_action.type": "PURCHASE", "conversion_action.category": "PURCHASE",
         "conversion_action.primary_for_goal": True, "conversion_action.counting_type": "ONE_PER_CLICK",
         "conversion_action.attribution_model_settings.attribution_model": "GOOGLE_SEARCH_ATTRIBUTION_DATA_DRIVEN",
         "metrics.conversions": 40},
        # same id split across two raw rows (e.g. by a segment) -> must merge
        {"conversion_action.id": 1, "conversion_action.name": "Purchase", "conversion_action.status": "ENABLED",
         "conversion_action.type": "PURCHASE", "conversion_action.category": "PURCHASE",
         "conversion_action.primary_for_goal": True, "conversion_action.counting_type": "ONE_PER_CLICK",
         "conversion_action.attribution_model_settings.attribution_model": "GOOGLE_SEARCH_ATTRIBUTION_DATA_DRIVEN",
         "metrics.conversions": 5},
    ]}
    curr_raw = {"result": [
        {"campaign.id": 9, "campaign.name": "C9", "metrics.clicks": 100, "metrics.impressions": 2000,
         "metrics.cost_micros": 50_000_000, "metrics.conversions": 8},
    ]}
    prior_raw = {"result": [
        {"campaign.id": 9, "campaign.name": "C9", "metrics.clicks": 90, "metrics.impressions": 1800,
         "metrics.cost_micros": 45_000_000, "metrics.conversions": 10},
        # a campaign that only ran in the prior window -> no-row-loss via the join
        {"campaign.id": 10, "campaign.name": "C10-paused", "metrics.clicks": 40, "metrics.impressions": 900,
         "metrics.cost_micros": 20_000_000, "metrics.conversions": 3},
    ]}
    meta = {"client_name": "T", "account_id": "1", "currency": "CAD",
            "window_curr": "wc", "window_prior": "wp", "generated": "2026-07-12"}
    with tempfile.TemporaryDirectory() as td:
        pc = Path(td) / "config.txt"; pc.write_text(json.dumps(config_raw))
        pcu = Path(td) / "curr.txt"; pcu.write_text(json.dumps(curr_raw))
        pp = Path(td) / "prior.txt"; pp.write_text(json.dumps(prior_raw))
        f = A.assemble(str(pc), str(pcu), str(pp), None, dict(meta))
        check("config rows merged by id", len(f["conversion_actions"]) == 1, len(f["conversion_actions"]))
        check("merged conversions_30d summed (45)",
              abs(f["conversion_actions"][0]["conversions_30d"] - 45.0) < 1e-9)
        check("campaign join keeps the paused-in-current campaign (no-row-loss)",
              len(f["campaign_trend"]) == 2, len(f["campaign_trend"]))
        c10 = next(r for r in f["campaign_trend"] if r["campaign_id"] == 10)
        check("C10 has zero current-window metrics (never dropped)",
              c10["clicks_curr"] == 0 and c10["clicks_prior"] == 40)
        check("default manual_checks emitted honestly when no --ec-csv",
              len(f["manual_checks"]) == 2
              and all(r["data_source"] == "not_confirmed" for r in f["manual_checks"]))
        rec = f["meta"]["reconciliation"]
        check("reconciliation embedded with raw stamps",
              rec["campaign_trend"]["rows"] == 2 and len(rec.get("raw_files", [])) == 3)
        fp = Path(td) / "findings.json"; fp.write_text(json.dumps(f))
        core.load_findings(str(fp))
        check("assembled findings pass core verification", True)
        f["campaign_trend"][0]["cost_curr"] += 500
        fp.write_text(json.dumps(f))
        try:
            core.load_findings(str(fp)); ok = False
        except core.FindingsError:
            ok = True
        check("hand-edited findings rejected by core", ok)


def test_mcp_vs_csv_identical_model_shape():
    print("test_mcp_vs_csv_identical_model_shape")
    import csv
    import tempfile
    import assemble_findings as A
    config_raw = {"result": [
        {"conversion_action.id": 1, "conversion_action.name": "Purchase", "conversion_action.status": "ENABLED",
         "conversion_action.type": "PURCHASE", "conversion_action.category": "PURCHASE",
         "conversion_action.primary_for_goal": True, "conversion_action.counting_type": "ONE_PER_CLICK",
         "conversion_action.attribution_model_settings.attribution_model": "GOOGLE_SEARCH_ATTRIBUTION_DATA_DRIVEN",
         "metrics.conversions": 40},
    ]}
    curr_raw = {"result": [{"campaign.id": 9, "campaign.name": "C9", "metrics.clicks": 100,
                            "metrics.impressions": 2000, "metrics.cost_micros": 50_000_000,
                            "metrics.conversions": 8}]}
    prior_raw = {"result": [{"campaign.id": 9, "campaign.name": "C9", "metrics.clicks": 90,
                             "metrics.impressions": 1800, "metrics.cost_micros": 45_000_000,
                             "metrics.conversions": 10}]}
    meta = {"client_name": "T", "account_id": "1", "currency": "CAD",
            "window_curr": "wc", "window_prior": "wp", "generated": "2026-07-12"}
    with tempfile.TemporaryDirectory() as td:
        pc = Path(td) / "config.txt"; pc.write_text(json.dumps(config_raw))
        pcu = Path(td) / "curr.txt"; pcu.write_text(json.dumps(curr_raw))
        pp = Path(td) / "prior.txt"; pp.write_text(json.dumps(prior_raw))
        f_no_csv = A.assemble(str(pc), str(pcu), str(pp), None, dict(meta))

        csv_path = Path(td) / "ec_consent.csv"
        with csv_path.open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["Check", "Value", "Note"])
            w.writerow(["Enhanced Conversions", "Enabled", "confirmed in UI"])
            w.writerow(["Consent Mode v2", "Basic", ""])
        f_csv = A.assemble(str(pc), str(pcu), str(pp), str(csv_path), dict(meta))

        m1, m2 = core.compute_model(f_no_csv), core.compute_model(f_csv)
        check("same trend row count", len(m1["rows"]) == len(m2["rows"]))
        check("same config row count", len(m1["config_rows"]) == len(m2["config_rows"]))
        check("same manual row count", len(m1["manual_rows"]) == len(m2["manual_rows"]) == 2)
        check("no-CSV path is honestly not_confirmed",
              all(r["data_source"] == "not_confirmed" for r in m1["manual_rows"]))
        check("CSV path is honestly user_csv", all(r["data_source"] == "user_csv" for r in m2["manual_rows"]))
        check("trend summary identical (same underlying campaign data)",
              {k: v for k, v in m1["summary"].items() if not k.startswith(("config_", "manual_"))} ==
              {k: v for k, v in m2["summary"].items() if not k.startswith(("config_", "manual_"))})
        check("row shapes match key-for-key",
              set(m1["rows"][0].keys()) == set(m2["rows"][0].keys()))


def test_bundle_md_html_parity_and_lazy():
    print("test_bundle_md_html_parity_and_lazy")
    import re
    import tempfile
    import conv_tracking_spec as spec_mod
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
    check("html embeds every campaign (in-play envelope == scored, matches trend rows count)",
          html_rows == n, f"{html_rows} vs {n}")
    check("md has the config-health section", "## Conversion-action config health" in md)
    check("md has the manual EC/Consent-Mode section",
          "## Enhanced Conversions / Consent Mode (manual)" in md)
    blob = C.vendor_blob()
    check("explorer embeds the verified vendor runtime", blob in html)
    stripped = html.replace(blob, "")
    check("html is self-contained outside the verified vendor blob",
          len(re.findall(r"https?://|<link|src=|cdn", stripped)) == 0)
    check("both chart svgs written", svgs == ["cvr_trend_scatter.svg", "tier_counts.svg"], svgs)
    check("md has a Charts section", "## Charts" in md)
    check("explorer embeds the chart specs", "const CHARTS = " in html)
    check("building md/html did not import openpyxl", "openpyxl" not in sys.modules)


def main():
    for t in (test_fixture_counts, test_no_row_loss_both_datasets, test_config_health_flags,
              test_manual_checks_honesty, test_no_benchmark_row_present, test_empty_universe,
              test_assemble_findings_from_raw, test_mcp_vs_csv_identical_model_shape,
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
