"""Shared fixtures for the wPPC test-suite.

The worked-example numbers live ONLY here (and in the spec) — never in library
logic. Weights, k, baseline, and replacement are always derived at runtime.
"""

import pandas as pd
import pytest

from wppc.weights import FUNNEL_STATES, derive_weights_from_p

# Worked-example P(purchase|S) table (illustrative; from the framework doc).
EXAMPLE_P = {
    "click": 0.025,
    "engagement": 0.055,
    "add_to_cart": 0.200,
    "initiate_checkout": 0.420,
    "purchase": 1.000,
}
EXAMPLE_CM3_ORDER = 42.00
EXAMPLE_REPEAT_RATE = 0.50
EXAMPLE_CM3_REPEAT = 42.00

# Expected incremental weights for the table above.
EXPECTED_WEIGHTS = {
    "click": 1.05,
    "engagement": 1.26,
    "add_to_cart": 6.09,
    "initiate_checkout": 9.24,
    "purchase": 24.36,
    "repeat": 21.00,
}


@pytest.fixture
def example_weights():
    """Weights derived from the worked-example P table."""
    return derive_weights_from_p(
        EXAMPLE_P, EXAMPLE_CM3_ORDER, EXAMPLE_REPEAT_RATE, EXAMPLE_CM3_REPEAT
    )


def make_segments(rows):
    """Build a normalized scoring frame from a list of dicts.

    Each row dict provides: segment_id and the five funnel reach counts
    (click, engagement, add_to_cart, initiate_checkout, purchase) plus repeats.
    ``clicks`` (the wPPC denominator) defaults to the click reach.
    """
    records = []
    for r in rows:
        rec = {"segment_id": r["segment_id"]}
        rec["clicks"] = r.get("clicks", r["click"])
        for s in FUNNEL_STATES:
            rec[s] = r[s]
        rec["repeats"] = r.get("repeats", 0)
        records.append(rec)
    return pd.DataFrame.from_records(records)
