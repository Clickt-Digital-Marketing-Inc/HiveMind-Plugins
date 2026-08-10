#!/usr/bin/env python3
"""Deterministic Vega-Lite chart layer for the analytical bundle.

Charts are DECLARED in the skill spec and GENERATED here — never hand-authored.
One declaration drives both render paths:

  * static  — vl-convert (lazy import, exact-pinned) renders spec + rows to SVG
              at build time for the md report and the in-Claude tuner widget.
  * live    — the same spec JSON is embedded in the standalone explorer, where
              the vendored Vega/Vega-Lite runtime (render/vendor/, pinned to the
              same Vega-Lite minor) rebuilds the chart from the recomputed rows
              on every control change.

All aggregation/binning/filtering lives in the Vega-Lite `transform` array
inside the spec, so there is exactly ONE transform definition shared verbatim
by both paths. Chart data is always the model's row array (optionally adapted
by spec['chart_rows']); every spec reads from the named dataset "rows".

Declaration contract (spec['charts'] = [decl, ...]):

  decl = {
    "id": str,            # stable [a-z0-9_]+ slug -> filename + DOM id
    "title": str,
    "mark": ...,          # verbatim Vega-Lite
    "encoding": {...},    # verbatim Vega-Lite
    "transform": [...],   # verbatim Vega-Lite (optional)
    "width": int, "height": int,   # optional; fixed defaults below
    "md": bool,           # default True  — static SVG shipped with the md report
    "widget": bool,       # default False — static SVG inlined in the tuner widget
  }
  spec['chart_rows'] = lambda model: [...]   # optional; default model['rows']

Determinism: canonical_json (sorted keys, compact) for every serialized spec;
fixed dimensions (no autosize-by-content); the theme uses only vl-convert's
bundled font metrics; `sample` transforms and inline `data` are rejected; chart
data preserves model row order. Same model + spec in, byte-identical SVG out.

Stdlib only at import time — vl_convert is imported inside render_chart_svg,
mirroring the openpyxl discipline in render.xlsx.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

VL_VERSION = "5.20"  # must match vendor/vega-lite.min.js major.minor (see vendor/VERSIONS.md)

VENDOR_DIR = Path(__file__).resolve().parent / "vendor"
VENDOR_FILES = ("vega.min.js", "vega-lite.min.js", "embed_shim.js")  # load order matters
VENDOR_BEGIN = "/*__VENDOR_JS_BEGIN__*/"
VENDOR_END = "/*__VENDOR_JS_END__*/"

_DEFAULT_WIDTH = 640
_DEFAULT_HEIGHT = 240

# Frozen Vega-Lite config: Clickt teal primary, categorical range matching the
# explorer's badge palette, and the light-card chrome the explorer already uses.
CLICKT_THEME = {
    "background": "#ffffff",
    "font": "Helvetica, Arial, sans-serif",
    "title": {"fontSize": 13, "fontWeight": 600, "color": "#0f172a", "anchor": "start"},
    "axis": {"labelFontSize": 11, "titleFontSize": 11, "labelColor": "#475569",
             "titleColor": "#475569", "gridColor": "#eef2f7", "domainColor": "#cbd5e1",
             "tickColor": "#cbd5e1"},
    "legend": {"labelFontSize": 11, "titleFontSize": 11, "labelColor": "#475569",
               "titleColor": "#475569"},
    "range": {"category": ["#0369a1", "#7c3aed", "#15803d", "#b45309", "#b91c1c", "#64748b"]},
    "bar": {"fill": "#1f7a82"},
    "line": {"stroke": "#1f7a82"},
    "point": {"filled": True, "size": 42},
    "view": {"stroke": None},
}

_ID_RE = re.compile(r"[a-z0-9_]+\Z")


def canonical_json(obj) -> str:
    """Stable serialization: sorted keys, compact, '</' escaped so the string
    can sit inside a <script> element without closing it early."""
    return (json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            .replace("</", "<\\/"))


def build_vl_spec(chart: dict, *, theme: dict | None = None) -> dict:
    """Expand one chart declaration into a full Vega-Lite spec reading from the
    named dataset "rows". Pure function of the declaration — no data, no clock."""
    for key in ("id", "title", "mark", "encoding"):
        if not chart.get(key):
            raise ValueError(f"chart declaration missing required key '{key}'")
    if not _ID_RE.match(chart["id"]):
        raise ValueError(f"chart id '{chart['id']}' must be a [a-z0-9_]+ slug")
    if "data" in chart:
        raise ValueError(f"chart '{chart['id']}': inline 'data' is not allowed — "
                         "charts always read the model rows (named dataset 'rows')")
    transform = chart.get("transform", [])
    if any("sample" in t for t in transform):
        raise ValueError(f"chart '{chart['id']}': 'sample' transform is nondeterministic")
    spec = {
        "title": chart["title"],
        "width": chart.get("width", _DEFAULT_WIDTH),
        "height": chart.get("height", _DEFAULT_HEIGHT),
        "data": {"name": "rows"},
        "mark": chart["mark"],
        "encoding": chart["encoding"],
        "config": theme or CLICKT_THEME,
    }
    if transform:
        spec["transform"] = transform
    return spec


def chart_rows(model: dict, spec: dict) -> list:
    """The rows every chart consumes, in model order (deterministic)."""
    return (spec.get("chart_rows") or (lambda m: m["rows"]))(model)


def render_chart_svg(vl_spec: dict, rows: list) -> str:
    """Static render: inline the rows and convert to SVG via vl-convert."""
    try:
        import vl_convert  # lazy: only the static path needs it
    except ImportError:
        import sys
        sys.stderr.write(
            "ERROR: this spec declares charts but vl-convert-python is not installed.\n"
            "Install it (pip install 'vl-convert-python==1.7.0') or pass --no-charts.\n")
        sys.exit(2)
    spec = dict(vl_spec)
    spec["data"] = {"values": rows}
    return vl_convert.vegalite_to_svg(canonical_json(spec), vl_version=VL_VERSION)


def render_spec_charts(model: dict, spec: dict, *, only: str | None = None) -> list:
    """Render every declared chart at the model's default params.

    only='md' / 'widget' filters by the declaration flags (md defaults True,
    widget defaults False). Returns [(chart_id, title, svg), ...] in
    declaration order."""
    if only not in (None, "md", "widget"):
        raise ValueError(f"unknown chart filter '{only}'")
    decls = spec.get("charts") or []
    if only == "md":
        decls = [c for c in decls if c.get("md", True)]
    elif only == "widget":
        decls = [c for c in decls if c.get("widget", False)]
    if not decls:
        return []
    rows = chart_rows(model, spec)
    out = []
    for decl in decls:
        vl = build_vl_spec(decl)
        out.append((decl["id"], decl["title"], render_chart_svg(vl, rows)))
    return out


def charts_json(spec: dict) -> str:
    """Canonical JSON array of the built specs, for embedding in the explorer."""
    return canonical_json([build_vl_spec(c) for c in (spec.get("charts") or [])])


def vendor_blob() -> str:
    """The committed runtime (vega + vega-lite + embed shim) between sentinels.
    Byte-stable: the vendor files are pinned and checksummed (vendor/SHA256SUMS);
    the self-containment test verifies any embedded blob equals this exactly."""
    parts = [VENDOR_BEGIN]
    for name in VENDOR_FILES:
        parts.append((VENDOR_DIR / name).read_text(encoding="utf-8"))
    parts.append(VENDOR_END)
    return "\n".join(parts)
