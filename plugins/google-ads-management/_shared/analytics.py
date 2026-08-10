#!/usr/bin/env python3
# Copyright (c) 2026 Clickt Digital Marketing Inc. All rights reserved.
"""Reusable analytics primitives for the google-ads-management skills —
concentration, declarative signals, and severity pre-scoring, in pure stdlib.

Back-ports the machine-computed analytics pattern proven in the audit plugins
(`plugins/meta-ads-audit/.../concentration.py` + `prescore.py`,
`plugins/shopify-cro-audit/.../concentration.py`), which themselves mirror the
MediaMetrics analytics module. The HHI / Effective-N / top-N-share arithmetic
here is the SAME math as those modules; only the coercion rule deviates
(deliberately — see "Kernel-mirror contract" below).

Every primitive is:
  - pure stdlib (`math` only) — importable everywhere, never openpyxl;
  - deterministic — no wall clock, no dict-order dependence, canonical value
    ordering before every float sum (input row order never changes a result);
  - kernel-mirrorable — expressible verbatim in browser JS and xlsx formulas.
    `JS_MIRROR` (bottom of this module) is the canonical JS translation;
    skills splice it into their spec's `js_kernel` instead of re-writing it,
    and the Node<->Python parity gate (`skills/google-ads/tests/run_parity.py
    analytics-primitives`) asserts it against this module on shared vectors.

Kernel-mirror contract (normative — JS and xlsx must match this verbatim)
=========================================================================

Rounding — `_round_half_up(x, nd)`, defined for x >= 0 only:
    floor(x * 10^nd + 0.5) / 10^nd
  JS:   Math.floor(x * Math.pow(10, nd) + 0.5) / Math.pow(10, nd)
  xlsx: ROUND(x, nd)
  All rounded quantities in this module are >= 0, so half-away-from-zero and
  half-up coincide and all three environments agree. (Python's built-in
  round() is banker's rounding and is NEVER used here.) Caveat: xlsx ROUND is
  decimal-based; a value whose binary double lands exactly on a .5 boundary
  after `x * 10^nd` float error can differ in the last decimal — keep
  thresholds and fixtures away from exact .5 boundaries.

Numeric coercion — two rules, applied per primitive:
  - `_nonneg(v)` (concentration values): v is numeric-typed and finite -> v,
    clipped to >= 0; anything else (missing / None / bool / string / NaN /
    inf) -> 0.0.  JS: (typeof v === "number" && isFinite(v)) ? Math.max(0, v)
    : 0.  DELIBERATE DEVIATION from the audit plugins' `_nonneg`, which
    coerces numeric STRINGS via float(v): string parsing is not mirrorable
    across Python/JS/xlsx ("3e2", "  4."), and the transcription-firewall
    assemblers already deliver typed floats, so strings count as 0 here.
  - `_num(v)` (signal operands): numeric-typed and finite -> float(v),
    anything else -> None ("no signal" — the rule does NOT fire; a missing
    field is never treated as 0).

Ordering — before any float sum, values are put in a canonical order:
  concentration sorts values descending; pre_score sums over the SORTED SET
  of flag ids. Float addition is order-dependent; canonical order makes every
  result independent of input row/flag order (asserted in tests).

concentration(rows, value_key, top_n=3) -> dict
  values   = [_nonneg(row.get(value_key)) for row in rows], sorted DESC
  total    = sum(values)                        # desc order
  if total <= 0 (or rows empty): top_share = hhi = effective_n = 0.0
  else:
    top_share   = _round_half_up(sum(values[:max(0, top_n)]) / total, 4)
    ssq         = sum((v / total)^2 for v in values)   # desc order
    hhi         = _round_half_up(ssq * 10000, 1)       # 0..10,000 scale
    effective_n = _round_half_up(1 / ssq, 2)           # inverse Simpson
  returns {"n": len(rows), "n_nonzero": count(v > 0), "top_n": min(top_n, n)
           clipped >= 0, "total": _round_half_up(total, 4),
           "top_share", "hhi", "effective_n"}
  xlsx: total = SUM(range); top_share = ROUND(SUM(LARGE(range, {1..k})) /
  total, 4); hhi = ROUND(SUMPRODUCT((range/total)^2) * 10000, 1);
  effective_n = ROUND(1 / SUMPRODUCT((range/total)^2), 2).

signals(rows, rules) -> list[list[str]]  (one flag-id list per row, in order)
  Each rule is a dict:
    {"id": str, "key": str, "op": "gt"|"ge"|"lt"|"le"|"eq"|"ne",
     "value": number}                             # absolute threshold
    or
    {"id", "key", "op", "value_key": str, "mult": number (default 1.0)}
                                                  # relative: row[value_key]*mult
  For each row, rules are evaluated in DECLARATION ORDER; a rule fires when
  _num(row[key]) op threshold is true. If _num(row[key]) is None — or, for
  the relative form, _num(row[value_key]) is None — the rule does not fire
  (missing data is no signal, mirroring the audit pre-scorer's skip
  discipline). eq/ne are exact float comparisons (== / !=; JS === / !==).
  Malformed rules (unknown op, missing id/key, neither value nor value_key,
  non-finite threshold, `mult` on an absolute `value` rule) raise ValueError —
  a spec bug fails loudly. `mult` is meaningful ONLY in the relative form: an
  absolute rule carrying it would silently compare against the unscaled
  `value`, so it is rejected rather than ignored.
  xlsx: one boolean column per rule, e.g. =IF(ISNUMBER(v), v > t, FALSE).

pre_score(row, weights) -> float
  flags = row.get("flags") or []; score = sum(weights[f] for f in
  sorted(set(flags)) if f in weights); returns _round_half_up(score, 4).
  Duplicate flags count once; flags without a weight contribute 0. Weights
  must be finite numbers >= 0 (ValueError otherwise — keeps the score in the
  half-up rounding domain).
  xlsx: SUMPRODUCT(flag_booleans, weights) with each flag a 0/1 column.

segment_liveness(rows, *, status_key, spend_key, prior_spend_key=None)
    -> list[dict]  (one shallow-copied row per input row, order preserved,
                    with a "liveness" field added — never mutates the input)
  Classifies every row into one of three liveness bands, so a scoring skill
  can gate its severity/recommendation universe on live+recently_active and
  leave long-dead campaigns present-but-tagged (no-row-loss) generating zero
  recommendations. Per row, with cur = _nonneg(row[spend_key]) (current-window
  spend), prior = _nonneg(row[prior_spend_key]) if prior_spend_key else 0
  (prior-window spend; 0 when no prior window is available), and enabled =
  (row[status_key] is a string that upper/strip-normalizes to "ENABLED"):
    live            = enabled AND cur > 0
    recently_active = any recent signal that isn't live —
                      enabled (enabled-but-idle: cur == 0)
                      OR cur > 0 (PAUSED/REMOVED but spent mid-window)
                      OR prior > 0 (spend only in the prior window)
    dormant         = NOT enabled AND cur == 0 AND prior == 0
  Equivalent branch order (mirrored verbatim): live if enabled & cur>0; else
  recently_active if (enabled | cur>0 | prior>0); else dormant. Spend coercion
  is `_nonneg` (missing/None/negative/non-numeric -> 0, so "zero spend" and
  "spend > 0" are well-defined); status coercion is exact string ==/=== after
  upper+strip, so a non-string or non-"ENABLED" status is "not enabled".
  Two-band degradation: when prior_spend_key is None the prior-window signal
  can't fire (prior is always 0) — live/recently_active/dormant are still all
  reachable, but the "spent only in the prior window" path is unavailable; a
  skill with a single window documents this rather than inventing prior data.
  xlsx: one text column, e.g. =IF(AND(UPPER(status)="ENABLED", cur>0), "live",
  IF(OR(UPPER(status)="ENABLED", cur>0, prior>0), "recently_active", "dormant")).

Stdlib only.
"""
from __future__ import annotations

