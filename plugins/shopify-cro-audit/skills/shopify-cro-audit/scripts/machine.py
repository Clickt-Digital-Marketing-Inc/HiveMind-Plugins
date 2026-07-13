#!/usr/bin/env python3
# Copyright (c) 2026 Clickt Digital Marketing Inc. All rights reserved.
"""Deterministic analytics assembler + merge for the Shopify CRO audit.

The CRO analog of the meta-ads-audit ``prescore.py`` with one structural
difference: the CRO framework has no check IDs — the machine-scored unit is
the analytics FIELD. :func:`compute_machine` assembles the payload's entire
Step-1 ``analytics`` block (PERCENT units, 2dp) from the same deterministic
sources the rest of the toolchain consumes — ``manual_csv`` adapter outputs
(GA4 + Shopify UI exports, FRACTION units) and saved Shopify MCP raw pulls
(``shopify_rows``, FRACTION units) — and :func:`merge_into_payload` then
REPLACES the model-authored (transcribed) values at build time, logging every
disagreement (the built-in drift detector). Fields with no machine source are
*skipped* — they stay transcribed — so both input paths degrade gracefully.

Units pin (binding — CONTRACTS.md): the payload ``analytics`` block is
PERCENT end-to-end; every input source ships FRACTIONS. The fraction→percent
conversion happens here, exactly once, at the payload boundary
(``_round_half_up(frac × 100, 2)``; share columns 1dp). Rates are recomputed
from counts whenever the counts exist (counts win over shipped rates); AOV is
the one exception — VERBATIM always (SHAPE-NOTES trap: Shopify's
``average_order_value`` is neither total_sales/orders nor net_sales/orders,
so it is never recomputed and never averaged).

``inputs`` shape (both keys optional; ``compute_machine`` returns None when
nothing at all is usable)::

    {
      "csv": {                      # manual_csv adapter outputs, keyed by the
        "shopify-conversion.csv":   #   canonical --csv-dir filename; each
            (funnel, meta),         #   value is the adapter's (data, meta)
        "ga4-funnel.csv": ...,      #   tuple (manual_csv.load_csv_dir shape)
        "ga4-device.csv": ...,
        "ga4-channels.csv": ...,
        "ga4-landing.csv": ...,
        "ga4-new-returning.csv": ...,
        "shopify-traffic-source.csv": ...,
        "shopify-landing.csv": ...,
        "shopify-sales-product.csv": ...,
        "shopify-customers.csv": ...,
        "shopify-aov.csv": ...,
      },
      "raw": {                      # PATHS to saved Shopify MCP result files
        "shop_info": path,          #   (--raw-dir filenames; the ".json"
        "analytics_funnel": path,   #   suffix is tolerated on the keys).
        "analytics_device": path,   #   Loaded via shopify_rows (loud
        "analytics_referrer": path, #   RawResultError on bad files), stamped
        "analytics_landing": path,  #   with file_stamp, checksum-verified via
        "analytics_products": path, #   checksum_note. orders.json /
        "analytics_totals": path,   #   products.json feed other modules and
        "analytics_customers": path,#   are ignored here.
      },
    }

Per-field source precedence (plan §A; first usable source wins, single source
per block — funnel stages are NEVER mixed across sources)::

    funnel                 shopify-conversion.csv > analytics_funnel.json
                           > ga4-funnel.csv  (GA4 counts USERS — basis noted)
    device                 ga4-device.csv > analytics_device.json
    channels               ga4-channels.csv > shopify-traffic-source.csv
                           > analytics_referrer.json
    landing_pages          ga4-landing.csv > shopify-landing.csv
                           > analytics_landing.json
    revenue_concentration  shopify-sales-product.csv > analytics_products.json
    new_vs_returning       ga4-new-returning.csv ONLY (the only session-basis
                           source; Shopify customers = order-share evidence)
    aov                    shopify-aov.csv > analytics_totals.json (VERBATIM)
    meta.currency          shop_info.json (fill-if-blank only)

Landing-page names are URL-normalized BEFORE any math
(``shopify_rows.normalize_url``: lowercase, strip ?query, strip trailing "/")
and duplicates merge (sessions sum, cvr sessions-weighted). Full-universe
math happens before the bounded embeds: ``landing_pages`` is the top-25 by
sessions and ``revenue_concentration`` the top-10 by revenue, but every
``share_pct`` is computed against the FULL universe totals (1dp), and the
full fraction-unit universes are returned in ``machine["universes"]`` for
``concentration.py`` / ``cvr_signals.py`` to consume. When two sources cover
the same block, total sessions diverging by more than ``DIVERGENCE_NOTE``
(10%) earns an honest note.

Machine Read verdicts mirror the workbook formulas via
``audit_model.read_verdict`` (funnel stages + Mobile/Desktop device rows
ONLY — Tablet/other have no benchmark) and ``audit_model.aov_band``.

:func:`merge_into_payload` is PURE (deep copy; neither argument mutated).
Machine values REPLACE transcribed values; every material disagreement is
logged as ``machine: analytics.funnel.atc_rate 6.20->6.10
(shopify-conversion.csv)`` — counts correct on ANY difference, rates/money on
``> RATE_TOL`` (0.05) absolute difference. Blank/absent payload fields are
``filled``; machine-uncomputable fields are ``skipped`` (with reasons). The
merge NEVER touches ``meta`` (except ``meta.currency`` fill-if-blank),
``steps_detail``, or ``findings``. Returns ``(merged, machine_block,
log_lines)`` with ``machine_block = {applied, corrected, filled, skipped,
reads, sources, notes}``.

Stdlib only. Deterministic: no wall clock, fixed iteration and note order,
sorted embeds, half-up rounding everywhere (never banker's).
"""
from __future__ import annotations

import copy
import math
from pathlib import Path

from audit_model import (BENCH, FUNNEL_STAGES, _device_bench_key,
                         _round_half_up, aov_band, read_verdict)
import shopify_rows

RATE_TOL = 0.05         # ⚙ abs correction threshold for rates/money (percent / currency units)
DIVERGENCE_NOTE = 0.10  # ⚙ relative sessions divergence across sources worth a note
TOP_PAGES = 25          # bounded landing_pages embed (shares stay full-universe)
TOP_PRODUCTS = 10       # bounded revenue_concentration embed


class MachineError(ValueError):
    """The `inputs` mapping is malformed (wrong shapes — not missing data)."""


# ── source precedence tables (plan §A; first usable candidate wins) ──────────

_FUNNEL_SOURCES = (("csv", "shopify-conversion.csv"),
                   ("raw", "analytics_funnel"),
                   ("csv", "ga4-funnel.csv"))
