"""Obsidian-ready markdown record for the wPPC report — one of the three outputs.

Renders the SAME computed ``model`` (from ``model.build_model``) that the xlsx and
the interactive HTML render, so the three never disagree. Every value is READ from
the model; nothing is recomputed here. Deterministic: a pure function of the model
(the only non-static bytes are the vl-convert chart SVGs, themselves a pure
function of the model rows).

White-label: the record leads with the platform/account data — no vendor name, no
logo, no third-party credit.

Static charts: each of the four declared charts is rendered to an inline SVG via
``charts.render_chart_svg`` against ITS row source — the derived-weights chart from
``model['weights_table']``, the other three from ``model['segments']`` — exactly the
per-chart mapping the model carries in ``charts.row_source``.
"""

from __future__ import annotations

from pathlib import Path

from . import charts as _charts


def _c(s) -> str:
    """Escape a markdown table cell: pipes and newlines."""
    return str("" if s is None else s).replace("|", "\\|").replace("\n", " ").strip()


def _row(cells) -> str:
    return "| " + " | ".join(_c(c) for c in cells) + " |"


def _num(value, fmt="{:,.2f}"):
    """Format a number, or an em-dash for None."""
    return "—" if value is None else fmt.format(value)


def _wv_label(wv):
    """The weights-snapshot version identity (its timestamp) for the frontmatter.
    The run-metadata carries the full snapshot dict; its full inputs live in the
    ``.weights.json`` sidecar, so the record shows only the version id here."""
    if isinstance(wv, dict):
        return wv.get("timestamp") or "snapshot"
    return wv or ""


def _chart_svgs(model: dict) -> list:
    """Render every declared chart to (title, svg) against its own row source.

    The row source is the model's own ``charts.row_source`` map — segment charts
    read ``model['segments']``, the derived-weights chart reads
    ``model['weights_table']`` — so the weights chart renders from the weight rows,
    never the segment rows.
    """
    charts = model.get("charts", {})
    decls = charts.get("declarations", [])
    row_source = charts.get("row_source", {})
    out = []
    for decl in decls:
        rows_key = row_source.get(decl["id"], "segments")
        rows = model.get(rows_key, [])
        vl_spec = _charts.build_vl_spec(decl)
        svg = _charts.render_chart_svg(vl_spec, rows)
        out.append((decl["title"], svg))
    return out


