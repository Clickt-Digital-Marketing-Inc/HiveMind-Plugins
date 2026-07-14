"""Load CSV exports and the YAML column-mapping; map columns -> concepts.

All column-to-concept mapping is driven by a user-supplied YAML file — column
names are NEVER hardcoded or guessed. If a mapped column is absent from the CSV
we fail with a precise error naming the column and the platform.
"""

from __future__ import annotations

import pandas as pd
import yaml

from .weights import FUNNEL_STATES


class MappingError(ValueError):
    """Raised when the mapping config or a mapped column is invalid/missing."""


def load_mapping(mapping_path: str, platform: str) -> dict:
    """Load the per-platform mapping block from a YAML file."""
    with open(mapping_path, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    if not isinstance(cfg, dict) or platform not in cfg:
        available = list(cfg) if isinstance(cfg, dict) else []
        raise MappingError(
            f"Platform '{platform}' not found in mapping file '{mapping_path}'. "
            f"Available platform blocks: {available}."
        )

    block = cfg[platform]
    # Validate the mapping block has every required key before touching the CSV.
    for key in ("denominator", "funnel", "repeats", "segment_id", "currency"):
        if key not in block:
            raise MappingError(
                f"Mapping for platform '{platform}' is missing required key '{key}' "
                f"in '{mapping_path}'."
            )
    for state in FUNNEL_STATES:
        if state not in block["funnel"]:
            raise MappingError(
                f"Mapping for platform '{platform}' is missing funnel state "
                f"'{state}' under 'funnel' in '{mapping_path}'. "
                f"Required states: {FUNNEL_STATES}."
            )
    for ccy in ("CM3_order", "repeat_rate", "CM3_repeat"):
        if ccy not in block["currency"]:
            raise MappingError(
                f"Mapping for platform '{platform}' is missing currency parameter "
                f"'{ccy}' under 'currency' in '{mapping_path}'."
            )
    return block


def load_segments(csv_path: str, mapping: dict, platform: str):
    """Read a segment-export CSV and normalize it to the wPPC schema.

    Returns ``(df, currency)`` where ``df`` has columns:
        segment_id, clicks, click, engagement, add_to_cart,
        initiate_checkout, purchase, repeats
    (``clicks`` is the wPPC denominator; ``click`` is reach at the click state —
    normally the same column.) ``currency`` is the mapping's currency dict.
    """
    skip_rows = int(mapping.get("skip_rows", 0) or 0)
    raw = pd.read_csv(csv_path, skiprows=skip_rows)

    funnel = mapping["funnel"]
    # concept -> source column name in the CSV.
    column_map = {
        "segment_id": mapping["segment_id"],
        "clicks": mapping["denominator"],
        "repeats": mapping["repeats"],
        **{state: funnel[state] for state in FUNNEL_STATES},
    }

    # Validate presence BEFORE any transform — never silently guess a column.
    for concept, col in column_map.items():
        if col not in raw.columns:
            raise MappingError(
                f"Mapped column '{col}' (for '{concept}') is missing from the "
                f"{platform} CSV '{csv_path}'"
                + (f" (after skipping {skip_rows} preamble row(s))" if skip_rows else "")
                + f". Available columns: {list(raw.columns)}."
            )

    out = pd.DataFrame()
    out["segment_id"] = raw[column_map["segment_id"]].astype(str)
    out["clicks"] = _numeric(raw[column_map["clicks"]])
    for state in FUNNEL_STATES:
        out[state] = _numeric(raw[column_map[state]])
    out["repeats"] = _numeric(raw[column_map["repeats"]])

    return out, mapping["currency"]


def _numeric(series: pd.Series) -> pd.Series:
    """Coerce a column to non-negative numbers, tolerating thousands separators."""
    if not pd.api.types.is_numeric_dtype(series):
        series = series.astype(str).str.replace(",", "", regex=False).str.strip()
    return pd.to_numeric(series, errors="coerce").fillna(0.0).clip(lower=0.0)
