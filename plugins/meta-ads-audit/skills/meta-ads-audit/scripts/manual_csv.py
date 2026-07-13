#!/usr/bin/env python3
# Copyright (c) 2026 Clickt Digital Marketing Inc. All rights reserved.
"""Parse Meta Ads Manager **UI CSV exports** for the no-MCP (manual) audit path.

NEEDS-REAL-EXPORT-VALIDATION: the column names in this module are encoded from
the documented Ads Manager export format ("Export table data" -> .csv), NOT yet
validated against a real export file. Column spellings, the summary-row shape,
and the ranking value strings must be confirmed against genuine exports before
this path is trusted for client work; until then any mismatch surfaces loudly
through the REQUIRED_COLUMNS wrong-report guard. English exports assumed.

What this module assumes about Ads Manager exports (defensively coded):

- header on row 1 (a defensive header-row scan is retained anyway);
- currency-bearing columns carry the account currency as a parenthesised
  suffix: ``Amount spent (CAD)``, ``CPM (cost per 1,000 impressions) (CAD)`` —
  matched by prefix via `_col`;
- every data row carries ``Reporting starts`` / ``Reporting ends`` dates;
- a summary row whose level-name cell is empty or reads ``Results from …``;
- cells may contain embedded newlines inside quotes (entity names);
- numbers are plain (thousands commas tolerated); missing values are ``''``,
  ``--``, ``-``, or an em/en dash;
- rankings arrive as ``Above average`` / ``Average`` /
  ``Below average (bottom 20% of ads)`` / ``Not enough data``.

Adapters convert rows into the SAME canonical flat dicts `meta_rows.normalize`
produces (CONTRACTS.md §1: ``name``, ``spend``, ``impressions``, ``results`` +
``results_indicator`` + ``conv_results``, ISO ``date_start``/``date_stop``, …;
absent = key omitted). Files are parsed verbatim — numbers never pass through
the model (transcription firewall). Rows are returned sorted spend-desc then
name-asc (deterministic entity ordering).

Adapter return shape (all three adapters; documented for build_audit.py):

    campaigns_rows(path) -> (rows, meta)
    adsets_rows(path)    -> (rows, meta)
    ads_rows(path)       -> (rows, meta)

    rows — list[dict] of canonical normalized rows (summary rows dropped).
    meta — {
        "window":      str,        # "YYYY-MM-DD – YYYY-MM-DD" from
                                   # min(Reporting starts)–max(Reporting ends);
                                   # "" when no row dates parsed
        "window_days": int | None, # inclusive day count (CR-07 true bands
                                   # unlock iff <= 8); None when no window
        "n_rows_raw":  int,        # data rows kept (post summary-row drop)
        "file":        str,        # basename, for provenance display
        "stamp":       dict,       # {"file","sha256","bytes"} provenance stamp
    }

The 2-tuple mirrors google's ``rows, meta = _CSV_ADAPTERS[key](path)`` wiring;
the CSV path's window label is ``meta["window"]`` (google: ``date_range``).

Stdlib only. Deterministic: no wall clock, no locale-dependent parsing.
"""
from __future__ import annotations

import csv
import datetime
import hashlib
import re
from pathlib import Path


class ManualCsvError(ValueError):
    """A UI export file is missing, malformed, or the wrong report."""


# Required column prefixes per level (prefix-matched via _col so the
# currency-suffixed ``Amount spent (CAD)`` header satisfies ``Amount spent``).
REQUIRED_COLUMNS = {
    "campaigns": ["Campaign name", "Amount spent", "Impressions", "Results"],
    "adsets": ["Ad set name", "Amount spent", "Impressions", "Results"],
    "ads": ["Ad name", "Amount spent", "Impressions", "Results"],
}
_NAME_COLUMN = {"campaigns": "Campaign name", "adsets": "Ad set name",
                "ads": "Ad name"}

