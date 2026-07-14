"""Run-metadata assembly for the wPPC report layer.

``build_run_meta`` collects the run-level scalars a report needs into one
JSON-serializable dict: the derived baseline/replacement/k, the k-honesty
provenance (estimated vs fallback), segment/stabilization counts, and the
weights' telescoping self-check. ``weights_version``, ``drift``, ``decay`` and
``incrementality`` are pass-through kwargs filled by their respective CLI
flags; all default to None (their prior stubbed behaviour) when omitted.

Nothing here recomputes methodology numbers — the values are read from the
scored results' ``attrs`` and the ``Weights`` object.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd

from .charts import WPPC_CHARTS
from .weights import FUNNEL_STATES, Weights

# Which model row array each declared chart reads from. The three segment charts
# read the per-segment rows; the derived-weights chart reads the weight rows.
# This is the CLI-402 forward-contract made explicit (see build_model docstring).
CHART_ROW_SOURCE = {
    "mar_by_segment": "segments",
    "wppc_plus_by_segment": "segments",
    "derived_weights": "weights_table",
    "closing_ratio_vs_wppc": "segments",
}

# The six required fields on every incrementality-table tier entry (see
# wppc/references/incrementality-seam.md for the full contract).
_INCREMENTALITY_TIER_FIELDS = ("tier", "value", "ci", "power", "window", "timestamp")


def build_run_meta(
    results: pd.DataFrame,
    weights: Weights,
    platform,
    *,
    generated=None,
    weights_version=None,
    drift=None,
    decay=None,
    incrementality=None,
) -> dict:
    """Assemble the run-metadata block for one scored platform.

    ``results`` is the frame returned by ``score.score`` (carries the run-level
    scalars in ``.attrs``). ``weights`` is the derived ``Weights`` table.
    ``platform`` labels the platform the run covers.

    ``generated`` is the run timestamp. When None, defaults to the current UTC
    time as an ISO-8601 string; when a value is passed it is used verbatim (so a
    determinism test can pin it). No clock is read when a value is supplied.

    ``weights_version`` (this run's weights snapshot), ``drift`` (the
    weight-drift comparison result), ``decay`` (the two-period wPPC+ movement
    meta block) and ``incrementality`` (the Layer-5 seam meta block, see
    ``build_incrementality_meta``) pass straight through into the returned
    dict. All default to None so existing call-sites that omit them get exactly
    the prior stubbed behaviour.
    """
    if generated is None:
        generated = datetime.now(timezone.utc).isoformat()

    attrs = results.attrs
    telescope_sum = weights.telescope_sum

    # The weights carry their own telescoping self-check (weights.py verifies it
    # at construction and refuses to build an inconsistent table), so read it
    # directly rather than recomputing the tolerance here.
    self_check_pass = bool(weights.self_check_pass)

    return {
        "baseline": attrs.get("baseline"),
        "replacement": attrs.get("replacement"),
        "k": attrs.get("k"),
        "k_source": attrs.get("k_source"),
        "n_segments": attrs.get("n_segments"),
        "n_stabilized": attrs.get("n_stabilized"),
        "self_check_pass": self_check_pass,
        "telescope_sum": telescope_sum,
        "generated": generated,
        "platform": platform,
        # Filled by CLI-399 (W1 weight-drift); pass-through, default None.
        "weights_version": weights_version,
        "drift": drift,
        # Filled by CLI-400 (W4 decay); pass-through, default None.
        "decay": decay,
        # Filled by CLI-401 (Layer-5 incrementality seam); pass-through, default None.
        "incrementality": incrementality,
    }


def build_decay(current_results: pd.DataFrame, prior_results: pd.DataFrame, band) -> pd.DataFrame:
    """Per-segment wPPC+ movement between two periods (current vs prior).

    Joins ``current_results`` to ``prior_results`` on ``segment_id`` and emits a
    frame (row order = ``current_results`` order) with columns:

        segment_id, wPPC+_prior, wPPC+_delta, delta_pct, trend

    where ``wPPC+_delta = current − prior`` and ``delta_pct = (cur − prior)/prior``
    (guarded: ``prior == 0`` → None, since the relative change is undefined).

    ``trend`` classifies the move in wPPC+ points against ``band``:
        "Rising"  when delta >  +band
        "Falling" when delta <  −band
        "Flat"    otherwise (inclusive band: delta == ±band → "Flat").

    A segment absent from the prior period (or with a non-finite prior/current
    wPPC+) gets None for prior/delta/pct and trend None — never a fabricated
    number. Decay is parallel data: it is never blended into wPPC+ / MAR / any
    point-in-time score.

    Instrument constancy: both frames MUST be scored with the SAME weights
    table (the CLI scores the prior CSV with the current period's weights).
    Holding the measuring stick constant makes the delta a pure segment-behavior
    signal; event-side weight change is the separate W1 drift signal. Passing a
    prior frame scored under different weights silently changes the semantics.
    """
    band = float(band)
    prior_lookup = dict(zip(prior_results["segment_id"], prior_results["wPPC+"]))

    rows = []
    for _, r in current_results.iterrows():
        seg = r["segment_id"]
        cur_plus = r["wPPC+"]
        prior_plus = prior_lookup.get(seg)

        if (
            seg in prior_lookup
            and prior_plus is not None
            and not pd.isna(prior_plus)
            and cur_plus is not None
            and not pd.isna(cur_plus)
        ):
            prior_plus = float(prior_plus)
            delta = float(cur_plus) - prior_plus
            delta_pct = (delta / prior_plus) if prior_plus != 0 else None
            if delta > band:
                trend = "Rising"
            elif delta < -band:
                trend = "Falling"
            else:
                trend = "Flat"
        else:
            prior_plus = None
            delta = None
            delta_pct = None
            trend = None

        rows.append({
            "segment_id": seg,
            "wPPC+_prior": prior_plus,
            "wPPC+_delta": delta,
            "delta_pct": delta_pct,
            "trend": trend,
        })

    return pd.DataFrame.from_records(
        rows,
        columns=["segment_id", "wPPC+_prior", "wPPC+_delta", "delta_pct", "trend"],
    )


def build_decay_meta(status: str, prior_input=None, band=None) -> dict:
    """Small run-metadata block describing the decay computation.

    ``status`` is ``"computed"`` when a prior period was supplied and joined, or
    ``"not-run"`` when no ``--prior-input`` was given. ``prior_input`` records the
    prior CSV path (None when not run); ``band`` records the trend band used.
    """
    return {"status": status, "prior_input": prior_input, "band": band}


def build_weights_snapshot(weights: Weights, platform, *, timestamp=None) -> dict:
    """Capture the weight-table inputs as a JSON-serializable snapshot.

    The snapshot records only the *input* components that determine the derived
    weights — the currency parameters, the P(purchase|S) vector, and the
    telescoping self-check sum — so a later run can detect event-side drift by
    comparing against a prior blessed snapshot.

    ``timestamp`` is injectable for determinism (same pattern as
    ``build_run_meta``'s ``generated``): defaults to the current UTC time as an
    ISO-8601 string only when None; a supplied value is used verbatim.
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()

    return {
        "timestamp": timestamp,
        "platform": platform,
        "cm3_order": weights.cm3_order,
        "repeat_rate": weights.repeat_rate,
        "cm3_repeat": weights.cm3_repeat,
        # P(purchase|S) per funnel state — the event-side inputs most prone to drift.
        "p_vector": dict(weights.p),
        "telescope_sum": weights.telescope_sum,
    }


def _snapshot_components(snapshot: dict) -> dict:
    """Flatten a snapshot into a {component_field: numeric value} map.

    Scalar currency inputs and the telescope sum keep their own names; each
    P(purchase|S) entry is namespaced as ``p_vector.<state>``.
    """
    components = {
        "cm3_order": snapshot.get("cm3_order"),
        "repeat_rate": snapshot.get("repeat_rate"),
        "cm3_repeat": snapshot.get("cm3_repeat"),
        "telescope_sum": snapshot.get("telescope_sum"),
    }
    for state, value in (snapshot.get("p_vector") or {}).items():
        components[f"p_vector.{state}"] = value
    return components


def compare_weights_snapshot(current: dict, baseline: dict, tolerance: float) -> dict:
    """Compare this run's snapshot against a prior blessed one, component-wise.

    For each numeric input component (``cm3_order``, ``repeat_rate``,
    ``cm3_repeat``, ``telescope_sum``, and each ``p_vector.<state>`` entry) the
    relative change ``pct = (to - from) / from`` is computed. A component whose
    ``abs(pct)`` exceeds ``tolerance`` lands in ``moved``; ``flagged`` is True
    when any component moved.

    Zero-denominator handling: if the baseline value is 0 and the current value
    is also 0 there is no change (skipped). If the baseline is 0 but the current
    is non-zero the relative change is undefined, so the component is treated as
    *flagged* with ``pct=None`` (an infinite move — impossible to express as a
    ratio). Components missing from either snapshot are skipped (nothing to
    compare).

    The caller fills ``baseline_path``; it is None here.
    """
    cur = _snapshot_components(current)
    base = _snapshot_components(baseline)

    moved = []
    for field, from_val in base.items():
        to_val = cur.get(field)
        if from_val is None or to_val is None:
            # A component absent from one side can't be compared.
            continue
        if from_val == 0:
            if to_val == 0:
                continue
            # Undefined relative change from a zero baseline -> always flag.
            moved.append({"field": field, "from": from_val, "to": to_val, "pct": None})
            continue
        pct = (to_val - from_val) / from_val
        if abs(pct) > tolerance:
            moved.append({"field": field, "from": from_val, "to": to_val, "pct": pct})

    return {
        "baseline_path": None,
        "tolerance": tolerance,
        "moved": moved,
        "flagged": len(moved) > 0,
    }


def load_incrementality(path) -> dict:
    """Load and shape-validate a Layer-5 incrementality (IM) table.

    ``path`` is a JSON file shaped ``{"tiers": [{"tier", "value", "ci", "power",
    "window", "timestamp"}, ...]}`` — see wppc/references/incrementality-seam.md
    for the full contract. This function only loads and shape-validates the
    table; v1 never applies it to any score (see the seam in ``score.score``).

    Raises ``ValueError`` with a precise message naming the missing/malformed
    field and the tier index whenever the shape doesn't hold.
    """
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    if not isinstance(data, dict) or "tiers" not in data:
        raise ValueError(f"Incrementality file '{path}': missing top-level 'tiers' list.")

    tiers = data["tiers"]
    if not isinstance(tiers, list):
        raise ValueError(f"Incrementality file '{path}': 'tiers' must be a list.")

    for i, entry in enumerate(tiers):
        if not isinstance(entry, dict):
            raise ValueError(f"Incrementality file '{path}': tier {i} must be an object.")

        for field in _INCREMENTALITY_TIER_FIELDS:
            if field not in entry:
                raise ValueError(
                    f"Incrementality file '{path}': tier {i} is missing required field '{field}'."
                )

        value = entry["value"]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(
                f"Incrementality file '{path}': tier {i} field 'value' must be numeric, got {value!r}."
            )

        ci = entry["ci"]
        if not isinstance(ci, list) or len(ci) != 2:
            raise ValueError(
                f"Incrementality file '{path}': tier {i} field 'ci' must be a 2-list [lo, hi], got {ci!r}."
            )
        for bound in ci:
            if isinstance(bound, bool) or not isinstance(bound, (int, float)):
                raise ValueError(
                    f"Incrementality file '{path}': tier {i} field 'ci' entries must be numeric, got {ci!r}."
                )

        power = entry["power"]
        if isinstance(power, bool) or not isinstance(power, (int, float)):
            raise ValueError(
                f"Incrementality file '{path}': tier {i} field 'power' must be numeric, got {power!r}."
            )

    return data


def build_incrementality_meta(path, table: dict) -> dict:
    """Small run-metadata block recording the Layer-5 seam's v1 (inert) status.

    ``path`` is the incrementality-file path; ``table`` is the dict returned by
    ``load_incrementality``. v1 never applies the table to any score — see
    wppc/references/incrementality-seam.md.
    """
    return {
        "status": "provided, not applied (v1)",
        "path": path,
        "tiers": [entry["tier"] for entry in table["tiers"]],
    }


# ---------------------------------------------------------------------------
# Decision lens — the Scale / Cut / Watch call per segment.
#
# Deterministic from MAR (margin above replacement) and stabilization only. The
# whole rule lives in ONE place so the three output formats never disagree and
# there are no scattered thresholds:
#
#   Scale = stabilized AND MAR > 0   (real, confident surplus -> lean in)
#   Cut   = stabilized AND MAR < 0   (real, confident drag    -> pull back)
#   Watch = everything else          (not stabilized, or stabilized at MAR == 0)
#
# "Stabilized" means the segment cleared the empirical-Bayes stabilization bar
# (clicks >= k); score.py emits it as the "Y"/"N" flag consumed here.
# ---------------------------------------------------------------------------
def classify_decision(stabilized, mar) -> str:
    """Return "Scale", "Cut", or "Watch" for one segment (see block comment)."""
    is_stable = (stabilized == "Y") if isinstance(stabilized, str) else bool(stabilized)
    if not is_stable:
        return "Watch"
    if mar > 0:
        return "Scale"
    if mar < 0:
        return "Cut"
    return "Watch"


def _round_or_none(value, ndigits):
    """Round a numeric to ``ndigits``, or None for None/NaN."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return round(float(value), ndigits)


def _text_or_none(value):
    """Pass a text value through, or None for None/NaN. Mirrors report.py's
    helper of the same name, defined here so model.py is self-contained — the
    decay serializer below uses it, so build_model(..., decay=<frame>) must not
    depend on report.py's namespace."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _segment_row(row) -> dict:
    """One results-frame row -> the model's per-segment dict.

    Rounding mirrors report.py's Report tab exactly (wPPC/wPPC_shrunk/MAR/
    closing_ratio 2dp, wPPC+ 0dp, clicks/conversions int) so the model, the md
    table, and the xlsx cells carry byte-identical numbers. ``decision`` is
    derived from the ROUNDED MAR that is stored here, so the shown number and the
    shown label can never contradict each other.
    """
    mar = round(float(row["MAR"]), 2)
    stabilized = row["stabilized"]
    return {
        "segment_id": str(row["segment_id"]),
        "clicks": int(row["clicks"]),
        "conversions": int(row["conversions"]),
        "wPPC": round(float(row["wPPC"]), 2),
        "wPPC+": round(float(row["wPPC+"])),
        "wPPC_shrunk": round(float(row["wPPC_shrunk"]), 2),
        "MAR": mar,
        "stabilized": stabilized,
        "closing_ratio": round(float(row["closing_ratio"]), 2),
        "decision": classify_decision(stabilized, mar),
    }


def _weights_table(weights: Weights) -> list:
    """The derived-weight rows — the CLI-402 forward-contract row source for the
    ``derived_weights`` chart (fields ``state``, ``w``). Mirrors the xlsx Weights
    tab: one row per funnel state (with P/PE) plus a terminal ``repeat`` row
    (incremental weight only, P/PE = None)."""
    rows = [
        {
            "state": s,
            "w": round(weights.w[s], 4),
            "p": round(weights.p[s], 6),
            "pe": round(weights.pe[s], 4),
        }
        for s in FUNNEL_STATES
    ]
    rows.append({"state": "repeat", "w": round(weights.w["repeat"], 4), "p": None, "pe": None})
    return rows


def _decay_rows(decay: pd.DataFrame) -> list:
    """Serialize a decay frame to model rows. Rounding matches report.py's decay
    columns (prior/delta 0dp, delta_pct 4dp); trend passes through as text."""
    out = []
    for _, r in decay.iterrows():
        out.append({
            "segment_id": str(r["segment_id"]),
            "wPPC+_prior": _round_or_none(r["wPPC+_prior"], 0),
            "wPPC+_delta": _round_or_none(r["wPPC+_delta"], 0),
            "delta_pct": _round_or_none(r["delta_pct"], 4),
            "trend": _text_or_none(r["trend"]),
        })
    return out


def build_model(
    results: pd.DataFrame,
    weights: Weights,
    run_meta: dict,
    decay: pd.DataFrame | None = None,
) -> dict:
    """Assemble the single JSON-serializable model the three output formats consume.

    ``results`` is the scored frame from ``score.score`` (its ``.attrs`` scalars
    are already folded into ``run_meta`` by ``build_run_meta``). ``weights`` is the
    derived weight table. ``run_meta`` is the block from ``build_run_meta`` (it
    carries the injectable ``generated`` timestamp — the clock is NEVER read here).
    ``decay`` is the optional two-period wPPC+ movement frame from ``build_decay``.

    Every number is carried straight from ``results`` / ``weights`` / ``run_meta``;
    nothing is recomputed. The renderers TEMPLATE these values, they never
    re-derive them — determinism is preserved end to end.

    Returned top-level keys:
        provenance    — identity + generation + pass/status flags
        metadata      — methodology scalars (baseline, replacement, k, ...)
        segments      — per-segment rows (score columns + ``decision``)
        weights_table — derived-weight rows (the derived_weights chart's rows)
        self_check    — telescoping self-check {telescope_sum, cm3_order, pass}
        decision_lens — Scale/Cut/Watch summary counts {scale, cut, watch}
        decay         — {status, rows}: computed rows, or the not-run meta
        charts        — {declarations, row_source}: the 4 chart decls + the
                        per-chart row-source map (derived_weights -> weights_table,
                        the other three -> segments)
    """
    rm = run_meta

    decay_status = (rm.get("decay") or {}).get("status") if rm.get("decay") else None
    incr_meta = rm.get("incrementality")
    incrementality_status = incr_meta.get("status") if incr_meta else "not-provided"

    segments = [_segment_row(row) for _, row in results.iterrows()]

    counts = {"scale": 0, "cut": 0, "watch": 0}
    for seg in segments:
        counts[seg["decision"].lower()] += 1

    if decay is not None:
        decay_block = {"status": decay_status or "computed", "rows": _decay_rows(decay)}
    else:
        decay_block = {"status": decay_status or "not-run", "rows": []}

    provenance = {
        "platform": rm.get("platform"),
        "generated": rm.get("generated"),
        "n_segments": rm.get("n_segments"),
        "n_stabilized": rm.get("n_stabilized"),
        "k_source": rm.get("k_source"),
        "weights_version": rm.get("weights_version"),
        "drift": rm.get("drift"),
        "decay_status": decay_block["status"],
        "incrementality_status": incrementality_status,
    }

    metadata = {
        "platform": rm.get("platform"),
        "baseline": rm.get("baseline"),
        "replacement": rm.get("replacement"),
        "k": rm.get("k"),
        "k_source": rm.get("k_source"),
        "n_segments": rm.get("n_segments"),
        "n_stabilized": rm.get("n_stabilized"),
        "self_check_pass": rm.get("self_check_pass"),
        "telescope_sum": rm.get("telescope_sum"),
        "cm3_order": weights.cm3_order,
    }

    self_check = {
        "telescope_sum": round(weights.telescope_sum, 4),
        "cm3_order": round(weights.cm3_order, 4),
        "pass": bool(weights.self_check_pass),
    }

    charts = {
        "declarations": [dict(c) for c in WPPC_CHARTS],
        "row_source": dict(CHART_ROW_SOURCE),
    }

    return {
        "provenance": provenance,
        "metadata": metadata,
        "segments": segments,
        "weights_table": _weights_table(weights),
        "self_check": self_check,
        "decision_lens": counts,
        "decay": decay_block,
        "charts": charts,
    }
