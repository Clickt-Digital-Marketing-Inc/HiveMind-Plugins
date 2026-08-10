#!/usr/bin/env python3
"""Conversions & tracking advisor — model / single source of truth (stdlib only,
plus the shared `analytics` primitives module).

Every renderer (md, html, xlsx) imports this module so the classification logic
can never diverge across formats. The findings-JSON input contract is
documented authoritatively in `references/conversion-tracking-filter.md` (do
not duplicate the schema here).

TWO datasets, each with its own honesty posture:

  conversion_actions  — config-HEALTH checklist over live `conversion_action`
    rows pulled via MCP. Deterministic pass/flag rules (dormant primary,
    "Every"-counting for lead categories, legacy attribution model, duplicate
    primary-goal category) plus one account-level check (no primary action at
    all). status="config" on every row — nothing here is a trend/score.

  campaign_trend  — per-campaign CVR/CTR trend over two comparable windows,
    the SCORED half of the model: `_shared/analytics.signals` fires
    declarative threshold/relative rules, `_shared/analytics.pre_score`
    weights them into a severity score, and rows are bucketed into a tier
    (Critical/High/Watch/clean). Campaigns with no usable prior-window
    benchmark (clicks_prior == 0) are kept with status="no_benchmark" and
    never scored — no-row-loss holds across both datasets.

  manual_checks  — Enhanced Conversions / Consent Mode. The Google Ads API
    does not expose these; every row here carries status="manual" and a
    `data_source` of "user_csv" (assembled from a UI export via
    `_shared/csv_input.py`) or "not_confirmed" (no CSV given — the row is
    still emitted, honestly labelled, never silently dropped). These rows are
    NEVER presented as an API-confirmed finding.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "_shared"))  # analytics / reconcile

import analytics  # noqa: E402

DROP_LADDER = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.75]

DEFAULT_PARAMS = {
    "cvr_drop_pct": 0.30,     # flag when cvr_curr <= cvr_prior * (1 - this)
    "min_conv_30d": 30,       # flag when conversions_curr < this (volume too thin for automation)
    "ctr_factor": 1.00,       # flag "ctr held/up" when ctr_curr >= ctr_prior * this
    "cvr_factor": 0.50,       # flag when cvr_curr < account_avg_cvr * this
}

# ConversionActionCategory values where "count every conversion" (MANY_PER_CLICK)
# typically double-counts a single lead (the UI calls MANY_PER_CLICK "Every").
LEAD_CATEGORIES = {"SUBMIT_LEAD_FORM", "BOOK_APPOINTMENT", "REQUEST_QUOTE", "CONTACT", "SIGNUP"}

# attribution_model_settings.attribution_model values superseded by data-driven
# attribution — rule-based models that don't reflect the real conversion path.
LEGACY_ATTRIBUTION = {
    "GOOGLE_ADS_LAST_CLICK",
    "GOOGLE_SEARCH_ATTRIBUTION_FIRST_CLICK",
    "GOOGLE_SEARCH_ATTRIBUTION_LINEAR",
    "GOOGLE_SEARCH_ATTRIBUTION_TIME_DECAY",
    "GOOGLE_SEARCH_ATTRIBUTION_POSITION_BASED",
}

CONFIG_WEIGHTS = {
    "dormant_primary": 5.0,
    "every_counting_lead": 3.0,
    "legacy_attribution": 2.0,
    "duplicate_primary_category": 3.0,
}
TREND_WEIGHTS = {
    "cvr_drop": 4.0,
    "landing_page_suspect": 6.0,
    "thin_volume": 1.0,
    "below_account_cvr": 2.0,
}

CONFIG_FLAG_LABELS = [
    ("dormant_primary", "Dormant primary action — 0 conversions (30d) on an ENABLED primary-for-goal action"),
    ("every_counting_lead", "“Every” counting (MANY_PER_CLICK) on a lead-style category — likely double-counts"),
    ("legacy_attribution", "Legacy rule-based attribution model (not data-driven)"),
    ("duplicate_primary_category", "Multiple ENABLED primary-for-goal actions share one category"),
]
TREND_FLAG_LABELS = [
    ("cvr_drop", "CVR dropped ≥ the threshold vs. the prior window"),
    ("ctr_held_or_up", "CTR held or improved vs. the prior window (context, not itself a flag)"),
    ("landing_page_suspect", "CVR dropped while CTR held/improved — points at the landing page, not the ads"),
    ("thin_volume", "Conversions (current window) below the volume-sufficiency floor"),
    ("below_account_cvr", "CVR well below the account's click-weighted average CVR"),
]


class FindingsError(ValueError):
    """Raised when the findings JSON is missing/invalid."""


# Control-total contract shared with scripts/assemble_findings.py: per findings
# array, the numeric fields whose sums are embedded as meta.reconciliation and
# re-verified here on every load. manual_checks carries no numeric fields (EC /
# Consent-Mode config is categorical) so only its row count is reconciled.
RECONCILE_ARRAYS = {
    "conversion_actions": ["conversions_30d"],
    "campaign_trend": ["clicks_curr", "impressions_curr", "cost_curr", "conversions_curr",
                       "clicks_prior", "impressions_prior", "cost_prior", "conversions_prior"],
    "manual_checks": [],
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
    for req in ("conversion_actions", "campaign_trend", "manual_checks"):
        if not isinstance(data.get(req), list):
            raise FindingsError(f"findings JSON missing required array '{req}'")
    if (data.get("meta") or {}).get("reconciliation"):
        try:
            import reconcile  # lazy: _shared module, on sys.path via the builders/tests
        except ImportError as e:
            raise FindingsError(
                "findings carry reconciliation totals but the _shared toolkit is not "
                "on sys.path — run via build_conv_tracking_report.py, or add the "
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


def _liveness_note(row: dict) -> str:
    """Conditional-phrasing seam for recently_active trend rows (HM-603) — the
    note the recommendation layer surfaces so a CVR-drop on a paused/idle/gone-
    dark campaign is hedged ("confirm intent") rather than presented as a hard
    Critical. Empty for live (nothing to caveat) and dormant (never scored)."""
    if row.get("liveness") != "recently_active":
        return ""
    enabled = str(row.get("campaign_status") or "").strip().upper() == "ENABLED"
    cur = _num(row.get("cost_curr"))
    if not enabled and cur > 0:
        return (f"Paused/removed mid-window after spending {cur:,.2f} — confirm intent "
                "before acting on the trend.")
    if enabled and cur <= 0:
        return "Enabled but no spend in the current window — confirm it should be running."
    return ("Spent only in the prior window — the CVR trend may be an artifact of going "
            "dark; confirm intent.")


# --------------------------------------------------------------------------
# Dataset 1 — conversion-action config health (status="config")
# --------------------------------------------------------------------------
def build_config_rows(conversion_actions: list) -> tuple[list, bool]:
    """Every conversion_action row, annotated with flags/verdict. Nothing
    dropped. Returns (rows, no_primary_action) — the account-level flag is
    True when no row is an ENABLED primary-for-goal action."""
    primary_rows = [a for a in conversion_actions
                    if bool(a.get("primary_for_goal")) and str(a.get("status", "")).upper() == "ENABLED"]
    dup_categories = {cat for cat, n in
                      Counter(str(a.get("category", "")).upper() for a in primary_rows).items() if n > 1}
    rows = []
    for a in conversion_actions:
        enabled = str(a.get("status", "")).upper() == "ENABLED"
        primary = bool(a.get("primary_for_goal"))
        counting = str(a.get("counting_type", "")).upper()
        category = str(a.get("category", "")).upper()
        attribution = str(a.get("attribution_model", "")).upper()
        conv30 = _num(a.get("conversions_30d"))
        flags = []
        if primary and enabled and conv30 <= 0:
            flags.append("dormant_primary")
        if counting == "MANY_PER_CLICK" and category in LEAD_CATEGORIES:
            flags.append("every_counting_lead")
        if attribution in LEGACY_ATTRIBUTION:
            flags.append("legacy_attribution")
        if primary and enabled and category in dup_categories:
            flags.append("duplicate_primary_category")
        score = analytics.pre_score({"flags": flags}, CONFIG_WEIGHTS)
        rows.append({
            "id": a.get("id"), "name": a.get("name", ""), "status": "config",
            "action_status": a.get("status", ""), "category": category, "type": a.get("type", ""),
            "primary_for_goal": primary, "counting_type": a.get("counting_type", ""),
            "attribution_model": a.get("attribution_model", ""), "conversions_30d": conv30,
            "flags": flags, "verdict": "flag" if flags else "pass", "score": score,
        })
    rows.sort(key=lambda r: (-r["score"], r["name"]))
    return rows, (len(primary_rows) == 0)


# --------------------------------------------------------------------------
# Dataset 2 — Enhanced Conversions / Consent Mode (status="manual", honest)
# --------------------------------------------------------------------------
def build_manual_rows(manual_checks: list) -> list:
    """Pass every manual-check row through unchanged except normalizing
    status="manual" (never "confirmed by the API") and defaulting a
    data_source label so the report can honestly say where the value came
    from. Nothing here is ever implied to be an MCP/API result."""
    rows = []
    for c in manual_checks:
        rows.append({
            "check": c.get("check", ""),
            "status": "manual",
            "value": c.get("value") or "not confirmed via API",
            "data_source": c.get("data_source") or "not_confirmed",
            "note": c.get("note", ""),
        })
    return rows


# --------------------------------------------------------------------------
# Dataset 3 — per-campaign CVR/CTR trend (status="scored"/"no_benchmark")
# --------------------------------------------------------------------------
def build_trend_universe(campaign_trend: list) -> list:
    """Every campaign_trend row with recomputed CTR/CVR for both windows and
    a status. status='scored' requires a usable prior-window click benchmark
    (clicks_prior > 0); otherwise the row is kept as 'no_benchmark' with prior
    fields left as None (never 0.0 — a real zero must not masquerade as a
    computed rate) so the classifier's relative rules never spuriously fire."""
    rows = []
    for c in campaign_trend:
        clicks_curr = _num(c.get("clicks_curr"))
        impr_curr = _num(c.get("impressions_curr"))
        conv_curr = _num(c.get("conversions_curr"))
        clicks_prior = _num(c.get("clicks_prior"))
        impr_prior = _num(c.get("impressions_prior"))
        conv_prior = _num(c.get("conversions_prior"))
        ctr_curr = (clicks_curr / impr_curr) if impr_curr else 0.0
        cvr_curr = (conv_curr / clicks_curr) if clicks_curr else 0.0
        scored = clicks_prior > 0
        ctr_prior = (clicks_prior / impr_prior) if (scored and impr_prior) else None
        cvr_prior = (conv_prior / clicks_prior) if scored else None
        rows.append({
            "campaign_id": c.get("campaign_id"), "campaign": c.get("campaign", ""),
            # Raw campaign.status under a NEW key — the pipeline "status"
            # (scored/no_benchmark) below is a different axis and must not collide.
            "campaign_status": c.get("campaign_status", ""),
            "clicks_curr": clicks_curr, "impressions_curr": impr_curr,
            "cost_curr": _num(c.get("cost_curr")), "conversions_curr": conv_curr,
            "ctr_curr": ctr_curr, "cvr_curr": cvr_curr,
            "clicks_prior": clicks_prior, "impressions_prior": impr_prior,
            "cost_prior": _num(c.get("cost_prior")), "conversions_prior": conv_prior,
            "ctr_prior": ctr_prior, "cvr_prior": cvr_prior,
            "status": "scored" if scored else "no_benchmark",
        })
    # Campaign liveness (HM-603): three-band — this dataset carries campaign.status
    # (campaign_status), current-window spend (cost_curr) AND prior-window spend
    # (cost_prior), so all three bands are fully derivable. Severity is gated on
    # live+recently_active in classify_trend; dormant rows stay present-but-tagged.
    rows = analytics.segment_liveness(rows, status_key="campaign_status",
                                      spend_key="cost_curr", prior_spend_key="cost_prior")
    for r in rows:
        r["liveness_note"] = _liveness_note(r)
    rows.sort(key=lambda r: r["cost_curr"], reverse=True)
    return rows


