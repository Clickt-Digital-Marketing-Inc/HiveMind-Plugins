#!/usr/bin/env python3
"""Quality Score forensics — model / single source of truth (stdlib only).

Every renderer (md, html, xlsx) consumes this model via the shared toolkit
(`_shared/render`). The findings-JSON contract is authoritative in
`references/quality-score-report.md`.

One row per keyword. Low-QS keywords (QS < threshold) are bucketed by their
PRIMARY failing component — the QS triad localizes the root cause:
  Landing page  — post_click_quality_score below target
  Ad relevance  — creative_quality_score below target
  Expected CTR  — search_predicted_ctr below target
  Critical      — all three components below target
  Other         — QS is low but no single component is below target
A keyword is also flagged a low-CTR **pause** candidate (independent of bucket)
when impressions >= min AND CTR < max AND 0 conversions.
Unscored keywords (quality_score 0/null = too little data, NOT a literal 0) are
kept with status="unscored" and never bucketed or averaged in.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import analytics  # _shared module; on sys.path via the builders/tests (see
                   # build_qs_report.py / build_qs_workbook.py / test_qs.py)

# component rating -> rank (the GAQL enums map onto 1/2/3; 0 = unknown)
_RANK = {"BELOW_AVERAGE": 1, "AVERAGE": 2, "ABOVE_AVERAGE": 3,
         "BELOW AVERAGE": 1, "ABOVE AVERAGE": 3,
         "below average": 1, "average": 2, "above average": 3, "": 0, None: 0}
_RANK_LABEL = {0: "Unknown", 1: "Below average", 2: "Average", 3: "Above average"}
TARGET_OPTIONS = [["Below average", 1], ["Average", 2], ["Above average", 3]]

DEFAULT_PARAMS = {
    "qs_low_threshold": 5,      # QS strictly below this is "in scope"
    "component_target": 2,      # a component below this rank is the bottleneck (2 = flag Below avg)
    "pause_min_impr": 100,      # low-CTR pause: impressions at/above this
    "pause_max_ctr": 0.01,      # ...and CTR below this
}

_COMPONENTS = [("lp", "Landing page"), ("ar", "Ad relevance"), ("ctr_q", "Expected CTR")]


class FindingsError(ValueError):
    """Raised when the findings JSON is missing/invalid."""


# Control-total contract shared with scripts/assemble_findings.py: per findings
# array, the numeric fields whose sums are embedded as meta.reconciliation and
# re-verified here on every load. Catches transcription drift and hand-edits.
RECONCILE_ARRAYS = {
    "keywords": ["cost", "clicks", "impressions", "conversions", "quality_score"],
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
    if not isinstance(data.get("keywords"), list):
        raise FindingsError("findings JSON missing required array 'keywords'")
    if (data.get("meta") or {}).get("reconciliation"):
        try:
            import reconcile  # lazy: _shared module, on sys.path via the builders/tests
        except ImportError as e:
            raise FindingsError(
                "findings carry reconciliation totals but the _shared toolkit is not "
                "on sys.path — run via build_qs_report.py, or add the plugin's "
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


def _rank(v) -> int:
    if isinstance(v, (int, float)) and v in (0, 1, 2, 3):
        return int(v)
    return _RANK.get(str(v).strip(), _RANK.get(str(v).strip().upper(), 0))


def _r2(x):
    return math.floor(float(x) * 100 + 0.5) / 100


def _key(k: dict) -> tuple:
    return (k.get("ad_group_id"), str(k.get("keyword", "")), str(k.get("match_type", "")).upper())


def dedupe_keywords(keywords: list) -> list:
    """Merge rows sharing (ad_group_id, keyword, match_type): sum impressions/
    clicks/cost/conversions; QS and the component ranks are point-in-time, taken
    from the first occurrence."""
    merged: dict = {}
    order: list = []
    for k in keywords:
        kk = _key(k)
        if kk not in merged:
            merged[kk] = dict(k)
            merged[kk]["impressions"] = 0.0
            merged[kk]["clicks"] = 0.0
            merged[kk]["cost"] = 0.0
            merged[kk]["conversions"] = 0.0
            order.append(kk)
        m = merged[kk]
        m["impressions"] += _num(k.get("impressions"))
        m["clicks"] += _num(k.get("clicks"))
        m["cost"] += _num(k.get("cost"))
        m["conversions"] += _num(k.get("conversions"))
    return [merged[kk] for kk in order]


def build_rows(keywords: list) -> list:
    rows = []
    for k in dedupe_keywords(keywords):
        qs_raw = k.get("quality_score")
        qs = int(qs_raw) if qs_raw not in (None, "", 0, "0") else None
        impr = _num(k.get("impressions"))
        clicks = _num(k.get("clicks"))
        rows.append({
            "ad_group_id": k.get("ad_group_id"),
            "ad_group": k.get("ad_group", ""),
            "campaign": k.get("campaign", ""),
            "keyword": k.get("keyword", ""),
            "match_type": str(k.get("match_type", "")).upper(),
            "qs": qs,
            "lp": _rank(k.get("landing_page_exp")),
            "ar": _rank(k.get("ad_relevance")),
            "ctr_q": _rank(k.get("expected_ctr")),
            "lp_label": _RANK_LABEL[_rank(k.get("landing_page_exp"))],
            "ar_label": _RANK_LABEL[_rank(k.get("ad_relevance"))],
            "ctr_label": _RANK_LABEL[_rank(k.get("expected_ctr"))],
            "impressions": impr, "clicks": clicks, "cost": _num(k.get("cost")),
            "conversions": _num(k.get("conversions")),
            "ctr": (clicks / impr) if impr else 0.0,
            "status": "scored" if qs is not None else "unscored",
        })
    rows.sort(key=lambda r: (r["qs"] if r["qs"] is not None else 99, -r["cost"]))
    return rows


def _belows(row, target):
    return [name for key, name in _COMPONENTS if 0 < row[key] < target]


def classify_row(row: dict, params: dict) -> dict:
    """Bucket a low-QS keyword by its primary failing component. Returns also a
    pause flag (independent of the bucket)."""
    pause = (row["status"] == "scored" and row["impressions"] >= params["pause_min_impr"]
             and row["ctr"] < params["pause_max_ctr"] and row["conversions"] == 0)
    if row["status"] != "scored" or row["qs"] >= params["qs_low_threshold"]:
        return {"bucket": "", "pause": pause}
    target = params["component_target"]
    belows = _belows(row, target)
    if not belows:
        return {"bucket": "Other", "pause": pause}
    if len(belows) == 3:
        return {"bucket": "Critical", "pause": pause}
    # primary = the worst (lowest rank); tie broken by component order LP, AR, CTR
    order = {name: i for i, (_k, name) in enumerate(_COMPONENTS)}
    ranks = {"Landing page": row["lp"], "Ad relevance": row["ar"], "Expected CTR": row["ctr_q"]}
    primary = min(belows, key=lambda n: (ranks[n], order[n]))
    return {"bucket": primary, "pause": pause}


def classify(rows: list, params: dict) -> list:
    out = []
    for r in rows:
        rr = dict(r)
        rr.update(classify_row(r, params))
        out.append(rr)
    return out


_BUCKETS = ("Landing page", "Ad relevance", "Expected CTR", "Critical", "Other")

_COMPONENT_ORDER = {name: i for i, (_k, name) in enumerate(_COMPONENTS)}
_COMPONENT_KEY_OF = {name: key for key, name in _COMPONENTS}


def component_drag(rows: list, params: dict) -> list:
    """Cost + keyword-count drag attributable to each QS component being
    below the component target, across in-scope scored rows. A row with
    several below-target components (e.g. Critical) contributes to EACH one
    — this measures how each component alone drags the account, distinct
    from a row's single primary bucket (classify_row)."""
    target = params["component_target"]
    totals = {name: {"component": name, "cost": 0.0, "keywords": 0}
              for _k, name in _COMPONENTS}
    for r in rows:
        if r["status"] != "scored" or r["qs"] >= params["qs_low_threshold"]:
            continue
        for name in _belows(r, target):
            totals[name]["cost"] += r["cost"]
            totals[name]["keywords"] += 1
    return [totals[name] for _k, name in _COMPONENTS]


