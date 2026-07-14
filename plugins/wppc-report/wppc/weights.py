"""Derive the linear weights — the run-expectancy step.

The weight of a funnel event is the *profit expectancy it confers*, exactly as
wOBA weights come from run expectancy by base-out state.

    P(purchase | S) = purchases / sessions that reached state S   (account-wide)
    PE(S)           = P(purchase | S) * CM3_order
    w(S)            = PE(S) - PE(prior state)        (w(click) = PE(click) - 0)
    w(repeat)       = repeat_rate * CM3_repeat

Self-check (the elegant property): a click that travels all the way to purchase
accrues w(click)+...+w(purchase) == CM3_order exactly — the incremental weights
telescope to the terminal value. If they don't, the P(purchase|S) table is
inconsistent and we refuse to score on it.

Nothing here is hardcoded: every number is derived from the supplied data /
currency parameters at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass

# Funnel states in order. The denominator (the scarce opportunity) is the click.
FUNNEL_STATES = ["click", "engagement", "add_to_cart", "initiate_checkout", "purchase"]

# Tolerance for the telescoping self-check, in account currency units ($0.01).
SELF_CHECK_TOL = 0.01


@dataclass
class Weights:
    """Derived linear-weights table for one platform."""

    p: dict          # state -> P(purchase | state)
    pe: dict         # state -> profit expectancy PE(S) (telescoped value at S)
    w: dict          # state -> incremental weight w(S); also key "repeat"
    cm3_order: float
    repeat_rate: float
    cm3_repeat: float
    telescope_sum: float   # sum of w(click..purchase)
    self_check_pass: bool


def derive_weights_from_p(
    p: dict,
    cm3_order: float,
    repeat_rate: float,
    cm3_repeat: float,
    tol: float = SELF_CHECK_TOL,
) -> Weights:
    """Build the weight table directly from a P(purchase|S) table.

    Raises ValueError naming the inconsistent table if the weights fail to
    telescope to CM3_order within ``tol``.
    """
    missing = [s for s in FUNNEL_STATES if s not in p]
    if missing:
        raise ValueError(
            f"P(purchase|S) table is missing funnel state(s) {missing}. "
            f"Required states (in order): {FUNNEL_STATES}."
        )

    pe = {s: p[s] * cm3_order for s in FUNNEL_STATES}

    w: dict = {}
    prior = 0.0
    for s in FUNNEL_STATES:
        w[s] = pe[s] - prior
        prior = pe[s]
    w["repeat"] = repeat_rate * cm3_repeat

    telescope_sum = sum(w[s] for s in FUNNEL_STATES)
    self_check_pass = abs(telescope_sum - cm3_order) <= tol

    if not self_check_pass:
        p_str = ", ".join(f"{s}={p[s]:.6g}" for s in FUNNEL_STATES)
        raise ValueError(
            "Weight self-check FAILED: telescoped weight sum "
            f"${telescope_sum:.4f} != CM3_order ${cm3_order:.4f} "
            f"(diff ${telescope_sum - cm3_order:+.4f}, tol ${tol}). "
            "The P(purchase|S) table is inconsistent — P(purchase|purchase) must "
            f"be 1.0 and probabilities non-decreasing down the funnel. Table: [{p_str}]."
        )

    return Weights(
        p=p,
        pe=pe,
        w=w,
        cm3_order=cm3_order,
        repeat_rate=repeat_rate,
        cm3_repeat=cm3_repeat,
        telescope_sum=telescope_sum,
        self_check_pass=self_check_pass,
    )


def derive_weights(
    reach_totals: dict,
    purchases_total: float,
    cm3_order: float,
    repeat_rate: float,
    cm3_repeat: float,
    tol: float = SELF_CHECK_TOL,
) -> Weights:
    """Derive weights from account-wide cumulative reach totals.

    ``reach_totals`` maps each funnel state to the total number of sessions that
    reached state S (cumulative) across the whole platform. ``purchases_total``
    is the account-wide purchase count (== reach_totals['purchase']).
    """
    p = {}
    for s in FUNNEL_STATES:
        reach = reach_totals.get(s)
        if reach is None:
            raise ValueError(f"reach_totals is missing funnel state '{s}'.")
        if reach <= 0:
            raise ValueError(
                f"Cannot derive P(purchase|{s}): total reach for state '{s}' is "
                f"{reach} (must be > 0). Check the mapped column for this state."
            )
        p[s] = purchases_total / reach

    return derive_weights_from_p(p, cm3_order, repeat_rate, cm3_repeat, tol=tol)
