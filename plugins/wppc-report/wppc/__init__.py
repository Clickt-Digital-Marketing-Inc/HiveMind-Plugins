"""wPPC — Weighted Profit-Per-Click reporting for Google & Meta Ads.

A sabermetric linear-weights framework: every funnel event is credited at its
expected contribution-margin (CM3) value, indexed to the account baseline
(wPPC+), shrunk for sample size (empirical Bayes), and scored above replacement
(MAR). Weights, k, baseline, and replacement are ALWAYS derived from the data at
runtime — never hardcoded.
"""

from .weights import FUNNEL_STATES, Weights, derive_weights, derive_weights_from_p
from .score import score, K_FALLBACK

__all__ = [
    "FUNNEL_STATES",
    "Weights",
    "derive_weights",
    "derive_weights_from_p",
    "score",
    "K_FALLBACK",
]

__version__ = "1.0.0"
