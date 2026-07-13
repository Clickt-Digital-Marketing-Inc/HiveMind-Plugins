#!/usr/bin/env python3
# Copyright (c) 2026 Clickt Digital Marketing Inc. All rights reserved.
"""CVR Signals for the Shopify CRO audit — rate-significance statistics
(Wilson intervals, two-proportion z, significance gates, Beta-binomial
credible intervals, empirical-Bayes shrinkage, stabilization, weighted
averages) in pure stdlib.

The statistical functions mirror the MediaMetrics Meta analytics module
(`plugins/mediametrics-meta/skills/mediametrics-meta/analytics.py`) EXACTLY —
same clamps, same degenerate returns — reimplemented with `math` +
`statistics` only (no numpy) so this plugin stays standalone.

`compute_cvr_signals` consumes FRACTION-rate row dicts
(`{name, sessions, cvr?, conversions?}`; rates are fractions, e.g. 0.0198 =
1.98% — the Shopify ShopifyQL PERCENT dtype ships fractions verbatim and
machine.py converts fraction→percent exactly once, at the payload boundary).
Conversion counts are preferred when present; otherwise they are DERIVED as
`floor(sessions × CVR + 0.5)` (half-up) and the row is flagged `derived`
(honesty note emitted). Two-proportion z-tests obey the SINGLE-SOURCE
COMPLEMENT RULE: the complement is the sum of the sibling rows of the SAME
input list — never assembled across sources.

Full-universe math (significance-gate counts, the empirical-Bayes prior
strength k = median sessions/page, stabilization dispersion) happens BEFORE
the bounded top-`top_n` embed cut. Deterministic: no wall clock, sessions-desc
/ name-asc ordering everywhere, fixed note order.

Stdlib only.
"""
from __future__ import annotations

import math
from statistics import median

Z_SIG = 1.96              # |z| at/above this = significant (95% two-sided)
TOP_N = 25                # bounded-embed cap for the pages table
CONFIDENCE = 0.95         # confidence level for the min-sessions gate
STABILIZATION_MIN_PAGES = 8  # ungated pages needed before the stabilization note


