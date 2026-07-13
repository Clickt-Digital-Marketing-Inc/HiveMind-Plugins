#!/usr/bin/env python3
# Copyright (c) 2026 Clickt Digital Marketing Inc. All rights reserved.
"""Deterministic pre-scorer — machine-scores the audit's mechanical checks.

Every framework check whose logic is a pure data comparison gets its
result/observed computed here, in Python, from the same raw-MCP or manual-CSV
rows the Concentration report ingests. `merge_into_findings` then enforces
those results over the model-authored findings JSON at build time, logging any
disagreement (a built-in drift detector). Checks whose required fields are
absent from the inputs are *skipped* — they stay LLM-judged — so both input
paths degrade gracefully.

Thresholds are verbatim from `references/benchmarks.md`; check metadata
(name/verify/severity/tab) verbatim from `references/audit-framework.md`.
v1 uses the Lead Gen / Ecommerce bands, which are identical for every
machine-scored check; the B2B column is not reachable (business_model is a
binary enum) and is documented out of scope.

Stdlib only. All numbers here come from files parsed deterministically —
nothing in this module reads model-authored text except the findings JSON it
corrects.
"""
from __future__ import annotations

import copy
import re

from audit_model import ANALYSIS_TABS

_TAB_TITLE = dict(ANALYSIS_TABS)
_TAB_ORDER = [t for t, _ in ANALYSIS_TABS]
_TAB_BY_PREFIX = {
    "AS": "03_Account_Structure", "PR": "04_Performance_Review",
    "KW": "05_Keyword_Strategy", "AD": "06_Ad_Creatives_Assets",
    "LP": "07_Landing_Pages", "BB": "08_Budget_Bidding",
    "TR": "09_Tracking_Measurement", "AU": "10_Audiences",
    "AT": "11_Automation_Recommendations",
}

# Framework metadata for machine-scored (A) and evidence-only (B) checks.
CHECK_RULES = {
    "PR-01": {"name": "CTR at/above benchmark", "severity": "Medium",
              "verify": "Account Search CTR within the vertical benchmark range"},
    "PR-04": {"name": "Search Impression Share healthy", "severity": "Medium",
              "verify": "Search IS above benchmark (>65%)"},
    "PR-05": {"name": "Lost IS (Budget) controlled", "severity": "High",
              "verify": "Search lost IS (budget) < 10%"},
    "PR-06": {"name": "Lost IS (Rank) controlled", "severity": "Medium",
              "verify": "Search lost IS (rank) < 20%"},
    "KW-02": {"name": "Wasted spend controlled", "severity": "High",
              "verify": "<5% of spend on >$10 / 0-conversion search terms"},
    "KW-03": {"name": "Legacy BMM reviewed", "severity": "Medium",
              "verify": "BROAD + Manual CPC keywords examined, not left unmanaged"},
    "KW-05": {"name": "No duplicate keywords", "severity": "Medium",
              "verify": "No duplicate keyword+match across ad groups"},
    "AS-03": {"name": "No keyword cannibalization", "severity": "Medium",
              "verify": "Same keyword+match not duplicated across campaigns"},
    "BB-02": {"name": "No deprecated eCPC", "severity": "Medium",
              "verify": "Enhanced CPC not in use"},
    # Category B (evidence only — result stays with the auditor)
    "PR-02": {"name": "CPA within 20% of target", "severity": "High", "verify": ""},
    "PR-03": {"name": "ROAS at/above target", "severity": "High", "verify": ""},
    "BB-01": {"name": "Bidding strategy fits goal", "severity": "High", "verify": ""},
    "KW-04": {"name": "Match-type balance", "severity": "Medium", "verify": ""},
}


# ── canonicalizers (unify raw-API enums and UI display strings) ─────────────

def canon_enum(v) -> str:
    """'Phrase match (close variant)' -> 'PHRASE_MATCH_CLOSE_VARIANT';
    'BELOW_AVERAGE' == canon of 'Below average'."""
    return re.sub(r"_+", "_", re.sub(r"[^A-Z0-9]+", "_", str(v or "").upper())).strip("_")


