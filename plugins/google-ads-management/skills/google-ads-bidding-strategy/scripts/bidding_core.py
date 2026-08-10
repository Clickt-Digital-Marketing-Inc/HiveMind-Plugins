#!/usr/bin/env python3
"""Bidding-strategy Data Maturity Score — model / single source of truth (stdlib only).

Every renderer (md, html, xlsx) imports this module so the classification logic
can never diverge across formats. Stdlib + `_shared/analytics` only (no
third-party dependencies; `_shared` is put on `sys.path` by the callers —
`build_bidding_report.py`, `assemble_findings.py`, and `tests/`).

The findings-JSON input contract is documented authoritatively in
`references/bidding-strategy-maturity.md` (do not duplicate the schema here).

## The model

Per campaign, a **Data Maturity Score** (0-100):

    Score = VolumeScore * volume_weight
          + ValueVarianceScore * value_weight
          + TrackingConfidenceScore * tracking_weight

- **VolumeScore** is hard-scored from `conv30` against the tunable
  `conv_target` (`= min(100, 100 * conv30 / conv_target)`) — the one component
  computed purely from pulled/exported data.
- **ValueVarianceScore** and **TrackingConfidenceScore** are optional judgment
  inputs (0-100; higher = more mature/stable) that the MCP cannot supply —
  when a campaign's findings row omits one, the tunable assumed-neutral value
  (`assumed_value_score` / `assumed_tracking_score`, default 50) is used
  instead. Every row's `confidence` field is `"measured"` (both supplied),
  `"partial"` (one supplied), or `"assumed"` (neither) — never silently
  presented as a hard-measured score.

The maturity score maps to a recommended bid-strategy tier via four tunable
**band edges** (default 30/50/70/85 — see `TIER_LABELS`). The campaign's
*current* strategy also maps to a tier via `STRATEGY_TIERS` (fixed — that
mapping is about the enum, not tunable). The **bid-strategy-mismatch signal**
compares the two tiers:

- `tier_gap = current_tier - recommended_tier`
- `tier_gap > tier_gap_threshold`  -> "Over-automated" (running a strategy the
  data doesn't yet support)
- `tier_gap < -tier_gap_threshold` -> "Under-automated" (data supports more
  automation than is switched on)
- Automation gate: a campaign with `conv30 < conv_gate` (default 30 — the same
  "30 conversions/30 days" gate `google-ads-bidding-strategy/SKILL.md`
  documents) running ANY automated strategy (`current_tier >= 1`) is flagged
  **"Over-automated (under-data)"** — the Critical case — regardless of the
  plain tier-gap comparison.

Campaigns with **zero spend** in the window cannot be assessed at all
(`status="no_spend"`) and campaigns on a bidding strategy this model does not
map to a tier (`status="unsupported_strategy"`, e.g. Commission, Target
Impression Share) are held out from classification. Both statuses are kept —
no-row-loss — never silently dropped.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_SHARED = HERE.parents[2] / "_shared"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

import analytics  # noqa: E402  (_shared/analytics.py — concentration/signals/pre_score)

GATE_LADDER = [10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0, 75.0, 100.0]

DEFAULT_PARAMS = {
    "conv_target": 30.0,             # conv30 at which the volume component saturates to 100
    "conv_gate": 30.0,                # automation gate: conv30 below this + automated = Critical
    "tier_gap_threshold": 1.0,        # tiers of difference before flagging a plain mismatch
    "band_edge_1": 30.0,              # Manual CPC/Max Clicks -> Enhanced CPC
    "band_edge_2": 50.0,              # Enhanced CPC -> Target CPA/Max Conversions
    "band_edge_3": 70.0,              # Target CPA/Max Conversions -> Target ROAS/Max Conv Value
    "band_edge_4": 85.0,              # Target ROAS/Max Conv Value -> + Smart Bidding Exploration
    "volume_weight": 0.40,
    "value_weight": 0.30,
    "tracking_weight": 0.30,
    "assumed_value_score": 50.0,      # neutral assumption when value-variance judgment is absent
    "assumed_tracking_score": 50.0,   # neutral assumption when tracking-confidence judgment is absent
}

TIER_LABELS = [
    "Manual CPC / Maximize Clicks",
    "Enhanced CPC",
    "Target CPA / Maximize Conversions",
    "Target ROAS / Maximize Conversion Value",
    "Target ROAS + Smart Bidding Exploration",
]

# Fixed (not tunable) — which GAQL bidding_strategy_type enum (or Google Ads UI
# "Bid strategy type" export label, which normalizes to the same token) maps to
# which tier. Anything absent here -> status="unsupported_strategy".
STRATEGY_TIERS = {
    "MANUAL_CPC": 0, "MANUAL_CPM": 0, "MANUAL_CPV": 0, "PERCENT_CPC": 0,
    "TARGET_SPEND": 0, "MAXIMIZE_CLICKS": 0,
    "ENHANCED_CPC": 1,
    "TARGET_CPA": 2, "MAXIMIZE_CONVERSIONS": 2,
    "TARGET_ROAS": 3, "MAXIMIZE_CONVERSION_VALUE": 3,
}
# Tier 4 (Target ROAS + Exploration) is a judgment bump on top of TARGET_ROAS —
# ai_max_setting.enable_ai_max is the closest MCP-queryable proxy the SKILL.md
# already pulls; UI exports rarely carry it, so it defaults False (never assumed).
_TIER4_BASE_STRATEGY = "TARGET_ROAS"

# NOT part of the shared analytics.JS_MIRROR kernel-mirror contract (these are
# this skill's own weights, not a generic primitive) — mirrored by hand as an
# identical object literal in bidding_spec.JS_KERNEL. Keep the two in sync;
# tests/js_kernel_parity.py is the regression guard (asserts `severity`
# equality on every fixture row/param scenario), not an auto-discovered gate.
SEVERITY_WEIGHTS = {"under_data_automated": 8.0, "over_automated": 3.0, "under_automated": 2.0}


class FindingsError(ValueError):
    """Raised when the findings JSON is missing/invalid."""


# Control-total contract shared with scripts/assemble_findings.py: per findings
# array, the numeric fields whose sums are embedded as meta.reconciliation and
# re-verified here on every load. Catches transcription drift and hand-edits.
RECONCILE_ARRAYS = {"campaigns": ["cost", "conv30", "value"]}


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
                "on sys.path — run via build_bidding_report.py, or add the plugin's "
                "_shared/ to sys.path before loading") from e
        try:
            reconcile.verify(data, RECONCILE_ARRAYS)
        except reconcile.ReconciliationError as e:
            raise FindingsError(str(e)) from e
    return data


def resolve_params(raw: dict | None) -> dict:
    p = dict(DEFAULT_PARAMS)
    for k, v in (raw or {}).items():
        if v is not None and k in DEFAULT_PARAMS:
            p[k] = v
    return p


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _optnum(v):
    """Optional judgment score: a real number passes through, anything else
    (missing / None / non-numeric) means "no signal" — never coerced to 0."""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _round_half_up(x: float, nd: int) -> float:
    """Half-up rounding for x >= 0 — the same kernel-mirror contract as
    `_shared/analytics.py` (duplicated here rather than importing a private
    helper; mirrored verbatim in JS_KERNEL and the xlsx ROUND() formulas)."""
    q = 10 ** nd
    return __import__("math").floor(x * q + 0.5) / q


def normalize_strategy(raw) -> str:
    """GAQL enum ('TARGET_CPA') and Google Ads UI export label ('Target CPA')
    both normalize to the same token so STRATEGY_TIERS matches either input path."""
    return re.sub(r"[^A-Za-z0-9]+", "_", str(raw or "").strip()).strip("_").upper()


def strategy_tier(strategy_norm: str, ai_max_enabled: bool):
    """Fixed strategy -> tier lookup, or None (unsupported/unrecognized)."""
    base = STRATEGY_TIERS.get(strategy_norm)
    if base is None:
        return None
    if base == 3 and strategy_norm == _TIER4_BASE_STRATEGY and ai_max_enabled:
        return 4
    return base


def tier_for_score(score: float, params: dict) -> int:
    """Maturity score -> recommended tier via the four tunable band edges.
    Edges are sorted defensively so an out-of-order tune stays monotonic."""
    edges = sorted(_num(params[f"band_edge_{i}"]) for i in (1, 2, 3, 4))
    tier = 0
    for e in edges:
        if score >= e:
            tier += 1
    return tier


def _campaign_key(c: dict):
    return c.get("campaign_id")


def dedupe_campaigns(campaigns: list) -> list:
    """Merge rows sharing campaign_id: sum cost/conv30/value; carry the first
    non-empty attribute (name, strategy, ai_max, judgment scores) — attributes
    are campaign-level and identical across any split (e.g. by segment)."""
    merged: dict = {}
    order: list = []
    for c in campaigns:
        k = _campaign_key(c)
        if k not in merged:
            merged[k] = {
                "campaign_id": k, "campaign": c.get("campaign", str(k)),
                "bidding_strategy_type": c.get("bidding_strategy_type", ""),
                "ai_max_enabled": bool(c.get("ai_max_enabled")),
                "campaign_status": c.get("status", ""),
                "value_score": _optnum(c.get("value_score")),
                "tracking_score": _optnum(c.get("tracking_score")),
                "cost": 0.0, "conv30": 0.0, "value": 0.0,
            }
            order.append(k)
        m = merged[k]
        m["cost"] += _num(c.get("cost"))
        m["conv30"] += _num(c.get("conv30"))
        m["value"] += _num(c.get("value"))
        if not m["campaign"] and c.get("campaign"):
            m["campaign"] = c["campaign"]
        if not m["bidding_strategy_type"] and c.get("bidding_strategy_type"):
            m["bidding_strategy_type"] = c["bidding_strategy_type"]
        if not m["campaign_status"] and c.get("status"):
            m["campaign_status"] = c["status"]
        if c.get("ai_max_enabled"):
            m["ai_max_enabled"] = True
        if m["value_score"] is None:
            m["value_score"] = _optnum(c.get("value_score"))
        if m["tracking_score"] is None:
            m["tracking_score"] = _optnum(c.get("tracking_score"))
    return [merged[k] for k in order]


def _confidence(value_score, tracking_score) -> str:
    have = (value_score is not None) + (tracking_score is not None)
    return "measured" if have == 2 else ("partial" if have == 1 else "assumed")


def _liveness_note(row: dict) -> str:
    """Conditional-phrasing seam for recently_active rows (HM-603) — the note
    the recommendation layer surfaces so a paused/idle campaign's bid-strategy
    advice is hedged. Empty for live (nothing to caveat) and dormant (generates
    no finding). This skill pulls current-window spend but NO prior-window spend
    (two-band-derivable — see build_universe), so the only recently_active paths
    are paused-mid-window (not ENABLED, spent) and enabled-but-idle."""
    if row.get("liveness") != "recently_active":
        return ""
    enabled = str(row.get("campaign_status") or "").strip().upper() == "ENABLED"
    cost = _num(row.get("cost"))
    if not enabled and cost > 0:
        return (f"Paused/removed mid-window after spending {cost:,.2f} — confirm the "
                "bid strategy intent before acting.")
    if enabled and cost <= 0:
        return "Enabled but no spend in the window — confirm it should be running before retuning bids."
    return ""


def build_universe(campaigns: list) -> list:
    """Every deduped campaign, annotated with its fixed strategy tier and a
    status. status = 'scored' (spend > 0 and a recognized strategy) /
    'no_spend' (0 cost in the window — nothing to assess) /
    'unsupported_strategy' (strategy this model does not map to a tier).
    Nothing dropped."""
    universe = []
    for c in dedupe_campaigns(campaigns):
        strategy_norm = normalize_strategy(c["bidding_strategy_type"])
        tier = strategy_tier(strategy_norm, c["ai_max_enabled"])
        if c["cost"] <= 0:
            status = "no_spend"
        elif tier is None:
            status = "unsupported_strategy"
        else:
            status = "scored"
        universe.append({
            "campaign_id": c["campaign_id"], "campaign": c["campaign"],
            "bidding_strategy": c["bidding_strategy_type"],
            "bidding_strategy_norm": strategy_norm,
            "ai_max_enabled": c["ai_max_enabled"],
            "campaign_status": c["campaign_status"],
            "current_tier": tier,
            "current_label": TIER_LABELS[tier] if tier is not None else "",
            "conv30": c["conv30"], "cost": c["cost"], "value": c["value"],
            "value_score": c["value_score"], "tracking_score": c["tracking_score"],
            "confidence": _confidence(c["value_score"], c["tracking_score"]),
            "status": status,
        })
    # Campaign liveness (HM-603): TWO-BAND-DERIVABLE — this skill pulls
    # campaign.status (campaign_status) and current-window spend (cost) but NO
    # prior-window spend, so prior_spend_key=None. All three bands stay reachable
    # (the "spent only in the prior window" recently_active path is the one that
    # is unavailable). Severity is gated on live+recently_active in classify_row;
    # dormant rows stay present-but-tagged (no-row-loss). NOTE the row's `status`
    # is the PIPELINE status (scored/no_spend/unsupported_strategy) — the raw
    # campaign.status lives under `campaign_status` to avoid the collision.
    universe = analytics.segment_liveness(universe, status_key="campaign_status",
                                          spend_key="cost", prior_spend_key=None)
    for r in universe:
        r["liveness_note"] = _liveness_note(r)
    universe.sort(key=lambda r: r["cost"], reverse=True)
    return universe


def classify_row(row: dict, params: dict) -> dict:
    """Return the maturity score + mismatch signal for one row at the given
    params. Rows not status='scored' — and dormant rows (HM-603: not ENABLED,
    zero spend in the window — a long-dead campaign that can never be a
    recommendation source) — are never classified. The dormant guard mirrors the
    JS kernel and the xlsx Mismatch formula; a scored row can never be dormant
    (spend>0 ⇒ at least recently_active), so this only ever fires on held-out
    rows, but it is asserted explicitly for correctness + the tag."""
    if row.get("liveness") == "dormant" or row["status"] != "scored":
        return {"volume_score": None, "value_score_used": None, "tracking_score_used": None,
                "maturity_score": None, "recommended_tier": None, "recommended_label": "",
                "tier_gap": None, "under_data": None, "mismatch": "", "flags": [], "severity": 0.0}

    conv_target = _num(params["conv_target"])
    volume_score = 0.0 if conv_target <= 0 else min(100.0, max(0.0, 100.0 * row["conv30"] / conv_target))
    value_score = row["value_score"] if row["value_score"] is not None else params["assumed_value_score"]
    tracking_score = row["tracking_score"] if row["tracking_score"] is not None else params["assumed_tracking_score"]
    maturity = _round_half_up(
        volume_score * params["volume_weight"] + value_score * params["value_weight"]
        + tracking_score * params["tracking_weight"], 2)
    recommended_tier = tier_for_score(maturity, params)
    current_tier = row["current_tier"]
    tier_gap = current_tier - recommended_tier

    sig_row = {"conv30": row["conv30"], "tier_gap": tier_gap}
    rules = [
        {"id": "under_data", "key": "conv30", "op": "lt", "value": params["conv_gate"]},
        {"id": "over_automated", "key": "tier_gap", "op": "gt", "value": params["tier_gap_threshold"]},
        {"id": "under_automated", "key": "tier_gap", "op": "lt", "value": -params["tier_gap_threshold"]},
    ]
    base_flags = analytics.signals([sig_row], rules)[0]

    if "under_data" in base_flags and current_tier >= 1:
        composite, mismatch = ["under_data_automated"], "Over-automated (under-data)"
    elif "over_automated" in base_flags:
        composite, mismatch = ["over_automated"], "Over-automated"
    elif "under_automated" in base_flags:
        composite, mismatch = ["under_automated"], "Under-automated"
    else:
        composite, mismatch = [], ""
    severity = analytics.pre_score({"flags": composite}, SEVERITY_WEIGHTS)

    return {
        "volume_score": round(volume_score, 2), "value_score_used": value_score,
        "tracking_score_used": tracking_score, "maturity_score": maturity,
        "recommended_tier": recommended_tier, "recommended_label": TIER_LABELS[recommended_tier],
        "tier_gap": tier_gap, "under_data": "under_data" in base_flags,
        "mismatch": mismatch, "flags": base_flags, "severity": severity,
    }


def classify(universe: list, params: dict) -> list:
    out = []
    for r in universe:
        rr = dict(r)
        rr.update(classify_row(r, params))
        out.append(rr)
    return out


def summarize(classified: list) -> dict:
    scored = [r for r in classified if r["status"] == "scored"]
    no_spend = [r for r in classified if r["status"] == "no_spend"]
    unsupported = [r for r in classified if r["status"] == "unsupported_strategy"]
    over_ud = [r for r in scored if r["mismatch"] == "Over-automated (under-data)"]
    over = [r for r in scored if r["mismatch"] == "Over-automated"]
    under = [r for r in scored if r["mismatch"] == "Under-automated"]
    aligned = [r for r in scored if r["mismatch"] == ""]
    conc = analytics.concentration(classified, "cost", top_n=3)
    return {
        "universe": len(classified), "scored": len(scored),
        "no_spend": len(no_spend), "unsupported_strategy": len(unsupported),
        "over_automated_under_data": len(over_ud), "over_automated": len(over),
        "under_automated": len(under), "aligned": len(aligned),
        "total_mismatched": len(over_ud) + len(over) + len(under),
        "avg_maturity_score": (round(sum(r["maturity_score"] for r in scored) / len(scored), 2)
                               if scored else 0.0),
        "critical_spend": round(sum(r["cost"] for r in over_ud), 2),
        "spend_top3_share": conc["top_share"], "spend_hhi": conc["hhi"],
        "spend_effective_n": conc["effective_n"],
    }


def gate_sensitivity(universe: list, params: dict, ladder: list | None = None) -> list:
    """How the automation-gate flag count moves as conv_gate changes, holding
    every other param at `params` (mirrors the reference skill's cost-multiple
    sensitivity ladder)."""
    ladder = ladder or GATE_LADDER
    out = []
    for g in ladder:
        p = dict(params); p["conv_gate"] = g
        s = summarize(classify(universe, p))
        out.append({"conv_gate": g, "over_automated_under_data": s["over_automated_under_data"],
                    "total_mismatched": s["total_mismatched"],
                    "is_current": abs(g - params["conv_gate"]) < 1e-9})
    return out


def borderline(classified: list, params: dict, top_n: int = 15) -> list:
    """Scored campaigns whose maturity score sits closest to a tier boundary —
    worth watching even when not currently flagged (the near-miss layer)."""
    edges = [params[f"band_edge_{i}"] for i in (1, 2, 3, 4)]
    pool = []
    for r in classified:
        if r["status"] != "scored":
            continue
        dist = min(abs(r["maturity_score"] - e) for e in edges)
        pool.append({**r, "distance_to_edge": round(dist, 2)})
    pool.sort(key=lambda r: r["distance_to_edge"])
    return pool[:top_n]


def provenance(findings: dict, params: dict) -> dict:
    meta = findings.get("meta") or {}
    return {
        "client_name": meta.get("client_name", ""),
        "account_id": meta.get("account_id", ""),
        "currency": meta.get("currency", ""),
        "window_30d": meta.get("window_30d", ""),
        "generated": meta.get("generated", ""),
        "source": meta.get("source", "mcp"),
        "params": dict(params),
    }


def _build_meta(findings: dict, universe: list, params: dict) -> dict:
    """meta pass-through + the assumed-judgment-score auto-stamp (HM-604): when
    ANY row's value_score/tracking_score fell back to the tunable neutral
    default (confidence "partial"/"assumed" — see _confidence), the resolved
    default(s) get an honest basis=model_default entry, never silently
    presented as a measured judgment call."""
    meta = dict(findings.get("meta") or {})
    entries = [a for a in (meta.get("assumptions") or [])
              if a["param"] not in ("assumed_value_score", "assumed_tracking_score")]
    used_value = any(r["value_score"] is None for r in universe)
    used_tracking = any(r["tracking_score"] is None for r in universe)
    if used_value:
        entries.append({"param": "assumed_value_score", "value": params["assumed_value_score"],
                        "basis": "model_default",
                        "note": "one or more campaigns had no ValueVarianceScore judgment input — "
                                f"used the neutral default {params['assumed_value_score']:.0f}. Supply "
                                "a real score via --judgment to replace it."})
    if used_tracking:
        entries.append({"param": "assumed_tracking_score", "value": params["assumed_tracking_score"],
                        "basis": "model_default",
                        "note": "one or more campaigns had no TrackingConfidenceScore judgment input "
                                f"— used the neutral default {params['assumed_tracking_score']:.0f}. "
                                "Supply a real score via --judgment to replace it."})
    if entries:
        meta["assumptions"] = entries
    return meta


def compute_model(findings: dict) -> dict:
    """Assemble the full model at the resolved params. JSON-serializable —
    safe to embed in the HTML explorer for live recompute. This is the single
    source of truth; presentation (md sections, html spec, xlsx layout) lives
    in bidding_spec / bidding_xlsx_spec and the shared render toolkit."""
    params = resolve_params(findings.get("params"))
    universe = build_universe(findings["campaigns"])
    classified = classify(universe, params)
    return {
        "provenance": provenance(findings, params),
        "params": params,
        "rows": classified,
        "summary": summarize(classified),
        "gate_sensitivity": gate_sensitivity(universe, params),
        "borderline": borderline(classified, params),
        "tier_labels": TIER_LABELS,
        # Pass-through so every renderer sees the assembler's meta.assumptions
        # and meta.source verbatim, plus the auto-stamped judgment fallback.
        "meta": _build_meta(findings, universe, params),
        "gate_ladder": GATE_LADDER,
        "_universe": universe,   # unclassified rows for renderers that re-tune live
    }
