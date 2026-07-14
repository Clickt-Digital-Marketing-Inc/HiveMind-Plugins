#!/usr/bin/env python3
"""Competitive-pressure model — own-side WoW IS/CPC deltas + rank-vs-budget
IS-loss attribution, plus (optional) Auction Insights competitor concentration.
Single source of truth; every renderer (md, html, xlsx) imports this module so
the classification logic can never diverge across formats. Stdlib +
`_shared/analytics` only (no openpyxl).

The findings-JSON input contract is documented authoritatively in
`references/competitive-pressure-filter.md` (do not duplicate the schema here).

Own-side model (from the MCP, campaign-level, week-over-week):
  status = 'inactive'   — zero cost/impressions in BOTH weeks
           'no_prior'   — no matching row in the prior-week pull (new/resumed campaign)
           'no_is'      — impression-share metrics unavailable this or prior week
                          (Google Ads returns "--" below its data threshold)
           'scored'     — has both weeks' impression-share data; classified below
  Two mutually exclusive blocks, assigned only to 'scored' campaigns spending at
  least `min_cost` this week, flagged when EITHER condition below fires:
    is_drop  — WoW impression-share delta <= -is_drop_flag (a drop of that many
               percentage points, e.g. -0.05 = 5pp)
    cpc_jump — WoW average-CPC delta >= cpc_jump_flag (e.g. 0.15 = 15%)
  A flagged campaign's block is attributed to whichever loss driver worsened
  more this week: 'Rank pressure' when the rank-lost-IS delta >= the
  budget-lost-IS delta, else 'Budget capped'.

Competitor payload (Auction Insights, user-supplied CSV only — NOT available via
the Google Ads API): each CSV row carries status='competitor_csv'. Never dropped;
never implied to come from the API. `concentration()` (HHI / effective-N /
top-N share) summarizes how concentrated competitive impression share is across
the non-self competitor rows.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parents[2]
sys.path.insert(0, str(PLUGIN_ROOT / "_shared"))
from analytics import concentration, pre_score, signals  # noqa: E402

DEFAULT_PARAMS = {
    "is_drop_flag": 0.05,          # WoW impression-share drop (fraction, 0.05 = 5pp)
    "cpc_jump_flag": 0.15,         # WoW average-CPC increase (fraction, 0.15 = 15%)
    "min_cost": 50.0,              # this-week spend floor to be flag-eligible
    "concentration_top_n": 3,      # top-N competitors for the concentration read
}

# Sensitivity ladder for the IS-drop threshold (percentage points, as fractions),
# holding cpc_jump_flag/min_cost at their current values — mirrors the waste
# filter's cost-multiple ladder.
IS_DROP_LADDER = [0.02, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20]

# Control-total contract shared with scripts/assemble_findings.py: per findings
# array, the numeric fields whose sums are embedded as meta.reconciliation and
# re-verified here on every load.
RECONCILE_ARRAYS = {
    "campaigns": ["cost_this", "clicks_this", "impressions_this", "conversions_this",
                 "cost_prior", "clicks_prior", "impressions_prior", "conversions_prior"],
    "competitors": [],
}

_SIGNAL_RULES = [
    {"id": "is_drop", "key": "is_delta_pp", "op": "le", "value": None},   # value patched per-call
    {"id": "cpc_jump", "key": "cpc_delta_pct", "op": "ge", "value": None},
]

PRESSURE_WEIGHTS = {"is_drop": 2.0, "cpc_jump": 1.0}


class FindingsError(ValueError):
    """Raised when the findings JSON is missing/invalid."""


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
    if "competitors" in data and not isinstance(data["competitors"], list):
        raise FindingsError("findings JSON 'competitors' must be a list when present")
    if (data.get("meta") or {}).get("reconciliation"):
        try:
            import reconcile  # lazy: _shared module, on sys.path via the builders/tests
        except ImportError as e:
            raise FindingsError(
                "findings carry reconciliation totals but the _shared toolkit is not "
                "on sys.path — run via build_competitive_report.py, or add the "
                "plugin's _shared/ to sys.path before loading") from e
        try:
            reconcile.verify(data, RECONCILE_ARRAYS)
        except reconcile.ReconciliationError as e:
            raise FindingsError(str(e)) from e
    return data


def resolve_params(raw: dict | None) -> dict:
    p = dict(DEFAULT_PARAMS)
    for k, v in (raw or {}).items():
        if v is not None:
            p[k] = v
    return p


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _share(v):
    """Nullable impression-share-style field: missing/non-numeric -> None (the
    Google Ads API returns '--' below its data threshold — that is NOT zero)."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def classify_campaign(row: dict, params: dict) -> dict:
    """Annotate one joined this/prior campaign row with status + (if scored)
    the WoW deltas and rank-vs-budget attribution. Never mutates the input."""
    rr = dict(row)
    cost_this = _num(row.get("cost_this"))
    cost_prior = _num(row.get("cost_prior"))
    impr_this = _num(row.get("impressions_this"))
    impr_prior = _num(row.get("impressions_prior"))
    is_this = _share(row.get("impression_share_this"))
    is_prior = _share(row.get("impression_share_prior"))
    has_prior = bool(row.get("has_prior"))

    if cost_this <= 0 and cost_prior <= 0 and impr_this <= 0 and impr_prior <= 0:
        status = "inactive"
    elif not has_prior:
        status = "no_prior"
    elif is_this is None or is_prior is None:
        status = "no_is"
    else:
        status = "scored"

    is_delta_pp = None
    cpc_delta_pct = None
    rank_lost_delta = None
    budget_lost_delta = None
    if status == "scored":
        is_delta_pp = round(is_this - is_prior, 6)
        cpc_this = _num(row.get("avg_cpc_this"))
        cpc_prior = _num(row.get("avg_cpc_prior"))
        cpc_delta_pct = round((cpc_this - cpc_prior) / cpc_prior, 6) if cpc_prior > 0 else None
        rank_this = _num(row.get("rank_lost_is_this"))
        rank_prior = _num(row.get("rank_lost_is_prior"))
        budget_this = _num(row.get("budget_lost_is_this"))
        budget_prior = _num(row.get("budget_lost_is_prior"))
        rank_lost_delta = round(rank_this - rank_prior, 6)
        budget_lost_delta = round(budget_this - budget_prior, 6)

    rr.update({
        "status": status,
        "cost_this": cost_this, "cost_prior": cost_prior,
        "is_delta_pp": is_delta_pp, "cpc_delta_pct": cpc_delta_pct,
        "rank_lost_delta": rank_lost_delta, "budget_lost_delta": budget_lost_delta,
        "eligible": status == "scored" and cost_this >= params["min_cost"],
        "flags": [], "block": "", "pressure_score": 0.0,
    })
    return rr


