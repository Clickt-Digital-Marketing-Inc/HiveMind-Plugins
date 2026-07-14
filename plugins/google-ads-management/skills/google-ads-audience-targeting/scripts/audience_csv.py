#!/usr/bin/env python3
"""CSV manual-input path for google-ads-audience-targeting — the skill's own
`column_map` declarations plus the two CSV assemblers, per the shared
contract in `_shared/csv_input.py` / `google-ads-foundation/references/
artifact-formats.md` ("Dual input (MCP or CSV)").

Two independent CSVs:

  audiences   — the CSV alternative to the MCP pull (`assemble_findings.py`).
                A Google Ads UI "Audiences" report export. Optional — only
                used when the MCP is unavailable or the user already has the
                export; never run both paths for the same data.
  first_party — Customer Match / Enhanced Conversions / Consent Mode v2 / CMP
                readiness. ALWAYS this path — the Google Ads API does not
                return match rates, list sizes, or Enhanced-Conversions /
                Consent-Mode configuration state (see google-ads-foundation/
                references/artifact-formats.md, "What the MCP cannot
                return"). `assemble_from_csv` stamps meta.source = "user_csv"
                — never presented as an API pull.

Both assemblers hand back the SAME row shape `audience_core.build_universe` /
`build_first_party` expect, so the MCP and CSV paths for `audiences` are
provably identical once loaded (tests/test_core.py: MCP-vs-CSV parity).
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parents[2]          # .../plugins/google-ads-management
sys.path.insert(0, str(PLUGIN_ROOT / "_shared"))

from csv_input import assemble_from_csv, CsvInputError  # noqa: E402

# -- applied audiences (Google Ads UI "Audiences" report style export) ------
AUDIENCE_COLUMN_MAP = {
    "campaign": {"aliases": ["Campaign"], "type": "str"},
    "ad_group": {"aliases": ["Ad group", "Ad Group"], "type": "str"},
    "list_name": {"aliases": ["Audience", "Audience name", "Audience segment"], "type": "str"},
    "list_type": {"aliases": ["Audience type", "Segment type"], "type": "str"},
    # UI shows a delta percent (e.g. "+25%"), not the API's 1.0-based
    # multiplier — assemble_audiences_from_csv() converts after reconciliation.
    "bid_modifier_pct": {"aliases": ["Bid adj.", "Bid adjustment", "Audience bid adj."], "type": "pct"},
    "criterion_status": {"aliases": ["Criterion status", "Status"], "type": "str"},
    "negative_label": {"aliases": ["Targeting", "Targeting setting"], "type": "str"},
    "impressions": {"aliases": ["Impr.", "Impressions"], "type": "num"},
    "clicks": {"aliases": ["Clicks"], "type": "num"},
    "cost": {"aliases": ["Cost"], "type": "num"},
    "conversions": {"aliases": ["Conversions"], "type": "num"},
}
AUDIENCE_REQUIRED = ("campaign", "ad_group", "list_name", "criterion_status",
                     "impressions", "clicks", "cost", "conversions")
AUDIENCE_SUMS = ["impressions", "clicks", "cost", "conversions"]

# -- first-party readiness (manual template — no native Ads UI report) ------
FIRST_PARTY_COLUMN_MAP = {
    "category": {"aliases": ["Category"], "type": "str"},
    "item": {"aliases": ["Item", "Check", "Readiness Item"], "type": "str"},
    "row_type": {"aliases": ["Type", "Row Type"], "type": "str"},   # "config" or "manual"
    "readiness": {"aliases": ["Status", "Readiness", "Readiness Status"], "type": "str"},
    "detail": {"aliases": ["Detail", "Notes", "Description"], "type": "str"},
    "verified_date": {"aliases": ["Verified Date", "Last Verified", "Date"], "type": "str"},
}
FIRST_PARTY_REQUIRED = ("category", "item", "row_type", "readiness")


def assemble_audiences_from_csv(csv_path: str, meta: dict) -> dict:
    """User CSV -> the SAME 'audiences' findings shape as assemble_findings.py
    (the MCP path). Reconciliation totals the RAW parsed numeric columns
    (impressions/clicks/cost/conversions); bid_modifier/negative are derived
    AFTERWARD from the delta-% and Targeting columns, so the embedded control
    totals never depend on the derived fields."""
    rows, findings = assemble_from_csv(
        csv_path, column_map=AUDIENCE_COLUMN_MAP, required_fields=AUDIENCE_REQUIRED,
        reconcile_spec={"array": "audiences", "sums": AUDIENCE_SUMS}, meta=meta)
    for r in rows:
        pct = r.pop("bid_modifier_pct", 0.0)
        r["bid_modifier"] = round(1.0 + pct, 4)
        label = str(r.pop("negative_label", "") or "")
        r["negative"] = "exclu" in label.strip().lower()
    return findings


def assemble_first_party_from_csv(csv_path: str, meta: dict) -> dict:
    """User CSV -> the 'first_party' findings shape. Always meta.source =
    'user_csv' (assemble_from_csv's default) — this dataset has no MCP
    alternative; never imply Customer Match / Enhanced Conversions / Consent
    Mode status was confirmed by the API."""
    _, findings = assemble_from_csv(
        csv_path, column_map=FIRST_PARTY_COLUMN_MAP, required_fields=FIRST_PARTY_REQUIRED,
        reconcile_spec={"array": "first_party", "sums": []}, meta=meta)
    return findings