# Cell values that mean "absent" (key omitted, matching the raw path).
_ABSENT = {"", "-", "--", "—", "–"}  # em dash / en dash

_MONTHS = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
           "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
           "november": 11, "december": 12}

# Indicator substrings that mark NON-conversion results (SHAPE-NOTES rule;
# mirrors meta_rows.is_conversion_indicator).
_NON_CONVERSION = ("reach", "video", "impression", "recall", "engagement",
                   "view", "like", "follow", "click")

_RANK_CANON = [("above average", "ABOVE_AVERAGE"),
               ("below average", "BELOW_AVERAGE"),
               ("average", "AVERAGE")]  # checked in order: prefixes overlap


def _col(header: list[str], prefix: str) -> str | None:
    """First header matching ``prefix`` exactly or as ``prefix (…)``.

    ``_col(h, "Amount spent")`` matches ``Amount spent (CAD)`` but not
    ``Amount spent per result``; exact matches win column-order ties."""
    for h in header:
        if h == prefix or h.startswith(prefix + " ("):
            return h
    return None


def _is_absent(v) -> bool:
    return v is None or str(v).strip() in _ABSENT


def _num(v) -> float | None:
    """Plain UI number -> float, or None when absent/unparseable.

    Handles thousands commas ('583,301'), a trailing '%' (value returned on
    the percent scale — caller decides whether to /100), NBSP, and a
    defensive currency prefix ('CA$1,023.31')."""
    if _is_absent(v):
        return None
    s = str(v).strip().replace("\u00a0", " ").replace(",", "")
    s = s.rstrip("%").strip()
    s = re.sub(r"^[A-Za-z]{0,3}\$", "", s)
    try:
        return float(s)
    except ValueError:
        return None


def _parse_date(v) -> datetime.date | None:
    """Export date cell -> date. Accepts ISO '2026-06-11' (the documented
    Reporting starts/ends format) plus '11 June 2026' / 'June 11, 2026'
    fallbacks via an explicit month map (never locale-dependent)."""
    if _is_absent(v):
        return None
    s = str(v).strip().replace("\u00a0", " ")
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        pass
    m = re.match(r"^(\d{1,2})\s+([A-Za-z]+),?\s+(\d{4})$", s)   # 11 June 2026
    if m:
        day, month_name, year = m.group(1), m.group(2), m.group(3)
    else:
        m = re.match(r"^([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})$", s)  # June 11, 2026
        if not m:
            return None
        day, month_name, year = m.group(2), m.group(1), m.group(3)
    month = _MONTHS.get(month_name.lower())
    if month is None:
        return None
    try:
        return datetime.date(int(year), month, int(day))
    except ValueError:
        return None


def _is_conversion_indicator(label: str) -> bool:
    low = label.lower()
    return not any(tok in low for tok in _NON_CONVERSION)


def _canon_ranking(v) -> str | None:
    """'Below average (bottom 20% of ads)' -> 'BELOW_AVERAGE'; '--', blank,
    'Not enough data', anything unrecognised -> None (key omitted)."""
    if _is_absent(v):
        return None
    low = str(v).strip().lower()
    for prefix, canon in _RANK_CANON:
        if low.startswith(prefix):
            return canon
    return None


def _file_stamp(path: str) -> dict:
    """Provenance stamp — same shape as meta_rows.file_stamp / google's."""
    p = Path(path)
    return {"file": p.name,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "bytes": p.stat().st_size}


def _put_num(d: dict, row: dict, header: list[str], prefix: str, key: str) -> None:
    col = _col(header, prefix)
    if col is None:
        return
    v = _num(row.get(col))
    if v is not None:
        d[key] = v


def _put_str(d: dict, row: dict, header: list[str], prefix: str, key: str) -> None:
    col = _col(header, prefix)
    if col is None:
        return
    s = str(row.get(col) or "").strip()
    if s and not _is_absent(s):
        d[key] = s