def canon_match(v) -> str | None:
    e = canon_enum(v)
    for m in ("BROAD", "PHRASE", "EXACT"):
        if m in e:
            return m
    return None


def canon_channel(v) -> str:
    return canon_enum(v)


def canon_strategy(v) -> str:
    e = canon_enum(v)
    if "ENHANCED" in e:
        return "ENHANCED_CPC"
    if "MANUAL" in e:
        return "MANUAL_CPC"
    return e


def canon_kw_text(v) -> str:
    """Strip the UI's match-type decorations ('\"quoted\"' phrase, '[bracketed]'
    exact), casefold, collapse whitespace — so UI and API keyword text agree."""
    s = str(v or "").strip().strip('"\'').strip()
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1]
    return re.sub(r"\s+", " ", s).casefold().strip()


def _f(row, key):
    v = row.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def wavg(pairs) -> float | None:
    """[(weight, value)] -> sum(w*v)/sum(w); None when total weight <= 0."""
    tw = sum(w for w, _ in pairs)
    if tw <= 0:
        return None
    return sum(w * v for w, v in pairs) / tw


# ── rule engine ─────────────────────────────────────────────────────────────

def _band(value, lo, hi, higher_is_better):
    """Threshold banding: (lo, hi) delimit FLAG territory."""
    if higher_is_better:
        return "PASS" if value >= hi else ("FLAG" if value >= lo else "FAIL")
    return "PASS" if value < lo else ("FLAG" if value <= hi else "FAIL")


def _search_rows(campaign_rows):
    return [r for r in campaign_rows
            if canon_channel(r.get("campaign.advertising_channel_type")) == "SEARCH"]


def _wtd_is(rows, key):
    """Cost-weighted mean of a fraction field over rows that carry it -> %-points."""
    pairs = [(r.get("metrics.cost_micros", 0) / 1e6, _f(r, key) * 100.0)
             for r in rows if _f(r, key) is not None]
    v = wavg(pairs)
    n = len(pairs)
    spend = sum(w for w, _ in pairs)
    return v, n, spend


def _agg_terms(search_term_rows):
    """Aggregate spend/conv per term; track excluded status when present."""
    agg: dict[str, list] = {}
    for r in search_term_rows:
        name = r.get("search_term_view.search_term")
        if name is None:
            continue
        e = agg.setdefault(str(name), [0.0, 0.0, False])
        e[0] += r.get("metrics.cost_micros", 0) / 1e6
        e[1] += float(r.get("metrics.conversions") or 0)
        if "EXCLUDED" in canon_enum(r.get("search_term_view.status")):
            e[2] = True
    return agg


def _dupe_count(keyword_rows, scope_key):
    """Distinct (text, match) identities appearing in >1 scope value."""
    seen: dict[tuple, set] = {}
    for r in keyword_rows:
        text = r.get("ad_group_criterion.keyword.text")
        scope = r.get(scope_key)
        if text is None or scope is None:
            continue
        ident = (canon_kw_text(text), canon_match(r.get("ad_group_criterion.keyword.match_type")))
        seen.setdefault(ident, set()).add(str(scope))
    return sum(1 for scopes in seen.values() if len(scopes) > 1)


