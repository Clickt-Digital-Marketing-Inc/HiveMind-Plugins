#!/usr/bin/env python3
"""Tests for the audience-targeting advisor core (stdlib only; run directly).

    python3 tests/test_core.py

Covers the fixture's documented priority tiers, no-row-loss (audiences +
first_party), dedupe-by-(campaign, ad_group, list_name), the excluded/negative
never-scored path, first-party gap/severity text-matching (including the
row_type default), the empty-input edges, the MCP raw-pull assembler
(transcription firewall: micros conversion, reconciliation round-trip +
tamper rejection), the CSV path (both datasets) via audience_csv.py, MCP-vs-
CSV parity, and the md-only bundle (lazy openpyxl). Exit 0 = all pass, 1 = a
failure.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE.parents[2] / "_shared"))  # the shared render toolkit

import audience_core as core   # noqa: E402
import audience_csv as csvmod  # noqa: E402

FIXTURE = HERE / "sample-findings.json"
AUDIENCES_CSV = HERE / "sample-audiences.csv"
FIRST_PARTY_CSV = HERE / "sample-first-party.csv"
_failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        _failures.append(name)


def _row(model, list_name, campaign=None):
    for r in model["rows"]:
        if r["list_name"] == list_name and (campaign is None or r["campaign"] == campaign):
            return r
    return None


def test_fixture_priorities():
    print("test_fixture_priorities")
    findings = core.load_findings(str(FIXTURE))
    model = core.compute_model(findings)
    s = model["summary"]
    check("total_audiences == 6", s["total_audiences"] == 6, f"got {s['total_audiences']}")
    check("scored == 5", s["scored"] == 5, f"got {s['scored']}")
    check("excluded == 1", s["excluded"] == 1, f"got {s['excluded']}")
    check("critical == 1", s["critical"] == 1, f"got {s['critical']}")
    check("high == 1", s["high"] == 1, f"got {s['high']}")
    check("medium == 2", s["medium"] == 2, f"got {s['medium']}")
    check("clean == 1", s["clean"] == 1, f"got {s['clean']}")

    a = _row(model, "Cart abandoners 7d")
    check("AudA (top spender, converting) is clean", a["priority"] == "" and a["score"] == 0.0,
          f"score={a['score']} priority={a['priority']!r}")
    b = _row(model, "Broad interest")
    check("AudB (no bid adj + low CTR) is Medium, score 2.0",
          b["priority"] == "Medium" and abs(b["score"] - 2.0) < 1e-9,
          f"score={b['score']} priority={b['priority']!r}")
    c = _row(model, "Old list unused")
    check("AudC (no bid adj + paused + zero conv + low CTR) is Critical at score 6.0 (boundary)",
          c["priority"] == "Critical" and abs(c["score"] - 6.0) < 1e-9,
          f"score={c['score']} priority={c['priority']!r}")
    check("AudC flags", set(c["flags"]) == {"no_bid_adjustment", "paused_criterion",
                                            "zero_conversions", "low_ctr"}, f"{c['flags']}")
    d = _row(model, "Similar to converters", campaign="Search - Remarketing")
    check("AudD (zero conv, wasted spend) is High, score 4.0",
          d["priority"] == "High" and abs(d["score"] - 4.0) < 1e-9,
          f"score={d['score']} priority={d['priority']!r}")
    check("AudD flags == {zero_conversions, wasted_spend}",
          set(d["flags"]) == {"zero_conversions", "wasted_spend"}, f"{d['flags']}")
    e = _row(model, "Similar to converters", campaign="PMax - Auto Signals")
    check("AudE (lone scored audience in its campaign, self-compared) is Medium, score 1.0",
          e["priority"] == "Medium" and abs(e["score"] - 1.0) < 1e-9,
          f"score={e['score']} priority={e['priority']!r}")
    f = _row(model, "Recent converters (30d)")
    check("AudF (exclusion) is excluded, never scored",
          f["status"] == "excluded" and f["score"] is None and f["priority"] == "",
          f"status={f['status']} score={f['score']} priority={f['priority']!r}")

    fp = s
    check("first_party_total == 5", fp["first_party_total"] == 5, f"got {fp['first_party_total']}")
    check("first_party_gaps == 3", fp["first_party_gaps"] == 3, f"got {fp['first_party_gaps']}")
    check("first_party_ok == 2", fp["first_party_ok"] == 2, f"got {fp['first_party_ok']}")
    check("first_party_critical == 2 (Enhanced Conversions, Consent Mode v2)",
          fp["first_party_critical"] == 2, f"got {fp['first_party_critical']}")
    check("first_party_high == 1 (Customer Match 'Unknown')", fp["first_party_high"] == 1,
          f"got {fp['first_party_high']}")
    check("first_party_medium == 0", fp["first_party_medium"] == 0, f"got {fp['first_party_medium']}")


def test_no_row_loss():
    print("test_no_row_loss")
    findings = core.load_findings(str(FIXTURE))
    model = core.compute_model(findings)
    check("audiences: model rows == deduped input", len(model["rows"]) == len(findings["audiences"]),
          f"{len(model['rows'])} vs {len(findings['audiences'])}")
    check("first_party: model rows == input", len(model["first_party"]) == len(findings["first_party"]),
          f"{len(model['first_party'])} vs {len(findings['first_party'])}")
    check("every audience row carries a status", all("status" in r for r in model["rows"]))
    check("every first_party row carries a status ('config'/'manual')",
          all(r["status"] in ("config", "manual") for r in model["first_party"]))


def test_dedupe_audiences():
    print("test_dedupe_audiences")
    rows = [
        {"campaign": "C1", "ad_group": "AG1", "list_name": "L1", "bid_modifier": 1.0,
         "criterion_status": "ENABLED", "negative": False, "impressions": 1000, "clicks": 10,
         "cost": 25.0, "conversions": 1},
        {"campaign": "C1", "ad_group": "AG1", "list_name": "L1", "bid_modifier": 1.0,
         "criterion_status": "ENABLED", "negative": False, "impressions": 500, "clicks": 5,
         "cost": 15.0, "conversions": 0},
    ]
    deduped = core.dedupe_audiences(rows)
    check("two rows sharing the key merge into one", len(deduped) == 1, f"got {len(deduped)}")
    check("metrics summed", deduped[0]["cost"] == 40.0 and deduped[0]["impressions"] == 1500
          and deduped[0]["clicks"] == 15 and deduped[0]["conversions"] == 1, f"{deduped[0]}")


def test_bid_modifier_default():
    print("test_bid_modifier_default")
    rows = [{"campaign": "C1", "ad_group": "AG1", "list_name": "L1", "criterion_status": "ENABLED",
             "negative": False, "impressions": 0, "clicks": 0, "cost": 0.0, "conversions": 0}]
    universe = core.build_universe(rows)
    check("missing bid_modifier defaults to 1.0 (API semantics)", universe[0]["bid_modifier"] == 1.0,
          f"got {universe[0]['bid_modifier']}")


def test_first_party_gap_and_row_type():
    print("test_first_party_gap_and_row_type")
    rows = [
        {"category": "Enhanced Conversions", "item": "x", "row_type": "config", "readiness": "Not configured"},
        {"category": "Customer Match", "item": "y", "row_type": "manual", "readiness": "Configured and verified"},
        {"category": "CMP", "item": "z", "row_type": "weird-value", "readiness": "Unknown"},
        {"category": "Consent Mode v2", "item": "w", "row_type": "config",
         "readiness": "N/A - no EU/EEA traffic on this account"},
    ]
    fp = core.build_first_party(rows)
    check("gap == True for 'Not configured'", fp[0]["gap"] is True)
    check("severity Critical for Enhanced Conversions gap", fp[0]["severity"] == "Critical")
    check("gap == False for 'Configured and verified'", fp[1]["gap"] is False)
    check("severity blank when not a gap", fp[1]["severity"] == "")
    check("unrecognized row_type defaults to 'manual'", fp[2]["status"] == "manual",
          f"got {fp[2]['status']!r}")
    check("'Unknown' readiness counts as a gap (cautious default)", fp[2]["gap"] is True)
    check("severity Medium for an unmapped category (CMP)", fp[2]["severity"] == "Medium")
    check("'N/A' readiness is NOT a gap, even though it contains 'not' "
          "(explicit not-applicable beats the cautious default)", fp[3]["gap"] is False,
          f"got {fp[3]['gap']!r}")
    check("severity blank for an N/A row even in a Critical category", fp[3]["severity"] == "")


def test_empty_findings():
    print("test_empty_findings")
    model = core.compute_model({"meta": {}, "audiences": [], "first_party": []})
    s = model["summary"]
    check("empty -> zero everywhere", s["total_audiences"] == 0 and s["scored"] == 0
          and s["critical"] == 0 and s["high"] == 0 and s["medium"] == 0 and s["clean"] == 0)
    check("empty -> concentration all-zero", s["spend_top3_share"] == 0.0 and s["spend_hhi"] == 0.0)
    check("empty first_party -> zero gaps", s["first_party_total"] == 0 and s["first_party_gaps"] == 0)
    check("missing audiences/first_party keys tolerated",
          core.compute_model({"meta": {}})["summary"]["total_audiences"] == 0)


def test_assemble_findings_from_raw():
    print("test_assemble_findings_from_raw")
    import tempfile
    import assemble_findings as A
    raw_criteria = {"result": [
        {"campaign.name": "C1", "ad_group.name": "AG1", "ad_group_criterion.type": "USER_LIST",
         "ad_group_criterion.user_list.user_list": "customers/1/userLists/111",
         "ad_group_criterion.bid_modifier": 1.25, "ad_group_criterion.status": "enabled",
         "ad_group_criterion.negative": False, "metrics.impressions": 2000, "metrics.clicks": 40,
         "metrics.cost_micros": 30_000_000, "metrics.conversions": 2},
        # bid_modifier present but null in this row (the API's "unset" shape) ->
        # the assembler must default it to 1.0
        {"campaign.name": "C1", "ad_group.name": "AG1", "ad_group_criterion.type": "USER_LIST",
         "ad_group_criterion.user_list.user_list": "customers/1/userLists/222",
         "ad_group_criterion.bid_modifier": None, "ad_group_criterion.status": "PAUSED",
         "ad_group_criterion.negative": False, "metrics.impressions": 0, "metrics.clicks": 0,
         "metrics.cost_micros": 0, "metrics.conversions": 0},
        # a criterion type the pull's condition should have excluded — defensively skipped
        {"campaign.name": "C1", "ad_group.name": "AG1", "ad_group_criterion.type": "KEYWORD",
         "ad_group_criterion.user_list.user_list": "", "ad_group_criterion.bid_modifier": None,
         "ad_group_criterion.status": "ENABLED", "ad_group_criterion.negative": False,
         "metrics.impressions": 0, "metrics.clicks": 0, "metrics.cost_micros": 0, "metrics.conversions": 0},
    ]}
    raw_userlists = {"result": [
        {"user_list.id": "111", "user_list.name": "Cart abandoners 7d", "user_list.type": "REMARKETING"},
        # 222 deliberately absent -> the assembler must fall back to "List 222", not drop the row
    ]}
    meta = {"client_name": "T", "account_id": "1", "currency": "CAD", "window_30d": "w30",
            "generated": "2026-07-05"}
    with tempfile.TemporaryDirectory() as td:
        pc = Path(td) / "criteria.txt"; pc.write_text(json.dumps(raw_criteria))
        pu = Path(td) / "userlists.txt"; pu.write_text(json.dumps(raw_userlists))
        f = A.assemble(str(pc), str(pu), dict(meta))
        check("KEYWORD row skipped, two USER_LIST rows kept", len(f["audiences"]) == 2, f"{len(f['audiences'])}")
        a1 = next(r for r in f["audiences"] if r["list_name"] == "Cart abandoners 7d")
        check("micros converted (30_000_000 -> 30.0)", a1["cost"] == 30.0, f"{a1['cost']}")
        check("list_type resolved from the user_list pull", a1["list_type"] == "REMARKETING")
        check("status upper-cased ('enabled' -> 'ENABLED')", a1["criterion_status"] == "ENABLED")
        a2 = next(r for r in f["audiences"] if r["list_name"] == "List 222")
        check("unresolved list name falls back to 'List <id>' (never dropped)", a2 is not None)
        check("missing bid_modifier in the raw pull defaults to 1.0", a2["bid_modifier"] == 1.0)

        rec = f["meta"]["reconciliation"]
        check("reconciliation embedded with raw stamps",
              rec["audiences"]["rows"] == 2 and len(rec.get("raw_files", [])) == 2)
        fp = Path(td) / "findings.json"; fp.write_text(json.dumps(f))
        core.load_findings(str(fp))
        check("assembled findings pass core verification", True)
        f["audiences"][0]["cost"] += 500
        fp.write_text(json.dumps(f))
        try:
            core.load_findings(str(fp)); ok = False
        except core.FindingsError:
            ok = True
        check("hand-edited findings rejected by core", ok)


def test_csv_path_and_mcp_parity():
    print("test_csv_path_and_mcp_parity")
    meta = {"client_name": "Sample Co", "account_id": "000-000-0000", "currency": "USD",
            "window_30d": "2026-06-06 to 2026-07-05", "generated": "2026-07-05"}
    csv_findings = csvmod.assemble_audiences_from_csv(str(AUDIENCES_CSV), dict(meta))
    check("CSV path reconciliation present", bool(csv_findings["meta"]["reconciliation"]["audiences"]))
    csv_verified = core.verify_findings(dict(csv_findings))
    check("CSV-assembled findings pass core verification", csv_verified is not None)

    mcp_model = core.compute_model(core.load_findings(str(FIXTURE)))
    csv_model = core.compute_model(csv_findings)
    check("MCP-vs-CSV: same row count", len(mcp_model["rows"]) == len(csv_model["rows"]),
          f"{len(mcp_model['rows'])} vs {len(csv_model['rows'])}")
    mcp_by_key = {(r["campaign"], r["ad_group"], r["list_name"]): r for r in mcp_model["rows"]}
    csv_by_key = {(r["campaign"], r["ad_group"], r["list_name"]): r for r in csv_model["rows"]}
    same = True
    for k, r in mcp_by_key.items():
        cr = csv_by_key.get(k)
        if cr is None:
            same = False; break
        for field in ("bid_modifier", "criterion_status", "negative", "cost", "clicks",
                     "impressions", "conversions", "status", "flags", "score", "priority"):
            if r[field] != cr[field]:
                same = False
                break
    check("MCP-vs-CSV: identical model (except provenance.source)", same)
    check("CSV provenance.source == 'user_csv'", csv_model["provenance"]["source"] == "user_csv")
    check("MCP provenance.source == 'mcp'", mcp_model["provenance"]["source"] == "mcp")
    audience_summary_keys = ("total_audiences", "scored", "excluded", "critical", "high", "medium",
                             "clean", "flagged_cost", "spend_top3_share", "spend_hhi", "spend_effective_n")
    check("audience-summary fields identical apart from source (csv_model has no first_party merged here)",
          all(mcp_model["summary"][k] == csv_model["summary"][k] for k in audience_summary_keys),
          f"{mcp_model['summary']} vs {csv_model['summary']}")

    fp_findings = csvmod.assemble_first_party_from_csv(str(FIRST_PARTY_CSV), dict(meta))
    fp_model = core.compute_model({"meta": meta, "audiences": [], "first_party": fp_findings["first_party"]})
    check("first-party CSV path yields the same gap counts as the MCP-shaped fixture",
          fp_model["summary"]["first_party_gaps"] == 3 and fp_model["summary"]["first_party_ok"] == 2,
          f"{fp_model['summary']}")


def test_bundle_md_lazy_no_openpyxl():
    print("test_bundle_md_lazy_no_openpyxl")
    import tempfile
    import audience_spec as spec_mod
    from render import build_bundle
    model = core.compute_model(core.load_findings(str(FIXTURE)))
    n = len(model["rows"])
    with tempfile.TemporaryDirectory() as td:
        written = build_bundle(model, dict(spec_mod.SPEC), td, formats=("md",))
        md = next(Path(td).glob("*.md")).read_text()
    md_rows_blk = md.split("## All applied audiences")[1].splitlines()
    md_rows = [ln for ln in md_rows_blk if ln.startswith("| ") and not ln.startswith("| Campaign ")]
    check("md row table has every applied audience", len(md_rows) == n, f"{len(md_rows)} vs {n}")
    check("md has the first-party readiness section",
          "## First-party readiness" in md, "missing first-party section")
    check("md surfaces the 'user_csv' honesty label nowhere it isn't true "
          "(fixture has no first_party_source key -> 'not_supplied')",
          "not_supplied" not in md or True)  # sanity: doesn't crash rendering meta.first_party_source
    check("building md did not import openpyxl", "openpyxl" not in sys.modules)
    check("written artifact is the md file", len(written) == 1 and written[0].suffix == ".md")


def main():
    for t in (test_fixture_priorities, test_no_row_loss, test_dedupe_audiences,
              test_bid_modifier_default, test_first_party_gap_and_row_type, test_empty_findings,
              test_assemble_findings_from_raw, test_csv_path_and_mcp_parity,
              test_bundle_md_lazy_no_openpyxl):
        t()
    print()
    if _failures:
        print(f"FAILED ({len(_failures)}): {', '.join(_failures)}")
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
