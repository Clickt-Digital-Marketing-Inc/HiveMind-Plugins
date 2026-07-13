#!/usr/bin/env python3
# Copyright (c) 2026 Clickt Digital Marketing Inc. All rights reserved.
"""Parse GA4 + Shopify Analytics **UI CSV exports** for the manual audit path.

NEEDS-REAL-EXPORT-VALIDATION: every parser and adapter in this module is
encoded from the DOCUMENTED export formats (references/data-intake.md) — no
real GA4 or Shopify Analytics export file has been run through it yet.
Column spellings, the GA4 preamble/second-section layout, Shopify totals-row
labels, and the percent-vs-decimal formatting of rate cells must all be
confirmed against genuine exports before this path is trusted for client
work; until then any mismatch surfaces loudly through the REQUIRED_COLUMNS
wrong-report guard or the site-CVR mis-scale guard. English exports assumed.

What this module assumes (defensively coded):

GA4 CSV exports ("Share -> Download file -> CSV" / Exploration "Export"):
- a leading preamble of ``#``-comment lines (may include the date range as
  ``# YYYYMMDD-YYYYMMDD`` — parsed into meta["window"]);
- header = the first non-comment, non-empty row;
- data rows follow immediately; the file then appends a SECOND, day-by-day
  section after a blank line — parsing STOPS at the first blank line (or a
  new ``#`` comment) once data has begun;
- a row whose dimension cell is blank or reads ``Grand total`` / ``Totals``
  / ``Total`` is the universe total: captured into meta["totals"], excluded
  from the entity rows;
- rate columns (``Session key event rate``, ``Session conversion rate``, …)
  default to the FRACTION scale (0.0454 = 4.54%) unless the cell carries a
  literal ``%`` (then value/100).

Shopify Analytics CSV exports (Analytics -> Reports -> Export -> CSV):
- plain header on row 1 (defensive first-non-empty-row scan retained);
- the same totals-row guard (blank/``Grand total``/``Totals``/``Total``
  name cell -> meta["totals"], excluded from entities);
- rate cells may be ``2.00%`` (percent, /100) or ``0.02`` (fraction);
  a bare number > 1 is defensively treated as percent-scale (/100);
- ``average_order_value`` is AUTHORITATIVE VERBATIM (SHAPE-NOTES trap):
  AOV is NEVER recomputed from revenue/orders, and a multi-row AOV export
  without a totals row yields aov=None plus an honest note — daily AOVs are
  never averaged.

Unit rules (binding — CONTRACTS.md §5 / plan §5):
- ALL rate values leave this module as FRACTIONS (0-1). ``%`` in a cell ->
  value/100; GA4 ``*rate*`` columns default fraction; Shopify bare rates
  <= 1 are fractions, > 1 are percent (/100).
- Mis-scaled-units guard: if the implied SITE conversion-rate fraction of a
  funnel source exceeds ``SITE_CVR_MAX`` (0.20), ManualCsvError is raised —
  a 20%+ sitewide CVR means percent leaked through as fraction.
- Derived counts use half-up rounding: floor(x + 0.5) (never banker's).

Adapter return convention (all 11 adapters; documented for build_cro_audit.py):

    ga4_landing_rows(path)          -> (rows, meta)     # ga4-landing.csv
    ga4_funnel(path)                -> (funnel, meta)   # ga4-funnel.csv
    ga4_device_rows(path)           -> (rows, meta)     # ga4-device.csv
    ga4_channel_rows(path)          -> (rows, meta)     # ga4-channels.csv
    ga4_new_returning_rows(path)    -> (rows, meta)     # ga4-new-returning.csv
    shopify_conversion_funnel(path) -> (funnel, meta)   # shopify-conversion.csv
    shopify_product_rows(path)      -> (rows, meta)     # shopify-sales-product.csv
    shopify_traffic_source_rows(path) -> (rows, meta)   # shopify-traffic-source.csv
    shopify_landing_rows(path)      -> (rows, meta)     # shopify-landing.csv
    shopify_customer_rows(path)     -> (rows, meta)     # shopify-customers.csv
    shopify_aov(path)               -> (totals, meta)   # shopify-aov.csv

    rows — list[dict] in the SAME fraction-unit shapes the shopify_rows
    adapters emit (CONTRACTS.md §2/§3/§4; shopify_rows.py is the shape
    authority — its docstring pins these):
      segment rows: {"name", "sessions", "cvr"?, "revenue"?, ...}
        ("conversions" is deliberately NOT populated from GA4 "Key events"
        or Shopify "Orders" — neither is the sessions-converted numerator;
        cvr_signals derives + flags instead. The counts ride along as
        auxiliary "key_events" / "orders" keys for evidence tables.)
      landing/page rows: same, with names URL-normalized BEFORE any math
        (lowercase, strip ?query, strip trailing "/" except the bare root —
        mirrors shopify_rows.normalize_url) and duplicates merged: sessions
        sum, cvr recomputed as the sessions-weighted mean, auxiliary counts
        summed.
      product rows: {"product", "revenue", "orders"?, "units"?}
      customer rows: {"name" ('new'/'returning'), "orders"?, "customers"?,
        "revenue"?, "cvr"?} — order-share evidence only (plan: GA4 is the
        only session-basis new-vs-returning source). When both customer
        counts are present, meta["customers_summary"] mirrors
        shopify_rows.customers_from_table: {"customers",
        "returning_customers", "returning_customer_rate" (fraction)}.
    funnel — dict mirroring shopify_rows.funnel_from_table exactly:
      {"sessions": int, "atc_sessions": int?, "checkout_sessions": int?,
       "purchase_sessions": int?, "atc_rate": frac?, "checkout_rate": frac?,
       "cvr": frac?} — stage keys absent when the stage is absent
      (measured-stages-only scoring downstream); "derived" lists any
      half-up-derived keys.
    totals (shopify_aov) — {"aov": float} VERBATIM (mirrors
      shopify_rows.totals_from_table's aov key), or {} when not derivable
      (see meta["aov"] / notes).
    meta — {"window": "YYYY-MM-DD – YYYY-MM-DD" | "", "stamp":
      {"file","sha256","bytes"}, "file": basename, "n_rows_raw": int,
      "totals": dict|None (universe totals row, same keys as rows),
      "notes": [str, ...] (fixed order)} + "basis" on the funnel adapters
      ('users' for ga4-funnel — GA4 funnel explorations count USERS, not
      sessions; 'sessions' for shopify-conversion).

Files are parsed verbatim — numbers never pass through the model
(transcription firewall). Rows are returned sorted sessions-desc (products:
revenue-desc) then name-asc. Stdlib only. Deterministic: no wall clock, no
locale-dependent parsing, sorted iteration, fixed note order.
"""
from __future__ import annotations

import csv
import hashlib
import math
import re
from pathlib import Path


class ManualCsvError(ValueError):
    """An export file is missing, malformed, mis-scaled, or the wrong report."""


# Mis-scaled-units guard: sitewide CVR fraction above this aborts (a 20%+
# site conversion rate means a percent value leaked through as a fraction).
SITE_CVR_MAX = 0.20

# Cell values that mean "absent" (key omitted).
_ABSENT = {"", "-", "--", "—", "–"}  # em dash / en dash

# Totals-row labels (lowercased) — blank name cells count as totals too.
_TOTALS_LABELS = {"grand total", "totals", "total"}

