#!/usr/bin/env python3
"""Python side of this skill's OWN n-gram JS<->Python parity check (HM-536).

Not the shared hub harness (skills/google-ads/tests/run_parity.py + friends
are frozen during the parallel-batch build — see docs/orchestration.md) — a
standalone check, scoped to this skill's own tests/, for the
gxTermNgrams/gxWasteNgrams mirror spliced into waste_filter_spec.JS_KERNEL.
The shared analytics-primitives gate (run_parity.py analytics-primitives)
already covers the generic `concentration` arithmetic these functions call
(via this skill's own tests/analytics_vectors_ngram.json); this script proves
the tokenization + aggregation pipeline around it matches too.

Usage:
    python3 tests/_compute_ngram_expected.py <fixture.json> <tune_key> <tune_value>

Prints {"js_kernel": <the exact deployed js_kernel string, incl. analytics
mirror>, "rows": <html_embed rows, JS row shape>, "params": <default params>,
"expected_default": model.ngrams, "tuned_params": <...>,
"expected_tuned": tuned_model.ngrams}. `rows` is unchanged by tuning (only
`classify(r,P)` output changes; gxWasteNgrams recomputes live from the same
embedded rows, exactly like the widget/explorer does).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE.parents[2] / "_shared"))

import waste_filter_core as core  # noqa: E402
import waste_filter_spec as wfspec  # noqa: E402


def _coerce(v: str):
    try:
        f = float(v)
        return int(f) if f.is_integer() else f
    except ValueError:
        return v


def main() -> int:
    fixture, tune_key, tune_value = sys.argv[1:4]
    tv = _coerce(tune_value)

    findings = core.load_findings(fixture)
    model = core.compute_model(findings)
    embed = wfspec.html_embed(model)

    tuned_findings = dict(findings)
    tuned_params = dict(model["params"])
    tuned_params[tune_key] = tv
    tuned_findings["params"] = tuned_params
    tuned_model = core.compute_model(tuned_findings)

    out = {
        "js_kernel": wfspec.SPEC["js_kernel"],
        "rows": embed["rows"],
        "params": model["params"],
        "expected_default": model["ngrams"],
        "tuned_params": tuned_model["params"],
        "expected_tuned": tuned_model["ngrams"],
    }
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
