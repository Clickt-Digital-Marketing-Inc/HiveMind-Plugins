#!/usr/bin/env python3
# Copyright (c) 2026 Clickt Digital Marketing Inc. All rights reserved.
"""Deterministic pre-scorer — machine-scores the Meta audit's mechanical checks.

Every framework check whose logic is a pure data comparison gets its
result/observed computed here, in Python, from the same normalized raw-MCP or
manual-CSV rows (see `meta_rows.normalize` / `manual_csv`) the Concentration
report ingests. `merge_into_findings` then enforces those results over the
model-authored payload at build time, logging any disagreement (a built-in
drift detector). Checks whose required fields are absent from the inputs are
*skipped* — they stay LLM-judged — so both input paths degrade gracefully.

Thresholds are verbatim from `references/metrics-benchmarks.md`; check
metadata (name/expected/severity) from `references/audit-framework.md` (the
AR-04 severity is Critical per benchmarks §2 — hard goal mismatch). Meta
`results` are objective-relative: BP-02 is scored ONLY when the spending
campaigns' results indicators are homogeneous (otherwise the spend/results
mix is emitted as evidence, never scored), and every results-bearing line
names the indicators counted. CR-07 gets its full PASS/FLAG/FAIL bands only
on a <=8-day window (7d ad-set pull or a short CSV export); on longer windows
it degrades to PASS-only mode with an honest window label. CR-04 (CTR-Link)
is scored only on the manual-CSV path (`link_clicks`) for Ecommerce; the
all-click CTR is evidence-only and is always labeled "all-click (not link)".

Stdlib only. Deterministic: no wall clock (`generated_for_date` is an input;
its default is the max `date_stop` in the rows), sorted iteration, entity
lists ordered spend desc then name asc. All numbers here come from files
parsed deterministically — nothing in this module reads model-authored text
except the payload it corrects.
"""
from __future__ import annotations

import copy
import datetime as _dt
import re

from audit_model import FLAG_CANON, SECTIONS, SEV_CANON
from meta_rows import window_label

_CAT_BY_PREFIX = {code: cat for code, cat, _, _ in SECTIONS}
_CAT_ORDER = {cat: i for i, (_, cat, _, _) in enumerate(SECTIONS)}
_RAW_PULLS_DOC = "references/raw-pulls.md"

# Framework metadata for machine-scored (A) and evidence-only (B) checks.
# Names/severities match tests/sample-payload.json (the product contract);
# AR-04 is Critical per metrics-benchmarks.md §2 (hard goal mismatch).
CHECK_RULES = {
    # Category A — machine-scored
    "DI-01": {"name": "Dataset/pixel exists & active", "severity": "Critical",
              "expected": ">=1 active dataset receiving events"},
    "DI-04": {"name": "EMQ (Purchase/Lead)", "severity": "Critical",
              "expected": "Primary-event match quality >=8.0 (FLAG 6-8, FAIL <6)"},
    "AR-01": {"name": "Top-3 spend concentration", "severity": "High",
              "expected": "Top-3 campaigns >=60% of spend "
                          "(FLAG 45-60%, FAIL <45% — over-fragmented)"},
    "AR-02": {"name": "Fragmentation / learning starvation", "severity": "Critical",
              "expected": "Active ad sets clear ~25 results per 30d "
                          "(learning-phase floor)"},
    "AR-03": {"name": "Conflated goals", "severity": "High",
              "expected": "One optimization goal per campaign"},
    "AR-04": {"name": "Goal vs objective alignment", "severity": "Critical",
              "expected": "Ad-set optimization goals match the campaign objective "
                          "(no sales/leads objective optimizing clicks/reach/"
                          "engagement)"},
    "BP-02": {"name": "Spend vs results contribution", "severity": "High",
              "expected": "No campaign takes >10% of spend while producing "
                          "<5% of results"},
    "AT-02": {"name": "1-day-view reliance", "severity": "High",
              "expected": "<20% of spend on attribution containing 1d_view "
                          "(FLAG 20-50%, FAIL >50%)"},
    "AT-03": {"name": "7-day-click preference", "severity": "Medium",
              "expected": "Exactly-7d_click attribution dominant (>=50% of spend)"},
    "CR-03": {"name": "Hold-through (P100/P25)", "severity": "Medium",
              "expected": ">=35% of hooked (P25) viewers reach video end"},
    "CR-04": {"name": "CTR-Link", "severity": "High",
              "expected": "Link CTR >=0.8% (Ecommerce prospecting; "
                          "FLAG 0.5-0.8%, FAIL <0.5%)"},
    "CR-06": {"name": "Spend concentration (top-5 ads)", "severity": "High",
              "expected": "Top-5 ads <50% of L90 ad spend (FLAG 50-70%, FAIL >70%)"},
    "CR-07": {"name": "Frequency (prospecting)", "severity": "High",
              "expected": "Spend-weighted ad-set frequency <3.0 "
                          "(FLAG 3-5, FAIL >5 on a 7-day window)"},
    "CR-08": {"name": "Refresh cadence", "severity": "Low",
              "expected": "Newest active ad <=30 days old (FLAG 31-60, FAIL >60)"},
    # Category B — evidence only (result stays with the auditor)
    "AR-07": {"name": "Legacy campaign drift", "severity": "Medium", "expected": ""},
    "BP-01": {"name": "Daily vs lifetime pacing", "severity": "Medium", "expected": ""},
    "BP-03": {"name": "Budget-capped efficient campaigns", "severity": "Medium",
              "expected": ""},
    "BP-04": {"name": "Bid strategy fit", "severity": "Medium", "expected": ""},
    "AT-01": {"name": "Attribution-window inventory", "severity": "Medium",
              "expected": ""},
    "CR-01": {"name": "Thumb-stop (3s)", "severity": "Medium", "expected": ""},
    "CR-02": {"name": "ThruPlay (hold) rate", "severity": "Medium", "expected": ""},
    "CR-05": {"name": "Concept count (prospecting)", "severity": "High",
              "expected": ""},
}

# Thresholds (references/metrics-benchmarks.md; ⚙ = tunable module constant).
AR01_FLAG, AR01_PASS = 45.0, 60.0            # top-3 spend share %
AR02_RESULT_FLOOR = 25.0                     # results per ~30d
AR02_FAIL_SHARE, AR02_FLAG_SHARE = 50.0, 30.0  # ⚙ starved share %
AR02_FLAG_COUNT = 3                          # ⚙ starved count
BP02_SPEND_SHARE, BP02_RESULTS_SHARE = 10.0, 5.0
BP02_FAIL_SPEND = 25.0                       # ⚙ offenders' combined spend share %
AT02_LO, AT02_HI = 20.0, 50.0                # ⚙ 1d_view spend share %
AT03_PASS = 50.0                             # ⚙ exactly-7d_click spend share %
CR03_MIN_P25 = 100.0                         # ⚙ Σp25 floor before scoring
CR03_PASS = 35.0                             # hold-through %
CR04_FLAG, CR04_PASS = 0.5, 0.8              # CTR-Link %
CR06_FLAG, CR06_FAIL = 50.0, 70.0            # top-5 ad spend share %
CR07_FLAG, CR07_FAIL = 3.0, 5.0              # spend-weighted frequency
CR07_SHORT_WINDOW_DAYS = 8                   # full bands need window <= this
CR08_PASS_DAYS, CR08_FLAG_DAYS = 30, 60      # newest-active-ad age
DI04_FLAG, DI04_PASS = 6.0, 8.0              # EMQ composite
AR07_LEGACY_DAYS = 540                       # ⚙ legacy-campaign age
BP03_CPR_RATIO = 0.75                        # ⚙ CPR < ratio × median
BP03_SMALL_SHARE = 10.0                      # ⚙ "small" = spend share < this %

