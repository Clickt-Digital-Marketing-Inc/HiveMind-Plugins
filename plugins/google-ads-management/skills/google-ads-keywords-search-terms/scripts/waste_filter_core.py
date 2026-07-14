#!/usr/bin/env python3
"""Search-term waste filter — model / single source of truth (stdlib only).

Every renderer (md, csv, html, xlsx) imports this module so the classification
logic can never diverge across formats. No third-party dependencies.

The findings-JSON input contract is documented authoritatively in
`references/search-term-waste-filter.md` (do not duplicate the schema here).

Two blocks, each AND-joined, benchmarked against the term's OWN campaign:
  Block 1 — never-converted waste:  conv90 <= block1_max_conv_90d AND in scope
            AND ctr < ctr_factor*campaign_ctr AND cost > cost_multiple*campaign_cpa
  Block 2 — decaying converters:    conv90 >  block2_min_conv_90d AND
            conv30 <= block2_max_conv_30d AND in scope AND the same CTR/cost bars
Campaigns with 0 conversions (90d) have an undefined cost/conv benchmark, so
their terms are kept with status="no_benchmark" and never classified or dropped.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parents[2]                       # .../plugins/google-ads-management
if str(PLUGIN_ROOT / "_shared") not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT / "_shared"))

import analytics  # noqa: E402  (shared concentration primitive — HM-532)

COST_LADDER = [3.0, 2.5, 2.0, 1.5, 1.0, 0.5, 0.25]

DEFAULT_PARAMS = {
    "ctr_factor": 0.50,
    "cost_multiple": 2.50,
    "block1_max_conv_90d": 0,
    "block2_min_conv_90d": 0,
    "block2_max_conv_30d": 0,
    "match_types_in_scope": ["BROAD", "PHRASE", "NEAR_EXACT", "NEAR_PHRASE", "AI_MAX"],
}
# (friendly label, GAQL enum). Pure EXACT is excluded at the data source.
MATCH_TYPES = [
    ("Broad", "BROAD"),
    ("Phrase", "PHRASE"),
    ("Exact close variant", "NEAR_EXACT"),
    ("Phrase close variant", "NEAR_PHRASE"),
    ("AI Max", "AI_MAX"),
]


class FindingsError(ValueError):
    """Raised when the findings JSON is missing/invalid."""


# Control-total contract shared with scripts/assemble_findings.py: per findings
# array, the numeric fields whose sums are embedded as meta.reconciliation and
# re-verified here on every load. Catches transcription drift and hand-edits.
RECONCILE_ARRAYS = {
    "search_terms": ["cost", "clicks", "impressions", "conversions_90d", "conversions_30d"],
    "benchmarks": ["cost", "conversions"],
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
    for req in ("benchmarks", "search_terms"):
        if not isinstance(data.get(req), list):
            raise FindingsError(f"findings JSON missing required array '{req}'")
    if (data.get("meta") or {}).get("reconciliation"):
        try:
            import reconcile  # lazy: _shared module, on sys.path via the builders/tests
        except ImportError as e:
            raise FindingsError(
                "findings carry reconciliation totals but the _shared toolkit is not "
                "on sys.path — run via build_waste_filter.py, or add the plugin's "
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
    p["match_types_in_scope"] = [str(s).upper() for s in
                                 (p.get("match_types_in_scope") or DEFAULT_PARAMS["match_types_in_scope"])]
    return p


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _round2(x: float) -> float:
    """Half-up rounding to 2dp for x >= 0 (kernel-mirror contract, mirrored
    verbatim in JS as Math.round(x*100)/100 — equal to floor(x*100+0.5)/100
    for every non-negative x, which is all costs ever passed here). Python's
    round() is banker's-rounding and is deliberately not used, matching the
    _shared/analytics.py convention."""
    return math.floor(x * 100 + 0.5) / 100


def _fmt_money(v: float, cur: str) -> str:
    return f"{float(v):,.2f}" + (f" {cur}" if cur else "")


def _term_key(t: dict) -> tuple:
    return (t.get("campaign_id"), str(t.get("ad_group", "")),
            str(t.get("term", "")), str(t.get("match_type", "")).upper())


def dedupe_terms(terms: list) -> list:
    """Merge rows sharing (campaign_id, ad_group, term, match_type): sum
    impressions/clicks/cost/conversions and recompute CTR. Foundation rule:
    dedupe by key before counting (a key can legitimately appear split by a
    segment such as device)."""
    merged: dict = {}
    order: list = []
    for t in terms:
        k = _term_key(t)
        if k not in merged:
            merged[k] = {
                "campaign_id": t.get("campaign_id"),
                "campaign": t.get("campaign", ""),
                "ad_group": t.get("ad_group", ""),
                "term": t.get("term", ""),
                "match_type": str(t.get("match_type", "")).upper(),
                "impressions": 0.0, "clicks": 0.0, "cost": 0.0,
                "conversions_90d": 0.0, "conversions_30d": 0.0,
            }
            order.append(k)
        m = merged[k]
        m["impressions"] += _num(t.get("impressions"))
        m["clicks"] += _num(t.get("clicks"))
        m["cost"] += _num(t.get("cost"))
        m["conversions_90d"] += _num(t.get("conversions_90d"))
        m["conversions_30d"] += _num(t.get("conversions_30d"))
    for k in order:
        m = merged[k]
        m["ctr"] = (m["clicks"] / m["impressions"]) if m["impressions"] else 0.0
    return [merged[k] for k in order]


def build_benchmarks(rows: list) -> dict:
    bench = {}
    for c in rows:
        conv = _num(c.get("conversions"))
        cost = _num(c.get("cost"))
        bench[c.get("campaign_id")] = {
            "campaign_id": c.get("campaign_id"),
            "name": c.get("campaign", str(c.get("campaign_id"))),
            "ctr": _num(c.get("ctr")),
            "cost": cost,
            "conv": conv,
            "cpa": (cost / conv) if conv > 0 else None,
        }
    return bench


def build_universe(terms: list, bench: dict) -> list:
    """Every deduped term, annotated with its campaign benchmark and a status.
    status = 'scored' (campaign has a usable cost/conv benchmark) or
    'no_benchmark' (campaign absent or 0 conversions in 90d). Nothing dropped."""
    universe = []
    for t in dedupe_terms(terms):
        b = bench.get(t["campaign_id"])
        scored = b is not None and b["cpa"] is not None
        universe.append({
            "campaign_id": t["campaign_id"],
            "campaign": (b["name"] if b else t.get("campaign", str(t["campaign_id"]))),
            "ad_group": t["ad_group"],
            "term": t["term"],
            "match_type": t["match_type"],
            "impressions": t["impressions"],
            "clicks": t["clicks"],
            "ctr": t["ctr"],
            "cost": t["cost"],
            "conv90": t["conversions_90d"],
            "conv30": t["conversions_30d"],
            "camp_ctr": (b["ctr"] if b else None),
            "camp_cpa": (b["cpa"] if b else None),
            "status": "scored" if scored else "no_benchmark",
        })
    universe.sort(key=lambda r: r["cost"], reverse=True)
    return universe


def classify_row(row: dict, params: dict) -> dict:
    """Return condition flags + block for one row at the given params.
    no_benchmark rows are never classified (block='')."""
    if row["status"] != "scored":
        return {"in_scope": None, "ctr_pass": None, "cost_pass": None, "block": ""}
    scope = set(params["match_types_in_scope"])
    in_scope = row["match_type"] in scope
    ctr_pass = row["ctr"] < params["ctr_factor"] * row["camp_ctr"]
    cost_pass = row["cost"] > params["cost_multiple"] * row["camp_cpa"]
    block = ""
    if in_scope and ctr_pass and cost_pass:
        if row["conv90"] <= params["block1_max_conv_90d"]:
            block = "Block 1"
        elif row["conv90"] > params["block2_min_conv_90d"] and row["conv30"] <= params["block2_max_conv_30d"]:
            block = "Block 2"
    return {"in_scope": in_scope, "ctr_pass": ctr_pass, "cost_pass": cost_pass, "block": block}


def classify(universe: list, params: dict) -> list:
    out = []
    for r in universe:
        rr = dict(r)
        rr.update(classify_row(r, params))
        out.append(rr)
    return out


def summarize(classified: list) -> dict:
    b1 = [r for r in classified if r["block"] == "Block 1"]
    b2 = [r for r in classified if r["block"] == "Block 2"]
    no_bench = [r for r in classified if r["status"] == "no_benchmark"]
    return {
        "block1": len(b1), "block2": len(b2), "total": len(b1) + len(b2),
        "wasted": round(sum(r["cost"] for r in b1) + sum(r["cost"] for r in b2), 2),
        "universe": len(classified),
        "scored": sum(1 for r in classified if r["status"] == "scored"),
        "no_benchmark": len(no_bench),
    }


def sensitivity(universe: list, params: dict, ladder: list | None = None) -> list:
    """Qualifiers per cost multiple, holding all other params at `params`."""
    ladder = ladder or COST_LADDER
    out = []
    for m in ladder:
        p = dict(params); p["cost_multiple"] = m
        s = summarize(classify(universe, p))
        out.append({"cost_multiple": m, "block1": s["block1"], "block2": s["block2"],
                    "total": s["total"], "is_current": abs(m - params["cost_multiple"]) < 1e-9})
    return out


def near_misses(universe: list, params: dict, block: str, top_n: int = 25) -> list:
    """Scored rows meeting every NON-cost condition for `block`, ranked by how
    close they are to the cost bar. qualify_if_cost_multiple_le = cost/camp_cpa
    (the term qualifies on cost for any multiple <= this)."""
    scope = set(params["match_types_in_scope"])
    pool = []
    for r in universe:
        if r["status"] != "scored" or r["match_type"] not in scope:
            continue
        if not (r["ctr"] < params["ctr_factor"] * r["camp_ctr"]):
            continue
        if block == "Block 1":
            if not (r["conv90"] <= params["block1_max_conv_90d"]):
                continue
        else:
            if not (r["conv90"] > params["block2_min_conv_90d"] and r["conv30"] <= params["block2_max_conv_30d"]):
                continue
        x = (r["cost"] / r["camp_cpa"]) if r["camp_cpa"] else 0.0
        pool.append({**r, "qualify_if_cost_multiple_le": round(x, 3),
                     "currently_qualifies": r["cost"] > params["cost_multiple"] * r["camp_cpa"]})
    pool.sort(key=lambda r: r["qualify_if_cost_multiple_le"], reverse=True)
    return pool[:top_n]


def term_ngrams(term: str) -> list:
    """Unigrams + adjacent bigrams from a search term: lowercase, whitespace-
    split, unique per term, sorted for determinism. Kernel-mirror contract —
    mirrored verbatim as gxTermNgrams in waste_filter_spec.JS_KERNEL."""
    words = str(term or "").strip().lower().split()
    grams = set(words)
    grams.update(f"{words[i]} {words[i + 1]}" for i in range(len(words) - 1))
    return sorted(grams)


def waste_ngrams(classified: list, top_n: int = 15, concentration_top_n: int = 5) -> dict:
    """N-gram concentration over the waste block (Block 1 + Block 2 rows):
    which tokens concentrate wasted spend. A row's cost is credited once to
    each unique n-gram it carries (term_ngrams already dedupes per term).
    Kernel-mirror contract — mirrored verbatim as gxWasteNgrams in
    waste_filter_spec.JS_KERNEL, which recomputes this live on every slider
    move from the html embed's rows + the current classify(r,P)."""
    agg: dict = {}
    for r in classified:
        if r["block"] not in ("Block 1", "Block 2"):
            continue
        for g in term_ngrams(r["term"]):
            e = agg.setdefault(g, {"ngram": g, "cost": 0.0, "terms": 0})
            e["cost"] += r["cost"]
            e["terms"] += 1
    rows = list(agg.values())
    top_sorted = sorted(rows, key=lambda e: (-e["cost"], e["ngram"]))[:top_n]
    top = [{"ngram": e["ngram"], "cost": _round2(e["cost"]), "terms": e["terms"]}
           for e in top_sorted]
    conc = analytics.concentration(rows, "cost", top_n=concentration_top_n)
    return {"top": top, "concentration": conc}


