#!/usr/bin/env python3
"""Parse saved google-ads-mcp `search_search` results — the transcription firewall.

Raw MCP output reaches the analytical pipeline ONLY as a verbatim file:
large results are auto-saved by the harness to `tool-results/*.txt`; small
results are copied verbatim (the whole tool-result JSON, unedited) into a file
before anything else happens. This module is the only thing that turns those
files into rows, so metric values never pass through the model's token stream —
the model handles file paths, never numbers.

Observed file format (verified live 2026-07-06 against the connected MCP):
one JSON object `{"result": [{...}, ...]}` where each row is FLAT with dotted
keys exactly as requested in `fields` (e.g. "metrics.cost_micros", snake_case).
The parser also tolerates a bare JSON array and several concatenated
`{"result": [...]}` objects (a manually paginated pull saved into one file).

Stdlib only.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


class RawResultError(ValueError):
    """A saved raw-results file is missing, malformed, or from the wrong query."""


def load_rows(path: str, *, require_fields=None) -> list:
    """Return the row dicts from a saved search_search result file.

    require_fields — iterable of dotted field names every row must carry;
    catches "wrong file for this pull" early (e.g. a benchmarks file passed
    as the search-terms file)."""
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8-sig")   # writers emit utf-8; tolerate a BOM
    except FileNotFoundError as e:
        raise RawResultError(f"raw results file not found: {path}") from e
    rows = _parse(text, path)
    if require_fields:
        missing_example = None
        for i, r in enumerate(rows):
            missing = [f for f in require_fields if f not in r]
            if missing:
                missing_example = (i, missing)
                break
        if missing_example:
            i, missing = missing_example
            raise RawResultError(
                f"{path}: row {i} is missing field(s) {', '.join(missing)} — "
                "is this the raw file for the right GAQL pull?")
    return rows


def _parse(text: str, path: str) -> list:
    text = text.strip()
    if not text:
        raise RawResultError(f"{path}: file is empty")
    # Common case: one JSON document ({"result": [...]} or a bare array).
    try:
        doc = json.loads(text)
    except json.JSONDecodeError:
        doc = None
    if doc is not None:
        return _rows_of(doc, path)
    # Fallback: several concatenated JSON documents in one file.
    rows: list = []
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
                f"verbatim tool result, nothing hand-edited ({e})") from e
        rows.extend(_rows_of(doc, path))
        i = end
    return rows


def _rows_of(doc, path: str) -> list:
    if isinstance(doc, dict):
        rows = doc.get("result")
        if not isinstance(rows, list):
            raise RawResultError(f"{path}: JSON object has no 'result' array")
    elif isinstance(doc, list):
        rows = doc
    else:
        raise RawResultError(f"{path}: expected an object with 'result' or an array")
    for i, r in enumerate(rows):
        if not isinstance(r, dict):
            raise RawResultError(f"{path}: result[{i}] is not an object")
    return rows


def micros(v) -> float:
    """Google Ads money: micros -> account currency units."""
    try:
        return float(v or 0) / 1_000_000.0
    except (TypeError, ValueError):
        return 0.0


def num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def file_stamp(path: str) -> dict:
    """Provenance stamp for a raw file, embedded in meta.reconciliation."""
    p = Path(path)
    return {"file": p.name,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "bytes": p.stat().st_size}