def _signal_rules(params: dict) -> list:
    rules = [dict(r) for r in _SIGNAL_RULES]
    rules[0]["value"] = -float(params["is_drop_flag"])
    rules[1]["value"] = float(params["cpc_jump_flag"])
    return rules


def classify(campaigns: list, params: dict) -> list:
    """Full classification pass: status (per-row, above) + flags (batched
    through `_shared/analytics.signals`) + block attribution + pressure score."""
    rows = [classify_campaign(c, params) for c in campaigns]
    rules = _signal_rules(params)
    sig_inputs = [
        {"is_delta_pp": r["is_delta_pp"] if r["eligible"] else None,
         "cpc_delta_pct": r["cpc_delta_pct"] if r["eligible"] else None}
        for r in rows
    ]
    flag_lists = signals(sig_inputs, rules)
    out = []
    for r, flags in zip(rows, flag_lists):
        rr = dict(r)
        rr["flags"] = flags
        if flags:
            rank_d = rr["rank_lost_delta"] or 0.0
            budget_d = rr["budget_lost_delta"] or 0.0
            rr["block"] = "Rank pressure" if rank_d >= budget_d else "Budget capped"
        rr["pressure_score"] = pre_score(rr, PRESSURE_WEIGHTS)
        out.append(rr)
    out.sort(key=lambda r: (r["pressure_score"], r["cost_this"]), reverse=True)
    return out


def build_competitors(competitor_rows: list, params: dict) -> dict:
    """Concentration read (HHI / effective-N / top-N share) over the
    user-supplied Auction Insights CSV competitor rows, excluding the 'You'
    self-row. Returns {"rows": annotated_rows, "concentration": {...}}."""
    annotated = []
    threat_rows = []
    for r in competitor_rows:
        rr = dict(r)
        rr["status"] = "competitor_csv"
        is_self = str(r.get("domain", "")).strip().casefold() == "you"
        rr["is_self"] = is_self
        annotated.append(rr)
        if not is_self:
            threat_rows.append(rr)
    conc = concentration(threat_rows, "impression_share", top_n=params["concentration_top_n"])
    return {"rows": annotated, "concentration": conc}


