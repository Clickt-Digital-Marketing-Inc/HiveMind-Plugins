#!/usr/bin/env python3
"""Performance Max listing-group waste filter — model / single source of truth.

Stdlib only. Every renderer (md, html, xlsx) imports this module so the
classification logic can never diverge across formats. No third-party deps.

The findings-JSON input contract is documented authoritatively in
`references/pmax-listing-waste-filter.md` (do not duplicate the schema here).

Two blocks, each benchmarked against the unit's OWN campaign (last 30 days), with
a single tunable "expensiveness factor" F (default 1.50):
  Block 1 — expensive converters:  conv(unit) > 0  AND  cost/conv(unit) > F × cost/conv(campaign)
  Block 2 — zero-conversion waste:  conv(unit) = 0  AND  clicks(unit) > F × clicks/conv(campaign)
                                    AND  conv(campaign) > 0
A unit's campaign with 0 conversions (30d) has an undefined cost/conv and
clicks/conv benchmark, so its units are kept with status="no_benchmark" and never
classified or dropped.

The same engine classifies TWO universes against the same campaign benchmark:
  rows  — listing-group partitions   (asset_group_product_group_view)
  items — individual products / item-id (shopping_performance_view)
Both are optional; an absent universe is simply empty.

Tier concentration + listing signal (HM-539). Each universe (partitions,
products) is also read as a "tier" set: `analytics.concentration` measures how
much of the universe's 30-day spend sits in its top-N units (top_share / HHI /
effective-N), and a per-row "tier signal" flags units that are BOTH
over-concentrated (their own cost_share of the universe exceeds
`concentration_share_min`) AND weak on ROAS (`conversions_value / cost` below
`weak_roas_max`) — i.e. spend concentrated in a tier that isn't paying back.
This is independent of the expensiveness-factor blocks: a unit can carry a
tier signal whether or not it also qualifies Block 1/2. The primitives come
from `_shared/analytics.py` (kernel-mirrored verbatim in `pmax_listing_spec`'s
`js_kernel` and in the xlsx formulas — the Node<->Python parity gate holds
both to the same arithmetic).
"""
from __future__ import annotations

import json
from pathlib import Path

try:
    import analytics  # _shared module; callers put `_shared` on sys.path first
except ImportError as e:
    raise ImportError(
        "pmax_listing_core needs the plugin's _shared/ on sys.path (analytics.py) "
        "— run via build_pmax_listing_filter.py / build_pmax_listing_workbook.py, "
        "or add the plugin's _shared/ to sys.path before importing this module"
    ) from e

FACTOR_LADDER = [2.0, 1.75, 1.5, 1.25, 1.0, 0.75, 0.5]

DEFAULT_PARAMS = {
    "expensiveness_factor": 1.50,
    # Tier concentration + signal (HM-539) — see module docstring.
    "concentration_top_n": 3,
    "concentration_share_min": 0.30,
    "weak_roas_max": 1.0,
}


class FindingsError(ValueError):
    """Raised when the findings JSON is missing/invalid."""