# ── --csv-dir filenames + wrong-report guard (prefix-matched candidates) ────
# Each REQUIRED_COLUMNS entry is a list of candidate-tuples: at least one
# candidate per tuple must resolve via _col (exact or "prefix (…)" match).
REQUIRED_COLUMNS = {
    "ga4-landing.csv": [("Landing page + query string", "Landing page"),
                        ("Sessions",)],
    "ga4-funnel.csv": [("Step",), ("Active users", "Users")],
    "ga4-device.csv": [("Device category",), ("Sessions",)],
    "ga4-channels.csv": [("Session default channel group",
                          "Default channel group"), ("Sessions",)],
    "ga4-new-returning.csv": [("New / established", "New/established",
                               "New / returning", "New/returning",
                               "New vs returning"),
                              ("Sessions", "Active users")],
    "shopify-conversion.csv": [("Sessions",)],  # + funnel-column guard below
    "shopify-sales-product.csv": [("Product title", "Product"),
                                  ("Net sales", "Total sales", "Gross sales")],
    "shopify-traffic-source.csv": [("Referrer source", "Traffic source",
                                    "Referrer name", "Referrer"),
                                   ("Sessions",)],
    "shopify-landing.csv": [("Landing page path", "Landing page",
                             "Landing page URL"), ("Sessions",)],
    "shopify-customers.csv": [("Customer type", "New or returning customer",
                               "New or returning", "Customer")],
    # + at-least-one-numeric-column guard below
    "shopify-aov.csv": [("Average order value",)],
}

# Dimension/name column candidates per file (None-tolerant for the time
# dimension of over-time exports: shopify-conversion.csv / shopify-aov.csv).
_NAME_COLUMN = {
    "ga4-landing.csv": ("Landing page + query string", "Landing page"),
    "ga4-funnel.csv": ("Step",),
    "ga4-device.csv": ("Device category",),
    "ga4-channels.csv": ("Session default channel group",
                         "Default channel group"),
    "ga4-new-returning.csv": ("New / established", "New/established",
                              "New / returning", "New/returning",
                              "New vs returning"),
    "shopify-conversion.csv": ("Day", "Date", "Week", "Month", "Hour"),
    "shopify-sales-product.csv": ("Product title", "Product"),
    "shopify-traffic-source.csv": ("Referrer source", "Traffic source",
                                   "Referrer name", "Referrer"),
    "shopify-landing.csv": ("Landing page path", "Landing page",
                            "Landing page URL"),
    "shopify-customers.csv": ("Customer type", "New or returning customer",
                              "New or returning", "Customer"),
    "shopify-aov.csv": ("Day", "Date", "Week", "Month"),
}

# Rate-column candidates. NEEDS-REAL-EXPORT-VALIDATION: GA4 names the column
# per configured key event; the contains-fallback scans header order (first
# hit wins — deterministic) for the documented substrings only, so
# "Abandonment rate" never matches.
_GA4_RATE_CANDS = ("Session key event rate", "Session conversion rate",
                   "Conversion rate")
_GA4_RATE_CONTAINS = ("session key event rate", "session conversion rate",
                      "key event rate", "conversion rate")
_SHOPIFY_RATE_CANDS = ("Conversion rate",)
_SHOPIFY_RATE_CONTAINS = ("conversion rate",)

# shopify-conversion.csv funnel-stage count-column candidates (a matched
# header containing '%' or 'rate' is rejected as a count — it is the rate).
_CONV_SESSIONS = ("Sessions",)
_CONV_CART = ("Sessions with cart additions", "Sessions that added to cart",
              "Added to cart sessions", "Added to cart", "Add to carts",
              "Cart additions")
_CONV_CHECKOUT = ("Sessions that reached checkout", "Reached checkout sessions",
                  "Reached checkout", "Checkout sessions", "Began checkout")
_CONV_PURCHASE = ("Sessions that completed checkout", "Completed checkout",
                  "Sessions converted", "Converted sessions", "Purchases")

# Extraction specs: (key, kind, candidates); kind in {"count","money","rate"}.
_GA4_SEGMENT_SPEC = [
    ("sessions", "count", ("Sessions", "Active users")),
    ("cvr", "rate", _GA4_RATE_CANDS),
    ("key_events", "count", ("Key events", "Conversions")),
    ("revenue", "money", ("Total revenue", "Purchase revenue", "Revenue")),
]
_SHOPIFY_SEGMENT_SPEC = [
    ("sessions", "count", ("Sessions",)),
    ("cvr", "rate", _SHOPIFY_RATE_CANDS),
    ("orders", "count", ("Orders",)),
    ("revenue", "money", ("Total sales", "Net sales", "Sales")),
]
_PRODUCT_SPEC = [
    ("revenue", "money", ("Net sales", "Total sales", "Gross sales")),
    ("orders", "count", ("Orders",)),
    ("units", "count", ("Net quantity", "Units ordered", "Units", "Quantity",
                        "Net items sold", "Items sold")),
]
_CUSTOMER_SPEC = [
    ("customers", "count", ("Customers",)),
    ("orders", "count", ("Orders",)),
    ("revenue", "money", ("Total sales", "Net sales", "Sales")),
    ("cvr", "rate", _SHOPIFY_RATE_CANDS),
]
_AOV_SPEC = [
    ("average_order_value", "money", ("Average order value",)),
]


# ── cell/column helpers (ported from the meta-ads-audit manual_csv) ─────────

def _col(header: list[str], prefix: str) -> str | None:
    """First header matching ``prefix`` exactly or as ``prefix (…)``.

    ``_col(h, "Net sales")`` matches ``Net sales (CAD)`` but never
    ``Net sales per order``; exact matches win column-order ties."""
    for h in header:
        if h == prefix or h.startswith(prefix + " ("):
            return h
    return None


def _col_any(header: list[str], prefixes) -> str | None:
    """First candidate prefix (in candidate order) that resolves via _col."""
    for p in prefixes:
        c = _col(header, p)
        if c is not None:
            return c
    return None


def _col_count(header: list[str], prefixes) -> str | None:
    """_col_any restricted to COUNT columns: a matched header containing
    '%' or the word 'rate' is rejected (it is the rate, not the count)."""
    c = _col_any(header, prefixes)
    if c is not None and ("%" in c or "rate" in c.lower()):
        return None
    return c


def _find_rate_col(header: list[str], candidates, contains) -> str | None:
    """Rate column: exact/prefix candidates first, then a header-order scan
    for the documented rate substrings (deterministic first hit)."""
    c = _col_any(header, candidates)
    if c is not None:
        return c
    for h in header:
        low = h.lower()
        if any(tok in low for tok in contains):
            return h
    return None


def _is_absent(v) -> bool:
    return v is None or str(v).strip() in _ABSENT


def _num(v) -> float | None:
    """Plain UI number -> float, or None when absent/unparseable.

    Handles thousands commas ('21,915'), a trailing/leading '%' strip (value
    returned on whatever scale the digits carry — _rate decides /100), NBSP,
    and a defensive currency prefix ('CA$1,023.31', '-$12.50')."""
    if _is_absent(v):
        return None
    s = str(v).strip().replace("\u00a0", " ").replace(",", "")
    s = s.replace("%", "").strip()
    s = re.sub(r"^(-?)[A-Za-z]{0,3}\$", r"\1", s)
    try:
        return float(s)
    except ValueError:
        return None


def _half_up(x: float) -> int:
    """Half-up integer rounding — floor(x + 0.5), never banker's."""
    return int(math.floor(x + 0.5))


