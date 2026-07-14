"""Per-segment wPPC scoring: wPPC, wPPC+, shrinkage (+ k), MAR, closing ratio.

Everything is derived from the data at runtime. Index and shrink WITHIN a single
platform only — never compare or combine wPPC across platforms.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .weights import FUNNEL_STATES, Weights

logger = logging.getLogger("wppc")

# Fallback stabilization constant (click-units) when method-of-moments for k is
# unstable. Pragmatic ecommerce default in the 150-400 range.
K_FALLBACK = 250.0

# Replacement-level segment = this clicks-weighted percentile of segment wPPC.
REPLACEMENT_PERCENTILE = 25.0


def score(df: pd.DataFrame, weights: Weights, *, incrementality: dict | None = None) -> pd.DataFrame:
    """Score every segment. ``df`` is the normalized frame from io.load_segments.

    ``incrementality`` is the Layer-5 seam (v1: inert) — see
    wppc/references/incrementality-seam.md. It accepts a loaded incrementality
    table (or None) purely as the future insertion point; v1 never reads it
    when computing scores, so passing a table changes nothing about the output.

    Returns a DataFrame sorted by MAR descending with columns:
        segment_id, clicks, conversions, wPPC, wPPC+, wPPC_shrunk,
        MAR, stabilized, closing_ratio
    """
    df = _clamp_monotonic(df.copy()).reset_index(drop=True)

    w = weights.w
    clicks = df["clicks"].astype(float)

    # Numerator = Σ reach(S)·w(S) + repeats·w(repeat). Telescoping incremental
    # weights against cumulative reach credits each session once at its deepest
    # state — no double counting.
    numerator = sum(df[s].astype(float) * w[s] for s in FUNNEL_STATES)
    numerator = numerator + df["repeats"].astype(float) * w["repeat"]

    # Layer-5 seam (v1: inert) — see wppc/references/incrementality-seam.md;
    # weight_causal = weight_attributed × IM_applied applies to the numerator
    # HERE, before shrinkage. v1 ships the seam only: `incrementality` is
    # accepted above but never applied to `numerator`.

    wppc = _safe_div(numerator, clicks)

    # Account-wide baseline within this platform = total numerator / total clicks.
    total_clicks = float(clicks.sum())
    baseline = float(numerator.sum()) / total_clicks if total_clicks > 0 else 0.0

    # baseline is a scalar; divide the Series directly (don't route through
    # _safe_div, which would treat the scalar as a length-1 Series and misalign).
    wppc_plus = (wppc / baseline * 100.0) if baseline > 0 else pd.Series(np.nan, index=wppc.index)

    # Empirical-Bayes shrinkage toward the parent (account baseline).
    k, k_source = estimate_k(df, weights, wppc, clicks, baseline, return_provenance=True)
    wppc_shrunk = (clicks * wppc + k * baseline) / (clicks + k)
    stabilized = clicks >= k

    # Replacement-level wPPC = clicks-weighted 25th percentile of segment wPPC.
    replacement = _weighted_percentile(wppc.to_numpy(), clicks.to_numpy(), REPLACEMENT_PERCENTILE)

    mar = (wppc_shrunk - replacement) * clicks

    # Closing ratio = realized CM3/click ÷ wPPC. <1 leaky closer; >1 regression.
    realized_cm3_per_click = _safe_div(
        df["purchase"].astype(float) * weights.cm3_order
        + df["repeats"].astype(float) * weights.cm3_repeat,
        clicks,
    )
    closing_ratio = _safe_div(realized_cm3_per_click, wppc)

    out = pd.DataFrame(
        {
            "segment_id": df["segment_id"].values,
            "clicks": clicks.astype(int).values,
            "conversions": df["purchase"].astype(int).values,
            "wPPC": wppc.values,
            "wPPC+": wppc_plus.values,
            "wPPC_shrunk": wppc_shrunk.values,
            "MAR": mar.values,
            "stabilized": np.where(stabilized.values, "Y", "N"),
            "closing_ratio": closing_ratio.values,
        }
    )

    out = out.sort_values("MAR", ascending=False, kind="stable").reset_index(drop=True)

    # Stash run-level scalars for the report layer (baseline/replacement/k).
    out.attrs["baseline"] = baseline
    out.attrs["replacement"] = replacement
    out.attrs["k"] = k
    # k-honesty provenance + segment/stabilization counts for downstream outputs.
    out.attrs["k_source"] = k_source
    out.attrs["n_segments"] = int(len(df))
    out.attrs["n_stabilized"] = int(stabilized.sum())
    # Additive provenance flag for the Layer-5 seam; does not affect any score.
    out.attrs["incrementality_provided"] = incrementality is not None
    return out


def estimate_k(df, weights: Weights, wppc, clicks, baseline, *, return_provenance: bool = False):
    """Random-effects method-of-moments stabilization constant.

        k = sigma2_within / tau2_between

    - tau2_between = clicks-weighted variance of segment wPPC about the baseline.
    - sigma2_within = pooled per-click profit variance. The within-segment
      per-click profit distribution is reconstructable exactly from the
      cumulative reach buckets: each click is credited PE(deepest reached state),
      with the segment's repeat credit folded uniformly into its purchaser
      bucket. We pool those click-level variances clicks-weighted.

    Falls back to K_FALLBACK (logged) when estimation is unstable.

    When ``return_provenance`` is True, returns ``(k, method)`` where ``method``
    is ``"estimated"`` on the success branch and ``"fallback"`` on every branch
    that returns K_FALLBACK. When False (default), returns the bare float.
    """

    def _ret(value, method):
        return (value, method) if return_provenance else value

    n_segments = len(df)
    total_clicks = float(clicks.sum())

    if n_segments < 2 or total_clicks <= 0:
        logger.info("k method-of-moments unstable (<2 segments); falling back to k=%.0f.", K_FALLBACK)
        return _ret(K_FALLBACK, "fallback")

    # Between-segment variance of segment wPPC, clicks-weighted, about baseline.
    tau2_between = float((clicks * (wppc - baseline) ** 2).sum() / total_clicks)

    # Pooled within-segment per-click profit variance.
    pe = weights.pe
    w_repeat = weights.w["repeat"]
    within_ss = 0.0  # Σ_i Σ_click (value - mean_i)^2
    for _, row in df.iterrows():
        n = float(row["clicks"])
        if n <= 0:
            continue
        # Exclusive count reaching each state as its deepest, with PE value.
        reach = [float(row[s]) for s in FUNNEL_STATES]  # cumulative, monotone
        counts = []
        values = []
        for i, s in enumerate(FUNNEL_STATES):
            deeper = reach[i + 1] if i + 1 < len(FUNNEL_STATES) else 0.0
            cnt = reach[i] - deeper
            if cnt < 0:
                cnt = 0.0
            counts.append(cnt)
            values.append(pe[s])
        # Fold repeat credit uniformly into the purchaser bucket.
        purchasers = reach[-1]
        if purchasers > 0:
            values[-1] = pe[FUNNEL_STATES[-1]] + (float(row["repeats"]) * w_repeat) / purchasers
        # Clicks that never reached the click state shouldn't happen (click is
        # the denominator); any residual clicks beyond summed reach get value 0.
        residual = n - sum(counts)
        if residual > 1e-9:
            counts.append(residual)
            values.append(0.0)
        mean_i = sum(c * v for c, v in zip(counts, values)) / n
        within_ss += sum(c * (v - mean_i) ** 2 for c, v in zip(counts, values))

    sigma2_within = within_ss / total_clicks

    if not np.isfinite(tau2_between) or tau2_between <= 0 or not np.isfinite(sigma2_within):
        logger.info(
            "k method-of-moments unstable (tau2_between=%.6g, sigma2_within=%.6g); "
            "falling back to k=%.0f.",
            tau2_between, sigma2_within, K_FALLBACK,
        )
        return _ret(K_FALLBACK, "fallback")

    k = sigma2_within / tau2_between
    if not np.isfinite(k) or k <= 0:
        logger.info("k computed as %.6g (non-positive/non-finite); falling back to k=%.0f.", k, K_FALLBACK)
        return _ret(K_FALLBACK, "fallback")

    logger.info(
        "k estimated by method-of-moments = %.1f (sigma2_within=%.4f, tau2_between=%.4f).",
        k, sigma2_within, tau2_between,
    )
    return _ret(float(k), "estimated")


def _clamp_monotonic(df: pd.DataFrame) -> pd.DataFrame:
    """Reach counts must be non-increasing down the funnel; warn and clamp."""
    for i in range(1, len(FUNNEL_STATES)):
        prev, cur = FUNNEL_STATES[i - 1], FUNNEL_STATES[i]
        violating = df[cur] > df[prev]
        if violating.any():
            for idx in df.index[violating]:
                logger.warning(
                    "Monotonicity violation: segment %r stage '%s'=%g exceeds upstream "
                    "'%s'=%g; clamping '%s' down to %g.",
                    df.at[idx, "segment_id"], cur, df.at[idx, cur],
                    prev, df.at[idx, prev], cur, df.at[idx, prev],
                )
            df.loc[violating, cur] = df.loc[violating, prev]
    return df


def _safe_div(num, den):
    """Element-wise divide, yielding 0 where the denominator is 0."""
    num = pd.Series(num).astype(float).reset_index(drop=True)
    den = pd.Series(den).astype(float).reset_index(drop=True)
    return pd.Series(np.where(den != 0, num / den.replace(0, np.nan), 0.0)).fillna(0.0)


def _weighted_percentile(values: np.ndarray, weights: np.ndarray, pct: float) -> float:
    """Clicks-weighted percentile of ``values`` (pct in 0..100)."""
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    mask = weights > 0
    if not mask.any():
        return 0.0
    values, weights = values[mask], weights[mask]
    order = np.argsort(values)
    values, weights = values[order], weights[order]
    cum = np.cumsum(weights) - 0.5 * weights
    cum /= weights.sum()
    return float(np.interp(pct / 100.0, cum, values))
