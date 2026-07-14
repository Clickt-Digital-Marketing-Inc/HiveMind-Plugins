#!/usr/bin/env python3
"""Performance Max momentum filter — model / single source of truth (stdlib only).

Every renderer (md, html, xlsx) imports this module so the classification logic
can never diverge across formats. No third-party dependencies.

The findings-JSON input contract is documented authoritatively in
`references/pmax-momentum-filter.md` (do not duplicate the schema here).

One Performance Max campaign = one row, compared across two equal windows
(last 14 days vs the previous 14 days). Two blocks, each AND-joined:

  Block 1 — scaling winner:   conv(last) > conv(prev)
            AND roas(last) > roas_up_multiple   * roas(prev)
            AND impr(last) > 0 AND cost(last) > min_cost
  Block 2 — declining loser:  conv(last) < conv(prev)
            AND roas(last) < roas_down_multiple * roas(prev)
            AND impr(prev) > 0 AND cost(prev) > min_cost

A campaign with no impressions in EITHER window has no trend to evaluate, so it
is kept with status="no_activity" and never classified or dropped. min_cost
defaults to 0.0 — i.e. the bare "cost > 0" rule — but is tunable to suppress
noise from tiny-spend campaigns.

M1.4 deepening (HM-538) adds two structural diagnostics on top of the momentum
blocks, both built from the shared `_shared/analytics.py` primitives so their
arithmetic is parity-gated at the primitive level (see
references/pmax-momentum-filter.md '#asset-group-concentration' and
'#cannibalization-heuristic' for the authoritative rules):

  asset_group_concentration(asset_groups, params) — per-campaign concentration
    (top-1 asset-group share / HHI / effective-N) over the optional `asset_groups`
    findings array. Flags "concentration_risk" when the dominant asset group
    carries >= concentration_top_share_threshold of last-window spend across
    2+ active asset groups.

  cannibalization(rows, search_campaigns, params) — heuristic PMax-vs-Search
    overlap: pairs each active PMax campaign with Search campaigns whose
    normalized name shares a theme token, then flags "cannibalization_risk"
    when the PMax campaign's share of the paired last-window spend clears
    cannibalization_share_threshold. NAME heuristic only — not verified
    keyword/audience overlap (the API exposes no such cross-campaign metric).

Both `asset_groups` and `search_campaigns` are OPTIONAL findings arrays —
absent (or omitted from meta.reconciliation) findings still compute a full
momentum model; the two diagnostics are simply empty lists.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# Sensitivity ladders (each includes the rule default so a default run flags one
# "current" step). Block 1 relaxes/tightens the up-multiple; Block 2 the down.
UP_LADDER = [1.25, 1.50, 1.75, 2.00, 2.50, 3.00]
DOWN_LADDER = [0.25, 0.40, 0.50, 0.60, 0.75, 0.90]

DEFAULT_PARAMS = {
    "roas_up_multiple": 1.50,    # Block 1: roas(last) must exceed this × roas(prev)
    "roas_down_multiple": 0.50,  # Block 2: roas(last) must fall below this × roas(prev)
    "min_cost": 0.0,             # spend floor per window (0.0 == the literal "cost > 0")
    # M1.4 — asset-group concentration + cannibalization thresholds.
    "concentration_top_share_threshold": 0.80,  # flag when top asset group >= this share (2+ active groups)
    "cannibalization_share_threshold": 0.60,    # flag when PMax's share of paired spend >= this
    "cannibalization_min_cost": 0.0,            # combined (PMax + matched Search) spend floor
}
_FLOAT_PARAMS = ("roas_up_multiple", "roas_down_multiple", "min_cost",
                 "concentration_top_share_threshold", "cannibalization_share_threshold",
                 "cannibalization_min_cost")


class FindingsError(ValueError):
    """Raised when the findings JSON is missing/invalid."""


# Control-total contract shared with scripts/assemble_findings.py: per findings
# array, the numeric fields whose sums are embedded as meta.reconciliation and
# re-verified here on every load. Catches transcription drift and hand-edits.
RECONCILE_ARRAYS = {
    "last_window": ["cost", "clicks", "impressions", "conversions", "conversions_value"],
    "prev_window": ["cost", "clicks", "impressions", "conversions", "conversions_value"],
}

# M1.4 — optional structural arrays (asset-group breakdown, Search-campaign
# snapshot). Verified only when the array key is actually present in the
# findings dict, so findings without them (the pre-M1.4 shape) still load
# clean — see load_findings.
RECONCILE_ARRAYS_OPTIONAL = {
    "asset_groups": ["cost", "clicks", "impressions", "conversions", "conversions_value"],
    "search_campaigns": ["cost", "clicks", "impressions", "conversions", "conversions_value"],
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
    for req in ("last_window", "prev_window"):
        if not isinstance(data.get(req), list):
            raise FindingsError(f"findings JSON missing required array '{req}'")
    if (data.get("meta") or {}).get("reconciliation"):
        try:
            import reconcile  # lazy: _shared module, on sys.path via the builders/tests
        except ImportError as e:
            raise FindingsError(
                "findings carry reconciliation totals but the _shared toolkit is not "
                "on sys.path — run via build_pmax_filter.py, or add the plugin's "
                "_shared/ to sys.path before loading") from e
        try:
            reconcile.verify(data, RECONCILE_ARRAYS)
            # Optional M1.4 arrays are only checked when the findings actually
            # claim them — a pre-M1.4 findings JSON (no asset_groups/
            # search_campaigns keys) is unaffected.
            optional = {k: v for k, v in RECONCILE_ARRAYS_OPTIONAL.items() if k in data}
            if optional:
                reconcile.verify(data, optional)
        except reconcile.ReconciliationError as e:
            raise FindingsError(str(e)) from e
    return data


def resolve_params(raw: dict | None) -> dict:
    p = dict(DEFAULT_PARAMS)
    for k, v in (raw or {}).items():
        if v is not None and k in p:
            p[k] = v
    for k in _FLOAT_PARAMS:
        p[k] = float(p[k])
    return p


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _roas(value, cost) -> float:
    """ROAS = conversions value / cost. Undefined without spend, which we
    represent as 0.0 (no spend → nothing returned to measure)."""
    c = _num(cost)
    return (_num(value) / c) if c > 0 else 0.0


def _index_window(rows: list) -> dict:
    """Sum a window's metrics by campaign_id. Dedupe guard: a campaign should
    appear once per window, but a segmented export could split it."""
    by_id: dict = {}
    order: list = []
    for r in rows:
        cid = r.get("campaign_id")
        if cid not in by_id:
            by_id[cid] = {
                "campaign_id": cid, "campaign": r.get("campaign", ""),
                "impressions": 0.0, "clicks": 0.0, "cost": 0.0,
                "conversions": 0.0, "conversions_value": 0.0,
            }
            order.append(cid)
        m = by_id[cid]
        if not m["campaign"]:
            m["campaign"] = r.get("campaign", "")
        m["impressions"] += _num(r.get("impressions"))
        m["clicks"] += _num(r.get("clicks"))
        m["cost"] += _num(r.get("cost"))
        m["conversions"] += _num(r.get("conversions"))
        m["conversions_value"] += _num(r.get("conversions_value"))
    return by_id


def build_rows(last_window: list, prev_window: list) -> list:
    """One row per campaign (union of both windows) with last/prev metrics,
    pre-computed ROAS, deltas and a status. Nothing dropped. Sorted by last-window
    cost (highest first)."""
    last = _index_window(last_window)
    prev = _index_window(prev_window)
    rows = []
    for cid in list(last.keys()) + [k for k in prev if k not in last]:
        lw = last.get(cid)
        pw = prev.get(cid)
        name = (lw or pw or {}).get("campaign") or str(cid)
        impr_last = (lw or {}).get("impressions", 0.0)
        impr_prev = (pw or {}).get("impressions", 0.0)
        cost_last = (lw or {}).get("cost", 0.0)
        cost_prev = (pw or {}).get("cost", 0.0)
        conv_last = (lw or {}).get("conversions", 0.0)
        conv_prev = (pw or {}).get("conversions", 0.0)
        value_last = (lw or {}).get("conversions_value", 0.0)
        value_prev = (pw or {}).get("conversions_value", 0.0)
        roas_last = _roas(value_last, cost_last)
        roas_prev = _roas(value_prev, cost_prev)
        active = impr_last > 0 or impr_prev > 0
        rows.append({
            "campaign_id": cid, "campaign": name,
            "impr_last": impr_last, "cost_last": cost_last, "conv_last": conv_last,
            "value_last": value_last, "roas_last": roas_last,
            "impr_prev": impr_prev, "cost_prev": cost_prev, "conv_prev": conv_prev,
            "value_prev": value_prev, "roas_prev": roas_prev,
            "conv_delta": round(conv_last - conv_prev, 4),
            "roas_ratio": (round(roas_last / roas_prev, 4) if roas_prev > 0 else None),
            "status": "scored" if active else "no_activity",
        })
    rows.sort(key=lambda r: r["cost_last"], reverse=True)
    return rows


def classify_row(row: dict, params: dict) -> dict:
    """Condition flags + block for one row. no_activity rows are never
    classified (block='')."""
    if row["status"] != "scored":
        return {"conv_up": None, "roas_up": None, "conv_down": None,
                "roas_down": None, "block": ""}
    up, down, floor = params["roas_up_multiple"], params["roas_down_multiple"], params["min_cost"]
    conv_up = row["conv_last"] > row["conv_prev"]
    conv_down = row["conv_last"] < row["conv_prev"]
    roas_up = row["roas_last"] > up * row["roas_prev"]
    roas_down = row["roas_last"] < down * row["roas_prev"]
    block = ""
    if conv_up and roas_up and row["impr_last"] > 0 and row["cost_last"] > floor:
        block = "Block 1"
    elif conv_down and roas_down and row["impr_prev"] > 0 and row["cost_prev"] > floor:
        block = "Block 2"
    return {"conv_up": conv_up, "roas_up": roas_up, "conv_down": conv_down,
            "roas_down": roas_down, "block": block}


def classify(rows: list, params: dict) -> list:
    out = []
    for r in rows:
        rr = dict(r)
        rr.update(classify_row(r, params))
        out.append(rr)
    return out


def summarize(classified: list) -> dict:
    b1 = [r for r in classified if r["block"] == "Block 1"]
    b2 = [r for r in classified if r["block"] == "Block 2"]
    return {
        "block1": len(b1), "block2": len(b2), "total": len(b1) + len(b2),
        "universe": len(classified),
        "scored": sum(1 for r in classified if r["status"] == "scored"),
        "no_activity": sum(1 for r in classified if r["status"] == "no_activity"),
        "winners_spend": round(sum(r["cost_last"] for r in b1), 2),
        "losers_spend": round(sum(r["cost_last"] for r in b2), 2),
        "spend_last": round(sum(r["cost_last"] for r in classified), 2),
        "spend_prev": round(sum(r["cost_prev"] for r in classified), 2),
    }


def sensitivity_up(rows: list, params: dict, ladder: list | None = None) -> list:
    """Block 1 count as the up-multiple changes (other params held current)."""
    ladder = ladder or UP_LADDER
    out = []
    for m in ladder:
        p = dict(params); p["roas_up_multiple"] = m
        s = summarize(classify(rows, p))
        out.append({"multiple": m, "block1": s["block1"],
                    "is_current": abs(m - params["roas_up_multiple"]) < 1e-9})
    return out


def sensitivity_down(rows: list, params: dict, ladder: list | None = None) -> list:
    """Block 2 count as the down-multiple changes (other params held current)."""
    ladder = ladder or DOWN_LADDER
    out = []
    for m in ladder:
        p = dict(params); p["roas_down_multiple"] = m
        s = summarize(classify(rows, p))
        out.append({"multiple": m, "block2": s["block2"],
                    "is_current": abs(m - params["roas_down_multiple"]) < 1e-9})
    return out


def near_misses(rows: list, params: dict, block: str, top_n: int = 15) -> list:
    """Scored rows meeting every condition for `block` EXCEPT (possibly) the ROAS
    bar, ranked by ROAS-ratio closeness. roas_ratio = roas(last)/roas(prev); it is
    None when roas(prev) == 0 (a campaign with no prior return — momentum
    undefined). Block 1 qualifies for any up-multiple <= ratio; Block 2 for any
    down-multiple >= ratio."""
    floor = params["min_cost"]
    pool = []
    for r in rows:
        if r["status"] != "scored":
            continue
        ratio = (r["roas_last"] / r["roas_prev"]) if r["roas_prev"] > 0 else None
        if block == "Block 1":
            if not (r["conv_last"] > r["conv_prev"] and r["impr_last"] > 0 and r["cost_last"] > floor):
                continue
            pool.append({**r,
                         "qualify_if_up_multiple_le": (round(ratio, 3) if ratio is not None else None),
                         "currently_qualifies": r["roas_last"] > params["roas_up_multiple"] * r["roas_prev"]})
        else:
            if not (r["conv_last"] < r["conv_prev"] and r["impr_prev"] > 0 and r["cost_prev"] > floor):
                continue
            pool.append({**r,
                         "qualify_if_down_multiple_ge": (round(ratio, 3) if ratio is not None else None),
                         "currently_qualifies": r["roas_last"] < params["roas_down_multiple"] * r["roas_prev"]})
    if block == "Block 1":  # highest momentum (closest to clearing the up bar) first
        pool.sort(key=lambda r: (r["qualify_if_up_multiple_le"] is None, -(r["qualify_if_up_multiple_le"] or 0.0)))
    else:                    # steepest decline (lowest ratio) first
        pool.sort(key=lambda r: (r["qualify_if_down_multiple_ge"] is None, (r["qualify_if_down_multiple_ge"] or 0.0)))
    return pool[:top_n]


def provenance(findings: dict, params: dict) -> dict:
    """window_90d/window_30d are left EMPTY on purpose: the generic md/html
    renderers hard-label those slots "90-day"/"30-day", which would be untrue for
    this 14-day report. The real windows ride on the custom window_last/window_prev
    keys and are surfaced honestly by the spec (md_params row, html js_extra panel,
    xlsx subtitle)."""
    meta = findings.get("meta") or {}
    return {
        "client_name": meta.get("client_name", ""),
        "account_id": meta.get("account_id", ""),
        "currency": meta.get("currency", ""),
        "source": meta.get("source", "mcp"),  # "mcp" | "user_csv" — dual-input honesty
        "window_90d": "",
        "window_30d": "",
        "window_last": meta.get("window_last", ""),
        "window_prev": meta.get("window_prev", ""),
        "generated": meta.get("generated", ""),
        "params": dict(params),
    }


# ---------------------------------------------------------------------------
# M1.4 — asset-group concentration (HM-538)
# ---------------------------------------------------------------------------
def _index_asset_groups(asset_group_rows: list) -> dict:
    """asset_group rows -> {campaign_id: {"campaign_id", "campaign", "groups": [...]}}
    (insertion order preserved). Mirrors _index_window's dedupe-by-id discipline."""
    by_campaign: dict = {}
    order: list = []
    for r in asset_group_rows or []:
        cid = r.get("campaign_id")
        if cid not in by_campaign:
            by_campaign[cid] = {"campaign_id": cid, "campaign": r.get("campaign", ""), "groups": []}
            order.append(cid)
        entry = by_campaign[cid]
        if not entry["campaign"]:
            entry["campaign"] = r.get("campaign", "")
        entry["groups"].append({
            "asset_group_id": r.get("asset_group_id"),
            "asset_group": r.get("asset_group", ""),
            "cost": _num(r.get("cost")),
        })
    return {cid: by_campaign[cid] for cid in order}