def _account_avg_cvr(universe: list) -> float:
    scored = [r for r in universe if r["status"] == "scored"]
    clicks = sum(r["clicks_curr"] for r in scored)
    if clicks <= 0:
        return 0.0
    return sum(r["conversions_curr"] for r in scored) / clicks


def _trend_rules(params: dict) -> list:
    return [
        {"id": "cvr_drop", "key": "cvr_curr", "op": "le", "value_key": "cvr_prior",
         "mult": 1.0 - params["cvr_drop_pct"]},
        {"id": "ctr_held_or_up", "key": "ctr_curr", "op": "ge", "value_key": "ctr_prior",
         "mult": params["ctr_factor"]},
        {"id": "thin_volume", "key": "conversions_curr", "op": "lt", "value": params["min_conv_30d"]},
        {"id": "below_account_cvr", "key": "cvr_curr", "op": "lt", "value_key": "account_avg_cvr",
         "mult": params["cvr_factor"]},
    ]


def _tier(status: str, score: float) -> str:
    if status != "scored":
        return ""
    if score >= 6:
        return "Critical"
    if score >= 3:
        return "High"
    if score > 0:
        return "Watch"
    return ""


def classify_trend(universe: list, params: dict) -> list:
    """Batch-classify the trend universe via the shared analytics primitives.
    `account_avg_cvr` is broadcast onto every row (scored and no_benchmark
    alike) so the relative rule reads it identically to a per-row field —
    the same "campaign benchmark join" idiom as the search-term waste filter."""
    avg_cvr = _account_avg_cvr(universe)
    rows = [{**r, "account_avg_cvr": avg_cvr} for r in universe]
    flags_per_row = analytics.signals(rows, _trend_rules(params))
    out = []
    for r, flags in zip(rows, flags_per_row):
        flags = list(flags)
        if "cvr_drop" in flags and "ctr_held_or_up" in flags:
            flags.append("landing_page_suspect")
        # Liveness gate (HM-603): a dormant campaign (not ENABLED, zero spend in
        # BOTH windows) never manufactures a CVR-drop finding — flags cleared, so
        # score 0 and tier "" follow. The row survives, tagged liveness="dormant".
        # live + recently_active rows are scored normally (recently_active carries
        # a liveness_note so the recommendation is hedged, not the score).
        if r.get("liveness") == "dormant":
            flags = []
        score = analytics.pre_score({"flags": flags}, TREND_WEIGHTS)
        rr = dict(r)
        rr["flags"] = flags
        rr["score"] = score
        rr["tier"] = _tier(r["status"], score)
        out.append(rr)
    return out