def _flag_worst(drag: list) -> list:
    """Attach a cost share + a `signals` flag (id 'worst_factor') marking the
    component(s) carrying the highest below-target cost. Ties are flagged
    together — honest, not arbitrarily broken (the tie-break for a single
    `dominant_component` label happens separately, in component order)."""
    total = sum(d["cost"] for d in drag)
    max_cost = max((d["cost"] for d in drag), default=0.0)
    rows = []
    for d in drag:
        d2 = dict(d)
        d2["share"] = _r2(d2["cost"] / total) if total > 0 else 0.0
        d2["max_cost"] = max_cost
        rows.append(d2)
    flags = analytics.signals(
        rows, [{"id": "worst_factor", "key": "cost", "op": "ge", "value_key": "max_cost"}])
    for d2, f in zip(rows, flags):
        d2["flags"] = f
    return rows


def dominant_factor(rows: list, params: dict) -> dict:
    """Which QS component drags the account most, and where the dominant
    component's drag concentrates across ad groups.

    Uses the shared `_shared/analytics.py` primitives (kernel-mirrored +
    parity-gated) rather than skill-local math: `concentration` over the
    three components' below-target cost locates the dominant factor
    (top_n=1 -> how much the single worst component accounts for), a second
    `concentration` pass over that factor's cost by ad group (top_n=3) shows
    where it concentrates, and `signals` flags the worst factor (ties
    flagged together)."""
    drag = _flag_worst(component_drag(rows, params))
    comp_conc = analytics.concentration(drag, "cost", top_n=1)
    flagged = [d for d in drag if "worst_factor" in d["flags"] and d["cost"] > 0]
    dominant_name = (min(flagged, key=lambda d: _COMPONENT_ORDER[d["component"]])["component"]
                     if flagged else "")

    target = params["component_target"]
    dom_key = _COMPONENT_KEY_OF.get(dominant_name)
    by_ag: dict = {}
    ag_order: list = []
    if dom_key:
        for r in rows:
            if r["status"] != "scored" or r["qs"] >= params["qs_low_threshold"]:
                continue
            if not (0 < r[dom_key] < target):
                continue
            key = r["ad_group_id"]
            if key not in by_ag:
                by_ag[key] = {"ad_group": r["ad_group"], "cost": 0.0, "keywords": 0}
                ag_order.append(key)
            by_ag[key]["cost"] += r["cost"]
            by_ag[key]["keywords"] += 1
    location_rows = sorted((by_ag[k] for k in ag_order), key=lambda d: -d["cost"])
    loc_conc = analytics.concentration(location_rows, "cost", top_n=3)

    dom_cost = next((d["cost"] for d in drag if d["component"] == dominant_name), 0.0)
    return {
        "drag": drag,
        "dominant_component": dominant_name,
        "dominant_cost": _r2(dom_cost),
        "concentration": comp_conc,
        "location": loc_conc,
        "location_rows": location_rows,
    }


