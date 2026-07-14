#!/usr/bin/env python3
"""Performance report — model / single source of truth (stdlib only).

Every renderer (md, html, xlsx) consumes this model via the shared toolkit
(`_shared/render`), so the classification can never diverge across formats.

The findings-JSON input contract is documented authoritatively in
`references/performance-report.md` (do not duplicate the schema here).

One row per campaign for the reporting window, each annotated with its
prior-period deltas and a ROAS-vs-goal bucket:
  Scale  — ROAS >= goal AND budget-lost impression share > flag (a winner the
           budget is throttling) -> make the budget-increase case
  Winner — ROAS >= goal, not budget-constrained
  Fix    — ROAS <  goal AND spend >= min_spend (a material laggard)
  Hold   — measured, below the spend floor / mild
Campaigns with no revenue signal (conversions_value not tracked) are kept with
status="no_value" and never ROAS-bucketed (never dropped).
Period-over-period **anomaly signals**, spend/conversion **concentration**, and a
per-row **anomaly pre-score** are computed via the shared `_shared/analytics.py`
primitives (concentration / signals / pre_score) — the SAME kernel-mirror
contract every google-ads-management skill uses, spliced into the browser
kernel (`perf_spec.JS_KERNEL`) and the xlsx formulas (`perf_xlsx_spec.py`) so
all three formats agree. Anomaly flags fire off the existing period-over-period
deltas (spend_delta/conv_delta/value_delta) against the tunable `delta_flag`
threshold; a missing prior (delta is None) is "no signal", never a flag.
"""
from __future__ import annotations

import json
from pathlib import Path

import analytics

ROAS_LADDER = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0]

DEFAULT_PARAMS = {
    "roas_goal": 4.0,            # ROAS target (conversions_value / spend)
    "budget_lost_is_flag": 0.10,  # budget-lost impression share above this = throttled
    "delta_flag": 0.25,          # period-over-period swing beyond this = anomaly
    "min_spend": 0.0,            # only call a sub-goal campaign "Fix" at/above this spend
}

# Anomaly pre-score weights (analytics.pre_score contract) — severity-weighted:
# a conversion or revenue drop outweighs a spend swing of the same magnitude.
ANOMALY_WEIGHTS = {
    "spend_spike": 2.0,
    "spend_drop": 1.5,
    "conv_drop": 2.5,
    "value_drop": 2.0,
}


def anomaly_rules(delta_flag: float) -> list:
    """analytics.signals() rule set for one row's period-over-period deltas.

    Missing-prior deltas are None (analytics._num -> no signal, never fires) —
    a campaign with no prior-period data is never flagged as anomalous."""
    return [
        {"id": "spend_spike", "key": "spend_delta", "op": "gt", "value": delta_flag},
        {"id": "spend_drop", "key": "spend_delta", "op": "lt", "value": -delta_flag},
        {"id": "conv_drop", "key": "conv_delta", "op": "lt", "value": -delta_flag},
        {"id": "value_drop", "key": "value_delta", "op": "lt", "value": -delta_flag},
    ]


class FindingsError(ValueError):
    """Raised when the findings JSON is missing/invalid."""


# Control-total contract shared with scripts/assemble_findings.py: per findings
# array, the numeric fields whose sums are embedded as meta.reconciliation and
# re-verified here on every load. Catches transcription drift and hand-edits.
# (Impression-share fractions are included purely as tamper checks — their sums
# are control totals, not analytics; None/absent values total as 0 on both
# sides, so no_value / PMax-null rows stay consistent.)
RECONCILE_ARRAYS = {
    "campaigns": ["cost", "impressions", "clicks", "conversions", "conversions_value",
                  "search_impression_share", "search_budget_lost_is", "search_rank_lost_is",
                  "prior_cost", "prior_conversions", "prior_conversions_value",
                  "prior_impressions", "prior_clicks"],
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
                "on sys.path — run via build_perf_report.py, or add the plugin's "
                "_shared/ to sys.path before loading") from e
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


