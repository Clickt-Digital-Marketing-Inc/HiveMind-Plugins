#!/usr/bin/env python3
"""Product-segments filter — model / single source of truth (stdlib only).

Every renderer (md, html, xlsx) imports this module so the classification logic
can never diverge across formats. No third-party dependencies.

The findings-JSON input contract is documented authoritatively in
`references/product-segments-filter.md` (do not duplicate the schema here).

Three account-aggregated, per-product segments (each row = one product, metrics
summed across Shopping + PMax sources by product_item_id):

  ZOMBIE — wasted spend:  conversions(30d) <= zombie_conv_max AND
           cost(30d) > zombie_cost_min AND merchant id present (14d).
  SURGING — accelerating: conversions(14d) > surge_multiple × conversions(prev-14d)
           AND conversions(prev-14d) > 0.  (impressions(prev-14d) >= 0 is trivially
           true for count data — the load-bearing guard is prev-14d conv > 0.)
  DECLINING — collapsing:  conversions(14d) < decline_multiple × conversions(prev-14d).
           (impressions(14d) >= 0 is trivially true; if prev-14d conv == 0 the
           inequality is impossible for non-negative counts, so a product with no
           prior conversions is never Declining — correct, falls out naturally.)

The three are mutually exclusive by construction; precedence Zombie > Surging >
Declining makes any degenerate row deterministic.

Every product survives into the model with a status:
  scored   — has cost or impressions in at least one window (evaluable).
  inactive — zero cost AND zero impressions in every window (nothing to score;
             segment "" — kept, never dropped).
Merchant presence is NOT a status: it is the merchant_id value plus a `<>""`
term in the zombie test, so the Python, JS, and xlsx formula paths stay
byte-identical across all three formats.
"""
from __future__ import annotations

import json
from pathlib import Path

# Sensitivity ladders for the explorer / snapshot (held-others-constant sweeps).
SURGE_LADDER = [1.25, 1.50, 1.75, 2.00, 2.50, 3.00]
DECLINE_LADDER = [0.25, 0.33, 0.50, 0.66, 0.75]

DEFAULT_PARAMS = {
    "surge_multiple": 1.50,    # conversions(14d) must exceed this × conversions(prev-14d)
    "decline_multiple": 0.50,  # conversions(14d) below this × conversions(prev-14d)
    "zombie_cost_min": 0.0,    # zombie requires cost(30d) STRICTLY GREATER than this
    "zombie_conv_max": 0.0,    # zombie requires conversions(30d) <= this
}

# the seven per-product metric fields summed during dedupe (account aggregate)
_METRIC_FIELDS = (
    "conversions_30d", "cost_30d", "impressions_30d",
    "conversions_14d", "impressions_14d",
    "conversions_prev14d", "impressions_prev14d",
)


class FindingsError(ValueError):
    """Raised when the findings JSON is missing/invalid."""