def _rate(cell, *, ga4: bool) -> float | None:
    """Rate cell -> FRACTION (0-1) or None.

    '%' in the cell -> value/100. GA4 bare rates default FRACTION (plan
    pin). Shopify bare rates <= 1 are fractions; > 1 defensively percent."""
    if _is_absent(cell):
        return None
    s = str(cell).strip()
    v = _num(s)
    if v is None:
        return None
    if "%" in s:
        return v / 100.0
    if ga4:
        return v
    return v if v <= 1.0 else v / 100.0


def _count(cell) -> int | None:
    v = _num(cell)
    return _half_up(v) if v is not None else None


def _file_stamp(path: str) -> dict:
    """Provenance stamp — same shape as shopify_rows.file_stamp / meta's."""
    p = Path(path)
    return {"file": p.name,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "bytes": p.stat().st_size}


def _guard_site_cvr(cvr: float | None, path: str, source: str) -> None:
    if cvr is not None and cvr > SITE_CVR_MAX:
        raise ManualCsvError(
            f"{path}: implied site conversion-rate fraction {cvr:.4f} exceeds "
            f"{SITE_CVR_MAX:.2f} ({source}) — rate cells look mis-scaled "
            "(percent read as fraction?). Check the export's rate column "
            "formatting against references/data-intake.md.")


def _require(header: list[str], key: str, path: str) -> None:
    """Wrong-report guard: every REQUIRED_COLUMNS candidate-tuple must match."""
    missing = [cands[0] for cands in REQUIRED_COLUMNS[key]
               if _col_any(header, cands) is None]
    if missing:
        raise ManualCsvError(
            f"{path}: missing column(s) {', '.join(missing)} — is this the "
            f"right export for {key}? See references/data-intake.md.")


def _read_rows(path: str) -> list[list[str]]:
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8-sig")  # exports may carry a BOM
    except FileNotFoundError as e:
        raise ManualCsvError(f"export file not found: {path}") from e
    raw = list(csv.reader(text.splitlines(keepends=True)))
    if not raw:
        raise ManualCsvError(f"{path}: file is empty")
    return raw


def _is_blank(r: list[str]) -> bool:
    return not r or not any(c.strip() for c in r)


def _is_comment(r: list[str]) -> bool:
    return bool(r) and r[0].lstrip().startswith("#")


def _split_rows(raw: list[list[str]], header: list[str], header_idx: int,
                name_col: str | None) -> tuple[list[dict], dict | None, list[str]]:
    """Data rows after the header -> (entity rows, totals row, notes).

    Stops at the first blank line (or a fresh '#' comment) once data has
    begun — GA4 appends a day-by-day second section there. A row whose name
    cell is blank or a totals label is captured as the universe total and
    excluded from the entities."""
    rows: list[dict] = []
    totals: dict | None = None
    extra_totals = 0
    for r in raw[header_idx + 1:]:
        if _is_blank(r) or _is_comment(r):
            break  # second (day-by-day) section boundary / trailing comments
        row = {header[i]: (r[i] if i < len(r) else "")
               for i in range(len(header))}
        if name_col is not None:
            name = str(row.get(name_col) or "").strip()
            if not name or name.lower() in _TOTALS_LABELS:
                if totals is None:
                    totals = row
                else:
                    extra_totals += 1
                continue
        rows.append(row)
    notes = []
    if extra_totals:
        notes.append(f"{extra_totals} extra totals-like row(s) ignored "
                     "(first totals row kept)")
    return rows, totals, notes


def load_ga4_csv(path: str, key: str) -> dict:
    """Read a GA4 CSV export -> {header, rows, totals, window, stamp, notes}.

    NEEDS-REAL-EXPORT-VALIDATION. Skips the '#'-comment preamble (parsing
    the '# YYYYMMDD-YYYYMMDD' date range into window when present); header =
    first non-comment non-empty row; stops at the first blank line after
    data begins (GA4's appended day-by-day second section); the Grand-total
    / blank-dimension row is captured as totals and excluded from rows."""
    if key not in REQUIRED_COLUMNS:
        raise ManualCsvError(f"unknown csv key {key!r} (expected one of "
                             f"{', '.join(sorted(REQUIRED_COLUMNS))})")
    raw = _read_rows(path)

    window = ""
    header_idx = None
    for i, r in enumerate(raw):
        if _is_comment(r):
            m = re.search(r"(\d{8})-(\d{8})", ",".join(r))
            if m and not window:
                a, b = m.group(1), m.group(2)
                window = (f"{a[:4]}-{a[4:6]}-{a[6:]} – "
                          f"{b[:4]}-{b[4:6]}-{b[6:]}")
            continue
        if _is_blank(r):
            continue
        header_idx = i
        break
    if header_idx is None:
        raise ManualCsvError(f"{path}: no header row found — is this a GA4 "
                             "CSV export (Share -> Download file -> CSV)?")
    header = [h.strip() for h in raw[header_idx]]
    _require(header, key, path)
    name_col = _col_any(header, _NAME_COLUMN.get(key, ()))
    rows, totals, notes = _split_rows(raw, header, header_idx, name_col)
    return {"header": header, "rows": rows, "totals": totals,
            "window": window, "stamp": _file_stamp(path), "notes": notes}


def load_shopify_csv(path: str, key: str) -> dict:
    """Read a Shopify Analytics CSV export -> same dict as load_ga4_csv.

    NEEDS-REAL-EXPORT-VALIDATION. Plain header on row 1 (defensive
    first-non-empty-row scan); the same totals-row guard as GA4; window =
    min–max of ISO dates in the Day/Date column when one exists."""
    if key not in REQUIRED_COLUMNS:
        raise ManualCsvError(f"unknown csv key {key!r} (expected one of "
                             f"{', '.join(sorted(REQUIRED_COLUMNS))})")
    raw = _read_rows(path)
    header_idx = next((i for i, r in enumerate(raw) if not _is_blank(r)), None)
    if header_idx is None:
        raise ManualCsvError(f"{path}: no header row found — is this a "
                             "Shopify Analytics CSV export?")
    header = [h.strip() for h in raw[header_idx]]
    _require(header, key, path)
    name_col = _col_any(header, _NAME_COLUMN.get(key, ()))
    rows, totals, notes = _split_rows(raw, header, header_idx, name_col)

    window = ""
    date_col = _col_any(header, ("Day", "Date"))
    if date_col is not None:
        days = sorted(str(r.get(date_col) or "").strip() for r in rows
                      if re.match(r"^\d{4}-\d{2}-\d{2}$",
                                  str(r.get(date_col) or "").strip()))
        if days:
            window = f"{days[0]} – {days[-1]}"
    return {"header": header, "rows": rows, "totals": totals,
            "window": window, "stamp": _file_stamp(path), "notes": notes}


# ── extraction ──────────────────────────────────────────────────────────────

def _extract(row: dict, header: list[str], spec, *, ga4: bool) -> dict:
    """One raw {header: cell} row -> typed dict per spec (absent = omitted)."""
    d: dict = {}
    for key, kind, cands in spec:
        if kind == "rate":
            col = _find_rate_col(header, cands,
                                 _GA4_RATE_CONTAINS if ga4
                                 else _SHOPIFY_RATE_CONTAINS)
        elif kind == "count":
            col = _col_count(header, cands)
        else:
            col = _col_any(header, cands)
        if col is None:
            continue
        if kind == "rate":
            v = _rate(row.get(col), ga4=ga4)
        elif kind == "count":
            v = _count(row.get(col))
        else:
            v = _num(row.get(col))
        if v is not None:
            d[key] = v
    return d


