#!/usr/bin/env python3
"""Audience & targeting advisor — model / single source of truth (stdlib +
_shared/analytics only). Every renderer (md, xlsx) imports this module so the
scoring logic can never diverge across formats.

The findings-JSON input contract is documented authoritatively in
`references/audience-targeting-filter.md` (do not duplicate the schema here).

Two independent datasets, one findings JSON:

  audiences   — applied-audience criteria (ad_group_criterion, type=USER_LIST)
                with performance metrics. SCORED via `_shared/analytics`
                (signals -> pre_score -> a priority tier), benchmarked against
                each audience's OWN campaign (mean cost, weighted-mean CTR
                over that campaign's scored audiences — no separate benchmark
                pull). Negative/exclusion criteria are never scored (status
                "excluded" — kept for coverage visibility, e.g. confirming a
                recent-converters exclusion list is actually attached).
  first_party — Customer Match / Enhanced Conversions / Consent Mode v2 / CMP
                readiness. ALWAYS user-supplied (CSV/manual) — this is not in
                the Google Ads API. Every row carries a `status` of "manual"
                or "config" (never "scored" — this dataset is never computed
                from performance data) and a deterministic `gap` + `severity`
                read from the free-text Readiness column the user provides.
                HONEST: never imply the API confirmed a match rate or a
                configuration state.

Kernel-mirror contract: the applied-audience scoring (signals/pre_score/
priority) is mirrored in the xlsx formulas (audience_xlsx_spec.py) via the
SAME rule/weight/threshold shapes. The first-party gap/severity read has NO
tunable params (it's a fixed text match on a free-text column, not a scored
signal), so the xlsx First-Party Readiness sheet is a static snapshot of the
Python-computed values, not a live formula — there is nothing to keep in
sync there. No HTML explorer/JS kernel exists for this reduced-bundle skill —
the Node<->Python parity gate this skill participates in is the shared
`_shared/analytics.py` primitives gate (own vectors in
tests/analytics_vectors.json), not a per-skill widget.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parents[2]          # .../plugins/google-ads-management
sys.path.insert(0, str(PLUGIN_ROOT / "_shared"))

import analytics as A  # noqa: E402

DEFAULT_PARAMS = {
    "cost_multiple": 2.0,          # wasted_spend / high_cpa bar, × the campaign's own average
    "ctr_factor": 0.5,             # low_ctr: ctr < this × campaign_avg_ctr
    "w_no_bid_adjustment": 1.0,    # pre_score weights (all tunable, all >= 0)
    "w_paused_criterion": 3.0,
    "w_zero_conversions": 1.0,
    "w_wasted_spend": 3.0,
    "w_high_cpa": 3.0,
    "w_low_ctr": 1.0,
    "critical_threshold": 6.0,     # score >= this -> Critical
    "high_threshold": 3.0,         # score >= this (and < critical) -> High
}

# Two cost signals, mirroring the two-block pattern already proven in
# google-ads-keywords-search-terms' waste_filter_core (never-converted waste
# vs. elevated cost-per-conversion among converters) rather than one signal
# that would penalize a high-spending, well-converting audience just for
# spending a lot:
#   wasted_spend — conversions == 0 AND cost > cost_multiple × campaign_avg_cost
#   high_cpa     — conversions >  0 AND cpa  > cost_multiple × campaign_avg_cpa
RULE_IDS = ["no_bid_adjustment", "paused_criterion", "zero_conversions",
           "wasted_spend", "high_cpa", "low_ctr"]

# First-party category -> severity when a gap is found (mirrors SKILL.md's
# existing Recommend framing: Enhanced Conversions / Consent Mode are the
# measurement foundation -> Critical; Customer Match is a targeting upside
# missed -> High; everything else (CMP, etc.) -> Medium).
_CRITICAL_FP_CATS = ("enhanced conversion", "consent mode")
_HIGH_FP_CATS = ("customer match",)
_GAP_NA_TOKENS = ("n/a", "not applicable", "not required", "not relevant")
_GAP_NOT_TOKENS = ("not", "partial")
_GAP_OK_TOKENS = ("configured", "complete", "done", "yes", "verified")

# Control-total contract shared with scripts/assemble_findings.py and
# scripts/audience_csv.py: per findings array, the numeric fields whose sums
# are embedded as meta.reconciliation and re-verified here. `first_party` has
# no numeric fields (all categorical/free-text) so only its row count is
# control-totaled (empty `sums`) — that still catches row-loss/tampering.
RECONCILE_ARRAYS = {
    "audiences": ["cost", "clicks", "impressions", "conversions"],
    "first_party": [],
}


class FindingsError(ValueError):
    """Raised when the findings JSON is missing/invalid."""


def _verify(data: dict) -> dict:
    if not isinstance(data, dict):
        raise FindingsError("findings JSON must be an object")
    if not isinstance(data.get("audiences"), list):
        raise FindingsError("findings JSON missing required array 'audiences'")
    if "first_party" in data and not isinstance(data["first_party"], list):
        raise FindingsError("findings JSON 'first_party' must be an array")
    rec = (data.get("meta") or {}).get("reconciliation")
    if rec:
        try:
            import reconcile  # lazy: _shared module, on sys.path via the builders/tests
        except ImportError as e:
            raise FindingsError(
                "findings carry reconciliation totals but the _shared toolkit is not "
                "on sys.path — run via build_audience_report.py, or add the plugin's "
                "_shared/ to sys.path before loading") from e
        # Verify only the arrays actually present in the reconciliation block —
        # 'first_party' is added incrementally by build_audience_report.py when
        # --first-party-csv is supplied, so a pure MCP (audiences-only) findings
        # JSON is not penalized for not carrying it yet.
        present = {k: v for k, v in RECONCILE_ARRAYS.items() if k in rec}
        try:
            reconcile.verify(data, present)
        except reconcile.ReconciliationError as e:
            raise FindingsError(str(e)) from e
    return data


def load_findings(path: str) -> dict:
    try:
        data = json.loads(Path(path).read_text())
    except FileNotFoundError as e:
        raise FindingsError(f"findings file not found: {path}") from e
    except json.JSONDecodeError as e:
        raise FindingsError(f"findings file is not valid JSON: {e}") from e
    return _verify(data)


def verify_findings(data: dict) -> dict:
    """Same checks as load_findings, for an in-memory dict (the CSV-assembly
    path in build_audience_report.py verifies a freshly-built dict before any
    merge, rather than round-tripping it through a file)."""
    return _verify(data)


def resolve_params(raw: dict | None) -> dict:
    p = dict(DEFAULT_PARAMS)
    for k, v in (raw or {}).items():
        if v is not None:
            p[k] = v
    for k in DEFAULT_PARAMS:
        try:
            p[k] = float(p.get(k, DEFAULT_PARAMS[k]))
        except (TypeError, ValueError):
            p[k] = float(DEFAULT_PARAMS[k])
    return p


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _num_or(v, default: float) -> float:
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _akey(r: dict) -> tuple:
    return (str(r.get("campaign", "")), str(r.get("ad_group", "")), str(r.get("list_name", "")))


def dedupe_audiences(audiences: list) -> list:
    """Merge rows sharing (campaign, ad_group, list_name): SUM the four metric
    fields, keep the first non-metric values (bid_modifier/status/type/
    negative should not legitimately differ for the same criterion)."""
    merged: dict = {}
    order: list = []
    for r in audiences or []:
        k = _akey(r)
        if k not in merged:
            merged[k] = {
                "campaign": r.get("campaign", ""), "ad_group": r.get("ad_group", ""),
                "list_name": r.get("list_name", ""), "list_type": r.get("list_type", "") or "",
                "bid_modifier": _num_or(r.get("bid_modifier"), 1.0),
                "criterion_status": str(r.get("criterion_status", "") or "").upper(),
                "negative": bool(r.get("negative", False)),
                "impressions": 0.0, "clicks": 0.0, "cost": 0.0, "conversions": 0.0,
            }
            order.append(k)
        m = merged[k]
        m["impressions"] += _num(r.get("impressions"))
        m["clicks"] += _num(r.get("clicks"))
        m["cost"] += _num(r.get("cost"))
        m["conversions"] += _num(r.get("conversions"))
    return [merged[k] for k in order]


def build_universe(audiences: list) -> list:
    """Every deduped applied-audience row, annotated with a status. Nothing
    dropped. status = 'scored' (targeting criterion) or 'excluded' (negative/
    exclusion criterion — never classified, kept for coverage visibility)."""
    universe = []
    for a in dedupe_audiences(audiences):
        impr, clicks = a["impressions"], a["clicks"]
        negative = bool(a["negative"])
        universe.append({
            "campaign": a["campaign"], "ad_group": a["ad_group"],
            "list_name": a["list_name"] or "(unnamed list)",
            "list_type": a["list_type"] or "UNKNOWN",
            "bid_modifier": round(a["bid_modifier"], 4),
            "criterion_status": a["criterion_status"] or "UNKNOWN",
            "negative": negative,
            "impressions": impr, "clicks": clicks,
            "cost": round(a["cost"], 6), "conversions": round(a["conversions"], 6),
            "ctr": (clicks / impr) if impr else 0.0,
            "is_paused": 1.0 if a["criterion_status"] == "PAUSED" else 0.0,
            "status": "excluded" if negative else "scored",
        })
    universe.sort(key=lambda r: r["cost"], reverse=True)
    return universe


def _campaign_stats(universe: list) -> dict:
    """Per-campaign benchmark computed from THIS pull's own scored audiences
    (no separate benchmark query — thinnest fit):
      avg_cost = arithmetic mean cost per scored audience (all scored rows).
      avg_ctr  = SUM(clicks)/SUM(impressions) (weighted, not mean-of-ratios)
                 over the campaign's scored audiences.
      avg_cpa  = SUM(cost)/SUM(conversions) (weighted) over the campaign's
                 scored audiences that HAVE conversions — None if none do."""
    agg: dict = {}
    for r in universe:
        if r["status"] != "scored":
            continue
        a = agg.setdefault(r["campaign"], {"cost_sum": 0.0, "n": 0, "clicks_sum": 0.0,
                                           "impr_sum": 0.0, "conv_cost_sum": 0.0, "conv_sum": 0.0})
        a["cost_sum"] += r["cost"]; a["n"] += 1
        a["clicks_sum"] += r["clicks"]; a["impr_sum"] += r["impressions"]
        if r["conversions"] > 0:
            a["conv_cost_sum"] += r["cost"]; a["conv_sum"] += r["conversions"]
    out = {}
    for camp, a in agg.items():
        out[camp] = {
            "avg_cost": (a["cost_sum"] / a["n"]) if a["n"] else 0.0,
            "avg_ctr": (a["clicks_sum"] / a["impr_sum"]) if a["impr_sum"] else 0.0,
            "avg_cpa": (a["conv_cost_sum"] / a["conv_sum"]) if a["conv_sum"] > 0 else None,
        }
    return out


def rules(params: dict) -> list:
    """The declarative analytics.signals rules — SAME shape mirrored in the
    xlsx formula columns (audience_xlsx_spec.py). `cost_if_zero_conv` and
    `cpa` are None on rows they don't apply to, so analytics.signals' "missing
    operand = no fire" rule keeps wasted_spend/high_cpa mutually exclusive by
    construction (a row either has 0 conversions or it doesn't)."""
    return [
        {"id": "no_bid_adjustment", "key": "bid_modifier", "op": "eq", "value": 1.0},
        {"id": "paused_criterion", "key": "is_paused", "op": "eq", "value": 1.0},
        {"id": "zero_conversions", "key": "conversions", "op": "eq", "value": 0.0},
        {"id": "wasted_spend", "key": "cost_if_zero_conv", "op": "gt", "value_key": "campaign_avg_cost",
         "mult": params["cost_multiple"]},
        {"id": "high_cpa", "key": "cpa", "op": "gt", "value_key": "campaign_avg_cpa",
         "mult": params["cost_multiple"]},
        {"id": "low_ctr", "key": "ctr", "op": "lt", "value_key": "campaign_avg_ctr",
         "mult": params["ctr_factor"]},
    ]


def weights(params: dict) -> dict:
    return {
        "no_bid_adjustment": params["w_no_bid_adjustment"],
        "paused_criterion": params["w_paused_criterion"],
        "zero_conversions": params["w_zero_conversions"],
        "wasted_spend": params["w_wasted_spend"],
        "high_cpa": params["w_high_cpa"],
        "low_ctr": params["w_low_ctr"],
    }


def priority(score, params: dict) -> str:
    if score is None or score <= 0:
        return ""
    if score >= params["critical_threshold"]:
        return "Critical"
    if score >= params["high_threshold"]:
        return "High"
    return "Medium"


def classify(universe: list, params: dict) -> list:
    campstats = _campaign_stats(universe)
    scored_rows = []
    for r in universe:
        if r["status"] != "scored":
            continue
        camp = campstats.get(r["campaign"], {"avg_cost": 0.0, "avg_ctr": 0.0, "avg_cpa": None})
        conv = r["conversions"]
        scored_rows.append({
            **r,
            "campaign_avg_cost": camp["avg_cost"],
            "campaign_avg_ctr": camp["avg_ctr"],
            "campaign_avg_cpa": camp["avg_cpa"],
            "cost_if_zero_conv": r["cost"] if conv == 0 else None,
            "cpa": (r["cost"] / conv) if conv > 0 else None,
        })
    flags_list = A.signals(scored_rows, rules(params)) if scored_rows else []
    w = weights(params)

    out = []
    si = 0
    for r in universe:
        rr = dict(r)
        if r["status"] == "scored":
            sr = scored_rows[si]
            flags = flags_list[si]
            score = A.pre_score({"flags": flags}, w)
            rr["campaign_avg_cost"] = sr["campaign_avg_cost"]
            rr["campaign_avg_ctr"] = sr["campaign_avg_ctr"]
            rr["campaign_avg_cpa"] = sr["campaign_avg_cpa"]
            rr["cpa"] = sr["cpa"]
            rr["flags"] = flags
            rr["score"] = score
            rr["priority"] = priority(score, params)
            si += 1
        else:
            rr["campaign_avg_cost"] = None
            rr["campaign_avg_ctr"] = None
            rr["campaign_avg_cpa"] = None
            rr["cpa"] = None
            rr["flags"] = []
            rr["score"] = None
            rr["priority"] = ""
        out.append(rr)
    return out


def _is_gap(readiness) -> bool:
    """Deterministic, case-insensitive substring read of the free-text
    Readiness column. An explicit "N/A / not applicable / not required" is
    NEVER a gap (the item doesn't apply to this account — e.g. Consent Mode
    on a non-EU account — flagging it would be a false positive, not caution)
    and is checked FIRST since "not applicable" would otherwise also match
    the generic "not" token. Otherwise errs cautious: unrecognized text
    counts as a gap. This runs once, here — the xlsx First-Party Readiness
    sheet is a static snapshot of these already-computed values, not a live
    formula (see the module docstring)."""
    s = str(readiness or "").strip().lower()
    if any(t in s for t in _GAP_NA_TOKENS):
        return False
    has_not = any(t in s for t in _GAP_NOT_TOKENS)
    has_ok = any(t in s for t in _GAP_OK_TOKENS)
    return bool(has_not or not has_ok)


def _fp_severity(category, gap: bool) -> str:
    if not gap:
        return ""
    c = str(category or "").strip().lower()
    if any(t in c for t in _CRITICAL_FP_CATS):
        return "Critical"
    if any(t in c for t in _HIGH_FP_CATS):
        return "High"
    return "Medium"


def build_first_party(rows: list) -> list:
    """Every first-party readiness row, annotated with a deterministic gap +
    severity read. Nothing dropped. status = 'config' or 'manual' (never
    'scored' — this dataset is never computed from performance data)."""
    out = []
    for r in rows or []:
        readiness = str(r.get("readiness", "") or "")
        category = str(r.get("category", "") or "")
        row_type = str(r.get("row_type", "") or "manual").strip().lower()
        if row_type not in ("config", "manual"):
            row_type = "manual"
        gap = _is_gap(readiness)
        out.append({
            "category": category,
            "item": str(r.get("item", "") or ""),
            "readiness": readiness,
            "detail": str(r.get("detail", "") or ""),
            "verified_date": str(r.get("verified_date", "") or ""),
            "gap": gap,
            "severity": _fp_severity(category, gap),
            "status": row_type,   # data-lineage field: "manual" or "config"
        })
    return out


def provenance(findings: dict, params: dict) -> dict:
    meta = findings.get("meta") or {}
    return {
        "client_name": meta.get("client_name", ""),
        "account_id": meta.get("account_id", ""),
        "currency": meta.get("currency", ""),
        "window_30d": meta.get("window_30d", ""),
        "generated": meta.get("generated", ""),
        # Honest data-source label (HM-572 canonical normalization): the live-pull
        # default is the canonical "mcp" token; "user_csv" is stamped by the CSV
        # path. Never presented as an API pull when it wasn't one.
        "source": meta.get("source", "mcp"),
        "first_party_source": meta.get("first_party_source", "not_supplied"),
        "params": dict(params),
    }


def summarize(classified: list, first_party: list) -> dict:
    scored = [r for r in classified if r["status"] == "scored"]
    excluded = [r for r in classified if r["status"] == "excluded"]
    critical = [r for r in scored if r["priority"] == "Critical"]
    high = [r for r in scored if r["priority"] == "High"]
    medium = [r for r in scored if r["priority"] == "Medium"]
    clean = [r for r in scored if r["priority"] == ""]
    conc = A.concentration(scored, "cost", top_n=3)

    fp_gaps = [r for r in first_party if r["gap"]]
    fp_ok = [r for r in first_party if not r["gap"]]
    return {
        "total_audiences": len(classified),
        "scored": len(scored),
        "excluded": len(excluded),
        "critical": len(critical), "high": len(high), "medium": len(medium), "clean": len(clean),
        "flagged_cost": round(sum(r["cost"] for r in scored if r["priority"] != ""), 2),
        "spend_top3_share": conc["top_share"],
        "spend_hhi": conc["hhi"],
        "spend_effective_n": conc["effective_n"],
        "first_party_total": len(first_party),
        "first_party_gaps": len(fp_gaps),
        "first_party_ok": len(fp_ok),
        "first_party_critical": sum(1 for r in fp_gaps if r["severity"] == "Critical"),
        "first_party_high": sum(1 for r in fp_gaps if r["severity"] == "High"),
        "first_party_medium": sum(1 for r in fp_gaps if r["severity"] == "Medium"),
    }


def compute_model(findings: dict) -> dict:
    """Assemble the full model at the resolved params. JSON-serializable. This
    is the single source of truth; presentation (md sections, xlsx layout)
    lives in audience_spec / audience_xlsx_spec."""
    params = resolve_params(findings.get("params"))
    universe = build_universe(findings.get("audiences") or [])
    classified = classify(universe, params)
    first_party = build_first_party(findings.get("first_party") or [])
    return {
        "provenance": provenance(findings, params),
        "params": params,
        "rows": classified,
        "first_party": first_party,
        "summary": summarize(classified, first_party),
        "_universe": universe,
    }
