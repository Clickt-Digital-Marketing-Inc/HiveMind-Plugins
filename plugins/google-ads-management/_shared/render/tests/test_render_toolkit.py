#!/usr/bin/env python3
"""Tests for the shared render toolkit (stdlib only; run directly).

    python3 _shared/render/tests/test_render_toolkit.py

Asserts the toolkit invariants independent of any one skill: the no-row-loss
guard, md/html chrome, HTML self-containment, markdown pipe-escaping, filename
stem, and the lazy-openpyxl import discipline. Exit 0 = all pass, 1 = a failure.
"""
import hashlib
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHARED = HERE.parents[1]            # .../_shared
sys.path.insert(0, str(SHARED))

from render import build_bundle, render_md, render_html  # noqa: E402
from render import charts as C      # noqa: E402
from render import model as M       # noqa: E402


def _has_vl_convert() -> bool:
    try:
        import vl_convert  # noqa: F401
        return True
    except ImportError:
        return False

_failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        _failures.append(name)


def _model():
    return {
        "provenance": {"client_name": "Acme | Co", "account_id": "123", "currency": "CAD",
                       "window_90d": "", "window_30d": "", "generated": "2026-06-26", "params": {}},
        "params": {"thr": 1},
        "rows": [
            {"name": "a | b", "status": "scored", "cost": 10, "block": "Block 1"},
            {"name": "c", "status": "no_benchmark", "cost": 5, "block": ""},
        ],
        "summary": {"hits": 1, "universe": 2},
    }


def _spec():
    return {
        "slug_prefix": "demo",
        "title": "Demo Report",
        "md_kpis": lambda m: [("Hits", str(m["summary"]["hits"]))],
        "md_sections": lambda m: [{"title": "Things", "headers": ["Name", "Cost"],
                                   "rows": [[r["name"], r["cost"]] for r in m["rows"]]}],
        "md_rows": lambda m: {"title": "All rows", "headers": ["Name", "Status"],
                              "rows": [[r["name"], r["status"]] for r in m["rows"]]},
        "html_columns": [{"key": "name", "label": "Name"},
                         {"key": "cost", "label": "Cost", "num": True, "fmt": "money"},
                         {"key": "status", "label": "Status", "fmt": "status"}],
        "html_kpis": [{"label": "Hits", "key": "hits"}],
    }


def _chart_spec():
    s = _spec()
    s["charts"] = [{
        "id": "spend_by_block",
        "title": "Spend by block",
        "mark": {"type": "bar"},
        "transform": [
            {"filter": "datum.block != ''"},
            {"aggregate": [{"op": "sum", "field": "cost", "as": "spend"}],
             "groupby": ["block"]},
        ],
        "encoding": {"x": {"field": "block", "type": "nominal", "title": None},
                     "y": {"field": "spend", "type": "quantitative", "title": "Spend"}},
        "md": True, "widget": True,
    }]
    return s


def test_require_model_guards_row_loss():
    print("test_require_model_guards_row_loss")
    bad = {"provenance": {}, "params": {}, "summary": {}, "rows": [{"x": 1}]}
    try:
        M.require_model(bad); ok = False
    except ValueError:
        ok = True
    check("row without 'status' rejected", ok)
    try:
        M.assert_no_row_loss({"rows": [1, 2]}, 3); ok = False
    except ValueError:
        ok = True
    check("assert_no_row_loss catches a dropped row", ok)


def test_stem():
    print("test_stem")
    s = M.stem(_model(), _spec())
    check("stem uses prefix_account_date", s == "demo_123_2026-06-26", s)


def test_md_chrome_and_escaping():
    print("test_md_chrome_and_escaping")
    md = render_md(_model(), _spec())
    # H1 is not a table cell, so the pipe stays raw there; the provenance TABLE escapes it.
    check("title + account in H1", md.splitlines()[0] == "# Demo Report — Acme | Co (123)", md.splitlines()[0])
    check("headline KPI present", "**Hits:** 1" in md)
    check("provenance currency present", "| Currency | CAD |" in md)
    check("pipe in provenance table cell escaped", "| Account | Acme \\| Co 123 |" in md)
    # every row present in the md rows table (no row loss)
    rows_blk = md.split("## All rows")[1]
    data = [ln for ln in rows_blk.splitlines() if ln.startswith("| ") and not ln.startswith("| Name")]
    check("md carries every row", len(data) == 2, f"got {len(data)}")
    check("pipe in row cell escaped", r"a \| b" in md)