def asset_group_concentration(asset_group_rows: list, params: dict) -> list:
    """One row per PMax campaign with an asset-group breakdown pulled: concentration
    of last-window spend in the campaign's SINGLE LARGEST asset group (top_n=1 —
    an xlsx-formula-friendly MAX/SUM ratio; see references/pmax-momentum-filter.md
    '#asset-group-concentration'). Built on the shared `_shared/analytics.py`
    `concentration` primitive, so the arithmetic is parity-gated at the primitive
    level — this function only does the campaign-grouping + flag-gating around it.

    "concentration_risk" fires only for campaigns with 2+ active (nonzero-cost)
    asset groups — a single-asset-group campaign trivially has a 100% top share,
    which is a structural fact, not a diversification risk."""
    import analytics as _A  # lazy: _shared module, on sys.path via the builders/tests
    by_campaign = _index_asset_groups(asset_group_rows)
    threshold = params["concentration_top_share_threshold"]
    rows = []
    for cid, entry in by_campaign.items():
        conc = _A.concentration(entry["groups"], "cost", top_n=1)
        rows.append({
            "campaign_id": cid, "campaign": entry["campaign"],
            "asset_groups": conc["n"], "asset_groups_active": conc["n_nonzero"],
            "cost": conc["total"], "top_share": conc["top_share"],
            "hhi": conc["hhi"], "effective_n": conc["effective_n"],
            "flaggable_top_share": conc["top_share"] if conc["n_nonzero"] >= 2 else None,
        })
    flags_list = _A.signals(rows, [
        {"id": "concentration_risk", "key": "flaggable_top_share", "op": "ge", "value": threshold},
    ])
    for row, flags in zip(rows, flags_list):
        row["flags"] = flags
        row["risk"] = "concentration_risk" in flags
        row.pop("flaggable_top_share", None)
    rows.sort(key=lambda r: (-r["top_share"], -r["cost"]))
    return rows


