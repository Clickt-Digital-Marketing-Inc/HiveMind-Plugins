#!/usr/bin/env python3
"""Make GAQL a tested asset — assert every skill's declared field list is
selectable on the resource its SKILL.md documents (HM-606).

Discovers each skill's `*_FIELDS` constant (imported straight from its
scripts/ module — the same object `require_fields=` uses at runtime, so this
can never silently drift from the code) and asserts every dotted field name
in it appears in `_shared/tests/fixtures/gaql_schema_2026-07.json`'s
`selectable` list for the correct resource.

**Resource routing.** A field's own dotted prefix names its resource
(`campaign.id` -> `campaign`, `ad_group_criterion.keyword.text` ->
`ad_group_criterion`, `campaign_budget.amount_micros` -> `campaign_budget`)
independent of which resource the GAQL `FROM` clause names — GAQL freely
selects fields from joined resources (e.g. `FROM keyword_view SELECT
ad_group_criterion.keyword.text`, or `FROM campaign SELECT
campaign_budget.amount_micros`). The two virtual namespaces `metrics.*` and
`segments.*` are the one exception: those field lists are scoped per `FROM`
resource, so they're checked against the constant's DECLARED resource (the
manifest's `resource` column) instead of a literal "metrics" resource.

**Limitation (read before trusting a green run):** this validates
field-*selectability* only — that the API version accepted the field name for
the given resource. It does NOT validate full query semantics: WHERE/ORDER BY
compatibility, `segments.date` requirements on metrics queries, resource-join
legality (whether two resources can actually appear together in one query),
or account-level feature gating. A field can pass this test and still make a
live query fail for one of those reasons.

Run: python3 tests/test_gaql_schema.py
Exit 0 = all pass, 1 = a failure.
"""
from __future__ import annotations

import datetime
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # .../skills/google-ads/tests
SKILLS_DIR = HERE.parents[1]                     # .../skills
PLUGIN_ROOT = HERE.parents[2]                    # .../google-ads-management
FIXTURE = PLUGIN_ROOT / "_shared" / "tests" / "fixtures" / "gaql_schema_2026-07.json"

_failures: list[str] = []
_module_counter = 0


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        _failures.append(name)


def _load_module(path: Path):
    """Import a script module by file path under a unique name so same-named
    modules across sibling skills (every skill has its own assemble_findings.py)
    never collide in sys.modules."""
    global _module_counter
    _module_counter += 1
    name = f"_gaql_schema_check_{_module_counter}_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    # Some assemble_findings.py modules import sibling modules (e.g. a
    # *_core.py owning the reconcile contract) via `sys.path.insert(0,
    # str(HERE))` at module scope relative to their own __file__ — that
    # works unmodified since we pass the real file path.
    spec.loader.exec_module(mod)
    return mod


def _fields_of(constant) -> list[str]:
    """Normalize a `*_FIELDS` constant to a flat list of dotted field names.
    Most are flat tuples of strings; performance-reporting's IS_FIELDS is a
    tuple of (dotted_field, short_alias) pairs."""
    out = []
    for item in constant:
        if isinstance(item, (tuple, list)):
            out.append(item[0])
        else:
            out.append(item)
    return out


def _resource_for(field: str, declared_resource: str) -> str:
    prefix = field.split(".", 1)[0]
    if prefix in ("metrics", "segments"):
        return declared_resource
    return prefix


