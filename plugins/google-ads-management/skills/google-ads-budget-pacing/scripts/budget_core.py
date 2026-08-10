#!/usr/bin/env python3
"""Budget & pacing — model / single source of truth (stdlib only).

Every renderer (md, html, xlsx) consumes this model via the shared toolkit
(`_shared/render`). The findings-JSON contract is authoritative in
`references/budget-pacing-report.md`.

One row per campaign, bucketed for action (priority order):
  Kill        — 0 conversions (30d) AND spend >= kill_multiple x target CPA (the 3x rule)
  Raise       — budget-lost IS > flag AND converting at/under target CPA (constrained winner;
                <= +20% per step)
  Rank-limited— rank-lost IS > flag (a quality/bid problem — NOT a budget problem)
  Low budget  — daily budget < min_budget_multiple x target CPA (unstable Smart Bidding)
  OK          — none of the above
Account-level pacing (MTD spend vs the goal x elapsed/elapsed-in-month) is computed in the
summary and driven by the tunable monthly goal. Campaigns with no daily budget are kept with
status="no_budget" and never bucketed (never dropped).

Deepened (HM-535) with two `_shared/analytics.py`-driven layers, still one row per
campaign, still no-row-loss:
  - Spend CONCENTRATION across all campaigns (top-3 share / HHI / effective-N over
    window `cost`), folded into `summary` (`conc_*` keys).
  - A per-campaign PACE PRE-SCORER: `campaign_pace_ratio = mtd_spend / (daily_budget
    x days_elapsed)` (how the campaign's own MTD spend compares to its own daily
    budget's implied pace), a declarative-flag severity score (`pace_score`, via
    `analytics.signals` + `analytics.pre_score`), an over/under/on-track/n/a
    `pace_verdict`, and a high/low `pace_confidence` (>=7 days elapsed AND MTD >=
    target CPA — enough data to trust the signal).
Both are pure functions of the row set + resolved params, mirrored verbatim in
`budget_spec.JS_KERNEL` (splices `analytics.JS_MIRROR`) and `budget_xlsx_spec.XLSX`
formulas — the Node<->Python parity gate covers both.

The `advisor` block turns the pace pre-score into a prioritized reallocation
shortlist: `fund` (Raise-bucket campaigns, capped +20%/step) and `trim` (Kill-bucket
campaigns UNION over-pacing campaigns whose CPA is above target) — see
`build_advisor`.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

GOAL_LADDER_STEPS = 8  # sensitivity strip resolution around the monthly goal

DEFAULT_PARAMS = {
    "monthly_goal": 0.0,          # account monthly spend goal (0 => pacing N/A)
    "target_cpa": 50.0,           # target cost / conversion
    "budget_lost_is_flag": 0.10,  # budget-lost IS above this = constrained
    "kill_multiple": 3.0,         # spend >= this x target CPA with 0 conv = kill
    "min_budget_multiple": 5.0,   # daily budget < this x target CPA = unstable
    "pacing_tolerance": 0.15,     # +/- band for on-track (account AND per-campaign pace)
    "days_elapsed": 0,            # filled from meta
    "days_in_month": 30,          # filled from meta
}

# Per-campaign pace pre-scorer: declarative flags (analytics.signals) and their
# severity weights (analytics.pre_score). Constants, not tunable params — mirrored
# verbatim (as literals) in budget_spec.JS_KERNEL's `paceRules`/`PACE_FLAG_WEIGHTS`
# and in budget_xlsx_spec's "Pace score" formula.
PACE_FLAG_WEIGHTS = {"over_pace": 1.0, "under_pace": 1.0, "constrained": 1.5, "zero_conv": 2.0}


class FindingsError(ValueError):
    """Raised when the findings JSON is missing/invalid."""


# Control-total contract shared with scripts/assemble_findings.py: per findings
# array, the numeric fields whose sums are embedded as meta.reconciliation and
# re-verified here on every load. Catches transcription drift and hand-edits.
RECONCILE_ARRAYS = {
    "campaigns": ["cost", "mtd_spend", "conversions", "daily_budget",
                  "search_budget_lost_is", "search_rank_lost_is"],
}


def load_findings(path: str) -> dict:
    try:
        data = json.loads(Path(path).read_text())
    except FileNotFoundError as e:
        raise FindingsError(f"findings file not found: {path}") from e
    except json.JSONDecodeError as e:
        raise FindingsError(f"findings file is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise FindingsError("findings JSON must be an object")
    if not isinstance(data.get("campaigns"), list):
        raise FindingsError("findings JSON missing required array 'campaigns'")
    if (data.get("meta") or {}).get("reconciliation"):
        try:
            import reconcile  # lazy: _shared module, on sys.path via the builders/tests
        except ImportError as e:
            raise FindingsError(
                "findings carry reconciliation totals but the _shared toolkit is not "
                "on sys.path — run via build_budget_report.py, or add the plugin's "
                "_shared/ to sys.path before loading") from e
        try:
            reconcile.verify(data, RECONCILE_ARRAYS)
        except reconcile.ReconciliationError as e:
            raise FindingsError(str(e)) from e
    return data


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _opt(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _r2(x):
    """Round half-up to 2dp, matching JS Math.round(x*100)/100."""
    return math.floor(float(x) * 100 + 0.5) / 100


def _r1(x):
    """Round half-up to 1dp — same algorithm as _r2/analytics._round_half_up."""
    return math.floor(float(x) * 10 + 0.5) / 10


def _analytics():
    """Lazy-import the shared analytics primitives (mirrors the `reconcile` lazy
    import above): _shared/ must be on sys.path — true via every current caller
    (build_budget_report.py, assemble_from_csv.py, tests/test_budget.py)."""
    try:
        import analytics
    except ImportError as e:
        raise FindingsError(
            "the _shared toolkit is not on sys.path — run via build_budget_report.py, "
            "or add the plugin's _shared/ to sys.path before loading") from e
    return analytics


def resolve_params(raw: dict | None, meta: dict | None = None) -> dict:
    p = dict(DEFAULT_PARAMS)
    for k, v in (raw or {}).items():
        if v is not None:
            p[k] = v
    meta = meta or {}
    for k in ("days_elapsed", "days_in_month", "monthly_goal"):
        if meta.get(k) is not None:
            p[k] = meta[k]
    return p


def _liveness_note(row: dict) -> str:
    """Conditional-phrasing seam for recently_active rows (HM-603) — the note the
    advisor surfaces so a paused/idle campaign's budget advice is hedged. Empty
    for live (nothing to caveat) and dormant (never a recommendation source).
    Two-band degradation (prior_spend_key=None): the "prior-window only" path is
    unreachable here, so a recently_active row is always either paused-mid-window
    (not enabled, spent) or enabled-but-idle."""
    if row.get("liveness") != "recently_active":
        return ""
    enabled = str(row.get("campaign_status") or "").strip().upper() == "ENABLED"
    cur = _num(row.get("cost"))
    if not enabled and cur > 0:
        return (f"Paused/removed mid-window after spending {cur:,.2f} — "
                "confirm intent before changing budget.")
    if enabled and cur <= 0:
        return ("Enabled but no spend in the window — confirm it should be "
                "running before adjusting budget.")
    return "Spent only in the prior window — confirm intent before changing budget."


def build_rows(campaigns: list, analytics=None) -> list:
    analytics = analytics or _analytics()
    rows = []
    for c in campaigns:
        cost = _num(c.get("cost"))
        conv = _num(c.get("conversions"))
        daily = _opt(c.get("daily_budget"))
        rows.append({
            "campaign_id": c.get("campaign_id"),
            "campaign": c.get("campaign", str(c.get("campaign_id"))),
            "channel": c.get("channel", ""),
            # Raw campaign.status (GAQL enum / UI "Campaign state") — kept under a
            # DISTINCT key from the pipeline "status" (measured/no_budget) so the
            # two never collide. Feeds liveness only.
            "campaign_status": c.get("campaign_status", ""),
            "daily_budget": daily,
            "cost": cost,
            "mtd_spend": _num(c.get("mtd_spend")),
            "conversions": conv,
            "cpa": (cost / conv) if conv else None,
            "budget_lost_is": _opt(c.get("search_budget_lost_is")),
            "rank_lost_is": _opt(c.get("search_rank_lost_is")),
            "status": "measured" if daily is not None else "no_budget",
        })
    # Campaign liveness (HM-603): TWO-BAND-derivable — this skill pulls
    # campaign.status (campaign_status) and current-window spend (cost) but NO
    # prior-*window* spend (mtd_spend is current-month-to-date, not a prior
    # comparable window), so prior_spend_key=None. live/recently_active/dormant
    # are all still reachable; only the "spent only in the prior window" path is
    # unavailable (documented — never invented). Severity/bucketing/pace is gated
    # on live+recently_active; dormant rows stay present-but-tagged (no-row-loss).
    rows = analytics.segment_liveness(rows, status_key="campaign_status",
                                      spend_key="cost", prior_spend_key=None)
    for r in rows:
        r["liveness_note"] = _liveness_note(r)
    rows.sort(key=lambda r: r["cost"], reverse=True)
    return rows


def classify_row(row: dict, params: dict) -> dict:
    # Liveness gate (HM-603): a dormant campaign (not ENABLED, zero spend in the
    # window) is never bucketed — it behaves like the existing non-"measured"
    # early return, staying present-but-tagged liveness="dormant". This is the
    # fix for the self-contradicting "Low budget on a paused campaign" headline.
    if row.get("liveness") == "dormant" or row["status"] != "measured":
        return {"bucket": ""}
    tcpa = params["target_cpa"]
    cost, conv, daily = row["cost"], row["conversions"], row["daily_budget"]
    blis, rlis = row["budget_lost_is"], row["rank_lost_is"]
    if conv == 0 and cost >= params["kill_multiple"] * tcpa:
        return {"bucket": "Kill"}
    if blis is not None and blis > params["budget_lost_is_flag"] and conv > 0 \
            and row["cpa"] is not None and row["cpa"] <= tcpa:
        return {"bucket": "Raise"}
    if rlis is not None and rlis > params["budget_lost_is_flag"]:
        return {"bucket": "Rank-limited"}
    if daily is not None and daily < params["min_budget_multiple"] * tcpa:
        return {"bucket": "Low budget"}
    return {"bucket": "OK"}


def classify(rows: list, params: dict) -> list:
    out = []
    for r in rows:
        rr = dict(r)
        rr.update(classify_row(r, params))
        out.append(rr)
    return out


def _pace_verdict(ratio, tol: float) -> str:
    if ratio is None:
        return "n/a"
    if ratio > 1.0 + tol:
        return "over"
    if ratio < 1.0 - tol:
        return "under"
    return "on track"


def _pace_rules(params: dict) -> list:
    """Declarative flag rules for `analytics.signals` — see the module docstring.
    Mirrored verbatim (as `paceRules(P)`, with `conversions` renamed `conv` to
    match the html-embedded row shape) in budget_spec.JS_KERNEL."""
    return [
        {"id": "over_pace", "key": "campaign_pace_ratio", "op": "gt",
         "value": 1.0 + params["pacing_tolerance"]},
        {"id": "under_pace", "key": "campaign_pace_ratio", "op": "lt",
         "value": 1.0 - params["pacing_tolerance"]},
        {"id": "constrained", "key": "budget_lost_is", "op": "gt",
         "value": params["budget_lost_is_flag"]},
        {"id": "zero_conv", "key": "conversions", "op": "eq", "value": 0},
    ]


def add_pace(rows: list, params: dict, analytics=None) -> list:
    """Per-campaign pace pre-score: campaign_pace_ratio, pace_verdict,
    pace_confidence, pace_flags, pace_score (analytics.signals + pre_score over
    PACE_FLAG_WEIGHTS). Pure addition — every input row's other fields pass
    through unchanged (no-row-loss). Rows without a computable ratio (no daily
    budget, or days_elapsed == 0) get ratio=None, verdict="n/a" — never dropped."""
    analytics = analytics or _analytics()
    tol = params["pacing_tolerance"]
    tcpa = params["target_cpa"]
    de = params["days_elapsed"]
    out = []
    for r in rows:
        rr = dict(r)
        # Liveness gate (HM-603): a dormant campaign never contributes a pace
        # verdict, flag or score — pace is suppressed exactly like the no-budget
        # early-out (ratio None, verdict n/a), so it stays out of the summary's
        # over/under-pace counts and the advisor's trim list while remaining
        # present-but-tagged. Mirrors budget_spec.JS_KERNEL's pace() dormant gate.
        if r.get("liveness") == "dormant":
            rr["campaign_pace_ratio"] = None
            rr["pace_verdict"] = "n/a"
            rr["pace_confidence"] = "low"
            out.append(rr)
            continue
        daily, mtd = r["daily_budget"], r["mtd_spend"]
        ratio = _r2(mtd / (daily * de)) if (daily is not None and daily > 0 and de) else None
        rr["campaign_pace_ratio"] = ratio
        rr["pace_verdict"] = _pace_verdict(ratio, tol)
        rr["pace_confidence"] = "high" if (de >= 7 and mtd >= tcpa) else "low"
        out.append(rr)
    flags = analytics.signals(out, _pace_rules(params))
    for rr, fl in zip(out, flags):
        if rr.get("liveness") == "dormant":
            rr["pace_flags"] = []
            rr["pace_score"] = 0.0
        else:
            rr["pace_flags"] = fl
            rr["pace_score"] = analytics.pre_score({"flags": fl}, PACE_FLAG_WEIGHTS)
    return out


def build_advisor(rows: list, params: dict) -> dict:
    """Reallocation shortlist from the bucketed + paced rows.

    fund — Raise-bucket campaigns (budget-constrained winners), proposed budget
    capped at +20% per step, sorted by budget-lost IS (worst-constrained first).
    trim — Kill-bucket campaigns (the 3x rule) UNION over-pacing campaigns whose
    CPA sits above target (a laggard the pace pre-score just caught, distinct
    from the Kill 3x rule), sorted by window spend (biggest bleed first)."""
    tcpa = params["target_cpa"]
    fund = []
    for r in rows:
        if r.get("bucket") != "Raise":
            continue
        proposed = _r2((r["daily_budget"] or 0.0) * 1.2)
        reason = f"Lost {(r['budget_lost_is'] or 0.0) * 100:.0f}% IS to budget"
        if r["cpa"] is not None:
            reason += f", CPA {r['cpa']:.2f} <= target {tcpa:.2f}"
        fund.append({"campaign": r["campaign"], "daily_budget": r["daily_budget"],
                     "proposed_budget": proposed, "budget_lost_is": r["budget_lost_is"],
                     "cpa": r["cpa"], "pace_verdict": r["pace_verdict"], "reason": reason})
    fund.sort(key=lambda r: r["budget_lost_is"] or 0.0, reverse=True)

    trim = []
    for r in rows:
        if r.get("bucket") == "Kill":
            trim.append({"campaign": r["campaign"], "cost": r["cost"],
                         "conversions": r["conversions"], "source": "kill",
                         "reason": (f"0 conversions, spend {r['cost']:.2f} >= "
                                    f"{params['kill_multiple']:.0f}x target CPA "
                                    f"{tcpa:.2f} (3x rule)")})
        elif (r.get("pace_verdict") == "over" and r.get("cpa") is not None
              and r["cpa"] > tcpa):
            trim.append({"campaign": r["campaign"], "cost": r["cost"],
                         "conversions": r["conversions"], "source": "over_pace",
                         "reason": (f"Over-pacing ({r['campaign_pace_ratio']:.2f}x "
                                    f"implied daily rate) with CPA {r['cpa']:.2f} "
                                    f"above target {tcpa:.2f}")})
    trim.sort(key=lambda r: r["cost"], reverse=True)
    return {"fund": fund, "trim": trim}


def pacing(rows: list, params: dict) -> dict:
    goal = params["monthly_goal"]
    de, dim = params["days_elapsed"], params["days_in_month"]
    mtd = sum(r["mtd_spend"] for r in rows)
    if not goal or not dim:
        return {"monthly_goal": goal, "mtd_spend": _r2(mtd), "expected_mtd": None,
                "pace_ratio": None, "verdict": "n/a"}
    expected = goal * (de / dim)
    ratio = (mtd / expected) if expected else None
    tol = params["pacing_tolerance"]
    if ratio is None:
        verdict = "n/a"
    elif ratio > 1 + tol:
        verdict = "over"
    elif ratio < 1 - tol:
        verdict = "under"
    else:
        verdict = "on track"
    return {"monthly_goal": goal, "mtd_spend": _r2(mtd), "expected_mtd": _r2(expected),
            "pace_ratio": (_r2(ratio) if ratio is not None else None), "verdict": verdict}


def summarize(rows: list, params: dict, analytics=None) -> dict:
    analytics = analytics or _analytics()
    spend = sum(r["cost"] for r in rows)
    conv = sum(r["conversions"] for r in rows)
    buckets = {b: 0 for b in ("Kill", "Raise", "Rank-limited", "Low budget", "OK")}
    for r in rows:
        if r.get("bucket") in buckets:
            buckets[r["bucket"]] += 1
    pace = pacing(rows, params)
    conc = analytics.concentration(rows, "cost", top_n=3)
    over_pace = sum(1 for r in rows if r.get("pace_verdict") == "over")
    under_pace = sum(1 for r in rows if r.get("pace_verdict") == "under")
    off_pace_high_conf = sum(1 for r in rows if r.get("pace_verdict") in ("over", "under")
                             and r.get("pace_confidence") == "high")
    return {
        "campaigns": len(rows),
        "spend": _r2(spend),
        "conversions": _r2(conv),
        "cpa": _r2(spend / conv) if conv else None,
        "kill": buckets["Kill"], "raise_": buckets["Raise"],
        "rank_limited": buckets["Rank-limited"], "low_budget": buckets["Low budget"],
        "ok": buckets["OK"],
        "no_budget": sum(1 for r in rows if r["status"] == "no_budget"),
        "mtd_spend": pace["mtd_spend"], "expected_mtd": pace["expected_mtd"],
        "pace_ratio": pace["pace_ratio"], "pace_verdict": pace["verdict"],
        # Passthrough of the tunable (not derived) — lets the html KPI row show
        # the monthly goal alongside its inline assumption marker (HM-604).
        "monthly_goal": pace["monthly_goal"] or None,
        # Spend concentration (analytics.concentration over window `cost`, top-3).
        "conc_top_share": conc["top_share"], "conc_hhi": conc["hhi"],
        "conc_effective_n": conc["effective_n"],
        "conc_top3_pct": _r1(conc["top_share"] * 100.0),
        # Per-campaign pace pre-score aggregates.
        "over_pace": over_pace, "under_pace": under_pace,
        "off_pace_high_conf": off_pace_high_conf,
    }


def goal_sensitivity(rows: list, params: dict) -> list:
    """Pace ratio/verdict as the monthly goal scales 0.7x..1.3x the current goal."""
    goal = params["monthly_goal"]
    if not goal:
        return []
    out = []
    for i in range(GOAL_LADDER_STEPS):
        factor = 0.7 + i * (0.6 / (GOAL_LADDER_STEPS - 1))
        g = round(goal * factor, 2)
        p = dict(params); p["monthly_goal"] = g
        pc = pacing(rows, p)
        out.append({"monthly_goal": g, "pace_ratio": pc["pace_ratio"], "verdict": pc["verdict"],
                    "is_current": abs(factor - 1.0) < 1e-9})
    return out


def provenance(findings: dict, params: dict) -> dict:
    meta = findings.get("meta") or {}
    return {
        "client_name": meta.get("client_name", ""),
        "account_id": meta.get("account_id", ""),
        "currency": meta.get("currency", ""),
        "window_90d": meta.get("period", ""),
        "window_30d": (f"day {params['days_elapsed']} of {params['days_in_month']}"
                       if params.get("days_in_month") else ""),
        "generated": meta.get("generated", ""),
        # Honest data-source label (HM-534/535 dual-input contract, canonicalized by
        # HM-572): assemble_from_csv.py stamps meta.source="user_csv"; the MCP path
        # (assemble_findings.py) sets none, so this defaults to the canonical "mcp"
        # live-pull token — never presented as unlabeled.
        "source": meta.get("source") or "mcp",
        "params": dict(params),
    }


def compute_model(findings: dict) -> dict:
    analytics = _analytics()
    params = resolve_params(findings.get("params"), findings.get("meta"))
    rows = build_rows(findings["campaigns"], analytics)
    classified = classify(rows, params)
    paced = add_pace(classified, params, analytics)
    return {
        "provenance": provenance(findings, params),
        "params": params,
        "rows": paced,
        "summary": summarize(paced, params, analytics),
        "advisor": build_advisor(paced, params),
        "goal_sensitivity": goal_sensitivity(rows, params),
        # Pass-through so every renderer sees the assembler's meta.assumptions
        # (HM-604 provenance/assumptions contract) and meta.source verbatim —
        # this dict is never re-derived or re-labeled here.
        "meta": dict(findings.get("meta") or {}),
        "_rows": rows,
    }
