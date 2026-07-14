#!/usr/bin/env python3
"""Skill-specific artifacts the shared render toolkit doesn't own: the action
plan, the renaming worklist, and the Editor pause-list CSV — retained from the
pre-advisor SKILL.md, adapted to the per-check row model.

`negative_keywords.csv` from the pre-advisor version is DELIBERATELY NOT
reproduced here: this skill's `no_negatives` check only knows a campaign has
too few negatives, never which specific terms are junk — that needs term-
level search-query data this skill does not pull. Writing a CSV with
fabricated placeholder terms would be actively harmful (a user could import
it and pollute the account with a literal placeholder negative). The action
plan instead hands that check off to `google-ads-keywords-search-terms`,
which has the term-level data.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import health_core as core

HERE = Path(__file__).resolve().parent
FOUNDATION_SCRIPTS = HERE.parents[1] / "google-ads-foundation" / "scripts"
sys.path.insert(0, str(FOUNDATION_SCRIPTS))
import make_editor_csv as MEC  # noqa: E402

_ACTIONS = {
    "sprawl": "Segment into themed 5–10 keyword ad groups.",
    "no_negatives": "Add campaign-level negatives (junk + competitor terms) — see "
                    "google-ads-keywords-search-terms for term-level candidates.",
    "automation_no_data": "Revert to Manual CPC / Max Clicks until conversion data accrues "
                          "(hand off to google-ads-bidding-strategy).",
    "naming": "Rename to the convention in the Controls tab / references/account-health-filter.md "
             "— confirm the segments/geos with the user first.",
    "pmax_cannibalization": "Add an account-level negative-keyword / brand-exclusion list to the "
                            "PMax campaign — confirm current exclusion status in the UI first.",
}


def action_plan_md(model: dict) -> str:
    pr = model["provenance"]
    L = ["# Account Health — Action Plan",
         "",
         f"Account: {pr.get('client_name', '')} {pr.get('account_id', '')}  ·  "
         f"generated {pr.get('generated', '')}",
         "",
         "Ordered by severity — Critical first, then High, then Medium. Each item names the "
         "artifact that applies it, or **manual** when no Editor CSV can.",
         ""]
    order = ["Critical", "High", "Medium"]
    tf = model["top_fixes"]
    by_sev = {s: [r for r in tf if r["severity"] == s] for s in order}
    if not tf:
        L.append("**Clean — no structural red flags across all five checks.** Nothing to action.")
        return "\n".join(L) + "\n"
    for sev in order:
        rows = by_sev[sev]
        if not rows:
            continue
        L.append(f"## {sev}")
        for r in rows:
            artifact = ("`*_pause_list.csv`" if r["check"] == "sprawl"
                        else "`*_renaming.md`" if r["check"] == "naming"
                        else "manual (Editor / UI)")
            L.append(f"- [ ] **{r['check_label']}** — {r['entity_name']}"
                     + (f" ({r['campaign_name']})" if r['campaign_name'] and r['campaign_name'] != r['entity_name'] else "")
                     + f" — {_ACTIONS[r['check']]} — pre-score {r['pre_score']:.1f} — {artifact}")
        L.append("")
    return "\n".join(L) + "\n"


def renaming_md(model: dict) -> str:
    rows = [r for r in model["rows"] if r["check"] == "naming" and r["is_flagged"]]
    L = ["# Account Health — Renaming Worklist", "",
         f"Default convention (unconfirmed — see `references/account-health-filter.md`): "
         f"`{model['params']['naming_regex']}`",
         "",
         "Renaming is **manual** in Google Ads Editor (Account → rename). This worklist names the "
         "campaigns that fail the convention; it does not invent a compliant name — confirm the "
         "brand/geo/channel/product/year segments with the user before renaming.",
         ""]
    if not rows:
        L.append("**Clean — every campaign name matches the convention.**")
        return "\n".join(L) + "\n"
    L.append("| Current name | Campaign ID | Confirm with user |")
    L.append("|---|---|---|")
    for r in sorted(rows, key=lambda r: r["campaign_name"]):
        L.append(f"| {r['campaign_name']} | {r['entity_id']} | brand/geo/channel/product/year segments |")
    L.append("")
    return "\n".join(L) + "\n"


def pause_list_rows(model: dict) -> list:
    rows = [r for r in model["rows"] if r["check"] == "sprawl" and r["is_flagged"]]
    out = []
    for r in sorted(rows, key=lambda r: -r["pre_score"]):
        out.append({
            "Campaign": r["campaign_name"], "Ad Group": r["entity_name"],
            "Entity Type": "Ad Group", "Entity": r["entity_name"],
            "Reason": f"Sprawl: {int(r['keyword_count'])} keywords, "
                     f"CTR {r['ad_group_ctr'] * 100:.2f}% (30d) — segment into themed groups.",
        })
    return out


def write_pause_list_csv(model: dict, out_path: str) -> int:
    rows = pause_list_rows(model)
    columns = MEC.SCHEMAS["pause_list"]
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(MEC._row_to_columns(row, columns))
    return len(rows)


def write_artifacts(model: dict, stem: str, outdir: str) -> list:
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    written = []

    p = out / f"{stem}_action_plan.md"
    p.write_text(action_plan_md(model))
    written.append(p)

    p = out / f"{stem}_renaming.md"
    p.write_text(renaming_md(model))
    written.append(p)

    p = out / f"{stem}_pause_list.csv"
    write_pause_list_csv(model, str(p))
    written.append(p)

    return written
