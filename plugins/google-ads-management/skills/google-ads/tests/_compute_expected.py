#!/usr/bin/env python3
"""Compute a skill's default + tuned model summaries (isolated subprocess).

Usage:
    _compute_expected.py <scripts_dir> <core_module> <fixture> <tune_key> <tune_value>
        [<multi_key> <multi_drop>]
    _compute_expected.py --analytics <vectors.json> [<vectors.json> ...]

Prints JSON {"default": <summary>, "tuned": <summary>, "tune_value": <coerced>}.
Run as a subprocess (one per skill) by run_parity.py so each skill's `scripts/`
dir is the only one on sys.path — avoids sibling-module name collisions across
skills. The tuned summary recomputes `compute_model` with the findings' `params`
block overridden by {tune_key: tune_value} (every core resolves params from
findings.get("params"), so this is the same single-param override the widget
applies live).

Optional multi-select tuning: when <multi_key> <multi_drop> are given, also
recompute with the multi-valued param `multi_key` reduced to its default list
minus `multi_drop` (the one enum the widget operator unchecks). This mirrors the
checkbox-group ("multi") control toggling a value off, and adds
{"multi_scope": [...], "multi_tuned": <summary>} to the output so the JS<->Python
parity check can assert the live recompute matches after a match-type is dropped.

--analytics mode (HM-532): computes the Python side of the shared analytics-
primitives parity check. Each vectors.json holds {"concentration": [cases],
"signals": [cases], "pre_score": [cases]} (see
_shared/tests/analytics_vectors.json). Prints JSON {"js_mirror":
analytics.JS_MIRROR, "cases": [{"fn", "file", "i", "args", "expected"}]};
tuner_parity.mjs --analytics replays the cases through JS_MIRROR and asserts
equality.
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path


def _coerce(v: str):
    try:
        f = float(v)
        return int(f) if f.is_integer() else f
    except ValueError:
        return v


def _analytics_mode(vector_files: list[str]) -> int:
    """Compute Python-expected outputs for the shared analytics primitives."""
    plugin_root = Path(__file__).resolve().parents[3]   # tests -> google-ads -> skills -> plugin
    sys.path.insert(0, str(plugin_root / "_shared"))
    import analytics  # noqa: PLC0415 — path injected above

    fns = {"concentration":
               lambda c: analytics.concentration(c["rows"], c["value_key"],
                                                 c.get("top_n", 3)),
           "signals": lambda c: analytics.signals(c["rows"], c["rules"]),
           "pre_score": lambda c: analytics.pre_score(c["row"], c["weights"]),
           "segment_liveness":
               lambda c: analytics.segment_liveness(
                   c["rows"], status_key=c["status_key"], spend_key=c["spend_key"],
                   prior_spend_key=c.get("prior_spend_key"))}
    cases = []
    for vf in vector_files:
        data = json.loads(Path(vf).read_text(encoding="utf-8"))
        name = Path(vf).name
        for fn, compute in fns.items():
            for i, case in enumerate(data.get(fn, [])):
                cases.append({"fn": fn, "file": name, "i": i, "args": case,
                              "expected": compute(case)})
    if not cases:
        print("no analytics vectors found in: " + ", ".join(vector_files),
              file=sys.stderr)
        return 2
    print(json.dumps({"js_mirror": analytics.JS_MIRROR, "cases": cases}))
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--analytics":
        return _analytics_mode(sys.argv[2:])
    scripts_dir, core_module, fixture, tune_key, tune_value = sys.argv[1:6]
    multi_key = sys.argv[6] if len(sys.argv) > 6 else None
    multi_drop = sys.argv[7] if len(sys.argv) > 7 else None
    scripts_dir = Path(scripts_dir).resolve()
    plugin_root = scripts_dir.parents[2]          # .../skills/<skill>/scripts -> plugin root
    sys.path.insert(0, str(scripts_dir))
    sys.path.insert(0, str(plugin_root / "_shared"))
    core = importlib.import_module(core_module)

    tv = _coerce(tune_value)
    findings = core.load_findings(fixture)
    m = core.compute_model(findings)
    default_params = dict(m["params"])
    tuned_params = dict(default_params)
    tuned_params[tune_key] = tv
    findings_tuned = dict(findings)
    findings_tuned["params"] = tuned_params
    m2 = core.compute_model(findings_tuned)

    out = {"default": m["summary"], "tuned": m2["summary"], "tune_value": tv}

    # Full-model extras for the bounded-embed trim check — emitted ONLY for a model
    # whose sensitivity/near-miss shape matches the waste filter's (other skills name
    # these differently or omit them). The trim test asserts the trimmed widget
    # reproduces these from its in-play envelope; non-trim skills never read them.
    sens = m.get("sensitivity") or []
    if sens and isinstance(sens[0], dict) and {"cost_multiple", "total"} <= set(sens[0]):
        out["sensitivity"] = [{"cost_multiple": r["cost_multiple"], "total": r["total"]} for r in sens]
    nm = (m.get("near_misses_block1") or []) + (m.get("near_misses_block2") or [])
    terms = [r["term"] for r in nm if isinstance(r, dict) and "term" in r]
    if terms:
        out["near_miss_terms"] = sorted(set(terms))

    if multi_key and multi_drop:
        # The default multi-valued list with one entry unchecked — the same edit
        # the widget's "multi" checkbox group makes to P[multi_key] on toggle.
        scope = [v for v in (default_params.get(multi_key) or []) if v != multi_drop]
        multi_params = dict(default_params)
        multi_params[multi_key] = scope
        findings_multi = dict(findings)
        findings_multi["params"] = multi_params
        m3 = core.compute_model(findings_multi)
        out["multi_scope"] = scope
        out["multi_tuned"] = m3["summary"]

    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
