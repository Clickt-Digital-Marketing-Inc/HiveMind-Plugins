#!/usr/bin/env python3
"""Shared model/render contract helpers for the google-ads-management bundle.

Stdlib only. Imported by md.py, html.py, xlsx.py, and by per-skill spec modules.

The toolkit consumes two things:

  model  — the JSON-serializable output of a skill's `compute_model(findings)`.
           Minimal contract every renderer relies on:
             provenance : {client_name, account_id, currency, window_90d,
                           window_30d, generated, params}
             params     : dict of the resolved tunable parameters
             rows       : list of row dicts; EVERY input row is present and each
                          carries a "status" (e.g. "scored" / "no_benchmark").
                          No renderer may drop a row.
             summary    : dict of headline numbers
           Anything else a skill needs (benchmarks, sensitivity, near-misses …)
           lives on the model too and is surfaced through the spec's adapter
           functions — the generic renderers never reach into skill internals.

  spec   — a per-skill dict (see _shared/render/README.md for the full contract)
           describing how to render that model: filename prefix, title, the md
           sections/KPIs/narrative adapters, the HTML controls/columns/kernel,
           and the optional xlsx workbook layout.
"""
from __future__ import annotations

import re

# --------------------------------------------------------------------------
# formatting helpers (shared so every format renders numbers identically)
# --------------------------------------------------------------------------


def slugify(s) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", str(s or "")).strip("-").lower()
    return s or "account"


def money(v, cur: str = "") -> str:
    return f"{float(v):,.2f}" + (f" {cur}" if cur else "")


def pct(v) -> str:
    return f"{float(v) * 100:.2f}%"


def num(v):
    """Int when integral, else 2dp float — for impressions/clicks style values."""
    f = float(v)
    return int(f) if f.is_integer() else round(f, 2)


def mdcell(s) -> str:
    """Escape characters that break a markdown table cell. Campaign names
    routinely contain '|' (e.g. 'S | NB - UC - AB'); a literal backslash or
    newline in a cell would also corrupt the row. Backslash is escaped first so
    the escaping is not doubled, and newlines collapse to a space."""
    return (str("" if s is None else s)
            .replace("\\", "\\\\").replace("|", "\\|").replace("\n", " "))


# --------------------------------------------------------------------------
# contract guards
# --------------------------------------------------------------------------


def assert_no_row_loss(model: dict, n_input_rows: int) -> None:
    """Raise if the model dropped any input row. Renderers preserve this too:
    every row in model['rows'] is emitted by md, html, and xlsx with a status."""
    got = len(model.get("rows", []))
    if got != n_input_rows:
        raise ValueError(
            f"row-loss: model has {got} rows but {n_input_rows} were input — "
            "every input row must survive into the model with a status")


def require_model(model: dict) -> None:
    for key in ("provenance", "params", "rows", "summary"):
        if key not in model:
            raise ValueError(f"model missing required key '{key}'")
    if not isinstance(model["rows"], list):
        raise ValueError("model['rows'] must be a list")
    for i, r in enumerate(model["rows"]):
        if "status" not in r:
            raise ValueError(f"model['rows'][{i}] has no 'status' (no-row-loss contract)")


def require_spec(spec: dict) -> None:
    for key in ("slug_prefix", "title"):
        if not spec.get(key):
            raise ValueError(f"spec missing required key '{key}'")


def stem(model: dict, spec: dict, brand: str = "") -> str:
    """Canonical artifact filename stem: '<prefix>_<account-or-client>_<date>'."""
    pr = model["provenance"]
    slug = slugify(pr.get("account_id") or pr.get("client_name") or brand)
    date = slugify(pr.get("generated")) or "undated"
    return f"{spec['slug_prefix']}_{slug}_{date}"


# --------------------------------------------------------------------------
# provenance.source display (HM-572 — canonical live-pull normalization)
# --------------------------------------------------------------------------

# Canonical live-pull provenance token. Every skill's assemble_findings.py /
# *_core.py defaults meta.source (and therefore provenance["source"]) to this
# on a live Google Ads MCP pull — never "" or a per-skill spelling, so a live
# pull is never rendered unlabeled. The CSV path is always "user_csv" (stamped
# by _shared/csv_input or a skill's own assemble_from_csv) — untouched here.
LIVE_PULL_SOURCE = "mcp"

# Single friendly display label for a live pull, shared by every skill's md/
# html/xlsx "Data source" line so all 12 skills render it identically.
LIVE_PULL_LABEL = "Google Ads API (live pull)"

CSV_SOURCE = "user_csv"


def source_label(source: str, csv_label: str = "User-supplied CSV export") -> str:
    """Friendly display for provenance.source. The canonical live-pull token
    maps to LIVE_PULL_LABEL (identical across every skill); "user_csv" maps to
    the caller-supplied (skill-specific) csv_label — untouched per skill, per
    the dual-input honesty contract. Anything else (legacy/unknown) falls back
    to LIVE_PULL_LABEL rather than rendering a blank/raw token."""
    if source == CSV_SOURCE:
        return csv_label
    if source == LIVE_PULL_SOURCE:
        return LIVE_PULL_LABEL
    return source or LIVE_PULL_LABEL