def summarize_trend(classified: list) -> dict:
    scored = [r for r in classified if r["status"] == "scored"]
    nb = [r for r in classified if r["status"] == "no_benchmark"]
    crit = sum(1 for r in scored if r["tier"] == "Critical")
    high = sum(1 for r in scored if r["tier"] == "High")
    watch = sum(1 for r in scored if r["tier"] == "Watch")
    return {
        "campaigns": len(classified), "scored": len(scored), "no_benchmark": len(nb),
        "critical": crit, "high": high, "watch": watch,
        "clean": len(scored) - crit - high - watch,
        "account_avg_cvr": round(_account_avg_cvr(classified), 6),
        "landing_page_suspect": sum(1 for r in scored if "landing_page_suspect" in r["flags"]),
    }


def trend_sensitivity(universe: list, params: dict, ladder: list | None = None) -> list:
    """How many campaigns qualify Critical/High as cvr_drop_pct steps down,
    holding every other param at `params` — mirrors the waste-filter's
    threshold-sensitivity table."""
    ladder = ladder or DROP_LADDER
    out = []
    for pct in ladder:
        p = dict(params)
        p["cvr_drop_pct"] = pct
        s = summarize_trend(classify_trend(universe, p))
        out.append({"cvr_drop_pct": pct, "critical": s["critical"], "high": s["high"],
                    "watch": s["watch"], "is_current": abs(pct - params["cvr_drop_pct"]) < 1e-9})
    return out


