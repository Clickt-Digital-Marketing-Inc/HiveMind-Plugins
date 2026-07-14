"""Shared render toolkit for the google-ads-management plugin.

Public API:
    from render import build_bundle, render_md, render_html
    from render import model as render_model   # formatting + contract helpers
    from render import charts as render_charts # deterministic Vega-Lite layer

md + html are stdlib only. xlsx (render.xlsx) imports openpyxl and is loaded
lazily by build_bundle only when the 'xlsx' format is requested, so importing
this package never pulls openpyxl. Charts mirror that: render.charts is stdlib
at import time and pulls vl_convert only when a static chart SVG is rendered.

See README.md for the model and spec contracts.
"""
from .bundle import build_bundle, FORMATS
from .md import render_md
from .html import render_html
from . import charts
from . import model

__all__ = ["build_bundle", "FORMATS", "render_md", "render_html", "charts", "model"]
