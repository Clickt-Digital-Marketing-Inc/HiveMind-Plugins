#!/usr/bin/env python3
# Copyright (c) 2026 Clickt Digital Marketing Inc. All rights reserved.
"""Concentration analysis for the Meta Ads audit — HHI / Effective-N / Gini /
Lorenz / Pareto-ABC on spend and conversion results across campaigns, ad sets,
ads, and objectives.

Rows arrive ALREADY NORMALIZED by `meta_rows.normalize` (the transcription
firewall lives there: the model handles file paths, never numbers). This
module consumes the canonical flat rows — float `spend` in currency units
(no micros on Meta), float `conv_results` present only when the row's result
indicator is conversion-like — so there is no raw-envelope parsing here.
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

VERDICTS = {
    "no_conv_signal": ("No conversion signal in this window — verdict unavailable; "
                       "check conversion tracking or extend the window."),
    "consolidate": ("Diffuse spend, concentrated outcomes — a small core converts "
                    "while budget sprays wide. Consolidate into the proven core and "
                    "tighten negatives around it."),
    "fragility": ("Concentration fragility — spend and conversions both depend on a "
                  "handful of entities. One going cold takes the account with it; "
                  "plan deliberate diversification."),
    "diversified": ("Diversified — spend and conversions are both spread. Healthy, "
                    "provided the spread reflects intent rather than neglect."),
    "review_bidding": ("Concentrated spend, diffuse outcomes — budget is piling into "
                       "entities that don't dominate conversions. Review bidding, "
                       "targeting, and whether the spend leaders deserve their share."),
    "insufficient": "Insufficient data in this window to judge concentration.",
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


def verdict(spend_hhi, conv_hhi) -> tuple[str, str]:
    """Classify the spend-vs-conversions concentration gap. conv_hhi None means
    no conversion signal; spend_hhi None means no spend signal."""
    if spend_hhi is None:
        return "insufficient", VERDICTS["insufficient"]
    if conv_hhi is None:
        return "no_conv_signal", VERDICTS["no_conv_signal"]
    s_high = spend_hhi > HHI_HIGH
    c_high = conv_hhi > HHI_HIGH
    if s_high and c_high:
        key = "fragility"
    elif c_high:
        key = "consolidate"
    elif s_high:
        key = "review_bidding"
    else:
        key = "diversified"
    return key, VERDICTS[key]


# ── dimension assembly ──────────────────────────────────────────────────────

def _aggregate(rows, key_of, label_of=None) -> list[tuple[str, float, float, str]]:
    """Sum spend/conv_results per entity; drop all-zero entities;
    sort spend desc, label asc, key asc (deterministic).

    Returns (label, spend, conv, key) 4-tuples. `_dimension` reads only the
    first three (it indexes e[0..2]); the trailing key is what lets
    `_dupe_caveat` describe the entities that SURVIVED the all-zero filter
    rather than the raw rows.

    key_of IDENTIFIES the entity, label_of DISPLAYS it (defaults to key_of).
    The split matters: Meta entity names are NOT unique — reusing "Broad" or
    "LAL 1%" across campaigns, or running one creative in several ad sets, is
    the standard workflow. Keying by name silently merged those distinct
    entities into one, which inflated every metric computed downstream (HHI,
    Effective-N, Gini, Lorenz, ABC) and could flip the verdict. Key by the
    entity's own id where the source provides one; the manual UI-export path
    has no ids, so it falls back to the name (the best that data supports).

    The conversion side sums `conv_results` ONLY — rows whose result indicator
    is non-conversion (Reach, video views, …) contribute spend but zero
    conversions; `_excluded_indicators` surfaces them as a note."""
    label_of = label_of or key_of
    agg: dict[str, list] = {}
    for r in rows:
        key = key_of(r)
        if key is None:
            continue
        e = agg.setdefault(str(key), [0.0, 0.0, str(label_of(r) or key)])
        e[0] += num(r.get("spend"))
        e[1] += num(r.get("conv_results"))
    ents = [(v[2], v[0], v[1], k) for k, v in agg.items() if v[0] > 0 or v[1] > 0]
    ents.sort(key=lambda e: (-e[1], e[0], e[3]))
    return ents


def _entity_key(r):
    """Identity for aggregation: the entity's own id, else its name.

    The fallback is the manual UI-export path, which carries no ids — there,
    same-named rows are genuinely indistinguishable, so merging them is the
    honest limit of that data (_dupe_caveat says so in the report)."""
    return r.get("id") or r.get("name")


def _entity_label(r):
    """Display label: always the human name (never the opaque numeric id)."""
    return r.get("name")


def _dupe_caveat(rows, ents) -> str | None:
    """Describe shared names among the entities the table actually SHOWS.

    Two distinct situations, and they are properties of a NAME, not of the
    dimension — an earlier cut decided both from one dimension-wide `id_less`
    flag, so a single id-less row made the whole report claim rows had been
    merged when none had, and hid the genuine shared-name case behind it:

      split  — one name, several ids: distinct entities counted separately, so
               the table legitimately shows more than one row with that name.
      merged — one name, no id, several source rows: they collapsed into one
               entity because the export cannot tell them apart. A limit of the
               data, and the report should say so rather than imply precision.

    `ents` is the post-filter entity list, so a name whose entities were all
    dropped as all-zero is never described — it isn't on screen to explain.
    Single pass over rows: accounts can carry thousands of ads.
    """
    surviving: dict[str, set] = {}
    for label, _spend, _conv, key in ents:
        surviving.setdefault(label, set()).add(key)
    rows_by_name: dict[str, int] = {}
    for r in rows or []:
        name = r.get("name")
        if name is None:
            continue
        name = str(name)
        rows_by_name[name] = rows_by_name.get(name, 0) + 1
    split = sum(1 for keys in surviving.values() if len(keys) > 1)
    # keys == {label} means the entity was keyed by its own NAME — i.e. the row
    # carried no id — so >1 source row under that name collapsed into it.
    merged = sum(1 for label, keys in surviving.items()
                 if keys == {label} and rows_by_name.get(label, 0) > 1)
    parts = []
    if split:
        parts.append(f"{split} name(s) are shared by more than one entity — each "
                     "is counted separately (keyed by its own id), so the table "
                     "shows one row per entity.")
    if merged:
        parts.append(f"{merged} name(s) appear on more than one source row and "
                     "carry no id — those rows are merged, which the export "
                     "cannot distinguish.")
    return " ".join(parts) or None


def _excluded_indicators(rows) -> list[str]:
    """Result indicators dropped from the conversion side: rows carrying a raw
    `results` count but no `conv_results` (non-conversion indicator per
    meta_rows.is_conversion_indicator). Sorted for determinism."""
    inds = set()
    for r in rows or []:
        if "results" in r and "conv_results" not in r:
            inds.add(str(r.get("results_indicator") or "(unlabeled)"))
    return sorted(inds)


def _window_from_rows(rows) -> str:
    """Row-derived window fallback: span of ISO date_start..date_stop."""
    starts = [r["date_start"] for r in rows or [] if r.get("date_start")]
    stops = [r["date_stop"] for r in rows or [] if r.get("date_stop")]
    if starts and stops:
        return f"{min(starts)} – {max(stops)}"
    return ""


def _metric_block(values) -> dict | None:
    a = _nonneg(values)
    if sum(a) <= 0:
        return None
    h = hhi(a)
    return {"hhi": round(h, 1), "eff_n": round(effective_n(a), 2),
            "gini": round(gini(a), 3), "band": hhi_band(h)}


def _dimension(key: str, label: str, ents, n_rows_raw: int, *,
               window: str = "", top_n: int = 25, lorenz_max: int = 101,
               caveat_extra: str | None = None) -> dict:
    names = [e[0] for e in ents]
    spend = [e[1] for e in ents]
    conv = [e[2] for e in ents]
    total_spend, total_conv = sum(spend), sum(conv)
    sb, cb = _metric_block(spend), _metric_block(conv)
    vkey, vtext = verdict(sb["hhi"] if sb else None, cb["hhi"] if cb else None)
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


def compute_concentration(campaign_rows=None, adset_rows=None, ad_rows=None, *,
                          windows=None, files=None, top_n: int = 25,
                          lorenz_max: int = 101) -> dict | None:
    """Build the model["concentration"] block from NORMALIZED Meta rows
    (see meta_rows.normalize — flat dicts with float spend/conv_results).

    windows — optional display labels for provenance: {"structure": str,
    "creative": str}; campaigns/ad_sets/objectives take the structure window,
    ads the creative window, optionally overridden per dimension via
    "campaigns"/"ad_sets"/"ads"/"objectives" keys. A missing label falls back
    to the rows' own date_start..date_stop span.
    files — pre-computed provenance stamps ({name: meta_rows.file_stamp(path)}).
    Returns None when no row lists are supplied or every dimension is empty."""
    if campaign_rows is None and adset_rows is None and ad_rows is None:
        return None
    w = windows or {}

    def win(dim_key: str, default_key: str, rows) -> str:
        return w.get(dim_key) or w.get(default_key) or _window_from_rows(rows)

    dims, notes = [], []

    # Entity dimensions key by the row's own id (falling back to name only when
    # the source carries no id — the UI-export path); the name is the LABEL.
    # See _aggregate: names collide by design in Meta accounts.
    if campaign_rows is not None:
        ents = _aggregate(campaign_rows, _entity_key, _entity_label)
        dims.append(_dimension("campaigns", "Campaigns", ents, len(campaign_rows),
                               window=win("campaigns", "structure", campaign_rows),
                               top_n=top_n, lorenz_max=lorenz_max,
                               caveat_extra=_dupe_caveat(campaign_rows, ents)))
    if adset_rows is not None:
        ents = _aggregate(adset_rows, _entity_key, _entity_label)
        dims.append(_dimension("ad_sets", "Ad sets", ents, len(adset_rows),
                               window=win("ad_sets", "structure", adset_rows),
                               top_n=top_n, lorenz_max=lorenz_max,
                               caveat_extra=_dupe_caveat(adset_rows, ents)))
    if ad_rows is not None:
        ents = _aggregate(ad_rows, _entity_key, _entity_label)
        dims.append(_dimension("ads", "Ads", ents, len(ad_rows),
                               window=win("ads", "creative", ad_rows),
                               top_n=top_n, lorenz_max=lorenz_max,
                               caveat_extra=_dupe_caveat(ad_rows, ents)))
    if campaign_rows is not None:
        if any("objective" in r for r in campaign_rows):
            ents = _aggregate(campaign_rows, lambda r: r.get("objective"))
            dims.append(_dimension("objectives", "Objectives", ents,
                                   len(campaign_rows),
                                   window=win("objectives", "structure", campaign_rows),
                                   top_n=top_n, lorenz_max=lorenz_max))
        else:
            notes.append("objective absent from the campaigns pull — "
                         "objectives dimension omitted.")

    for label, rows in (("Campaigns", campaign_rows), ("Ad sets", adset_rows),
                        ("Ads", ad_rows)):
        if rows is None:
            continue
        inds = _excluded_indicators(rows)
        if inds:
            notes.append(f"{label}: non-conversion result indicators excluded "
                         f"from the conversion side — {', '.join(inds)}.")

    if not any(d["n_entities"] for d in dims):
        return None
    return {"dimensions": dims, "files": files or {}, "notes": notes}