def config_segments(config_rows: list) -> tuple[list, list]:
    """Split the config-health rows by primary_for_goal — primary-for-goal
    actions (which Smart Bidding optimizes toward, so they drive the health
    framing) vs. secondary actions (listed separately, never dropped). Both
    keep the score sort already applied by build_config_rows."""
    primary = [r for r in config_rows if r.get("primary_for_goal")]
    secondary = [r for r in config_rows if not r.get("primary_for_goal")]
    return primary, secondary


def summarize_config(config_rows: list, no_primary_action: bool) -> dict:
    flagged = [r for r in config_rows if r["verdict"] == "flag"]
    primary, secondary = config_segments(config_rows)
    return {
        "actions": len(config_rows), "flagged": len(flagged), "clean": len(config_rows) - len(flagged),
        "no_primary_action": no_primary_action,
        # Primary-for-goal actions drive the health framing; secondary listed with its own count.
        "primary_actions": len(primary),
        "primary_flagged": sum(1 for r in primary if r["verdict"] == "flag"),
        "secondary_actions": len(secondary),
        "secondary_flagged": sum(1 for r in secondary if r["verdict"] == "flag"),
        "dormant_primary": sum(1 for r in config_rows if "dormant_primary" in r["flags"]),
        "every_counting_lead": sum(1 for r in config_rows if "every_counting_lead" in r["flags"]),
        "legacy_attribution": sum(1 for r in config_rows if "legacy_attribution" in r["flags"]),
        "duplicate_primary_category": sum(1 for r in config_rows if "duplicate_primary_category" in r["flags"]),
    }


