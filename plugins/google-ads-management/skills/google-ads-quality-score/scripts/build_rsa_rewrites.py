#!/usr/bin/env python3
"""Build the RSA-rewrite advisor artifact (`*_rsa_rewrites.md`) — the deepened
step-4 "ad relevance matrix" worklist (thin CLI, stdlib only).

Grounded entirely in the reconciled model (qs_core.compute_model): every
keyword whose Ad-relevance component rates below the component target (the
same test qs_core.dominant_factor uses for the "Ad relevance" drag total —
Critical keywords, whose Ad relevance is ALSO below target, are included too)
is grouped by ad group with its cost/impressions, so the fix is prioritized by
spend, not alphabetically. The Google Ads MCP is read-only and does not expose
current RSA headline text, so this worklist prescribes what each ad group's
headlines must contain — it is not a live keyword<->headline diff. Cross-
reference it against the ad group's current RSAs in the Google Ads UI or
Editor before publishing.

Extends (does not replace) the analytical bundle built by build_qs_report.py:
run this AFTER the bundle, from the same findings.json.

Usage:
    python3 build_rsa_rewrites.py --input findings.json --outdir artifacts --brand "Acme Corp"

Exit codes: 0 success, 1 usage/validation error.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PLUGIN_ROOT / "_shared"))

import qs_core as core                    # noqa: E402
from render import model as M             # noqa: E402

HEADLINE_MAX = 30   # RSA headline character limit


def ad_relevance_keywords(model: dict) -> list:
    """Every in-scope, scored keyword whose Ad relevance component is below
    the component target — the same test qs_core.component_drag uses for the
    'Ad relevance' drag total. A superset of the 'Ad relevance' bucket: also
    includes 'Critical' keywords (their Ad relevance is below target too)."""
    p = model["params"]
    target = p["component_target"]
    rows = [r for r in model["rows"]
            if r["status"] == "scored" and r["qs"] is not None
            and r["qs"] < p["qs_low_threshold"] and 0 < r["ar"] < target]
    rows.sort(key=lambda r: -r["cost"])
    return rows


def group_by_ad_group(rows: list) -> list:
    groups: dict = {}
    order: list = []
    for r in rows:
        key = r["ad_group_id"]
        if key not in groups:
            groups[key] = {"ad_group": r["ad_group"], "campaign": r["campaign"],
                           "keywords": [], "cost": 0.0, "impressions": 0.0}
            order.append(key)
        g = groups[key]
        g["keywords"].append(r)
        g["cost"] += r["cost"]
        g["impressions"] += r["impressions"]
    out = [groups[k] for k in order]
    out.sort(key=lambda g: -g["cost"])
    return out


def render_md(model: dict, groups: list) -> str:
    pr = model["provenance"]
    dom = model["dominant_factor"]
    ar_drag = next((d for d in dom["drag"] if d["component"] == "Ad relevance"), None)
    total_kw = sum(len(g["keywords"]) for g in groups)
    total_cost = sum(g["cost"] for g in groups)
    cur = pr.get("currency", "")

    lines = [
        f"# RSA-Rewrite Advisor — {pr.get('client_name') or 'Account'}"
        + (f" ({pr['account_id']})" if pr.get("account_id") else ""),
        "",
        f"Currency {cur or '—'}  ·  {pr.get('window_90d') or '—'}  ·  generated "
        f"{pr.get('generated') or '—'}  ·  source {pr.get('source', 'mcp')}",
        "",
        "Deepens step 4 of the Quality Score forensic (the ad-relevance keyword↔headline "
        "matrix): every in-scope keyword whose Ad relevance rates below target, grouped by ad "
        "group and prioritized by spend. The MCP is read-only and does not return current RSA "
        "headline text — this is a prescriptive worklist (what each ad group's headlines must "
        "contain), not a live diff. Check the ad group's current RSAs in the Google Ads UI or "
        "Editor before publishing.",
        "",
        f"**{len(groups)} ad group(s) · {total_kw} keyword(s) · "
        f"{M.money(total_cost, cur)} in below-target spend.**"
        + (f" Model total for the Ad relevance component: {M.money(ar_drag['cost'], cur)} across "
           f"{ar_drag['keywords']} keyword(s) (dominant_factor.drag)." if ar_drag else ""),
        "",
    ]
    if not groups:
        lines.append("_No keywords have a below-target Ad relevance component at the current "
                     "thresholds — clean._")
        return "\n".join(lines) + "\n"

    for g in groups:
        lines.append(f"## {g['ad_group']} — {g['campaign']}")
        lines.append(f"{len(g['keywords'])} keyword(s) · {M.money(g['cost'], cur)} · "
                     f"{M.num(g['impressions'])} impressions.")
        lines.append("")
        lines.append("Rewrite at least one RSA headline (≤ 30 characters) to contain each exact "
                     "phrase below — ad relevance is scored on whether ad copy echoes the keyword.")
        lines.append("")
        lines.append("| Keyword | QS | Ad relevance | Cost | Impr | Suggested headline coverage |")
        lines.append("|---|---:|---|---:|---:|---|")
        for r in g["keywords"]:
            kw = M.mdcell(r["keyword"])
            fits = "fits as-is" if len(r["keyword"]) <= HEADLINE_MAX else \
                f"trim to ≤{HEADLINE_MAX} chars (keyword is {len(r['keyword'])})"
            lines.append(f"| {kw} | {r['qs']} | {r['ar_label']} "
                         f"| {r['cost']:,.2f} | {int(r['impressions'])} | {fits} |")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the RSA-rewrite advisor artifact.")
    ap.add_argument("--input", required=True)
    ap.add_argument("--outdir", default="artifacts")
    ap.add_argument("--brand", default="")
    args = ap.parse_args()

    try:
        findings = core.load_findings(args.input)
    except core.FindingsError as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return 1
    model = core.compute_model(findings)
    groups = group_by_ad_group(ad_relevance_keywords(model))

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    stem = M.stem(model, {"slug_prefix": "quality-score"}, args.brand)
    out_path = outdir / f"{stem}_rsa_rewrites.md"
    out_path.write_text(render_md(model, groups), encoding="utf-8")

    print(f"Wrote {out_path}")
    print(f"  ad_groups={len(groups)} keywords={sum(len(g['keywords']) for g in groups)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