def _f(x) -> float:
    """Coerce a scalar to float; None / non-numeric / NaN / inf -> 0.0.
    Mirror of mediametrics-meta analytics.py `_f` — exact. Never raises."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(v) or math.isinf(v):
        return 0.0
    return v


def _seq(values) -> list:
    """Coerce a sequence to a list of floats; NaN/inf/non-numeric -> 0.0;
    None -> []. Stdlib stand-in for analytics.py `_arr` (numpy) with the same
    element semantics (nan_to_num -> 0.0). Never raises."""
    if values is None:
        return []
    return [_f(v) for v in values]


# ---------------------------------------------------------------------------
# Rate-significance functions — EXACT stdlib mirrors of
# plugins/mediametrics-meta/skills/mediametrics-meta/analytics.py
# ---------------------------------------------------------------------------
def wilson_ci(succ: float, n: float, z: float = 1.96) -> tuple:
    """Wilson score confidence interval for a binomial proportion.
    Mirror of mediametrics-meta analytics.py `wilson_ci` — exact.

    Returns (low, high), each clamped to [0, 1]. Far better small-sample
    coverage than the normal (Wald) interval. n <= 0 -> (0.0, 0.0);
    succ clamped to [0, n].
    """
    n = float(n)
    if n <= 0:
        return (0.0, 0.0)
    succ = max(0.0, min(float(succ), n))
    p = succ / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1.0 - p) / n + z2 / (4.0 * n * n))
    low = max(0.0, center - half)
    high = min(1.0, center + half)
    return (float(low), float(high))


def wilson_lower_bound(succ: float, n: float, z: float = 1.96) -> float:
    """Wilson score LOWER bound — the fair way to rank rates across unequal n
    (a 1/1 rate ranks below a 95/100 rate). n <= 0 -> 0.0.
    Mirror of mediametrics-meta analytics.py `wilson_lower_bound` — exact."""
    return wilson_ci(succ, n, z)[0]


def two_proportion_z(x1: float, n1: float, x2: float, n2: float) -> float:
    """Pooled two-proportion z-statistic for p1 vs p2.
    Mirror of mediametrics-meta analytics.py `two_proportion_z` — exact.

    z = (p1 - p2) / sqrt( p*(1-p)*(1/n1 + 1/n2) ), p = pooled rate. Positive z
    => group 1 has the higher rate. Degenerate (n<=0 or se=0) -> 0.0.
    """
    n1, n2 = float(n1), float(n2)
    if n1 <= 0 or n2 <= 0:
        return 0.0
    p1, p2 = float(x1) / n1, float(x2) / n2
    p = (float(x1) + float(x2)) / (n1 + n2)
    se = math.sqrt(p * (1.0 - p) * (1.0 / n1 + 1.0 / n2))
    if se == 0:
        return 0.0
    return float((p1 - p2) / se)


def min_clicks_for_significance(cvr0: float, confidence: float = 0.95) -> int:
    """Minimum zero-conversion trials to call an entity a confident loser.
    Mirror of mediametrics-meta analytics.py `min_clicks_for_significance` —
    exact (there the trials are clicks; here they are sessions).

    n_min = ceil( ln(1 - confidence) / ln(1 - cvr0) ): the session count at
    which an entity with 0 conversions had >=`confidence` probability of
    converting at the site rate. cvr0 <= 0 -> 0 (undefined); cvr0 >= 1 -> 1.
    """
    cvr0 = float(cvr0)
    if cvr0 <= 0:
        return 0
    if cvr0 >= 1:
        return 1
    return int(math.ceil(math.log(1.0 - confidence) / math.log(1.0 - cvr0)))


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta function (Lentz's method).
    Mirror of mediametrics-meta analytics.py `_betacf` — exact."""
    MAXIT, EPS, FPMIN = 200, 3.0e-15, 1.0e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < EPS:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta function I_x(a, b) in [0, 1].
    Mirror of mediametrics-meta analytics.py `betainc` — exact.

    Pure-Python (Numerical Recipes `betai`); deterministic. Used to build the
    Beta posterior CDF for credible intervals without SciPy.
    """
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    bt = math.exp(lbeta + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def beta_ppf(q: float, a: float, b: float) -> float:
    """Inverse Beta CDF (quantile) via monotone bisection on betainc.
    Mirror of mediametrics-meta analytics.py `beta_ppf` — exact."""
    q = min(1.0, max(0.0, float(q)))
    if q <= 0.0:
        return 0.0
    if q >= 1.0:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if betainc(a, b, mid) < q:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def beta_binomial_credible(succ: float, n: float, alpha_prior: float = 1.0,
                           beta_prior: float = 1.0, mass: float = 0.95
                           ) -> tuple:
    """Bayesian credible interval for a binomial rate via a Beta posterior.
    Mirror of mediametrics-meta analytics.py `beta_binomial_credible` — exact.

    Posterior = Beta(a0+succ, b0+n-succ). Returns (low, high, mean) for the
    central `mass` interval. Uniform prior (1,1) by default. n <= 0 returns
    the prior interval. Deterministic (bisection-inverted incomplete beta).
    """
    succ = max(0.0, float(succ))
    n = max(0.0, float(n))
    a = alpha_prior + succ
    b = beta_prior + max(0.0, n - succ)
    tail = (1.0 - mass) / 2.0
    low = beta_ppf(tail, a, b)
    high = beta_ppf(1.0 - tail, a, b)
    mean = a / (a + b) if (a + b) > 0 else 0.0
    return (float(low), float(high), float(mean))


def empirical_bayes_shrink(succ: float, n: float, prior_rate: float,
                           k: float) -> float:
    """Empirical-Bayes shrinkage of a rate toward a prior.
    Mirror of mediametrics-meta analytics.py `empirical_bayes_shrink` — exact.

    shrunk = (succ + prior_rate*k)/(n + k) — equivalently weight w = n/(n+k)
    on the observed rate succ/n and (1-w) on prior_rate. `k` is the prior
    strength (pseudo-trials, clamped >= 0). n + k <= 0 -> prior_rate. Thin
    samples are pulled toward the parent mean.
    """
    succ, n, pr, k = _f(succ), _f(n), _f(prior_rate), max(0.0, _f(k))
    denom = n + k
    if denom <= 0:
        return float(pr)
    return float((succ + pr * k) / denom)


def stabilization_point(p: float, sd: float, target_r: float = 0.5) -> float:
    """Sample size at which a rate stabilizes to reliability `target_r`.
    Mirror of mediametrics-meta analytics.py `stabilization_point` — exact.

    n* = (r/(1-r))*(p(1-p)/sd^2) — the trials at which between-entity signal
    equals within-entity binomial noise (split-half reliability r). `p` = the
    rate (clamped to [0, 1]), `sd` = its between-entity dispersion. sd <= 0 or
    target_r not in (0,1) -> 0.0.
    """
    p = min(1.0, max(0.0, _f(p)))
    sd = _f(sd)
    r = _f(target_r)
    if sd <= 0 or r <= 0 or r >= 1:
        return 0.0
    return float((r / (1.0 - r)) * (p * (1.0 - p) / (sd * sd)))


def vwap(values, weights) -> float:
    """Weight-weighted average sum(v_i*w_i)/sum(w_i) (e.g. session-weighted CVR).
    Mirror of mediametrics-meta analytics.py `vwap` — exact semantics, numpy
    rewritten as list comprehensions (element coercion matches `_arr`:
    NaN/inf -> 0.0).

    The "what's actually true" average — weighting each entity by its traffic
    so big entities count proportionally. Sequences are truncated to the
    shorter length. Empty, or sum(weights) <= 0, -> 0.0.
    """
    va, wa = _seq(values), _seq(weights)
    n = min(len(va), len(wa))
    if n == 0:
        return 0.0
    wsum = float(sum(wa[:n]))
    if wsum <= 0:
        return 0.0
    return float(sum(v * w for v, w in zip(va[:n], wa[:n])) / wsum)


# ---------------------------------------------------------------------------
# Derived-counts rule + row resolution
# ---------------------------------------------------------------------------
def derived_conversions(sessions: float, cvr_fraction: float) -> int:
    """Conversion count derived from a shipped rate:
    floor(sessions * cvr + 0.5) — HALF-UP, never banker's rounding.

    Shopify/GA4 UI exports frequently ship rates without counts; z-tests and
    Wilson bounds need counts, so we reconstruct them and flag the rows
    `derived` (see the honesty note in `compute_cvr_signals`).
    """
    return int(math.floor(_f(sessions) * _f(cvr_fraction) + 0.5))


def _resolve(row) -> dict:
    """Normalize one input row {name, sessions, cvr?, conversions?} into
    {name, sessions:int, conversions:int, derived:bool, cvr_raw:float}.

    Conversion counts are PREFERRED when present; else derived from the
    shipped fraction (row flagged `derived`, and `cvr_raw` keeps the shipped
    fraction — the raw observation — rather than the reconstructed ratio).
    Neither present -> a zero-conversion row (derived False). Funnel aliases
    tolerated: `conversion_rate` for cvr; `purchases` /
    `sessions_that_completed_checkout` for conversions (fixed precedence).
    """
    name = str(row.get("name", ""))
    sessions = int(math.floor(_f(row.get("sessions")) + 0.5))
    conv_in = None
    for key in ("conversions", "purchases", "sessions_that_completed_checkout"):
        if row.get(key) is not None:
            conv_in = row[key]
            break
    cvr_in = None
    for key in ("cvr", "conversion_rate"):
        if row.get(key) is not None:
            cvr_in = row[key]
            break
    if conv_in is not None:
        conversions = int(math.floor(_f(conv_in) + 0.5))
        derived = False
        cvr_raw = conversions / sessions if sessions > 0 else 0.0
    elif cvr_in is not None:
        cvr_raw = _f(cvr_in)
        conversions = derived_conversions(sessions, cvr_raw)
        derived = True
    else:
        conversions, cvr_raw, derived = 0, 0.0, False
    return {"name": name, "sessions": sessions, "conversions": conversions,
            "derived": derived, "cvr_raw": float(cvr_raw)}


def _resolve_rows(rows) -> list:
    """Resolve + deterministically order a row list: sessions desc, name asc."""
    resolved = [_resolve(r) for r in (rows or [])]
    resolved.sort(key=lambda b: (-b["sessions"], b["name"]))
    return resolved


# ---------------------------------------------------------------------------
# Audit-block assembly
# ---------------------------------------------------------------------------
def _segment_blocks(resolved) -> list:
    """Segment embeds with sibling-complement z-tests (single-source rule:
    the complement for each row is the sum of the OTHER rows of the same
    list). z is rounded to 2dp and the significance pill reads the ROUNDED z
    (so the pill always agrees with the displayed value); z is null when the
    row or its complement has no sessions."""
    total_s = sum(b["sessions"] for b in resolved)
    total_c = sum(b["conversions"] for b in resolved)
    out = []
    for b in resolved:
        comp_s = total_s - b["sessions"]
        comp_c = total_c - b["conversions"]
        if b["sessions"] > 0 and comp_s > 0:
            z = round(two_proportion_z(b["conversions"], b["sessions"],
                                       comp_c, comp_s), 2)
            significant = abs(z) >= Z_SIG
        else:
            z, significant = None, False
        out.append({"name": b["name"], "sessions": b["sessions"],
                    "conversions": b["conversions"], "derived": b["derived"],
                    "cvr": round(b["cvr_raw"], 6),
                    "z": z, "significant": significant})
    return out


def _headline_device_z(device_resolved):
    """Mobile-vs-desktop headline z (prefix-matched names, first match each —
    device benchmarks exist only for Mobile/Desktop). Positive z = mobile
    converts higher. None when either side is missing or has no sessions."""
    mob = next((b for b in device_resolved
                if b["name"].lower().startswith("mobile")), None)
    desk = next((b for b in device_resolved
                 if b["name"].lower().startswith("desktop")), None)
    if mob is None or desk is None or mob["sessions"] <= 0 or desk["sessions"] <= 0:
        return None
    z = round(two_proportion_z(mob["conversions"], mob["sessions"],
                               desk["conversions"], desk["sessions"]), 2)
    return {"z": z, "significant": abs(z) >= Z_SIG}


def _pstdev(values) -> float:
    """Population standard deviation (ddof=0) — numpy `.std(ddof=0)` parity.
    Empty -> 0.0."""
    vals = _seq(values)
    if not vals:
        return 0.0
    mu = sum(vals) / len(vals)
    return math.sqrt(sum((v - mu) ** 2 for v in vals) / len(vals))


def compute_cvr_signals(funnel=None, device_rows=None, channel_rows=None,
                        nvr=None, page_rows=None, *, top_n: int = TOP_N,
                        window=None):
    """Assemble the CVR Signals model block. Returns None when no input at
    all is usable (every argument None/empty).

    Inputs are FRACTION-rate row dicts {name, sessions, cvr?, conversions?}
    (see `_resolve` for the funnel key aliases). `funnel` is a single dict of
    site totals; when absent, site totals are summed from the first non-empty
    list in the fixed fallback order device -> channels -> new-vs-returning ->
    pages (noted). `window` is an optional pass-through label (plan §2's
    block key; None when the caller doesn't know it).

    Block (fractions internally; fractions rounded 6dp, z 2dp):
      window · site{sessions, conversions, cvr, ci:[lo,hi]} ·
      min_sessions (n* = min_clicks_for_significance(site cvr, CONFIDENCE)) ·
      prior{rate = site cvr, k = median sessions/page over the FULL page
      universe, basis} · segments{device[], channels[], new_vs_returning[],
      headline_device_z} · pages (top-`top_n` by sessions desc/name asc:
      {page, sessions, conversions, derived, cvr_raw, cvr_shrunk, wilson_lb,
      gated}) · pages_universe{n, sessions, gated_n} · notes[].

    Full-universe math BEFORE the top-`top_n` cut: `pages_universe.gated_n`,
    the prior k, and the stabilization dispersion cover ALL page rows. Notes
    are emitted in a fixed order: (1) funnel-fallback, (2) derived-counts
    honesty, (3) significance gate, (4) stabilization, then the
    missing-input notes for device / channels / new-vs-returning / pages.
    """
    device = _resolve_rows(device_rows)
    channels = _resolve_rows(channel_rows)
    nvr_res = _resolve_rows(nvr)
    pages_res = _resolve_rows(page_rows)

    # Site totals — funnel preferred; fixed same-source fallback order.
    funnel_row = None
    fallback_noun = None
    if funnel is not None:
        funnel_row = _resolve(dict(funnel))
        site_res = funnel_row
        basis = "site CVR (funnel)"
    else:
        site_res = None
        for rows, noun in ((device, "device rows"),
                           (channels, "channel rows"),
                           (nvr_res, "new-vs-returning rows"),
                           (pages_res, "page rows")):
            if rows:
                site_res = {
                    "sessions": sum(b["sessions"] for b in rows),
                    "conversions": sum(b["conversions"] for b in rows),
                }
                s = site_res["sessions"]
                site_res["cvr_raw"] = (site_res["conversions"] / s
                                       if s > 0 else 0.0)
                fallback_noun = noun
                break
        basis = f"site CVR (summed {fallback_noun})" if site_res else ""
    if site_res is None:
        return None

    site_cvr = site_res["cvr_raw"]          # unrounded — feeds gate/prior
    ci_lo, ci_hi = wilson_ci(site_res["conversions"], site_res["sessions"],
                             Z_SIG)
    min_sessions = min_clicks_for_significance(site_cvr, CONFIDENCE)

    # Full-universe page math BEFORE the embed cut.
    prior_k = float(median([b["sessions"] for b in pages_res])) \
        if pages_res else 0.0
    gated_n = 0
    ungated_rates = []
    page_blocks = []
    for b in pages_res:
        gated = b["sessions"] < min_sessions
        if gated:
            gated_n += 1
        else:
            ungated_rates.append(b["cvr_raw"])
        page_blocks.append({
            "page": b["name"],
            "sessions": b["sessions"],
            "conversions": b["conversions"],
            "derived": b["derived"],
            "cvr_raw": round(b["cvr_raw"], 6),
            "cvr_shrunk": round(empirical_bayes_shrink(
                b["conversions"], b["sessions"], site_cvr, prior_k), 6),
            "wilson_lb": round(wilson_lower_bound(
                b["conversions"], b["sessions"], Z_SIG), 6),
            "gated": gated,
        })

    # Derived-counts honesty tally — every resolved input row, full universe.
    all_rows = device + channels + nvr_res + pages_res \
        + ([funnel_row] if funnel_row is not None else [])
    derived_n = sum(1 for b in all_rows if b["derived"])

    # Notes — fixed order for determinism.
    notes = []
    if funnel is None and fallback_noun:
        notes.append(f"No funnel totals provided — site totals summed from "
                     f"{fallback_noun}.")
    if derived_n:
        notes.append(f"{derived_n} of {len(all_rows)} input rows ship a rate "
                     "but no conversion count — counts derived as "
                     "floor(sessions × CVR + 0.5) and flagged 'derived' "
                     "(±0.5 conversions of rounding per row).")
    if pages_res and gated_n:
        notes.append(f"{gated_n} of {len(pages_res)} landing pages sit below "
                     f"the n*={min_sessions}-session significance gate "
                     f"({int(round(CONFIDENCE * 100))}% confidence at site "
                     "CVR) — flagged 'gated'.")
    if len(ungated_rates) >= STABILIZATION_MIN_PAGES:
        sd = _pstdev(ungated_rates)
        n_star = stabilization_point(site_cvr, sd)
        if n_star > 0:
            notes.append(f"Page CVR stabilizes to r=0.5 reliability around "
                         f"n≈{int(math.floor(n_star + 0.5)):,} sessions/page "
                         f"(dispersion of {len(ungated_rates)} ungated "
                         "pages).")
    if not device:
        notes.append("No device rows provided — device CVR split not "
                     "computed.")
    if not channels:
        notes.append("No channel rows provided — channel CVR split not "
                     "computed.")
    if not nvr_res:
        notes.append("No new-vs-returning rows provided (GA4-only segment) — "
                     "not computed.")
    if not pages_res:
        notes.append("No landing-page rows provided — page-level CVR signals "
                     "not computed.")

    return {
        "window": window,
        "site": {
            "sessions": site_res["sessions"],
            "conversions": site_res["conversions"],
            "cvr": round(site_cvr, 6),
            "ci": [round(ci_lo, 6), round(ci_hi, 6)],
        },
        "min_sessions": int(min_sessions),
        "prior": {"rate": round(site_cvr, 6), "k": round(prior_k, 1),
                  "basis": basis},
        "segments": {
            "device": _segment_blocks(device),
            "channels": _segment_blocks(channels),
            "new_vs_returning": _segment_blocks(nvr_res),
            "headline_device_z": _headline_device_z(device),
        },
        "pages": page_blocks[:top_n],
        "pages_universe": {
            "n": len(pages_res),
            "sessions": sum(b["sessions"] for b in pages_res),
            "gated_n": gated_n,
        },
        "notes": notes,
    }