def load_ui_csv(path: str, *, level: str) -> tuple[list[str], list[dict], dict]:
    """Read a Meta Ads Manager export -> (header, rows, stamp).

    header — stripped header cells (row 1; defensive scan retained).
    rows — list of {header: cell} dicts; summary rows (empty level-name cell
    or one starting with 'Results from') are dropped.
    level — key into REQUIRED_COLUMNS; missing required columns raise
    ManualCsvError ('is this the right report?')."""
    if level not in REQUIRED_COLUMNS:
        raise ManualCsvError(f"unknown level {level!r} (expected one of "
                             f"{', '.join(sorted(REQUIRED_COLUMNS))})")
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8-sig")  # exports may carry a BOM
    except FileNotFoundError as e:
        raise ManualCsvError(f"export file not found: {path}") from e
    raw = list(csv.reader(text.splitlines(keepends=True)))
    if not raw:
        raise ManualCsvError(f"{path}: file is empty")

    name_col_prefix = _NAME_COLUMN[level]
    # Header is expected on row 1; scan defensively for the first row that
    # carries the level-name column, falling back to the first wide row so
    # the REQUIRED_COLUMNS guard below can name what is missing.
    header_idx = next(
        (i for i, r in enumerate(raw)
         if _col([c.strip() for c in r], name_col_prefix) is not None), None)
    if header_idx is None:
        header_idx = next((i for i, r in enumerate(raw) if len(r) >= 4), None)
    if header_idx is None:
        raise ManualCsvError(f"{path}: no header row found — is this a Meta "
                             "Ads Manager .csv export (Export table data)?")
    header = [h.strip() for h in raw[header_idx]]

    missing = [c for c in REQUIRED_COLUMNS[level] if _col(header, c) is None]
    if missing:
        raise ManualCsvError(
            f"{path}: missing column(s) {', '.join(missing)} — is this the "
            f"{level} report, exported with the required columns?")

    name_col = _col(header, name_col_prefix)
    rows = []
    for r in raw[header_idx + 1:]:
        if not r or not any(c.strip() for c in r):
            continue
        row = {header[i]: (r[i] if i < len(r) else "") for i in range(len(header))}
        name = str(row.get(name_col) or "").strip()
        # Summary/total row: level-name cell empty or "Results from N …".
        if not name or name.startswith("Results from") or name in _ABSENT:
            continue
        rows.append(row)
    return header, rows, _file_stamp(path)