def summarize(rows: list, params: dict) -> dict:
    scored = [r for r in rows if r["status"] == "scored"]
    in_scope = [r for r in scored if r["qs"] < params["qs_low_threshold"]]
    buckets = {b: 0 for b in _BUCKETS}
    for r in rows:
        if r.get("bucket") in buckets:
            buckets[r["bucket"]] += 1
    avg_qs = _r2(sum(r["qs"] for r in scored) / len(scored)) if scored else None
    dom = dominant_factor(rows, params)
    return {
        "keywords": len(rows),
        "scored": len(scored),
        "unscored": sum(1 for r in rows if r["status"] == "unscored"),
        "in_scope": len(in_scope),
        "avg_qs": avg_qs,
        "lp": buckets["Landing page"], "ad_rel": buckets["Ad relevance"],
        "exp_ctr": buckets["Expected CTR"], "critical": buckets["Critical"],
        "other": buckets["Other"],
        "pause_candidates": sum(1 for r in rows if r.get("pause")),
        "wasted_low_qs_cost": _r2(sum(r["cost"] for r in in_scope)),
        "dominant_component": dom["dominant_component"],
        "dominant_share_pct": _r2(dom["concentration"]["top_share"] * 100),
        "dominant_location_share_pct": _r2(dom["location"]["top_share"] * 100),
    }


def threshold_sensitivity(rows: list, params: dict) -> list:
    """In-scope (and Critical) counts as the QS-low threshold moves 2..8."""
    out = []
    for t in range(2, 9):
        p = dict(params); p["qs_low_threshold"] = t
        s = summarize(classify(rows, p), p)
        out.append({"qs_low": t, "in_scope": s["in_scope"], "critical": s["critical"],
                    "is_current": t == params["qs_low_threshold"]})
    return out


def provenance(findings: dict, params: dict) -> dict:
    meta = findings.get("meta") or {}
    tgt = _RANK_LABEL.get(params["component_target"], str(params["component_target"]))
    return {
        "client_name": meta.get("client_name", ""),
        "account_id": meta.get("account_id", ""),
        "currency": meta.get("currency", ""),
        "window_90d": meta.get("period", ""),
        "window_30d": f"QS < {params['qs_low_threshold']} · target ≥ {tgt}",
        "generated": meta.get("generated", ""),
        # honesty: dual-input contract (google-ads-foundation/references/
        # artifact-formats.md) — CSV-sourced findings stamp source="user_csv";
        # absent (legacy/MCP findings) defaults to "mcp".
        "source": meta.get("source", "mcp"),
        "params": dict(params),
    }


def compute_model(findings: dict) -> dict:
    params = resolve_params(findings.get("params"))
    rows = build_rows(findings["keywords"])
    classified = classify(rows, params)
    return {
        "provenance": provenance(findings, params),
        "params": params,
        "rows": classified,
        "summary": summarize(classified, params),
        "dominant_factor": dominant_factor(classified, params),
        "threshold_sensitivity": threshold_sensitivity(rows, params),
        "target_options": TARGET_OPTIONS,
        "_rows": rows,
    }
