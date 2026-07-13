#!/usr/bin/env python3
# Copyright (c) 2026 Clickt Digital Marketing Inc. All rights reserved.
"""Raw Shopify MCP result loader/normalizer for the Shopify CRO audit.

Inputs are RAW saved MCP tool-result files (the transcription firewall): the
model handles file paths, never numbers. The tolerant concatenated-docs
reader is ported from the meta-ads-audit ``meta_rows.py`` and extended to
skip non-JSON spans, because Shopify MCP error results arrive as error prose
plus the echoed EMPTY envelope wrapped in an injection-warning tag — such
error-shaped results (empty ``columns`` + ``rows``) raise :class:`RawResultError`
pointing at ``references/shopify-pulls.md``.

ShopifyQL envelope (pinned in SHAPE-NOTES.md, verified live 2026-07-12)::

    {"query": str,
     "columns": [{"name": str, "dataType": "STRING"|"INTEGER"|"MONEY"|"PERCENT"}],
     "rows": [[str, ...]], "rowCount": int, "chartHint"?: {...},
     "summaryMetric"?: {"label", "value"}, "shopDomain": str}

Pinned parsing facts:

* Rows are arrays of STRINGS, positionally matched to ``columns`` — coerce by
  ``dataType``: INTEGER -> int, MONEY -> float (plain decimal strings, no
  symbols), STRING -> str (verbatim).
* **PERCENT dataType = FRACTION values** ("0.0198..." means 1.98%; verified
  conversion_rate == purchases/sessions exactly). NEVER multiply or divide by
  100 at parse time — fractions are the cvr_signals unit, and machine.py
  converts fraction -> percent exactly once at the payload boundary.
* ``summaryMetric.value`` is a comma-formatted string of the sum over the
  RETURNED rows only (never the universe total — a LIMIT-truncated GROUP BY
  sums just the returned page). :func:`checksum_note` uses it as a parse
  checksum and returns a warn note on mismatch.
* **AOV TRAP (validated live)**: ``average_order_value`` (242.494) is NEITHER
  total_sales/orders (298.91) NOR net_sales/orders (252.66) — Shopify's AOV
  formula is its own. :func:`totals_from_table` takes it VERBATIM from the
  column and NEVER recomputes it from totals.

Adapter output shapes (FRACTION units — manual_csv.py mirrors these exactly):

* ``funnel_from_table``   -> ``{"sessions": int, "atc_sessions": int?,
  "checkout_sessions": int?, "purchase_sessions": int?, "atc_rate": frac?,
  "checkout_rate": frac?, "cvr": frac?}`` (cvr verbatim from the PERCENT
  column when present; counts-derived only as a fallback)
* ``device_rows_from_table`` / ``referrer_rows_from_table`` /
  ``landing_rows_from_table`` -> ``[{"name": str, "sessions": int,
  "cvr": frac?}]`` sorted sessions desc, name asc. Landing names are
  URL-normalized (strip ?query, strip trailing "/" except the bare root,
  lowercase) and duplicates merge: sessions sum, cvr recomputed as the
  sessions-weighted mean.
* ``product_rows_from_table`` -> ``[{"product": str, "revenue": float,
  "orders": int?}]`` sorted revenue desc, product asc (revenue = net_sales,
  gross_sales fallback).
* ``totals_from_table``    -> ``{"orders": int?, "net_sales": float?,
  "total_sales": float?, "aov": float?}`` — aov VERBATIM (see trap above).
* ``customers_from_table`` -> ``{"customers": int?, "returning_customers":
  int?, "returning_customer_rate": frac?}`` (order-share, evidence only —
  session-based new-vs-returning CVR is NOT exposed by ShopifyQL).

Absent values follow the meta convention: the key is simply omitted (never
None, except None cells inside :func:`load_table` rows for blank numerics).

Stdlib only. Deterministic: no wall clock, fixed sort orders, fixed note
wording.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from pathlib import Path

RAW_PULLS_DOC = "references/shopify-pulls.md"

QL_DTYPES = ("STRING", "INTEGER", "MONEY", "PERCENT")

# summaryMetric comparison tolerance by dataType (float sums of 2dp money
# strings drift ~1e-9; integers are exact; percent never summarized so far).
_CHECKSUM_TOL = {"INTEGER": 0.5, "MONEY": 0.005, "PERCENT": 1e-6}


class RawResultError(ValueError):
    """A saved raw-results file is missing, malformed, error-shaped, or from
    the wrong pull."""


# ── tolerant document reader (ported from meta_rows.py, + stray-text skip) ──

def _read_text(path) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise RawResultError(
            f"raw results file not found: {path} (see {RAW_PULLS_DOC})") from e


def _scan(text: str, path: str) -> tuple[list, str]:
    """Parse every JSON document in the file -> (docs, stray_text).

    Tolerates concatenated documents AND non-JSON text around/between them
    (error prose, injection-warning tag wrappers). ``stray_text`` collects the
    skipped spans so error-shaped results can surface a snippet. No JSON
    document at all -> RawResultError (loud fail, never guess numbers).
    """
    text = text.lstrip("\ufeff")
    if not text.strip():
        raise RawResultError(f"{path}: file is empty (see {RAW_PULLS_DOC})")
    try:
        return [json.loads(text)], ""
    except json.JSONDecodeError:
        pass
    dec = json.JSONDecoder()
    docs: list = []
    stray_parts: list[str] = []
    i, n = 0, len(text)
    while i < n:
        starts = [k for k in (text.find("{", i), text.find("[", i)) if k != -1]
        if not starts:
            stray_parts.append(text[i:])
            break
        j = min(starts)
        if j > i:
            stray_parts.append(text[i:j])
        try:
            doc, end = dec.raw_decode(text, j)
        except json.JSONDecodeError:
            stray_parts.append(text[j])
            i = j + 1
            continue
        docs.append(doc)
        i = end
    stray = " ".join(p.strip() for p in stray_parts if p.strip())
    if not docs:
        snippet = stray[:120]
        raise RawResultError(
            f"{path}: no JSON document found — the file must be the verbatim "
            f"tool result, nothing hand-edited (see {RAW_PULLS_DOC}) "
            f"(leading text: {snippet!r})")
    return docs, stray


def _undouble(doc):
    """Decode a double-encoded (string) JSON document; leave others as-is."""
    if isinstance(doc, str):
        try:
            return json.loads(doc)
        except json.JSONDecodeError:
            return doc
    return doc


# ── ShopifyQL envelope parsing ──────────────────────────────────────────────

def _is_envelope(doc) -> bool:
    return (isinstance(doc, dict)
            and isinstance(doc.get("columns"), list)
            and isinstance(doc.get("rows"), list))


def load_envelope(path) -> dict:
    """Load ONE ShopifyQL result envelope from a saved run-analytics-query
    file.

    Error-shaped results (empty ``columns`` + ``rows``, as echoed alongside
    ShopifyQL error text) -> RawResultError. Concatenated envelopes with an
    IDENTICAL column signature merge their rows (a paginated pull saved into
    one file); the merged doc drops ``summaryMetric`` because per-page sums
    cannot be combined.
    """
    docs, stray = _scan(_read_text(path), str(path))
    envelopes = [d for d in (_undouble(doc) for doc in docs) if _is_envelope(d)]
    if not envelopes:
        raise RawResultError(
            f"{path}: no ShopifyQL envelope (columns/rows) found — is this "
            f"the saved run-analytics-query result? (see {RAW_PULLS_DOC})")
    good = [e for e in envelopes if e["columns"]]
    if not good:
        snippet = stray.strip()[:160]
        raise RawResultError(
            f"{path}: error-shaped result (empty columns/rows) — the ShopifyQL "
            f"query failed; fix and re-run it, then save the verbatim result "
            f"(see {RAW_PULLS_DOC})"
            + (f" [error text: {snippet!r}]" if snippet else ""))
    if len(good) == 1:
        return good[0]
    sig0 = [(c.get("name"), c.get("dataType")) for c in good[0]["columns"]]
    for e in good[1:]:
        if [(c.get("name"), c.get("dataType")) for c in e["columns"]] != sig0:
            raise RawResultError(
                f"{path}: multiple ShopifyQL envelopes with different columns "
                f"— save one query per file (see {RAW_PULLS_DOC})")
    merged = dict(good[0])
    rows: list = []
    for e in good:
        rows.extend(e["rows"])
    merged["rows"] = rows
    merged["rowCount"] = len(rows)
    merged.pop("summaryMetric", None)  # per-page sum; meaningless after merge
    return merged


def _coerce_cell(raw, dtype, *, col, row_idx, path):
    """Coerce one row cell by its column dataType (SHAPE-NOTES facts 1-3).

    INTEGER -> int, MONEY -> float, STRING -> str (verbatim), blank numeric
    cells -> None. PERCENT -> float taken AS-IS: the PERCENT dataType carries
    FRACTION strings ("0.0198..." = 1.98%) — NEVER multiply or divide by 100
    here. Unknown dataTypes pass through as the raw string.
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise RawResultError(
            f"{path}: row {row_idx} column {col!r}: unexpected boolean cell "
            f"(see {RAW_PULLS_DOC})")
    if isinstance(raw, (int, float)):  # tolerate a pre-coerced numeric cell
        if dtype == "INTEGER":
            return int(raw)
        if dtype in ("MONEY", "PERCENT"):
            return float(raw)
        return str(raw)
    if not isinstance(raw, str):
        raise RawResultError(
            f"{path}: row {row_idx} column {col!r}: unexpected cell type "
            f"{type(raw).__name__} (see {RAW_PULLS_DOC})")
    if dtype == "STRING" or dtype not in QL_DTYPES:
        return raw
    s = raw.strip()
    if not s:
        return None
    try:
        if dtype == "INTEGER":
            t = s.replace(",", "")
            try:
                return int(t)
            except ValueError:
                f = float(t)
                if f.is_integer():
                    return int(f)
                raise ValueError(t)
        if dtype == "MONEY":
            return float(s.replace(",", ""))
        # PERCENT: fraction string, verbatim value — no unit change.
        return float(s)
    except ValueError as e:
        raise RawResultError(
            f"{path}: row {row_idx} column {col!r}: cannot coerce {raw!r} to "
            f"{dtype} — is this the verbatim saved result? "
            f"(see {RAW_PULLS_DOC})") from e