_DEVICE_SOURCES = (("csv", "ga4-device.csv"),
                   ("raw", "analytics_device"))
_CHANNEL_SOURCES = (("csv", "ga4-channels.csv"),
                    ("csv", "shopify-traffic-source.csv"),
                    ("raw", "analytics_referrer"))
_LANDING_SOURCES = (("csv", "ga4-landing.csv"),
                    ("csv", "shopify-landing.csv"),
                    ("raw", "analytics_landing"))
_PRODUCT_SOURCES = (("csv", "shopify-sales-product.csv"),
                    ("raw", "analytics_products"))
_NVR_SOURCES = (("csv", "ga4-new-returning.csv"),)
_AOV_SOURCES = (("csv", "shopify-aov.csv"),
                ("raw", "analytics_totals"))
_CUSTOMER_SOURCES = (("csv", "shopify-customers.csv"),
                     ("raw", "analytics_customers"))

# Raw --raw-dir keys -> shopify_rows adapters (fixed load order). shop_info
# is special-cased (flat object, no envelope).
_RAW_ADAPTERS = {
    "analytics_funnel": shopify_rows.funnel_from_table,
    "analytics_device": shopify_rows.device_rows_from_table,
    "analytics_referrer": shopify_rows.referrer_rows_from_table,
    "analytics_landing": shopify_rows.landing_rows_from_table,
    "analytics_products": shopify_rows.product_rows_from_table,
    "analytics_totals": shopify_rows.totals_from_table,
    "analytics_customers": shopify_rows.customers_from_table,
}
_RAW_ORDER = ("shop_info", "analytics_funnel", "analytics_device",
              "analytics_referrer", "analytics_landing", "analytics_products",
              "analytics_totals", "analytics_customers")

# Fraction-source funnel keys -> payload keys (shopify_rows.funnel_from_table
# / manual_csv funnel adapters emit the left column; the payload/workbook
# consume the right — count keys byte-match audit_model.FUNNEL_STAGES).
_FUNNEL_COUNTS = (("sessions", "sessions"),
                  ("atc_sessions", "atc"),
                  ("checkout_sessions", "checkout"),
                  ("purchase_sessions", "purchases"))
_FUNNEL_RATES = (("atc_sessions", "atc_rate"),
                 ("checkout_sessions", "checkout_rate"),
                 ("purchase_sessions", "cvr"))

# Merge field specs: (payload key, kind) — kind drives the correction rule
# (count: any diff; rate/money: > RATE_TOL abs).
_FUNNEL_MERGE = (("sessions", "count"), ("atc", "count"),
                 ("checkout", "count"), ("purchases", "count"),
                 ("atc_rate", "rate"), ("checkout_rate", "rate"),
                 ("cvr", "rate"))
_NVR_MERGE = (("new_cvr", "rate"), ("returning_cvr", "rate"))
# List blocks: payload key -> (row name key, ((cell, kind), ...)).
_LIST_SPECS = {
    "device": ("device", (("sessions", "count"), ("cvr", "rate"))),
    "channels": ("channel", (("sessions", "count"), ("cvr", "rate"),
                             ("revenue", "money"))),
    "landing_pages": ("page", (("sessions", "count"),
                               ("share_pct", "rate"))),
    "revenue_concentration": ("product", (("revenue", "money"),
                                          ("share_pct", "rate"))),
}
_SKIP_REASONS = {
    "funnel": "no funnel source (shopify-conversion.csv / "
              "analytics_funnel.json / ga4-funnel.csv)",
    "device": "no device source (ga4-device.csv / analytics_device.json)",
    "channels": "no channels source (ga4-channels.csv / "
                "shopify-traffic-source.csv / analytics_referrer.json)",
    "landing_pages": "no landing-pages source (ga4-landing.csv / "
                     "shopify-landing.csv / analytics_landing.json)",
    "revenue_concentration": "no products source (shopify-sales-product.csv "
                             "/ analytics_products.json)",
    "new_vs_returning": "no ga4-new-returning.csv — GA4 is the only "
                        "session-basis new-vs-returning source (Shopify "
                        "customer splits are order-share evidence)",
    "aov": "no AOV source (shopify-aov.csv / analytics_totals.json) — AOV "
           "is verbatim-only, never recomputed",
    "currency": "no shop_info.json — currency not machine-verifiable",
}


# ── small numeric helpers ────────────────────────────────────────────────────

def _pct(frac, nd: int = 2) -> float:
    """FRACTION -> PERCENT at the payload boundary (half-up, default 2dp).
    The ONE place in the toolchain where the unit changes."""
    return _round_half_up(float(frac) * 100.0, nd)


