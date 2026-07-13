#!/usr/bin/env python3
# Copyright (c) 2026 Clickt Digital Marketing Inc. All rights reserved.
"""Creative Signals for the Meta Ads audit — creative fatigue, reach saturation,
effective-frequency zones, and ad-ranking decomposition, in pure stdlib.

The four signal functions mirror the MediaMetrics Meta analytics module
(`plugins/mediametrics-meta/skills/mediametrics-meta/analytics.py`) EXACTLY —
same clamps, same weight renormalization, same tie-breaks — reimplemented with
`math` only (no numpy) so this plugin stays standalone. Band cutoffs mirror
`mediametrics_meta_report.py`: fatigue saturated > 0.66, watch > 0.33;
reach saturation high > 0.5.

`compute_creative_signals` consumes canonical normalized rows (see
`meta_rows.normalize` / `manual_csv` adapters): flat dicts, floats, absent =
key omitted. Reach and frequency are NON-ADDITIVE — never summed; the tail
aggregate deliberately excludes them. Every embed is bounded (top-25 by spend,
name-asc tie-break); summary counts always cover the FULL row universe.
Deterministic: no wall clock, sorted iteration, fixed note order.

Stdlib only.
"""
from __future__ import annotations

import math

# Band cutoffs (mirror mediametrics_meta_report.py) and embed bounds.
FATIGUE_SATURATED = 0.66   # fatigue score above this = "saturated"
FATIGUE_WATCH = 0.33       # fatigue score above this = "watch" (else "fresh")
SATURATION_HIGH = 0.5      # reach-saturation above this = highly saturated
EFFECTIVE_LO = 3.0         # effective-frequency zone floor (Krugman/Naples)
EFFECTIVE_HI = 7.0         # effective-frequency zone ceiling
MIN_IMPRESSIONS_FATIGUE = 1000  # below this, fatigue is null (not scored)
TOP_N = 25                 # bounded-embed cap for ads / zones / rankings rows

_RANK_ORD = {"BELOW_AVERAGE": 0, "AVERAGE": 1, "ABOVE_AVERAGE": 2}
_RANK_LEVERS = ("quality", "engagement", "conversion")
_RANK_KEYS = ("quality_ranking", "engagement_rate_ranking",
              "conversion_rate_ranking")


