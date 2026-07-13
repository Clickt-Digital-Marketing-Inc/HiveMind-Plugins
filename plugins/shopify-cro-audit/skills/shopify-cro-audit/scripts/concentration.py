#!/usr/bin/env python3
# Copyright (c) 2026 Clickt Digital Marketing Inc. All rights reserved.
"""Concentration analysis for the Shopify CRO audit — HHI / Effective-N / Gini /
Lorenz / Pareto-ABC on the store's weight-vs-outcome split across products,
landing pages, and traffic channels.

Rows arrive ALREADY NORMALIZED by the shopify_rows / manual_csv adapters (the
transcription firewall lives there: the model handles file paths, never
numbers). This module consumes canonical flat rows — fraction-unit CVRs, plain
floats for money — so there is no raw-envelope parsing here. Dimensions map
onto the generic weight/outcome pair (JSON keys stay `spend`/`conv` so the
renderer port needs label changes only):

  products       spend = revenue,  conv = orders (absent -> no_conv_signal)
  landing_pages  spend = sessions, conv = conversions (precomputed on the row
                 when present, else derived from sessions x CVR, half-up)
  channels       spend = sessions, conv = revenue when exported, else
                 conversions (precomputed or derived), else none

Metric semantics mirror the MediaMetrics analytics module in pure stdlib
(no numpy). One deliberate deviation: `pareto_abc` bands by cumulative share
BEFORE adding each entity (crossing-inclusive), so an entity holding e.g.
83% of conversions is classed "A" — under the mirror-exact rule it would land
in "B" and band A would be empty on exactly the concentrated accounts this
report targets.

Stdlib only.
"""
from __future__ import annotations

import math

# HHI bands: the DOJ/FTC merger-guideline cutoffs, used descriptively.
HHI_MODERATE = 1500.0
HHI_HIGH = 2500.0
SMALL_N = 8  # below this, band language is unreliable — lean on Effective-N

# CRO verdict wording — {w} = the weight noun ("spend" side), {o} = the
# outcome noun ("conv" side), filled per dimension via NOUNS. The meta-ads
# `review_bidding` key is RENAMED `review_mix` (budget-causal wording replaced
# with merchandising/mix wording).
VERDICTS = {
    "no_conv_signal": ("No {o} signal in this window — verdict unavailable; "
                       "check analytics coverage or extend the window."),
    "consolidate": ("Diffuse {w}, concentrated {o} — a small core accounts for "
                    "most of the {o}, with {w} spread thin across the long "
                    "tail. Double down on the proven core and fix or cut the "
                    "tail."),
    "fragility": ("Concentration fragility — {w} and {o} both depend on a "
                  "handful of entities. One going cold takes the store with "
                  "it; plan deliberate diversification."),
    "diversified": ("Diversified — {w} and {o} are both spread. Healthy, "
                    "provided the spread reflects strategy rather than "
                    "neglect."),
    "review_mix": ("Concentrated {w}, diffuse {o} — a handful of entities soak "
                   "up the {w} without dominating the {o}. Review the mix and "
                   "whether those leaders earn their place."),
    "insufficient": "Insufficient data in this window to judge concentration.",
}

# Weight/outcome nouns per dimension. Channels' outcome noun follows the
# conversion basis actually used (revenue when exported, else conversions) so
# the verdict never names a metric that isn't in the table.
NOUNS = {
    "products": ("revenue", "orders"),
    "landing_pages": ("sessions", "conversions"),
    "channels": ("sessions", "revenue"),
    "channels_conversions": ("sessions", "conversions"),
}


def num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


# ── concentration metrics (mirror mediametrics analytics.py, numpy-free) ───

def _nonneg(values) -> list[float]:
    """Coerce to floats; None/non-numeric/NaN/inf -> 0.0; clip negatives to 0."""
    out = []
    for v in (values or []):
        try:
            f = float(v)
        except (TypeError, ValueError):
            f = 0.0
        if math.isnan(f) or math.isinf(f) or f < 0:
            f = 0.0
        out.append(f)
    return out


def hhi(values) -> float:
    """Herfindahl-Hirschman Index on the 0-10,000 scale.

    HHI = sum(s_i^2) * 10,000 where s_i = v_i / sum(v). Empty/zero-sum -> 0.0."""
    a = _nonneg(values)
    total = sum(a)
    if total <= 0:
        return 0.0
    return sum((v / total) ** 2 for v in a) * 10000.0