def summarize_manual(manual_rows: list) -> dict:
    return {
        "checks": len(manual_rows),
        "user_confirmed": sum(1 for r in manual_rows if r["data_source"] == "user_csv"),
        "not_confirmed": sum(1 for r in manual_rows if r["data_source"] != "user_csv"),
    }


def provenance(findings: dict, params: dict) -> dict:
    meta = findings.get("meta") or {}
    # Windows are operator-chosen (7d-vs-prior-7d, THIS_MONTH-vs-LAST_MONTH, ...),
    # never literally 90d/30d — reuse the shared html template's hardcoded
    # window_90d/window_30d provenance slots (established convention: see
    # budget_core.provenance) and relabel them honestly via spec['window_labels'].
    return {
        "client_name": meta.get("client_name", ""), "account_id": meta.get("account_id", ""),
        "currency": meta.get("currency", ""), "window_90d": meta.get("window_curr", ""),
        "window_30d": meta.get("window_prior", ""), "generated": meta.get("generated", ""),
        # Canonical live-pull token (HM-572): "mcp"; CSV path stamps "user_csv".
        "source": meta.get("source", "mcp"), "params": dict(params),
    }


def compute_model(findings: dict) -> dict:
    """Assemble the full model at the resolved params. JSON-serializable —
    safe to embed in the HTML explorer for live recompute. Single source of
    truth; presentation (md sections, html spec, xlsx layout) lives in
    conv_tracking_spec / conv_tracking_xlsx_spec and the shared render toolkit.

    model['rows'] is the PRIMARY tunable dataset (campaign CVR/CTR trend) —
    the one the in-Claude tuner and the HTML sliders drive live. The
    config-health checklist and the manual EC/Consent-Mode rows are the
    secondary, non-tunable datasets (model['config_rows'] / ['manual_rows']),
    surfaced through the md/xlsx snapshot sections instead — no-row-loss holds
    for all three, just not through the single generic 'rows' contract."""
    params = resolve_params(findings.get("params"))
    config_rows, no_primary_action = build_config_rows(findings["conversion_actions"])
    manual_rows = build_manual_rows(findings["manual_checks"])
    trend_universe = build_trend_universe(findings["campaign_trend"])
    trend_rows = classify_trend(trend_universe, params)

    # One FLAT summary dict (matches the shared render toolkit's implicit
    # single-namespace contract — model['summary'].get(key) is used verbatim
    # by render/xlsx.py's results 'value_key' lookups). Trend keys are
    # unprefixed (the primary/tunable dataset); config/manual keys are
    # prefixed to avoid collisions.
    summary = dict(summarize_trend(trend_rows))
    summary.update({f"config_{k}": v for k, v in summarize_config(config_rows, no_primary_action).items()})
    summary.update({f"manual_{k}": v for k, v in summarize_manual(manual_rows).items()})

    return {
        "provenance": provenance(findings, params),
        "params": params,
        "rows": trend_rows,
        "config_rows": config_rows,
        "manual_rows": manual_rows,
        "summary": summary,
        "sensitivity": trend_sensitivity(trend_universe, params),
        "drop_ladder": DROP_LADDER,
        "config_flag_labels": CONFIG_FLAG_LABELS,
        "trend_flag_labels": TREND_FLAG_LABELS,
    }
