#!/usr/bin/env python3
"""Reconciliation totals — catch data-transcription drift before it ships.

The assembler (script) computes control totals from the findings arrays it just
built and embeds them as `meta.reconciliation`. The skill core recomputes the
same totals from the findings arrays it loaded and hard-fails on any mismatch.
A findings JSON that was hand-edited — or hand-written by a model instead of
assembled by the script — can no longer change a number silently: either the
totals disagree (build fails) or reconciliation is absent (builders warn that
transcription is unverified).

Shape (per findings JSON, under meta):

    "reconciliation": {
        "<array_name>": {"rows": <int>, "sums": {"<field>": <float>, ...}},
        ...
        "raw_files": [{"file", "sha256", "bytes"}, ...],  # provenance, not checked
        "raw_totals": {"<name>": <float>, ...}             # optional, IS checked (see below)
    }

`raw_totals` is for control totals that cannot be recomputed by summing a
findings array field — e.g. a raw universe count that includes rows joined
out of every findings array (an orphan pull id absent from the array a
foreign key points at). The assembler embeds the true raw figure via
`build(..., raw_totals=...)`; the core recomputes its own honest total from
the *loaded* findings (including whatever no-row-loss summary field accounts
for the excluded rows) and passes it to `verify(..., raw_totals=...)` — a
mismatch means rows were silently dropped between assembly and load.

Stdlib only.
"""
from __future__ import annotations


class ReconciliationError(ValueError):
    """Findings arrays do not match their embedded control totals."""


def build(findings: dict, arrays: dict, raw_stamps=None, raw_totals=None) -> dict:
    """Compute the reconciliation block for a findings dict.

    arrays — {"search_terms": ["cost", "clicks", ...], ...}: per findings
    array, the numeric fields to control-total.
    raw_totals — {"<name>": <float>, ...}: optional scalar totals computed
    from the raw pull(s) directly (not from a findings array), embedded
    verbatim and checked by `verify(..., raw_totals=...)`."""
    rec = {}
    for name, fields in arrays.items():
        rows = findings.get(name) or []
        rec[name] = {"rows": len(rows),
                     "sums": {f: _total(rows, f) for f in fields}}
    if raw_stamps:
        rec["raw_files"] = list(raw_stamps)
    if raw_totals:
        rec["raw_totals"] = {k: float(v) for k, v in raw_totals.items()}
    return rec


def verify(findings: dict, arrays: dict, raw_totals=None, *, report: bool = True) -> None:
    """Raise ReconciliationError unless every control total matches.

    No-op when meta.reconciliation is absent (legacy findings / fixtures) —
    the BUILDER is responsible for warning loudly in that case.

    raw_totals — {"<name>": <float>, ...}: totals the CALLER recomputed from
    the loaded findings (e.g. an in-scope sum plus an out-of-scope/orphan
    summary count); checked against the embedded `reconciliation.raw_totals`
    of the same name. Names absent from either side are skipped (no-op),
    same convention as legacy findings without a reconciliation block.

    On success, prints one line to stdout — `reconciliation: PASSED (<n>
    arrays, <m> rows)` — so builders stop succeeding silently (HM-607). This
    is the ONE shared spot every skill's core.load_findings() already routes
    through, so no per-skill build script needs to change. Pass report=False
    to suppress it (e.g. a caller that verifies the same findings repeatedly
    in a tight loop and wants only the exception behavior)."""
    rec = (findings.get("meta") or {}).get("reconciliation")
    if not rec:
        return
    problems = []
    for name, fields in arrays.items():
        expected = rec.get(name)
        if not isinstance(expected, dict):
            problems.append(f"reconciliation block missing '{name}'")
            continue
        rows = findings.get(name) or []
        if expected.get("rows") != len(rows):
            problems.append(f"{name}: {len(rows)} rows but reconciliation says "
                            f"{expected.get('rows')}")
        sums = expected.get("sums") or {}
        for f in fields:
            if f not in sums:
                problems.append(f"{name}: reconciliation has no control total for '{f}'")
                continue
            got, want = _total(rows, f), float(sums[f])
            if abs(got - want) > _tolerance(want):
                problems.append(f"{name}.{f}: sums to {got:,.4f} but reconciliation "
                                f"says {want:,.4f}")
    if raw_totals:
        embedded = rec.get("raw_totals") or {}
        for name, got in raw_totals.items():
            if name not in embedded:
                continue
            want = float(embedded[name])
            got = float(got)
            if abs(got - want) > _tolerance(want):
                problems.append(f"raw_totals.{name}: findings account for {got:,.4f} but "
                                f"reconciliation says the raw pull totalled {want:,.4f}")
    if problems:
        raise ReconciliationError(
            "findings failed reconciliation — the data does not match the control "
            "totals computed at assembly time. Rebuild the findings JSON with the "
            "skill's assemble_findings.py from the saved raw pulls; never hand-edit "
            "numbers.\n  - " + "\n  - ".join(problems))
    if report:
        total_rows = sum(int(rec.get(name, {}).get("rows") or 0) for name in arrays)
        print(f"reconciliation: PASSED ({len(arrays)} arrays, {total_rows} rows)")


def _total(rows, field) -> float:
    total = 0.0
    for r in rows:
        try:
            total += float(r.get(field) or 0)
        except (TypeError, ValueError):
            pass
    return total


def _tolerance(expected: float) -> float:
    # float64 sum-order drift only; real transcription errors are >> 1 cent
    return max(0.01, abs(expected) * 1e-9)