# Control-total contract shared with scripts/assemble_findings.py: per findings
# array, the numeric fields whose sums are embedded as meta.reconciliation and
# re-verified here on every load. Catches transcription drift and hand-edits.
# (The structural labels pull carries no metrics, so nothing of it is summed.)
RECONCILE_ARRAYS = {
    "listing_groups": ["cost", "clicks", "impressions", "conversions", "conversions_value"],
    "products": ["cost", "clicks", "impressions", "conversions", "conversions_value"],
    "benchmarks": ["cost", "clicks", "conversions"],
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
    if not isinstance(data.get("benchmarks"), list):
        raise FindingsError("findings JSON missing required array 'benchmarks'")
    for opt in ("listing_groups", "products"):
        if opt in data and not isinstance(data[opt], list):
            raise FindingsError(f"findings JSON '{opt}' must be an array if present")
    # Presence, not truthiness: a key present with an empty array is a valid empty
    # universe (e.g. a feedless lead-gen account has zero retail listing groups AND
    # zero products — both legitimately []). Only an ABSENT key means the source
    # was never pulled/assembled.
    if "listing_groups" not in data and "products" not in data:
        raise FindingsError(
            "findings JSON must contain at least one of 'listing_groups' or 'products'")
    if (data.get("meta") or {}).get("reconciliation"):
        try:
            import reconcile  # lazy: _shared module, on sys.path via the builders/tests
        except ImportError as e:
            raise FindingsError(
                "findings carry reconciliation totals but the _shared toolkit is not "
                "on sys.path — run via build_pmax_listing_filter.py, or add the "
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
    p["expensiveness_factor"] = float(p["expensiveness_factor"])
    p["concentration_top_n"] = int(p["concentration_top_n"])
    p["concentration_share_min"] = float(p["concentration_share_min"])
    p["weak_roas_max"] = float(p["weak_roas_max"])
    return p


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


# --------------------------------------------------------------------------
# normalize the two input shapes into one common "unit" dict
# --------------------------------------------------------------------------
def _unit_from_listing_group(t: dict) -> dict:
    return {
        "campaign_id": t.get("campaign_id"),
        "campaign": t.get("campaign", ""),
        "group": t.get("asset_group", ""),
        "code": t.get("listing_group_id", ""),
        "label": t.get("listing_group", "") or "Everything else",
        "dimension": t.get("dimension", ""),
        "impressions": _num(t.get("impressions")),
        "clicks": _num(t.get("clicks")),
        "cost": _num(t.get("cost")),
        "conv": _num(t.get("conversions")),
        "value": _num(t.get("conversions_value")),
    }


def _unit_from_product(t: dict) -> dict:
    return {
        "campaign_id": t.get("campaign_id"),
        "campaign": t.get("campaign", ""),
        "group": "",
        "code": t.get("item_id", ""),
        "label": t.get("title", "") or t.get("item_id", ""),
        "dimension": "product_item_id",
        "impressions": _num(t.get("impressions")),
        "clicks": _num(t.get("clicks")),
        "cost": _num(t.get("cost")),
        "conv": _num(t.get("conversions")),
        "value": _num(t.get("conversions_value")),
    }


def _unit_key(u: dict) -> tuple:
    return (u.get("campaign_id"), str(u.get("group", "")), str(u.get("code", "")),
            str(u.get("label", "")))


def dedupe_units(units: list) -> list:
    """Merge units sharing (campaign_id, group, code, label): sum
    impressions/clicks/cost/conv/value and recompute CTR. Foundation rule:
    dedupe by key before counting (a key can legitimately appear split by a
    segment such as device)."""
    merged: dict = {}
    order: list = []
    for u in units:
        k = _unit_key(u)
        if k not in merged:
            merged[k] = {
                "campaign_id": u["campaign_id"], "campaign": u["campaign"],
                "group": u["group"], "code": u["code"], "label": u["label"],
                "dimension": u["dimension"],
                "impressions": 0.0, "clicks": 0.0, "cost": 0.0, "conv": 0.0, "value": 0.0,
            }
            order.append(k)
        m = merged[k]
        for f in ("impressions", "clicks", "cost", "conv", "value"):
            m[f] += u[f]
    for k in order:
        m = merged[k]
        m["ctr"] = (m["clicks"] / m["impressions"]) if m["impressions"] else 0.0
    return [merged[k] for k in order]


def build_benchmarks(rows: list) -> dict:
    bench = {}
    for c in rows:
        conv = _num(c.get("conversions"))
        cost = _num(c.get("cost"))
        clicks = _num(c.get("clicks"))
        bench[c.get("campaign_id")] = {
            "campaign_id": c.get("campaign_id"),
            "name": c.get("campaign", str(c.get("campaign_id"))),
            "clicks": clicks,
            "cost": cost,
            "conv": conv,
            "cpa": (cost / conv) if conv > 0 else None,
            "clicks_per_conv": (clicks / conv) if conv > 0 else None,
        }
    return bench


def build_universe(units: list, bench: dict) -> list:
    """Every deduped unit, annotated with its campaign benchmark and a status.
    status = 'scored' (campaign has a usable cost/conv benchmark, i.e. campaign
    conversions > 0) or 'no_benchmark' (campaign absent or 0 conversions in 30d).
    Nothing dropped."""
    universe = []
    for u in dedupe_units(units):
        b = bench.get(u["campaign_id"])
        scored = b is not None and b["cpa"] is not None
        conv = u["conv"]
        universe.append({
            "campaign_id": u["campaign_id"],
            "campaign": (b["name"] if b else u.get("campaign", str(u["campaign_id"]))),
            "group": u["group"],
            "code": u["code"],
            "label": u["label"],
            "dimension": u["dimension"],
            "impressions": u["impressions"],
            "clicks": u["clicks"],
            "ctr": u["ctr"],
            "cost": u["cost"],
            "conv": conv,
            "value": u["value"],
            "roas": (u["value"] / u["cost"]) if u["cost"] > 0 else None,
            "lg_cpa": (u["cost"] / conv) if conv > 0 else None,
            "camp_cpa": (b["cpa"] if b else None),
            "camp_clicks_per_conv": (b["clicks_per_conv"] if b else None),
            "status": "scored" if scored else "no_benchmark",
        })
    universe.sort(key=lambda r: r["cost"], reverse=True)
    return universe


def annotate_signals(universe: list, params: dict) -> list:
    """Add per-row `cost_share` (this row's share of the UNIVERSE's total 30d
    cost — every row, scored or no_benchmark; no-row-loss holds) and the tier
    signal: `over_concentrated` (cost_share > concentration_share_min) AND
    `weak_roas` (roas < weak_roas_max) BOTH firing on the same row. Declarative
    rules via `analytics.signals` — the same primitive the JS kernel mirrors,
    so a row's tier_signal can never disagree between Python and the explorer.
    Independent of the expensiveness factor (never touches conv/clicks/cpa)."""
    total_cost = sum(r["cost"] for r in universe)
    with_share = []
    for r in universe:
        rr = dict(r)
        rr["cost_share"] = (r["cost"] / total_cost) if total_cost > 0 else 0.0
        with_share.append(rr)
    rules = [
        {"id": "over_concentrated", "key": "cost_share", "op": "gt",
         "value": params["concentration_share_min"]},
        {"id": "weak_roas", "key": "roas", "op": "lt", "value": params["weak_roas_max"]},
    ]
    flags_list = analytics.signals(with_share, rules)
    out = []
    for r, flags in zip(with_share, flags_list):
        rr = dict(r)
        rr["signal_flags"] = flags
        rr["tier_signal"] = "over_concentrated" in flags and "weak_roas" in flags
        out.append(rr)
    return out


def classify_row(row: dict, params: dict) -> dict:
    """Return condition flags + block for one row at the given params.
    no_benchmark rows are never classified (block='')."""
    if row["status"] != "scored":
        return {"cpa_pass": None, "clicks_pass": None, "block": ""}
    f = params["expensiveness_factor"]
    cpa_pass = (row["conv"] > 0 and row["lg_cpa"] is not None
                and row["lg_cpa"] > f * row["camp_cpa"])
    clicks_pass = (row["conv"] == 0 and row["camp_clicks_per_conv"] is not None
                   and row["clicks"] > f * row["camp_clicks_per_conv"])
    block = ""
    if row["conv"] > 0:
        if cpa_pass:
            block = "Block 1"
    else:
        if clicks_pass:
            block = "Block 2"
    return {"cpa_pass": cpa_pass, "clicks_pass": clicks_pass, "block": block}


def classify(universe: list, params: dict) -> list:
    out = []
    for r in universe:
        rr = dict(r)
        rr.update(classify_row(r, params))
        out.append(rr)
    return out


def summarize(classified: list, params: dict) -> dict:
    b1 = [r for r in classified if r["block"] == "Block 1"]
    b2 = [r for r in classified if r["block"] == "Block 2"]
    no_bench = [r for r in classified if r["status"] == "no_benchmark"]
    tier = [r for r in classified if r.get("tier_signal")]
    conc = analytics.concentration(classified, "cost", top_n=params["concentration_top_n"])
    return {
        "block1": len(b1), "block2": len(b2), "total": len(b1) + len(b2),
        "flagged_spend": round(sum(r["cost"] for r in b1) + sum(r["cost"] for r in b2), 2),
        "universe": len(classified),
        "scored": sum(1 for r in classified if r["status"] == "scored"),
        "no_benchmark": len(no_bench),
        "tier_signals": len(tier),
        "signal_spend": round(sum(r["cost"] for r in tier), 2),
        "concentration": conc,
    }


def sensitivity(universe: list, params: dict, ladder: list | None = None) -> list:
    """Qualifiers per expensiveness factor, holding all other params at `params`.
    (Concentration/tier-signal fields don't depend on the factor, so they don't
    move across the ladder — only block1/block2/total are read here.)"""
    ladder = ladder or FACTOR_LADDER
    out = []
    for f in ladder:
        p = dict(params); p["expensiveness_factor"] = f
        s = summarize(classify(universe, p), p)
        out.append({"factor": f, "block1": s["block1"], "block2": s["block2"],
                    "total": s["total"],
                    "is_current": abs(f - params["expensiveness_factor"]) < 1e-9})
    return out


def near_misses(universe: list, params: dict, block: str, top_n: int = 25) -> list:
    """Scored rows on the correct side of the conversion split for `block`, ranked
    by how close they are to the factor bar. qualify_if_factor_le = the largest
    factor at which the row would still qualify (cost/conv ÷ campaign cost/conv for
    Block 1; clicks ÷ campaign clicks/conv for Block 2)."""
    f = params["expensiveness_factor"]
    pool = []
    for r in universe:
        if r["status"] != "scored":
            continue
        if block == "Block 1":
            if not (r["conv"] > 0 and r["camp_cpa"]):
                continue
            x = r["lg_cpa"] / r["camp_cpa"]
            now = r["lg_cpa"] > f * r["camp_cpa"]
        else:  # Block 2
            if not (r["conv"] == 0 and r["camp_clicks_per_conv"]):
                continue
            x = r["clicks"] / r["camp_clicks_per_conv"]
            now = r["clicks"] > f * r["camp_clicks_per_conv"]
        pool.append({**r, "qualify_if_factor_le": round(x, 3), "currently_qualifies": now})
    pool.sort(key=lambda r: r["qualify_if_factor_le"], reverse=True)
    return pool[:top_n]


def provenance(findings: dict, params: dict) -> dict:
    meta = findings.get("meta") or {}
    return {
        "client_name": meta.get("client_name", ""),
        "account_id": meta.get("account_id", ""),
        "currency": meta.get("currency", ""),
        "window_30d": meta.get("window_30d", ""),
        "generated": meta.get("generated", ""),
        # Honest data-source label (HM-539 dual-input contract, canonicalized by
        # HM-572): the canonical "mcp" live-pull token (assemble_findings.py, the
        # MCP path) or "user_csv" (assemble_from_csv.py). Never presented as an
        # API pull when it wasn't one.
        "source": meta.get("source", "mcp"),
        "params": dict(params),
    }


def _fmt_money(v, cur: str) -> str:
    if v is None:
        return "n/a"
    return f"{v:,.2f}" + (f" {cur}" if cur else "")


def recommendations(model: dict) -> list:
    """Prioritized advisor recommendations grounded in the model — Critical/High/
    Medium per the google-ads-foundation advisor output contract
    (references/artifact-formats.md). Every number cited is read off `model`
    (never re-narrated raw data). This skill has no Editor apply-CSV — PMax
    listing-group/product exclusions are manual in the web UI — so every
    recommendation's artifact is that manual worklist (the flagged rows the
    bundle already surfaces). Empty severities are honest: a clean account may
    return no recommendations at all."""
    cur = model["provenance"]["currency"]
    s, it = model["summary"], model["summary"]["item"]
    MANUAL = "manual — Google Ads web UI listing-group tree (no Editor apply-CSV for PMax listing groups)"
    out = []

    def block_spend(rows, block):
        return round(sum(r["cost"] for r in rows if r["block"] == block), 2)

    # --- Critical: Block 2, zero-conversion waste (direct bleed) ---
    if s["block2"] or it["block2"]:
        parts = []
        if s["block2"]:
            parts.append(f"{s['block2']} listing-group partition(s) "
                         f"({_fmt_money(block_spend(model['rows'], 'Block 2'), cur)})")
        if it["block2"]:
            parts.append(f"{it['block2']} product(s) "
                         f"({_fmt_money(block_spend(model['items'], 'Block 2'), cur)})")
        out.append({
            "severity": "Critical",
            "text": ("Exclude or down-prioritize " + " and ".join(parts) + " burning clicks "
                     "with zero conversions in the last 30 days — Block 2 of the waste filter."),
            "artifact": MANUAL,
        })

    # --- High: Block 1, expensive converters (quantified upside if segmented) ---
    if s["block1"] or it["block1"]:
        parts = []
        if s["block1"]:
            parts.append(f"{s['block1']} listing-group partition(s) "
                         f"({_fmt_money(block_spend(model['rows'], 'Block 1'), cur)})")
        if it["block1"]:
            parts.append(f"{it['block1']} product(s) "
                         f"({_fmt_money(block_spend(model['items'], 'Block 1'), cur)})")
        out.append({
            "severity": "High",
            "text": ("Segment " + " and ".join(parts) + " converting above their campaign's "
                     "cost/conversion bar into a tighter tCPA/tROAS asset group (or exclude only "
                     "if the margin is negative) — Block 1 of the waste filter."),
            "artifact": MANUAL,
        })

    # --- High: tier signal — spend concentrated in a weak-ROAS tier ---
    if s["tier_signals"] or it["tier_signals"]:
        parts = []
        if s["tier_signals"]:
            parts.append(f"{s['tier_signals']} partition(s) ({_fmt_money(s['signal_spend'], cur)})")
        if it["tier_signals"]:
            parts.append(f"{it['tier_signals']} product(s) ({_fmt_money(it['signal_spend'], cur)})")
        share_pct = f"{model['params']['concentration_share_min'] * 100:.0f}%"
        roas_bar = model["params"]["weak_roas_max"]
        out.append({
            "severity": "High",
            "text": ("Reallocate spend away from " + " and ".join(parts) + " — each holds more "
                     f"than {share_pct} of its universe's 30-day spend AND has ROAS below "
                     f"{roas_bar:.2f} (the tier concentration + weak-ROAS signal)."),
            "artifact": MANUAL,
        })

    # --- Medium: near-miss watchlist (partitions only — the live-tunable primary) ---
    nm = [r for r in (model.get("near_misses_block1") or []) + (model.get("near_misses_block2") or [])
          if not r.get("currently_qualifies")]
    if nm:
        out.append({
            "severity": "Medium",
            "text": (f"{len(nm)} partition(s) sit just below the expensiveness-factor bar (see the "
                     "near-miss tables) — watch next cycle, or relax the factor in the explorer to "
                     "review them now."),
            "artifact": MANUAL,
        })

    # --- Medium: dominant "Everything else" catch-all ---
    catchall_share = max((r.get("cost_share", 0.0) for r in model["rows"]
                          if r["label"] == "Everything else"), default=0.0)
    if catchall_share > model["params"]["concentration_share_min"]:
        out.append({
            "severity": "Medium",
            "text": (f"An 'Everything else' catch-all partition holds "
                     f"{catchall_share * 100:.0f}% of partition spend — the asset group likely "
                     "needs subdividing rather than left as one bucket."),
            "artifact": MANUAL,
        })

    return out


def compute_model(findings: dict) -> dict:
    """Assemble the full model at the resolved params. JSON-serializable —
    safe to embed in the HTML explorer for live recompute."""
    params = resolve_params(findings.get("params"))
    bench = build_benchmarks(findings["benchmarks"])

    lg_units = [_unit_from_listing_group(t) for t in findings.get("listing_groups", [])]
    pr_units = [_unit_from_product(t) for t in findings.get("products", [])]
    part_uni = annotate_signals(build_universe(lg_units, bench), params)
    item_uni = annotate_signals(build_universe(pr_units, bench), params)

    part_rows = classify(part_uni, params)
    item_rows = classify(item_uni, params)

    part_sum = summarize(part_rows, params)
    item_sum = summarize(item_rows, params)
    summary = dict(part_sum)
    summary["item"] = item_sum
    summary["has_items"] = bool(item_rows)
    summary["has_partitions"] = bool(part_rows)

    model = {
        "provenance": provenance(findings, params),
        "params": params,
        "benchmarks": [bench[k] for k in bench],
        "rows": part_rows,
        "items": item_rows,
        "summary": summary,
        "sensitivity": sensitivity(part_uni, params),
        "item_sensitivity": sensitivity(item_uni, params),
        "near_misses_block1": near_misses(part_uni, params, "Block 1"),
        "near_misses_block2": near_misses(part_uni, params, "Block 2"),
        "item_near_misses_block1": near_misses(item_uni, params, "Block 1"),
        "item_near_misses_block2": near_misses(item_uni, params, "Block 2"),
        "factor_ladder": FACTOR_LADDER,
        "_universe": part_uni,       # unclassified partitions for live re-tune
        "_universe_items": item_uni,  # unclassified products for live re-tune
    }
    model["recommendations"] = recommendations(model)
    return model