def rows_from_envelope(doc, path="<doc>") -> list[dict]:
    """One parsed ShopifyQL envelope -> list of {column_name: coerced} dicts."""
    if not _is_envelope(doc):
        raise RawResultError(
            f"{path}: not a ShopifyQL envelope (columns/rows) "
            f"(see {RAW_PULLS_DOC})")
    cols = doc["columns"]
    rows = doc["rows"]
    if not cols and not rows:
        raise RawResultError(
            f"{path}: error-shaped result (empty columns/rows) — the ShopifyQL "
            f"query failed; fix and re-run it (see {RAW_PULLS_DOC})")
    specs = []
    for i, c in enumerate(cols):
        if not isinstance(c, dict) or not c.get("name"):
            raise RawResultError(
                f"{path}: columns[{i}] has no name (see {RAW_PULLS_DOC})")
        specs.append((str(c["name"]), str(c.get("dataType") or "STRING")))
    out: list[dict] = []
    for i, row in enumerate(rows):
        if not isinstance(row, list) or len(row) != len(specs):
            raise RawResultError(
                f"{path}: row {i} does not match the {len(specs)} declared "
                f"columns (see {RAW_PULLS_DOC})")
        rec: dict = {}
        for (name, dtype), cell in zip(specs, row):
            rec[name] = _coerce_cell(cell, dtype, col=name, row_idx=i,
                                     path=path)
        out.append(rec)
    return out