# ---------------------------------------------------------------------------
# M1.4 — PMax-vs-Search cannibalization signal (HM-538)
# ---------------------------------------------------------------------------
# Pure channel/type boilerplate — deliberately does NOT strip targeting-scope
# words like "brand"/"nonbrand"/"generic"/"core" (those ARE meaningful theme
# signals for this heuristic; PMax siphoning branded Search traffic is exactly
# the case this rule is meant to catch). See references/pmax-momentum-filter.md
# '#cannibalization-heuristic' for the documented rationale + limitation.
_THEME_STOPWORDS = frozenset({
    "pmax", "performance", "max", "search", "shopping", "display", "video",
    "app", "campaign", "ads", "google", "the", "and", "or", "for",
})
_THEME_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_THEME_SPLIT_RE = re.compile(r"[^A-Za-z0-9]+")


def _theme_tokens(name: str) -> frozenset:
    """Normalize a campaign name into significant theme tokens for the
    cannibalization pairing heuristic: strip 4-digit years and punctuation,
    lowercase, drop channel/type boilerplate and tokens under 3 chars. Two
    campaigns are a candidate cannibalization pair when their token sets
    intersect. NAME heuristic only — see the module/reference docs."""
    s = _THEME_YEAR_RE.sub(" ", name or "")
    s = _THEME_SPLIT_RE.sub(" ", s)
    return frozenset(t for t in s.lower().split()
                     if len(t) >= 3 and t not in _THEME_STOPWORDS)