# AR-04 alignment table. Hard mismatches FAIL, soft FLAG; OFFSITE_CONVERSIONS
# is ALIGNED for sales/leads (website conversions). For OUTCOME_AWARENESS,
# soft=None means anything not aligned is a soft mismatch. Combos not
# classified here are ignored and noted (never guessed).
_AR04_HARD = frozenset({"LINK_CLICKS", "THRUPLAY", "REACH", "POST_ENGAGEMENT",
                        "PAGE_LIKES", "TWO_SECOND_CONTINUOUS_VIDEO_VIEWS"})
_AR04_TABLE = {
    "OUTCOME_SALES": {
        "aligned": frozenset({"OFFSITE_CONVERSIONS", "VALUE"}),
        "hard": _AR04_HARD, "soft": frozenset({"LANDING_PAGE_VIEWS"})},
    "OUTCOME_LEADS": {
        "aligned": frozenset({"OFFSITE_CONVERSIONS", "LEAD_GENERATION",
                              "QUALITY_LEAD"}),
        "hard": _AR04_HARD, "soft": frozenset({"LANDING_PAGE_VIEWS"})},
    "OUTCOME_TRAFFIC": {
        "aligned": frozenset({"LINK_CLICKS", "LANDING_PAGE_VIEWS"}),
        "hard": frozenset(),
        "soft": frozenset({"OFFSITE_CONVERSIONS", "VALUE"})},
    "OUTCOME_AWARENESS": {
        "aligned": frozenset({"REACH", "IMPRESSIONS", "THRUPLAY",
                              "AD_RECALL_LIFT",
                              "TWO_SECOND_CONTINUOUS_VIDEO_VIEWS"}),
        "hard": frozenset(), "soft": None},
}


# ── canonicalizers / small helpers (ported from the google skeleton) ─────────

def canon_enum(v) -> str:
    """'Outcome Leads' -> 'OUTCOME_LEADS'; already-canonical enums unchanged."""
    return re.sub(r"_+", "_", re.sub(r"[^A-Z0-9]+", "_", str(v or "").upper())).strip("_")


def _f(row, key):
    v = row.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def wavg(pairs) -> float | None:
    """[(weight, value)] -> sum(w*v)/sum(w); None when total weight <= 0."""
    tw = sum(w for w, _ in pairs)
    if tw <= 0:
        return None
    return sum(w * v for w, v in pairs) / tw


def _band(value, lo, hi, higher_is_better):
    """Threshold banding: (lo, hi) delimit FLAG territory."""
    if higher_is_better:
        return "PASS" if value >= hi else ("FLAG" if value >= lo else "FAIL")
    return "PASS" if value < lo else ("FLAG" if value <= hi else "FAIL")


def _spend(r) -> float:
    return _f(r, "spend") or 0.0


def _active(r) -> bool:
    return canon_enum(r.get("effective_status")) == "ACTIVE"


def _iso(v):
    try:
        return _dt.date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _ref_date(rows, generated_for_date):
    """Reference date for age checks: generated_for_date wins, else the max
    date_stop across the rows. -> (date|None, source_label|None)."""
    d = _iso(generated_for_date) if generated_for_date else None
    if d is not None:
        return d, "generated_for_date"
    stops = sorted(d for d in (_iso(r.get("date_stop")) for r in rows or [])
                   if d is not None)
    if stops:
        return stops[-1], "max date_stop"
    return None, None


def _win(rows) -> tuple:
    label, days = window_label(rows)
    return (label or "window unavailable", days)


def _names(items, n=5) -> str:
    """Join up to n names; deterministic (caller pre-sorts)."""
    items = list(items)
    out = ", ".join(items[:n])
    if len(items) > n:
        out += f", … (+{len(items) - n} more)"
    return out


def _median(values) -> float | None:
    vals = sorted(values)
    if not vals:
        return None
    n = len(vals)
    mid = n // 2
    return vals[mid] if n % 2 else (vals[mid - 1] + vals[mid]) / 2.0


# ── rule engine ──────────────────────────────────────────────────────────────

def _ar04_class(objective: str, goal: str) -> str:
    spec = _AR04_TABLE.get(objective)
    if spec is None:
        return "unknown"
    if goal in spec["aligned"]:
        return "aligned"
    if goal in spec["hard"]:
        return "hard"
    if spec["soft"] is None or goal in spec["soft"]:
        return "soft"
    return "unknown"