def effective_n(values) -> float:
    """Effective number of entities = 1 / sum(s_i^2) (inverse Simpson).

    Equal split of k entities -> exactly k. Empty/zero-sum -> 0.0."""
    a = _nonneg(values)
    total = sum(a)
    if total <= 0:
        return 0.0
    denom = sum((v / total) ** 2 for v in a)
    return 1.0 / denom if denom > 0 else 0.0


def gini(values) -> float:
    """Gini coefficient (0 = equal, ->1 = maximally unequal).

    Sorted-rank formula G = (2*sum(i*x_i))/(n*sum(x)) - (n+1)/n, i=1..n over
    values sorted ascending; clamped into [0, 1]. Empty/zero-sum -> 0.0."""
    a = _nonneg(values)
    n = len(a)
    total = sum(a)
    if n == 0 or total <= 0:
        return 0.0
    xs = sorted(a)
    g = (2.0 * sum((i + 1) * x for i, x in enumerate(xs))) / (n * total) - (n + 1.0) / n
    return min(1.0, max(0.0, g))


def lorenz_points(values) -> list[list[float]]:
    """Lorenz curve: n+1 cumulative (population frac, value frac) points from
    [0,0], values sorted ascending. Empty/zero-sum -> [[0.0, 0.0]]."""
    a = _nonneg(values)
    n = len(a)
    total = sum(a)
    if n == 0 or total <= 0:
        return [[0.0, 0.0]]
    xs = sorted(a)
    pts, cum = [[0.0, 0.0]], 0.0
    for i, x in enumerate(xs):
        cum += x
        pts.append([round((i + 1) / n, 4), round(cum / total, 4)])
    return pts


def downsample_lorenz(pts: list, max_pts: int = 101) -> list:
    """Stride-sample a Lorenz polyline to <= max_pts, always keeping both ends."""
    if len(pts) <= max_pts:
        return pts
    step = (len(pts) - 1) / (max_pts - 1)
    keep = [pts[round(i * step)] for i in range(max_pts - 1)]
    keep.append(pts[-1])
    return keep


def pareto_abc(values) -> list[str]:
    """ABC (Pareto 80/20) banding, returned in ORIGINAL input order.

    DELIBERATE DEVIATION from the MediaMetrics `pareto_abc`: entities are banded
    by cumulative share BEFORE adding them (crossing-inclusive) — cum_before
    < 0.80 -> A, < 0.95 -> B, else C — so the entity that crosses a boundary
    belongs to the band it crosses out of. Mirror-exact banding would leave
    band A empty whenever one entity alone exceeds 80%. Empty -> [];
    zero-sum -> all "C"."""
    a = _nonneg(values)
    n = len(a)
    if n == 0:
        return []
    total = sum(a)
    if total <= 0:
        return ["C"] * n
    order = sorted(range(n), key=lambda i: (-a[i], i))
    bands = ["C"] * n
    cum = 0.0
    for i in order:
        before = cum / total
        if before < 0.80 - 1e-12:
            bands[i] = "A"
        elif before < 0.95 - 1e-12:
            bands[i] = "B"
        else:
            bands[i] = "C"
        cum += a[i]
    return bands


def hhi_band(h: float) -> str:
    if h < HHI_MODERATE:
        return "unconcentrated"
    if h <= HHI_HIGH:
        return "moderate"
    return "high"


def verdict(spend_hhi, conv_hhi, nouns=("weight", "outcomes")) -> tuple[str, str]:
    """Classify the weight-vs-outcomes concentration gap. conv_hhi None means
    no outcome signal; spend_hhi None means no weight signal. `nouns` fills the
    {w}/{o} template slots of the dimension's verdict wording."""
    w, o = nouns
    if spend_hhi is None:
        return "insufficient", VERDICTS["insufficient"]
    if conv_hhi is None:
        return "no_conv_signal", VERDICTS["no_conv_signal"].format(w=w, o=o)
    s_high = spend_hhi > HHI_HIGH
    c_high = conv_hhi > HHI_HIGH
    if s_high and c_high:
        key = "fragility"
    elif c_high:
        key = "consolidate"
    elif s_high:
        key = "review_mix"
    else:
        key = "diversified"
    return key, VERDICTS[key].format(w=w, o=o)


# ── row access + derived conversions ────────────────────────────────────────

def derived_conversions(sessions, cvr_fraction) -> int:
    """conversions = floor(sessions * cvr + 0.5) — half-up, mirrors
    cvr_signals.derived_conversions. CVR is a FRACTION (ShopifyQL PERCENT
    dtype ships fractions; never pre-multiplied by 100)."""
    return int(math.floor(num(sessions) * num(cvr_fraction) + 0.5))