def render_md(model: dict, *, animate=None) -> str:
    """Render the wPPC markdown record from a computed model.

    ``animate`` is accepted for a uniform renderer signature; a markdown record is
    static, so it is a no-op here (there is nothing to animate in plain text).
    """
    P = model["provenance"]
    MD = model["metadata"]
    SC = model["self_check"]
    DL = model["decision_lens"]
    platform = P.get("platform", "")

    L: list[str] = []

    # --- YAML frontmatter (run-metadata scalars) ---
    L += [
        "---",
        f'title: "wPPC Report — {platform}"',
        f'platform: "{platform}"',
        f"n_segments: {P.get('n_segments', 0)}",
        f"n_stabilized: {P.get('n_stabilized', 0)}",
        f'baseline_wppc: {MD.get("baseline")}',
        f'replacement_wppc: {MD.get("replacement")}',
        f'k: {MD.get("k")}',
        f'k_source: "{P.get("k_source", "")}"',
        f"self_check_pass: {str(bool(SC.get('pass'))).lower()}",
        f'telescope_sum: {SC.get("telescope_sum")}',
        f'cm3_order: {SC.get("cm3_order")}',
        f'decay_status: "{P.get("decay_status", "not-run")}"',
        f'incrementality_status: "{P.get("incrementality_status", "not-provided")}"',
        f'weights_version: "{_wv_label(P.get("weights_version"))}"',
        f'generated: "{P.get("generated", "")}"',
        "tags: [wppc, report]",
        "---",
        "",
        f"# wPPC Report — {platform}",
        "",
        f"**Platform** {platform} · **Segments** {P.get('n_segments', 0)} "
        f"({P.get('n_stabilized', 0)} stabilized) · "
        f"**Baseline wPPC** {_num(MD.get('baseline'))} · "
        f"**Replacement wPPC** {_num(MD.get('replacement'))} · "
        f"**k** {_num(MD.get('k'), '{:,.1f}')} ({P.get('k_source', '')}) · "
        f"**Generated** {P.get('generated', '')}",
        "",
    ]

    # --- decision lens ---
    L += [
        "## Decision lens",
        "",
        f"**Scale {DL.get('scale', 0)}** · **Cut {DL.get('cut', 0)}** · "
        f"**Watch {DL.get('watch', 0)}**",
        "",
        "_Scale = stabilized with MAR > 0 (confident surplus). "
        "Cut = stabilized with MAR < 0 (confident drag). "
        "Watch = not yet stabilized, or stabilized at MAR = 0._",
        "",
    ]

    # --- per-segment table ---
    L += [
        "## Segments",
        "",
        _row(["Segment", "Clicks", "Conv", "wPPC", "wPPC+", "wPPC_shrunk",
              "MAR", "Stabilized", "Closing ratio", "Decision"]),
        _row(["---"] * 10),
    ]
    for s in model["segments"]:
        L.append(_row([
            s["segment_id"],
            f"{s['clicks']:,}",
            f"{s['conversions']:,}",
            _num(s["wPPC"]),
            _num(s["wPPC+"], "{:,.0f}"),
            _num(s["wPPC_shrunk"]),
            _num(s["MAR"]),
            s["stabilized"],
            _num(s["closing_ratio"]),
            s["decision"],
        ]))
    L.append("")

    # --- derived weights + self-check ---
    L += [
        "## Derived weights",
        "",
        _row(["Funnel state", "P(purchase|S)", "PE(S)", "w(S) incremental"]),
        _row(["---", "---", "---", "---"]),
    ]
    for wrow in model["weights_table"]:
        L.append(_row([
            wrow["state"],
            _num(wrow["p"], "{:,.6f}"),
            _num(wrow["pe"], "{:,.4f}"),
            _num(wrow["w"], "{:,.4f}"),
        ]))
    L += [
        "",
        f"**Self-check** telescoped Σ w(click..purchase) = "
        f"{_num(SC.get('telescope_sum'), '{:,.4f}')} vs CM3_order "
        f"{_num(SC.get('cm3_order'), '{:,.4f}')} → "
        f"**{'PASS' if SC.get('pass') else 'FAIL'}**",
        "",
    ]

    # --- decay (parallel data; never blended into wPPC+/MAR) ---
    L += ["## Decay (two-period wPPC+ movement)", ""]
    decay = model.get("decay", {})
    if decay.get("rows"):
        L += [
            _row(["Segment", "wPPC+ prior", "wPPC+ delta", "delta %", "Trend"]),
            _row(["---", "---", "---", "---", "---"]),
        ]
        for d in decay["rows"]:
            pct = d.get("delta_pct")
            L.append(_row([
                d["segment_id"],
                _num(d.get("wPPC+_prior"), "{:,.0f}"),
                _num(d.get("wPPC+_delta"), "{:+,.0f}"),
                "—" if pct is None else f"{pct * 100:+.1f}%",
                d.get("trend") or "—",
            ]))
        L.append("")
    else:
        L += [f"_decay: {decay.get('status', 'not-run')}_", ""]

    # --- charts (static SVGs, each from its own row source) ---
    L += ["## Charts", ""]
    for title, svg in _chart_svgs(model):
        L += [f"### {title}", "", svg, ""]

    L += [
        "---",
        f"_Generated {P.get('generated', '')} · a self-contained interactive HTML "
        f"and a formula-driven .xlsx accompany this record._",
        "",
    ]
    return "\n".join(L)


def build_markdown(model: dict, path, *, animate=None) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_md(model, animate=animate), encoding="utf-8")