# ---------------------------------------------------------------------------
# Manifest: every skill's declared GAQL field-list constant and the resource
# its SKILL.md documents it against. Entries with no findings-JSON consumer
# (prose-only "Pull the data" bullets) are marked accordingly in a comment —
# they're still asserted, since the point is to catch drift in the documented
# field list itself, consumed or not.
# ---------------------------------------------------------------------------
MANIFEST = [
    # (skill_dir, script_relpath, constant_name, resource)
    ("google-ads-foundation", "scripts/account_fields.py", "CUSTOMER_FIELDS", "customer"),

    ("google-ads-account-health", "scripts/assemble_findings.py", "KEYWORDS_FIELDS", "ad_group_criterion"),
    ("google-ads-account-health", "scripts/assemble_findings.py", "ADGROUP_PERF_FIELDS", "ad_group"),
    ("google-ads-account-health", "scripts/assemble_findings.py", "CAMPAIGNS_FIELDS", "campaign"),
    ("google-ads-account-health", "scripts/assemble_findings.py", "NEGATIVES_FIELDS", "campaign_criterion"),

    ("google-ads-audience-targeting", "scripts/assemble_findings.py", "CRITERIA_FIELDS", "ad_group_criterion"),
    ("google-ads-audience-targeting", "scripts/assemble_findings.py", "METRICS_FIELDS", "ad_group_audience_view"),
    ("google-ads-audience-targeting", "scripts/assemble_findings.py", "USERLIST_FIELDS", "user_list"),
    # prose-only pull ("Campaign types") — no findings-JSON consumer
    ("google-ads-audience-targeting", "scripts/assemble_findings.py", "CAMPAIGN_TYPE_FIELDS", "campaign"),

    ("google-ads-bidding-strategy", "scripts/assemble_findings.py", "CAMPAIGN_FIELDS", "campaign"),

    ("google-ads-budget-pacing", "scripts/assemble_findings.py", "PERF_FIELDS", "campaign"),
    ("google-ads-budget-pacing", "scripts/assemble_findings.py", "BUDGET_FIELDS", "campaign"),
    ("google-ads-budget-pacing", "scripts/assemble_findings.py", "MTD_FIELDS", "campaign"),

    ("google-ads-competitive-analysis", "scripts/assemble_findings.py", "CAMPAIGN_FIELDS", "campaign"),

    ("google-ads-conversions-tracking", "scripts/assemble_findings.py", "CONFIG_FIELDS", "conversion_action"),
    ("google-ads-conversions-tracking", "scripts/assemble_findings.py", "CAMPAIGN_FIELDS", "campaign"),

    ("google-ads-keywords-search-terms", "scripts/assemble_findings.py", "TERMS_90D_FIELDS", "search_term_view"),
    ("google-ads-keywords-search-terms", "scripts/assemble_findings.py", "TERMS_30D_FIELDS", "search_term_view"),
    ("google-ads-keywords-search-terms", "scripts/assemble_findings.py", "BENCH_FIELDS", "campaign"),
    # prose-only pulls (basic SQR audit / monthly keyword analysis) — no findings-JSON consumer
    ("google-ads-keywords-search-terms", "scripts/assemble_findings.py", "NEGATIVES_FIELDS", "campaign_criterion"),
    ("google-ads-keywords-search-terms", "scripts/assemble_findings.py", "KEYWORD_QS_FIELDS", "keyword_view"),

    ("google-ads-performance-reporting", "scripts/assemble_findings.py", "PERIOD_FIELDS", "campaign"),
    ("google-ads-performance-reporting", "scripts/assemble_findings.py", "PRIOR_FIELDS", "campaign"),
    ("google-ads-performance-reporting", "scripts/assemble_findings.py", "IS_FIELDS", "campaign"),

    ("google-ads-pmax-campaigns", "scripts/assemble_findings.py", "WINDOW_FIELDS", "campaign"),
    ("google-ads-pmax-campaigns", "scripts/assemble_findings.py", "ASSET_GROUP_FIELDS", "asset_group"),

    ("google-ads-pmax-listing-groups", "scripts/assemble_findings.py", "LG_FIELDS", "asset_group_product_group_view"),
    ("google-ads-pmax-listing-groups", "scripts/assemble_findings.py", "LABEL_FIELDS", "asset_group_listing_group_filter"),
    ("google-ads-pmax-listing-groups", "scripts/assemble_findings.py", "BENCH_FIELDS", "campaign"),
    ("google-ads-pmax-listing-groups", "scripts/assemble_findings.py", "PRODUCT_FIELDS", "shopping_performance_view"),

    ("google-ads-products", "scripts/assemble_findings.py", "P30_FIELDS", "shopping_performance_view"),
    ("google-ads-products", "scripts/assemble_findings.py", "P14_FIELDS", "shopping_performance_view"),
    ("google-ads-products", "scripts/assemble_findings.py", "PREV14_FIELDS", "shopping_performance_view"),

    ("google-ads-quality-score", "scripts/assemble_findings.py", "KEYWORDS_FIELDS", "keyword_view"),
    # prose-only pulls (search-terms low-CTR drag / RSA ad-relevance matrix) — no findings-JSON consumer
    ("google-ads-quality-score", "scripts/assemble_findings.py", "SEARCH_TERMS_FIELDS", "search_term_view"),
    ("google-ads-quality-score", "scripts/assemble_findings.py", "AD_ASSETS_FIELDS", "ad_group_ad"),
]


def load_fixture() -> dict:
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


def check_fixture_freshness(fixture: dict):
    recorded = fixture.get("recorded")
    check("fixture has a 'recorded' date", bool(recorded), f"got {recorded!r}")
    if not recorded:
        return
    try:
        recorded_date = datetime.date.fromisoformat(recorded)
    except ValueError:
        check("recorded date is ISO 'YYYY-MM-DD'", False, f"got {recorded!r}")
        return
    age_days = (datetime.date.today() - recorded_date).days
    if age_days > 183:
        print(f"  WARN  fixture recorded {recorded} is {age_days} days old (> 6 months) — "
              "refresh per _shared/README.md before trusting a MISSING verdict")


def run() -> int:
    fixture = load_fixture()
    check_fixture_freshness(fixture)
    resources = fixture.get("resources", {})

    for skill_dir, script_rel, const_name, declared_resource in MANIFEST:
        script_path = SKILLS_DIR / skill_dir / script_rel
        label = f"{skill_dir}/{script_rel}::{const_name}"
        if not script_path.is_file():
            check(f"{label} — script exists", False, str(script_path))
            continue
        try:
            mod = _load_module(script_path)
        except Exception as e:  # pragma: no cover - surfaced as a failure, not a crash
            check(f"{label} — module imports", False, repr(e))
            continue
        constant = getattr(mod, const_name, None)
        if constant is None:
            check(f"{label} — constant exists", False, "not found in module")
            continue
        fields = _fields_of(constant)
        check(f"{label} — non-empty", len(fields) > 0, "constant is empty")

        for field in fields:
            target_resource = _resource_for(field, declared_resource)
            target = resources.get(target_resource)
            if target is None:
                check(f"{label} — {field} (resource '{target_resource}' recorded)", False,
                      f"resource '{target_resource}' is not in the fixture — refresh it "
                      "(see _shared/README.md)")
                continue
            ok = field in target.get("selectable", [])
            check(f"{label} — {field} selectable on {target_resource}", ok)

    if _failures:
        print("FAIL — %d problem(s):" % len(_failures))
        for f in _failures:
            print("  - " + f)
        return 1
    print("OK — %d field constants across %d skills validated against %s"
          % (len(MANIFEST), len({m[0] for m in MANIFEST}), FIXTURE.name))
    return 0


if __name__ == "__main__":
    sys.exit(run())