def _get(r, *keys):
    """First non-None value among aliases (canonical key first)."""
    for k in keys:
        v = r.get(k)
        if v is not None:
            return v
    return None


def _name(r, keys):
    v = _get(r, *keys)
    if v is None or str(v) == "":
        return None
    return str(v)


_NAME_KEYS = {
    "products": ("name", "product", "title", "product_title"),
    "landing_pages": ("name", "page", "landing_page", "landing_page_path", "path"),
    "channels": ("name", "channel", "referrer", "referrer_source", "source"),
}


def _conv_value(r) -> float:
    """Conversion count for a sessions-based row: precomputed `conversions`
    when present, else derived from sessions x CVR (half-up), else 0."""
    c = r.get("conversions")
    if c is not None:
        return num(c)
    cvr = _get(r, "cvr", "conversion_rate")
    if cvr is not None:
        return float(derived_conversions(_get(r, "sessions"), cvr))
    return 0.0


def _n_derived(rows) -> int:
    """Rows whose conversion count had to be derived from a CVR fraction."""
    return sum(1 for r in rows
               if r.get("conversions") is None
               and _get(r, "cvr", "conversion_rate") is not None)


# ── dimension assembly ──────────────────────────────────────────────────────

def _aggregate(rows, name_of, spend_of, conv_of) -> list[tuple[str, float, float]]:
    """Sum the weight/outcome pair per entity name; drop all-zero entities;
    sort spend desc, name asc (deterministic)."""
    agg: dict[str, list[float]] = {}
    for r in rows:
        name = name_of(r)
        if name is None:
            continue
        e = agg.setdefault(str(name), [0.0, 0.0])
        e[0] += num(spend_of(r))
        e[1] += num(conv_of(r))
    ents = [(k, v[0], v[1]) for k, v in agg.items() if v[0] > 0 or v[1] > 0]
    ents.sort(key=lambda e: (-e[1], e[0]))
    return ents


def _metric_block(values) -> dict | None:
    a = _nonneg(values)
    if sum(a) <= 0:
        return None
    h = hhi(a)
    return {"hhi": round(h, 1), "eff_n": round(effective_n(a), 2),
            "gini": round(gini(a), 3), "band": hhi_band(h)}


def _dimension(key: str, label: str, ents, n_rows_raw: int, *,
               window: str = "", top_n: int = 25, lorenz_max: int = 101,
               caveat_extra: str | None = None,
               nouns=("weight", "outcomes")) -> dict:
    names = [e[0] for e in ents]
    spend = [e[1] for e in ents]
    conv = [e[2] for e in ents]
    total_spend, total_conv = sum(spend), sum(conv)
    sb, cb = _metric_block(spend), _metric_block(conv)
    vkey, vtext = verdict(sb["hhi"] if sb else None, cb["hhi"] if cb else None, nouns)
    abc = pareto_abc(spend)
    abc_summary = {}
    for band in ("A", "B", "C"):
        idx = [i for i, b in enumerate(abc) if b == band]
        share = (sum(spend[i] for i in idx) / total_spend) if total_spend > 0 else 0.0
        abc_summary[band] = {"n": len(idx), "share": round(share, 4)}
    top = []
    for i in range(min(top_n, len(ents))):
        top.append({
            "name": names[i], "spend": round(spend[i], 2), "conv": round(conv[i], 2),
            "spend_share": round(spend[i] / total_spend, 4) if total_spend > 0 else 0.0,
            "conv_share": round(conv[i] / total_conv, 4) if total_conv > 0 else 0.0,
            "abc": abc[i]})
    tail = None
    if len(ents) > top_n:
        t_spend = sum(spend[top_n:])
        tail = {"n": len(ents) - top_n, "spend": round(t_spend, 2),
                "conv": round(sum(conv[top_n:]), 2),
                "spend_share": round(t_spend / total_spend, 4) if total_spend > 0 else 0.0}
    caveats = []
    if len(ents) and len(ents) < SMALL_N:
        caveats.append(f"Only {len(ents)} entities — HHI bands assume many entities; "
                       "read Effective-N instead.")
    if caveat_extra:
        caveats.append(caveat_extra)
    return {
        "key": key, "label": label, "window": window,
        "n_entities": len(ents), "n_rows_raw": n_rows_raw,
        "total_spend": round(total_spend, 2), "total_conv": round(total_conv, 2),
        "spend": sb, "conv": cb,
        "verdict_key": vkey if ents else "insufficient",
        "verdict": vtext if ents else VERDICTS["insufficient"],
        "caveat": " ".join(caveats) or None,
        "lorenz": {"spend": downsample_lorenz(lorenz_points(spend), lorenz_max) if sb else None,
                   "conv": downsample_lorenz(lorenz_points(conv), lorenz_max) if cb else None},
        "abc": {"spend": abc_summary},
        "top": top, "tail": tail,
    }