def _num_or_none(v):
    """Loose numeric parse (payload values may be transcribed strings)."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        f = float(v)
        return None if (f != f or math.isinf(f)) else f
    if isinstance(v, str):
        s = v.strip().replace(",", "").replace("%", "")
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _is_blank(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _fmt_val(v, kind: str) -> str:
    """Log-line value formatting: counts as ints, rates/money 2dp."""
    n = _num_or_none(v)
    if n is None:
        return str(v)
    if kind == "count" and float(n).is_integer():
        return str(int(n))
    return "%.2f" % n


def _row_cvr_pct(row) -> float | None:
    """Row CVR in PERCENT: recomputed from counts when a conversion count
    exists (counts win), else the shipped fraction; None when neither."""
    if not isinstance(row, dict):
        return None
    sess = row.get("sessions")
    conv = row.get("conversions")
    if conv is not None and sess:
        return _pct(int(conv) / int(sess))
    cvr = row.get("cvr")
    if isinstance(cvr, (int, float)) and not isinstance(cvr, bool):
        return _pct(cvr)
    return None


def _sessions_total(data) -> int:
    """Total sessions of a candidate (funnel dict or segment row list)."""
    if isinstance(data, dict):
        s = data.get("sessions")
        return int(s) if isinstance(s, (int, float)) and not isinstance(s, bool) else 0
    total = 0
    for r in data or []:
        s = r.get("sessions") if isinstance(r, dict) else None
        if isinstance(s, (int, float)) and not isinstance(s, bool):
            total += int(s)
    return total


# ── input access ─────────────────────────────────────────────────────────────

def _csv_entry(csv_in: dict, key: str):
    """(data, meta) for a --csv-dir key, or None. Loud on a wrong shape."""
    v = (csv_in or {}).get(key)
    if v is None:
        return None
    if isinstance(v, (tuple, list)) and len(v) == 2:
        return v[0], dict(v[1] or {})
    raise MachineError(
        f"inputs['csv'][{key!r}] must be the manual_csv (data, meta) tuple — "
        f"got {type(v).__name__}")


def _load_raw(raw_in: dict) -> dict:
    """Load every recognized --raw-dir path via shopify_rows (fixed order).

    Returns {key: (data, file-label)} plus ``stamps`` ({file: file_stamp})
    and ``checksum_notes`` (summaryMetric-vs-Σrows warnings, fixed order).
    Unknown keys (orders/products — other modules' inputs) are ignored.
    Loading failures raise shopify_rows.RawResultError loudly — never guess.
    """
    paths: dict[str, str] = {}
    for k, v in (raw_in or {}).items():
        if v is None:
            continue
        key = str(k)
        if key.endswith(".json"):
            key = key[:-5]
        paths[key] = str(v)
    out: dict = {"stamps": {}, "checksum_notes": []}
    for key in _RAW_ORDER:
        p = paths.get(key)
        if p is None:
            continue
        stamp = shopify_rows.file_stamp(p)
        label = stamp["file"]
        out["stamps"][label] = stamp
        if key == "shop_info":
            out[key] = (shopify_rows.load_shop_info(p), label)
            continue
        env = shopify_rows.load_envelope(p)
        note = shopify_rows.checksum_note(env)
        if note:
            out["checksum_notes"].append(f"{label}: {note}")
        out[key] = (_RAW_ADAPTERS[key](env), label)
    return out


def _candidates(spec, csv_in: dict, raw: dict) -> list:
    """Present candidates for one block, precedence order: [(label, data,
    meta)] — csv label = the canonical filename, raw label = the real file
    basename; raw meta is {} (MCP pulls carry no window/notes)."""
    out = []
    for kind, key in spec:
        if kind == "csv":
            e = _csv_entry(csv_in, key)
            if e is not None:
                out.append((key, e[0], e[1]))
        else:
            e = raw.get(key)
            if e is not None:
                out.append((e[1], e[0], {}))
    return out


def _usable_funnel(data) -> bool:
    return isinstance(data, dict) and bool(data.get("sessions"))


def _usable_rows(data) -> bool:
    return isinstance(data, list) and len(data) > 0


# ── payload-block builders (fraction in, percent out) ────────────────────────

def _funnel_payload(f: dict) -> dict:
    """Fraction funnel dict -> percent payload funnel. Counts pass through as
    ints; rates recomputed from counts when the counts exist (counts win),
    else converted from the shipped fraction. Stage keys absent from the
    source stay absent (measured-stages-only scoring downstream)."""
    out: dict = {}
    for src, dst in _FUNNEL_COUNTS:
        v = f.get(src)
        if v is not None:
            out[dst] = int(v)
    sessions = f.get("sessions")
    for cnt_key, rate_key in _FUNNEL_RATES:
        cnt = f.get(cnt_key)
        if sessions and cnt is not None:
            out[rate_key] = _pct(int(cnt) / int(sessions))
        elif f.get(rate_key) is not None:
            out[rate_key] = _pct(f[rate_key])
    return out


def _segment_payload(rows: list, name_key: str, *, revenue: bool) -> list:
    """Fraction segment rows -> payload rows [{name_key, sessions, cvr?,
    revenue?}] (cvr percent 2dp; revenue money 2dp; absent keys omitted)."""
    out = []
    for r in rows:
        rec: dict = {name_key: str(r.get("name", "")),
                     "sessions": int(r.get("sessions") or 0)}
        cvr = _row_cvr_pct(r)
        if cvr is not None:
            rec["cvr"] = cvr
        if revenue and r.get("revenue") is not None:
            rec["revenue"] = _round_half_up(float(r["revenue"]), 2)
        out.append(rec)
    return out


def _merge_pages(rows: list) -> list:
    """Defensive URL re-normalization + duplicate merge over the FULL page
    universe (idempotent on adapter output — mirrors
    shopify_rows.landing_rows_from_table: sessions sum, cvr
    sessions-weighted, conversion counts summed). Sorted sessions desc,
    name asc."""
    agg: dict[str, dict] = {}
    for r in rows:
        name = shopify_rows.normalize_url(r.get("name"))
        a = agg.setdefault(name, {"sessions": 0, "_wsum": 0.0, "_scvr": 0,
                                  "conversions": None})
        sess = int(r.get("sessions") or 0)
        a["sessions"] += sess
        cvr = r.get("cvr")
        if isinstance(cvr, (int, float)) and not isinstance(cvr, bool):
            a["_wsum"] += sess * float(cvr)
            a["_scvr"] += sess
        conv = r.get("conversions")
        if conv is not None:
            a["conversions"] = (a["conversions"] or 0) + int(conv)
    out = []
    for name in sorted(agg):
        a = agg[name]
        rec: dict = {"name": name, "sessions": a["sessions"]}
        if a["conversions"] is not None:
            rec["conversions"] = a["conversions"]
        if a["_scvr"] > 0:
            rec["cvr"] = a["_wsum"] / a["_scvr"]
        out.append(rec)
    out.sort(key=lambda r: (-r["sessions"], r["name"]))
    return out


def _pages_payload(universe: list) -> list:
    """Top-TOP_PAGES landing-page embed; share_pct vs the FULL universe
    sessions total (1dp)."""
    total = sum(r["sessions"] for r in universe)
    out = []
    for r in universe[:TOP_PAGES]:
        rec = {"page": r["name"], "sessions": r["sessions"],
               "share_pct": (_pct(r["sessions"] / total, 1)
                             if total > 0 else 0.0)}
        out.append(rec)
    return out


def _products_payload(rows: list) -> list:
    """Top-TOP_PRODUCTS revenue embed; share_pct vs the FULL universe revenue
    total (1dp). Rows arrive revenue-desc from the adapters; the sort is
    re-applied defensively."""
    ordered = sorted(rows, key=lambda r: (-(float(r.get("revenue") or 0.0)),
                                          str(r.get("product", ""))))
    total = sum(float(r.get("revenue") or 0.0) for r in ordered)
    out = []
    for r in ordered[:TOP_PRODUCTS]:
        rev = float(r.get("revenue") or 0.0)
        out.append({"product": str(r.get("product", "")),
                    "revenue": _round_half_up(rev, 2),
                    "share_pct": (_pct(rev / total, 1) if total > 0 else 0.0)})
    return out


def _nvr_payload(rows: list) -> dict:
    """GA4 new-vs-returning rows -> {new_cvr, returning_cvr} (percent 2dp;
    rows outside the canonical 'new'/'returning' names — e.g. '(not set)' —
    are ignored; absent rates omitted)."""
    by = {}
    for r in rows:
        name = str(r.get("name", "")).strip().lower()
        if name in ("new", "returning") and name not in by:
            by[name] = r
    out: dict = {}
    for name, key in (("new", "new_cvr"), ("returning", "returning_cvr")):
        v = _row_cvr_pct(by.get(name))
        if v is not None:
            out[key] = v
    return out


def _divergence_notes(block_label: str, cands: list) -> list:
    """GA4-vs-Shopify honesty notes: the chosen source's total sessions vs
    each unchosen candidate's; relative gap > DIVERGENCE_NOTE -> note."""
    notes = []
    if len(cands) < 2:
        return notes
    label0, s0 = cands[0][0], _sessions_total(cands[0][1])
    if s0 <= 0:
        return notes
    for label, data, _meta in cands[1:]:
        s = _sessions_total(data)
        if s <= 0:
            continue
        rel = abs(s0 - s) / s0
        if rel > DIVERGENCE_NOTE:
            notes.append(
                f"{block_label}: sessions diverge "
                f"{_round_half_up(rel * 100.0, 1)}% between {label0} "
                f"({s0:,}) and {label} ({s:,}) — different counting bases; "
                f"{label0} used.")
    return notes


# ── the machine block ────────────────────────────────────────────────────────

def compute_machine(inputs) -> dict | None:
    """Assemble the percent-unit ``analytics`` block + Reads + universes from
    deterministic inputs (see the module docstring for the ``inputs`` shape
    and the per-field precedence). Returns None when nothing is usable.

    Output::

        {"analytics": {...percent payload block, computed fields only...},
         "currency": str?,                    # shop_info currencyCode
         "reads":   {"funnel.cvr": ..., "device.mobile": ..., "aov_band": ...},
         "sources": {block: source-file label},
         "skipped": [{"field", "reason"}, ...],   # machine-uncomputable
         "notes":   [...],                        # fixed order
         "stamps":  {file: file_stamp},
         "windows": {block: "YYYY-MM-DD – YYYY-MM-DD" | "", "default": ...},
         "universes": {...FULL fraction-unit universes for concentration /
                       cvr_signals: funnel, device, channels, pages,
                       products, nvr, totals, customers...}}
    """
    inputs = inputs or {}
    csv_in = inputs.get("csv") or {}
    raw_in = inputs.get("raw") or {}
    if not isinstance(csv_in, dict) or not isinstance(raw_in, dict):
        raise MachineError("inputs['csv'] / inputs['raw'] must be mappings")
    if not csv_in and not raw_in:
        return None
    raw = _load_raw(raw_in)

    analytics: dict = {}
    sources: dict = {}
    reads: dict = {}
    skipped: list = []
    notes: list = []
    universes: dict = {}
    windows: dict = {}
    stamps: dict = dict(raw["stamps"])
    for key in sorted(csv_in):
        e = _csv_entry(csv_in, key)
        if e is None:
            continue
        st = e[1].get("stamp")
        if isinstance(st, dict):
            stamps[str(st.get("file") or key)] = dict(st)

    def skip(field: str, reason: str) -> None:
        skipped.append({"field": field, "reason": reason})

    # ---- funnel (single source — stages never mixed across sources) --------
    cands = [c for c in _candidates(_FUNNEL_SOURCES, csv_in, raw)
             if _usable_funnel(c[1])]
    if cands:
        label, data, meta = cands[0]
        analytics["funnel"] = _funnel_payload(data)
        sources["funnel"] = label
        universes["funnel"] = copy.deepcopy(data)
        windows["funnel"] = str(meta.get("window") or "")
        for n in meta.get("notes") or []:
            notes.append(f"funnel ({label}): {n}")
        notes.extend(_divergence_notes("funnel", cands))
    else:
        skip("analytics.funnel", _SKIP_REASONS["funnel"])

    # ---- device -------------------------------------------------------------
    cands = [c for c in _candidates(_DEVICE_SOURCES, csv_in, raw)
             if _usable_rows(c[1])]
    if cands:
        label, data, meta = cands[0]
        analytics["device"] = _segment_payload(data, "device", revenue=False)
        sources["device"] = label
        universes["device"] = copy.deepcopy(data)
        windows["device"] = str(meta.get("window") or "")
        notes.extend(_divergence_notes("device", cands))
    else:
        skip("analytics.device", _SKIP_REASONS["device"])

    # ---- channels -----------------------------------------------------------
    cands = [c for c in _candidates(_CHANNEL_SOURCES, csv_in, raw)
             if _usable_rows(c[1])]
    if cands:
        label, data, meta = cands[0]
        analytics["channels"] = _segment_payload(data, "channel",
                                                 revenue=True)
        sources["channels"] = label
        universes["channels"] = copy.deepcopy(data)
        windows["channels"] = str(meta.get("window") or "")
        notes.extend(_divergence_notes("channels", cands))
    else:
        skip("analytics.channels", _SKIP_REASONS["channels"])

    # ---- landing pages (URL-normalized BEFORE any math; full universe) ------
    cands = [c for c in _candidates(_LANDING_SOURCES, csv_in, raw)
             if _usable_rows(c[1])]
    if cands:
        label, data, meta = cands[0]
        universe = _merge_pages(data)
        analytics["landing_pages"] = _pages_payload(universe)
        sources["landing_pages"] = label
        universes["pages"] = universe
        windows["landing_pages"] = str(meta.get("window") or "")
        notes.extend(_divergence_notes("landing pages", cands))
    else:
        skip("analytics.landing_pages", _SKIP_REASONS["landing_pages"])

    # ---- revenue concentration (products) ------------------------------------
    cands = [c for c in _candidates(_PRODUCT_SOURCES, csv_in, raw)
             if _usable_rows(c[1])]
    if cands:
        label, data, meta = cands[0]
        analytics["revenue_concentration"] = _products_payload(data)
        sources["revenue_concentration"] = label
        universes["products"] = copy.deepcopy(data)
        windows["products"] = str(meta.get("window") or "")
    else:
        skip("analytics.revenue_concentration",
             _SKIP_REASONS["revenue_concentration"])

    # ---- new vs returning (GA4 only — session basis) -------------------------
    cands = [c for c in _candidates(_NVR_SOURCES, csv_in, raw)
             if _usable_rows(c[1])]
    nvr_out = _nvr_payload(cands[0][1]) if cands else {}
    if nvr_out:
        label, data, meta = cands[0]
        analytics["new_vs_returning"] = nvr_out
        sources["new_vs_returning"] = label
        universes["nvr"] = copy.deepcopy(data)
        windows["new_vs_returning"] = str(meta.get("window") or "")
    elif cands:
        skip("analytics.new_vs_returning",
             f"{cands[0][0]} has no usable new/returning CVR rows")
    else:
        skip("analytics.new_vs_returning", _SKIP_REASONS["new_vs_returning"])

    # ---- AOV (VERBATIM — never recomputed, never averaged) -------------------
    cands = [c for c in _candidates(_AOV_SOURCES, csv_in, raw)
             if isinstance(c[1], dict) and c[1].get("aov") is not None]
    if cands:
        label, data, meta = cands[0]
        analytics["aov"] = float(data["aov"])
        sources["aov"] = label
        windows["aov"] = str(meta.get("window") or "")
        if universes.get("totals") is None:
            universes["totals"] = copy.deepcopy(data)
    else:
        skip("analytics.aov", _SKIP_REASONS["aov"])
    # richer raw totals win the universes slot when present
    if raw.get("analytics_totals") is not None:
        universes["totals"] = copy.deepcopy(raw["analytics_totals"][0])

    # ---- checksum notes (fixed raw order) -------------------------------------
    notes.extend(raw["checksum_notes"])

    # ---- customers (order-share EVIDENCE only — never a CVR) ------------------
    for label, data, meta in _candidates(_CUSTOMER_SOURCES, csv_in, raw):
        summ = meta.get("customers_summary") if meta else None
        if summ is None and isinstance(data, dict) and data:
            summ = data
        rate = (summ or {}).get("returning_customer_rate")
        if rate is not None:
            notes.append(
                f"New-vs-returning CVR is session-basis (GA4 only); {label} "
                f"shows returning customers at {_pct(rate, 1)}% by order "
                f"share — evidence, not a CVR.")
            universes["customers"] = dict(summ)
            break

    # ---- currency (meta fill-if-blank only) -----------------------------------
    currency = ""
    if raw.get("shop_info") is not None:
        info, label = raw["shop_info"]
        currency = str(info.get("currencyCode") or "").strip()
        if currency:
            sources["currency"] = label
    if not currency:
        skip("meta.currency", _SKIP_REASONS["currency"])

    if not analytics and not currency:
        return None

    # ---- machine Reads (mirror the workbook formulas) --------------------------
    funnel_out = analytics.get("funnel") or {}
    for rate_key, bench_key, _label, _cnt in FUNNEL_STAGES:
        v = read_verdict(funnel_out.get(rate_key), BENCH[bench_key])
        if v:
            reads[f"funnel.{rate_key}"] = v
    for d in analytics.get("device") or []:
        bkey = _device_bench_key(d.get("device"))
        if bkey:
            v = read_verdict(d.get("cvr"), BENCH[bkey])
            if v:
                reads[f"device.{d['device']}"] = v
    if "aov" in analytics:
        band = aov_band(analytics["aov"])
        if band:
            reads["aov_band"] = band

    windows["default"] = next(
        (windows[k] for k in ("funnel", "landing_pages", "channels", "device",
                              "products", "new_vs_returning", "aov")
         if windows.get(k)), "")

    out: dict = {
        "analytics": analytics,
        "reads": reads,
        "sources": sources,
        "skipped": skipped,
        "notes": notes,
        "stamps": stamps,
        "windows": windows,
        "universes": universes,
    }
    if currency:
        out["currency"] = currency
    return out


# ── merge into the model-authored payload ────────────────────────────────────

def merge_into_payload(payload: dict, machine: dict | None
                       ) -> tuple[dict, dict | None, list[str]]:
    """Enforce the machine-computed analytics over the transcribed payload.

    PURE: deep-copies the payload, mutates neither argument. Machine values
    REPLACE transcribed values field by field; disagreements are corrections
    (counts: any diff; rates/money: > RATE_TOL abs) logged as
    ``machine: analytics.funnel.atc_rate 6.20->6.10 (shopify-conversion.csv)``.
    Blank/absent payload fields become ``filled``. Dict blocks (funnel /
    new_vs_returning) are replaced WHOLE — a transcribed stage the machine
    source lacks is DROPPED (and logged), never left to mix sources within
    the funnel. List blocks are replaced wholesale; matched rows (by
    canonical name — landing pages URL-normalized) get per-cell corrections
    and entity-set changes one ``.entities`` correction. NEVER touches
    ``meta`` (except ``meta.currency`` fill-if-blank), ``steps_detail``, or
    ``findings``. Returns (merged, machine_block, log_lines);
    machine=None -> (payload, None, []).
    """
    if machine is None:
        return payload, None, []
    merged = copy.deepcopy(payload or {})
    analytics = merged.get("analytics")
    if not isinstance(analytics, dict):
        analytics = {}
        merged["analytics"] = analytics
    m = machine.get("analytics") or {}
    sources = machine.get("sources") or {}
    applied: list[str] = []
    corrected: list[dict] = []
    filled: list[str] = []
    log: list[str] = []
    notes_out = list(machine.get("notes") or [])

    def src(block: str) -> str:
        return sources.get(block, "machine")

    def compare(path: str, old, new, kind: str, block: str) -> None:
        """old is known non-blank; record a correction when material."""
        ov = _num_or_none(old)
        nv = _num_or_none(new)
        if ov is None or nv is None:
            differs = str(old) != str(new)
        elif kind == "count":
            differs = int(round(ov)) != int(round(nv))
        else:
            differs = abs(ov - nv) > RATE_TOL
        if differs:
            corrected.append({"field": path, "from": old, "to": new})
            log.append(f"machine: {path} {_fmt_val(old, kind)}->"
                       f"{_fmt_val(new, kind)} ({src(block)})")

    def merge_dict_block(key: str, spec) -> None:
        if key not in m:
            return
        new_block = m[key]
        old_block = analytics.get(key)
        old_block = old_block if isinstance(old_block, dict) else {}
        for field, kind in spec:
            path = f"analytics.{key}.{field}"
            if field in new_block:
                applied.append(path)
                old = old_block.get(field)
                if _is_blank(old):
                    filled.append(path)
                else:
                    compare(path, old, new_block[field], kind, key)
            elif not _is_blank(old_block.get(field)):
                # whole-block replace: a transcribed stage the machine source
                # lacks is dropped, never left to mix sources within a block.
                corrected.append({"field": path,
                                  "from": old_block.get(field), "to": None})
                log.append(f"machine: {path} "
                           f"{_fmt_val(old_block.get(field), kind)}->dropped "
                           f"(single-source: not in {src(key)})")
        analytics[key] = copy.deepcopy(new_block)

    def merge_list_block(key: str) -> None:
        if key not in m:
            return
        name_key, cells = _LIST_SPECS[key]
        new_list = m[key]
        old_list = analytics.get(key)
        old_list = old_list if isinstance(old_list, list) else []
        path = f"analytics.{key}"
        applied.append(path)
        if not old_list:
            filled.append(path)
        else:
            def canon(n):
                s = str(n if n is not None else "")
                if key == "landing_pages":
                    return shopify_rows.normalize_url(s)
                return s.strip().casefold()

            old_by: dict = {}
            for r in old_list:
                if isinstance(r, dict):
                    old_by.setdefault(canon(r.get(name_key)), r)
            new_names = {canon(r.get(name_key)) for r in new_list}
            if new_names != set(old_by):
                corrected.append({"field": f"{path}.entities",
                                  "from": f"{len(old_list)} rows",
                                  "to": f"{len(new_list)} rows"})
                log.append(f"machine: {path}.entities {len(old_list)} rows->"
                           f"{len(new_list)} rows ({src(key)})")
            for r in new_list:
                o = old_by.get(canon(r.get(name_key)))
                if o is None:
                    continue
                for field, kind in cells:
                    if field not in r or _is_blank(o.get(field)):
                        continue
                    compare(f"{path}[{r.get(name_key)}].{field}",
                            o.get(field), r[field], kind, key)
        analytics[key] = copy.deepcopy(new_list)

    # Fixed processing order (drives the log-line order).
    merge_dict_block("funnel", _FUNNEL_MERGE)
    merge_list_block("device")
    merge_list_block("channels")
    merge_list_block("landing_pages")
    merge_list_block("revenue_concentration")
    merge_dict_block("new_vs_returning", _NVR_MERGE)
    if "aov" in m:
        path = "analytics.aov"
        applied.append(path)
        old = analytics.get("aov")
        if _is_blank(old):
            filled.append(path)
        else:
            compare(path, old, m["aov"], "money", "aov")
        analytics["aov"] = m["aov"]

    # meta.currency — the ONLY meta touch, and fill-if-blank only.
    currency = machine.get("currency")
    if currency:
        meta = merged.get("meta")
        if not isinstance(meta, dict):
            meta = {}
            merged["meta"] = meta
        if _is_blank(meta.get("currency")):
            meta["currency"] = currency
            applied.append("meta.currency")
            filled.append("meta.currency")
        elif str(meta.get("currency")).strip() != str(currency):
            notes_out.append(
                f"meta.currency left as transcribed "
                f"({str(meta.get('currency')).strip()}); "
                f"{src('currency')} reports {currency}.")

    block = {"applied": sorted(applied),
             "corrected": corrected,
             "filled": sorted(filled),
             "skipped": [dict(s) for s in machine.get("skipped") or []],
             "reads": dict(machine.get("reads") or {}),
             "sources": dict(sources),
             "notes": notes_out}
    return merged, block, log


# ── self-test (synthetic inputs; the real-capture smoke lives in tests) ──────

def _self_test() -> None:  # pragma: no cover - developer harness
    import json
    import tempfile

    checks = [0]

    def ok(cond, label):
        checks[0] += 1
        if not cond:
            raise AssertionError(f"self-test check failed: {label}")

    def envelope(cols, rows, **extra):
        doc = {"query": "q", "columns": [{"name": n, "dataType": t}
                                         for n, t in cols],
               "rows": rows, "rowCount": len(rows), "shopDomain": "t"}
        doc.update(extra)
        return json.dumps(doc)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)

        def w(name, text):
            p = root / name
            p.write_text(text, encoding="utf-8")
            return str(p)

        raw = {
            "shop_info": w("shop_info.json", json.dumps(
                {"name": "Test Store", "domain": "test.example",
                 "currencyCode": "CAD", "planName": "Basic"})),
            "analytics_funnel": w("analytics_funnel.json", envelope(
                [("sessions", "INTEGER"),
                 ("sessions_with_cart_additions", "INTEGER"),
                 ("sessions_that_reached_checkout", "INTEGER"),
                 ("sessions_that_completed_checkout", "INTEGER"),
                 ("conversion_rate", "PERCENT")],
                [["1000", "121", "90", "20", "0.02"]])),
            "analytics_device.json": w("analytics_device.json", envelope(
                [("session_device_type", "STRING"), ("sessions", "INTEGER"),
                 ("conversion_rate", "PERCENT")],
                [["mobile", "700", "0.0143"], ["desktop", "250", "0.0382"],
                 ["tablet", "50", "0.0068"]])),
            "analytics_referrer": w("analytics_referrer.json", envelope(
                [("referrer_source", "STRING"), ("sessions", "INTEGER"),
                 ("conversion_rate", "PERCENT")],
                [["search", "400", "0.024"], ["direct", "350", "0.0292"],
                 ["social", "230", "0.0035"], ["email", "20", "0.0548"]])),
            "analytics_landing": w("analytics_landing.json", envelope(
                [("landing_page_path", "STRING"), ("sessions", "INTEGER"),
                 ("conversion_rate", "PERCENT")],
                [["/", "300", "0.0365"]]
                + [[f"/products/p{i:02d}", str(200 - i), "0.02"]
                   for i in range(28)]
                + [["/Products/P00/?ref=x", "50", "0.04"]])),
            "analytics_products": w("analytics_products.json", envelope(
                [("product_title", "STRING"), ("net_sales", "MONEY"),
                 ("orders", "INTEGER")],
                [[f"SKU {chr(65 + i)}", str(1000.0 - i * 50), "2"]
                 for i in range(12)],
                summaryMetric={"label": "net_sales", "value": "8,700"})),
            "analytics_totals": w("analytics_totals.json", envelope(
                [("orders", "INTEGER"), ("net_sales", "MONEY"),
                 ("total_sales", "MONEY"),
                 ("average_order_value", "MONEY")],
                [["400", "150000.25", "180000.00", "250.47"]])),
            "analytics_customers": w("analytics_customers.json", envelope(
                [("customers", "INTEGER"), ("returning_customers", "INTEGER"),
                 ("returning_customer_rate", "PERCENT")],
                [["530", "173", "0.3264"]])),
        }

        # 1. raw-only machine block: percent boundary + counts-win rates.
        mach = compute_machine({"raw": raw})
        f = mach["analytics"]["funnel"]
        ok(f == {"sessions": 1000, "atc": 121, "checkout": 90,
                 "purchases": 20, "atc_rate": 12.1, "checkout_rate": 9.0,
                 "cvr": 2.0},
           "funnel counts int + rates recomputed from counts, percent 2dp")
        ok(mach["sources"]["funnel"] == "analytics_funnel.json",
           "raw funnel source label = file basename")
        dev = mach["analytics"]["device"]
        ok(dev[0] == {"device": "mobile", "sessions": 700, "cvr": 1.43},
           "device fraction 0.0143 -> 1.43 percent")
        ok(mach["reads"]["funnel.atc_rate"] == "At / above benchmark"
           and mach["reads"]["funnel.cvr"] == "Well below benchmark",
           "funnel Reads mirror read_verdict")
        ok(mach["reads"]["device.mobile"] == "Well below benchmark"
           and mach["reads"]["device.desktop"] == "Below benchmark"
           and "device.tablet" not in mach["reads"],
           "device Reads: Mobile/Desktop only (Tablet has no benchmark)")
        ok(mach["analytics"]["aov"] == 250.47
           and mach["reads"]["aov_band"].startswith("Over-$200"),
           "AOV verbatim (never total_sales/orders) + band read")
        pages = mach["analytics"]["landing_pages"]
        ok(len(pages) == 25, "landing pages top-25 embed")
        ok(mach["universes"]["pages"][0]["name"] == "/"
           and len(mach["universes"]["pages"]) == 29,
           "FULL page universe retained (30 rows -> 29 after URL merge)")
        p00 = next(p for p in mach["universes"]["pages"]
                   if p["name"] == "/products/p00")
        ok(p00["sessions"] == 250
           and abs(p00["cvr"] - (200 * 0.02 + 50 * 0.04) / 250) < 1e-12,
           "URL normalization before math: dup merged, cvr session-weighted")
        total_sess = sum(p["sessions"] for p in mach["universes"]["pages"])
        ok(pages[0]["share_pct"] == _pct(300 / total_sess, 1),
           "share_pct vs FULL universe (1dp), not the top-25 slice")
        prods = mach["analytics"]["revenue_concentration"]
        ok(len(prods) == 10 and prods[0]["product"] == "SKU A",
           "revenue concentration top-10 embed")
        tot_rev = sum(1000.0 - i * 50 for i in range(12))
        ok(prods[0]["share_pct"] == _pct(1000.0 / tot_rev, 1),
           "product share vs FULL universe revenue")
        ok(mach["currency"] == "CAD", "currency from shop_info")
        ok(any(s["field"] == "analytics.new_vs_returning"
               for s in mach["skipped"]),
           "new_vs_returning skipped without GA4 input")
        ok(any("order share — evidence, not a CVR" in n
               for n in mach["notes"]), "customers order-share note")
        ok("analytics_funnel.json" in mach["stamps"]
           and len(mach["stamps"]["analytics_funnel.json"]["sha256"]) == 64,
           "raw stamps present")
        ok(mach["universes"]["totals"]["aov"] == 250.47,
           "totals universe carries verbatim aov")

        # 2. determinism: same inputs -> byte-identical block.
        ok(compute_machine({"raw": raw}) == mach, "deterministic recompute")

        # 3. CSV precedence beats raw; funnel meta notes propagate; divergence.
        csv_funnel = ({"sessions": 2000, "atc_sessions": 100,
                       "checkout_sessions": 80, "purchase_sessions": 44,
                       "atc_rate": 0.05, "checkout_rate": 0.04, "cvr": 0.022},
                      {"window": "2026-01-01 – 2026-03-31",
                       "stamp": {"file": "shopify-conversion.csv",
                                 "sha256": "0" * 64, "bytes": 10},
                       "file": "shopify-conversion.csv", "n_rows_raw": 1,
                       "totals": None, "notes": ["universe totals row used "
                                                 "verbatim (1 period row(s) "
                                                 "not aggregated)"],
                       "basis": "sessions"})
        mach2 = compute_machine({"csv": {"shopify-conversion.csv": csv_funnel},
                                 "raw": raw})
        ok(mach2["sources"]["funnel"] == "shopify-conversion.csv",
           "funnel precedence: shopify-conversion.csv > analytics_funnel.json")
        ok(mach2["analytics"]["funnel"]["sessions"] == 2000
           and mach2["analytics"]["funnel"]["cvr"] == 2.2,
           "single-source funnel: no stage mixing with the raw pull")
        ok(any(n.startswith("funnel (shopify-conversion.csv):")
               for n in mach2["notes"]), "funnel source notes propagate")
        ok(any("funnel: sessions diverge 50.0% between "
               "shopify-conversion.csv (2,000) and analytics_funnel.json "
               "(1,000)" in n for n in mach2["notes"]),
           "GA4-vs-Shopify divergence >10% noted")
        ok(mach2["windows"]["funnel"] == "2026-01-01 – 2026-03-31"
           and mach2["windows"]["default"] == "2026-01-01 – 2026-03-31",
           "csv window propagates")

        # 4. ga4-funnel fallback (users basis note rides the meta notes).
        ga4_funnel = ({"sessions": 900, "purchase_sessions": 18,
                       "cvr": 0.02},
                      {"window": "", "stamp": {"file": "ga4-funnel.csv",
                                               "sha256": "1" * 64,
                                               "bytes": 9},
                       "file": "ga4-funnel.csv", "n_rows_raw": 4,
                       "totals": None,
                       "notes": ["GA4 funnel counts USERS, not sessions — "
                                 "users basis"], "basis": "users"})
        mach3 = compute_machine({"csv": {"ga4-funnel.csv": ga4_funnel}})
        ok(mach3["sources"]["funnel"] == "ga4-funnel.csv"
           and any("USERS" in n for n in mach3["notes"]),
           "ga4-funnel fallback with users-basis note")
        ok("atc_rate" not in mach3["analytics"]["funnel"],
           "unmeasured stages stay absent (measured-stages-only downstream)")

        # 5. nvr from GA4 rows; '(not set)' ignored.
        nvr_rows = ([{"name": "new", "sessions": 800, "cvr": 0.015},
                     {"name": "returning", "sessions": 200, "cvr": 0.032},
                     {"name": "(not set)", "sessions": 5}],
                    {"window": "", "stamp": {"file": "ga4-new-returning.csv",
                                             "sha256": "2" * 64, "bytes": 8},
                     "file": "ga4-new-returning.csv", "n_rows_raw": 3,
                     "totals": None, "notes": []})
        mach4 = compute_machine({"csv": {"ga4-new-returning.csv": nvr_rows}})
        ok(mach4["analytics"]["new_vs_returning"] ==
           {"new_cvr": 1.5, "returning_cvr": 3.2},
           "nvr percent block from GA4 rows")

        # 6. merge: purity + replace/corrections/filled/skipped + log format.
        payload = {
            "meta": {"store_name": "T", "currency": ""},
            "analytics": {
                "funnel": {"sessions": 999, "atc": 121, "checkout": 90,
                           "purchases": 20, "atc_rate": 12.08,
                           "checkout_rate": 4.40, "cvr": 2.30},
                "device": [
                    {"device": "Mobile", "sessions": 700, "cvr": 1.90},
                    {"device": "Desktop", "sessions": 250, "cvr": 3.85},
                    {"device": "Tablet", "sessions": 50, "cvr": 0.68}],
                "new_vs_returning": {"new_cvr": 1.70, "returning_cvr": 6.40},
                "aov": 84.90,
            },
            "steps_detail": {"heuristic": {"findings": []}},
            "findings": [{"id": "F-001", "severity": "High"}],
        }
        before = copy.deepcopy(payload)
        merged, block, log = merge_into_payload(payload, mach)
        ok(payload == before, "merge purity: input payload untouched")
        ok(merged["analytics"]["funnel"]["sessions"] == 1000
           and merged["analytics"]["funnel"]["cvr"] == 2.0,
           "machine values replace transcribed values")
        ok("machine: analytics.funnel.sessions 999->1000 "
           "(analytics_funnel.json)" in log,
           "count corrected on ANY diff, pinned log format")
        ok(not any("atc_rate" in ln for ln in log)
           and merged["analytics"]["funnel"]["atc_rate"] == 12.1,
           "rate diff 0.02 <= RATE_TOL: replaced silently, not corrected")
        ok("machine: analytics.funnel.cvr 2.30->2.00 "
           "(analytics_funnel.json)" in log,
           "rate diff > 0.05 corrected (2dp log formatting)")
        ok("machine: analytics.device.entities 3 rows->3 rows "
           "(analytics_device.json)" not in log
           and any(ln.startswith("machine: analytics.device[mobile].cvr "
                                 "1.90->1.43") for ln in log),
           "device rows matched case-insensitively, per-cell corrections")
        ok(not any("desktop].cvr" in ln for ln in log),
           "desktop 3.85 vs 3.82 within tolerance")
        ok("analytics.landing_pages" in block["filled"]
           and "analytics.channels" in block["filled"],
           "absent payload blocks land in filled")
        ok(not any(c["field"].startswith("analytics.new_vs_returning")
                   for c in block["corrected"])
           and merged["analytics"]["new_vs_returning"] ==
           {"new_cvr": 1.70, "returning_cvr": 6.40},
           "machine-skipped block stays transcribed (never dropped)")
        ok(any(s["field"] == "analytics.new_vs_returning"
               for s in block["skipped"]),
           "skipped list rides into machine_block")
        # 6b. single-source drop: a transcribed stage the machine source
        #     lacks is dropped from the replaced block (never mixed).
        merged_b, block_b, log_b = merge_into_payload(payload, mach3)
        ok(merged_b["analytics"]["funnel"] ==
           {"sessions": 900, "purchases": 18, "cvr": 2.0},
           "whole-block funnel replace (no stage mixing)")
        drops = [c for c in block_b["corrected"]
                 if c["to"] is None and c["field"].startswith(
                     "analytics.funnel.")]
        ok({c["field"] for c in drops} ==
           {"analytics.funnel.atc", "analytics.funnel.checkout",
            "analytics.funnel.atc_rate", "analytics.funnel.checkout_rate"},
           "transcribed stages absent from the single source are dropped")
        ok(any(ln == "machine: analytics.funnel.atc 121->dropped "
                     "(single-source: not in ga4-funnel.csv)"
               for ln in log_b), "drop log line names the single source")
        ok("machine: analytics.aov 84.90->250.47 (analytics_totals.json)"
           in log and merged["analytics"]["aov"] == 250.47,
           "aov corrected + stored verbatim (log shows 2dp)")
        ok(merged["meta"]["currency"] == "CAD"
           and "meta.currency" in block["filled"],
           "meta.currency fill-if-blank")
        ok(merged["steps_detail"] == payload["steps_detail"]
           and merged["findings"] == payload["findings"]
           and merged["meta"]["store_name"] == "T",
           "steps_detail / findings / other meta untouched")
        ok(block["reads"] == mach["reads"]
           and block["sources"] == mach["sources"],
           "reads + sources ride into machine_block")
        ok(sorted(block["applied"]) == block["applied"]
           and "analytics.funnel.cvr" in block["applied"],
           "applied sorted, field-level for scalar blocks")

        # 7. currency present -> untouched + honest note; machine=None no-op.
        payload2 = {"meta": {"currency": "USD"}, "analytics": {}}
        merged2, block2, _ = merge_into_payload(payload2, mach)
        ok(merged2["meta"]["currency"] == "USD"
           and any("meta.currency left as transcribed (USD)" in n
                   for n in block2["notes"]),
           "non-blank currency never overwritten (note instead)")
        p, b, lg = merge_into_payload(payload2, None)
        ok(p is payload2 and b is None and lg == [],
           "machine=None -> payload passthrough")

        # 8. no inputs at all -> None.
        ok(compute_machine(None) is None and compute_machine({}) is None,
           "no inputs -> None")

    print(f"machine self-test OK ({checks[0]} checks)")


