#!/usr/bin/env python3
"""Tests for the product-segments filter core (stdlib only; run directly).

    python3 tests/test_filter.py

Asserts the documented fixture result, no-row-loss, dedupe-by-product, the
empty-products edge, fractional-conversion handling, the merchant-empty-not-
zombie edge, sensitivity shape, the raw-pull assembler (transcription firewall:
micros conversion, per-product aggregation, window join, reconciliation
round-trip + tamper rejection), and md/html bundle parity + lazy openpyxl.
Exit 0 = all pass, 1 = a failure.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE.parents[2] / "_shared"))  # the shared render toolkit

import csv_input as C               # noqa: E402  (CSV path robustness assertions)
import product_filter_core as core  # noqa: E402

FIXTURE = HERE / "product-sample-findings.json"
_failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        _failures.append(name)


def _row(model, item_id):
    return next(r for r in model["rows"] if r["product_item_id"] == item_id)


def test_fixture_counts():
    print("test_fixture_counts")
    findings = core.load_findings(str(FIXTURE))
    model = core.compute_model(findings)
    s = model["summary"]
    check("zombie == 1", s["zombie"] == 1, f"got {s['zombie']}")
    check("surging == 1", s["surging"] == 1, f"got {s['surging']}")
    check("declining == 1", s["declining"] == 1, f"got {s['declining']}")
    check("zombie_wasted_cost == 120.0", abs(s["zombie_wasted_cost"] - 120.0) < 1e-6, f"got {s['zombie_wasted_cost']}")
    check("inactive == 1", s["inactive"] == 1, f"got {s['inactive']}")
    check("no_merchant == 2", s["no_merchant"] == 2, f"got {s['no_merchant']}")
    # 8 input rows, SKU-DUP appears twice -> 7 deduped
    n_dedup = len(core.dedupe_products(findings["products"]))
    check("universe == deduped count (7)", s["universe"] == 7 and n_dedup == 7, f"got {s['universe']} / {n_dedup}")
    check("scored == 6", s["scored"] == 6, f"got {s['scored']}")
    check("rows preserved == deduped input (no row loss)", len(model["rows"]) == n_dedup,
          f"{len(model['rows'])} vs {n_dedup}")


def test_merchant_empty_not_zombie():
    print("test_merchant_empty_not_zombie")
    model = core.compute_model(core.load_findings(str(FIXTURE)))
    r = _row(model, "SKU-NOMERCH")  # conv30=0, cost30=90 (>0), merchant ""
    check("merchant-empty waste row is NOT a zombie", r["is_zombie"] is False, f"got {r['is_zombie']}")
    check("merchant-empty waste row has empty segment", r["segment"] == "", f"got {r['segment']!r}")


def test_inactive_row_present():
    print("test_inactive_row_present")
    model = core.compute_model(core.load_findings(str(FIXTURE)))
    r = _row(model, "SKU-INACTIVE")
    check("inactive row kept with status inactive", r["status"] == "inactive")
    check("inactive row has empty segment", r["segment"] == "")


def test_dedupe_by_product():
    print("test_dedupe_by_product")
    model = core.compute_model(core.load_findings(str(FIXTURE)))
    dup = [r for r in model["rows"] if r["product_item_id"] == "SKU-DUP"]
    check("duplicate product merged to one row", len(dup) == 1, f"got {len(dup)}")
    check("merged 30d cost summed (50+50=100)", dup and abs(dup[0]["cost_30d"] - 100.0) < 1e-6,
          f"got {dup[0]['cost_30d'] if dup else None}")
    check("merged channels union", dup and dup[0]["channels"] == ["PERFORMANCE_MAX", "SHOPPING"],
          f"got {dup[0]['channels'] if dup else None}")


def test_empty_products():
    print("test_empty_products")
    model = core.compute_model({"meta": {}, "products": []})
    s = model["summary"]
    check("empty -> universe 0", s["universe"] == 0)
    check("empty -> all segments 0", s["zombie"] == 0 and s["surging"] == 0 and s["declining"] == 0)
    check("empty -> surge sensitivity computed without crash",
          len(model["sensitivity_surge"]) == len(core.SURGE_LADDER))
    check("empty -> decline sensitivity computed without crash",
          len(model["sensitivity_decline"]) == len(core.DECLINE_LADDER))


def test_fractional_neither_then_flips():
    print("test_fractional_neither_then_flips")
    # prev14d=2.0, cur14d=2.75 -> not surging (2.75 < 1.5*2=3.0), not declining (2.75 > 0.5*2=1.0)
    base = {"product_item_id": "F", "product_title": "frac", "merchant_id": "9",
            "conversions_30d": 3, "cost_30d": 70, "impressions_30d": 3000,
            "conversions_14d": 2.75, "impressions_14d": 1500,
            "conversions_prev14d": 2.0, "impressions_prev14d": 1400}
    s = core.compute_model({"meta": {}, "products": [dict(base)]})["summary"]
    check("fractional 2.75 vs 2.0 -> neither", s["surging"] == 0 and s["declining"] == 0,
          f"surging={s['surging']} declining={s['declining']}")
    surge = dict(base); surge["conversions_14d"] = 3.5  # 3.5 > 3.0 -> Surging
    s2 = core.compute_model({"meta": {}, "products": [surge]})["summary"]
    check("cur14d 3.5 -> Surging (sanity)", s2["surging"] == 1, f"got {s2['surging']}")
    dec = dict(base); dec["conversions_14d"] = 0.5  # 0.5 < 1.0 -> Declining
    s3 = core.compute_model({"meta": {}, "products": [dec]})["summary"]
    check("cur14d 0.5 -> Declining (sanity)", s3["declining"] == 1, f"got {s3['declining']}")


def test_sensitivity_shapes():
    print("test_sensitivity_shapes")
    model = core.compute_model(core.load_findings(str(FIXTURE)))
    ss, ds = model["sensitivity_surge"], model["sensitivity_decline"]
    check("surge sensitivity has a row per ladder step", len(ss) == len(core.SURGE_LADDER))
    check("decline sensitivity has a row per ladder step", len(ds) == len(core.DECLINE_LADDER))
    check("exactly one surge row flagged current", sum(1 for r in ss if r["is_current"]) == 1)
    check("exactly one decline row flagged current", sum(1 for r in ds if r["is_current"]) == 1)


def test_assemble_findings_from_raw():
    print("test_assemble_findings_from_raw")
    import tempfile
    import assemble_findings as A
    raw30 = {"result": [
        # same product across two channels -> must merge (sum metrics, union channels)
        {"segments.product_item_id": "SKU-A", "segments.product_title": "Widget A",
         "segments.product_merchant_id": "111", "campaign.advertising_channel_type": "SHOPPING",
         "metrics.conversions": 0, "metrics.cost_micros": 2_000_000, "metrics.impressions": 100},
        {"segments.product_item_id": "SKU-A", "segments.product_title": "Widget A",
         "segments.product_merchant_id": "111", "campaign.advertising_channel_type": "PERFORMANCE_MAX",
         "metrics.conversions": 1, "metrics.cost_micros": 1_000_000, "metrics.impressions": 100},
        # a product with no rows in either 14d window -> those windows default to 0
        {"segments.product_item_id": "SKU-B", "segments.product_title": "Widget B",
         "segments.product_merchant_id": "222", "campaign.advertising_channel_type": "SHOPPING",
         "metrics.conversions": 2.5, "metrics.cost_micros": 4_500_000, "metrics.impressions": 50},
    ]}
    raw14 = {"result": [
        # merchant id from the most recent window the product appears in (999 wins over 111)
        {"segments.product_item_id": "SKU-A", "segments.product_merchant_id": "999",
         "metrics.conversions": 0.5, "metrics.impressions": 50},
    ]}
    rawprev = {"result": [
        {"segments.product_item_id": "SKU-A", "metrics.conversions": 2, "metrics.impressions": 60},
    ]}
    meta = {"client_name": "T", "account_id": "1", "currency": "CAD",
            "window_30d": "w30", "window_14d": "w14", "window_prev14d": "wp14",
            "generated": "2026-07-06"}
    with tempfile.TemporaryDirectory() as td:
        p30 = Path(td) / "p30.txt"; p30.write_text(json.dumps(raw30))
        p14 = Path(td) / "p14.txt"; p14.write_text(json.dumps(raw14))
        pprev = Path(td) / "prev14.txt"; pprev.write_text(json.dumps(rawprev))
        f = A.assemble(str(p30), str(p14), str(pprev), dict(meta))
        prods = {p["product_item_id"]: p for p in f["products"]}
        check("union of pulls: two products", len(prods) == 2, f"{len(prods)}")
        a = prods.get("SKU-A") or {}
        check("channel rows merged, micros converted (2+1 -> 3.0)",
              abs(a.get("cost_30d", 0) - 3.0) < 1e-9 and a.get("conversions_30d") == 1
              and a.get("impressions_30d") == 200)
        check("channels unioned + sorted", a.get("channels") == ["PERFORMANCE_MAX", "SHOPPING"],
              f"{a.get('channels')}")
        check("14d/prev-14d windows joined by product",
              a.get("conversions_14d") == 0.5 and a.get("impressions_14d") == 50
              and a.get("conversions_prev14d") == 2 and a.get("impressions_prev14d") == 60)
        check("merchant id from the most recent window (14d)", a.get("merchant_id") == "999",
              f"{a.get('merchant_id')!r}")
        b = prods.get("SKU-B") or {}
        check("missing windows default to 0",
              b.get("conversions_14d") == 0 and b.get("impressions_14d") == 0
              and b.get("conversions_prev14d") == 0 and b.get("impressions_prev14d") == 0)
        check("merchant id falls back to the 30d pull", b.get("merchant_id") == "222",
              f"{b.get('merchant_id')!r}")
        check("fractional conversions preserved (2.5)", b.get("conversions_30d") == 2.5)
        rec = f["meta"]["reconciliation"]
        check("reconciliation embedded with raw stamps",
              rec["products"]["rows"] == 2 and len(rec.get("raw_files", [])) == 3)
        # the assembled findings load clean through the core's verification...
        fp = Path(td) / "findings.json"; fp.write_text(json.dumps(f))
        core.load_findings(str(fp))
        check("assembled findings pass core verification", True)
        # ...and a hand-edit is a hard load failure
        f["products"][0]["cost_30d"] += 500
        fp.write_text(json.dumps(f))
        try:
            core.load_findings(str(fp)); ok = False
        except core.FindingsError:
            ok = True
        check("hand-edited findings rejected by core", ok)


_CSV_META = {"client_name": "T", "account_id": "1", "currency": "CAD",
             "window_30d": "w30", "window_14d": "w14", "window_prev14d": "wp14",
             "generated": "2026-07-06"}

# The SAME product data as test_assemble_findings_from_raw's raw30/raw14/rawprev,
# expressed as three Google Ads UI "Products" report exports — the CSV-vs-MCP
# identical-model acceptance check. UI-export quirks on purpose: a title row +
# date-range row above the header, a currency-prefixed Cost cell, a "Total:"
# summary row (30d), and the "Impr." header alias (14d).
_CSV_30D = """Products report
"May 28, 2026 - June 26, 2026"
Item ID,Item title,Merchant Center ID,Campaign type,Cost,Conversions,Impressions
SKU-A,Widget A,111,SHOPPING,CA$2.00,0,100
SKU-A,Widget A,111,PERFORMANCE_MAX,1.00,1,100
SKU-B,Widget B,222,SHOPPING,4.50,2.5,50
Total: products,,,,7.50,3.5,250
"""
_CSV_14D = """Item ID,Merchant Center ID,Conversions,Impr.
SKU-A,999,0.5,50
"""
_CSV_PREV14D = """Item ID,Conversions,Impressions
SKU-A,2,60
"""


def _write_csv_windows(td):
    p30 = Path(td) / "p30.csv"; p30.write_text(_CSV_30D)
    p14 = Path(td) / "p14.csv"; p14.write_text(_CSV_14D)
    pprev = Path(td) / "pprev.csv"; pprev.write_text(_CSV_PREV14D)
    return str(p30), str(p14), str(pprev)


def _raw_windows_for_csv_fixture():
    """The GAQL-shaped equivalent of _CSV_30D/_CSV_14D/_CSV_PREV14D (same
    product data, same numbers) so the two paths can be compared directly."""
    raw30 = {"result": [
        {"segments.product_item_id": "SKU-A", "segments.product_title": "Widget A",
         "segments.product_merchant_id": "111", "campaign.advertising_channel_type": "SHOPPING",
         "metrics.conversions": 0, "metrics.cost_micros": 2_000_000, "metrics.impressions": 100},
        {"segments.product_item_id": "SKU-A", "segments.product_title": "Widget A",
         "segments.product_merchant_id": "111", "campaign.advertising_channel_type": "PERFORMANCE_MAX",
         "metrics.conversions": 1, "metrics.cost_micros": 1_000_000, "metrics.impressions": 100},
        {"segments.product_item_id": "SKU-B", "segments.product_title": "Widget B",
         "segments.product_merchant_id": "222", "campaign.advertising_channel_type": "SHOPPING",
         "metrics.conversions": 2.5, "metrics.cost_micros": 4_500_000, "metrics.impressions": 50},
    ]}
    raw14 = {"result": [
        {"segments.product_item_id": "SKU-A", "segments.product_merchant_id": "999",
         "metrics.conversions": 0.5, "metrics.impressions": 50},
    ]}
    rawprev = {"result": [
        {"segments.product_item_id": "SKU-A", "metrics.conversions": 2, "metrics.impressions": 60},
    ]}
    return raw30, raw14, rawprev


def test_csv_matches_mcp_model():
    print("test_csv_matches_mcp_model")
    import tempfile
    import assemble_findings as A
    raw30, raw14, rawprev = _raw_windows_for_csv_fixture()
    with tempfile.TemporaryDirectory() as td:
        p30 = Path(td) / "p30.txt"; p30.write_text(json.dumps(raw30))
        p14 = Path(td) / "p14.txt"; p14.write_text(json.dumps(raw14))
        pprev = Path(td) / "prev14.txt"; pprev.write_text(json.dumps(rawprev))
        mcp_findings = A.assemble(str(p30), str(p14), str(pprev), dict(_CSV_META))

        c30, c14, cprev = _write_csv_windows(td)
        csv_findings = A.assemble_csv(c30, c14, cprev, dict(_CSV_META))

        check("mcp path stamps meta.source=mcp",
              mcp_findings["meta"]["source"] == "mcp")
        check("csv path stamps meta.source=user_csv",
              csv_findings["meta"]["source"] == "user_csv")
        check("csv products array identical to mcp (modulo source)",
              csv_findings["products"] == mcp_findings["products"],
              f"csv={csv_findings['products']!r} mcp={mcp_findings['products']!r}")

        # round-trip through disk + core verification, exactly like a real run
        mcp_path = Path(td) / "mcp_findings.json"; mcp_path.write_text(json.dumps(mcp_findings))
        csv_path = Path(td) / "csv_findings.json"; csv_path.write_text(json.dumps(csv_findings))
        mcp_model = core.compute_model(core.load_findings(str(mcp_path)))
        csv_model = core.compute_model(core.load_findings(str(csv_path)))
        check("csv findings pass core verification", True)

        mp = dict(mcp_model["provenance"]); cp = dict(csv_model["provenance"])
        check("provenance sources differ as expected",
              mp.pop("source") == "mcp" and cp.pop("source") == "user_csv")
        check("provenance identical apart from source", mp == cp, f"mcp={mp} csv={cp}")
        check("rows identical", mcp_model["rows"] == csv_model["rows"],
              f"mcp={mcp_model['rows']!r} csv={csv_model['rows']!r}")
        check("summary identical", mcp_model["summary"] == csv_model["summary"],
              f"mcp={mcp_model['summary']!r} csv={csv_model['summary']!r}")
        check("surge sensitivity identical",
              mcp_model["sensitivity_surge"] == csv_model["sensitivity_surge"])
        check("decline sensitivity identical",
              mcp_model["sensitivity_decline"] == csv_model["sensitivity_decline"])


def test_csv_robustness():
    print("test_csv_robustness")
    import tempfile
    import assemble_findings as A
    with tempfile.TemporaryDirectory() as td:
        c30, c14, cprev = _write_csv_windows(td)
        findings = A.assemble_csv(c30, c14, cprev, dict(_CSV_META))
        prods = {p["product_item_id"]: p for p in findings["products"]}
        check("title/date rows above the header skipped", "SKU-A" in prods)
        check("Total: summary row dropped (30d)", len(prods) == 2, f"{list(prods)}")
        check("currency-prefixed + plain Cost cells summed (CA$2.00+1.00=3.0)",
              abs(prods["SKU-A"]["cost_30d"] - 3.0) < 1e-9, f"{prods['SKU-A']['cost_30d']}")
        check("'Impr.' alias resolves on the 14d export",
              prods["SKU-A"]["impressions_14d"] == 50)
        check("merchant id adopted from the 14d export (999 wins over 111)",
              prods["SKU-A"]["merchant_id"] == "999")

        # missing the REQUIRED Merchant Center ID column on the 14d export -> raises
        broken_14d = Path(td) / "broken14.csv"
        broken_14d.write_text("Item ID,Conversions,Impr.\nSKU-A,0.5,50\n")
        try:
            A.assemble_csv(c30, str(broken_14d), cprev, dict(_CSV_META))
            ok = False
        except C.CsvInputError as e:
            ok = "merchant_id" in str(e)
        check("14d export missing Merchant Center ID raises (not a silent blank)", ok)


def test_recommendations_cite_model_numbers():
    print("test_recommendations_cite_model_numbers")
    model = core.compute_model(core.load_findings(str(FIXTURE)))
    recs = core.recommendations(model)
    by_sev = {r["severity"]: r for r in recs}
    check("three tiers present on the mixed fixture",
          set(by_sev) == {"Critical", "High", "Medium"}, f"{sorted(by_sev)}")
    s = model["summary"]
    cur = model["provenance"]["currency"]
    check("Critical cites the zombie count", str(s["zombie"]) in by_sev["Critical"]["action"])
    check("Critical cites the wasted-cost model number",
          f"{s['zombie_wasted_cost']:,.2f} {cur}" in by_sev["Critical"]["why"])
    check("High cites the surge multiple param",
          f"{model['params']['surge_multiple']:.2f}" in by_sev["High"]["why"])
    check("Medium cites the decline multiple param",
          f"{model['params']['decline_multiple']:.2f}" in by_sev["Medium"]["why"])
    check("severity order is Critical -> High -> Medium",
          [r["severity"] for r in recs] == ["Critical", "High", "Medium"])

    clean = core.compute_model({"meta": {}, "products": []})
    check("clean result -> no recommendations (honest, not padded)",
          core.recommendations(clean) == [])


def test_bundle_md_html_parity_and_lazy():
    print("test_bundle_md_html_parity_and_lazy")
    import re
    import tempfile
    import product_filter_spec as spec_mod
    from render import build_bundle
    from render import charts as C
    model = core.compute_model(core.load_findings(str(FIXTURE)))
    n = len(model["rows"])
    with tempfile.TemporaryDirectory() as td:
        written = build_bundle(model, dict(spec_mod.SPEC), td, formats=("md", "html"))
        md = next(Path(td).glob("*.md")).read_text()
        html = next(Path(td).glob("*_explorer.html")).read_text()
        svgs = sorted(p.name for p in written if p.suffix == ".svg")
    rows_blk = md.split("## All products")[1].splitlines()
    md_rows = [ln for ln in rows_blk if ln.startswith("| ") and not ln.startswith("| Product ")]
    embedded = json.loads(re.search(r"^const MODEL = (.+);$", html, re.M).group(1))
    html_rows = len(embedded["rows"])
    check("md row table has every product", len(md_rows) == n, f"{len(md_rows)} vs {n}")
    check("html embeds every product", html_rows == n, f"{html_rows} vs {n}")
    # self-containment: the only opaque region allowed is the vendored chart
    # runtime, and only byte-equal to the committed, checksummed vendor files.
    blob = C.vendor_blob()
    check("explorer embeds the verified vendor runtime", blob in html)
    stripped = html.replace(blob, "")
    check("html is self-contained outside the verified vendor blob",
          len(re.findall(r"https?://|<link|src=|cdn", stripped)) == 0)
    # declared charts render as static SVGs and are referenced from the md
    check("both chart svgs written", svgs == ["cost_conv_scatter.svg", "spend_by_segment.svg"], svgs)
    check("md has a Charts section", "## Charts" in md)
    check("md references charts relatively", "_charts/spend_by_segment.svg)" in md)
    check("explorer embeds the chart specs", "const CHARTS = " in html)
    check("building md/html did not import openpyxl", "openpyxl" not in sys.modules)


def main():
    for t in (test_fixture_counts, test_merchant_empty_not_zombie, test_inactive_row_present,
              test_dedupe_by_product, test_empty_products, test_fractional_neither_then_flips,
              test_sensitivity_shapes, test_assemble_findings_from_raw,
              test_csv_matches_mcp_model, test_csv_robustness,
              test_recommendations_cite_model_numbers,
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