import math

__all__ = ["concentration", "signals", "pre_score", "segment_liveness", "JS_MIRROR"]

_OPS = ("gt", "ge", "lt", "le", "eq", "ne")


def _round_half_up(x: float, nd: int) -> float:
    """Half-up rounding for x >= 0 (kernel-mirror contract; see module doc)."""
    q = 10 ** nd
    return math.floor(x * q + 0.5) / q


def _is_finite_number(v) -> bool:
    """True only for real numeric types (bool excluded) that are finite."""
    return (isinstance(v, (int, float)) and not isinstance(v, bool)
            and math.isfinite(v))


def _nonneg(v) -> float:
    """Concentration coercion: finite number -> clipped to >= 0, else 0.0."""
    if not _is_finite_number(v):
        return 0.0
    return float(v) if v > 0 else 0.0


def _num(v) -> float | None:
    """Signal-operand coercion: finite number -> float, else None (no signal)."""
    return float(v) if _is_finite_number(v) else None


def _status_enabled(v) -> bool:
    """Liveness status coercion: a string that upper/strip-normalizes to
    "ENABLED" -> True, anything else -> False (kernel-mirror contract; handles
    both the GAQL enum "ENABLED" and the Google Ads UI export label "Enabled")."""
    return isinstance(v, str) and v.strip().upper() == "ENABLED"