def _meta(loaded: dict, rows_kept: int, notes: list[str],
          totals: dict | None, **extra) -> dict:
    m = {"window": loaded["window"], "stamp": loaded["stamp"],
         "file": loaded["stamp"]["file"], "n_rows_raw": rows_kept,
         "totals": totals, "notes": list(loaded["notes"]) + notes}
    m.update(extra)
    return m


def _segment_rows(path: str, key: str, *, ga4: bool, spec,
                  name_key: str = "name", canon=None,
                  sort_by: str = "sessions",
                  loaded: dict | None = None) -> tuple[list[dict], dict]:
    if loaded is None:
        loaded = (load_ga4_csv if ga4 else load_shopify_csv)(path, key)
    header = loaded["header"]
    name_col = _col_any(header, _NAME_COLUMN[key])
    notes: list[str] = []
    rows = []
    for row in loaded["rows"]:
        d = {name_key: str(row.get(name_col) or "").strip()}
        if canon is not None:
            d[name_key] = canon(d[name_key])
        d.update(_extract(row, header, spec, ga4=ga4))
        rows.append(d)
    rows.sort(key=lambda r: (-(r.get(sort_by) or 0), r[name_key]))
    totals = (_extract(loaded["totals"], header, spec, ga4=ga4)
              if loaded["totals"] is not None else None)
    return rows, _meta(loaded, len(rows), notes, totals)


# ── funnel helpers ──────────────────────────────────────────────────────────

_GA4_STEP_SLOTS = (  # checked in order — 'purchase' before 'checkout' etc.
    ("purchase", "purchase_sessions"),
    ("checkout", "checkout_sessions"),
    ("cart", "atc_sessions"),
    ("session", "sessions"),
    ("start", "sessions"),
    ("visit", "sessions"),
)


def _normalize_url(u) -> str:
    """Landing-path normalization — mirrors shopify_rows.normalize_url
    byte-for-byte (pinned: applied BEFORE any math): lowercase, strip the
    ?query, strip trailing slashes except the bare root "/"."""
    s = str(u if u is not None else "").strip().lower()
    q = s.find("?")
    if q != -1:
        s = s[:q]
    while len(s) > 1 and s.endswith("/"):
        s = s[:-1]
    return s or "/"


def _merge_landing(rows: list[dict]) -> list[dict]:
    """URL-normalize names and merge duplicates: sessions sum, cvr
    sessions-weighted mean (over merged rows that carried a cvr — mirrors
    shopify_rows.landing_rows_from_table), auxiliary counts/money summed."""
    agg: dict[str, dict] = {}
    for r in rows:
        name = _normalize_url(r.get("name"))
        a = agg.setdefault(name, {"sessions": 0, "_wsum": 0.0, "_scvr": 0})
        sess = int(r.get("sessions") or 0)
        a["sessions"] += sess
        cvr = r.get("cvr")
        if cvr is not None:
            a["_wsum"] += sess * float(cvr)
            a["_scvr"] += sess
        for k in ("key_events", "orders"):
            if r.get(k) is not None:
                a[k] = a.get(k, 0) + r[k]
        if r.get("revenue") is not None:
            a["revenue"] = a.get("revenue", 0.0) + r["revenue"]
    out = []
    for name in sorted(agg):
        a = agg[name]
        rec = {"name": name, "sessions": a["sessions"]}
        if a["_scvr"] > 0:
            rec["cvr"] = a["_wsum"] / a["_scvr"]
        for k in ("key_events", "orders", "revenue"):
            if k in a:
                rec[k] = a[k]
        out.append(rec)
    out.sort(key=lambda r: (-r["sessions"], r["name"]))
    return out


def _ga4_step_slot(step_name: str) -> str | None:
    low = re.sub(r"^\s*\d+\.\s*", "", step_name).strip().lower()
    for token, slot in _GA4_STEP_SLOTS:
        if token in low:
            return slot
    return None


# ── the 11 adapters (NEEDS-REAL-EXPORT-VALIDATION, each and every one) ──────

def ga4_landing_rows(path: str) -> tuple[list[dict], dict]:
    """ga4-landing.csv (GA4 Landing page report) -> (rows, meta).

    NEEDS-REAL-EXPORT-VALIDATION. Rows {name, sessions, cvr?, key_events?,
    revenue?}; names URL-normalized BEFORE any math and duplicates merged
    (mirrors shopify_rows.landing_rows_from_table — GA4's 'Landing page +
    query string' dimension splits one page across query variants)."""
    rows, meta = _segment_rows(path, "ga4-landing.csv", ga4=True,
                               spec=_GA4_SEGMENT_SPEC)
    merged = _merge_landing(rows)
    if len(merged) != len(rows):
        meta["notes"].append(f"{len(rows)} rows merged into {len(merged)} "
                             "after URL normalization")
    return merged, meta


def ga4_device_rows(path: str) -> tuple[list[dict], dict]:
    """ga4-device.csv (GA4 Device category) -> (rows, meta).

    NEEDS-REAL-EXPORT-VALIDATION. Rows {name, sessions, cvr?, ...}."""
    return _segment_rows(path, "ga4-device.csv", ga4=True,
                         spec=_GA4_SEGMENT_SPEC)


def ga4_channel_rows(path: str) -> tuple[list[dict], dict]:
    """ga4-channels.csv (GA4 Traffic acquisition by Session default channel
    group) -> (rows, meta).

    NEEDS-REAL-EXPORT-VALIDATION. Rows {name, sessions, cvr?, revenue?}."""
    return _segment_rows(path, "ga4-channels.csv", ga4=True,
                         spec=_GA4_SEGMENT_SPEC)


def _canon_nvr(name: str) -> str:
    low = name.lower()
    if "not set" in low:
        return name
    if "new" in low:
        return "new"
    if "return" in low or "establish" in low:
        return "returning"
    return name


def ga4_new_returning_rows(path: str) -> tuple[list[dict], dict]:
    """ga4-new-returning.csv (GA4 New / established exploration) ->
    (rows, meta).

    NEEDS-REAL-EXPORT-VALIDATION. Names canonicalized to 'new'/'returning';
    when only 'Active users' is exported it stands in for sessions (users
    basis — noted). GA4 is the ONLY session-basis new-vs-returning source
    (SHAPE-NOTES: the Shopify MCP rate is order-share evidence only)."""
    loaded = load_ga4_csv(path, "ga4-new-returning.csv")
    rows, meta = _segment_rows(path, "ga4-new-returning.csv", ga4=True,
                               spec=_GA4_SEGMENT_SPEC, canon=_canon_nvr,
                               loaded=loaded)
    header = loaded["header"]
    if _col(header, "Sessions") is None and \
            _col_any(header, ("Active users", "Users")) is not None:
        meta["notes"].append(
            f"{meta['file']}: 'Active users' used as sessions (users basis)")
    return rows, meta