def compute_concentration(product_rows=None, page_rows=None, channel_rows=None, *,
                          windows=None, files=None, top_n: int = 25,
                          lorenz_max: int = 101) -> dict | None:
    """Build the model["concentration"] block from NORMALIZED Shopify/GA4 rows
    (shopify_rows / manual_csv adapters — flat dicts, fraction-unit CVRs).

    product_rows — {name, revenue, orders?}: spend = revenue, conv = orders
      (orders absent everywhere -> conv block None -> no_conv_signal).
    page_rows — {name, sessions, cvr?, conversions?}: spend = sessions,
      conv = precomputed conversions when present, else derived from
      sessions x CVR (half-up, flagged in notes).
    channel_rows — {name, sessions, revenue?, cvr?, conversions?}: spend =
      sessions, conv = revenue when any row exports it, else conversions
      (precomputed or derived), else none.

    windows — optional display labels for provenance, keyed per dimension
    ("products"/"landing_pages"/"channels") with a "default" fallback. Rows
    carry no dates, so a missing label renders as "" — never fabricated.
    files — pre-computed provenance stamps ({name: file_stamp(path)}), passed
    through verbatim.
    Returns None when no row lists are supplied or every dimension is empty."""
    if product_rows is None and page_rows is None and channel_rows is None:
        return None
    w = windows or {}

    def win(dim_key: str) -> str:
        return w.get(dim_key) or w.get("default") or ""

    dims, notes = [], []

    if product_rows is not None:
        ents = _aggregate(product_rows,
                          lambda r: _name(r, _NAME_KEYS["products"]),
                          lambda r: _get(r, "revenue", "net_sales"),
                          lambda r: r.get("orders"))
        dims.append(_dimension("products", "Products", ents, len(product_rows),
                               window=win("products"), top_n=top_n,
                               lorenz_max=lorenz_max, nouns=NOUNS["products"]))

    if page_rows is not None:
        ents = _aggregate(page_rows,
                          lambda r: _name(r, _NAME_KEYS["landing_pages"]),
                          lambda r: r.get("sessions"),
                          _conv_value)
        dims.append(_dimension("landing_pages", "Landing pages", ents,
                               len(page_rows), window=win("landing_pages"),
                               top_n=top_n, lorenz_max=lorenz_max,
                               nouns=NOUNS["landing_pages"]))
        k = _n_derived(page_rows)
        if k:
            notes.append(f"Landing pages: conversions derived from sessions x CVR "
                         f"(half-up) for {k} of {len(page_rows)} rows.")

    if channel_rows is not None:
        if any(r.get("revenue") is not None for r in channel_rows):
            basis, nouns = "revenue", NOUNS["channels"]
            conv_of = lambda r: r.get("revenue")
        elif any(r.get("conversions") is not None
                 or _get(r, "cvr", "conversion_rate") is not None
                 for r in channel_rows):
            basis, nouns = "conversions", NOUNS["channels_conversions"]
            conv_of = _conv_value
        else:
            basis, nouns = None, NOUNS["channels"]
            conv_of = lambda r: 0.0
        ents = _aggregate(channel_rows,
                          lambda r: _name(r, _NAME_KEYS["channels"]),
                          lambda r: r.get("sessions"),
                          conv_of)
        dims.append(_dimension("channels", "Channels", ents, len(channel_rows),
                               window=win("channels"), top_n=top_n,
                               lorenz_max=lorenz_max, nouns=nouns))
        if basis == "conversions":
            notes.append("Channels: revenue absent from the channels pull — "
                         "conversion side uses conversions instead.")
            k = _n_derived(channel_rows)
            if k:
                notes.append(f"Channels: conversions derived from sessions x CVR "
                             f"(half-up) for {k} of {len(channel_rows)} rows.")

    if not any(d["n_entities"] for d in dims):
        return None
    return {"dimensions": dims, "files": files or {}, "notes": notes}