def summarize(classified: list, competitors: dict, params: dict) -> dict:
    scored = [r for r in classified if r["status"] == "scored"]
    flagged = [r for r in classified if r["block"]]
    rank_pressure = [r for r in flagged if r["block"] == "Rank pressure"]
    budget_capped = [r for r in flagged if r["block"] == "Budget capped"]
    return {
        "campaigns": len(classified),
        "scored": len(scored),
        "no_prior": sum(1 for r in classified if r["status"] == "no_prior"),
        "no_is": sum(1 for r in classified if r["status"] == "no_is"),
        "inactive": sum(1 for r in classified if r["status"] == "inactive"),
        "flagged": len(flagged),
        "rank_pressure": len(rank_pressure),
        "budget_capped": len(budget_capped),
        "flagged_cost_this": round(sum(r["cost_this"] for r in flagged), 2),
        "competitor_rows": len(competitors["rows"]),
        "competitor_hhi": competitors["concentration"]["hhi"],
        "competitor_effective_n": competitors["concentration"]["effective_n"],
        "competitor_top_share": competitors["concentration"]["top_share"],
    }


def sensitivity(campaigns: list, params: dict, ladder: list | None = None) -> list:
    """Flag counts per IS-drop threshold, holding cpc_jump_flag/min_cost fixed."""
    ladder = ladder or IS_DROP_LADDER
    out = []
    for t in ladder:
        p = dict(params); p["is_drop_flag"] = t
        classified = classify(campaigns, p)
        flagged = [r for r in classified if r["block"]]
        out.append({
            "is_drop_flag": t,
            "rank_pressure": sum(1 for r in flagged if r["block"] == "Rank pressure"),
            "budget_capped": sum(1 for r in flagged if r["block"] == "Budget capped"),
            "total": len(flagged),
            "is_current": abs(t - params["is_drop_flag"]) < 1e-9,
        })
    return out


def near_misses(classified: list, params: dict, top_n: int = 15) -> list:
    """Eligible, scored, unflagged campaigns ranked by closeness to firing
    either rule (ratio >= 1 would fire; only unflagged rows are near-misses)."""
    pool = []
    for r in classified:
        if r["status"] != "scored" or not r["eligible"] or r["block"]:
            continue
        is_ratio = 0.0
        if params["is_drop_flag"] and r["is_delta_pp"] is not None:
            is_ratio = max(0.0, -r["is_delta_pp"] / params["is_drop_flag"])
        cpc_ratio = 0.0
        if params["cpc_jump_flag"] and r["cpc_delta_pct"] is not None:
            cpc_ratio = max(0.0, r["cpc_delta_pct"] / params["cpc_jump_flag"])
        closeness = max(is_ratio, cpc_ratio)
        if closeness <= 0:
            continue
        pool.append({**r, "closeness": round(closeness, 4),
                     "driver": "is_drop" if is_ratio >= cpc_ratio else "cpc_jump"})
    pool.sort(key=lambda r: r["closeness"], reverse=True)
    return pool[:top_n]


def provenance(findings: dict, params: dict) -> dict:
    meta = findings.get("meta") or {}
    return {
        "client_name": meta.get("client_name", ""),
        "account_id": meta.get("account_id", ""),
        "currency": meta.get("currency", ""),
        "window_this": meta.get("window_this", ""),
        "window_prior": meta.get("window_prior", ""),
        "generated": meta.get("generated", ""),
        "source": meta.get("source", "mcp"),
        "auction_insights_source": meta.get("auction_insights_source", ""),
        "params": dict(params),
    }


def compute_model(findings: dict) -> dict:
    """Assemble the full model at the resolved params. JSON-serializable —
    safe to embed in the HTML explorer for live recompute. This is the single
    source of truth; presentation (md sections, html spec, xlsx layout) lives
    in competitive_spec / competitive_xlsx_spec + the shared render toolkit."""
    params = resolve_params(findings.get("params"))
    classified = classify(findings["campaigns"], params)
    competitors = build_competitors(findings.get("competitors") or [], params)
    return {
        "provenance": provenance(findings, params),
        "params": params,
        "rows": classified,
        "competitors": competitors["rows"],
        "competitor_concentration": competitors["concentration"],
        "summary": summarize(classified, competitors, params),
        "sensitivity": sensitivity(findings["campaigns"], params),
        "near_misses": near_misses(classified, params),
        "is_drop_ladder": IS_DROP_LADDER,
    }