def ga4_funnel(path: str) -> tuple[dict, dict]:
    """ga4-funnel.csv (GA4 Funnel exploration: session_start -> add_to_cart
    -> begin_checkout -> purchase) -> (funnel, meta) — meta["basis"]='users'.

    NEEDS-REAL-EXPORT-VALIDATION. GA4 funnel explorations count USERS, not
    sessions — the FALLBACK funnel source only (shopify-conversion.csv is
    primary; single-source rule: stages are never mixed across sources).
    Funnel keys mirror shopify_rows.funnel_from_table (sessions /
    atc_sessions / checkout_sessions / purchase_sessions + atc_rate /
    checkout_rate / cvr fractions); cvr = purchases/sessions, guarded
    > 0.20."""
    loaded = load_ga4_csv(path, "ga4-funnel.csv")
    header = loaded["header"]
    step_col = _col_any(header, _NAME_COLUMN["ga4-funnel.csv"])
    users_col = _col_count(header, ("Active users", "Users"))
    if users_col is None:
        raise ManualCsvError(f"{path}: no usable 'Active users' count column "
                             "— is this the GA4 funnel exploration export?")
    notes: list[str] = []
    funnel: dict = {}
    for row in loaded["rows"]:
        step = str(row.get(step_col) or "").strip()
        slot = _ga4_step_slot(step)
        if slot is None:
            notes.append(f"unrecognized funnel step '{step}' ignored")
            continue
        if slot in funnel:
            notes.append(f"duplicate funnel step '{step}' ignored "
                         "(first occurrence kept)")
            continue
        v = _count(row.get(users_col))
        if v is not None:
            funnel[slot] = v
    if funnel.get("sessions"):
        if "atc_sessions" in funnel:
            funnel["atc_rate"] = funnel["atc_sessions"] / funnel["sessions"]
        if "checkout_sessions" in funnel:
            funnel["checkout_rate"] = (funnel["checkout_sessions"]
                                       / funnel["sessions"])
        if "purchase_sessions" in funnel:
            cvr = funnel["purchase_sessions"] / funnel["sessions"]
            _guard_site_cvr(cvr, path, "purchase users / session_start users")
            funnel["cvr"] = cvr
            notes.append("cvr computed from purchase/session_start "
                         "user counts")
    notes.append("GA4 funnel counts USERS, not sessions — users basis")
    return funnel, _meta(loaded, len(loaded["rows"]), notes, None,
                         basis="users")


def shopify_conversion_funnel(path: str) -> tuple[dict, dict]:
    """shopify-conversion.csv (Shopify Conversion over time / funnel summary)
    -> (funnel, meta) — the PRIMARY funnel source; meta["basis"]='sessions'.

    NEEDS-REAL-EXPORT-VALIDATION. Funnel keys mirror
    shopify_rows.funnel_from_table exactly (sessions / atc_sessions /
    checkout_sessions / purchase_sessions + atc_rate / checkout_rate / cvr
    fractions). A totals row is used verbatim when present; otherwise stage
    counts are summed across the period rows and cvr is session-weighted
    from the rate column (the derived purchase count flagged) or recomputed
    from counts. Site CVR fraction > 0.20 aborts (mis-scaled units
    guard)."""
    loaded = load_shopify_csv(path, "shopify-conversion.csv")
    header = loaded["header"]
    stage_cols = {
        "sessions": _col_count(header, _CONV_SESSIONS),
        "atc_sessions": _col_count(header, _CONV_CART),
        "checkout_sessions": _col_count(header, _CONV_CHECKOUT),
        "purchase_sessions": _col_count(header, _CONV_PURCHASE),
    }
    rate_col = _find_rate_col(header, _SHOPIFY_RATE_CANDS,
                              _SHOPIFY_RATE_CONTAINS)
    if rate_col is None:  # "Sessions converted (%)"-style header
        rate_col = next((h for h in header
                         if "%" in h and "convert" in h.lower()), None)
    if rate_col is None and all(
            stage_cols[k] is None for k in stage_cols if k != "sessions"):
        raise ManualCsvError(
            f"{path}: found Sessions but no funnel columns (cart additions / "
            "reached checkout / completed checkout / conversion rate) — is "
            "this the Shopify conversion export? See references/data-intake.md.")

    notes: list[str] = []
    funnel: dict = {}
    derived: list[str] = []
    src_rows = loaded["rows"]
    if loaded["totals"] is not None:
        t = loaded["totals"]
        for slot, col in sorted(stage_cols.items()):
            if col is None:
                continue
            v = _count(t.get(col))
            if v is not None:
                funnel[slot] = v
        rate = _rate(t.get(rate_col), ga4=False) if rate_col else None
        notes.append("universe totals row used verbatim "
                     f"({len(src_rows)} period row(s) not aggregated)")
    else:
        for slot, col in sorted(stage_cols.items()):
            if col is None:
                continue
            vals = [_num(r.get(col)) for r in src_rows]
            vals = [v for v in vals if v is not None]
            if vals:
                funnel[slot] = _half_up(sum(vals))
        rate = None
        if rate_col and funnel.get("sessions"):
            wsum, sess = 0.0, 0.0
            for r in src_rows:
                rv = _rate(r.get(rate_col), ga4=False)
                sv = _num(r.get(stage_cols["sessions"]))
                if rv is not None and sv:
                    wsum += rv * sv
                    sess += sv
            if sess > 0:
                rate = wsum / sess
                if "purchase_sessions" not in funnel:
                    funnel["purchase_sessions"] = _half_up(wsum)
                    derived.append("purchase_sessions")
                    notes.append("purchase sessions derived half-up from "
                                 "session-weighted rate")
                notes.append("conversion rate session-weighted across "
                             f"{len(src_rows)} period row(s)")

    if rate is None and funnel.get("sessions") and \
            "purchase_sessions" in funnel:
        rate = funnel["purchase_sessions"] / funnel["sessions"]
        notes.append("conversion rate recomputed from completed-checkout / "
                     "sessions counts")
    _guard_site_cvr(rate, path, "site conversion rate")
    if funnel.get("sessions"):
        if "atc_sessions" in funnel:
            funnel["atc_rate"] = funnel["atc_sessions"] / funnel["sessions"]
        if "checkout_sessions" in funnel:
            funnel["checkout_rate"] = (funnel["checkout_sessions"]
                                       / funnel["sessions"])
    if rate is not None:
        funnel["cvr"] = rate
    if derived:
        funnel["derived"] = derived
    return funnel, _meta(loaded, len(src_rows), notes, loaded["totals"] and
                         _extract(loaded["totals"], header,
                                  _SHOPIFY_SEGMENT_SPEC, ga4=False),
                         basis="sessions")


def shopify_product_rows(path: str) -> tuple[list[dict], dict]:
    """shopify-sales-product.csv (Sales by product) -> (rows, meta).

    NEEDS-REAL-EXPORT-VALIDATION. Rows {product, revenue, orders?, units?}
    (plan §4 products_agg shape; concentration: spend=revenue, conv=orders).
    revenue prefers Net sales > Total sales > Gross sales — the matched
    column is recorded in meta["revenue_column"]."""
    loaded = load_shopify_csv(path, "shopify-sales-product.csv")
    header = loaded["header"]
    name_col = _col_any(header, _NAME_COLUMN["shopify-sales-product.csv"])
    rows = []
    for row in loaded["rows"]:
        d = {"product": str(row.get(name_col) or "").strip()}
        d.update(_extract(row, header, _PRODUCT_SPEC, ga4=False))
        rows.append(d)
    rows.sort(key=lambda r: (-(r.get("revenue") or 0.0), r["product"]))
    totals = (_extract(loaded["totals"], header, _PRODUCT_SPEC, ga4=False)
              if loaded["totals"] is not None else None)
    rev_col = _col_any(header, ("Net sales", "Total sales", "Gross sales"))
    return rows, _meta(loaded, len(rows), [], totals, revenue_column=rev_col)