def _f(x) -> float:
    """Coerce a scalar to float; None / non-numeric / NaN / inf -> 0.0.
    Mirrors analytics.py `_f` exactly. Never raises."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(v) or math.isinf(v):
        return 0.0
    return v


# ---------------------------------------------------------------------------
# Signal functions — EXACT stdlib mirrors of mediametrics-meta analytics.py
# ---------------------------------------------------------------------------
def creative_fatigue_score(frequency: float, ctr: float, cpm: float,
                           ctr_baseline: float, cpm_baseline: float) -> float:
    """Creative-fatigue score in [0, 1], rising with over-exposure.
    Mirror of mediametrics-meta analytics.py `creative_fatigue_score`.

    Blends three signals, weight-renormalized over whichever baselines exist:
      - frequency saturation `1 - exp(-max(0, frequency-1)/3)` (weight 0.5);
      - CTR erosion `min(1, max(0, 1 - ctr/ctr_baseline))` (weight 0.3),
        only when `ctr_baseline > 0`;
      - CPM inflation `min(1, max(0, cpm/cpm_baseline - 1))` (weight 0.2),
        only when `cpm_baseline > 0`.
    A missing/zero baseline drops that term (weight excluded). All inputs
    coerced via `_f`; result clamped to [0, 1]. Higher = more fatigued.
    """
    freq = max(0.0, _f(frequency))
    freq_comp = 1.0 - math.exp(-max(0.0, freq - 1.0) / 3.0)
    parts: list[tuple[float, float]] = [(0.5, freq_comp)]
    cb = _f(ctr_baseline)
    if cb > 0:
        parts.append((0.3, min(1.0, max(0.0, 1.0 - _f(ctr) / cb))))
    mb = _f(cpm_baseline)
    if mb > 0:
        parts.append((0.2, min(1.0, max(0.0, _f(cpm) / mb - 1.0))))
    wsum = sum(w for w, _ in parts)
    score = sum(w * c for w, c in parts) / wsum if wsum > 0 else 0.0
    return float(min(1.0, max(0.0, score)))


def reach_saturation(reach: float, impressions: float) -> float:
    """Reach saturation = 1 - reach/impressions, clamped [0, 1].
    Mirror of mediametrics-meta analytics.py `reach_saturation`.

    Share of impressions that were REPEAT exposures: 0 = every impression a
    unique person, ->1 = the same people seen over and over.
    impressions <= 0 -> 0.0.
    """
    imps = _f(impressions)
    if imps <= 0:
        return 0.0
    return float(min(1.0, max(0.0, 1.0 - _f(reach) / imps)))


def effective_frequency(frequency: float) -> dict:
    """Effective-frequency zone for an average frequency.
    Mirror of mediametrics-meta analytics.py `effective_frequency`.

    Returns {'frequency', 'effective', 'zone'} where `effective` is
    frequency >= EFFECTIVE_LO and zone is 'under' (<3), 'effective' (3-7) or
    'oversaturated' (>7) per the Krugman "three exposures" heuristic.
    """
    f = max(0.0, _f(frequency))
    if f < EFFECTIVE_LO:
        zone = "under"
    elif f <= EFFECTIVE_HI:
        zone = "effective"
    else:
        zone = "oversaturated"
    return {"frequency": float(f), "effective": bool(f >= EFFECTIVE_LO),
            "zone": zone}


def _rank_ord(grade) -> int | None:
    """Meta ranking grade -> ordinal; UNKNOWN / unrecognized -> None."""
    return _RANK_ORD.get(str(grade or "").strip().upper())


def ranking_decomposition(quality, engagement, conversion) -> dict:
    """Decompose Meta ad rankings into the weakest lever.
    Mirror of mediametrics-meta analytics.py `ranking_decomposition`.

    Inputs are the three Meta grade strings {BELOW_AVERAGE, AVERAGE,
    ABOVE_AVERAGE, UNKNOWN}. UNKNOWN (or anything unrecognized) is NO SIGNAL —
    never scored. Returns {'weakest' (ties broken quality -> engagement ->
    conversion; None if all unknown), 'known_count', 'all_unknown',
    'priority' (known levers weakest-first), 'grades'}.
    """
    levers = [(name, _rank_ord(g)) for name, g in
              zip(_RANK_LEVERS, (quality, engagement, conversion))]
    known = [(n, o) for n, o in levers if o is not None]
    all_unknown = not known
    weakest = None
    if known:
        best: tuple[str, int] | None = None
        for n, o in levers:                       # fixed order => stable tie-break
            if o is None:
                continue
            if best is None or o < best[1]:
                best = (n, o)
        weakest = best[0]
    priority = [n for n, o in sorted(
        known, key=lambda x: (x[1], _RANK_LEVERS.index(x[0])))]
    return {"weakest": weakest, "known_count": len(known),
            "all_unknown": all_unknown, "priority": priority,
            "grades": {n: o for n, o in levers}}


# ---------------------------------------------------------------------------
# Audit-block assembly
# ---------------------------------------------------------------------------
def fatigue_band(score) -> str | None:
    """Band a fatigue score per mediametrics_meta_report.py: saturated > 0.66,
    watch > 0.33, else fresh. None in -> None out."""
    if score is None:
        return None
    return ("saturated" if score > FATIGUE_SATURATED
            else "watch" if score > FATIGUE_WATCH else "fresh")


def account_baselines(ad_rows) -> dict:
    """Totals-based account baselines (the MediaMetrics convention — NOT
    spend-weighted per-ad means): ctr = sum(clicks)/sum(impressions),
    cpm = sum(spend)/sum(impressions)*1000. Zero impressions -> 0.0 baselines
    (fatigue then drops those terms). Values UNROUNDED."""
    rows = list(ad_rows or [])
    clicks = sum(_f(r.get("clicks")) for r in rows)
    impressions = sum(_f(r.get("impressions")) for r in rows)
    spend = sum(_f(r.get("spend")) for r in rows)
    ctr = clicks / impressions if impressions > 0 else 0.0
    cpm = spend / impressions * 1000.0 if impressions > 0 else 0.0
    return {"ctr": ctr, "cpm": cpm, "n_ads": len(rows)}


def _by_spend(rows) -> list:
    """Deterministic entity order: spend desc, then name asc, then id asc."""
    return sorted(rows, key=lambda r: (-_f(r.get("spend")),
                                       str(r.get("name", "")),
                                       str(r.get("id", ""))))


def _rnd(row, key, nd):
    """round(row[key], nd) when present, else None (absent = null in embeds)."""
    return round(_f(row.get(key)), nd) if key in row else None


def _window(rows) -> str | None:
    """Window label from the rows' own dates: min date_start - max date_stop."""
    starts = sorted(r["date_start"] for r in rows if r.get("date_start"))
    stops = sorted(r["date_stop"] for r in rows if r.get("date_stop"))
    if not starts or not stops:
        return None
    return f"{starts[0]} – {stops[-1]}"