if __name__ == "__main__":
    import argparse
    import json
    import sys

    ap = argparse.ArgumentParser(
        description="Deterministic CRO analytics assembler (machine layer). "
                    "No flags -> self-test.")
    ap.add_argument("--raw-dir", help="folder of saved Shopify MCP results "
                                      "(shop_info.json, analytics_*.json)")
    ap.add_argument("--csv-dir", help="folder of GA4/Shopify UI CSV exports "
                                      "(manual_csv filenames)")
    ap.add_argument("--payload", help="payload JSON to merge into (prints "
                                      "the machine_block + log)")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test or not (args.raw_dir or args.csv_dir):
        _self_test()
        sys.exit(0)

    inputs: dict = {}
    if args.raw_dir:
        d = Path(args.raw_dir)
        raw = {}
        for key in _RAW_ORDER:
            p = d / f"{key}.json"
            if p.is_file():
                raw[key] = str(p)
        inputs["raw"] = raw
    if args.csv_dir:
        import manual_csv
        inputs["csv"] = manual_csv.load_csv_dir(args.csv_dir)

    machine = compute_machine(inputs)
    if machine is None:
        print(json.dumps({"machine": None}))
        sys.exit(0)
    out: dict = {"machine": {k: v for k, v in machine.items()
                             if k != "universes"},
                 "universe_sizes": {k: (len(v) if isinstance(v, list) else 1)
                                    for k, v in sorted(
                                        machine["universes"].items())}}
    if args.payload:
        payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
        _merged, blockb, log = merge_into_payload(payload, machine)
        out["machine_block"] = blockb
        out["log"] = log
        for line in log:
            print(line, file=sys.stderr)
    print(json.dumps(out, indent=2, sort_keys=True))