def concentration(rows, value_key: str, top_n: int = 3) -> dict:
    """Top-N share + HHI + Effective-N over rows[i][value_key].

    Deterministic and order-independent: values are sorted descending before
    every sum. Empty rows / zero-sum -> all-zero metrics. See the module
    docstring for the exact arithmetic (the kernel-mirror contract)."""
    values = sorted((_nonneg((r or {}).get(value_key)) for r in (rows or [])),
                    reverse=True)
    n = len(values)
    k = max(0, min(int(top_n), n))
    total = 0.0
    for v in values:
        total += v
    n_nonzero = sum(1 for v in values if v > 0)
    if total <= 0:
        top_share = hhi = effective_n = 0.0
    else:
        top = 0.0
        for v in values[:k]:
            top += v
        top_share = _round_half_up(top / total, 4)
        ssq = 0.0
        for v in values:
            s = v / total
            ssq += s * s
        hhi = _round_half_up(ssq * 10000.0, 1)
        effective_n = _round_half_up(1.0 / ssq, 2) if ssq > 0 else 0.0
    return {"n": n, "n_nonzero": n_nonzero, "top_n": k,
            "total": _round_half_up(total, 4), "top_share": top_share,
            "hhi": hhi, "effective_n": effective_n}


def _validate_rule(rule) -> None:
    if not isinstance(rule, dict):
        raise ValueError("signals: rule must be a dict, got %r" % (rule,))
    rid, key, op = rule.get("id"), rule.get("key"), rule.get("op")
    if not rid or not isinstance(rid, str):
        raise ValueError("signals: rule missing string 'id': %r" % (rule,))
    if not key or not isinstance(key, str):
        raise ValueError("signals: rule %r missing string 'key'" % (rid,))
    if op not in _OPS:
        raise ValueError("signals: rule %r has unknown op %r (want one of %s)"
                         % (rid, op, "/".join(_OPS)))
    has_value = "value" in rule
    has_vkey = "value_key" in rule
    if has_value == has_vkey:   # neither, or both
        raise ValueError("signals: rule %r needs exactly one of "
                         "'value' or 'value_key'" % (rid,))
    if has_value:
        if _num(rule["value"]) is None:
            raise ValueError("signals: rule %r 'value' is not a finite number: %r"
                             % (rid, rule["value"]))
        if "mult" in rule:
            raise ValueError("signals: rule %r has 'mult' but no 'value_key' "
                             "('mult' scales a relative threshold; an absolute "
                             "'value' rule would silently ignore it)" % (rid,))
    if has_vkey:
        if not isinstance(rule["value_key"], str) or not rule["value_key"]:
            raise ValueError("signals: rule %r 'value_key' must be a "
                             "non-empty string" % (rid,))
        if "mult" in rule and _num(rule["mult"]) is None:
            raise ValueError("signals: rule %r 'mult' is not a finite "
                             "number: %r" % (rid, rule["mult"]))