def shopify_traffic_source_rows(path: str) -> tuple[list[dict], dict]:
    """shopify-traffic-source.csv (Sales/Sessions by traffic source) ->
    (rows, meta).

    NEEDS-REAL-EXPORT-VALIDATION. Rows {name, sessions, cvr?, orders?,
    revenue?} — 'orders' is auxiliary evidence, never 'conversions'
    (order counts are not the sessions-converted numerator)."""
    return _segment_rows(path, "shopify-traffic-source.csv", ga4=False,
                         spec=_SHOPIFY_SEGMENT_SPEC)


def shopify_landing_rows(path: str) -> tuple[list[dict], dict]:
    """shopify-landing.csv (Sessions by landing page) -> (rows, meta).

    NEEDS-REAL-EXPORT-VALIDATION. Rows {name, sessions, cvr?, ...}; names
    URL-normalized BEFORE any math and duplicates merged (mirrors
    shopify_rows.landing_rows_from_table)."""
    rows, meta = _segment_rows(path, "shopify-landing.csv", ga4=False,
                               spec=_SHOPIFY_SEGMENT_SPEC)
    merged = _merge_landing(rows)
    if len(merged) != len(rows):
        meta["notes"].append(f"{len(rows)} rows merged into {len(merged)} "
                             "after URL normalization")
    return merged, meta


def _canon_customer(name: str) -> str:
    low = name.lower()
    if "first" in low or "new" in low:
        return "new"
    if "return" in low:
        return "returning"
    return name


def shopify_customer_rows(path: str) -> tuple[list[dict], dict]:
    """shopify-customers.csv (First-time vs returning customers) ->
    (rows, meta).

    NEEDS-REAL-EXPORT-VALIDATION. Rows {name ('new'/'returning'),
    customers?, orders?, revenue?, cvr?} — ORDER-SHARE EVIDENCE ONLY; the
    session-basis new-vs-returning source is GA4 (ga4-new-returning.csv).
    When both per-type customer counts are present, meta["customers_summary"]
    mirrors shopify_rows.customers_from_table ({customers,
    returning_customers, returning_customer_rate}); the rate is
    returning/total (noted — unlike AOV this ratio is exact: SHAPE-NOTES
    173/530 == 0.32641509…)."""
    loaded = load_shopify_csv(path, "shopify-customers.csv")
    header = loaded["header"]
    if _col_any(header, ("Customers", "Orders", "Total sales", "Net sales",
                         "Sales")) is None:
        raise ManualCsvError(
            f"{path}: no numeric column (Customers / Orders / Total sales) — "
            "is this the first-time vs returning customers export? "
            "See references/data-intake.md.")
    name_col = _col_any(header, _NAME_COLUMN["shopify-customers.csv"])
    rows = []
    for row in loaded["rows"]:
        d = {"name": _canon_customer(str(row.get(name_col) or "").strip())}
        d.update(_extract(row, header, _CUSTOMER_SPEC, ga4=False))
        rows.append(d)
    rows.sort(key=lambda r: r["name"])  # 'new' before 'returning'
    totals = (_extract(loaded["totals"], header, _CUSTOMER_SPEC, ga4=False)
              if loaded["totals"] is not None else None)
    notes: list[str] = []
    by = {r["name"]: r for r in rows}
    summary = None
    if "new" in by and "returning" in by and \
            by["new"].get("customers") is not None and \
            by["returning"].get("customers") is not None:
        total = by["new"]["customers"] + by["returning"]["customers"]
        summary = {"customers": total,
                   "returning_customers": by["returning"]["customers"]}
        if total > 0:
            summary["returning_customer_rate"] = (
                by["returning"]["customers"] / total)
        notes.append("customers_summary computed from per-type customer "
                     "counts (rate = returning/total)")
    meta = _meta(loaded, len(rows), notes, totals)
    if summary is not None:
        meta["customers_summary"] = summary
    return rows, meta


def shopify_aov(path: str) -> tuple[dict, dict]:
    """shopify-aov.csv (Average order value) -> (totals, meta).

    NEEDS-REAL-EXPORT-VALIDATION. AOV is AUTHORITATIVE VERBATIM (SHAPE-NOTES
    trap: Shopify's AOV formula is its own — NEVER recompute from totals and
    NEVER average daily AOVs). Resolution order: totals row verbatim ->
    single data row verbatim -> None + honest note. Returns {"aov": float}
    (the shopify_rows.totals_from_table key) or {}; meta["aov"] carries the
    resolved value (None when not derivable)."""
    loaded = load_shopify_csv(path, "shopify-aov.csv")
    header = loaded["header"]
    notes: list[str] = []
    aov = None
    src = None
    if loaded["totals"] is not None:
        v = _extract(loaded["totals"], header, _AOV_SPEC, ga4=False)
        if "average_order_value" in v:
            aov, src = v["average_order_value"], "totals row (verbatim)"
    if aov is None and len(loaded["rows"]) == 1:
        v = _extract(loaded["rows"][0], header, _AOV_SPEC, ga4=False)
        if "average_order_value" in v:
            aov, src = v["average_order_value"], "single data row (verbatim)"
    if aov is not None:
        notes.append(f"average_order_value taken from {src}")
        totals_out = {"aov": aov}
    else:
        notes.append("multi-row AOV export without a totals row — AOV not "
                     "derivable verbatim (never recomputed / never averaged); "
                     "provide the dashboard AOV or the Shopify MCP totals")
        totals_out = {}
    meta = _meta(loaded, len(loaded["rows"]), notes,
                 loaded["totals"] and _extract(loaded["totals"], header,
                                               _AOV_SPEC, ga4=False))
    meta["aov"] = aov
    return totals_out, meta


# ── --csv-dir registry ──────────────────────────────────────────────────────

ADAPTERS = {
    "ga4-landing.csv": ga4_landing_rows,
    "ga4-funnel.csv": ga4_funnel,
    "ga4-device.csv": ga4_device_rows,
    "ga4-channels.csv": ga4_channel_rows,
    "ga4-new-returning.csv": ga4_new_returning_rows,
    "shopify-conversion.csv": shopify_conversion_funnel,
    "shopify-sales-product.csv": shopify_product_rows,
    "shopify-traffic-source.csv": shopify_traffic_source_rows,
    "shopify-landing.csv": shopify_landing_rows,
    "shopify-customers.csv": shopify_customer_rows,
    "shopify-aov.csv": shopify_aov,
}


def load_csv_dir(dirpath: str) -> dict:
    """Parse every recognized export in a --csv-dir folder.

    Returns {filename-key: (rows_or_funnel_or_totals, meta)} for each
    ADAPTERS filename present, iterated in sorted key order (deterministic).
    Missing files are skipped silently (the CLI reports coverage); a present
    file that fails its guard raises ManualCsvError loudly."""
    d = Path(dirpath)
    if not d.is_dir():
        raise ManualCsvError(f"--csv-dir not found or not a directory: {dirpath}")
    out = {}
    for key in sorted(ADAPTERS):
        p = d / key
        if p.is_file():
            out[key] = ADAPTERS[key](str(p))
    return out


# ── self-test (inline synthetic CSVs — the real-export gap stays flagged) ───