def cannibalization(rows: list, search_rows: list, params: dict) -> list:
    """Heuristic PMax-vs-Search overlap: pairs each ACTIVE (status="scored") PMax
    campaign with Search campaigns whose normalized name shares a theme token,
    then flags "cannibalization_risk" when the PMax campaign's share of the
    paired last-window spend clears cannibalization_share_threshold AND the
    combined spend clears cannibalization_min_cost. See
    references/pmax-momentum-filter.md '#cannibalization-heuristic' for the
    exact rule, its thresholds, and its documented limitation (a campaign-NAME
    heuristic — not verified keyword/audience overlap, which the API does not
    expose)."""
    import analytics as _A  # lazy: _shared module, on sys.path via the builders/tests
    search_idx = [{
        "campaign_id": r.get("campaign_id"), "campaign": r.get("campaign", ""),
        "cost": _num(r.get("cost")), "conversions": _num(r.get("conversions")),
        "tokens": _theme_tokens(r.get("campaign", "")),
    } for r in (search_rows or [])]
    threshold = params["cannibalization_share_threshold"]
    floor = params["cannibalization_min_cost"]
    out = []
    for r in rows:
        if r["status"] != "scored":
            continue
        p_tokens = _theme_tokens(r["campaign"])
        matches = [s for s in search_idx if p_tokens and (p_tokens & s["tokens"])]
        if not matches:
            continue
        search_cost = round(sum(m["cost"] for m in matches), 4)
        search_conv = round(sum(m["conversions"] for m in matches), 4)
        combined = round(r["cost_last"] + search_cost, 4)
        share = round(r["cost_last"] / combined, 4) if combined > 0 else None
        out.append({
            "campaign_id": r["campaign_id"], "campaign": r["campaign"],
            "matched_search_campaigns": sorted({m["campaign"] for m in matches}),
            "pmax_cost_last": round(r["cost_last"], 2),
            "search_cost_last": search_cost, "search_conversions_last": search_conv,
            "combined_cost_last": combined, "pmax_theme_share": share,
            "flaggable_share": share if (share is not None and combined > floor) else None,
        })
    flags_list = _A.signals(out, [
        {"id": "cannibalization_risk", "key": "flaggable_share", "op": "ge", "value": threshold},
    ])
    for row, flags in zip(out, flags_list):
        row["flags"] = flags
        row["risk"] = "cannibalization_risk" in flags
        row.pop("flaggable_share", None)
    out.sort(key=lambda r: (r["pmax_theme_share"] is None, -(r["pmax_theme_share"] or 0.0)))
    return out