def _fires(v: float, op: str, t: float) -> bool:
    if op == "gt":
        return v > t
    if op == "ge":
        return v >= t
    if op == "lt":
        return v < t
    if op == "le":
        return v <= t
    if op == "eq":
        return v == t
    return v != t   # "ne" — _validate_rule already rejected unknown ops


def signals(rows, rules) -> list:
    """Per-row flag lists from declarative threshold/relative rules.

    Returns one list of fired rule ids per input row (row order preserved;
    flags in rule declaration order). Missing/non-numeric operands mean the
    rule does not fire. Malformed rules raise ValueError. See the module
    docstring for the exact semantics (the kernel-mirror contract)."""
    rules = list(rules or [])
    for rule in rules:
        _validate_rule(rule)
    out = []
    for r in (rows or []):
        r = r or {}
        flags = []
        for rule in rules:
            v = _num(r.get(rule["key"]))
            if v is None:
                continue
            if "value_key" in rule:
                base = _num(r.get(rule["value_key"]))
                if base is None:
                    continue
                t = base * float(rule.get("mult", 1.0))
            else:
                t = float(rule["value"])
            if _fires(v, rule["op"], t):
                flags.append(rule["id"])
        out.append(flags)
    return out


def pre_score(row, weights) -> float:
    """Severity pre-score: weighted sum over the row's UNIQUE flags.

    row["flags"] is a list of flag ids (duplicates count once); weights maps
    flag id -> finite weight >= 0 (ValueError otherwise). Flags without a
    weight contribute 0. Summation runs over the sorted flag-id set, so the
    result is independent of flag order. Rounded half-up to 4dp. See the
    module docstring for the exact arithmetic (the kernel-mirror contract)."""
    weights = weights or {}
    for fid in sorted(weights):
        w = _num(weights[fid])
        if w is None or w < 0:
            raise ValueError("pre_score: weight for %r must be a finite "
                             "number >= 0, got %r" % (fid, weights[fid]))
    flags = sorted({str(f) for f in ((row or {}).get("flags") or [])})
    score = 0.0
    for fid in flags:
        if fid in weights:
            score += float(weights[fid])
    return _round_half_up(score, 4)


def segment_liveness(rows, *, status_key: str, spend_key: str,
                     prior_spend_key: str | None = None) -> list:
    """Annotate every row with a `liveness` band (live/recently_active/dormant).

    Returns one shallow copy of each input row with `liveness` added (input
    rows are never mutated; order preserved). See the module docstring for the
    exact three-band contract (the kernel-mirror contract). Deterministic and
    row-order-independent — each row's band depends only on its own fields."""
    out = []
    for r in (rows or []):
        r = r or {}
        cur = _nonneg(r.get(spend_key))
        prior = _nonneg(r.get(prior_spend_key)) if prior_spend_key else 0.0
        enabled = _status_enabled(r.get(status_key))
        if enabled and cur > 0:
            liveness = "live"
        elif enabled or cur > 0 or prior > 0:
            liveness = "recently_active"
        else:
            liveness = "dormant"
        out.append({**r, "liveness": liveness})
    return out