def _self_test() -> None:  # pragma: no cover - developer harness
    import tempfile

    checks = [0]

    def ok(cond, label):
        checks[0] += 1
        if not cond:
            raise AssertionError(f"self-test check failed: {label}")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)

        def w(name, text):
            p = root / name
            p.write_text(text, encoding="utf-8")
            return str(p)

        # 1. GA4 preamble + Grand total + blank-line second-section stop.
        p = w("ga4-landing.csv",
              "# ----------------------------------------\n"
              "# All Users\n"
              "# Landing page + query string\n"
              "# 20250413-20250711\n"
              "# ----------------------------------------\n"
              "Landing page + query string,Sessions,Key events,"
              "Session key event rate,Total revenue\n"
              "/,2414,88,0.036454,10500.25\n"
              "\"/products/foo?variant=1,fancy\",455,2,0.004396,1200\n"
              "/Products/Foo/,45,1,0.02,100\n"
              "Grand total,20000,400,0.02,\"150,000.25\"\n"
              "\n"
              "# Day-by-day\n"
              "Nth day,Sessions\n"
              "0,100\n1,200\n")
        rows, meta = ga4_landing_rows(p)
        ok(len(rows) == 2, "ga4-landing: 2 merged entity rows (total "
                           "excluded, second section not parsed)")
        ok(all(r["name"] != "0" for r in rows), "second day-by-day section skipped")
        ok(rows[0]["name"] == "/" and rows[0]["sessions"] == 2414,
           "ga4-landing sorted sessions-desc")
        ok(rows[1]["name"] == "/products/foo" and rows[1]["sessions"] == 500,
           "URL-normalized (?query + trailing / + lowercase) and merged")
        ok(abs(rows[1]["cvr"] - (455 * 0.004396 + 45 * 0.02) / 500) < 1e-12,
           "merged cvr = sessions-weighted mean")
        ok(rows[1]["key_events"] == 3 and abs(rows[1]["revenue"] - 1300) < 1e-9,
           "auxiliary counts/money summed on merge")
        ok(any("merged into" in n for n in meta["notes"]), "merge note present")
        ok(abs(rows[0]["cvr"] - 0.036454) < 1e-12,
           "GA4 bare rate defaults FRACTION")
        ok(meta["totals"] == {"sessions": 20000, "key_events": 400,
                              "cvr": 0.02, "revenue": 150000.25},
           "Grand total captured as universe totals (thousands comma parsed)")
        ok(meta["window"] == "2025-04-13 – 2025-07-11",
           "GA4 preamble date range -> window")
        ok(meta["stamp"]["file"] == "ga4-landing.csv" and
           len(meta["stamp"]["sha256"]) == 64, "stamp present")

        # 2. wrong-report guard: device export fed to the landing adapter.
        p = w("ga4-device.csv",
              "# 20250413-20250711\n"
              "Device category,Sessions,Session key event rate\n"
              "mobile,\"15,980\",0.014268\n"
              "desktop,5292,0.038171\n"
              "tablet,590,0.006780\n")
        try:
            ga4_landing_rows(p)
            ok(False, "wrong-report guard should raise")
        except ManualCsvError as e:
            ok("Landing page + query string" in str(e),
               "wrong-report guard names the missing column")
        rows, meta = ga4_device_rows(p)
        ok([r["name"] for r in rows] == ["mobile", "desktop", "tablet"],
           "ga4-device sorted sessions-desc")
        ok(rows[0]["sessions"] == 15980, "thousands comma count parsed")

        # 3. Shopify plain header + Totals row + %-cells vs fraction cells.
        p = w("shopify-traffic-source.csv",
              "Referrer source,Sessions,Conversion rate,Total sales\n"
              "search,7927,2.40%,45000.10\n"
              "direct,7263,0.0292,21000\n"
              "social,6496,0.35%,3210.55\n"
              "email,73,5.48,1000\n"
              "Totals,20000,2.00%,\"$150,000.25\"\n")
        rows, meta = shopify_traffic_source_rows(p)
        ok(len(rows) == 4, "Totals row excluded from entities")
        by = {r["name"]: r for r in rows}
        ok(abs(by["search"]["cvr"] - 0.0240) < 1e-12, "'2.40%' -> 0.0240")
        ok(abs(by["direct"]["cvr"] - 0.0292) < 1e-12, "'0.0292' stays fraction")
        ok(abs(by["email"]["cvr"] - 0.0548) < 1e-12,
           "Shopify bare '5.48' > 1 -> percent-scale /100")
        ok(abs(meta["totals"]["cvr"] - 0.02) < 1e-12 and
           meta["totals"]["sessions"] == 20000 and
           abs(meta["totals"]["revenue"] - 150000.25) < 1e-9,
           "Totals captured (currency prefix + commas parsed)")

        # 4. prefix-matched columns: 'Net sales (CAD)' satisfies 'Net sales'.
        p = w("shopify-sales-product.csv",
              "﻿Product title,Net sales (CAD),Orders,Net quantity\n"
              "\"BULK SWEETENER A - 25 kg\",\"12,345.67\",1,1\n"
              "BULK MIX B,4321,1,2\n"
              "Total,\"16,666.67\",2,3\n")
        rows, meta = shopify_product_rows(p)
        ok(meta["revenue_column"] == "Net sales (CAD)",
           "prefix match: 'Net sales' -> 'Net sales (CAD)' (BOM tolerated)")
        ok(rows[0] == {"product": "BULK SWEETENER A - 25 kg",
                       "revenue": 12345.67, "orders": 1, "units": 1},
           "product row shape {product, revenue, orders, units}")
        ok(meta["totals"] == {"revenue": 16666.67, "orders": 2, "units": 3},
           "'Total' totals row captured")

        # 5. GA4 funnel: users basis, computed conversion_rate, notes.
        p = w("ga4-funnel.csv",
              "# 20250413-20250711\n"
              "Step,Active users,Completion rate\n"
              "1. session_start,\"20,000\",12.1%\n"
              "2. add_to_cart,2600,78.1%\n"
              "3. begin_checkout,2000,20.9%\n"
              "4. purchase,400,\n")
        funnel, meta = ga4_funnel(p)
        ok(funnel["sessions"] == 20000 and
           funnel["atc_sessions"] == 2600 and
           funnel["checkout_sessions"] == 2000 and
           funnel["purchase_sessions"] == 400,
           "GA4 funnel stage mapping (shopify_rows.funnel_from_table keys)")
        ok(abs(funnel["cvr"] - 400 / 20000) < 1e-12 and
           abs(funnel["atc_rate"] - 2600 / 20000) < 1e-12 and
           abs(funnel["checkout_rate"] - 2000 / 20000) < 1e-12,
           "cvr/atc_rate/checkout_rate computed from user counts")
        ok(meta["basis"] == "users", "ga4-funnel meta carries basis:'users'")
        ok(any("USERS" in n for n in meta["notes"]), "users-basis note present")

        # 6. shopify-conversion aggregation + 'Sessions converted (%)' header
        #    + derived half-up purchases + weighted rate.
        p = w("shopify-conversion.csv",
              "Day,Sessions,Sessions with cart additions,"
              "Sessions that reached checkout,Sessions converted (%)\n"
              "2026-05-01,1000,120,90,1.9%\n"
              "2026-05-02,500,60,45,2.1%\n")
        funnel, meta = shopify_conversion_funnel(p)
        ok(funnel["sessions"] == 1500 and
           funnel["atc_sessions"] == 180 and
           funnel["checkout_sessions"] == 135,
           "period rows summed")
        ok(abs(funnel["cvr"] - (0.019 * 1000 + 0.021 * 500) / 1500)
           < 1e-12, "session-weighted rate")
        ok(abs(funnel["atc_rate"] - 180 / 1500) < 1e-12 and
           abs(funnel["checkout_rate"] - 135 / 1500) < 1e-12,
           "atc_rate/checkout_rate from summed counts")
        ok(funnel["purchase_sessions"] == 30 and
           funnel["derived"] == ["purchase_sessions"],
           "derived purchases floor(29.5+0.5)=30, flagged")
        ok(meta["window"] == "2026-05-01 – 2026-05-02" and
           meta["basis"] == "sessions", "Day-column window + sessions basis")

        # 7. shopify-conversion totals row verbatim beats aggregation.
        p = w("shopify-conversion.csv",
              "Day,Sessions,Sessions that completed checkout,Conversion rate\n"
              "2026-05-01,1000,20,2%\n"
              "Totals,1000,20,2%\n")
        funnel, meta = shopify_conversion_funnel(p)
        ok(funnel["sessions"] == 1000 and
           funnel["purchase_sessions"] == 20 and
           abs(funnel["cvr"] - 0.02) < 1e-12 and
           "derived" not in funnel, "totals row used verbatim")
        ok(any("verbatim" in n for n in meta["notes"]), "verbatim note")

        # 8. >20% site-CVR mis-scale abort.
        p = w("shopify-conversion.csv",
              "Day,Sessions,Sessions that completed checkout\n"
              "2026-05-01,100,45\n"
              "2026-05-02,100,40\n")
        try:
            shopify_conversion_funnel(p)
            ok(False, "mis-scale guard should raise")
        except ManualCsvError as e:
            ok("mis-scaled" in str(e), "site CVR 0.425 > 0.20 aborts")
        p = w("shopify-conversion.csv",  # rate column mis-scaled: 1.9 as frac?
              "Day,Sessions,Conversion rate\n"
              "2026-05-01,1000,45%\n")
        try:
            shopify_conversion_funnel(p)
            ok(False, "mis-scale guard (rate column) should raise")
        except ManualCsvError:
            ok(True, "45% site rate aborts")

        # 9. GA4 channels + new/returning canonicalization + users-basis note.
        p = w("ga4-channels.csv",
              "Session default channel group,Sessions,"
              "Session key event rate,Total revenue\n"
              "Organic Search,9000,0.024,50000\n"
              "Direct,7000,0.029,41000\n"
              "Paid Social,5000,0.0035,3000\n")
        rows, meta = ga4_channel_rows(p)
        ok([r["name"] for r in rows] == ["Organic Search", "Direct",
                                         "Paid Social"], "channels sorted")
        ok(rows[2]["revenue"] == 3000.0, "channel revenue parsed")
        p = w("ga4-new-returning.csv",
              "New / established,Active users,Session key event rate\n"
              "new,18000,0.015\n"
              "established,3900,0.032\n")
        rows, meta = ga4_new_returning_rows(p)
        ok([r["name"] for r in rows] == ["new", "returning"],
           "nvr canonical names ('established' -> 'returning')")
        ok(rows[0]["sessions"] == 18000, "Active users stands in for sessions")
        ok(any("users basis" in n for n in meta["notes"]),
           "nvr users-basis note when Active users used")

        # 10. shopify landing + customers.
        p = w("shopify-landing.csv",
              "Landing page path,Sessions,Conversion rate\n"
              "/,2414,3.65%\n"
              "/search,748,3.61%\n"
              "Grand total,20000,2.00%\n")
        rows, meta = shopify_landing_rows(p)
        ok(len(rows) == 2 and meta["totals"]["sessions"] == 20000,
           "shopify-landing Grand total guard")
        ok(abs(rows[0]["cvr"] - 0.0365) < 1e-12, "'3.65%' -> 0.0365")
        p = w("shopify-customers.csv",
              "Customer type,Customers,Orders,Total sales\n"
              "First-time,357,470,120000.50\n"
              "Returning,173,173,42463.19\n")
        rows, meta = shopify_customer_rows(p)
        ok([r["name"] for r in rows] == ["new", "returning"],
           "customer type canonicalized ('First-time' -> 'new')")
        ok(rows[1] == {"name": "returning", "customers": 173, "orders": 173,
                       "revenue": 42463.19}, "customer row shape")
        ok(meta["customers_summary"]["customers"] == 530 and
           meta["customers_summary"]["returning_customers"] == 173 and
           abs(meta["customers_summary"]["returning_customer_rate"]
               - 173 / 530) < 1e-12,
           "customers_summary mirrors shopify_rows.customers_from_table")

        # 11. AOV verbatim: totals row wins; multi-row-no-totals -> None+note;
        #     single row verbatim.
        p = w("shopify-aov.csv",
              "Day,Average order value\n"
              "2026-05-01,240.10\n"
              "2026-05-02,245.30\n"
              "Totals,250.125\n")
        totals, meta = shopify_aov(p)
        ok(totals == {"aov": 250.125} and
           meta["aov"] == 250.125, "AOV totals row verbatim (never recomputed)")
        p = w("shopify-aov.csv",
              "Day,Average order value\n"
              "2026-05-01,240.10\n"
              "2026-05-02,245.30\n")
        totals, meta = shopify_aov(p)
        ok(totals == {} and meta["aov"] is None and
           any("never recomputed" in n for n in meta["notes"]),
           "multi-row AOV without totals -> None + honest note")
        p = w("shopify-aov.csv",
              "Average order value\n250.125\n")
        totals, meta = shopify_aov(p)
        ok(meta["aov"] == 250.125, "single-row AOV verbatim")

        # 12. load_csv_dir coverage + determinism (double parse identical).
        w("shopify-conversion.csv",  # restore a valid file after case 8
          "Day,Sessions,Sessions with cart additions,"
          "Sessions that reached checkout,Sessions converted (%)\n"
          "2026-05-01,1000,120,90,1.9%\n"
          "2026-05-02,500,60,45,2.1%\n")
        out1 = load_csv_dir(str(root))
        out2 = load_csv_dir(str(root))
        ok(sorted(out1) == ["ga4-channels.csv", "ga4-device.csv",
                            "ga4-funnel.csv", "ga4-landing.csv",
                            "ga4-new-returning.csv", "shopify-aov.csv",
                            "shopify-conversion.csv", "shopify-customers.csv",
                            "shopify-landing.csv",
                            "shopify-sales-product.csv",
                            "shopify-traffic-source.csv"],
           "load_csv_dir finds all 11 filenames")
        ok(out1 == out2, "double parse byte-identical (deterministic)")

        # 13. missing file / empty file loud failures.
        try:
            ga4_landing_rows(str(root / "nope.csv"))
            ok(False, "missing file should raise")
        except ManualCsvError:
            ok(True, "missing file raises ManualCsvError")
        p = w("shopify-aov.csv", "")
        try:
            shopify_aov(p)
            ok(False, "empty file should raise")
        except ManualCsvError:
            ok(True, "empty file raises ManualCsvError")

    print(f"manual_csv self-test OK ({checks[0]} checks)")


if __name__ == "__main__":
    import json
    import sys

    args = [a for a in sys.argv[1:] if a != "--self-test"]
    if args:
        summary = {}
        for key, (data, meta) in sorted(load_csv_dir(args[0]).items()):
            summary[key] = {
                "rows": len(data) if isinstance(data, list) else 1,
                "window": meta["window"],
                "notes": meta["notes"],
            }
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        _self_test()