def compute_prescore(campaign_rows=None, adset_rows=None, ad_rows=None,
                     adset7_rows=None, datasets=None, dataset_quality=None, *,
                     business_model: str = "", generated_for_date=None,
                     creative_signals: dict | None = None) -> dict | None:
    """Machine-score the mechanical checks from normalized entity rows.

    All positional inputs are optional; returns the prescore block, or None
    when nothing at all is supplied. `datasets` is the (deduped) list from
    `meta_rows.load_datasets`; `dataset_quality` the {channel: [events]}
    mapping from `meta_rows.load_dataset_quality`; `creative_signals` the
    block from `creative_signals.compute_creative_signals` (evidence + the
    Fatigued Ads KPI only — its per-ad math is not re-scored here)."""
    if (campaign_rows is None and adset_rows is None and ad_rows is None
            and adset7_rows is None and datasets is None
            and dataset_quality is None):
        return None

    checks: dict[str, dict] = {}
    evidence: dict[str, dict] = {}
    skipped: list[dict] = []
    notes: list[str] = []

    bm = business_model if business_model in ("Lead Gen", "Ecommerce") else "Lead Gen"
    if business_model not in ("Lead Gen", "Ecommerce"):
        notes.append("business_model absent/unknown — Lead Gen assumed (drives "
                     "CR-04 scoring and the DI-04 primary event).")

    def skip(cid, reason):
        skipped.append({"id": cid, "reason": reason})

    def add(cid, result, observed):
        checks[cid] = {"result": result, "observed": observed,
                       "severity": CHECK_RULES[cid]["severity"]}

    camps = list(campaign_rows or [])
    asets = list(adset_rows or [])
    ads = list(ad_rows or [])
    camp_win, camp_days = _win(camps)
    aset_win, aset_days = _win(asets)
    ad_win, _ad_days = _win(ads)
    spenders = [r for r in camps if _spend(r) > 0]
    total_camp_spend = sum(_spend(r) for r in spenders)

    # ---- AR-01 — top-3 campaign spend concentration ------------------------
    if campaign_rows is None:
        skip("AR-01", "no campaigns input provided")
    elif total_camp_spend <= 0:
        skip("AR-01", "no campaign spend in the input")
    else:
        top3 = sum(sorted((_spend(r) for r in camps), reverse=True)[:3])
        share = top3 / total_camp_spend * 100.0
        obs = (f"Top-3 campaigns {share:.1f}% of spend ({top3:,.2f} of "
               f"{total_camp_spend:,.2f} across {len(spenders)} spending "
               f"campaigns; {camp_win})")
        if len(spenders) < 4:
            obs += " — fewer than 4 spending campaigns, top-3 share is trivially high"
        add("AR-01", _band(share, AR01_FLAG, AR01_PASS, True), obs)

    # ---- AR-02 — learning starvation (starved ad sets) ---------------------
    if adset_rows is None:
        skip("AR-02", "no ad sets input provided")
    else:
        has_status = any("effective_status" in r for r in asets)
        universe = [r for r in asets
                    if _spend(r) > 0 and (not has_status or _active(r))]
        with_results = [r for r in universe if r.get("results") is not None]
        if not universe:
            skip("AR-02", "no active ad sets with spend in the input")
        elif not with_results:
            skip("AR-02", "ad-set rows carry no results — re-pull per "
                          f"{_RAW_PULLS_DOC} / re-export with the Results column")
        else:
            starved = [r for r in with_results
                       if (_f(r, "results") or 0.0) < AR02_RESULT_FLOOR]
            share = len(starved) / len(with_results) * 100.0
            inds = sorted({r.get("results_indicator") or "unlabeled"
                           for r in with_results})
            if share > AR02_FAIL_SHARE:
                result = "FAIL"
            elif len(starved) >= AR02_FLAG_COUNT or share > AR02_FLAG_SHARE:
                result = "FLAG"
            else:
                result = "PASS"
            obs = (f"{len(starved)} of {len(with_results)} active ad sets with "
                   f"spend under {int(AR02_RESULT_FLOOR)} results ({share:.0f}%; "
                   f"indicators counted: {', '.join(inds)}; {aset_win})")
            if not has_status:
                obs += " — delivery status not in input, spend>0 used as the active proxy"
            if len(with_results) < len(universe):
                obs += (f" — {len(universe) - len(with_results)} active ad sets "
                        "returned no results (excluded)")
            add("AR-02", result, obs)
            if aset_days is not None and not (28 <= aset_days <= 31):
                notes.append(f"AR-02: the 25-result learning floor assumes a "
                             f"~30-day window; the ad-set window is {aset_days} "
                             "days.")

    # ---- AR-03 — mixed optimization goals within a campaign ----------------
    if adset_rows is None:
        skip("AR-03", "no ad sets input provided")
    else:
        linked = [r for r in asets
                  if r.get("campaign_id") and r.get("optimization_goal")]
        if not linked:
            skip("AR-03", "ad-set rows carry no campaign_id + optimization_goal "
                          f"linkage — re-pull per {_RAW_PULLS_DOC}")
        else:
            by_camp: dict[str, set] = {}
            for r in linked:
                by_camp.setdefault(str(r["campaign_id"]), set()).add(
                    canon_enum(r["optimization_goal"]))
            name_by_id = {str(r.get("id")): r.get("name", "")
                          for r in camps if r.get("id")}
            mixed_ids = sorted(cid for cid, goals in by_camp.items()
                               if len(goals) > 1)
            if mixed_ids:
                labels = sorted(
                    f"{name_by_id.get(cid) or cid} "
                    f"({', '.join(sorted(by_camp[cid]))})" for cid in mixed_ids)
                add("AR-03", "FLAG",
                    f"{len(mixed_ids)} of {len(by_camp)} campaigns mix ad-set "
                    f"optimization goals: {_names(labels)} ({aset_win})")
            else:
                add("AR-03", "PASS",
                    f"No campaign mixes ad-set optimization goals "
                    f"({len(by_camp)} campaigns, {len(linked)} ad sets; {aset_win})")

    # ---- AR-04 — objective <-> optimization-goal alignment -----------------
    if adset_rows is None:
        skip("AR-04", "no ad sets input provided")
    elif campaign_rows is None:
        skip("AR-04", "no campaigns input provided — campaign objectives "
                      "unavailable for the alignment table")
    else:
        obj_by_id = {str(r["id"]): canon_enum(r["objective"])
                     for r in camps if r.get("id") and r.get("objective")}
        pairs = []
        for r in asets:
            goal = r.get("optimization_goal")
            obj = obj_by_id.get(str(r.get("campaign_id") or ""))
            if goal and obj:
                pairs.append((r, obj, canon_enum(goal)))
        if not pairs:
            skip("AR-04", "no ad-set -> campaign-objective linkage in the "
                          f"inputs — re-pull per {_RAW_PULLS_DOC}")
        else:
            hard, soft, unknown = [], [], set()
            n_aligned = 0
            for r, obj, goal in pairs:
                cls = _ar04_class(obj, goal)
                if cls == "hard":
                    hard.append(f"{r.get('name', '')} ({obj} -> {goal})")
                elif cls == "soft":
                    soft.append(f"{r.get('name', '')} ({obj} -> {goal})")
                elif cls == "aligned":
                    n_aligned += 1
                else:
                    unknown.add(f"{obj} -> {goal}")
            result = "FAIL" if hard else ("FLAG" if soft else "PASS")
            bits = [f"{len(pairs)} ad sets checked, {n_aligned} aligned"]
            if hard:
                bits.append(f"{len(hard)} HARD mismatches: {_names(sorted(hard))}")
            if soft:
                bits.append(f"{len(soft)} soft mismatches: {_names(sorted(soft))}")
            obs = "; ".join(bits) + f" ({aset_win})"
            add("AR-04", result, obs)
            if unknown:
                notes.append("AR-04: unclassified objective -> goal combos "
                             "ignored (not scored): "
                             + ", ".join(sorted(unknown)) + ".")

    # ---- BP-02 — spend vs results contribution -----------------------------
    if campaign_rows is None:
        skip("BP-02", "no campaigns input provided")
    elif total_camp_spend <= 0:
        skip("BP-02", "no campaign spend in the input")
    else:
        with_results = [r for r in spenders if r.get("results") is not None]
        inds = sorted({r.get("results_indicator") or "unlabeled"
                       for r in with_results})
        total_results = sum(_f(r, "results") or 0.0 for r in with_results)
        mix: dict[str, float] = {}
        for r in spenders:
            key = (r.get("results_indicator") or
                   ("(no results returned)" if r.get("results") is None
                    else "unlabeled"))
            mix[key] = mix.get(key, 0.0) + _spend(r)
        mix_parts = [f"{k} {v / total_camp_spend * 100:.1f}%"
                     for k, v in sorted(mix.items(), key=lambda x: (-x[1], x[0]))]
        if not with_results:
            skip("BP-02", "campaign rows carry no results — re-pull per "
                          f"{_RAW_PULLS_DOC} / re-export with the Results column")
        elif total_results <= 0:
            skip("BP-02", f"no results recorded in {camp_win} — results shares "
                          "undefined")
        elif len(inds) > 1:
            skip("BP-02", "results indicators are heterogeneous across spending "
                          "campaigns (" + ", ".join(inds) + ") — results are "
                          "objective-relative, shares not comparable; spend mix "
                          "left as evidence")
            evidence["BP-02"] = {"observed":
                "Not machine-scored: results indicators are mixed (results are "
                "objective-relative). Campaign spend by results indicator: "
                + ", ".join(mix_parts) + f" ({camp_win})."}
        else:
            offenders = []
            for r in with_results:
                ss = _spend(r) / total_camp_spend * 100.0
                rs = (_f(r, "results") or 0.0) / total_results * 100.0
                if ss > BP02_SPEND_SHARE and rs < BP02_RESULTS_SHARE:
                    offenders.append((ss, rs, r.get("name", "")))
            offenders.sort(key=lambda t: (-t[0], t[2]))
            off_spend = sum(ss for ss, _, _ in offenders)
            n_no_results = len(spenders) - len(with_results)
            if not offenders:
                obs = (f"No campaign takes >{BP02_SPEND_SHARE:.0f}% of spend with "
                       f"<{BP02_RESULTS_SHARE:.0f}% of results "
                       f"({len(with_results)} campaigns, indicator: {inds[0]}; "
                       f"{camp_win})")
                result = "PASS"
            else:
                labels = [f"{name} ({ss:.1f}% spend / {rs:.1f}% results)"
                          for ss, rs, name in offenders]
                obs = (f"{len(offenders)} campaign(s) over "
                       f"{BP02_SPEND_SHARE:.0f}% of spend with under "
                       f"{BP02_RESULTS_SHARE:.0f}% of results — combined "
                       f"{off_spend:.1f}% of spend: {_names(labels)} "
                       f"(indicator: {inds[0]}; {camp_win})")
                result = "FAIL" if off_spend > BP02_FAIL_SPEND else "FLAG"
            if n_no_results:
                obs += (f" — {n_no_results} spending campaign(s) returned no "
                        "results (excluded)")
            add("BP-02", result, obs)

    # ---- AT-02 / AT-03 — attribution-window spend shares --------------------
    att_rows = [r for r in asets if r.get("attribution_setting")]
    att_spend = sum(_spend(r) for r in att_rows)
    if adset_rows is None:
        skip("AT-02", "no ad sets input provided")
        skip("AT-03", "no ad sets input provided")
    elif not att_rows:
        for cid in ("AT-02", "AT-03"):
            skip(cid, "attribution_setting not present in the ad-set input — "
                      f"re-pull per {_RAW_PULLS_DOC} / re-export with the "
                      "Attribution setting column")
    elif att_spend <= 0:
        for cid in ("AT-02", "AT-03"):
            skip(cid, "no spend on ad sets carrying attribution_setting")
    else:
        view_rows = [r for r in att_rows
                     if "1d_view" in str(r["attribution_setting"]).casefold()]
        v_share = sum(_spend(r) for r in view_rows) / att_spend * 100.0
        add("AT-02", _band(v_share, AT02_LO, AT02_HI, False),
            f"{v_share:.1f}% of ad-set spend on attribution containing 1d_view "
            f"({len(view_rows)} of {len(att_rows)} ad sets; {aset_win})")
        click_rows = [r for r in att_rows
                      if str(r["attribution_setting"]).strip().casefold()
                      == "7d_click"]
        c_share = sum(_spend(r) for r in click_rows) / att_spend * 100.0
        add("AT-03", "PASS" if c_share >= AT03_PASS else "FLAG",
            f"{c_share:.1f}% of ad-set spend on exactly 7d_click attribution "
            f"({len(click_rows)} of {len(att_rows)} ad sets; {aset_win})")
        # AT-01 evidence: spend-weighted attribution distribution.
        dist: dict[str, list] = {}
        for r in att_rows:
            e = dist.setdefault(str(r["attribution_setting"]), [0.0, 0])
            e[0] += _spend(r)
            e[1] += 1
        parts = [f"{k} {v[0] / att_spend * 100:.1f}% ({v[1]} ad sets)"
                 for k, v in sorted(dist.items(), key=lambda x: (-x[1][0], x[0]))]
        evidence["AT-01"] = {"observed": "Attribution-setting spend mix: "
                                         + ", ".join(parts) + f" ({aset_win})."}

    # ---- CR-03 — video hold-through (P100/P25) -----------------------------
    if ad_rows is None:
        skip("CR-03", "no ads input provided")
    else:
        vid = [r for r in ads if (_f(r, "video_p25") or 0.0) > 0]
        p25 = sum(_f(r, "video_p25") for r in vid)
        p100 = sum(_f(r, "video_p100") or 0.0 for r in vid)
        if p25 < CR03_MIN_P25:
            skip("CR-03", f"only {p25:,.0f} P25 video views in {ad_win} — below "
                          f"the {int(CR03_MIN_P25)}-view floor for a stable "
                          "hold-through rate")
        else:
            h = p100 / p25 * 100.0
            add("CR-03", "PASS" if h >= CR03_PASS else "FLAG",
                f"Hold-through {h:.1f}% ({p100:,.0f} P100 / {p25:,.0f} P25 "
                f"across {len(vid)} video ads; {ad_win})")

    # ---- CR-04 — CTR-Link (scored) / all-click CTR (evidence only) ---------
    cr04_value = None
    if ad_rows is None:
        skip("CR-04", "no ads input provided")
    else:
        link_rows = [r for r in ads if r.get("link_clicks") is not None
                     and (_f(r, "impressions") or 0.0) > 0]
        both = [r for r in ads if r.get("impressions") is not None
                and r.get("clicks") is not None]
        impr_all = sum(_f(r, "impressions") for r in both)
        clicks_all = sum(_f(r, "clicks") for r in both)
        allclick = clicks_all / impr_all * 100.0 if impr_all > 0 else None
        if link_rows and bm == "Ecommerce":
            li = sum(_f(r, "link_clicks") for r in link_rows)
            im = sum(_f(r, "impressions") for r in link_rows)
            cr04_value = li / im * 100.0
            obs = (f"CTR-Link {cr04_value:.2f}% ({li:,.0f} link clicks / "
                   f"{im:,.0f} impressions across {len(link_rows)} ads; {ad_win})")
            n_impr = sum(1 for r in ads if (_f(r, "impressions") or 0.0) > 0)
            if len(link_rows) < n_impr:
                obs += (f" — link clicks present on {len(link_rows)} of "
                        f"{n_impr} ads with impressions")
            add("CR-04", _band(cr04_value, CR04_FLAG, CR04_PASS, True), obs)
        else:
            if bm != "Ecommerce":
                reason = ("business_model is Lead Gen — the CTR-Link benchmark "
                          "applies to Ecommerce prospecting")
            else:
                reason = ("link clicks not present (raw API path — "
                          "cost_per_action_type is not usable); the manual CSV "
                          "export path unlocks scoring")
            skip("CR-04", reason)
            ev_bits = []
            if allclick is not None:
                ev_bits.append(f"All-click CTR {allclick:.3f}% "
                               f"({clicks_all:,.0f} clicks / {impr_all:,.0f} "
                               f"impressions across {len(both)} ads; {ad_win}) — "
                               "all-click (not link); not scored against the "
                               "link benchmark.")
            if link_rows and bm != "Ecommerce":
                li = sum(_f(r, "link_clicks") for r in link_rows)
                im = sum(_f(r, "impressions") for r in link_rows)
                ev_bits.append(f"CTR-Link {li / im * 100.0:.2f}% over "
                               f"{len(link_rows)} ads (not scored: Lead Gen).")
            if ev_bits:
                evidence["CR-04"] = {"observed": " ".join(ev_bits)}

    # ---- CR-06 — top-5 ad spend concentration (L90) -------------------------
    cr06_share = None
    if ad_rows is None:
        skip("CR-06", "no ads input provided")
    else:
        tot_ad_spend = sum(_spend(r) for r in ads)
        if tot_ad_spend <= 0:
            skip("CR-06", "no ad spend in the input")
        else:
            top5 = sum(sorted((_spend(r) for r in ads), reverse=True)[:5])
            cr06_share = top5 / tot_ad_spend * 100.0
            obs = (f"Top-5 ads {cr06_share:.1f}% of ad spend ({top5:,.2f} of "
                   f"{tot_ad_spend:,.2f} across {len(ads)} ads; {ad_win})")
            if len(ads) < 6:
                obs += " — fewer than 6 ads, top-5 share is trivially high"
            add("CR-06", _band(cr06_share, CR06_FLAG, CR06_FAIL, False), obs)

    # ---- CR-07 — spend-weighted ad-set frequency ----------------------------
    cr07_value = cr07_win = None
    cr07_n = 0
    freq_rows = adset7_rows if adset7_rows is not None else adset_rows
    if freq_rows is None:
        skip("CR-07", "no ad-set input provided (frequency is scored per ad set)")
    else:
        rows = [r for r in freq_rows
                if r.get("frequency") is not None and _spend(r) > 0]
        f_win, f_days = _win(freq_rows)
        if not rows:
            skip("CR-07", "no ad-set rows carry both spend and frequency — "
                          f"re-pull per {_RAW_PULLS_DOC} / re-export with the "
                          "Frequency column")
        else:
            fv = wavg([(_spend(r), _f(r, "frequency")) for r in rows])
            cr07_value, cr07_win, cr07_n = fv, f_win, len(rows)
            short = f_days is not None and f_days <= CR07_SHORT_WINDOW_DAYS
            if short:
                result = _band(fv, CR07_FLAG, CR07_FAIL, False)
                obs = (f"Spend-weighted ad-set frequency {fv:.2f} over "
                       f"{len(rows)} ad sets ({f_win}, {f_days}-day window)")
            else:
                result = "PASS" if fv < CR07_FLAG else "FLAG"
                days_label = (f"{f_days}-day window" if f_days is not None
                              else "window length unknown")
                obs = (f"Spend-weighted ad-set frequency {fv:.2f} over "
                       f"{len(rows)} ad sets ({f_win}, {days_label}) — window "
                       f">{CR07_SHORT_WINDOW_DAYS} days: PASS-only mode (FLAG "
                       "ceiling, never FAIL; a 7-day pull unlocks the full bands)")
            add("CR-07", result, obs)

    # ---- CR-08 — creative refresh cadence (raw path only) -------------------
    if ad_rows is None:
        skip("CR-08", "no ads input provided")
    else:
        created = [r for r in ads if _iso(r.get("created_time")) is not None]
        if not created:
            skip("CR-08", "created_time not present in the ads input (manual "
                          "CSV path) — refresh cadence needs the raw pull "
                          f"({_RAW_PULLS_DOC})")
        else:
            has_status = any("effective_status" in r for r in ads)
            act = [r for r in created if not has_status or _active(r)]
            if not act:
                skip("CR-08", "no ACTIVE ads carry created_time")
            else:
                ref, ref_src = _ref_date(ads, generated_for_date)
                if ref is None:
                    skip("CR-08", "no reference date — generated_for_date absent "
                                  "and the ad rows carry no date_stop")
                else:
                    newest = max(_iso(r["created_time"]) for r in act)
                    days = (ref - newest).days
                    if days <= CR08_PASS_DAYS:
                        result = "PASS"
                    elif days <= CR08_FLAG_DAYS:
                        result = "FLAG"
                    else:
                        result = "FAIL"
                    obs = (f"Newest ACTIVE ad created {newest.isoformat()} — "
                           f"{days} days before {ref.isoformat()} ({ref_src}; "
                           f"{len(act)} active ads of {len(ads)})")
                    if not has_status:
                        obs += (" — delivery status not in input; all ads "
                                "considered")
                    add("CR-08", result, obs)

    # ---- DI-01 — dataset/pixel exists & active ------------------------------
    if datasets is None:
        skip("DI-01", "no datasets input provided (optional pull — see "
                      f"{_RAW_PULLS_DOC})")
    else:
        uniq, seen = [], set()
        for d in datasets or []:
            if not isinstance(d, dict):
                continue
            key = str(d.get("dataset_id") or d.get("id") or "")
            if key:
                if key in seen:
                    continue
                seen.add(key)
            uniq.append(d)
        active = [d for d in uniq if d.get("is_active")]

        def _fired(d):
            for k in ("last_fired_time", "server_last_fired_time"):
                m = re.match(r"^\s*(\d{4})", str(d.get(k) or ""))
                if m and int(m.group(1)) > 1970:  # epoch-zero = never fired
                    return True
            return False

        never = sorted(str(d.get("name") or d.get("dataset_id") or "?")
                       for d in active if not _fired(d))
        obs = f"{len(active)} of {len(uniq)} unique datasets active"
        if never:
            obs += (f" — {len(never)} active dataset(s) never fired: "
                    f"{_names(never)}")
        add("DI-01", "PASS" if active else "FAIL", obs)

    # ---- DI-04 — event match quality (EMQ) ----------------------------------
    if dataset_quality is None:
        skip("DI-04", "no dataset-quality input provided (optional pull — see "
                      f"{_RAW_PULLS_DOC})")
    else:
        event = "Purchase" if bm == "Ecommerce" else "Lead"
        scores: list[tuple] = []
        avail: set[str] = set()
        dq = dataset_quality if isinstance(dataset_quality, dict) else {}
        for channel in sorted(dq):
            events = dq[channel]
            if not isinstance(events, list):
                continue
            for e in events:
                if not isinstance(e, dict):
                    continue
                name = str(e.get("event_name") or "")
                if name:
                    avail.add(name)
                if name != event:
                    continue
                emq = e.get("event_match_quality")
                v = emq.get("composite_score") if isinstance(emq, dict) else None
                try:
                    v = float(v)
                except (TypeError, ValueError):
                    v = None
                if v is not None:
                    scores.append((v, str(channel)))
        if not scores:
            skip("DI-04", f"event {event!r} not in the dataset-quality input "
                          f"({bm} primary event; available events: "
                          + (", ".join(sorted(avail)) or "none") + ")")
        else:
            v, _ch = max(scores)
            channels = sorted({c for _, c in scores})
            add("DI-04", _band(v, DI04_FLAG, DI04_PASS, True),
                f"EMQ ({event}) composite {v:.1f} — max across "
                f"{len(channels)} channel(s): {', '.join(channels)} "
                f"({bm} primary event)")

    # ---- Category-B evidence (campaigns) ------------------------------------
    # Median cost-per-result per indicator (results are objective-relative:
    # CPR is only comparable within one indicator).
    cpr_groups: dict[str, list] = {}
    for r in spenders:
        res = _f(r, "results")
        if res and res > 0:
            ind = r.get("results_indicator") or "unlabeled"
            cpr_groups.setdefault(ind, []).append(_spend(r) / res)
    med_by_ind = {ind: _median(vals) for ind, vals in sorted(cpr_groups.items())}

    # AR-07 — legacy campaigns still spending.
    if campaign_rows is not None and spenders:
        ref, _src = _ref_date(camps, generated_for_date)
        dated = [(r, _iso(r.get("created_time"))) for r in spenders]
        dated = [(r, d) for r, d in dated if d is not None]
        if ref is not None and dated:
            legacy = sorted(((r, d) for r, d in dated
                             if (ref - d).days > AR07_LEGACY_DAYS),
                            key=lambda t: (-_spend(t[0]), t[0].get("name", "")))
            if legacy:
                labels = []
                for r, d in legacy:
                    bit = (f"{r.get('name', '')} (created {d.isoformat()}, "
                           f"spend {_spend(r):,.2f}")
                    res = _f(r, "results")
                    ind = r.get("results_indicator") or "unlabeled"
                    med = med_by_ind.get(ind)
                    if res and res > 0 and med:
                        bit += (f", CPR {_spend(r) / res:,.2f} vs {med:,.2f} "
                                f"median for {ind}")
                    labels.append(bit + ")")
                evidence["AR-07"] = {"observed":
                    f"{len(legacy)} of {len(dated)} spending campaigns created "
                    f">{AR07_LEGACY_DAYS} days before {ref.isoformat()}: "
                    + _names(labels) + f" ({camp_win})."}
            else:
                oldest = min(d for _, d in dated)
                evidence["AR-07"] = {"observed":
                    f"No spending campaign is older than {AR07_LEGACY_DAYS} "
                    f"days (oldest created {oldest.isoformat()}, reference "
                    f"{ref.isoformat()}; {len(dated)} dated campaigns; "
                    f"{camp_win})."}

    # BP-01 — budget mode on >=10%-spend campaigns (both levels).
    if campaign_rows is not None and total_camp_spend > 0:
        adsets_by_camp: dict[str, list] = {}
        for a in asets:
            if a.get("campaign_id"):
                adsets_by_camp.setdefault(str(a["campaign_id"]), []).append(a)
        hi = sorted((r for r in spenders
                     if _spend(r) / total_camp_spend * 100.0 >= BP02_SPEND_SHARE),
                    key=lambda r: (-_spend(r), r.get("name", "")))
        if hi:
            labels = []
            for r in hi:
                if r.get("daily_budget") is not None:
                    mode = "campaign daily"
                elif r.get("lifetime_budget") is not None:
                    mode = "campaign lifetime"
                else:
                    linked = adsets_by_camp.get(str(r.get("id") or ""), [])
                    if any(a.get("daily_budget") is not None for a in linked):
                        mode = "ad-set daily"
                    elif any(a.get("lifetime_budget") is not None
                             for a in linked):
                        mode = "ad-set lifetime"
                    else:
                        mode = "budget not returned"
                share = _spend(r) / total_camp_spend * 100.0
                labels.append(f"{r.get('name', '')} — {mode} "
                              f"({share:.0f}% of spend)")
            evidence["BP-01"] = {"observed":
                "Budget mode on campaigns with >=10% of spend: "
                + "; ".join(labels) + f" ({camp_win})."}

    # BP-03 — efficient (cheap-CPR) but small campaigns, within the largest
    # homogeneous indicator group.
    if campaign_rows is not None and cpr_groups and total_camp_spend > 0:
        ind = sorted(cpr_groups, key=lambda k: (-len(cpr_groups[k]), k))[0]
        grp = [r for r in spenders
               if (r.get("results_indicator") or "unlabeled") == ind
               and (_f(r, "results") or 0.0) > 0]
        med = med_by_ind.get(ind)
        if med and len(grp) >= 3:
            cheap_small = sorted(
                (r for r in grp
                 if _spend(r) / (_f(r, "results") or 1.0) < BP03_CPR_RATIO * med
                 and _spend(r) / total_camp_spend * 100.0 < BP03_SMALL_SHARE),
                key=lambda r: (-_spend(r), r.get("name", "")))
            if cheap_small:
                labels = [f"{r.get('name', '')} (CPR "
                          f"{_spend(r) / _f(r, 'results'):,.2f}, "
                          f"{_spend(r) / total_camp_spend * 100.0:.1f}% of spend)"
                          for r in cheap_small]
                body = (f"{len(cheap_small)} campaign(s) with CPR <"
                        f"{BP03_CPR_RATIO:g}x the median and <"
                        f"{BP03_SMALL_SHARE:.0f}% of spend — scale candidates: "
                        + _names(labels))
            else:
                body = (f"No campaign combines CPR <{BP03_CPR_RATIO:g}x the "
                        f"median with <{BP03_SMALL_SHARE:.0f}% of spend")
            evidence["BP-03"] = {"observed":
                f"Within {ind} campaigns (n={len(grp)}, median CPR "
                f"{med:,.2f}): {body} ({camp_win})."}

    # BP-04 — spend mix by bid strategy.
    if campaign_rows is not None and total_camp_spend > 0:
        mix2: dict[str, float] = {}
        for r in spenders:
            key = r.get("bid_strategy") or "not returned"
            mix2[key] = mix2.get(key, 0.0) + _spend(r)
        parts = [f"{k} {v / total_camp_spend * 100:.0f}%"
                 for k, v in sorted(mix2.items(), key=lambda x: (-x[1], x[0]))]
        evidence["BP-04"] = {"observed": "Campaign spend by bid strategy: "
                                         + ", ".join(parts) + f" ({camp_win})."}

    # CR-02 — ThruPlay (hold) rate over video ads.
    if ad_rows is not None:
        vids = [r for r in ads if r.get("thruplay") is not None
                and (_f(r, "impressions") or 0.0) > 0]
        if vids:
            tp = sum(_f(r, "thruplay") for r in vids)
            im = sum(_f(r, "impressions") for r in vids)
            evidence["CR-02"] = {"observed":
                f"ThruPlay rate {tp / im * 100.0:.2f}% ({tp:,.0f} ThruPlays / "
                f"{im:,.0f} impressions across {len(vids)} video ads; {ad_win}) "
                "— single-window level; a sharp-drop trend needs a "
                "time-series pull."}

    # CR-05 — delivering-ad count (ads != concepts).
    if ad_rows is not None and ads:
        has_status = any("effective_status" in r for r in ads)
        delivering = [r for r in ads
                      if (not has_status or _active(r))
                      and ((_f(r, "impressions") or 0.0) > 0 or _spend(r) > 0)]
        obs = f"{len(delivering)} delivering ads in {ad_win}"
        if not has_status:
            obs += " (spend/impressions > 0 used as the delivery proxy — no status in input)"
        obs += (" — ads are not distinct creative concepts; concept count "
                "needs creative inspection.")
        evidence["CR-05"] = {"observed": obs}

    # CR-01 — creative-signals counts (thumb-stop itself is not exposed).
    fatigued_kpi = None
    if creative_signals:
        s = creative_signals.get("summary") or {}
        z = creative_signals.get("zones") or {}
        b = creative_signals.get("baselines") or {}
        cs_win = creative_signals.get("window") or "window unavailable"
        n_cs = int(b.get("n_ads") or 0)
        below = int(s.get("below_floor") or 0)
        evidence["CR-01"] = {"observed":
            f"Thumb-stop (3s) is not exposed — nearest machine signals "
            f"({cs_win}): fatigue saturated {int(s.get('saturated') or 0)} / "
            f"watch {int(s.get('watch') or 0)} / fresh "
            f"{int(s.get('fresh') or 0)} ({below} below the impression floor); "
            f"{int(s.get('high_saturation') or 0)} ads with reach-saturation "
            f">0.5; ad-set frequency zones under {int(z.get('under') or 0)} / "
            f"effective {int(z.get('effective') or 0)} / oversaturated "
            f"{int(z.get('oversaturated') or 0)}."}
        fatigued_kpi = {
            "metric": "Fatigued Ads", "value": int(s.get("saturated") or 0),
            "unit": "", "benchmark": "0", "flag": "N/A",
            "notes": (f"fatigue >0.66 among {n_cs - below} scored of {n_cs} "
                      f"ads (watch {int(s.get('watch') or 0)}); {cs_win}; "
                      "informational (machine-scored)")}

    # ---- KPI rows (fixed order, stable metric names) -------------------------
    kpis: list[dict] = []
    if campaign_rows is not None and camps:
        base_rows, base_level, base_win = camps, "campaigns", camp_win
    elif adset_rows is not None and asets:
        base_rows, base_level, base_win = asets, "ad sets", aset_win
    elif ad_rows is not None and ads:
        base_rows, base_level, base_win = ads, "ads", ad_win
    else:
        base_rows, base_level, base_win = [], "", ""

    if base_rows:
        tot_spend = sum(_spend(r) for r in base_rows)
        kpis.append({"metric": "Spend", "value": round(tot_spend, 2),
                     "unit": "", "benchmark": "", "flag": "N/A",
                     "notes": f"account currency, {len(base_rows)} "
                              f"{base_level}, {base_win} (machine-scored)"})
        with_res = [r for r in base_rows if r.get("results") is not None]
        if with_res:
            inds = sorted({r.get("results_indicator") or "unlabeled"
                           for r in with_res})
            conv_rows = [r for r in base_rows
                         if r.get("conv_results") is not None]
            conv_tot = sum(_f(r, "conv_results") for r in conv_rows)
            if len(inds) == 1:
                tot_res = sum(_f(r, "results") for r in with_res)
                caveat = f"indicator: {inds[0]}"
            elif conv_tot > 0:
                # Mixed objectives: a raw sum (Reach + video views + leads)
                # would put a meaningless headline number in the scorecard —
                # report conversion-like results only.
                tot_res = conv_tot
                conv_inds = sorted({r.get("results_indicator") or "unlabeled"
                                    for r in conv_rows})
                excl = sorted(set(inds) - set(conv_inds))
                caveat = ("conversion-like results only ("
                          + ", ".join(conv_inds)
                          + "); excluded objective-relative indicators: "
                          + ", ".join(excl))
            else:
                tot_res = sum(_f(r, "results") for r in with_res)
                caveat = ("MIXED indicators (objective-relative, "
                          "not comparable): " + ", ".join(inds))
            kpis.append({"metric": "Results", "value": round(tot_res, 0),
                         "unit": "", "benchmark": "", "flag": "N/A",
                         "notes": f"{caveat}; {base_win} (machine-scored)"})
            if tot_res > 0 and tot_spend > 0:
                kpis.append({"metric": "Cost per Result",
                             "value": round(tot_spend / tot_res, 2),
                             "unit": "", "benchmark": "", "flag": "N/A",
                             "notes": f"blended, account currency; {caveat}; "
                                      f"{base_win} (machine-scored)"})

    rate_rows, rate_level, rate_win = ((ads, "ads", ad_win)
                                       if ad_rows is not None and ads
                                       else (base_rows, base_level, base_win))
    both = [r for r in rate_rows if r.get("impressions") is not None
            and r.get("clicks") is not None]
    impr = sum(_f(r, "impressions") for r in both)
    if impr > 0:
        ctr = sum(_f(r, "clicks") for r in both) / impr * 100.0
        kpis.append({"metric": "CTR (all-click)", "value": round(ctr, 3),
                     "unit": "%", "benchmark": "", "flag": "N/A",
                     "notes": f"all-click (not link), {len(both)} {rate_level}, "
                              f"{rate_win} (machine-scored)"})
    spendable = [r for r in rate_rows if r.get("impressions") is not None
                 and r.get("spend") is not None]
    impr_s = sum(_f(r, "impressions") for r in spendable)
    if impr_s > 0:
        cpm = sum(_spend(r) for r in spendable) / impr_s * 1000.0
        kpis.append({"metric": "CPM", "value": round(cpm, 2),
                     "unit": "", "benchmark": "", "flag": "N/A",
                     "notes": f"account currency per 1,000 impressions, "
                              f"{len(spendable)} {rate_level}, {rate_win} "
                              "(machine-scored)"})
    if "CR-07" in checks and cr07_value is not None:
        kpis.append({"metric": "Frequency (spend-wtd)",
                     "value": round(cr07_value, 2), "unit": "",
                     "benchmark": "<3", "flag": checks["CR-07"]["result"],
                     "notes": f"{cr07_n} ad sets, {cr07_win} (machine-scored)"})
    if "CR-06" in checks and cr06_share is not None:
        kpis.append({"metric": "Top-5 Ad Spend Share",
                     "value": round(cr06_share, 1), "unit": "%",
                     "benchmark": "<50%", "flag": checks["CR-06"]["result"],
                     "notes": f"{len(ads)} ads, {ad_win} (machine-scored)"})
    if fatigued_kpi is not None:
        kpis.append(fatigued_kpi)
    if "CR-04" in checks and cr04_value is not None:
        kpis.append({"metric": "CTR-Link", "value": round(cr04_value, 2),
                     "unit": "%", "benchmark": ">=0.8%",
                     "flag": checks["CR-04"]["result"],
                     "notes": f"Ecommerce prospecting benchmark, {ad_win} "
                              "(machine-scored)"})

    return {"source": "rows", "business_model": bm,
            "checks": checks, "evidence": evidence, "kpis": kpis,
            "skipped": sorted(skipped, key=lambda s: s["id"]),
            "notes": sorted(notes)}