# ---------------------------------------------------------------------------
# Canonical JS mirror — splice into a skill spec's `js_kernel` verbatim.
# The parity gate (run_parity.py analytics-primitives) evaluates THIS string
# against the Python functions above on shared vectors; edit both together.
# ---------------------------------------------------------------------------
JS_MIRROR = r"""
function gxRoundHalfUp(x, nd) {
  var q = Math.pow(10, nd);
  return Math.floor(x * q + 0.5) / q;
}
function gxNonneg(v) {
  return (typeof v === "number" && isFinite(v) && v > 0) ? v : 0;
}
function gxNum(v) {
  return (typeof v === "number" && isFinite(v)) ? v : null;
}
function gxStatusEnabled(v) {
  return typeof v === "string" && v.trim().toUpperCase() === "ENABLED";
}
function gxConcentration(rows, valueKey, topN) {
  if (topN === undefined) topN = 3;
  var values = (rows || []).map(function (r) { return gxNonneg((r || {})[valueKey]); });
  values.sort(function (a, b) { return b - a; });
  var n = values.length;
  var k = Math.max(0, Math.min(Math.trunc(topN), n));
  var total = 0, i;
  for (i = 0; i < n; i++) total += values[i];
  var nNonzero = 0;
  for (i = 0; i < n; i++) if (values[i] > 0) nNonzero++;
  var topShare = 0, hhi = 0, effN = 0;
  if (total > 0) {
    var top = 0;
    for (i = 0; i < k; i++) top += values[i];
    topShare = gxRoundHalfUp(top / total, 4);
    var ssq = 0;
    for (i = 0; i < n; i++) { var s = values[i] / total; ssq += s * s; }
    hhi = gxRoundHalfUp(ssq * 10000, 1);
    effN = ssq > 0 ? gxRoundHalfUp(1 / ssq, 2) : 0;
  }
  return { n: n, n_nonzero: nNonzero, top_n: k, total: gxRoundHalfUp(total, 4),
           top_share: topShare, hhi: hhi, effective_n: effN };
}
function gxSignals(rows, rules) {
  rules = rules || [];
  return (rows || []).map(function (r) {
    r = r || {};
    var flags = [];
    for (var j = 0; j < rules.length; j++) {
      var rule = rules[j];
      var v = gxNum(r[rule.key]);
      if (v === null) continue;
      var t;
      if ("value_key" in rule) {
        var base = gxNum(r[rule.value_key]);
        if (base === null) continue;
        t = base * (rule.mult === undefined ? 1.0 : rule.mult);
      } else {
        t = rule.value;
      }
      var op = rule.op, fires = false;
      if (op === "gt") fires = v > t;
      else if (op === "ge") fires = v >= t;
      else if (op === "lt") fires = v < t;
      else if (op === "le") fires = v <= t;
      else if (op === "eq") fires = v === t;
      else if (op === "ne") fires = v !== t;
      if (fires) flags.push(rule.id);
    }
    return flags;
  });
}
function gxPreScore(row, weights) {
  weights = weights || {};
  var seen = {};
  var flags = ((row || {}).flags || []).map(String).filter(function (f) {
    if (seen[f]) return false;
    seen[f] = true;
    return true;
  });
  flags.sort();
  var score = 0;
  for (var i = 0; i < flags.length; i++) {
    if (Object.prototype.hasOwnProperty.call(weights, flags[i])) score += weights[flags[i]];
  }
  return gxRoundHalfUp(score, 4);
}
function gxSegmentLiveness(rows, statusKey, spendKey, priorSpendKey) {
  return (rows || []).map(function (r) {
    r = r || {};
    var cur = gxNonneg(r[spendKey]);
    var prior = priorSpendKey ? gxNonneg(r[priorSpendKey]) : 0;
    var enabled = gxStatusEnabled(r[statusKey]);
    var liveness;
    if (enabled && cur > 0) liveness = "live";
    else if (enabled || cur > 0 || prior > 0) liveness = "recently_active";
    else liveness = "dormant";
    var out = {};
    for (var k in r) {
      if (Object.prototype.hasOwnProperty.call(r, k)) out[k] = r[k];
    }
    out.liveness = liveness;
    return out;
  });
}
"""
