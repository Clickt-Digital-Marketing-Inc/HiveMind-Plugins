#!/usr/bin/env python3
"""Shared in-Claude tuner emitter for the google-ads-management bundle skills.

Every tunable `build_<x>_report.py` calls `emit_widget(...)` to dump the data the
hub needs to render the in-Claude tuner (a `show_widget`): the model embed +
controls/columns/kpis + the live recompute kernel + the Save-to-HiveMind context.
The hub's `references/build_widget.py` assembles that JSON into the widget HTML.

Single source of truth: the same per-skill `*_spec.SPEC` dict that the standalone
HTML explorer and the xlsx use, so the widget's live JS recompute matches the
Python model exactly.

This is a sibling module to the `render/` package. `render/` was frozen while
the bundle skills conformed to it; the freeze was lifted (2026-07-06) to add the
deterministic chart layer (`render/charts.py` + vendored runtime), guarded by a
byte-identical regression test for chartless specs in
`render/tests/test_render_toolkit.py`. Builders already put `_shared/` on
sys.path before importing, so `from widget_emit import emit_widget` resolves,
and this module's `from render import model` resolves for the same reason.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from render import charts as rcharts  # noqa: E402  (_shared is on sys.path)
from render import model as rmodel  # noqa: E402

# The widget streams to the model as tokens, so its static chart SVGs carry a
# hard size budget. The bundle's md/html charts are unaffected by these caps.
_CHARTS_WARN_BYTES = 40_000
_CHARTS_MAX_BYTES = 80_000


def _widget_charts(model, spec) -> list:
    """Static SVGs for the widget-flagged chart declarations, at default params.

    Rendered over the FULL model rows (not the trimmed embed) so the preview is
    exact. Degrades gracefully when vl-convert is missing — the widget is a
    preview; the deliverable bundle (which hard-fails instead) is built
    elsewhere. Oversized charts are an error: shrink them or drop widget:True."""
    if not any(c.get("widget", False) for c in spec.get("charts") or []):
        return []
    try:
        import vl_convert  # noqa: F401  (probe only; render imports it again)
    except ImportError:
        sys.stderr.write("WARN: vl-convert-python not installed — widget charts "
                         "omitted (the bundle's charts are built separately)\n")
        return []
    rendered = rcharts.render_spec_charts(model, spec, only="widget")
    total = sum(len(svg) for _, _, svg in rendered)
    if total >= _CHARTS_MAX_BYTES:
        raise ValueError(
            f"widget charts total {total:,} bytes (>= {_CHARTS_MAX_BYTES:,}) — the widget "
            "streams as tokens; mark fewer charts widget:True or shrink them")
    if total >= _CHARTS_WARN_BYTES:
        sys.stderr.write(f"WARN: widget charts total {total:,} bytes "
                         f"(>= {_CHARTS_WARN_BYTES:,}) — consider trimming\n")
    return [{"id": cid, "title": title, "svg": svg} for cid, title, svg in rendered]


def emit_widget(model, spec, brand, path, *, skill_name, source_prefix=None):
    """Write the tuner's data JSON for one skill run.

    model        the computed model (single source of truth)
    spec         the skill's SPEC dict (title, html_*, js_*, slug_prefix, ...)
    brand        operator-supplied brand label (falls back to provenance)
    path         output path for the widget JSON
    skill_name   the SKILL.md `name:` (e.g. "google-ads-quality-score")
    source_prefix  HiveMind source-id prefix; defaults to spec['slug_prefix'].

    Bounded embed: if the spec provides an `in_play(row, params) -> bool` predicate,
    only rows that could ever be surfaced as the controls move are embedded (the rest
    are inert in the live preview). `params` is the model's resolved params so the
    predicate can size the envelope to the reachable control range. The full-model
    `summary` is still embedded
    (authoritative, param-independent counts), and `embed["total_rows"]` carries
    the true universe size so the widget's labels stay honest. The md / html / xlsx
    deliverables are built elsewhere (build_bundle over the full model) and are
    untouched by this trim. With no `in_play`, the embed is the full row set.
    """
    pr = model["provenance"]
    prefix = source_prefix or spec.get("slug_prefix") or skill_name
    full_rows = model.get("rows", [])
    in_play = spec.get("in_play")
    em_model = model
    if in_play:
        params = model.get("params") or {}
        em_model = {**model, "rows": [r for r in full_rows if in_play(r, params)]}
    embed = (spec.get("html_embed") or (lambda m: {
        "provenance": m["provenance"], "params": m["params"],
        "summary": m["summary"], "rows": m["rows"]}))(em_model)
    embed["total_rows"] = len(full_rows)   # authoritative universe size (pre-trim)
    widget = {
        "embed": embed,
        "spec": {
            "title": spec["title"],
            "row_noun": spec.get("row_noun", "rows"),
            "controls": spec.get("html_controls", []),
            "columns": spec.get("html_columns", []),
            "kpis": spec.get("html_kpis", []),
            "window_labels": list(spec.get("window_labels", ("Window", "Scope"))),
            "about": spec.get("about", {}),
        },
        "kernel": spec.get("js_kernel", ""),
        "extra": spec.get("js_extra", ""),
        "charts": _widget_charts(model, spec),
        "save": {
            "skill": skill_name,
            "account_id": pr.get("account_id", ""),
            "brand": brand or pr.get("client_name", ""),
            "filename_stem": rmodel.stem(model, spec, brand),
            "source_id": f"{prefix}:{pr.get('account_id', '')}",
        },
    }
    # encoding pinned: ensure_ascii=False emits real non-ASCII (fr/de campaign
    # names now survive csv_input parsing), and write_text() would otherwise
    # encode with the host's preferred encoding (cp1252 / POSIX C locale).
    Path(path).write_text(json.dumps(widget, ensure_ascii=False),
                          encoding="utf-8")