def compute_prescore(campaign_rows=None, keyword_rows=None, search_term_rows=None,
                     *, business_model: str = "", targets: dict | None = None) -> dict | None:
    """Machine-score the mechanical checks from raw/CSV entity rows.

    Returns the prescore block, or None when no rows are supplied at all."""
    if campaign_rows is None and keyword_rows is None and search_term_rows is None:
        return None
    targets = targets or {}
    checks: dict[str, dict] = {}
    evidence: dict[str, dict] = {}
    kpis: list[dict] = []
    skipped: list[dict] = []
    notes: list[str] = []

    bm = business_model if business_model in ("Lead Gen", "Ecommerce") else "Lead Gen"
    if business_model not in ("Lead Gen", "Ecommerce"):
        notes.append("business_model absent/unknown — Lead Gen thresholds used "
                     "(identical to Ecommerce for all machine-scored checks).")

    def skip(cid, reason):
        skipped.append({"id": cid, "reason": reason})

    # ---- campaign-level rules -------------------------------------------------
    search = _search_rows(campaign_rows) if campaign_rows else []
    approx_notes = []
    if campaign_rows:
        for r in campaign_rows:
            for a in r.get("_approx", []):
                approx_notes.append(a)
    if approx_notes:
        notes.append("Some UI values were bounds (e.g. '< 10%'); boundary values "
                     f"used for: {'; '.join(sorted(set(approx_notes)))}.")

    if campaign_rows is None:
        for cid in ("PR-01", "PR-04", "PR-05", "PR-06", "BB-02"):
            skip(cid, "no campaigns input provided")
    else:
        # PR-01 — account Search CTR (totals-based: the true blended CTR)
        impr = sum(_f(r, "metrics.impressions") or 0 for r in search
                   if _f(r, "metrics.impressions") is not None)
        clicks = sum(_f(r, "metrics.clicks") or 0 for r in search
                     if _f(r, "metrics.clicks") is not None)
        if not search:
            skip("PR-01", "no Search campaigns in the input")
            skip("PR-04", "no Search campaigns in the input")
            skip("PR-05", "no Search campaigns in the input")
            skip("PR-06", "no Search campaigns in the input")
        else:
            if impr <= 0:
                skip("PR-01", "impressions/clicks not present in the campaigns input")
                ctr = None
            else:
                ctr = clicks / impr * 100.0
                checks["PR-01"] = {
                    "result": _band(ctr, 3.0, 4.0, True),
                    "observed": f"Search CTR {ctr:.1f}% ({int(clicks):,} clicks / "
                                f"{int(impr):,} impr; benchmark 4%+)"}
            for cid, key, lo, hi, better, label in (
                    ("PR-04", "metrics.search_impression_share", 48.75, 65.0, True,
                     "Search impression share"),
                    ("PR-05", "metrics.search_budget_lost_impression_share", 10.0, 20.0, False,
                     "Lost IS (Budget)"),
                    ("PR-06", "metrics.search_rank_lost_impression_share", 20.0, 25.0, False,
                     "Lost IS (Rank)")):
                v, n, spend = _wtd_is(search, key)
                if v is None:
                    skip(cid, f"{key} not present in the campaigns input — "
                              "re-pull per gaql-queries.md Step 2 / re-export with the IS columns")
                    continue
                checks[cid] = {
                    "result": _band(v, lo, hi, better),
                    "observed": f"{label} {v:.1f}% cost-weighted across {n} Search "
                                f"campaigns (${spend:,.2f} spend)"}
            kpi_specs = [("Search Impr. Share", "PR-04", ">65%"),
                         ("Lost IS (Budget)", "PR-05", "<10%"),
                         ("Lost IS (Rank)", "PR-06", "<20%")]
            for metric, cid, bench in kpi_specs:
                if cid in checks:
                    m = re.search(r"(-?\d+\.\d)% cost-weighted", checks[cid]["observed"])
                    if m:
                        kpis.append({"metric": metric, "value": float(m.group(1)),
                                     "unit": "%", "benchmark": bench,
                                     "flag": checks[cid]["result"],
                                     "notes": "cost-weighted, Search campaigns (machine-scored)"})
            if ctr is not None:
                kpis.append({"metric": "CTR", "value": round(ctr, 1), "unit": "%",
                             "benchmark": "4%+", "flag": checks["PR-01"]["result"],
                             "notes": "Search totals (machine-scored)"})

        # BB-02 — deprecated eCPC
        strat_rows = [r for r in campaign_rows if r.get("campaign.bidding_strategy_type")]
        if not strat_rows:
            skip("BB-02", "campaign.bidding_strategy_type not present — re-pull per "
                          "gaql-queries.md Step 2 / re-export with 'Bid strategy type'")
        else:
            ecpc = [r["campaign.name"] for r in strat_rows
                    if canon_strategy(r["campaign.bidding_strategy_type"]) == "ENHANCED_CPC"]
            checks["BB-02"] = {
                "result": "FAIL" if ecpc else "PASS",
                "observed": (f"{len(ecpc)} campaign(s) on deprecated Enhanced CPC: "
                             f"{', '.join(sorted(ecpc)[:5])}" if ecpc
                             else f"No Enhanced CPC among {len(strat_rows)} campaigns")}
            # BB-01 evidence: spend mix by strategy
            mix: dict[str, float] = {}
            for r in strat_rows:
                mix[canon_strategy(r["campaign.bidding_strategy_type"])] = \
                    mix.get(canon_strategy(r["campaign.bidding_strategy_type"]), 0.0) \
                    + r.get("metrics.cost_micros", 0) / 1e6
            total = sum(mix.values())
            if total > 0:
                parts = [f"{k} {v / total * 100:.0f}%"
                         for k, v in sorted(mix.items(), key=lambda x: -x[1])]
                evidence["BB-01"] = {"observed": "Spend by bid strategy: " + ", ".join(parts)}

        # Blended CPA / ROAS / Avg CPC evidence + KPI rows
        cost = sum(r.get("metrics.cost_micros", 0) / 1e6 for r in campaign_rows)
        conv = sum(float(r.get("metrics.conversions") or 0) for r in campaign_rows)
        convval_rows = [r for r in campaign_rows if _f(r, "metrics.conversions_value") is not None]
        if conv > 0 and cost > 0:
            cpa = cost / conv
            evidence["PR-02"] = {"observed": f"Blended CPA ${cpa:,.2f} "
                                             f"(${cost:,.2f} / {conv:,.1f} conv)"}
            t = targets.get("target_cpa")
            if t:
                t = float(t)
                flag = "PASS" if cpa <= 1.2 * t else ("FLAG" if cpa <= 1.4 * t else "FAIL")
                kpis.append({"metric": "CPA", "value": round(cpa, 2), "unit": "$",
                             "benchmark": f"target ${t:,.2f}", "flag": flag,
                             "notes": f"{(cpa - t) / t * 100:+.0f}% vs target (machine-scored)"})
            else:
                kpis.append({"metric": "CPA", "value": round(cpa, 2), "unit": "$",
                             "benchmark": "client target", "flag": "N/A",
                             "notes": "no target_cpa in meta — judge vs client target"})
        if convval_rows and cost > 0:
            convval = sum(_f(r, "metrics.conversions_value") or 0 for r in convval_rows)
            roas = convval / cost
            evidence["PR-03"] = {"observed": f"ROAS {roas:.2f} "
                                             f"(${convval:,.2f} value / ${cost:,.2f} cost)"}
            t = targets.get("target_roas")
            if t:
                t = float(t)
                flag = "PASS" if roas >= t else ("FLAG" if roas >= 0.75 * t else "FAIL")
                kpis.append({"metric": "ROAS", "value": round(roas, 2), "unit": "x",
                             "benchmark": f"target {t:g}", "flag": flag,
                             "notes": "machine-scored vs target_roas"})
        clicks_all = sum(_f(r, "metrics.clicks") or 0 for r in campaign_rows
                         if _f(r, "metrics.clicks") is not None)
        if clicks_all > 0 and cost > 0:
            kpis.append({"metric": "Avg CPC", "value": round(cost / clicks_all, 2),
                         "unit": "$", "benchmark": "vertical-dependent", "flag": "N/A",
                         "notes": "judge vs account history — no universal benchmark"})

    # ---- search-term rules ----------------------------------------------------
    if search_term_rows is None:
        skip("KW-02", "no search-terms input provided")
    else:
        agg = _agg_terms(search_term_rows)
        total_spend = sum(v[0] for v in agg.values())
        if total_spend <= 0:
            skip("KW-02", "no search-term spend in the input")
        else:
            wasted = sum(v[0] for v in agg.values()
                         if v[0] > 10.0 and v[1] == 0 and not v[2])
            pct_w = wasted / total_spend * 100.0
            n_wasted = sum(1 for v in agg.values() if v[0] > 10.0 and v[1] == 0 and not v[2])
            checks["KW-02"] = {
                "result": _band(pct_w, 5.0, 10.0, False),
                "observed": f"{pct_w:.1f}% of search-term spend (${wasted:,.2f} of "
                            f"${total_spend:,.2f}) on {n_wasted} terms with >$10 spend "
                            "and 0 conversions"}
            if not any("EXCLUDED" in canon_enum(r.get("search_term_view.status"))
                       or r.get("search_term_view.status") for r in search_term_rows):
                notes.append("search-term status not present — already-excluded terms "
                             "could not be removed from the KW-02 numerator.")

    # ---- keyword rules ----------------------------------------------------------
    if keyword_rows is None:
        for cid in ("KW-05", "AS-03", "KW-03"):
            skip(cid, "no keywords input provided")
    else:
        has_ag = any("ad_group.id" in r or "ad_group.name" in r for r in keyword_rows)
        ag_key = "ad_group.id" if any("ad_group.id" in r for r in keyword_rows) else "ad_group.name"
        if not has_ag:
            skip("KW-05", "keywords rows carry no ad-group identity — re-pull per "
                          "gaql-queries.md Step 3 / re-export with the 'Ad group' column")
        else:
            d = _dupe_count(keyword_rows, ag_key)
            checks["KW-05"] = {
                "result": "PASS" if d == 0 else ("FLAG" if d <= 5 else "FAIL"),
                "observed": f"{d} keyword+match identities duplicated across ad groups"}
        if not any("campaign.name" in r for r in keyword_rows):
            skip("AS-03", "keywords rows carry no campaign.name — re-pull per "
                          "gaql-queries.md Step 3 / re-export with the 'Campaign' column")
            skip("KW-03", "keywords rows carry no campaign.name — cannot join to "
                          "campaign bid strategies")
        else:
            d = _dupe_count(keyword_rows, "campaign.name")
            checks["AS-03"] = {
                "result": "PASS" if d == 0 else ("FLAG" if d <= 5 else "FAIL"),
                "observed": f"{d} keyword+match identities duplicated across campaigns"}
            strat_by_camp = {r.get("campaign.name"): canon_strategy(
                r.get("campaign.bidding_strategy_type"))
                for r in (campaign_rows or []) if r.get("campaign.bidding_strategy_type")}
            if not strat_by_camp:
                skip("KW-03", "campaign bid strategies not present — cannot detect "
                              "legacy BMM (BROAD + Manual CPC)")
            else:
                bmm = [r for r in keyword_rows
                       if canon_match(r.get("ad_group_criterion.keyword.match_type")) == "BROAD"
                       and strat_by_camp.get(r.get("campaign.name")) in
                       ("MANUAL_CPC", "ENHANCED_CPC")]
                checks["KW-03"] = {
                    "result": "PASS" if not bmm else "FLAG",
                    "observed": (f"{len(bmm)} BROAD keywords in Manual/Enhanced-CPC "
                                 "campaigns (legacy-BMM pattern) — review intent"
                                 if bmm else
                                 "No BROAD keywords under Manual/Enhanced CPC")}
        # KW-04 evidence: spend mix by match type
        mix: dict[str, float] = {}
        for r in keyword_rows:
            m = canon_match(r.get("ad_group_criterion.keyword.match_type"))
            if m:
                mix[m] = mix.get(m, 0.0) + r.get("metrics.cost_micros", 0) / 1e6
        total = sum(mix.values())
        if total > 0:
            parts = [f"{k} {v / total * 100:.0f}%"
                     for k, v in sorted(mix.items(), key=lambda x: -x[1])]
            evidence["KW-04"] = {"observed": "Keyword spend by match type: " + ", ".join(parts)}
        # QS cost-weighted KPI
        qs_pairs = [(r.get("metrics.cost_micros", 0) / 1e6,
                     _f(r, "ad_group_criterion.quality_info.quality_score"))
                    for r in keyword_rows
                    if _f(r, "ad_group_criterion.quality_info.quality_score") is not None]
        qs = wavg([(w, v) for w, v in qs_pairs])
        if qs is not None:
            flag = "PASS" if qs >= 7 else ("FLAG" if qs >= 6 else "FAIL")
            kpis.append({"metric": "Quality Score (cost-wtd)", "value": round(qs, 1),
                         "unit": "", "benchmark": ">=7", "flag": flag,
                         "notes": f"over {len(qs_pairs)} scored keywords (machine-scored)"})

    # attach fixed metadata to every machine-scored check
    for cid, c in checks.items():
        c["severity"] = CHECK_RULES[cid]["severity"]

    return {"source": "rows", "business_model": bm,
            "checks": checks, "evidence": evidence, "kpis": kpis,
            "skipped": sorted(skipped, key=lambda s: s["id"]),
            "notes": sorted(notes)}