def advisor_summary(model: dict, top_n: int = 10) -> str:
    """Advisor negatives summary — the 'recommend' step of the emit -> report
    -> recommend -> offer-apply loop (google-ads-foundation/references/
    artifact-formats.md). Printed by build_waste_filter.py after every emit.
    Every number is read from `model` (compute_model's own output) — never
    re-derived, never narrated from memory."""
    s = model["summary"]
    cur = model["provenance"]["currency"]
    lines = ["", "=== Advisor — top negatives to add ==="]
    if s["total"] == 0:
        lines.append(
            "0 / 0 qualify under the current thresholds — a clean result, not "
            "an error. See the report's sensitivity table for where near-misses "
            "sit if you want to lower the bar.")
        return "\n".join(lines)

    def _rows_in(block):
        rows = [r for r in model["rows"] if r["block"] == block]
        rows.sort(key=lambda r: -r["cost"])
        return rows

    b1, b2 = _rows_in("Block 1"), _rows_in("Block 2")
    if b1:
        lines.append(f"\nCritical — Block 1, never-converted waste "
                     f"({len(b1)} term(s), {_fmt_money(sum(r['cost'] for r in b1), cur)}). "
                     "Add as negatives:")
        for r in b1[:top_n]:
            lines.append(f"  - \"{r['term']}\" ({r['match_type']}) in {r['campaign']} — "
                        f"{_fmt_money(r['cost'], cur)}, 0 conv/90d")
    if b2:
        lines.append(f"\nHigh — Block 2, decaying converters "
                     f"({len(b2)} term(s), {_fmt_money(sum(r['cost'] for r in b2), cur)}). "
                     "Review, then negate:")
        for r in b2[:top_n]:
            lines.append(f"  - \"{r['term']}\" ({r['match_type']}) in {r['campaign']} — "
                        f"{_fmt_money(r['cost'], cur)}, {r['conv90']:.2f} conv/90d but "
                        f"{r['conv30']:.2f} conv/30d")

    top_ngrams = (model.get("ngrams") or {}).get("top") or []
    if top_ngrams:
        conc = model["ngrams"]["concentration"]
        shown = top_ngrams[:5]
        lines.append(f"\nTop wasteful n-grams (top {len(shown)} carry "
                     f"{conc['top_share'] * 100:.1f}% of n-gram-weighted waste; "
                     f"HHI {conc['hhi']:.1f}, effective N {conc['effective_n']:.2f}) — "
                     "candidates for a shared/account negative list:")
        for g in shown:
            lines.append(f"  - \"{g['ngram']}\" — {_fmt_money(g['cost'], cur)} across "
                        f"{g['terms']} term(s)")

    lines.append(f"\nWasted spend across both blocks: {_fmt_money(s['wasted'], cur)}.")
    lines.append(
        "Want the Google Ads Editor CSVs for these? I can generate negative_keywords "
        "(Block 1 now, Block 2 once you confirm the review) via make_editor_csv.py — "
        "see google-ads-foundation/references/artifact-formats.md for the apply path.")
    return "\n".join(lines)