def compute_creative_signals(ad_rows, adset_rows=None, *, ref_date=None,
                             top_n: int = TOP_N,
                             min_impressions: int = MIN_IMPRESSIONS_FATIGUE
                             ) -> dict | None:
    """Assemble the Creative Signals model block from normalized ad (and
    optionally ad-set) rows. Returns None when there are no ad rows.

    `ref_date` is accepted for signature stability but unused (age-based
    checks live in prescore.py off `generated_for_date`). Fatigue is null for
    ads below the `min_impressions` floor. Rankings are only available when
    ranking keys exist on the rows (manual-CSV path). Summary counts span ALL
    rows; `ads`/`zones.rows`/`rankings.rows` embeds are top-`top_n` by spend.
    """
    rows = list(ad_rows or [])
    if not rows:
        return None
    asets = list(adset_rows or [])
    notes: list[str] = []
    base = account_baselines(rows)

    # Full-universe per-ad signals (bounded embeds sliced after).
    fatigue_by_id: dict[int, float | None] = {}
    saturation_by_id: dict[int, float | None] = {}
    summary = {"saturated": 0, "watch": 0, "fresh": 0,
               "high_saturation": 0, "below_floor": 0}
    missing_reach = 0
    for i, r in enumerate(rows):
        imps = r.get("impressions")
        if imps is None or _f(imps) < min_impressions:
            fatigue_by_id[i] = None
            summary["below_floor"] += 1
        else:
            score = creative_fatigue_score(r.get("frequency"), r.get("ctr"),
                                           r.get("cpm"), base["ctr"],
                                           base["cpm"])
            fatigue_by_id[i] = round(score, 4)
            summary[fatigue_band(fatigue_by_id[i])] += 1  # band the ROUNDED
            # score so summary counts always agree with the embedded bands
        if "reach" in r and "impressions" in r:
            sat = round(reach_saturation(r["reach"], r["impressions"]), 4)
            saturation_by_id[i] = sat
            if sat > SATURATION_HIGH:
                summary["high_saturation"] += 1
        else:
            saturation_by_id[i] = None
            missing_reach += 1

    order = sorted(range(len(rows)),
                   key=lambda i: (-_f(rows[i].get("spend")),
                                  str(rows[i].get("name", "")),
                                  str(rows[i].get("id", ""))))
    top_idx, tail_idx = order[:top_n], order[top_n:]

    ads = []
    for i in top_idx:
        r = rows[i]
        ads.append({
            "name": r.get("name", ""),
            "spend": _rnd(r, "spend", 2),
            "impressions": _rnd(r, "impressions", 2),
            "reach": _rnd(r, "reach", 2),
            "frequency": _rnd(r, "frequency", 2),
            "ctr": _rnd(r, "ctr", 6),
            "cpm": _rnd(r, "cpm", 2),
            "results": _rnd(r, "results", 2),
            "results_indicator": r.get("results_indicator"),
            "fatigue": fatigue_by_id[i],
            "fatigue_band": fatigue_band(fatigue_by_id[i]),
            "saturation": saturation_by_id[i],
        })

    total_spend = sum(_f(r.get("spend")) for r in rows)
    tail = None
    if tail_idx:
        t_spend = sum(_f(rows[i].get("spend")) for i in tail_idx)
        tail = {  # NO reach/frequency — non-additive across ads
            "n": len(tail_idx),
            "spend": round(t_spend, 2),
            "impressions": round(sum(_f(rows[i].get("impressions"))
                                     for i in tail_idx), 2),
            "spend_share": (round(t_spend / total_spend, 4)
                            if total_spend > 0 else 0.0),
        }

    # Effective-frequency zones — per AD SET (frequency is level-native there).
    zoned = [r for r in asets if r.get("frequency") is not None]
    zones = {"under": 0, "effective": 0, "oversaturated": 0, "rows": []}
    for r in zoned:
        zones[effective_frequency(r["frequency"])["zone"]] += 1
    for r in _by_spend(zoned)[:top_n]:
        zones["rows"].append({"name": r.get("name", ""),
                              "frequency": round(_f(r.get("frequency")), 2),
                              "zone": effective_frequency(r["frequency"])["zone"],
                              "spend": _rnd(r, "spend", 2)})

    # Rankings — CSV-path-only unlock (raw API rows carry no ranking keys).
    ranked = [r for r in rows if any(k in r for k in _RANK_KEYS)]
    if not ranked:
        rankings: dict = {"available": False}
    else:
        rsum = {"quality": 0, "engagement": 0, "conversion": 0}
        all_unknown = 0
        rrows = []
        for r in ranked:
            d = ranking_decomposition(r.get("quality_ranking"),
                                      r.get("engagement_rate_ranking"),
                                      r.get("conversion_rate_ranking"))
            if d["all_unknown"]:
                all_unknown += 1
            else:
                rsum[d["weakest"]] += 1
        for r in _by_spend(ranked)[:top_n]:
            d = ranking_decomposition(r.get("quality_ranking"),
                                      r.get("engagement_rate_ranking"),
                                      r.get("conversion_rate_ranking"))
            rrows.append({"name": r.get("name", ""),
                          "spend": _rnd(r, "spend", 2),
                          "quality": r.get("quality_ranking"),
                          "engagement": r.get("engagement_rate_ranking"),
                          "conversion": r.get("conversion_rate_ranking"),
                          "weakest": d["weakest"],
                          "known_count": d["known_count"],
                          "priority": d["priority"]})
        rankings = {"available": True, "rows": rrows,
                    "summary": {"n_ranked": len(ranked), "weakest": rsum,
                                "all_unknown": all_unknown}}

    # Notes — fixed order for determinism.
    objectives = sorted({r["objective"] for r in rows + asets
                         if r.get("objective")})
    if len(objectives) > 1:
        notes.append("Baselines are account-wide CTR/CPM across mixed "
                     "objectives (" + ", ".join(objectives) + ") — CTR-erosion "
                     "and CPM-inflation terms compare unlike campaigns.")
    else:
        goals = sorted({r["optimization_goal"] for r in asets
                        if r.get("optimization_goal")})
        inds = sorted({r["results_indicator"] for r in rows
                       if r.get("results_indicator")})
        mixed = goals if len(goals) > 1 else inds if len(inds) > 1 else None
        if mixed:
            notes.append("Baselines are account-wide CTR/CPM across mixed "
                         "campaign goals (" + ", ".join(mixed) + ") — "
                         "CTR-erosion and CPM-inflation terms compare unlike "
                         "campaigns.")
    if summary["below_floor"]:
        notes.append(f"{summary['below_floor']} of {len(rows)} ads below the "
                     f"{min_impressions:,}-impression floor — fatigue not "
                     "scored for them.")
    if missing_reach:
        notes.append(f"{missing_reach} of {len(rows)} ads missing reach — "
                     "saturation not computed for them.")
    if not asets:
        notes.append("No ad-set rows provided — effective-frequency zones "
                     "not computed.")
    elif len(zoned) < len(asets):
        notes.append(f"{len(asets) - len(zoned)} of {len(asets)} ad sets "
                     "missing frequency — excluded from zone counts.")
    if not ranked:
        notes.append("Quality/engagement/conversion rankings not present in "
                     "the input (raw API path) — rankings unlock on the "
                     "manual CSV export path.")

    return {
        "window": _window(rows),
        "baselines": {"ctr": round(base["ctr"], 6),
                      "cpm": round(base["cpm"], 4),
                      "n_ads": base["n_ads"]},
        "ads": ads,
        "tail": tail,
        "zones": zones,
        "summary": summary,
        "rankings": rankings,
        "notes": notes,
    }
