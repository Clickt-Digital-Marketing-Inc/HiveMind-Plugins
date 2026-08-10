#!/usr/bin/env python3
"""Bundle orchestrator — write the md + html [+ xlsx] artifacts from one model.

build_bundle(model, spec, outdir, formats, brand="", charts=True) -> list[Path]

Dependency discipline: md and html are stdlib only. openpyxl is imported ONLY
inside the xlsx branch (via render.xlsx), so importing this orchestrator never
pulls openpyxl. The xlsx build normalizes through LibreOffice and FAILS (exit 2)
if soffice is missing — never ships a file that may not open in Excel.

Charts follow the same discipline: vl-convert is imported only when the spec
declares charts (render.charts renders the static SVGs into {stem}_charts/ and
the md references them; the html explorer gets the live vendored runtime). If
vl-convert is missing while charts are declared the build FAILS (exit 2) rather
than silently shipping a chartless report — pass charts=False (CLI: --no-charts)
to opt out explicitly.
"""
from __future__ import annotations

from pathlib import Path

from . import model as M
from .md import render_md
from .html import render_html

FORMATS = ("md", "html", "xlsx")


def build_bundle(model: dict, spec: dict, outdir: str, formats=("md", "html", "xlsx"),
                 brand: str = "", normalize: bool = True, charts: bool = True) -> list:
    M.require_model(model)
    M.require_spec(spec)
    unknown = [f for f in formats if f not in FORMATS]
    if unknown:
        raise ValueError(f"unknown format(s): {', '.join(unknown)}")
    if not charts and spec.get("charts"):
        spec = {k: v for k, v in spec.items() if k != "charts"}

    stem = M.stem(model, spec, brand)
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    written = []

    if "md" in formats:
        chart_refs = []
        if any(c.get("md", True) for c in spec.get("charts") or []):
            from . import charts as chartsmod  # lazy: vl-convert only when charts declared
            cdir = out / f"{stem}_charts"
            cdir.mkdir(exist_ok=True)
            for cid, title, svg in chartsmod.render_spec_charts(model, spec, only="md"):
                cp = cdir / f"{cid}.svg"
                cp.write_text(svg, encoding="utf-8")
                written.append(cp)
                chart_refs.append((cid, title, f"{stem}_charts/{cid}.svg"))
        p = out / f"{stem}.md"
        p.write_text(render_md(model, spec, chart_refs=chart_refs or None),
                     encoding="utf-8")
        written.append(p)
    if "html" in formats:
        p = out / f"{stem}_explorer.html"
        p.write_text(render_html(model, spec), encoding="utf-8")
        written.append(p)
    if "xlsx" in formats:
        if not spec.get("xlsx"):
            raise ValueError(f"spec '{spec['slug_prefix']}' declares no xlsx layout")
        from . import xlsx as xlsxmod  # lazy: openpyxl only loaded when xlsx requested
        p = out / f"{stem}.xlsx"
        xlsxmod.build_xlsx(model, spec, str(p), brand=brand, normalize=normalize)
        written.append(p)
    return written