def load_table(path) -> list[dict]:
    """ShopifyQL envelope file -> list of {column_name: coerced-value} dicts.

    Row order is kept VERBATIM (the query's ORDER BY); adapters apply their
    own deterministic sorts.
    """
    return rows_from_envelope(load_envelope(path), str(path))


def _fmt_num(x: float) -> str:
    return f"{int(x):,}" if float(x).is_integer() else f"{x:,.2f}"


def checksum_note(doc) -> str | None:
    """Compare ``summaryMetric.value`` to the parsed column sum.

    ``summaryMetric.value`` is the sum over the RETURNED rows only — never
    the universe total (SHAPE-NOTES fact 4: products LIMIT 50 summarizes
    91,835.43 while the account total is 162,463.19), so it is a parse
    checksum, nothing more. Returns None on match (or when there is no
    summaryMetric), else a deterministic warn-note string. Accepts a parsed
    envelope dict or a path.
    """
    if isinstance(doc, (str, Path)):
        doc = load_envelope(doc)
    if not isinstance(doc, dict):
        raise RawResultError(
            f"checksum_note expects an envelope dict or a path "
            f"(see {RAW_PULLS_DOC})")
    sm = doc.get("summaryMetric")
    if not isinstance(sm, dict):
        return None
    label = str(sm.get("label") or "")
    raw_val = sm.get("value")
    dtypes = {str(c.get("name")): str(c.get("dataType") or "STRING")
              for c in doc.get("columns", []) if isinstance(c, dict)}
    if label not in dtypes:
        return (f"checksum: summaryMetric label {label!r} is not a returned "
                f"column — parse unverified (see {RAW_PULLS_DOC})")
    try:
        expected = float(str(raw_val).replace(",", "").strip())
    except (TypeError, ValueError):
        return (f"checksum: summaryMetric value {raw_val!r} is not numeric — "
                f"parse unverified (see {RAW_PULLS_DOC})")
    total, seen = 0.0, False
    for rec in rows_from_envelope(doc):
        v = rec.get(label)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            total += float(v)
            seen = True
    if not seen:
        return (f"checksum: no numeric values parsed for summaryMetric column "
                f"{label!r} — parse unverified (see {RAW_PULLS_DOC})")
    tol = _CHECKSUM_TOL.get(dtypes[label], 0.005)
    if abs(total - expected) <= tol:
        return None
    return (f"checksum: summaryMetric {label} {_fmt_num(expected)} != sum of "
            f"returned rows {_fmt_num(total)} — the saved pull may be "
            f"truncated or hand-edited; re-save the verbatim result "
            f"(see {RAW_PULLS_DOC})")