# ---------------------------------------------------------------------------
# M1.4 — advisor recommendations (google-ads-foundation output contract)
# ---------------------------------------------------------------------------
def _money_str(v, cur: str) -> str:
    return f"{float(v):,.2f}" + (f" {cur}" if cur else "")


def recommendations(model: dict) -> list:
    """Prioritized advisor recommendations (Critical/High/Medium), grounded ONLY
    in the model's own asset-group-concentration and cannibalization numbers —
    the emit -> report -> recommend -> offer-apply loop documented in
    google-ads-foundation/references/artifact-formats.md. Every figure here is
    read straight off the model that build_pmax_filter.py just wrote; nothing is
    re-derived or re-narrated from raw data. The momentum blocks (winners/
    losers) are the report's primary narrative and are not duplicated here."""
    cur = model["provenance"]["currency"]
    out = []
    for r in model.get("asset_group_concentration", []):
        if not r.get("risk"):
            continue
        out.append({
            "severity": "High",
            "title": f"Asset-group concentration — {r['campaign']}",
            "detail": (f"{r['top_share'] * 100:.0f}% of last-window spend "
                       f"({_money_str(r['cost'], cur)}) sits in one asset group out of "
                       f"{r['asset_groups_active']} active (effective spread "
                       f"{r['effective_n']:.2f} groups, HHI {r['hhi']:.0f})."),
            "action": ("Add creative/audience-signal variety to the campaign's other "
                       "asset groups (or split the dominant one) before scaling budget — "
                       "a single asset group carrying the campaign is a diversification "
                       "risk if it fatigues or its signal drifts."),
            "artifact": "*_explorer.html (Asset-group concentration) / *.xlsx (Sensitivity tab)",
        })
    for r in model.get("cannibalization", []):
        if not r.get("risk"):
            continue
        matches = ", ".join(r["matched_search_campaigns"])
        out.append({
            "severity": "Medium",
            "title": f"PMax/Search overlap — {r['campaign']}",
            "detail": (f"{r['pmax_theme_share'] * 100:.0f}% of combined last-window spend "
                       f"({_money_str(r['combined_cost_last'], cur)}) across the theme-matched "
                       f"Search campaign(s) [{matches}] is now flowing through this PMax "
                       "campaign."),
            "action": ("Check Search impression share on the matched campaign(s) and this "
                       "PMax campaign's asset-group audience signals before assuming pure "
                       "incrementality — this is a name-theme heuristic, not verified "
                       "keyword/audience overlap."),
            "artifact": "*_explorer.html (Cannibalization signal) / *.xlsx (Sensitivity tab)",
        })
    order = {"Critical": 0, "High": 1, "Medium": 2}
    out.sort(key=lambda r: order[r["severity"]])
    return out


def compute_model(findings: dict) -> dict:
    """Assemble the full model at the resolved params. JSON-serializable — safe to
    embed in the HTML explorer for live recompute. The classification numbers here
    are the single source of truth; the spec's js_kernel and the xlsx formulas
    only mirror them."""
    params = resolve_params(findings.get("params"))
    rows = build_rows(findings["last_window"], findings["prev_window"])
    classified = classify(rows, params)
    pr = provenance(findings, params)
    model = {
        "provenance": pr,
        "params": params,
        "rows": classified,
        "summary": summarize(classified),
        "sensitivity_up": sensitivity_up(rows, params),
        "sensitivity_down": sensitivity_down(rows, params),
        "near_misses_block1": near_misses(rows, params, "Block 1"),
        "near_misses_block2": near_misses(rows, params, "Block 2"),
        "up_ladder": UP_LADDER,
        "down_ladder": DOWN_LADDER,
        "asset_group_concentration": asset_group_concentration(findings.get("asset_groups") or [], params),
        "cannibalization": cannibalization(classified, findings.get("search_campaigns") or [], params),
    }
    model["recommendations"] = recommendations(model)
    return model
