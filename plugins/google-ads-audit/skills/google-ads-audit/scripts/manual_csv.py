#!/usr/bin/env python3
# Copyright (c) 2026 Clickt Digital Marketing Inc. All rights reserved.
"""Parse Google Ads **UI CSV exports** for the no-MCP (manual) audit path.

The Google Ads web UI's "Download → .csv" files differ from API output in
every way that matters, all verified against real exports (2026-07):

- two preamble lines before the header: a report title, then the date range
  (e.g. ``"April 1, 2026 - July 11, 2026"``);
- cells may contain embedded newlines inside quotes ("Ad strength details");
- numbers arrive as display strings: ``"18,632"``, ``52.76%``, ``CA$0.00``;
- missing values are ``--`` (often with a leading space);
- footer rows start with ``Total:`` in the first column and must be dropped.

Adapters convert rows into the SAME flat dotted-key dicts the raw-MCP parser
produces (``campaign.name``, ``metrics.cost_micros`` — micros synthesized from
currency units), so `concentration.compute_concentration` and everything
downstream run identically on either input path. Files are parsed verbatim —
numbers never pass through the model (transcription firewall).

Stdlib only.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path


class ManualCsvError(ValueError):
    """A UI export file is missing, malformed, or the wrong report."""


# Exact column names each report must carry (from real exports; the UI names
# are stable per language — this module assumes English exports).
REQUIRED_COLUMNS = {
    "campaigns": ["Campaign", "Campaign type", "Cost", "Conversions"],
    "keywords": ["Keyword", "Match type", "Cost", "Conversions"],
    "search_terms": ["Search term", "Cost", "Conversions"],
}


def ui_num(v) -> float:
    """Coerce a UI display value to float.

    Handles: '' / '--' / ' --' -> 0.0; thousands separators ('2,791.40');
    percentages ('52.76%' -> 52.76); currency prefixes ('CA$0.00' -> 0.0)."""
    if v is None:
        return 0.0
    s = str(v).strip()
    if not s or s == "--":
        return 0.0
    s = s.replace(",", "").rstrip("%")
    s = re.sub(r"^[A-Za-z]{0,3}\$", "", s)  # CA$ / US$ / $ prefixes
    try:
        return float(s)
    except ValueError:
        return 0.0


def ui_frac(v) -> tuple[float | None, str | None]:
    """Percent display value -> (fraction 0-1, approx marker).

    '52.76%' -> (0.5276, None); '< 10%' -> (0.10, '<'); '> 90%' -> (0.90, '>');
    '--'/'' -> (None, None). Fractions match the raw GAQL scale so downstream
    consumers never see mixed units."""
    if v is None:
        return None, None
    s = str(v).strip()
    if not s or s == "--":
        return None, None
    approx = None
    if s[0] in "<>":
        approx = s[0]
        s = s[1:].strip()
    s = s.replace(",", "").rstrip("%").strip()
    try:
        return float(s) / 100.0, approx
    except ValueError:
        return None, None


def ui_int_or_none(v):
    """'7' -> 7; ' --'/'' -> None (matches raw-path field absence)."""
    if v is None:
        return None
    s = str(v).strip()
    if not s or s == "--":
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def _put_frac(d: dict, row: dict, col: str, key: str) -> None:
    """Set d[key] from a UI percent column when present; record bound markers."""
    if col not in row:
        return
    val, approx = ui_frac(row.get(col))
    if val is None:
        return
    d[key] = val
    if approx:
        d.setdefault("_approx", []).append(f"{col} reported as '{approx} {val * 100:g}%'")


def _put_num(d: dict, row: dict, col: str, key: str, *, micros_scale: bool = False) -> None:
    """Set d[key] from a numeric UI column when the column exists and parses."""
    if col not in row:
        return
    s = str(row.get(col) or "").strip()
    if not s or s == "--":
        return
    v = ui_num(s)
    d[key] = round(v * 1_000_000) if micros_scale else v


def _put_str(d: dict, row: dict, col: str, key: str) -> None:
    s = str(row.get(col) or "").strip()
    if col in row and s and s != "--":
        d[key] = s


def load_ui_csv(path: str, *, kind: str) -> tuple[list[dict], dict]:
    """Read a Google Ads UI export -> (rows, meta).

    rows — list of {header: cell} dicts, Total:/empty rows excluded.
    meta — {"title": str, "date_range": str, "n_rows_raw": int, "file": name}.
    kind — key into REQUIRED_COLUMNS; mismatched columns raise ManualCsvError
    ("is this the right report?"), mirroring the raw-path require_fields."""
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8-sig")  # UI exports may carry a BOM
    except FileNotFoundError as e:
        raise ManualCsvError(f"export file not found: {path}") from e
    raw = list(csv.reader(text.splitlines(keepends=True)))
    if not raw:
        raise ManualCsvError(f"{path}: file is empty")

    header_idx = next((i for i, r in enumerate(raw) if len(r) >= 5), None)
    if header_idx is None:
        raise ManualCsvError(f"{path}: no header row found — is this a Google Ads "
                             "UI .csv export (Download → .csv)?")
    header = [h.strip() for h in raw[header_idx]]
    title = raw[0][0].strip() if raw[0] else ""
    date_range = ""
    for r in raw[1:header_idx]:
        if r and " - " in r[0]:
            date_range = r[0].strip()
            break

    missing = [c for c in REQUIRED_COLUMNS[kind] if c not in header]
    if missing:
        raise ManualCsvError(
            f"{path}: missing column(s) {', '.join(missing)} — is this the "
            f"{kind.replace('_', ' ')} report, exported with the required columns?")

    rows = []
    for r in raw[header_idx + 1:]:
        if not r or not any(c.strip() for c in r):
            continue
        if r[0].strip().startswith("Total:"):
            continue
        rows.append({header[i]: (r[i] if i < len(r) else "") for i in range(len(header))})
    return rows, {"title": title, "date_range": date_range,
                  "n_rows_raw": len(rows), "file": p.name}


def _money_fields(cost: float, conv: float) -> dict:
    # Synthesize micros so the concentration pipeline is identical for both paths.
    return {"metrics.cost_micros": round(cost * 1_000_000),
            "metrics.conversions": conv}


def campaigns_rows(path: str) -> tuple[list[dict], dict]:
    """Campaign report -> dotted-key rows (campaign.name, channel type, money)."""
    rows, meta = load_ui_csv(path, kind="campaigns")
    out = []
    for r in rows:
        name = (r.get("Campaign") or "").strip()
        if not name or name == "--":
            continue
        d = {"campaign.name": name,
             "campaign.advertising_channel_type": (r.get("Campaign type") or "").strip()}
        d.update(_money_fields(ui_num(r.get("Cost")), ui_num(r.get("Conversions"))))
        # Optional columns (raw-canonical scale) — these power the pre-scorer.
        _put_str(d, r, "Bid strategy type", "campaign.bidding_strategy_type")
        _put_str(d, r, "Campaign status", "campaign.status")
        _put_num(d, r, "Impr.", "metrics.impressions")
        _put_num(d, r, "Clicks", "metrics.clicks")
        _put_num(d, r, "Conv. value", "metrics.conversions_value")
        _put_num(d, r, "Avg. CPC", "metrics.average_cpc", micros_scale=True)
        _put_frac(d, r, "CTR", "metrics.ctr")
        _put_frac(d, r, "Search impr. share", "metrics.search_impression_share")
        _put_frac(d, r, "Search lost IS (budget)", "metrics.search_budget_lost_impression_share")
        _put_frac(d, r, "Search lost IS (rank)", "metrics.search_rank_lost_impression_share")
        out.append(d)
    return out, meta


def keywords_rows(path: str) -> tuple[list[dict], dict]:
    """Search keyword report -> dotted-key rows (text kept verbatim, incl. the
    UI's ""quoted""/[bracketed] decorations — deterministic either way)."""
    rows, meta = load_ui_csv(path, kind="keywords")
    out = []
    for r in rows:
        text = (r.get("Keyword") or "").strip()
        if not text or text == "--":
            continue
        d = {"ad_group_criterion.keyword.text": text,
             "ad_group_criterion.keyword.match_type": (r.get("Match type") or "").strip()}
        d.update(_money_fields(ui_num(r.get("Cost")), ui_num(r.get("Conversions"))))
        _put_str(d, r, "Campaign", "campaign.name")
        _put_str(d, r, "Ad group", "ad_group.name")
        _put_str(d, r, "Status", "ad_group_criterion.status")
        _put_str(d, r, "Exp. CTR", "ad_group_criterion.quality_info.search_predicted_ctr")
        _put_str(d, r, "Landing page exp.", "ad_group_criterion.quality_info.post_click_quality_score")
        _put_str(d, r, "Ad relevance", "ad_group_criterion.quality_info.creative_quality_score")
        _put_num(d, r, "Impr.", "metrics.impressions")
        _put_num(d, r, "Clicks", "metrics.clicks")
        qs = ui_int_or_none(r.get("Quality Score")) if "Quality Score" in r else None
        if qs is not None:
            d["ad_group_criterion.quality_info.quality_score"] = qs
        out.append(d)
    return out, meta


def search_terms_rows(path: str) -> tuple[list[dict], dict]:
    """Search terms report -> dotted-key rows (includes PMax-sourced terms,
    which the UI labels Match type = 'Performance Max')."""
    rows, meta = load_ui_csv(path, kind="search_terms")
    out = []
    for r in rows:
        term = (r.get("Search term") or "").strip()
        if not term or term == "--":
            continue
        d = {"search_term_view.search_term": term}
        d.update(_money_fields(ui_num(r.get("Cost")), ui_num(r.get("Conversions"))))
        _put_str(d, r, "Match type", "segments.search_term_match_type")
        _put_str(d, r, "Added/Excluded", "search_term_view.status")
        _put_str(d, r, "Campaign", "campaign.name")
        _put_num(d, r, "Clicks", "metrics.clicks")
        out.append(d)
    return out, meta
