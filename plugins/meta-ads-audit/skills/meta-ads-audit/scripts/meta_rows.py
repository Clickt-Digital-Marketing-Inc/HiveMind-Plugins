#!/usr/bin/env python3
# Copyright (c) 2026 Clickt Digital Marketing Inc. All rights reserved.
"""Raw Meta Ads MCP result loader/normalizer for the Meta Ads audit.

Inputs are RAW saved MCP tool-result files (the transcription firewall): the
model handles file paths, never numbers. The envelope parser ports the
google-ads-audit `concentration.py` loader (tolerant concatenated-docs JSON)
and adds the Meta `ads_get_ad_entities` envelope, where the row list arrives
as a JSON-encoded STRING under `ad_entities` (double parse required).

Meta metric values are human-formatted strings: money like "CA$1,023.31 CAD"
(currency prefix, thousands commas, non-breaking space + ISO code suffix),
counts like "583,301", ctr as a percent string like "0.0658%", and dates like
"11 June 2026". Any value whose string starts with "Not available" is MISSING
— the canonical row simply omits the key (never None, never the string).

The `results`/`cost_per_result` fields come in a dual shape under
`{"value": X}`: either "181,893 (Reach)" strings or a list of
`{indicator, values:[{value,...}]}` items. Indicators are heterogeneous
across campaigns (Reach vs Leads in one account), so each row keeps
`results` (raw optimization-event count) + `results_indicator`, and
`conv_results` is set ONLY when the indicator is conversion-like.

Rates are recomputed from counts wherever possible (ctr = clicks/impressions,
cpm = spend/impressions*1000); the returned ctr/cpm are used only as a
fallback, with a >1 => percent heuristic on ctr.

Stdlib only.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from pathlib import Path

RAW_PULLS_DOC = "references/raw-pulls.md"

LEVELS = ("campaign", "adset", "ad")


class RawResultError(ValueError):
    """A saved raw-results file is missing, malformed, or from the wrong pull."""


# ── scalar parsers ──────────────────────────────────────────────────────────

_ABSENT = {"", "-", "--", "—", "–"}  # blank / dashes = missing
_NUM_RE = re.compile(
    r"[^0-9+\-.]*([-+]?(?:\d+(?:\.\d*)?|\.\d+))(?:\s*[A-Za-z]{2,4})?\s*")
_RESULT_RE = re.compile(r"^\s*([\d.,]+)\s*\((.+)\)\s*$")
_ISO_DATE_RE = re.compile(r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})")
_HUMAN_DATE_RE = re.compile(r"^\s*(\d{1,2})\s+([A-Za-z]+)\.?,?\s+(\d{4})\s*$")

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}
_MONTHS_ABBR = {name[:3]: n for name, n in _MONTHS.items()}

# An indicator naming any of these tokens counts raw activity, not
# conversions (catches Reach, video_continuous_2_sec_watched_actions,
# ThruPlay counts via video_*, Landing page views, Link clicks,
# Post engagement, Page likes, Follows, ad recall).
_NON_CONVERSION_TOKENS = ("reach", "video", "impression", "recall",
                          "engagement", "view", "like", "follow", "click")


def _is_absent_str(s: str) -> bool:
    return s in _ABSENT or s.casefold().startswith("not available")


def num_or_none(v):
    """Parse Meta's human-formatted values to float, or None when missing.

    Handles "CA$1,023.31 CAD" (NBSP before the ISO code), "583,301", "3.21",
    "0.0658%" -> 0.000658 (percent strings become fractions), and the missing
    markers ""/"--"/"—"/"Not available…" -> None. Non-numeric text -> None.
    """
    if v is None:
        return None
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        f = float(v)
        if f != f or f in (float("inf"), float("-inf")):
            return None
        return f
    if not isinstance(v, str):
        return None
    s = v.replace("\u00a0", " ").strip()
    if _is_absent_str(s):
        return None
    percent = s.endswith("%")
    if percent:
        s = s[:-1].strip()
    s = s.replace(",", "")
    m = _NUM_RE.fullmatch(s)
    if not m:
        return None
    try:
        f = float(m.group(1))
    except ValueError:
        return None
    return f / 100.0 if percent else f


def parse_human_date(v) -> str | None:
    """"11 June 2026" -> "2026-06-11" via an explicit English month map
    (NOT locale-dependent strptime %B). ISO-prefixed strings pass through
    re-validated. Missing/unparseable -> None."""
    if not isinstance(v, str):
        return None
    s = v.replace("\u00a0", " ").strip()
    if _is_absent_str(s):
        return None
    m = _ISO_DATE_RE.match(s)
    if m:
        y, mo, d = (int(g) for g in m.groups())
    else:
        m = _HUMAN_DATE_RE.match(s)
        if not m:
            return None
        d, name, y = int(m.group(1)), m.group(2).casefold(), int(m.group(3))
        mo = _MONTHS.get(name) or _MONTHS_ABBR.get(name)  # full name or exact 3-letter abbr
        if mo is None:
            return None
    try:
        _dt.date(y, mo, d)
    except ValueError:
        return None
    return f"{y:04d}-{mo:02d}-{d:02d}"


def parse_result(value) -> tuple[float, str] | None:
    """Parse the dual-shape `results` field -> (count, indicator) or None.

    String form: "181,893 (Reach)", "107 (Leads (form))" — the regex keeps
    nested parens in the indicator. List form: [{indicator, values:[{value}]}]
    -> (sum of the first item's values, its indicator). Bare numbers ->
    (value, ""). "Not available…"/blank -> None.
    """
    if value is None:
        return None
    if isinstance(value, dict):
        if "value" in value:
            return parse_result(value["value"])
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        n = num_or_none(value)
        return None if n is None else (n, "")
    if isinstance(value, str):
        s = value.replace("\u00a0", " ").strip()
        if _is_absent_str(s):
            return None
        m = _RESULT_RE.match(s)
        if m:
            n = num_or_none(m.group(1))
            if n is None:
                return None
            return (n, m.group(2).strip())
        n = num_or_none(s)
        return None if n is None else (n, "")
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            indicator = str(item.get("indicator") or "").strip()
            total, seen = 0.0, False
            vals = item.get("values")
            if isinstance(vals, list):
                for entry in vals:
                    if isinstance(entry, dict):
                        n = num_or_none(entry.get("value"))
                        if n is not None:
                            total += n
                            seen = True
            if seen or indicator:
                return (total, indicator)
        return None
    return None


def is_conversion_indicator(label) -> bool:
    """True when a results indicator counts conversions (Leads, Purchases…).

    NON-conversion when the lowercased label contains any raw-activity token
    (reach/video/impression/recall/engagement/view/like/follow/click).
    Empty/unknown labels are NOT conversion-like (conservative).
    """
    if not isinstance(label, str):
        return False
    low = label.strip().casefold()
    if not low:
        return False
    return not any(t in low for t in _NON_CONVERSION_TOKENS)


# ── raw-file envelope parser (ports google concentration.py) ───────────────

def _iter_docs(text: str, path: str):
    """Yield each JSON document in the file (tolerates concatenated docs)."""
    text = text.lstrip("\ufeff").strip()
    if not text:
        raise RawResultError(f"{path}: file is empty (see {RAW_PULLS_DOC})")
    try:
        yield json.loads(text)
        return
    except json.JSONDecodeError:
        pass
    dec = json.JSONDecoder()
    i, n = 0, len(text)
    while i < n:
        while i < n and text[i] in " \t\r\n":
            i += 1
        if i >= n:
            break
        try:
            doc, end = dec.raw_decode(text, i)
        except json.JSONDecodeError as e:
            raise RawResultError(
                f"{path}: not valid JSON at offset {i} — the file must be the "
                f"verbatim tool result, nothing hand-edited "
                f"(see {RAW_PULLS_DOC}) ({e})") from e
        yield doc
        i = end


def _read_text(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise RawResultError(
            f"raw results file not found: {path} (see {RAW_PULLS_DOC})") from e


def _rows_of(doc, path: str) -> list:
    """Extract the raw row list from one parsed document.

    Accepts the ads_get_ad_entities envelope ({"ad_entities": "<JSON str>"}
    — DOUBLE PARSE — or an already-decoded list under that key), the
    google-style tolerant envelopes (list under result/data/entities/rows),
    a bare list, or a double-encoded whole document.
    """
    if isinstance(doc, str):
        try:
            doc = json.loads(doc)
        except json.JSONDecodeError as e:
            raise RawResultError(
                f"{path}: string document is not valid JSON — save the "
                f"verbatim tool result (see {RAW_PULLS_DOC}) ({e})") from e
        return _rows_of(doc, path)
    if isinstance(doc, dict):
        if "ad_entities" in doc:
            inner = doc["ad_entities"]
            if isinstance(inner, str):
                try:
                    inner = json.loads(inner)
                except json.JSONDecodeError as e:
                    raise RawResultError(
                        f"{path}: 'ad_entities' is not valid JSON — save the "
                        f"verbatim tool result (see {RAW_PULLS_DOC}) ({e})"
                    ) from e
            if not isinstance(inner, list):
                raise RawResultError(
                    f"{path}: 'ad_entities' did not decode to a list "
                    f"(see {RAW_PULLS_DOC})")
            rows = inner
        else:
            rows = None
            for key in ("result", "data", "entities", "rows"):
                v = doc.get(key)
                if isinstance(v, list):
                    rows = v
                    break
            if rows is None:
                raise RawResultError(
                    f"{path}: JSON object has no 'ad_entities', 'result', "
                    f"'data', 'entities' or 'rows' array (see {RAW_PULLS_DOC})")
    elif isinstance(doc, list):
        rows = doc
    else:
        raise RawResultError(
            f"{path}: expected an object envelope or an array "
            f"(see {RAW_PULLS_DOC})")
    for i, r in enumerate(rows):
        if not isinstance(r, dict):
            raise RawResultError(f"{path}: row {i} is not an object "
                                 f"(see {RAW_PULLS_DOC})")
    return rows


def _parse(text: str, path: str) -> list:
    rows: list = []
    for doc in _iter_docs(text, path):
        rows.extend(_rows_of(doc, path))
    return rows


# ── normalization ───────────────────────────────────────────────────────────

_STR_FIELDS = ("objective", "optimization_goal", "attribution_setting",
               "bid_strategy", "effective_status", "campaign_name")
_DATE_FIELDS = ("created_time", "date_start", "date_stop")
# canonical numeric key -> source aliases, in priority order
_NUM_ALIASES = (
    ("spend", ("spend", "amount_spent")),
    ("impressions", ("impressions",)),
    ("clicks", ("clicks",)),
    ("reach", ("reach",)),
    ("frequency", ("frequency",)),
    ("daily_budget", ("daily_budget",)),
    ("lifetime_budget", ("lifetime_budget",)),
    ("video_p25", ("video_p25", "video_p25_watched_actions")),
    ("video_p50", ("video_p50", "video_p50_watched_actions")),
    ("video_p75", ("video_p75", "video_p75_watched_actions")),
    ("video_p100", ("video_p100", "video_p100_watched_actions")),
    ("thruplay", ("thruplay", "video_thruplay_watched_actions")),
    ("link_clicks", ("link_clicks",)),
)
_RANKING_FIELDS = ("quality_ranking", "engagement_rate_ranking",
                   "conversion_rate_ranking")
_RANKING_ENUMS = {"BELOW_AVERAGE", "AVERAGE", "ABOVE_AVERAGE"}


def _clean_str(v) -> str | None:
    if v is None:
        return None
    s = str(v).replace("\u00a0", " ").strip()
    if not s or _is_absent_str(s):
        return None
    return s


def normalize(row, *, level) -> dict:
    """One raw entity row -> the canonical flat dict (absent = key omitted).

    Unknown source keys (cost_per_video_view, cost_per_action_type,
    buying_type, …) are ignored gracefully.
    """
    if level not in LEVELS:
        raise ValueError(f"level must be one of {LEVELS}, got {level!r}")
    if not isinstance(row, dict):
        raise RawResultError(
            f"{level} row is not an object (see {RAW_PULLS_DOC})")
    out: dict = {}
    name = _clean_str(row.get("name"))
    if not name:
        raise RawResultError(
            f"{level} row has no usable 'name' — is this the saved result "
            f"for the right pull? (see {RAW_PULLS_DOC})")
    out["name"] = name
    for k in ("id", "campaign_id"):
        s = _clean_str(row.get(k))
        if s is not None:
            out[k] = s
    for k in _STR_FIELDS:
        s = _clean_str(row.get(k))
        if s is not None:
            out[k] = s
    for canon, aliases in _NUM_ALIASES:
        for a in aliases:
            if a in row:
                n = num_or_none(row[a])
                if n is not None:
                    out[canon] = n
                    break
    for k in _DATE_FIELDS:
        if k in row:
            d = parse_human_date(row[k])
            if d is not None:
                out[k] = d
    pr = parse_result(row.get("results"))
    if pr is not None:
        val, indicator = pr
        out["results"] = val
        if indicator:
            out["results_indicator"] = indicator
            if is_conversion_indicator(indicator):
                out["conv_results"] = val
    imp = out.get("impressions")
    clk = out.get("clicks")
    spd = out.get("spend")
    # ctr: fraction 0-1, recomputed from counts when both present
    if imp and clk is not None:
        out["ctr"] = clk / imp
    else:
        c = num_or_none(row.get("ctr"))
        if c is not None:
            if c > 1:  # heuristic: plain number >1 must be a percent
                c = c / 100.0
            out["ctr"] = c
    # cpm: currency per 1000 impressions, recomputed when possible
    if imp and spd is not None:
        out["cpm"] = spd / imp * 1000.0
    else:
        m = num_or_none(row.get("cpm"))
        if m is not None:
            out["cpm"] = m
    # frequency fallback from counts when the platform value is absent
    if "frequency" not in out:
        reach = out.get("reach")
        if imp and reach:
            out["frequency"] = imp / reach
    for k in _RANKING_FIELDS:  # CSV-path enums pass through if already canon
        v = row.get(k)
        if isinstance(v, str):
            up = v.replace("\u00a0", " ").strip().upper().replace(" ", "_")
            if up in _RANKING_ENUMS:
                out[k] = up
    return out


def load_rows(path, *, level) -> list[dict]:
    """Load + normalize a saved entity-level pull; spend desc, name asc."""
    if level not in LEVELS:
        raise ValueError(f"level must be one of {LEVELS}, got {level!r}")
    rows = [normalize(r, level=level) for r in _parse(_read_text(path), path)]
    rows.sort(key=lambda r: (-r.get("spend", 0.0), r.get("name", "")))
    return rows


# ── datasets / dataset quality loaders ──────────────────────────────────────

def load_datasets(path) -> list[dict]:
    """Load a saved ads_get_datasets result; dedupe by dataset_id
    (first occurrence wins, input order preserved — the tool is known to
    return duplicates)."""
    out: list[dict] = []
    seen: set[str] = set()
    for doc in _iter_docs(_read_text(path), path):
        if isinstance(doc, str):
            try:
                doc = json.loads(doc)
            except json.JSONDecodeError as e:
                raise RawResultError(
                    f"{path}: string document is not valid JSON "
                    f"(see {RAW_PULLS_DOC}) ({e})") from e
        if isinstance(doc, dict):
            items = doc.get("datasets")
            if not isinstance(items, list):
                raise RawResultError(
                    f"{path}: JSON object has no 'datasets' array "
                    f"(see {RAW_PULLS_DOC})")
        elif isinstance(doc, list):
            items = doc
        else:
            raise RawResultError(
                f"{path}: expected an object with 'datasets' or an array "
                f"(see {RAW_PULLS_DOC})")
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                raise RawResultError(
                    f"{path}: datasets[{i}] is not an object "
                    f"(see {RAW_PULLS_DOC})")
            key = str(item.get("dataset_id") or item.get("id") or "")
            if key:
                if key in seen:
                    continue
                seen.add(key)
            out.append(item)
    return out


def load_dataset_quality(path) -> dict:
    """Load a saved ads_get_dataset_quality result: {channel: [event dicts]}.

    Concatenated docs (one per dataset pull) merge by extending each
    channel's event list in document order."""
    merged: dict = {}
    for doc in _iter_docs(_read_text(path), path):
        if isinstance(doc, str):
            try:
                doc = json.loads(doc)
            except json.JSONDecodeError as e:
                raise RawResultError(
                    f"{path}: string document is not valid JSON "
                    f"(see {RAW_PULLS_DOC}) ({e})") from e
        if not isinstance(doc, dict):
            raise RawResultError(
                f"{path}: expected a channel->events object from "
                f"ads_get_dataset_quality (see {RAW_PULLS_DOC})")
        for channel in sorted(doc):
            events = doc[channel]
            if not isinstance(events, list):
                raise RawResultError(
                    f"{path}: channel {channel!r} is not a list of events "
                    f"(see {RAW_PULLS_DOC})")
            merged.setdefault(channel, []).extend(events)
    return merged


# ── window + provenance helpers ─────────────────────────────────────────────

def window_label(rows) -> tuple:
    """Derive (label, window_days) from normalized rows' date_start/date_stop.

    label = "<min date_start> – <max date_stop>" (ISO dates); window_days is
    INCLUSIVE (a 7-day pull -> 7). (None, None) when no dates present.
    """
    starts = sorted(r["date_start"] for r in (rows or [])
                    if isinstance(r, dict) and r.get("date_start"))
    stops = sorted(r["date_stop"] for r in (rows or [])
                   if isinstance(r, dict) and r.get("date_stop"))
    if not starts or not stops:
        return (None, None)
    start, stop = starts[0], stops[-1]
    days = None
    try:
        d0 = _dt.date.fromisoformat(start)
        d1 = _dt.date.fromisoformat(stop)
        span = (d1 - d0).days + 1
        if span >= 1:
            days = span
    except ValueError:
        pass
    return (f"{start} – {stop}", days)


def file_stamp(path: str) -> dict:
    """Provenance stamp for a raw input file."""
    p = Path(path)
    return {"file": p.name,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "bytes": p.stat().st_size}