def _r2(x):
    """Round half-UP to 2dp, matching JS Math.round(x*100)/100 so the Python
    summary and the embedded JS kernel agree byte-for-byte (Python's built-in
    round() is banker's rounding and would diverge on .5 boundaries)."""
    import math
    return math.floor(float(x) * 100 + 0.5) / 100


def _opt(v):
    """Return float or None (preserves 'not tracked' vs a real 0)."""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def dedupe_campaigns(campaigns: list) -> list:
    """Merge rows sharing campaign_id (e.g. split by a segment): sum the additive
    metrics; impression-share/value fields are taken from the first occurrence."""
    merged: dict = {}
    order: list = []
    for c in campaigns:
        k = c.get("campaign_id")
        if k not in merged:
            merged[k] = dict(c)
            merged[k]["impressions"] = 0.0
            merged[k]["clicks"] = 0.0
            merged[k]["cost"] = 0.0
            merged[k]["conversions"] = 0.0
            merged[k]["_value_seen"] = False
            merged[k]["conversions_value"] = 0.0
            for pk in ("prior_cost", "prior_conversions", "prior_conversions_value",
                       "prior_impressions", "prior_clicks"):
                merged[k][pk] = 0.0
            order.append(k)
        m = merged[k]
        m["impressions"] += _num(c.get("impressions"))
        m["clicks"] += _num(c.get("clicks"))
        m["cost"] += _num(c.get("cost"))
        m["conversions"] += _num(c.get("conversions"))
        cv = _opt(c.get("conversions_value"))
        if cv is not None:
            m["_value_seen"] = True
            m["conversions_value"] += cv
        for pk in ("prior_cost", "prior_conversions", "prior_conversions_value",
                   "prior_impressions", "prior_clicks"):
            m[pk] += _num(c.get(pk))
    return [merged[k] for k in order]


def _pop_delta(curr, prior):
    """Period-over-period % change, or None if the prior is 0/undefined."""
    if not prior:
        return None
    return (curr - prior) / prior


def build_rows(campaigns: list) -> list:
    rows = []
    for c in dedupe_campaigns(campaigns):
        cost = _num(c.get("cost"))
        clicks = _num(c.get("clicks"))
        impr = _num(c.get("impressions"))
        conv = _num(c.get("conversions"))
        value_seen = c.get("_value_seen", c.get("conversions_value") is not None)
        value = _num(c.get("conversions_value")) if value_seen else None
        roas = (value / cost) if (value is not None and cost > 0) else None
        rows.append({
            "campaign_id": c.get("campaign_id"),
            "campaign": c.get("campaign", str(c.get("campaign_id"))),
            "status_label": c.get("status", ""),
            "channel": c.get("channel", ""),
            "impressions": impr, "clicks": clicks, "cost": cost,
            "conversions": conv, "value": value,
            "ctr": (clicks / impr) if impr else 0.0,
            "cvr": (conv / clicks) if clicks else 0.0,
            "cpa": (cost / conv) if conv else None,
            "roas": roas,
            "search_is": _opt(c.get("search_impression_share")),
            "budget_lost_is": _opt(c.get("search_budget_lost_is")),
            "rank_lost_is": _opt(c.get("search_rank_lost_is")),
            "spend_delta": _pop_delta(cost, _num(c.get("prior_cost"))),
            "conv_delta": _pop_delta(conv, _num(c.get("prior_conversions"))),
            "value_delta": _pop_delta(value, _num(c.get("prior_conversions_value"))) if value is not None else None,
            "status": "measured" if value is not None else "no_value",
        })
    rows.sort(key=lambda r: r["cost"], reverse=True)
    return rows


def classify_row(row: dict, params: dict) -> dict:
    """Bucket one row by ROAS vs goal. no_value rows are never bucketed."""
    if row["status"] != "measured" or row["roas"] is None:
        return {"bucket": ""}
    goal = params["roas_goal"]
    blis = row["budget_lost_is"]
    if row["roas"] >= goal:
        if blis is not None and blis > params["budget_lost_is_flag"]:
            return {"bucket": "Scale"}
        return {"bucket": "Winner"}
    if row["cost"] >= params["min_spend"]:
        return {"bucket": "Fix"}
    return {"bucket": "Hold"}