# ── other tools: shop info / orders / products ──────────────────────────────

_SHOP_KEYS = ("name", "domain", "currencyCode", "planName", "myshopifyDomain")

_ISO_TS_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})"
    r"(?:T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))?$")


def _iso_or_none(v) -> str | None:
    """Validate an ISO date/timestamp string ("2026-07-11T14:20:32Z" or
    "2026-07-11"); returns it VERBATIM, or None when absent/unparseable."""
    if not isinstance(v, str):
        return None
    s = v.strip()
    m = _ISO_TS_RE.match(s)
    if not m:
        return None
    try:
        _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None
    return s


def _float_or_none(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        f = float(v)
        if f != f or f in (float("inf"), float("-inf")):
            return None
        return f
    if isinstance(v, str):
        s = v.replace("\u00a0", " ").replace(",", "").strip()
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _clean_str(v) -> str | None:
    if v is None:
        return None
    s = str(v).replace("\u00a0", " ").strip()
    return s or None


def load_shop_info(path) -> dict:
    """Load a saved get-shop-info result: the flat ``{name, domain, email,
    planName, currencyCode, timezone, country, criticalUserMessage}`` object,
    passed through verbatim (provenance note: MCP ``shopDomain`` elsewhere is
    the myshopify subdomain, not this storefront domain)."""
    docs, _ = _scan(_read_text(path), str(path))
    for doc in docs:
        doc = _undouble(doc)
        if (isinstance(doc, dict) and not _is_envelope(doc)
                and any(k in doc for k in _SHOP_KEYS)):
            return dict(doc)
    raise RawResultError(
        f"{path}: no get-shop-info object found (expected keys like "
        f"name/domain/currencyCode) — is this the saved result for the right "
        f"pull? (see {RAW_PULLS_DOC})")


def load_orders(path) -> list[dict]:
    """Load a saved list-orders result -> canonical order rows.

    Envelope: ``{orders: [{id, name, createdAt, customerName, totalPrice,
    currencyCode, financialStatus, fulfillmentStatus, lineItemCount}],
    totalCount, requestedCount}`` (max 50/page, NO line-item detail;
    totalCount is all-time). Canonical row: ``{id, name, created_at (ISO,
    verbatim-validated), total_price (float), currency, customer_name,
    financial_status, fulfillment_status, line_item_count}`` — absent keys
    omitted. Sorted created_at desc, name asc. Orders are a shape-pin /
    optional evidence input only — ShopifyQL sales queries are the
    aggregated source.
    """
    docs, _ = _scan(_read_text(path), str(path))
    items: list = []
    found = False
    for doc in docs:
        doc = _undouble(doc)
        if isinstance(doc, dict) and isinstance(doc.get("orders"), list):
            found = True
            items.extend(doc["orders"])
        elif isinstance(doc, list):
            found = True
            items.extend(doc)
    if not found:
        raise RawResultError(
            f"{path}: no 'orders' array found — is this the saved list-orders "
            f"result? (see {RAW_PULLS_DOC})")
    out: list[dict] = []
    for i, o in enumerate(items):
        if not isinstance(o, dict):
            raise RawResultError(
                f"{path}: orders[{i}] is not an object (see {RAW_PULLS_DOC})")
        rec: dict = {}
        for src, dst in (("id", "id"), ("name", "name"),
                         ("customerName", "customer_name"),
                         ("financialStatus", "financial_status"),
                         ("fulfillmentStatus", "fulfillment_status")):
            s = _clean_str(o.get(src))
            if s is not None:
                rec[dst] = s
        iso = _iso_or_none(o.get("createdAt"))
        if iso is not None:
            rec["created_at"] = iso
        tp = _float_or_none(o.get("totalPrice"))
        if tp is not None:
            rec["total_price"] = tp
        cur = _clean_str(o.get("currencyCode"))
        if cur is not None:
            rec["currency"] = cur
        lic = o.get("lineItemCount")
        if isinstance(lic, (int, float)) and not isinstance(lic, bool):
            rec["line_item_count"] = int(lic)
        out.append(rec)
    out.sort(key=lambda r: r.get("name") or "")
    out.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return out


def _product_nodes(path) -> tuple[list, dict | None]:
    """Saved search_products / graphql_query result -> (nodes, pageInfo).

    GraphQL envelope: ``{data: {products: {edges: [{node: {...}}],
    pageInfo: {hasNextPage, endCursor}}}}``. Concatenated (paginated) docs
    extend the node list; pageInfo is the LAST page's.
    """
    docs, _ = _scan(_read_text(path), str(path))
    nodes: list = []
    page_info: dict | None = None
    found = False
    for doc in docs:
        doc = _undouble(doc)
        if not isinstance(doc, dict):
            continue
        prod = None
        data = doc.get("data")
        if isinstance(data, dict) and isinstance(data.get("products"), dict):
            prod = data["products"]
        elif isinstance(doc.get("products"), dict):
            prod = doc["products"]
        if not isinstance(prod, dict):
            continue
        edges = prod.get("edges")
        if not isinstance(edges, list):
            continue
        found = True
        for j, e in enumerate(edges):
            node = e.get("node") if isinstance(e, dict) else None
            if not isinstance(node, dict):
                raise RawResultError(
                    f"{path}: products edge {j} has no node object "
                    f"(see {RAW_PULLS_DOC})")
            nodes.append(node)
        pi = prod.get("pageInfo")
        if isinstance(pi, dict):
            page_info = pi
    if not found:
        raise RawResultError(
            f"{path}: no GraphQL products edges found — is this the saved "
            f"search_products result? (see {RAW_PULLS_DOC})")
    return nodes, page_info


def load_products(path) -> list[dict]:
    """Load a saved search_products (GraphQL edges/node) result -> canonical
    ``{id, title, price, status, handle, vendor, product_type, currency,
    total_inventory, variants_count, sku, created_at, updated_at}`` rows
    (absent keys omitted; ids are gid:// URIs; descriptions are tool-truncated
    and deliberately dropped). price = priceRangeV2.minVariantPrice.amount,
    first-variant price fallback. Sorted title asc, id asc."""
    nodes, _ = _product_nodes(path)
    out: list[dict] = []
    for i, node in enumerate(nodes):
        title = _clean_str(node.get("title"))
        if not title:
            raise RawResultError(
                f"{path}: product node {i} has no usable 'title' — is this "
                f"the saved result for the right pull? (see {RAW_PULLS_DOC})")
        rec: dict = {"title": title}
        for src, dst in (("id", "id"), ("handle", "handle"),
                         ("status", "status"), ("vendor", "vendor"),
                         ("productType", "product_type")):
            s = _clean_str(node.get(src))
            if s is not None:
                rec[dst] = s
        first_variant = None
        variants = node.get("variants")
        if isinstance(variants, dict):
            vedges = variants.get("edges")
            if isinstance(vedges, list) and vedges \
                    and isinstance(vedges[0], dict) \
                    and isinstance(vedges[0].get("node"), dict):
                first_variant = vedges[0]["node"]
        price = None
        currency = None
        prv2 = node.get("priceRangeV2")
        if isinstance(prv2, dict) and isinstance(
                prv2.get("minVariantPrice"), dict):
            mvp = prv2["minVariantPrice"]
            price = _float_or_none(mvp.get("amount"))
            currency = _clean_str(mvp.get("currencyCode"))
        if price is None and first_variant is not None:
            price = _float_or_none(first_variant.get("price"))
        if price is not None:
            rec["price"] = price
        if currency is not None:
            rec["currency"] = currency
        ti = node.get("totalInventory")
        if isinstance(ti, (int, float)) and not isinstance(ti, bool):
            rec["total_inventory"] = int(ti)
        vc = node.get("variantsCount")
        if isinstance(vc, dict) and isinstance(vc.get("count"), int):
            rec["variants_count"] = vc["count"]
        if first_variant is not None:
            sku = _clean_str(first_variant.get("sku"))
            if sku is not None:
                rec["sku"] = sku
        for src, dst in (("createdAt", "created_at"),
                         ("updatedAt", "updated_at")):
            iso = _iso_or_none(node.get(src))
            if iso is not None:
                rec[dst] = iso
        out.append(rec)
    out.sort(key=lambda r: (r.get("title") or "", r.get("id") or ""))
    return out


def load_products_page_info(path) -> dict | None:
    """pageInfo ``{hasNextPage, endCursor}`` of a saved products pull (last
    page's when the file concatenates pages), or None when absent."""
    return _product_nodes(path)[1]


# ── URL normalization (pinned: applied BEFORE any math) ─────────────────────

def normalize_url(u) -> str:
    """Landing-path normalization: lowercase, strip the ?query, strip
    trailing slashes except the bare root "/". Empty -> "/" (Shopify's blank
    landing path is the root)."""
    s = str(u if u is not None else "").strip().lower()
    q = s.find("?")
    if q != -1:
        s = s[:q]
    while len(s) > 1 and s.endswith("/"):
        s = s[:-1]
    return s or "/"


# ── adapters -> machine/cvr_signals/concentration row shapes ────────────────

def _as_table(source, kind: str) -> list[dict]:
    """Accept a path, a parsed envelope dict, or an already-coerced row list."""
    if isinstance(source, (str, Path)):
        return load_table(source)
    if isinstance(source, dict):
        return rows_from_envelope(source)
    if isinstance(source, list):
        for i, r in enumerate(source):
            if not isinstance(r, dict):
                raise RawResultError(
                    f"{kind} row {i} is not an object (see {RAW_PULLS_DOC})")
        return source
    raise RawResultError(
        f"{kind} adapter expects a path, envelope dict, or row list — got "
        f"{type(source).__name__} (see {RAW_PULLS_DOC})")


def _require_column(rows: list[dict], col: str, kind: str) -> None:
    if rows and col not in rows[0]:
        raise RawResultError(
            f"{kind} result has no {col!r} column — is this the saved result "
            f"for the right pull? (see {RAW_PULLS_DOC})")


def _single_row(table, kind: str) -> dict:
    rows = _as_table(table, kind)
    if len(rows) != 1:
        raise RawResultError(
            f"{kind} result must have exactly 1 row (no GROUP BY), got "
            f"{len(rows)} — is this the saved result for the right pull? "
            f"(see {RAW_PULLS_DOC})")
    return rows[0]


def funnel_from_table(table) -> dict:
    """Full-funnel single-row result -> FRACTION-unit funnel dict.

    ``{"sessions", "atc_sessions", "checkout_sessions", "purchase_sessions",
    "atc_rate", "checkout_rate", "cvr"}`` — cvr is the VERBATIM
    conversion_rate fraction when the PERCENT column is present (verified
    equal to purchases/sessions); counts-derived only as a fallback. Stage
    keys absent from the pull are omitted (measured-stages-only scoring
    downstream).
    """
    r = _single_row(table, "funnel")
    sess = r.get("sessions")
    if sess is None:
        raise RawResultError(
            f"funnel result has no 'sessions' value — is this the saved "
            f"result for the right pull? (see {RAW_PULLS_DOC})")
    out: dict = {"sessions": int(sess)}
    for src, dst in (("sessions_with_cart_additions", "atc_sessions"),
                     ("sessions_that_reached_checkout", "checkout_sessions"),
                     ("sessions_that_completed_checkout", "purchase_sessions")):
        v = r.get(src)
        if v is not None:
            out[dst] = int(v)
    if out["sessions"] > 0:
        if "atc_sessions" in out:
            out["atc_rate"] = out["atc_sessions"] / out["sessions"]
        if "checkout_sessions" in out:
            out["checkout_rate"] = out["checkout_sessions"] / out["sessions"]
    cvr = r.get("conversion_rate")
    if cvr is not None:
        out["cvr"] = float(cvr)  # verbatim fraction from the PERCENT column
    elif out["sessions"] > 0 and "purchase_sessions" in out:
        out["cvr"] = out["purchase_sessions"] / out["sessions"]
    return out


def _name_sessions_cvr(table, name_col: str, kind: str) -> list[dict]:
    rows = _as_table(table, kind)
    _require_column(rows, name_col, kind)
    _require_column(rows, "sessions", kind)
    out: list[dict] = []
    for r in rows:
        name = r.get(name_col)
        if name is None:
            raise RawResultError(
                f"{kind} row has a blank {name_col!r} (see {RAW_PULLS_DOC})")
        sess = r.get("sessions")
        rec: dict = {"name": str(name),
                     "sessions": int(sess) if sess is not None else 0}
        cvr = r.get("conversion_rate")
        if isinstance(cvr, (int, float)) and not isinstance(cvr, bool):
            rec["cvr"] = float(cvr)  # fraction, verbatim
        out.append(rec)
    out.sort(key=lambda r: (-r["sessions"], r["name"]))
    return out


def device_rows_from_table(table) -> list[dict]:
    """GROUP BY session_device_type result -> [{name, sessions, cvr}]
    (fractions; sorted sessions desc, name asc). Device names pass through
    verbatim ("mobile"/"desktop"/"tablet"/"other")."""
    return _name_sessions_cvr(table, "session_device_type", "device")


def referrer_rows_from_table(table) -> list[dict]:
    """GROUP BY referrer_source result -> channel rows [{name, sessions,
    cvr}] (fractions; sorted sessions desc, name asc)."""
    return _name_sessions_cvr(table, "referrer_source", "channel")


def landing_rows_from_table(table) -> list[dict]:
    """GROUP BY landing_page_path result -> page rows [{name, sessions,
    cvr}].

    Names are URL-normalized (:func:`normalize_url`) BEFORE any math;
    duplicates merge: sessions sum, cvr recomputed as the sessions-weighted
    mean over the merged rows that carried a cvr. Sorted sessions desc,
    name asc.
    """
    rows = _as_table(table, "landing")
    _require_column(rows, "landing_page_path", "landing")
    _require_column(rows, "sessions", "landing")
    agg: dict[str, list] = {}
    for r in rows:
        name = normalize_url(r.get("landing_page_path"))
        sess = r.get("sessions")
        sess = int(sess) if sess is not None else 0
        a = agg.setdefault(name, [0, 0.0, 0])  # [sessions, Σs·cvr, s_with_cvr]
        a[0] += sess
        cvr = r.get("conversion_rate")
        if isinstance(cvr, (int, float)) and not isinstance(cvr, bool):
            a[1] += sess * float(cvr)
            a[2] += sess
    out: list[dict] = []
    for name in sorted(agg):
        sess, wsum, s_cvr = agg[name]
        rec: dict = {"name": name, "sessions": sess}
        if s_cvr > 0:
            rec["cvr"] = wsum / s_cvr
        out.append(rec)
    out.sort(key=lambda r: (-r["sessions"], r["name"]))
    return out


def product_rows_from_table(table) -> list[dict]:
    """GROUP BY product_title sales result -> [{product, revenue, orders}]
    (revenue = net_sales, gross_sales fallback; orders omitted when the
    column is absent -> concentration's no_conv_signal). Sorted revenue desc,
    product asc."""
    rows = _as_table(table, "products")
    _require_column(rows, "product_title", "products")
    out: list[dict] = []
    for r in rows:
        title = r.get("product_title")
        if title is None:
            raise RawResultError(
                f"products row has a blank 'product_title' "
                f"(see {RAW_PULLS_DOC})")
        rev = r.get("net_sales")
        if rev is None:
            rev = r.get("gross_sales")
        if rev is None:
            raise RawResultError(
                f"products result has no net_sales/gross_sales value for "
                f"{str(title)!r} — is this the saved result for the right "
                f"pull? (see {RAW_PULLS_DOC})")
        rec: dict = {"product": str(title), "revenue": float(rev)}
        orders = r.get("orders")
        if orders is not None:
            rec["orders"] = int(orders)
        out.append(rec)
    out.sort(key=lambda r: (-r["revenue"], r["product"]))
    return out


def totals_from_table(table) -> dict:
    """Single-row sales totals -> {orders, net_sales, total_sales, aov}.

    AOV TRAP (SHAPE-NOTES fact 5, validated live): Shopify's
    average_order_value (242.494) is NEITHER total_sales/orders (298.91) NOR
    net_sales/orders (252.66) — its formula is Shopify's own. ``aov`` is
    taken VERBATIM from the average_order_value column and is NEVER
    recomputed from the totals; when the column is absent the key is simply
    omitted (never derived).
    """
    r = _single_row(table, "totals")
    out: dict = {}
    orders = r.get("orders")
    if orders is not None:
        out["orders"] = int(orders)
    for col, dst in (("net_sales", "net_sales"), ("total_sales",
                                                  "total_sales")):
        v = r.get(col)
        if v is not None:
            out[dst] = float(v)
    aov = r.get("average_order_value")
    if aov is not None:
        out["aov"] = float(aov)  # VERBATIM — never total_sales/orders etc.
    return out


def customers_from_table(table) -> dict:
    """Single-row customers result -> {customers, returning_customers,
    returning_customer_rate} — the rate is the VERBATIM fraction (PERCENT
    dtype) and is ORDER-SHARE evidence only; session-based new-vs-returning
    CVR is not exposed by ShopifyQL (GA4 remains that source)."""
    r = _single_row(table, "customers")
    out: dict = {}
    for col in ("customers", "returning_customers"):
        v = r.get(col)
        if v is not None:
            out[col] = int(v)
    rate = r.get("returning_customer_rate")
    if rate is not None:
        out["returning_customer_rate"] = float(rate)  # fraction, verbatim
    return out


# ── provenance (ported verbatim from meta_rows.py) ──────────────────────────

def file_stamp(path: str) -> dict:
    """Provenance stamp for a raw input file."""
    p = Path(path)
    return {"file": p.name,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "bytes": p.stat().st_size}
