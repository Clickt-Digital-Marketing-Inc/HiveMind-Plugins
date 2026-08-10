#!/usr/bin/env python3
"""Generic markdown renderer for the analytical bundle (stdlib only).

render_md(model, spec, chart_refs=None) -> str

chart_refs — optional [(chart_id, title, relpath), ...] of pre-rendered chart
SVGs (written by the bundle orchestrator into {stem}_charts/); emitted as a
"## Charts" section of relative image references so the md renders on GitHub
and in editor previews. No refs -> no section -> output unchanged.

Chrome owned here (every skill gets it identically):
  * H1 title + a provenance/params table (account, currency, windows, generated)
  * a Headline section of KPI bullets
  * optional skill narrative (e.g. the "0/0 is clean" framing)
  * each declared section as a markdown table (pipe-escaped cells)
  * a methodology footer pointing at the skill's authoritative reference

The skill supplies adapters via the spec:
  spec['md_kpis'](model)      -> [(label, value_str), ...]
  spec['md_narrative'](model) -> [line, ...]            (optional)
  spec['md_sections'](model)  -> [section, ...]         (optional)
      section = {title, note?, headers:[..], rows:[[cell,..],..],
                 aligns?:['l'|'r'|'c', ...]}   # cells are pre-formatted strings
  spec['methodology_ref']     -> str path                (optional)
"""
from __future__ import annotations

from . import model as M


def _table(headers, rows, aligns=None) -> list:
    out = ["| " + " | ".join(str(h) for h in headers) + " |"]
    sep = []
    for i in range(len(headers)):
        a = (aligns[i] if aligns and i < len(aligns) else "l")
        sep.append({"l": "---", "r": "---:", "c": ":---:"}.get(a, "---"))
    out.append("|" + "|".join(sep) + "|")
    for row in rows:
        out.append("| " + " | ".join(M.mdcell(c) for c in row) + " |")
    return out


def _assumptions_section(model: dict) -> list:
    """'Provenance & assumptions' callout, engine-owned so every skill gets it
    identically the moment it stamps model["meta"]["assumptions"] (HM-604) — []
    when there are none, so an unadopted skill renders byte-unchanged."""
    items = M.assumptions(model)
    if not items:
        return []
    L = ["## Provenance & assumptions",
         "_Every value below is assumed, proxied, or defaulted — not a confirmed "
         "client figure — unless its basis says otherwise._",
         ""]
    L.extend(_table(
        ["Parameter", "Value", "Basis", "Note"],
        [[a.get("param", ""), a.get("value", ""), M.basis_label(a.get("basis")), a.get("note", "")]
         for a in items],
        aligns=["l", "r", "l", "l"]))
    L.append("")
    return L


def render_md(model: dict, spec: dict, chart_refs=None) -> str:
    M.require_model(model)
    M.require_spec(spec)
    pr = model["provenance"]
    cur = pr.get("currency", "")
    L: list = []

    title = spec["title"]
    L.append(f"# {title} — {pr.get('client_name') or 'Account'}"
             + (f" ({pr['account_id']})" if pr.get("account_id") else ""))
    L.append("")
    L.append("| | |")
    L.append("|---|---|")
    L.append(f"| Account | {M.mdcell(pr.get('client_name', ''))} {pr.get('account_id', '')} |")
    L.append(f"| Currency | {cur or 'unspecified'} |")
    wl = spec.get("window_labels", ("90-day window", "30-day window"))
    if pr.get("window_90d"):
        L.append(f"| {wl[0]} | {pr['window_90d']} |")
    if pr.get("window_30d"):
        L.append(f"| {wl[1]} | {pr['window_30d']} |")
    L.append(f"| Generated | {pr.get('generated', '')} |")
    for label, val in (spec.get("md_params") or (lambda m: []))(model):
        L.append(f"| {label} | {M.mdcell(val)} |")
    L.append("")

    L.append("## Headline")
    for label, val in (spec.get("md_kpis") or (lambda m: []))(model):
        L.append(f"- **{label}:** {val}")
    L.append("")

    L.extend(_assumptions_section(model))

    for line in (spec.get("md_narrative") or (lambda m: []))(model):
        L.append(line)
    if (spec.get("md_narrative")):
        L.append("")

    if chart_refs:
        L.append("## Charts")
        for _cid, ctitle, relpath in chart_refs:
            L.append(f"![{M.mdcell(ctitle)}]({relpath})")
            L.append("")

    for sec in (spec.get("md_sections") or (lambda m: []))(model):
        L.append(f"## {sec['title']}")
        if sec.get("note"):
            L.append(sec["note"])
            L.append("")
        if not sec.get("rows"):
            L.append(sec.get("empty", "_None._"))
            L.append("")
            continue
        L.extend(_table(sec["headers"], sec["rows"], sec.get("aligns")))
        L.append("")

    # Full per-row table (the no-row-loss layer): every input row with a status.
    rows_sec = (spec.get("md_rows") or (lambda m: None))(model)
    if rows_sec:
        L.append(f"## {rows_sec['title']}")
        if rows_sec.get("note"):
            L.append(rows_sec["note"])
            L.append("")
        if rows_sec.get("rows"):
            L.extend(_table(rows_sec["headers"], rows_sec["rows"], rows_sec.get("aligns")))
        else:
            L.append(rows_sec.get("empty", "_No rows._"))
        L.append("")

    ref = spec.get("methodology_ref")
    L.append("---")
    # A skill may supply its own methodology footer via spec['methodology_note'];
    # otherwise fall back to the historical default (kept verbatim so skills that
    # don't set the key render byte-identically).
    foot = spec.get("methodology_note") or (
        "Conversions use the account's primary `metrics.conversions` "
        "(attribution-modeled, may be fractional).")
    if ref:
        L.append(f"Methodology and the findings-JSON schema: see `{ref}`. " + foot)
    else:
        L.append(foot)
    return "\n".join(L) + "\n"
