"""Weight derivation + telescoping self-check."""

import pytest

from wppc.weights import FUNNEL_STATES, derive_weights, derive_weights_from_p

from conftest import (
    EXAMPLE_CM3_ORDER,
    EXAMPLE_CM3_REPEAT,
    EXAMPLE_P,
    EXAMPLE_REPEAT_RATE,
    EXPECTED_WEIGHTS,
)


def test_weights_reproduce_example_from_p(example_weights):
    w = example_weights.w
    for state, expected in EXPECTED_WEIGHTS.items():
        assert round(w[state], 2) == expected, state


def test_telescope_sum_equals_cm3_order(example_weights):
    telescoped = sum(example_weights.w[s] for s in FUNNEL_STATES)
    assert round(telescoped, 2) == EXAMPLE_CM3_ORDER
    assert example_weights.self_check_pass is True


def test_derive_from_reach_totals_yields_exact_p():
    """An aggregate funnel whose ratios reproduce the example P table exactly.

    purchases=231 -> reach click 9240, eng 4200, atc 1155, checkout 550,
    purchase 231 gives P = {.025, .055, .200, .420, 1.0} exactly.
    """
    reach_totals = {
        "click": 9240,
        "engagement": 4200,
        "add_to_cart": 1155,
        "initiate_checkout": 550,
        "purchase": 231,
    }
    weights = derive_weights(
        reach_totals, 231, EXAMPLE_CM3_ORDER, EXAMPLE_REPEAT_RATE, EXAMPLE_CM3_REPEAT
    )
    for state, expected in EXPECTED_WEIGHTS.items():
        assert round(weights.w[state], 2) == expected, state
    assert weights.self_check_pass is True


def test_self_check_fails_on_inconsistent_p():
    """A P table where P(purchase|purchase) != 1.0 must NOT telescope to CM3."""
    bad_p = dict(EXAMPLE_P, purchase=0.90)  # purchasers can't be 90% likely to purchase
    with pytest.raises(ValueError, match="self-check FAILED"):
        derive_weights_from_p(
            bad_p, EXAMPLE_CM3_ORDER, EXAMPLE_REPEAT_RATE, EXAMPLE_CM3_REPEAT
        )


def test_zero_reach_raises_named_error():
    reach_totals = {
        "click": 9240, "engagement": 0, "add_to_cart": 1155,
        "initiate_checkout": 550, "purchase": 231,
    }
    with pytest.raises(ValueError, match="engagement"):
        derive_weights(reach_totals, 231, EXAMPLE_CM3_ORDER, EXAMPLE_REPEAT_RATE, EXAMPLE_CM3_REPEAT)
