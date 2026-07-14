#!/usr/bin/env python3
"""Tests for the shared analytics primitives (stdlib only; run directly).

    python3 _shared/tests/test_analytics.py

Covers concentration (top-N share / HHI / effective-N: known values, empty,
zero-sum, single row, ties, fractional, coercion, top_n clamping), signals
(absolute + relative rules, every op, missing-field no-fire, malformed-rule
ValueError), pre_score (weighted sums, dedupe, unweighted flags, weight
validation), determinism (shuffled input rows / flags -> identical output),
and the kernel-mirror contract's rounding helper. Exit 0 = all pass, 1 = a
failure.
"""
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHARED = HERE.parent
sys.path.insert(0, str(SHARED))

import analytics as A  # noqa: E402

_failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        _failures.append(name)


# ── rounding helper (the kernel-mirror contract) ────────────────────────────
print("rounding")
check("half-up at .5", A._round_half_up(0.12345, 4) == 0.1235)
check("half-up 2dp", A._round_half_up(2.675000001, 2) == 2.68)
check("integers unchanged", A._round_half_up(3.0, 1) == 3.0)
check("zero", A._round_half_up(0.0, 4) == 0.0)

# ── concentration ───────────────────────────────────────────────────────────
print("concentration")
rows = [{"name": "a", "cost": 500.0}, {"name": "b", "cost": 300.0},
        {"name": "c", "cost": 150.0}, {"name": "d", "cost": 50.0}]
c = A.concentration(rows, "cost", top_n=2)
check("n / n_nonzero", c["n"] == 4 and c["n_nonzero"] == 4)
check("total", c["total"] == 1000.0)
check("top-2 share", c["top_share"] == 0.8, str(c))
# HHI = (0.5^2 + 0.3^2 + 0.15^2 + 0.05^2) * 10000 = 3650.0
check("hhi", c["hhi"] == 3650.0, str(c))
# effective_n = 1/0.365 = 2.7397... -> 2.74
check("effective_n", c["effective_n"] == 2.74, str(c))

eq4 = A.concentration([{"v": 25} for _ in range(4)], "v", top_n=4)
check("equal split hhi = 10000/k", eq4["hhi"] == 2500.0)
check("equal split effective_n = k", eq4["effective_n"] == 4.0)
check("equal split full top share = 1", eq4["top_share"] == 1.0)

mono = A.concentration([{"v": 10}], "v", top_n=3)
check("single row hhi = 10000", mono["hhi"] == 10000.0)
check("single row top_n clamped", mono["top_n"] == 1)
check("single row share = 1", mono["top_share"] == 1.0)

empty = A.concentration([], "v", top_n=3)
check("empty rows all-zero", empty == {"n": 0, "n_nonzero": 0, "top_n": 0,
                                       "total": 0.0, "top_share": 0.0,
                                       "hhi": 0.0, "effective_n": 0.0}, str(empty))
zero = A.concentration([{"v": 0}, {"v": 0}], "v")
check("zero-sum all-zero metrics", zero["hhi"] == 0.0 and zero["top_share"] == 0.0
      and zero["effective_n"] == 0.0 and zero["n"] == 2 and zero["n_nonzero"] == 0)

ties = A.concentration([{"v": 100}, {"v": 100}, {"v": 100}], "v", top_n=2)
check("ties: top-2 of 3 equal = 2/3", ties["top_share"] == 0.6667, str(ties))

frac = A.concentration([{"v": 0.03}, {"v": 0.01}], "v", top_n=1)
check("fractional values", frac["top_share"] == 0.75 and frac["total"] == 0.04, str(frac))

coerce = A.concentration([{"v": 5}, {"v": -3}, {"v": None}, {"v": "7"},
                          {"v": float("nan")}, {"v": True}, {}], "v", top_n=10)
check("coercion: negatives/None/str/nan/bool/missing -> 0",
      coerce["total"] == 5.0 and coerce["n_nonzero"] == 1, str(coerce))
check("top_n > n clamps", coerce["top_n"] == 7)
check("top_n = 0 -> zero share", A.concentration(rows, "cost", top_n=0)["top_share"] == 0.0)

# ── signals ─────────────────────────────────────────────────────────────────
print("signals")
RULES = [
    {"id": "high_cost", "key": "cost", "op": "gt", "value": 100},
    {"id": "no_conv", "key": "conversions", "op": "eq", "value": 0},
    {"id": "cost_over_avg", "key": "cost", "op": "ge", "value_key": "avg_cost",
     "mult": 2.0},
    {"id": "low_ctr", "key": "ctr", "op": "lt", "value": 0.01},
]
srows = [
    {"cost": 250.0, "conversions": 0, "avg_cost": 100.0, "ctr": 0.005},
    {"cost": 50.0, "conversions": 3, "avg_cost": 100.0, "ctr": 0.02},
    {"cost": 200.0, "conversions": 1, "ctr": 0.02},        # no avg_cost
    {"cost": None, "conversions": 0},                       # missing operands
]
flags = A.signals(srows, RULES)
check("row0 fires all applicable", flags[0] == ["high_cost", "no_conv",
                                                "cost_over_avg", "low_ctr"], str(flags[0]))