def _normalize_row(row: dict, header: list[str], *, level: str) -> dict:
    """One export row -> canonical flat dict (CONTRACTS.md §1 keys)."""
    d: dict = {"name": str(row.get(_col(header, _NAME_COLUMN[level])) or "").strip()}

    _put_num(d, row, header, "Amount spent", "spend")
    _put_num(d, row, header, "Impressions", "impressions")
    _put_num(d, row, header, "Reach", "reach")
    _put_num(d, row, header, "Frequency", "frequency")
    _put_num(d, row, header, "Clicks (all)", "clicks")
    _put_num(d, row, header, "Link clicks", "link_clicks")
    _put_num(d, row, header, "ThruPlays", "thruplay")
    _put_num(d, row, header, "Video plays at 25%", "video_p25")
    _put_num(d, row, header, "Video plays at 50%", "video_p50")
    _put_num(d, row, header, "Video plays at 75%", "video_p75")
    _put_num(d, row, header, "Video plays at 100%", "video_p100")

    _put_str(d, row, header, "Objective", "objective")
    _put_str(d, row, header, "Bid strategy", "bid_strategy")
    _put_str(d, row, header, "Attribution setting", "attribution_setting")
    _put_str(d, row, header, "Result indicator", "results_indicator")
    if level in ("adsets", "ads"):
        _put_str(d, row, header, "Campaign name", "campaign_name")

    # results / conv_results — conv_results ONLY when the indicator is known
    # AND conversion-like (SHAPE-NOTES rule; indicator absent => unknown).
    _put_num(d, row, header, "Results", "results")
    if "results" in d and "results_indicator" in d and \
            _is_conversion_indicator(d["results_indicator"]):
        d["conv_results"] = d["results"]

    # ctr — fraction 0-1; recomputed from counts when both present, else the
    # CTR (all) column /100 when it carried a '%' or parses > 1 (CONTRACTS §1).
    if d.get("impressions"):
        if "clicks" in d:
            d["ctr"] = d["clicks"] / d["impressions"]
    if "ctr" not in d:
        col = _col(header, "CTR (all)")
        if col is not None:
            s = str(row.get(col) or "")
            v = _num(s)
            if v is not None:
                d["ctr"] = v / 100.0 if ("%" in s or v > 1) else v

    # cpm — recomputed spend/impressions*1000 when possible (CONTRACTS §1).
    if "spend" in d and d.get("impressions"):
        d["cpm"] = d["spend"] / d["impressions"] * 1000.0
    else:
        _put_num(d, row, header, "CPM (cost per 1,000 impressions)", "cpm")

    # budgets — routed by the paired type column; non-numeric budget cells
    # ("Using ad set budget") and unrecognised types are omitted (honest).
    budget_prefix = "Campaign budget" if level == "campaigns" else "Ad set budget"
    bcol = _col(header, budget_prefix)  # never matches "… budget type" (no " (")
    if bcol is not None:
        bval = _num(row.get(bcol))
        btype = ""
        tcol = _col(header, budget_prefix + " type")
        if tcol is not None:
            btype = str(row.get(tcol) or "").strip().lower()
        if bval is not None:
            if btype.startswith("daily"):
                d["daily_budget"] = bval
            elif btype.startswith("lifetime"):
                d["lifetime_budget"] = bval

    # rankings — CSV-only unlock for ranking_decomposition; UNKNOWN omitted.
    for prefix, key in (("Quality ranking", "quality_ranking"),
                        ("Engagement rate ranking", "engagement_rate_ranking"),
                        ("Conversion rate ranking", "conversion_rate_ranking")):
        col = _col(header, prefix)
        if col is not None:
            canon = _canon_ranking(row.get(col))
            if canon is not None:
                d[key] = canon

    # per-row reporting window -> ISO date_start/date_stop.
    for prefix, key in (("Reporting starts", "date_start"),
                        ("Reporting ends", "date_stop")):
        col = _col(header, prefix)
        if col is not None:
            dt = _parse_date(row.get(col))
            if dt is not None:
                d[key] = dt.isoformat()
    return d


def _level_rows(path: str, level: str) -> tuple[list[dict], dict]:
    header, raw_rows, stamp = load_ui_csv(path, level=level)
    rows = [_normalize_row(r, header, level=level) for r in raw_rows]
    rows.sort(key=lambda r: (-r.get("spend", 0.0), r["name"]))

    starts = sorted(r["date_start"] for r in rows if "date_start" in r)
    ends = sorted(r["date_stop"] for r in rows if "date_stop" in r)
    window, window_days = "", None
    if starts and ends:
        lo, hi = starts[0], ends[-1]
        window = f"{lo} – {hi}"
        window_days = (datetime.date.fromisoformat(hi)
                       - datetime.date.fromisoformat(lo)).days + 1
    meta = {"window": window, "window_days": window_days,
            "n_rows_raw": len(rows), "file": Path(path).name, "stamp": stamp}
    return rows, meta


def campaigns_rows(path: str) -> tuple[list[dict], dict]:
    """Campaign export -> (canonical rows, meta). See module docstring."""
    return _level_rows(path, "campaigns")


def adsets_rows(path: str) -> tuple[list[dict], dict]:
    """Ad set export -> (canonical rows, meta). See module docstring."""
    return _level_rows(path, "adsets")


def ads_rows(path: str) -> tuple[list[dict], dict]:
    """Ad export -> (canonical rows, meta). See module docstring."""
    return _level_rows(path, "ads")