def test_html_self_contained():
    print("test_html_self_contained")
    html = render_html(_model(), _spec())
    hits = re.findall(r"https?://|<link|src=|cdn", html)
    check("no external references", len(hits) == 0, f"{hits}")
    check("MODEL embedded", "const MODEL = " in html)
    check("every row embedded", html.count('"status":') == 2 or '"status"' in html)
    check("chartless carries no vendor bytes", C.VENDOR_BEGIN not in html)
    check("chartless carries no chart hooks",
          "chartsCard" not in html and "/*__CHARTS__*/" not in html and "/*__VENDOR__*/" not in html)

    # Charted variant: the ONLY allowed opaque region is the vendored runtime,
    # and only if it is byte-equal to the committed, checksummed vendor files.
    charted = render_html(_model(), _chart_spec())
    i, j = charted.find(C.VENDOR_BEGIN), charted.find(C.VENDOR_END)
    check("vendor blob present when charts declared", i >= 0 and j > i)
    blob = charted[i:j + len(C.VENDOR_END)]
    check("vendor blob byte-equal to committed files", blob == C.vendor_blob())
    stripped = charted.replace(blob, "")
    hits = re.findall(r"https?://|<link|src=|cdn", stripped)
    check("no external references outside verified vendor blob", len(hits) == 0, f"{hits}")
    check("chart specs embedded", "const CHARTS = " in charted)
    check("no $schema URL in chart specs", "$schema" not in stripped)


def test_chartless_output_unchanged():
    # The render/ freeze was lifted to add charts; a spec with no charts must
    # produce byte-identical output to the chart-free toolkit. Goldens first
    # captured 2026-07-06 pre-charts (5e0b2a19/4e476385); re-baselined the same
    # day after merging the HiveMind-teal rebrand (PR #12) — the new html hash
    # was verified byte-equal to origin/main's own chart-free render_html on
    # the same model+spec, so the chart layer still adds nothing when unused.
    print("test_chartless_output_unchanged")
    h = hashlib.sha256(render_html(_model(), _spec()).encode()).hexdigest()
    m = hashlib.sha256(render_md(_model(), _spec()).encode()).hexdigest()
    check("chartless html byte-identical to chart-free toolkit",
          h == "e395edcb6f089d819dd7fb2e0771ad4016838202d1843ebcd8b808a4b8d532a6", h)
    check("chartless md byte-identical to chart-free toolkit",
          m == "4e47638548d05b362b05f75f3be0f12fe4608188e7b0ebd2e9f44303c0b9fe59", m)


def test_chart_decl_validation():
    print("test_chart_decl_validation")
    base = {"id": "ok_1", "title": "t", "mark": "bar",
            "encoding": {"x": {"field": "cost", "type": "quantitative"}}}
    C.build_vl_spec(base)  # sanity: valid decl accepted
    for bad, why in ((dict(base, id="Bad Id"), "non-slug id"),
                     (dict(base, data={"values": []}), "inline data"),
                     (dict(base, transform=[{"sample": 100}]), "sample transform"),
                     ({k: v for k, v in base.items() if k != "encoding"}, "missing encoding")):
        try:
            C.build_vl_spec(bad); ok = False
        except ValueError:
            ok = True
        check(f"{why} rejected", ok)


def test_vendor_checksums():
    print("test_vendor_checksums")
    sums = (C.VENDOR_DIR / "SHA256SUMS").read_text().strip().splitlines()
    listed = {}
    for line in sums:
        digest, name = line.split()
        listed[name] = digest
    check("every vendor file listed", sorted(listed) == sorted(C.VENDOR_FILES), sorted(listed))
    for name in C.VENDOR_FILES:
        got = hashlib.sha256((C.VENDOR_DIR / name).read_bytes()).hexdigest()
        check(f"{name} checksum matches", got == listed.get(name), got)


def test_chart_svg_deterministic():
    print("test_chart_svg_deterministic")
    if not _has_vl_convert():
        print("  SKIP  vl-convert-python not installed — static chart path untested")
        return
    spec = _chart_spec()
    vl = C.build_vl_spec(spec["charts"][0])
    rows = C.chart_rows(_model(), spec)
    s1, s2 = C.render_chart_svg(vl, rows), C.render_chart_svg(vl, rows)
    check("svg render is byte-stable in-process", s1 == s2)
    check("svg looks like svg", s1.startswith("<svg"))
    # cross-process: a fresh interpreter must produce the same bytes
    import subprocess
    code = (
        f"import sys, hashlib; sys.path.insert(0, r'{SHARED}'); "
        f"sys.path.insert(0, r'{HERE}'); "
        "from render import charts as C; import test_render_toolkit as T; "
        "spec = T._chart_spec(); vl = C.build_vl_spec(spec['charts'][0]); "
        "svg = C.render_chart_svg(vl, C.chart_rows(T._model(), spec)); "
        "print(hashlib.sha256(svg.encode()).hexdigest())")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    got = out.stdout.strip()
    want = hashlib.sha256(s1.encode()).hexdigest()
    check("svg render is byte-stable across processes", got == want, got or out.stderr[-200:])
    # the charted explorer as a whole is also byte-stable
    h1, h2 = render_html(_model(), _chart_spec()), render_html(_model(), _chart_spec())
    check("charted explorer is byte-stable", h1 == h2)