check("row1 fires none", flags[1] == [])
check("relative rule needs value_key present", flags[2] == ["high_cost"], str(flags[2]))
check("missing operand = no fire (not zero)", flags[3] == ["no_conv"], str(flags[3]))
check("row order preserved", len(flags) == 4)

ops = A.signals([{"x": 5}], [
    {"id": "gt", "key": "x", "op": "gt", "value": 4},
    {"id": "ge", "key": "x", "op": "ge", "value": 5},
    {"id": "lt", "key": "x", "op": "lt", "value": 6},
    {"id": "le", "key": "x", "op": "le", "value": 5},
    {"id": "eq", "key": "x", "op": "eq", "value": 5},
    {"id": "ne", "key": "x", "op": "ne", "value": 4},
])[0]
check("every op fires when true", ops == ["gt", "ge", "lt", "le", "eq", "ne"], str(ops))
check("boundary: gt not ge", A.signals([{"x": 4}], [
    {"id": "gt", "key": "x", "op": "gt", "value": 4}])[0] == [])
check("empty rows / rules", A.signals([], RULES) == [] and A.signals(srows, [])
      == [[], [], [], []])

for bad, why in [
    ({"key": "x", "op": "gt", "value": 1}, "missing id"),
    ({"id": "r", "op": "gt", "value": 1}, "missing key"),
    ({"id": "r", "key": "x", "op": "??", "value": 1}, "unknown op"),
    ({"id": "r", "key": "x", "op": "gt"}, "no value or value_key"),
    ({"id": "r", "key": "x", "op": "gt", "value": 1, "value_key": "y"}, "both value and value_key"),
    ({"id": "r", "key": "x", "op": "gt", "value": float("nan")}, "nan value"),
    ({"id": "r", "key": "x", "op": "gt", "value": "5"}, "string value"),
    ({"id": "r", "key": "x", "op": "gt", "value_key": "y", "mult": "2"}, "string mult"),
]:
    try:
        A.signals([{"x": 1}], [bad])
        check(f"malformed rule raises ({why})", False)
    except ValueError:
        check(f"malformed rule raises ({why})", True)

# ── pre_score ───────────────────────────────────────────────────────────────
print("pre_score")
W = {"high_cost": 3.0, "no_conv": 5.0, "low_ctr": 1.5}
check("weighted sum", A.pre_score({"flags": ["high_cost", "no_conv"]}, W) == 8.0)
check("duplicates count once", A.pre_score({"flags": ["no_conv", "no_conv"]}, W) == 5.0)
check("unweighted flag = 0", A.pre_score({"flags": ["mystery"]}, W) == 0.0)
check("no flags key", A.pre_score({}, W) == 0.0)
check("empty weights", A.pre_score({"flags": ["high_cost"]}, {}) == 0.0)
check("fractional rounding 4dp",
      A.pre_score({"flags": ["a", "b"]}, {"a": 0.00005, "b": 0.0001}) == 0.0002)
for badw, why in [({"a": -1}, "negative"), ({"a": float("inf")}, "inf"),
                  ({"a": "3"}, "string")]:
    try:
        A.pre_score({"flags": ["a"]}, badw)
        check(f"bad weight raises ({why})", False)
    except ValueError:
        check(f"bad weight raises ({why})", True)

# ── determinism: input order never changes a result ─────────────────────────
print("determinism")
rng = random.Random(42)
big = [{"id": i, "cost": rng.uniform(0, 1000), "conversions": rng.choice([0, 1, 5]),
        "avg_cost": 400.0, "ctr": rng.uniform(0, 0.05)} for i in range(200)]
base_c = A.concentration(big, "cost", top_n=10)
base_flags = {r["id"]: f for r, f in zip(big, A.signals(big, RULES))}
ok_c = ok_s = True
for trial in range(5):
    shuf = big[:]
    rng.shuffle(shuf)
    if A.concentration(shuf, "cost", top_n=10) != base_c:
        ok_c = False
    if {r["id"]: f for r, f in zip(shuf, A.signals(shuf, RULES))} != base_flags:
        ok_s = False
check("concentration invariant under row shuffle", ok_c)
check("signals invariant under row shuffle (per-row)", ok_s)
fl = ["b", "a", "c", "a"]
check("pre_score invariant under flag shuffle",
      A.pre_score({"flags": fl}, {"a": 0.1, "b": 0.2, "c": 0.3})
      == A.pre_score({"flags": list(reversed(fl))}, {"a": 0.1, "b": 0.2, "c": 0.3}))

# ── JS mirror sanity (full parity lives in the Node gate) ───────────────────
print("js mirror")
check("JS_MIRROR defines all three kernels",
      all(f"function gx{n}" in A.JS_MIRROR
          for n in ("Concentration", "Signals", "PreScore", "RoundHalfUp")))
check("JS_MIRROR is self-contained ASCII", A.JS_MIRROR.isascii())

print()
if _failures:
    print(f"{len(_failures)} FAILURE(S): " + ", ".join(_failures))
    sys.exit(1)
print("all analytics tests passed")
