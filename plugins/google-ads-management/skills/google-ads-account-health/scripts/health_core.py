#!/usr/bin/env python3
"""Account-health checks — model / single source of truth (stdlib only).

Five heterogeneous, different-grain red-flag checks, modeled as PER-CHECK
SCORED ROWS in one flat list: `check` + entity ref + nullable metric columns
+ `flags` + `pre_score` + `status`. No single wide interactive explorer is
forced — a wide table over five unrelated entity grains reads poorly (see
`references/account-health-filter.md`).

The findings-JSON input contract is documented authoritatively in
`references/account-health-filter.md` (do not duplicate the schema here).

Checks (grain -> what fires it):
  sprawl                 ad_group  -> keyword_count >= min AND ad_group_ctr < max
  no_negatives            campaign -> negative_count <= max (Search only)
  automation_no_data      campaign -> bidding is automated AND conversions_30d < min
  naming                  campaign -> campaign.name fails the naming regex (status=config)
  pmax_cannibalization     campaign -> the campaign is PMax AND the account also runs
                                       an enabled brand Search campaign (status=manual —
                                       the read-only API cannot confirm whether an
                                       account-level negative-keyword/brand-exclusion
                                       list is attached to the PMax campaign)

Every row's `flags` + `pre_score` come from `_shared/analytics.signals` and
`_shared/analytics.pre_score` (HM-532) — the same kernel-mirrorable primitives
every other skill uses, run once across the WHOLE mixed-grain row list: fields
that don't apply to a check are `None` on that row, and `signals()` treats a
missing operand as "no signal" (the rule simply never fires for that row), so
one declarative rule set safely spans all five checks.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import analytics  # noqa: E402  (_shared, on sys.path via the builders/tests)

CHECKS = ("sprawl", "no_negatives", "automation_no_data", "naming", "pmax_cannibalization")

CHECK_LABELS = {
    "sprawl": "Ad-group sprawl",
    "no_negatives": "No campaign negatives",
    "automation_no_data": "Automation without data",
    "naming": "Naming inconsistency",
    "pmax_cannibalization": "PMax brand cannibalization",
}

# Fixed per-check severity (a domain-expert tier, not derived from magnitude —
# these are structural/binary checks across incomparable entity grains, so
# ranking severity BETWEEN checks by a raw score would be arbitrary; WITHIN
# the "top structural fixes" list, pre_score still orders same-check rows).
CHECK_SEVERITY = {
    "automation_no_data": "Critical",
    "sprawl": "High",
    "no_negatives": "High",
    "pmax_cannibalization": "High",
    "naming": "Medium",
}

CHECK_ENTITY_TYPE = {
    "sprawl": "ad_group",
    "no_negatives": "campaign",
    "automation_no_data": "campaign",
    "naming": "campaign",
    "pmax_cannibalization": "campaign",
}

# status ∈ scored (fully queryable + deterministic) / config (deterministic
# but runs against an UNCONFIRMED default, e.g. the naming regex) / manual
# (the read-only API cannot supply the fact at all — needs a human to confirm
# in the UI). No-row-loss + honest status hold regardless of which one a row
# carries (project hard rules).
CHECK_STATUS = {
    "sprawl": "scored",
    "no_negatives": "scored",
    "automation_no_data": "scored",
    "naming": "config",
    "pmax_cannibalization": "manual",
}

# The sub-signal flags each check requires to be considered "flagged" (an AND
# of every listed flag id — signals() only expresses single-field threshold
# rules, so composite AND logic is expressed here, exactly as every other
# skill's core expresses its own classify_row()).
CHECK_FLAG_SETS = {
    "sprawl": ("sprawl_size", "sprawl_low_ctr"),
    "no_negatives": ("no_negatives",),
    "automation_no_data": ("automated_bidding", "low_conversions"),
    "naming": ("name_pattern_fail",),
    "pmax_cannibalization": ("pmax_present", "brand_present"),
}

# Weights feed _shared/analytics.pre_score. A flagged row's pre_score is the
# sum of its check's flag weights (all of them fire together by construction
# of CHECK_FLAG_SETS), so it is effectively a per-check severity constant —
# ranking "top structural fixes" across checks without inventing a magnitude
# comparison the underlying binary/structural facts don't actually support.
WEIGHTS = {
    "sprawl_size": 3.0, "sprawl_low_ctr": 3.0,              # sprawl:      6.0 (High)
    "no_negatives": 7.0,                                     # negatives:   7.0 (High)
    "automated_bidding": 4.0, "low_conversions": 5.0,        # automation:  9.0 (Critical)
    "name_pattern_fail": 3.0,                                # naming:      3.0 (Medium)
    "pmax_present": 3.0, "brand_present": 3.5,               # pmax:        6.5 (High)
}

CHECK_MAX_SCORE = {c: round(sum(WEIGHTS[f] for f in fs), 4) for c, fs in CHECK_FLAG_SETS.items()}

DEFAULT_PARAMS = {
    "sprawl_min_keywords": 20,
    "sprawl_max_ctr": 0.03,
    "negatives_max_count": 0,
    "automation_min_conversions": 30,
    "naming_regex": r"^(Brand|NonBrand)_(US|UK|CA|DE|FR)_(Search|Display|PMax|Video|Demand)_[A-Z]{3,6}_\d{4}$",
    "automated_bidding_types": [
        "MAXIMIZE_CONVERSIONS", "MAXIMIZE_CONVERSION_VALUE",
        "TARGET_CPA", "TARGET_ROAS", "TARGET_IMPRESSION_SHARE",
    ],
    "brand_name_prefix": "brand",
}

RECONCILE_ARRAYS = {
    "ad_groups": ["keyword_count", "impressions", "clicks"],
    "campaigns": ["negative_count", "conversions_30d"],
}


class FindingsError(ValueError):
    """Raised when the findings JSON is missing/invalid."""


def load_findings(path: str) -> dict:
    try:
        data = json.loads(Path(path).read_text())
    except FileNotFoundError as e:
        raise FindingsError(f"findings file not found: {path}") from e
    except json.JSONDecodeError as e:
        raise FindingsError(f"findings file is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise FindingsError("findings JSON must be an object")
    for req in ("ad_groups", "campaigns"):
        if not isinstance(data.get(req), list):
            raise FindingsError(f"findings JSON missing required array '{req}'")
    if (data.get("meta") or {}).get("reconciliation"):
        try:
            import reconcile  # lazy: _shared module, on sys.path via the builders/tests
        except ImportError as e:
            raise FindingsError(
                "findings carry reconciliation totals but the _shared toolkit is not "
                "on sys.path — run via build_health_report.py, or add the plugin's "
                "_shared/ to sys.path before loading") from e
        # negatives raw-universe total: in-scope campaigns' negative_count PLUS
        # orphan_negatives.count (negatives on campaigns absent from the
        # campaigns pull, e.g. REMOVED) must equal the raw negatives pull —
        # this is what catches the post-join array silently losing rows
        # (control totals computed FROM the same lossy array can't).
        orphan = data.get("orphan_negatives") or {}
        campaigns_neg_total = sum(_num(c.get("negative_count")) for c in data.get("campaigns") or [])
        orphan_count = _num(orphan.get("count"))
        try:
            reconcile.verify(data, RECONCILE_ARRAYS,
                             raw_totals={"negatives": campaigns_neg_total + orphan_count})
        except reconcile.ReconciliationError as e:
            raise FindingsError(str(e)) from e
    return data


def resolve_params(raw: dict | None) -> dict:
    p = dict(DEFAULT_PARAMS)
    for k, v in (raw or {}).items():
        if v is not None:
            p[k] = v
    p["automated_bidding_types"] = [str(s).upper() for s in
                                    (p.get("automated_bidding_types")
                                     or DEFAULT_PARAMS["automated_bidding_types"])]
    return p


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _is_brand(name: str, prefix: str) -> bool:
    return str(name or "").strip().casefold().startswith(str(prefix or "").casefold())


def _yn(v) -> str | None:
    """0/1/None -> 'no'/'yes'/None — a friendly display twin of a 0/1 signal
    field, used by the md/xlsx renderers so they never re-derive the mapping."""
    if v is None:
        return None
    return "yes" if v else "no"


def _campaign_liveness(campaigns: list) -> tuple[dict, dict]:
    """Per-campaign liveness map (HM-603). Two-band-honest: this skill has a
    single 30-day window, so `segment_liveness` is called with
    prior_spend_key=None — live / recently_active / dormant are all reachable,
    but the 'spent only in the prior window' path can't fire (no prior window).
    Returns (liveness_by_campaign_id, note_by_campaign_id)."""
    tagged = analytics.segment_liveness(campaigns, status_key="status",
                                        spend_key="cost", prior_spend_key=None)
    live_by, note_by = {}, {}
    for c in tagged:
        cid = str(c.get("campaign_id", ""))
        live_by[cid] = c["liveness"]
        note_by[cid] = _liveness_note(c)
    return live_by, note_by


def _liveness_note(campaign: dict) -> str:
    """Conditional-phrasing seam for recently_active campaigns (the HM-605 hook).
    Empty for live and dormant. Single window -> only the enabled-idle and
    paused-mid-window reasons are derivable."""
    if campaign.get("liveness") != "recently_active":
        return ""
    enabled = str(campaign.get("status") or "").strip().upper() == "ENABLED"
    cur = _num(campaign.get("cost"))
    if not enabled and cur > 0:
        return (f"Paused/removed mid-window after spending {cur:,.2f} in the 30-day "
                "window — confirm intent before acting.")
    return "Enabled but no spend in the 30-day window — confirm it should be running before acting."


def build_rows(ad_groups: list, campaigns: list, params: dict) -> list:
    """Every ad_group -> 1 sprawl row; every campaign -> 3 rows (no_negatives,
    automation_no_data, naming); every PMax campaign -> 1 pmax row.
    No-row-loss: every input array element is represented (nothing dropped).
    Every row carries a `liveness` band (HM-603): campaign-grain rows use their
    own campaign's liveness; ad-group sprawl rows inherit their parent campaign's
    liveness (a dead campaign's ad groups are dead too). A row whose campaign is
    absent from the campaigns pull defaults to recently_active (kept in scope,
    never silently suppressed)."""
    live_by, note_by = _campaign_liveness(campaigns)

    def _tag(row):
        cid = str(row.get("campaign_id", ""))
        row["liveness"] = live_by.get(cid, "recently_active")
        row["liveness_note"] = note_by.get(cid, "")
        return row

    rows: list = []
    try:
        regex = re.compile(params["naming_regex"])
    except re.error as e:
        raise FindingsError(
            f"params.naming_regex is not a valid regular expression: {params['naming_regex']!r} "
            f"({e}) — fix it in the findings JSON or fall back to DEFAULT_PARAMS['naming_regex']"
        ) from e
    automated = set(params["automated_bidding_types"])
    brand_prefix = params["brand_name_prefix"]

    # account-wide fact used by every pmax_cannibalization row: does an
    # ENABLED brand Search campaign exist anywhere in the account?
    brand_present_account = any(
        _is_brand(c.get("campaign", ""), brand_prefix)
        and str(c.get("channel_type", "")).upper() == "SEARCH"
        and str(c.get("status", "")).upper() == "ENABLED"
        for c in campaigns)

    for ag in ad_groups:
        impressions = _num(ag.get("impressions"))
        clicks = _num(ag.get("clicks"))
        ctr = (clicks / impressions) if impressions else 0.0
        rows.append({
            "check": "sprawl", "check_label": CHECK_LABELS["sprawl"],
            "entity_type": "ad_group",
            "entity_id": str(ag.get("ad_group_id", "")),
            "entity_name": ag.get("ad_group", ""),
            "campaign_id": str(ag.get("campaign_id", "")),
            "campaign_name": ag.get("campaign", ""),
            "keyword_count": _num(ag.get("keyword_count")),
            "ad_group_ctr": round(ctr, 6),
            "negative_count": None, "bidding_strategy_type": None,
            "automated_bidding": None, "automated_bidding_label": None,
            "conversions_30d": None,
            "name_pattern_ok": None, "name_pattern_ok_label": None,
            "pmax_present": None, "pmax_present_label": None,
            "brand_present": None, "brand_present_label": None,
            "has_brand_exclusion": None, "has_brand_exclusion_label": None,
            "status": CHECK_STATUS["sprawl"],
        })

    for c in campaigns:
        cid = str(c.get("campaign_id", ""))
        cname = c.get("campaign", "")
        bst = str(c.get("bidding_strategy_type", "") or "")
        is_automated = 1 if bst.upper() in automated else 0
        name_ok = 1 if regex.match(str(cname or "")) else 0

        base = {
            "entity_type": "campaign", "entity_id": cid, "entity_name": cname,
            "campaign_id": cid, "campaign_name": cname,
            "keyword_count": None, "ad_group_ctr": None,
        }

        # no_negatives is Search-only (campaign-level negatives are a Search
        # hygiene check; PMax/Display/Video/Demand Gen don't use them the
        # same way) — matches the pre-advisor SKILL.md's original scope.
        if str(c.get("channel_type", "")).upper() == "SEARCH":
            rows.append({
                **base, "check": "no_negatives", "check_label": CHECK_LABELS["no_negatives"],
                "negative_count": _num(c.get("negative_count")),
                "bidding_strategy_type": None, "automated_bidding": None, "automated_bidding_label": None,
                "conversions_30d": None, "name_pattern_ok": None, "name_pattern_ok_label": None,
                "pmax_present": None, "pmax_present_label": None,
                "brand_present": None, "brand_present_label": None,
                "has_brand_exclusion": None, "has_brand_exclusion_label": None,
                "status": CHECK_STATUS["no_negatives"],
            })

        rows.append({
            **base, "check": "automation_no_data", "check_label": CHECK_LABELS["automation_no_data"],
            "negative_count": None,
            "bidding_strategy_type": bst or None, "automated_bidding": is_automated,
            "automated_bidding_label": _yn(is_automated),
            "conversions_30d": _num(c.get("conversions_30d")),
            "name_pattern_ok": None, "name_pattern_ok_label": None,
            "pmax_present": None, "pmax_present_label": None,
            "brand_present": None, "brand_present_label": None,
            "has_brand_exclusion": None, "has_brand_exclusion_label": None,
            "status": CHECK_STATUS["automation_no_data"],
        })

        rows.append({
            **base, "check": "naming", "check_label": CHECK_LABELS["naming"],
            "negative_count": None, "bidding_strategy_type": None, "automated_bidding": None,
            "automated_bidding_label": None,
            "conversions_30d": None, "name_pattern_ok": name_ok, "name_pattern_ok_label": _yn(name_ok),
            "pmax_present": None, "pmax_present_label": None,
            "brand_present": None, "brand_present_label": None,
            "has_brand_exclusion": None, "has_brand_exclusion_label": None,
            "status": CHECK_STATUS["naming"],
        })

        if str(c.get("channel_type", "")).upper() == "PERFORMANCE_MAX":
            bp = 1 if brand_present_account else 0
            rows.append({
                **base, "check": "pmax_cannibalization",
                "check_label": CHECK_LABELS["pmax_cannibalization"],
                "negative_count": None, "bidding_strategy_type": None, "automated_bidding": None,
                "automated_bidding_label": None,
                "conversions_30d": None, "name_pattern_ok": None, "name_pattern_ok_label": None,
                "pmax_present": 1, "pmax_present_label": _yn(1),
                "brand_present": bp, "brand_present_label": _yn(bp),
                "has_brand_exclusion": None, "has_brand_exclusion_label": None,
                # never confirmable via the read-only API — always None/"unconfirmed"
                "status": CHECK_STATUS["pmax_cannibalization"],
            })
    for r in rows:
        _tag(r)
    return rows


def _build_rules(params: dict) -> list:
    return [
        {"id": "sprawl_size", "key": "keyword_count", "op": "ge", "value": params["sprawl_min_keywords"]},
        {"id": "sprawl_low_ctr", "key": "ad_group_ctr", "op": "lt", "value": params["sprawl_max_ctr"]},
        {"id": "no_negatives", "key": "negative_count", "op": "le", "value": params["negatives_max_count"]},
        {"id": "automated_bidding", "key": "automated_bidding", "op": "eq", "value": 1},
        {"id": "low_conversions", "key": "conversions_30d", "op": "lt",
         "value": params["automation_min_conversions"]},
        {"id": "name_pattern_fail", "key": "name_pattern_ok", "op": "eq", "value": 0},
        {"id": "pmax_present", "key": "pmax_present", "op": "eq", "value": 1},
        {"id": "brand_present", "key": "brand_present", "op": "eq", "value": 1},
    ]


def score_rows(rows: list, params: dict) -> list:
    """Attach flags/is_flagged/pre_score/severity to every row (in place, on
    copies). Uses `_shared/analytics.signals` + `.pre_score` verbatim."""
    rules = _build_rules(params)
    flag_lists = analytics.signals(rows, rules)
    out = []
    for row, flags in zip(rows, flag_lists):
        r = dict(row)
        r["flags"] = flags
        # Liveness gate (HM-603): a dormant campaign (not ENABLED, zero 30d spend)
        # — and its ad groups — never trip a check (this is what stops the zombie
        # "revert to Manual CPC" rows on long-dead campaigns). The row survives,
        # tagged liveness="dormant", but carries no flags/severity/pre-score.
        dormant = r.get("liveness") == "dormant"
        need = set(CHECK_FLAG_SETS[r["check"]])
        r["is_flagged"] = (not dormant) and need <= set(flags)
        r["pre_score"] = analytics.pre_score(r, WEIGHTS) if r["is_flagged"] else 0.0
        r["severity"] = CHECK_SEVERITY[r["check"]] if r["is_flagged"] else None
        out.append(r)
    return out


def summarize(rows: list) -> dict:
    by_check = {c: {"universe": 0, "flagged": 0} for c in CHECKS}
    for r in rows:
        by_check[r["check"]]["universe"] += 1
        if r["is_flagged"]:
            by_check[r["check"]]["flagged"] += 1
    total_flagged = sum(v["flagged"] for v in by_check.values())
    by_severity = {"Critical": 0, "High": 0, "Medium": 0}
    for r in rows:
        if r["is_flagged"]:
            by_severity[r["severity"]] += 1
    by_liveness = {"live": 0, "recently_active": 0, "dormant": 0}
    for r in rows:
        by_liveness[r.get("liveness", "recently_active")] = \
            by_liveness.get(r.get("liveness", "recently_active"), 0) + 1
    return {
        "universe": len(rows),
        "total_flagged": total_flagged,
        "by_check": by_check,
        "by_severity": by_severity,
        # Liveness split (HM-603): dormant rows are kept + tagged but excluded
        # from the scored/severity universe (never flagged).
        "by_liveness": by_liveness,
        "structural_score": round(sum(r["pre_score"] for r in rows), 4),
    }


def top_fixes(rows: list, top_n: int = 25) -> list:
    """Flagged rows ranked by pre_score desc (ties: fixed severity order, then
    entity name) — the advisor's 'top structural fixes' list."""
    order = {"Critical": 0, "High": 1, "Medium": 2}
    flagged = [r for r in rows if r["is_flagged"]]
    flagged.sort(key=lambda r: (-r["pre_score"], order.get(r["severity"], 9), r["entity_name"]))
    return flagged[:top_n]


def provenance(findings: dict, params: dict) -> dict:
    meta = findings.get("meta") or {}
    return {
        "client_name": meta.get("client_name", ""),
        "account_id": meta.get("account_id", ""),
        "currency": meta.get("currency", ""),
        "window_30d": meta.get("window_30d", ""),
        "generated": meta.get("generated", ""),
        "source": meta.get("source", "mcp"),
        "params": dict(params),
    }


def orphan_negatives_summary(findings: dict) -> dict:
    """Negatives that reference a campaign id absent from the campaigns pull
    (e.g. REMOVED campaigns) — never dropped, always surfaced with an honest
    `status` (no-row-loss). Empty/zero when the findings predate this field
    (legacy fixtures) or the CSV path (no separate negatives pull to orphan
    against)."""
    orphan = findings.get("orphan_negatives") or {}
    return {
        "count": int(_num(orphan.get("count"))),
        "campaign_ids": list(orphan.get("campaign_ids") or []),
        "status": orphan.get("status", "out_of_scope"),
    }


def _build_meta(findings: dict, params: dict) -> dict:
    """meta pass-through + the naming_regex auto-stamp (HM-604): unless the
    client explicitly supplied params.naming_regex in the findings JSON, every
    campaign is being judged against DEFAULT_PARAMS['naming_regex'] — an
    unconfirmed convention, not something the account owner agreed to — so it
    gets an honest basis=model_default entry."""
    meta = dict(findings.get("meta") or {})
    supplied = (findings.get("params") or {}).get("naming_regex")
    if supplied is None:
        entries = [a for a in (meta.get("assumptions") or []) if a.get("param") != "naming_regex"]
        entries.append({"param": "naming_regex", "value": params["naming_regex"], "basis": "model_default",
                        "note": "no client-confirmed naming convention supplied — flagging campaigns "
                                "against the tool's default regex (DEFAULT_PARAMS['naming_regex'])"})
        meta["assumptions"] = entries
    return meta


def compute_model(findings: dict) -> dict:
    """Assemble the full model at the resolved params. JSON-serializable. This
    is the single source of truth; presentation (md/xlsx) lives in
    health_spec / health_xlsx_spec."""
    params = resolve_params(findings.get("params"))
    raw_rows = build_rows(findings["ad_groups"], findings["campaigns"], params)
    rows = score_rows(raw_rows, params)
    return {
        "provenance": provenance(findings, params),
        "params": params,
        "rows": rows,
        "summary": summarize(rows),
        "top_fixes": top_fixes(rows),
        "checks": CHECKS,
        "check_labels": CHECK_LABELS,
        "check_severity": CHECK_SEVERITY,
        "check_max_score": CHECK_MAX_SCORE,
        "orphan_negatives": orphan_negatives_summary(findings),
        # Pass-through so every renderer sees the assembler's meta.assumptions
        # (HM-604) and meta.source verbatim, plus the auto-stamped naming default.
        "meta": _build_meta(findings, params),
    }
