#!/usr/bin/env python3
"""Field constant for the account-selection pull (HM-606).

`Step 1 — Select the account` in SKILL.md is prose-only (it drives the model's own
`search_search` call directly; there is no findings assembler to import a
constant into) — this module exists purely to bind that documented pull to a
named code constant, per `_shared/tests` / `skills/google-ads/tests/
test_gaql_schema.py`, which asserts every field here is selectable on the
`customer` resource per the recorded GAQL schema fixture.

No behavior depends on importing this module; SKILL.md and the hub's
SKILL.md both name `CUSTOMER_FIELDS` as the authoritative field list for the
one-time-per-account `customer` resource query used to list/label accessible
customers and skip manager accounts.
"""
from __future__ import annotations

CUSTOMER_FIELDS = (
    "customer.id",
    "customer.descriptive_name",
    "customer.manager",
    "customer.currency_code",
    "customer.time_zone",
)
