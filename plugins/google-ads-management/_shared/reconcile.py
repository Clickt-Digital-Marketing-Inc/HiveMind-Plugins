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
        "raw_files": [{"file", "sha256", "bytes"}, ...]   # provenance, not checked
    }

Stdlib only.
"""
from __future__ import annotations


class ReconciliationError(ValueError):
    """Findings arrays do not match their embedded control totals."""


def build(findings: dict, arrays: dict, raw_stamps=None) -> dict:
    """Compute the reconciliation block for a findings dict.

    arrays — {"search_terms": ["cost", "clicks", ...], ...}: per findings
    array, the numeric fields to control-total."""
    rec = {}
    for name, fields in arrays.items():
        rows = findings.get(name) or []
        rec[name] = {"rows": len(rows),
                     "sums": {f: _total(rows, f) for f in fields}}
    if raw_stamps:
        rec["raw_files"] = list(raw_stamps)
    return rec


def verify(findings: dict, arrays: dict) -> None:
    """Raise ReconciliationError unless every control total matches.

    No-op when meta.reconciliation is absent (legacy findings / fixtures) —
    the BUILDER is responsible for warning loudly in that case."""
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
    if problems:
        raise ReconciliationError(
            "findings failed reconciliation — the data does not match the control "
            "totals computed at assembly time. Rebuild the findings JSON with the "
            "skill's assemble_findings.py from the saved raw pulls; never hand-edit "
            "numbers.\n  - " + "\n  - ".join(problems))


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