def classify(rows: list, params: dict) -> list:
    out = []
    for r in rows:
        rr = dict(r)
        rr.update(classify_row(r, params))
        out.append(rr)
    return out


def summarize(rows: list) -> dict:
    spend = sum(r["cost"] for r in rows)
    value = sum((r["value"] or 0) for r in rows)
    conv = sum(r["conversions"] for r in rows)
    clicks = sum(r["clicks"] for r in rows)
    impr = sum(r["impressions"] for r in rows)
    buckets = {b: 0 for b in ("Scale", "Winner", "Fix", "Hold")}
    for r in rows:
        if r.get("bucket") in buckets:
            buckets[r["bucket"]] += 1
    return {
        "campaigns": len(rows),
        "spend": _r2(spend),
        "revenue": _r2(value),
        "conversions": _r2(conv),
        "roas": _r2(value / spend) if spend else None,
        "cpa": _r2(spend / conv) if conv else None,
        "ctr": (clicks / impr) if impr else 0.0,
        "scale": buckets["Scale"], "winner": buckets["Winner"],
        "fix": buckets["Fix"], "hold": buckets["Hold"],
        "no_value": sum(1 for r in rows if r["status"] == "no_value"),
    }


def goal_sensitivity(rows: list, params: dict, ladder: list | None = None) -> list:
    """Bucket counts as the ROAS goal moves, holding other params."""
    ladder = ladder or ROAS_LADDER
    out = []
    for g in ladder:
        p = dict(params); p["roas_goal"] = g
        s = summarize(classify(rows, p))
        out.append({"roas_goal": g, "scale": s["scale"], "winner": s["winner"],
                    "fix": s["fix"], "is_current": abs(g - params["roas_goal"]) < 1e-9})
    return out


def provenance(findings: dict, params: dict) -> dict:
    meta = findings.get("meta") or {}
    return {
        "client_name": meta.get("client_name", ""),
        "account_id": meta.get("account_id", ""),
        "currency": meta.get("currency", ""),
        "window_90d": meta.get("period", ""),         # reuse the toolkit's window slots
        "window_30d": meta.get("prior_period", ""),
        "generated": meta.get("generated", ""),
        "source": meta.get("source") or "mcp",         # honest data-source label (M0.3 contract)
        "params": dict(params),
    }


def annotate_anomalies(rows: list, params: dict) -> list:
    """Attach period-over-period anomaly `flags` + a weighted `pre_score` to
    every row (all rows, incl. no_value — a lead-gen campaign's spend/conv can
    still be anomalous even with no ROAS signal)."""
    flags = analytics.signals(rows, anomaly_rules(params["delta_flag"]))
    out = []
    for r, f in zip(rows, flags):
        rr = dict(r)
        rr["flags"] = f
        rr["pre_score"] = analytics.pre_score(rr, ANOMALY_WEIGHTS)
        out.append(rr)
    return out


def compute_concentration(rows: list) -> dict:
    """Spend + conversion concentration (top-3 share / HHI / effective-N)."""
    return {
        "spend": analytics.concentration(rows, "cost", top_n=3),
        "conversions": analytics.concentration(rows, "conversions", top_n=3),
    }


def compute_model(findings: dict) -> dict:
    params = resolve_params(findings.get("params"))
    rows = build_rows(findings["campaigns"])
    classified = annotate_anomalies(classify(rows, params), params)
    summary = summarize(classified)
    summary["anomalies"] = sum(1 for r in classified if r["flags"])
    return {
        "provenance": provenance(findings, params),
        "params": params,
        "rows": classified,
        "summary": summary,
        "concentration": compute_concentration(classified),
        "goal_sensitivity": goal_sensitivity(rows, params),
        "roas_ladder": ROAS_LADDER,
        "_rows": rows,
    }
