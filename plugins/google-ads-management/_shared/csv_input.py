#!/usr/bin/env python3
"""Assemble findings from a user-supplied CSV — the manual-input firewall.

The CSV twin of the MCP path (`gaql_raw.py` + per-skill assemble_findings.py):
when the MCP cannot supply data (Auction Insights, Customer Match rates,
Enhanced-Conversions/Consent-Mode config) or the user simply has a Google Ads
UI export, THIS module — never the model — turns the file into rows and a
findings-shaped dict. Metric values go file -> parser -> findings without ever
passing through a token stream, and control totals are embedded as
`meta.reconciliation` (via `reconcile.build`) so downstream cores hard-fail if
the findings are later edited or were produced any other way. Both paths must
yield an IDENTICAL findings/model shape — the skill's core cannot tell them
apart (except by the honest `meta.source` label).

Column-mapping contract (per skill; the skill owns its map):

    COLUMN_MAP = {
        "term":  {"aliases": ["Search term", "Search terms"], "type": "str"},
        "cost":  {"aliases": ["Cost"], "type": "num"},
        "ctr":   {"aliases": ["CTR", "Interaction rate"], "type": "pct"},
        ...
    }

- one entry per LOGICAL field (the key the findings rows carry);
- `aliases` — every header spelling that may appear in a Google Ads UI export
  (locale/version variance). Matching is normalized: case-insensitive,
  whitespace-collapsed, surrounding quotes/BOM stripped. A parenthesised
  suffix on the CSV header is tolerated (`Cost (CAD)` matches alias `Cost`).
- `type` — `"str"` (default), `"num"` (float; tolerates thousands separators,
  currency prefixes, '%', and absent markers '', '--', '—' -> 0.0), or
  `"pct"` (percent-scale column -> fraction: '12.3%' -> 0.123).

Header handling is defensive: UI exports often carry title rows above the real
header and `Total: ...` summary rows below the data — the header row is found
by scanning for the row that resolves every required field, and total rows are
dropped. Missing or ambiguous columns raise `CsvInputError` naming them.

Stdlib only (`csv`). Deterministic: no wall clock, no locale-dependent parsing.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

import gaql_raw as _G      # file_stamp (provenance)
import reconcile as _R     # control totals


class CsvInputError(ValueError):
    """A user-supplied CSV is missing, malformed, or maps ambiguously."""


# Cell values that mean "absent" (Google Ads UI uses '--'; dashes tolerated).
_ABSENT = {"", "-", "--", "—", "–"}

_VALID_TYPES = ("str", "num", "pct")


def _norm(s: str) -> str:
    """Normalize a header cell / alias for matching: strip BOM + quotes,
    collapse whitespace, casefold."""
    s = str(s or "").replace("\ufeff", "").strip().strip('"').strip()
    return re.sub(r"\s+", " ", s).casefold()


def _is_absent(v) -> bool:
    return v is None or str(v).strip() in _ABSENT


def _num(v) -> float:
    """UI number cell -> float; absent/unparseable -> 0.0.

    Tolerates thousands commas ('1,234.56'), NBSP, a trailing '%', and a
    defensive currency prefix ('CA$1,023.31', '$5')."""
    if _is_absent(v):
        return 0.0
    s = str(v).strip().replace("\u00a0", " ").replace(",", "")
    s = s.rstrip("%").strip()
    s = re.sub(r"^[A-Za-z]{0,3}\$", "", s)
    try:
        return float(s)
    except ValueError:
        return 0.0


def _pct(v) -> float:
    """Percent-scale cell -> fraction: '12.3%' -> 0.123, '0.4' -> 0.4 (already
    a fraction), '40' -> 0.4 (percent without the sign — mirrors the audit
    plugins' rule: divide by 100 when '%' present or value > 1)."""
    if _is_absent(v):
        return 0.0
    s = str(v)
    x = _num(v)
    return x / 100.0 if ("%" in s or x > 1) else x


_CONVERT = {"str": lambda v: "" if _is_absent(v) else str(v).strip(),
            "num": _num, "pct": _pct}


def _validate_column_map(column_map: dict, required_fields) -> None:
    if not isinstance(column_map, dict) or not column_map:
        raise CsvInputError("column_map must be a non-empty dict of "
                            "{logical_field: {'aliases': [...], 'type': ...}}")
    for field, spec in column_map.items():
        if not isinstance(spec, dict) or not spec.get("aliases"):
            raise CsvInputError(f"column_map[{field!r}] needs a non-empty "
                                "'aliases' list")
        t = spec.get("type", "str")
        if t not in _VALID_TYPES:
            raise CsvInputError(f"column_map[{field!r}]: unknown type {t!r} "
                                f"(expected one of {', '.join(_VALID_TYPES)})")
    unknown = [f for f in (required_fields or ()) if f not in column_map]
    if unknown:
        raise CsvInputError("required_fields not declared in column_map: "
                            + ", ".join(unknown))


def resolve_columns(header: list, column_map: dict) -> dict:
    """Map logical fields -> header index for one candidate header row.

    A header cell matches an alias when the normalized forms are equal, or the
    header is `alias (suffix)` (currency/unit suffix tolerance). Raises
    CsvInputError when a logical field matches several distinct columns or one
    column matches several logical fields. Fields with no match are simply
    absent from the result (the caller decides whether that is fatal)."""
    normed = [_norm(h) for h in header]
    resolved: dict = {}
    claimed: dict = {}   # header index -> logical field
    problems = []
    for field, spec in column_map.items():
        hits = []
        for alias in spec["aliases"]:
            a = _norm(alias)
            for i, h in enumerate(normed):
                if h == a or h.startswith(a + " ("):
                    if i not in hits:
                        hits.append(i)
        if not hits:
            continue
        if len(hits) > 1:
            cols = ", ".join(repr(str(header[i]).strip()) for i in hits)
            problems.append(f"'{field}' matches several columns: {cols}")
            continue
        i = hits[0]
        if i in claimed:
            problems.append(f"column {str(header[i]).strip()!r} matches both "
                            f"'{claimed[i]}' and '{field}'")
            continue
        claimed[i] = field
        resolved[field] = i
    if problems:
        raise CsvInputError("ambiguous column mapping — fix the export or the "
                            "skill's column_map aliases:\n  - "
                            + "\n  - ".join(problems))
    return resolved


def load_csv_rows(csv_path: str, column_map: dict, required_fields=()
                  ) -> tuple[list, dict]:
    """Read a user-supplied CSV -> (rows, provenance_stamp).

    rows — list of {logical_field: typed value} dicts, one per data row, in
    file order. Every mapped-and-present field appears on every row (absent
    numeric cells -> 0.0, absent str cells -> ""); optional fields whose
    column is missing from the export are omitted from all rows. `Total: ...`
    summary rows and blank rows are dropped.

    Raises CsvInputError for a missing/empty/headerless file, for missing
    required columns (naming them), and for ambiguous mappings."""
    _validate_column_map(column_map, required_fields)
    required = list(required_fields or ())
    if not required:
        raise CsvInputError("required_fields must name at least one logical "
                            "field — it anchors the header-row scan")
    p = Path(csv_path)
    try:
        text = p.read_text(encoding="utf-8-sig")   # UI exports may carry a BOM
    except FileNotFoundError as e:
        raise CsvInputError(f"CSV file not found: {csv_path}") from e
    raw = [r for r in csv.reader(text.splitlines(keepends=True))]
    raw = [r for r in raw if any(str(c).strip() for c in r)]
    if not raw:
        raise CsvInputError(f"{csv_path}: file is empty")

    # Defensive header scan: UI exports carry title rows above the header.
    # Pick the first row that resolves every required field; remember the
    # best partial match so the error can name exactly what is missing.
    header_idx = None
    best_resolved: dict = {}
    ambiguity_err = None
    for i, row in enumerate(raw):
        try:
            resolved = resolve_columns(row, column_map)
        except CsvInputError as e:
            # Ambiguity on a candidate header row — data rows almost never
            # match aliases, so surface this if no clean header is found.
            if ambiguity_err is None:
                ambiguity_err = e
            continue
        if sum(1 for f in required if f in resolved) > \
                sum(1 for f in required if f in best_resolved):
            best_resolved = resolved
        if all(f in resolved for f in required):
            header_idx = i
            break
    if header_idx is None:
        if ambiguity_err is not None:
            raise ambiguity_err
        missing = [f for f in required if f not in best_resolved]
        wanted = "; ".join(
            f"'{f}' (any of: {', '.join(column_map[f]['aliases'])})"
            for f in missing)
        raise CsvInputError(
            f"{csv_path}: no header row carries the required column(s) — "
            f"missing {wanted}. Is this the right Google Ads UI export? "
            "If the export uses a different header spelling, add it to the "
            "skill's column_map aliases.")
    header = raw[header_idx]
    resolved = resolve_columns(header, column_map)   # includes optional fields

    rows = []
    for r in raw[header_idx + 1:]:
        first = next((str(c).strip() for c in r if str(c).strip()), "")
        # 'Total: ...' summary rows (colon required — a real data value may
        # legitimately start with the word "total"; no-row-loss).
        if _norm(first).startswith("total:"):
            continue
        row = {}
        for field, i in resolved.items():
            conv = _CONVERT[column_map[field].get("type", "str")]
            row[field] = conv(r[i] if i < len(r) else "")
        rows.append(row)
    return rows, _G.file_stamp(csv_path)


def assemble_from_csv(csv_path: str, column_map: dict, required_fields,
                      reconcile_spec: dict, *, meta=None) -> tuple[list, dict]:
    """User CSV -> (rows, findings-shaped dict) with reconciliation embedded.

    reconcile_spec — {"array": "<findings array name>",
                      "sums": ["<numeric logical field>", ...]}: where the rows
    live in the findings dict and which fields get control totals (the same
    arrays/fields contract the skill's core verifies via `reconcile.verify`).

    meta — the skill's provenance dict (client_name, account_id, currency,
    window labels, generated). `meta.source` defaults to "user_csv" — the
    honest data-source label; never presented as an API pull.

    The returned findings dict has the MCP-path shape:
        {"meta": {..., "source", "reconciliation"}, "params": {},
         "<array>": rows}
    Skills assembling several CSVs into one findings dict use `load_csv_rows`
    per file and call `reconcile.build` themselves over the merged arrays."""
    _validate_column_map(column_map, required_fields)
    if not isinstance(reconcile_spec, dict) or not reconcile_spec.get("array"):
        raise CsvInputError('reconcile_spec must be {"array": <name>, '
                            '"sums": [<numeric fields>]}')
    array = reconcile_spec["array"]
    sums = list(reconcile_spec.get("sums") or ())
    bad = [f for f in sums
           if column_map.get(f, {}).get("type", "str") not in ("num", "pct")]
    if bad:
        raise CsvInputError("reconcile_spec sums must be numeric "
                            "(type 'num'/'pct') fields: " + ", ".join(bad))

    rows, stamp = load_csv_rows(csv_path, column_map, required_fields)
    meta = dict(meta or {})
    meta.setdefault("source", "user_csv")
    findings = {"meta": meta, "params": {}, array: rows}
    findings["meta"]["reconciliation"] = _R.build(
        findings, {array: sums}, raw_stamps=[stamp])
    return rows, findings
