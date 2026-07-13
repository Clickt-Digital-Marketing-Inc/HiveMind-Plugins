#!/usr/bin/env python3
"""Tests for cm3-by-product-report conformance to the locked output bundle.

Covers: fixture band counts, no-row-loss, vendor extraction, empty-input edge,
tunable band-cutoff banding + provenance, markdown provenance + full-table parity,
HTML self-containment + row parity, the explorer rollup plumbing (full-depth
taxonomy + vendor COGS map + source mix embedded, rollup UI wired, Python
no-row-loss oracle; live JS<->Python rollup parity is pinned by the dev-only
run_explorer_parity_cm3.py harness), the in-Claude tuner fragment, the vendored
chart module drift guard (byte-identical to the canonical copy under
plugins/google-ads-management/_shared/render/ when run inside the development
monorepo; the cross-plugin half skips in a standalone repo), and chart
determinism.
Stdlib only except vl-convert-python (the chart smoke needs it; the build
hard-fails without it by design). Run: python3 tests/test_cm3.py
"""
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve()
SKILL = HERE.parents[1]
try:
    REPO = HERE.parents[5]
except IndexError:  # standalone repo: tree too shallow to hold a monorepo root
    REPO = None
sys.path.insert(0, str(SKILL))

import cm3_by_product as cm3  # noqa: E402
import cm3_html  # noqa: E402
sys.path.insert(0, str(SKILL / "_charts"))
import charts as chartsmod  # noqa: E402  (the vendored copy)

SAMPLE = HERE.parent / "sample-shopping.csv"
INPUTS = {"cogs_pct": 65, "ship_pct": 20, "proc_pct": 2.9, "fixed_costs": 0}

EXPECTED_BANDS = {"Excellent": 1, "High": 1, "Average": 1, "Low": 1, "Poor": 2, "Inactive": 1}

# The canonical chart module this skill vendors (copy, not import — cm3 is bespoke).
# Only resolvable inside the development monorepo; None/absent in a standalone repo.
CANONICAL = (REPO / "plugins" / "google-ads-management" / "_shared" / "render"
             if REPO is not None else None)
VENDORED = SKILL / "_charts"

# Allowed opaque regions in otherwise self-contained outputs: the verified
# vendor runtime blob and the SVG namespace declarations of generated charts.
# src=(?!=) — catch src attributes but not the JS kernel's `r.src==="Input"`.
_EXTERNAL_RE = re.compile(r"https?://|<link|src=(?!=)|cdn")
_SVG_XMLNS = ('xmlns="http://www.w3.org/2000/svg"',
              'xmlns:xlink="http://www.w3.org/1999/xlink"')

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


def check_self_contained(doc: str, label: str):
    """Assert no external references outside the allowed regions: the vendor
    blob (only if byte-equal to the committed, checksummed runtime) and the
    generated charts' SVG xmlns declarations."""
    i, j = doc.find(chartsmod.VENDOR_BEGIN), doc.find(chartsmod.VENDOR_END)
    if i >= 0 or j >= 0:
        check(i >= 0 and j > i, f"{label}: vendor sentinels malformed")
        blob = doc[i:j + len(chartsmod.VENDOR_END)]
        check(blob == chartsmod.vendor_blob(),
              f"{label}: embedded vendor blob is NOT byte-equal to the committed runtime")
        doc = doc.replace(blob, "")
    for ns in _SVG_XMLNS:
        doc = doc.replace(ns, "")
    hits = _EXTERNAL_RE.findall(doc)
    check(not hits, f"{label}: external reference(s) outside allowed regions: {hits}")


def check_chart_drift():
    """DRIFT GUARD — inside the development monorepo the vendored chart module
    and runtime must stay byte-identical to the canonical copies in the shared
    render toolkit; in a standalone repo the cross-plugin half skips and only
    the local checksum verification runs."""
    if CANONICAL is not None and CANONICAL.is_dir():
        check((VENDORED / "charts.py").read_bytes() == (CANONICAL / "charts.py").read_bytes(),
              "_charts/charts.py has drifted from the canonical _shared/render/charts.py")
        canon_vendor = {p.name for p in (CANONICAL / "vendor").iterdir()
                        if p.is_file() and p.name != ".DS_Store"}
        local_vendor = {p.name for p in (VENDORED / "vendor").iterdir()
                        if p.is_file() and p.name != ".DS_Store"}
        check(canon_vendor == local_vendor,
              f"_charts/vendor file set differs: canonical={sorted(canon_vendor)} local={sorted(local_vendor)}")
        for name in sorted(canon_vendor & local_vendor):
            same = (VENDORED / "vendor" / name).read_bytes() == (CANONICAL / "vendor" / name).read_bytes()
            check(same, f"_charts/vendor/{name} has drifted from the canonical copy")
    else:
        print("skip  canonical render toolkit not found for cross-plugin drift check")
    # The checksummed runtime must be intact regardless (mirrors the toolkit's own guard).
    sums = (VENDORED / "vendor" / "SHA256SUMS").read_text().strip().splitlines()
    for line in sums:
        digest, name = line.split()
        got = hashlib.sha256((VENDORED / "vendor" / name).read_bytes()).hexdigest()
        check(got == digest, f"_charts/vendor/{name} sha256 mismatch vs SHA256SUMS")