def provenance(findings: dict, params: dict) -> dict:
    meta = findings.get("meta") or {}
    return {
        "client_name": meta.get("client_name", ""),
        "account_id": meta.get("account_id", ""),
        "currency": meta.get("currency", ""),
        "window_90d": meta.get("window_90d", ""),
        "window_30d": meta.get("window_30d", ""),
        "generated": meta.get("generated", ""),
        # Canonical live-pull token (HM-572): "mcp"; CSV path stamps "user_csv".
        "source": meta.get("source") or "mcp",
        "params": dict(params),
    }


def compute_model(findings: dict) -> dict:
    """Assemble the full model at the resolved params. JSON-serializable —
    safe to embed in the HTML explorer for live recompute. This is the single
    source of truth; presentation (md sections, html spec, xlsx layout) lives in
    waste_filter_spec / waste_filter_xlsx_spec and the shared render toolkit."""
    params = resolve_params(findings.get("params"))
    bench = build_benchmarks(findings["benchmarks"])
    universe = build_universe(findings["search_terms"], bench)
    classified = classify(universe, params)
    return {
        "provenance": provenance(findings, params),
        "params": params,
        "benchmarks": [bench[k] for k in bench],
        "rows": classified,
        "summary": summarize(classified),
        "sensitivity": sensitivity(universe, params),
        "near_misses_block1": near_misses(universe, params, "Block 1"),
        "near_misses_block2": near_misses(universe, params, "Block 2"),
        "ngrams": waste_ngrams(classified),
        "match_types": MATCH_TYPES,
        "cost_ladder": COST_LADDER,
        "_universe": universe,  # unclassified rows for renderers that re-tune live
    }