# ── merge into the model-authored payload ────────────────────────────────────

def merge_into_findings(payload: dict, prescore: dict | None
                        ) -> tuple[dict, dict | None, list[str]]:
    """Enforce machine-scored results over the flat meta payload (pure; deep copy).

    Category A: overwrite flag/observed/severity on the FIRST check row whose
    id matches (canonical casing via audit_model SEV_CANON/FLAG_CANON so
    build_audit_xlsx.validate_and_normalize stays quiet), injecting a full
    check row (category from the SECTIONS prefix map, framework name/expected,
    empty recommendation) when the model omitted it. Category B: fill observed
    only when blank. KPI rows: replace by casefolded metric name in
    payload["kpis"] (created if absent), append unmatched.

    NOTE the name is historical: this enforces machine results over the
    payload's checks / observed / kpis. It does NOT rewrite payload["findings"]
    — those stay model-authored. It does report every check it MOVED whose
    narrative no longer follows, in both directions, as
    block["unreconciled"] = [{id, result, reason}] (reason "missing": scored
    FAIL/FLAG with no finding covering it; reason "cleared": scored PASS/N-A
    while a finding still argues it) plus a WARNING log line each, so a moved
    score never ships beside stale prose.

    Returns (merged_payload, model_block, stderr_log_lines)."""
    if prescore is None:
        return payload, None, []
    merged = copy.deepcopy(payload)
    checks_list = merged.setdefault("checks", [])
    applied, injected, evidence_filled, kpis_replaced = [], [], [], []
    corrected, log = [], []
    landed: dict = {}   # cid -> canonical machine result, filled in the loop below

    def find_check(cid):
        for c in checks_list:
            if isinstance(c, dict) and str(c.get("id", "")).strip() == cid:
                return c
        return None

    def insert_pos(cat):
        """End of the category's block: before the first later-order category."""
        order = _CAT_ORDER.get(cat, 99)
        for i, c in enumerate(checks_list):
            c_cat = str(c.get("category", "") or "") if isinstance(c, dict) else ""
            if _CAT_ORDER.get(c_cat, 99) > order:
                return i
        return len(checks_list)

    for cid in sorted(prescore.get("checks", {})):
        p = prescore["checks"][cid]
        sev_raw = str(p.get("severity", "") or "").strip()
        sev = SEV_CANON.get(sev_raw.lower(), sev_raw)
        res_raw = str(p.get("result", "") or "").strip()
        res = FLAG_CANON.get(res_raw.lower(), res_raw)
        row = find_check(cid)
        if row is None:
            rule = CHECK_RULES.get(cid, {})
            cat = _CAT_BY_PREFIX.get(cid.split("-")[0], "")
            checks_list.insert(insert_pos(cat), {
                "id": cid, "category": cat, "name": rule.get("name", cid),
                "severity": sev, "flag": res, "observed": p["observed"],
                "expected": rule.get("expected", ""), "recommendation": ""})
            injected.append(cid)
            log.append(f"prescore: {cid} injected as {res} ({p['observed']})")
        else:
            old_raw = str(row.get("flag", "") or "").strip()
            old = FLAG_CANON.get(old_raw.lower(), old_raw)
            if old and old != res:
                corrected.append({"id": cid, "from": old, "to": res})
                log.append(f"prescore: {cid} {old}->{res} ({p['observed']})")
            row["flag"] = res
            row["observed"] = p["observed"]
            row["severity"] = sev
        applied.append(cid)
        # Canonical landing value, captured where it is already computed —
        # re-deriving it later from prescore["checks"] invited a second, subtly
        # different canonicalization of the same field.
        landed[cid] = res

    for cid in sorted(prescore.get("evidence", {})):
        row = find_check(cid)
        if row is not None and not str(row.get("observed", "") or "").strip():
            row["observed"] = prescore["evidence"][cid]["observed"]
            evidence_filled.append(cid)

    if prescore.get("kpis"):
        kpi_list = merged.setdefault("kpis", [])
        by_name = {str(k.get("metric", "")).casefold(): i
                   for i, k in enumerate(kpi_list)}
        for row in prescore["kpis"]:
            key = str(row["metric"]).casefold()
            if key in by_name:
                kpi_list[by_name[key]] = dict(row)
                kpis_replaced.append(row["metric"])
            else:
                kpi_list.append(dict(row))

    # --- reconcile the NARRATIVE against the corrections -----------------------
    # The score is machine-enforced, but findings[] — the ICE-ranked roadmap the
    # advisor reads aloud (SKILL.md step 8: "the top 3-5 quick wins") — is
    # model-authored and nothing here rewrites it. So a check corrected
    # PASS->FAIL moves the Health Score while the prose beside it still argues
    # the overturned verdict, and an injected FAIL can enter the deliverable
    # with no finding at all. We do NOT fabricate a finding (that judgment is
    # the model's); we surface the gap loudly so it cannot pass unnoticed.
    # Findings carry no check-id field, so match on the id appearing anywhere in
    # the finding's own text — deliberately generous: a false "reconciled" is
    # quiet, a false "unreconciled" is merely a nudge.
    def _mentions(cid):
        for f in merged.get("findings", []) or []:
            if not isinstance(f, dict):
                continue
            blob = " ".join(str(f.get(k, "")) for k in
                            ("title", "evidence", "recommendation", "id"))
            if cid in blob:
                return True
        return False

    # Drift runs BOTH ways, and only reporting one direction is half a feature:
    #   missing — machine says FAIL/FLAG and no finding covers it. The score
    #             dropped; the roadmap is silent about why.
    #   cleared — machine says PASS/N-A and a finding still argues the problem.
    #             The score rose; the roadmap still tells the client to fix
    #             something the data says is fine. Real and routine: a live run
    #             logs `AR-02 FAIL->PASS` and `AR-01 FLAG->PASS`.
    # Only checks the machine actually MOVED (corrected) or added (injected) are
    # candidates — an untouched check agreeing with its finding is not drift.
    changed = {c["id"] for c in corrected} | set(injected)
    unreconciled = []
    for cid in sorted(changed):
        res = landed.get(cid, "")
        mentioned = _mentions(cid)
        if res in ("FAIL", "FLAG") and not mentioned:
            unreconciled.append({"id": cid, "result": res, "reason": "missing"})
            log.append(f"prescore: WARNING {cid} machine-scored {res} but no "
                       "finding mentions it — the score moved, the narrative "
                       "did not")
        elif res not in ("FAIL", "FLAG") and mentioned:
            unreconciled.append({"id": cid, "result": res, "reason": "cleared"})
            log.append(f"prescore: WARNING {cid} machine-scored {res} but a "
                       "finding still argues it — drop or amend that finding, "
                       "or the report tells the client to fix a non-problem")

    block = {"applied": sorted(applied), "corrected": corrected,
             "injected": sorted(injected),
             "evidence_filled": sorted(evidence_filled),
             "kpis_replaced": sorted(kpis_replaced),
             "unreconciled": unreconciled,
             "skipped": prescore.get("skipped", []),
             "notes": prescore.get("notes", [])}
    return merged, block, log