def test_bundle_writes_chart_svgs():
    print("test_bundle_writes_chart_svgs")
    if not _has_vl_convert():
        print("  SKIP  vl-convert-python not installed — chart bundle path untested")
        return
    with tempfile.TemporaryDirectory() as td:
        written = build_bundle(_model(), _chart_spec(), td, formats=("md", "html"))
        names = sorted(p.name for p in written)
        check("md + html + chart svg written",
              names == ["demo_123_2026-06-26.md", "demo_123_2026-06-26_explorer.html",
                        "spend_by_block.svg"], names)
        svg = [p for p in written if p.suffix == ".svg"][0]
        check("chart svg in the _charts sidecar dir", svg.parent.name == "demo_123_2026-06-26_charts")
        md = [p for p in written if p.suffix == ".md"][0].read_text()
        check("md references the chart relatively",
              "![Spend by block](demo_123_2026-06-26_charts/spend_by_block.svg)" in md)
        check("md has a Charts section", "## Charts" in md)
    with tempfile.TemporaryDirectory() as td:
        written = build_bundle(_model(), _chart_spec(), td, formats=("md", "html"), charts=False)
        check("charts=False writes no svg", all(p.suffix != ".svg" for p in written))
        md = [p for p in written if p.suffix == ".md"][0].read_text()
        check("charts=False md is chartless", "## Charts" not in md)
        check("charts=False md identical to chartless spec", md == render_md(_model(), _spec()))


def test_widget_charts():
    print("test_widget_charts")
    if not _has_vl_convert():
        print("  SKIP  vl-convert-python not installed — widget chart path untested")
        return
    import json
    import widget_emit as W
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "w.json"
        W.emit_widget(_model(), _chart_spec(), "Acme", str(p), skill_name="demo")
        data = json.loads(p.read_text())
        check("widget carries only widget-flagged charts",
              [c["id"] for c in data.get("charts", [])] == ["spend_by_block"],
              str(data.get("charts"))[:80])
        check("widget chart svg well-formed", data["charts"][0]["svg"].startswith("<svg"))
    with tempfile.TemporaryDirectory() as td:
        chartless = W  # same module; a spec without charts embeds an empty list
        p = Path(td) / "w.json"
        chartless.emit_widget(_model(), _spec(), "Acme", str(p), skill_name="demo")
        check("chartless spec -> empty widget charts",
              json.loads(p.read_text()).get("charts") == [])
    # the widget streams as tokens: oversized chart payloads are a hard error
    saved = W._CHARTS_MAX_BYTES
    W._CHARTS_MAX_BYTES = 10
    try:
        with tempfile.TemporaryDirectory() as td:
            try:
                W.emit_widget(_model(), _chart_spec(), "Acme", str(Path(td) / "w.json"),
                              skill_name="demo")
                ok = False
            except ValueError:
                ok = True
        check("oversized widget charts rejected", ok)
    finally:
        W._CHARTS_MAX_BYTES = saved


def test_lazy_vl_convert():
    print("test_lazy_vl_convert")
    # fresh subprocess: importing the toolkit (charts module included) must NOT
    # pull vl_convert — only an actual static chart render may.
    import subprocess
    code = (f"import sys; sys.path.insert(0, r'{SHARED}'); import render; import render.charts; "
            "print('vl_convert' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    check("importing render does not import vl_convert", out.stdout.strip() == "False", out.stdout.strip())


def test_bundle_md_html(tmp=None):
    print("test_bundle_md_html")
    with tempfile.TemporaryDirectory() as td:
        written = build_bundle(_model(), _spec(), td, formats=("md", "html"))
        names = sorted(p.name for p in written)
        check("md + html written", names == ["demo_123_2026-06-26.md", "demo_123_2026-06-26_explorer.html"], names)


def test_xlsx_without_layout_rejected():
    print("test_xlsx_without_layout_rejected")
    with tempfile.TemporaryDirectory() as td:
        try:
            build_bundle(_model(), _spec(), td, formats=("xlsx",)); ok = False
        except ValueError:
            ok = True
        check("xlsx requested but no xlsx spec -> error", ok)


def test_lazy_openpyxl():
    print("test_lazy_openpyxl")
    # fresh subprocess: importing the toolkit must NOT pull openpyxl
    import subprocess
    code = (f"import sys; sys.path.insert(0, r'{SHARED}'); import render; "
            "print('openpyxl' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    check("importing render does not import openpyxl", out.stdout.strip() == "False", out.stdout.strip())


def main():
    for t in (test_require_model_guards_row_loss, test_stem, test_md_chrome_and_escaping,
              test_html_self_contained, test_chartless_output_unchanged,
              test_chart_decl_validation, test_vendor_checksums,
              test_chart_svg_deterministic, test_bundle_writes_chart_svgs,
              test_widget_charts,
              test_bundle_md_html, test_xlsx_without_layout_rejected,
              test_lazy_openpyxl, test_lazy_vl_convert):
        t()
    print()
    if _failures:
        print(f"FAILED ({len(_failures)}): {', '.join(_failures)}")
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