def main():
    products, period, currency = cm3.parse_csv(str(SAMPLE))
    check(len(products) == 7, f"expected 7 products, got {len(products)}")
    check(currency == "CAD", f"currency should be CAD, got {currency}")

    ctx = cm3.compute(products, dict(INPUTS))
    by_band = ctx["by_band"]
    for band, n in EXPECTED_BANDS.items():
        got = by_band[band].n_products
        check(got == n, f"band {band}: expected {n}, got {got}")

    # No row loss: every product lands in exactly one band bucket.
    total_in_bands = sum(by_band[b].n_products for b in cm3.BAND_NAMES + ["Inactive"])
    check(total_in_bands == len(products), f"row loss: {total_in_bands} banded vs {len(products)} input")

    # Tunable cutoffs flow through compute(): lowering Excellent to 5% (and High to 2%)
    # promotes the 7.1%-CM3 product High -> Excellent and empties Average.
    tuned = cm3.compute(products, dict(INPUTS, band_exc=0.05, band_high=0.02))
    check(tuned["by_band"]["Excellent"].n_products == 2,
          f"tuned band_exc=0.05: expected 2 Excellent, got {tuned['by_band']['Excellent'].n_products}")
    check(tuned["by_band"]["Average"].n_products == 0,
          f"tuned band_high=0.02: expected 0 Average, got {tuned['by_band']['Average'].n_products}")

    # Vendor extraction from ' : Vendor' suffix.
    vendors = {p.vendor for p in products}
    check("Acme" in vendors and "Nimbus" in vendors, f"vendor extraction failed: {vendors}")

    # Empty input must not crash and yields zero totals.
    empty = cm3.compute([], dict(INPUTS))
    check(empty["totals"].conv_value == 0, "empty input should have zero revenue")

    # Vendored chart module drift guard.
    check_chart_drift()

    # Band chart colors must equal the explorer template's own band identity:
    # the .b-<Band> badge text color (var() refs resolved through :root).
    # (The pre-rebrand template used --exc/--high/... :root vars instead.)
    root_vars = dict(re.findall(r"(--[\w-]+):(#[0-9a-fA-F]{6})", cm3_html._TEMPLATE))
    for band in cm3_html.BAND_ORDER:
        cm = re.search(r"\.b-" + band + r"\{[^}]*color:(?:var\((--[\w-]+)\)|(#[0-9a-fA-F]{6}))",
                       cm3_html._TEMPLATE)
        got = (root_vars.get(cm.group(1)) if cm and cm.group(1) else (cm.group(2) if cm else None))
        check(got is not None and got.lower() == cm3_html.BAND_COLORS[band].lower(),
              f"chart color for {band} != explorer .b-{band} badge color ({got})")

    # Charts never reference the provenance 'generated' field.
    check("generated" not in json.dumps(cm3_html.CHARTS), "a chart references 'generated'")

    # Markdown: provenance params + full no-row-loss product table + chart SVGs.
    with tempfile.TemporaryDirectory() as td:
        md_path = os.path.join(td, "out.md")
        cm3.build_markdown(ctx, period, currency, md_path)
        md = Path(md_path).read_text(encoding="utf-8")
        check("ship_pct: 20" in md, "md frontmatter missing ship_pct")
        check("proc_pct: 2.9" in md, "md frontmatter missing proc_pct")
        check("generated:" in md, "md frontmatter missing generated")
        check("## All products (full)" in md, "md missing full product table")
        for p in products:
            stem = p.title.split(" : ")[0]
            check(stem in md, f"md missing product '{stem}' (row loss)")
        # Chart artifacts: every md-flagged chart written as {stem}_charts/{id}.svg,
        # referenced relatively from a "## Charts" section, and byte-deterministic
        # (same model + spec in, byte-identical SVG out — build twice and compare).
        check("## Charts" in md, "md missing Charts section")
        md_charts = [c for c in cm3_html.CHARTS if c.get("md", True)]
        svgs_first = {}
        for c in md_charts:
            rel = f"out_charts/{c['id']}.svg"
            check(f"![{c['title']}]({rel})" in md, f"md missing chart ref {rel}")
            sp = Path(td) / rel
            check(sp.is_file(), f"chart SVG not written: {rel}")
            if sp.is_file():
                svg = sp.read_text(encoding="utf-8")
                check(svg.startswith("<svg"), f"{rel} does not start with <svg")
                svgs_first[c["id"]] = svg
        md2_path = os.path.join(td, "again", "out.md")
        os.makedirs(os.path.dirname(md2_path))
        cm3.build_markdown(ctx, period, currency, md2_path)
        for cid, svg in svgs_first.items():
            again = (Path(td) / "again" / "out_charts" / f"{cid}.svg").read_text(encoding="utf-8")
            check(again == svg, f"chart {cid}.svg not byte-identical across two builds")
        # Opt-out: --no-charts writes no Charts section and no SVG dir.
        nc_path = os.path.join(td, "nc", "out.md")
        os.makedirs(os.path.dirname(nc_path))
        cm3.build_markdown(ctx, period, currency, nc_path, charts=False)
        nc = Path(nc_path).read_text(encoding="utf-8")
        check("## Charts" not in nc, "--no-charts md still has a Charts section")
        check(not (Path(td) / "nc" / "out_charts").exists(), "--no-charts still wrote SVGs")

    # HTML: self-contained (vendor blob + SVG xmlns are the only allowed opaque
    # regions) + embeds valid model + every product present + live chart hooks.
    html = cm3_html.render_html(ctx, period, currency)
    check_self_contained(html, "html")
    check(chartsmod.VENDOR_BEGIN in html, "html missing vendored chart runtime")
    check("const CHARTS = " in html and "renderCharts()" in html, "html missing live chart JS")
    check('id="chartsCard"' in html, "html missing charts card")
    check("$schema" not in html.replace(chartsmod.vendor_blob(), ""),
          "chart specs must not carry a $schema URL")
    html2 = cm3_html.render_html(ctx, period, currency)
    gen_re = re.compile(r'"generated":"[^"]*"')
    check(gen_re.sub("", html) == gen_re.sub("", html2),
          "html not deterministic modulo the generated timestamp")
    m = re.search(r'<script id="data" type="application/json">(.*?)</script>', html, re.S)
    check(m is not None, "html missing embedded data script")
    if m:
        model = json.loads(m.group(1).replace("<\\/", "</"))
        check(len(model["rows"]) == len(products), "html embedded rows != products (row loss)")
        check(abs(model["params"]["total_rev"] - ctx["totals"].conv_value) < 1e-6, "html total_rev mismatch")
        # Rollup data plumbing: full-depth taxonomy per row, vendor COGS map, source mix.
        r0 = model["rows"][0]
        check(isinstance(r0.get("catL"), list) and len(r0["catL"]) == 5, "model row missing 5-level catL")
        check(isinstance(r0.get("ptL"), list) and len(r0["ptL"]) == 5, "model row missing 5-level ptL")
        check("cat" not in r0 and "pt" not in r0, "model still carries the superseded cat/pt scalars")
        vc = model.get("vcogs")
        check(isinstance(vc, dict), "model missing vcogs vendor->COGS map")
        vendors = {p.vendor for p in products if p.vendor}
        check(vc is not None and set(vc.keys()) == vendors,
              f"vcogs vendor set {set((vc or {}).keys())} != {vendors}")
        sm = model.get("srcmix")
        check(isinstance(sm, dict) and sm, "model missing srcmix source counts")
        check(sm is not None and sum(sm.values()) == len(products), "srcmix counts != product count")
    for p in products:
        check(p.title.split(" : ")[0] in html, f"html missing product '{p.title}'")

    # Explorer rollup UI must be wired in (live JS<->Python parity of the numbers
    # is pinned separately by the dev-only run_explorer_parity_cm3.py harness).
    for marker in ("rollupData", "renderRollups", "setupRollnav", 'id="rollnav"',
                   'id="rollup"', 'id="sumkpis"', 'id="method"', "renderMethod",
                   "renderSummaryKpis"):
        check(marker in html, f"html missing rollup UI marker '{marker}'")

    # Python rollup oracle (what the live JS must reproduce): no row loss in any
    # dimension, and pinned aggregates on the single-campaign fixture.
    by_campaign, by_vendor = ctx["by_campaign"], ctx["by_vendor"]
    check(sum(b.n_products for b in by_campaign.values()) == len(products),
          "campaign rollup drops/duplicates products")
    n_vendored = sum(1 for p in products if p.vendor)
    check(sum(b.n_products for b in by_vendor.values()) == n_vendored,
          "vendor rollup product count wrong")
    for lvl, buckets in ctx["cat_levels"]:
        check(sum(b.n_products for b in buckets.values()) == len(products),
              f"category L{lvl} rollup drops/duplicates products")
    for lvl, buckets in ctx["pt_levels"]:
        check(sum(b.n_products for b in buckets.values()) == len(products),
              f"product-type L{lvl} rollup drops/duplicates products")
    check(len(by_campaign) == 1, f"fixture should have 1 campaign, got {len(by_campaign)}")
    only_camp = next(iter(by_campaign.values()))
    check(only_camp.n_products == len(products) and abs(only_camp.cm3 - ctx["totals"].cm3) < 1e-6,
          "single-campaign fixture: campaign bucket must equal totals")
    check({"Acme", "Nimbus"} <= set(by_vendor.keys()),
          f"vendor rollup missing Acme/Nimbus: {set(by_vendor.keys())}")
    # Chartless variant carries no vendor bytes and no chart chrome.
    nchtml = cm3_html.render_html(ctx, period, currency, charts=False)
    check(chartsmod.VENDOR_BEGIN not in nchtml and "chartsCard" not in nchtml
          and "/*__CHARTS__*/" not in nchtml and "/*__VENDOR__*/" not in nchtml,
          "charts=False html still carries chart hooks/vendor bytes")
    check_self_contained(nchtml, "chartless html")

    # In-Claude tuner fragment: self-contained, embeds the model, exposes the tuner
    # contract (controls + summarize kernel + Save/Export buttons), and inlines the
    # widget-flagged static chart SVG at the report defaults (small: <40KB of SVG).
    frag = cm3_html.build_widget_fragment(ctx, period, currency, brand="Test Co",
                                          csv_path=str(SAMPLE), cogs_csv=None)
    check_self_contained(frag, "widget fragment")
    widget_ids = [c["id"] for c in cm3_html.CHARTS if c.get("widget", False)]
    for cid in widget_ids:
        check(f'id="cxc_{cid}"' in frag, f"widget missing inline chart {cid}")
    nonwidget = [c["id"] for c in cm3_html.CHARTS if not c.get("widget", False)]
    for cid in nonwidget:
        check(f'id="cxc_{cid}"' not in frag, f"non-widget chart {cid} leaked into the fragment")
    frag_svgs = re.findall(r"<svg.*?</svg>", frag, re.S)
    check(len(frag_svgs) == len(widget_ids), f"widget svg count {len(frag_svgs)} != {len(widget_ids)}")
    check(all(s.startswith("<svg") for s in frag_svgs), "widget chart svg malformed")
    check(sum(len(s.encode()) for s in frag_svgs) < 40 * 1024,
          "widget chart SVG bytes exceed the 40KB budget")
    check("Shown at the report defaults" in frag, "widget chart caption missing")
    frag_nc = cm3_html.build_widget_fragment(ctx, period, currency, brand="Test Co",
                                             csv_path=str(SAMPLE), cogs_csv=None, charts=False)
    check("<svg" not in frag_nc and "cx-chart" not in frag_nc.split("</style>", 1)[1],
          "charts=False fragment still carries a chart")
    for marker in ("gx-controls", "gx-save", "gx-xlsx", "gx-html", "gx-pptx",
                   "summarize", "classify", "SPEC", "cx-data"):
        check(marker in frag, f"widget fragment missing marker '{marker}'")
    fm = re.search(r'<script id="cx-data"[^>]*>(.*?)</script>', frag, re.S)
    check(fm is not None, "widget fragment missing embedded cx-data model")
    if fm:
        wm = json.loads(fm.group(1).replace("<\\/", "</"))
        check(len(wm["rows"]) == len(products), "widget rows != products (row loss)")
        check(wm["save"]["skill"] == "cm3-by-product-report", "widget save.skill wrong")
        check(wm["save"]["filename_stem"].startswith("cm3-by-product"), "widget filename_stem wrong")

    if failures:
        print(f"FAIL — {len(failures)} problem(s):")
        for f in failures:
            print("  - " + f)
        return 1
    print(f"OK — cm3 conformance: {len(products)} products, bands {EXPECTED_BANDS}, "
          "md+html no-row-loss, html/widget self-contained, chart module drift-guarded, "
          "charts deterministic, explorer rollups wired (campaign/vendor/category/"
          "product-type + by-band + summary KPIs + methodology).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