# ── merge into the model-authored findings ──────────────────────────────────

def merge_into_findings(findings: dict, prescore: dict | None
                        ) -> tuple[dict, dict | None, list[str]]:
    """Enforce machine-scored results over the findings JSON (pure; deep copy).

    Category A: overwrite result/observed/severity by canonical check ID,
    injecting the check (framework name/verify, empty recommendation) when the
    model omitted it. Category B: fill observed only when blank. KPI rows:
    replace by casefolded metric name, append when new. Returns
    (merged, model_block, stderr_log_lines)."""
    if prescore is None:
        return findings, None, []
    merged = copy.deepcopy(findings)
    sections = merged.setdefault("sections", [])
    by_tab = {s.get("tab"): s for s in sections}
    applied, injected, evidence_filled, kpis_replaced = [], [], [], []
    corrected, log = [], []

    def find_check(cid):
        for s in sections:
            for c in s.get("checks", []):
                if str(c.get("id", "")).strip() == cid:
                    return c
        return None

    def section_for(cid):
        tab = _TAB_BY_PREFIX.get(cid.split("-")[0])
        if tab in by_tab:
            return by_tab[tab]
        sec = {"tab": tab, "title": _TAB_TITLE.get(tab, tab), "checks": []}
        order = {t: i for i, t in enumerate(_TAB_ORDER)}
        pos = next((i for i, s in enumerate(sections)
                    if order.get(s.get("tab"), 99) > order.get(tab, 99)), len(sections))
        sections.insert(pos, sec)
        by_tab[tab] = sec
        return sec

    for cid in sorted(prescore.get("checks", {})):
        p = prescore["checks"][cid]
        row = find_check(cid)
        if row is None:
            rule = CHECK_RULES.get(cid, {})
            section_for(cid)["checks"].append({
                "id": cid, "name": rule.get("name", cid),
                "verify": rule.get("verify", ""), "applies_to": "Both",
                "severity": p["severity"], "result": p["result"],
                "observed": p["observed"], "recommendation": ""})
            injected.append(cid)
            log.append(f"prescore: {cid} injected as {p['result']} ({p['observed']})")
        else:
            old = str(row.get("result", "")).strip()
            if old and old != p["result"]:
                corrected.append({"id": cid, "from": old, "to": p["result"]})
                log.append(f"prescore: {cid} {old}->{p['result']} ({p['observed']})")
            row["result"] = p["result"]
            row["observed"] = p["observed"]
            row["severity"] = p["severity"]
        applied.append(cid)

    for cid in sorted(prescore.get("evidence", {})):
        row = find_check(cid)
        if row is not None and not str(row.get("observed", "")).strip():
            row["observed"] = prescore["evidence"][cid]["observed"]
            evidence_filled.append(cid)

    if prescore.get("kpis"):
        kpi_list = merged.setdefault("kpis", [])
        by_name = {str(k.get("metric", "")).casefold(): i for i, k in enumerate(kpi_list)}
        for row in prescore["kpis"]:
            key = str(row["metric"]).casefold()
            if key in by_name:
                kpi_list[by_name[key]] = dict(row)
                kpis_replaced.append(row["metric"])
            else:
                kpi_list.append(dict(row))

    block = {"applied": sorted(applied), "corrected": corrected,
             "injected": sorted(injected), "evidence_filled": sorted(evidence_filled),
             "kpis_replaced": sorted(kpis_replaced),
             "skipped": prescore.get("skipped", []), "notes": prescore.get("notes", [])}
    return merged, block, log