# Control-total contract shared with scripts/assemble_findings.py: per findings
# array, the numeric fields whose sums are embedded as meta.reconciliation and
# re-verified here on every load. Catches transcription drift and hand-edits.
RECONCILE_ARRAYS = {
    "products": ["cost_30d", "conversions_30d", "impressions_30d",
                 "conversions_14d", "impressions_14d",
                 "conversions_prev14d", "impressions_prev14d"],
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
    if not isinstance(data.get("products"), list):
        raise FindingsError("findings JSON missing required array 'products'")
    if (data.get("meta") or {}).get("reconciliation"):
        try:
            import reconcile  # lazy: _shared module, on sys.path via the builders/tests
        except ImportError as e:
            raise FindingsError(
                "findings carry reconciliation totals but the _shared toolkit is not "
                "on sys.path — run via build_product_report.py, or add the plugin's "
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


def _mid(p: dict) -> str:
    v = p.get("merchant_id")
    return "" if v is None else str(v).strip()


def _pkey(p: dict) -> str:
    return str(p.get("product_item_id") or "")


def merge_product_windows(rows30: list, rows14: list, rows_prev14: list) -> list:
    """Join three per-window product-metric row lists into one row per
    product_item_id — the transcription-firewall merge shared by BOTH input
    paths (`assemble_findings.assemble` for saved GAQL pulls and
    `assemble_findings.assemble_csv` for the three UI CSV exports), so the
    join logic can never diverge between MCP and CSV. Callers normalize their
    source rows to these LOGICAL fields before calling:

        rows30      — product_item_id (required), product_title?, merchant_id?,
                      channel?, conversions, cost, impressions
        rows14      — product_item_id (required), merchant_id?, conversions, impressions
        rows_prev14 — product_item_id (required), conversions, impressions

    Sums metrics for rows sharing a product_item_id WITHIN a window (a product
    can appear once per campaign/channel), unions the channel set, takes the
    first non-empty title, and resolves merchant_id from the MOST RECENT
    window the product appears in: the 14d pull's value (even if blank —
    matching the "merchant id present in the LAST 14 DAYS" zombie test
    exactly) when the product has any row there, else the 30d pull's value.
    Missing windows default that window's metrics to 0. Returns the raw
    (pre-dedupe-across-windows-already-done) `products` array for the
    findings JSON — order is first-seen across rows30 -> rows14 -> rows_prev14."""
    merged: dict = {}
    order: list = []

    def slot(item_id) -> dict:
        k = str(item_id or "")
        if k not in merged:
            merged[k] = {"product_item_id": k, "product_title": "",
                         "merchant_id": "", "channels": set(),
                         "_in_14d": False, "_merchant_14d": "",
                         **{f: 0.0 for f in _METRIC_FIELDS}}
            order.append(k)
        return merged[k]

    for r in rows30:
        m = slot(r.get("product_item_id"))
        m["conversions_30d"] += _num(r.get("conversions"))
        m["cost_30d"] += _num(r.get("cost"))
        m["impressions_30d"] += _num(r.get("impressions"))
        if not m["product_title"] and r.get("product_title"):
            m["product_title"] = str(r["product_title"])
        if not m["merchant_id"] and _mid(r):
            m["merchant_id"] = _mid(r)
        if r.get("channel"):
            m["channels"].add(str(r["channel"]))
    for r in rows14:
        m = slot(r.get("product_item_id"))
        m["conversions_14d"] += _num(r.get("conversions"))
        m["impressions_14d"] += _num(r.get("impressions"))
        m["_in_14d"] = True
        if not m["_merchant_14d"] and _mid(r):
            m["_merchant_14d"] = _mid(r)
    for r in rows_prev14:
        m = slot(r.get("product_item_id"))
        m["conversions_prev14d"] += _num(r.get("conversions"))
        m["impressions_prev14d"] += _num(r.get("impressions"))

    products = []
    for k in order:
        m = merged[k]
        if m.pop("_in_14d"):
            m["merchant_id"] = m["_merchant_14d"]
        m.pop("_merchant_14d")
        m["channels"] = sorted(m["channels"])
        m["cost_30d"] = round(m["cost_30d"], 6)
        products.append(m)
    return products


def dedupe_products(products: list) -> list:
    """Merge rows sharing product_item_id (the same product appears once per
    campaign/channel): SUM the seven metric fields (account aggregate), take the
    first non-empty title and merchant id, union the channels. Preserve
    first-seen order."""
    merged: dict = {}
    order: list = []
    for p in products:
        k = _pkey(p)
        if k not in merged:
            merged[k] = {
                "product_item_id": k,
                "product_title": "",
                "merchant_id": "",
                "channels": set(),
                **{f: 0.0 for f in _METRIC_FIELDS},
            }
            order.append(k)
        m = merged[k]
        for f in _METRIC_FIELDS:
            m[f] += _num(p.get(f))
        if not m["product_title"] and p.get("product_title"):
            m["product_title"] = str(p["product_title"])
        if not m["merchant_id"] and _mid(p):
            m["merchant_id"] = _mid(p)
        for ch in (p.get("channels") or []):
            m["channels"].add(str(ch))
    out = []
    for k in order:
        m = dict(merged[k])
        m["channels"] = sorted(m["channels"])
        out.append(m)
    return out


def build_universe(products: list) -> list:
    """Every deduped product, annotated with a status. Nothing dropped.
    status = 'scored' (has spend or impressions somewhere) or 'inactive'."""
    universe = []
    for p in dedupe_products(products):
        cost30 = _num(p.get("cost_30d"))
        i30 = _num(p.get("impressions_30d"))
        i14 = _num(p.get("impressions_14d"))
        ip14 = _num(p.get("impressions_prev14d"))
        active = cost30 > 0 or i30 > 0 or i14 > 0 or ip14 > 0
        universe.append({
            "product_item_id": p["product_item_id"],
            "product_title": p.get("product_title", ""),
            "channels": p.get("channels", []),
            "merchant_id": p.get("merchant_id", ""),
            "conversions_30d": _num(p.get("conversions_30d")),
            "cost_30d": cost30,
            "impressions_30d": i30,
            "conversions_14d": _num(p.get("conversions_14d")),
            "impressions_14d": i14,
            "conversions_prev14d": _num(p.get("conversions_prev14d")),
            "impressions_prev14d": ip14,
            "status": "scored" if active else "inactive",
        })
    universe.sort(key=lambda r: r["cost_30d"], reverse=True)
    return universe


def classify_row(row: dict, params: dict) -> dict:
    """Per-condition flags + segment for one row at the given params.
    'inactive' rows are never classified (segment '')."""
    if row["status"] == "inactive":
        return {"is_zombie": None, "is_surging": None, "is_declining": None, "segment": ""}
    has_m = str(row.get("merchant_id") or "") != ""
    c30 = _num(row["conversions_30d"])
    k30 = _num(row["cost_30d"])
    c14 = _num(row["conversions_14d"])
    p14 = _num(row["conversions_prev14d"])
    # impressions(prev-14d) >= 0 / impressions(14d) >= 0 from the rule are no-ops
    # for count data; the meaningful surge guard is prev-14d conversions > 0.
    is_zombie = has_m and c30 <= params["zombie_conv_max"] and k30 > params["zombie_cost_min"]
    is_surging = p14 > 0 and c14 > params["surge_multiple"] * p14
    is_declining = c14 < params["decline_multiple"] * p14
    segment = ("Zombie" if is_zombie
               else "Surging" if is_surging
               else "Declining" if is_declining
               else "")
    return {"is_zombie": is_zombie, "is_surging": is_surging,
            "is_declining": is_declining, "segment": segment}


def classify(universe: list, params: dict) -> list:
    out = []
    for r in universe:
        rr = dict(r)
        rr.update(classify_row(r, params))
        out.append(rr)
    return out


def summarize(classified: list) -> dict:
    z = [r for r in classified if r["segment"] == "Zombie"]
    su = [r for r in classified if r["segment"] == "Surging"]
    d = [r for r in classified if r["segment"] == "Declining"]
    return {
        "zombie": len(z), "surging": len(su), "declining": len(d),
        "flagged": len(z) + len(su) + len(d),
        "zombie_wasted_cost": round(sum(_num(r["cost_30d"]) for r in z), 2),
        "universe": len(classified),
        "scored": sum(1 for r in classified if r["status"] == "scored"),
        "inactive": sum(1 for r in classified if r["status"] == "inactive"),
        "no_merchant": sum(1 for r in classified if str(r.get("merchant_id") or "") == ""),
    }


def sensitivity(universe: list, params: dict, axis: str = "surge", ladder: list | None = None) -> list:
    """Segment counts as the surge OR decline multiple steps, holding the other
    params at `params`. (Zombie is invariant to these multiples — shown for
    context.)"""
    if axis == "decline":
        ladder = ladder or DECLINE_LADDER
        pkey, cur = "decline_multiple", params["decline_multiple"]
    else:
        ladder = ladder or SURGE_LADDER
        pkey, cur = "surge_multiple", params["surge_multiple"]
    out = []
    for m in ladder:
        p = dict(params)
        p[pkey] = m
        s = summarize(classify(universe, p))
        out.append({"multiple": m, "zombie": s["zombie"], "surging": s["surging"],
                    "declining": s["declining"], "is_current": abs(m - cur) < 1e-9})
    return out


def provenance(findings: dict, params: dict) -> dict:
    meta = findings.get("meta") or {}
    return {
        "client_name": meta.get("client_name", ""),
        "account_id": meta.get("account_id", ""),
        "currency": meta.get("currency", ""),
        # window_30d is the one the shared chrome renders; 14d/prev-14d are
        # surfaced by the spec's md_params adapter + the HTML extra panel.
        "window_30d": meta.get("window_30d", ""),
        "window_14d": meta.get("window_14d", ""),
        "window_prev14d": meta.get("window_prev14d", ""),
        "generated": meta.get("generated", ""),
        "params": dict(params),
        # Honest data-source label (HM-540 dual-input, canonicalized by HM-572):
        # the canonical "mcp" live-pull token (stamped by assemble_findings.assemble)
        # or "user_csv" (the CSV path, stamped by _shared/csv_input's default) — never
        # "" so a live pull is never rendered unlabeled. Display-only — copied
        # straight through to the HTML embed and never recomputed, so it carries no
        # js_kernel/xlsx parity obligation.
        "source": meta.get("source", "mcp"),
    }


def compute_model(findings: dict) -> dict:
    """Assemble the full model at the resolved params. JSON-serializable — safe
    to embed in the HTML explorer for live recompute. The classification numbers
    here are the single source of truth; the spec adapters only present them."""
    params = resolve_params(findings.get("params"))
    universe = build_universe(findings["products"])
    classified = classify(universe, params)
    return {
        "provenance": provenance(findings, params),
        "params": params,
        "rows": classified,
        "summary": summarize(classified),
        "sensitivity_surge": sensitivity(universe, params, "surge"),
        "sensitivity_decline": sensitivity(universe, params, "decline"),
        "surge_ladder": SURGE_LADDER,
        "decline_ladder": DECLINE_LADDER,
        "_universe": universe,  # unclassified rows for renderers that re-tune live
    }


def _money(v, cur) -> str:
    return f"{float(v):,.2f}" + (f" {cur}" if cur else "")


def recommendations(model: dict) -> list:
    """Prioritized product actions (advisor output contract: Critical -> High
    -> Medium), each citing the model's OWN numbers — never re-narrated raw
    data. Formatting over already-computed `summary`/`rows`, so it derives no
    new classification/scoring math and carries no js_kernel/xlsx mirror
    obligation. An empty severity tier (or an empty list when nothing is
    flagged) is an honest clean result, not an omission — the caller prints
    that plainly rather than padding a tier."""
    s = model["summary"]
    cur = model["provenance"]["currency"]
    p = model["params"]

    def _top(rows, n=5):
        return sorted(rows, key=lambda r: r["cost_30d"], reverse=True)[:n]

    def _examples(rows):
        return [f"{r['product_title'] or r['product_item_id']} "
                f"({_money(r['cost_30d'], cur)})" for r in _top(rows)]

    zombies = [r for r in model["rows"] if r["segment"] == "Zombie"]
    surging = [r for r in model["rows"] if r["segment"] == "Surging"]
    declining = [r for r in model["rows"] if r["segment"] == "Declining"]

    recs = []
    if zombies:
        recs.append({
            "severity": "Critical",
            "action": f"Exclude/pause {s['zombie']} zombie product(s) in the "
                      "Shopping/PMax listing groups",
            "why": (f"{s['zombie']} product(s) spent {_money(s['zombie_wasted_cost'], cur)} "
                    "over 30 days with zero conversions while still in the merchant feed"),
            "examples": _examples(zombies),
            "worklist": "_zombie_worklist.csv",
        })
    if surging:
        recs.append({
            "severity": "High",
            "action": f"Scale budget/priority for {s['surging']} surging product(s) "
                      "before the spike passes",
            "why": (f"{s['surging']} product(s) show 14-day conversions above "
                    f"{p['surge_multiple']:.2f}× their previous 14 days"),
            "examples": _examples(surging),
            "worklist": "_surging_worklist.csv",
        })
    if declining:
        recs.append({
            "severity": "Medium",
            "action": f"Investigate {s['declining']} declining product(s) — feed, "
                      "price, or stock",
            "why": (f"{s['declining']} product(s) show 14-day conversions below "
                    f"{p['decline_multiple']:.2f}× their previous 14 days"),
            "examples": _examples(declining),
            "worklist": "_declining_worklist.csv",
        })
    return recs
