#!/usr/bin/env python3
# Copyright (c) 2026 Clickt Digital Marketing Inc. All rights reserved.
"""Markdown record for meta-ads-audit — the LLM-readable / vault-ingestible format.

Ported from google-ads-audit `scripts/audit_md.py`. Renders the same computed model
as the HTML and xlsx (so the three never disagree) into a plain-text, Obsidian-friendly
report: YAML frontmatter, the lever-weighted Health Score + grade, the KPI scorecard,
a table per audit lever (with the `expected` column and optional evidence tables),
the Concentration and Creative Signals sections, and the findings ranked by the model's
computed ICE priority (with the roadmap bucket). Stdlib only; deterministic except
`meta.generated`.
"""
from __future__ import annotations

from pathlib import Path

from audit_model import DEFAULT_ICE, ROADMAP_BUCKETS


def _c(s) -> str:
    """Escape a markdown table cell: pipes and newlines."""
    return str("" if s is None else s).replace("|", "\\|").replace("\n", " ").strip()


def _y(s) -> str:
    """One YAML double-quoted scalar, escaped. Client-controlled strings (account
    name above all) reach the frontmatter, and a stray `"` there silently breaks
    the whole block for any vault parser."""
    out = str("" if s is None else s).replace("\\", "\\\\").replace('"', '\\"')
    out = out.replace("\n", " ").replace("\r", " ")
    return '"%s"' % out


def _row(cells) -> str:
    return "| " + " | ".join(_c(c) for c in cells) + " |"


def _num(v, nd: int = 2) -> str:
    """Comma-grouped number or em-dash for missing."""
    if v is None or v == "":
        return "—"
    try:
        return f"{float(v):,.{nd}f}"
    except (TypeError, ValueError):
        return str(v)


def _pct2(v) -> str:
    """Fraction -> percent with 2 decimals (CTRs are small on Meta)."""
    if v is None or v == "":
        return "—"
    try:
        return f"{float(v) * 100:.2f}%"
    except (TypeError, ValueError):
        return str(v)


def render_md(model: dict) -> str:
    P = model["meta"]
    H = model["health"]
    S = model["summary"]
    grade_letter = H["grade"]
    windows = P.get("windows", {}) or {}
    L: list[str] = []

    # --- frontmatter ---
    # Every quoted scalar goes through _y: an account name containing a double
    # quote (Acme "Prime" Ltd) would otherwise close the string early and leave
    # the whole block unparseable — which defeats the point of an
    # Obsidian-ingestible record, and account names are client-controlled.
    L += [
        "---",
        f'title: {_y("Meta Ads Audit — " + str(P.get("account_name","")))}',
        f'client: {_y(P.get("account_name",""))}',
        f'account: {_y(P.get("account_id",""))}',
        f"health_score: {H['score']}",
        f'grade: {_y(grade_letter)}',
        f'business_model: {_y(P.get("business_model",""))}',
        f'window_structure: {_y(windows.get("structure",""))}',
        f'window_creative: {_y(windows.get("creative",""))}',
        f'generated: {_y(P.get("generated",""))}',
        "tags: [meta-ads, audit]",
        "---",
        "",
        f"# Meta Ads Audit — {P.get('account_name','')}",
        "",
        f"**Account** {P.get('account_id','')} · **Structure window** {windows.get('structure','')} · "
        f"**Creative window** {windows.get('creative','')} · **Currency** {P.get('currency','')} · "
        f"**Model** {P.get('business_model','')} · **Audited** {P.get('generated_for_date','')}",
        "",
    ]

    # --- headline ---
    L += [
        "## Health Score",
        "",
        f"**{H['score']} / 100 — Grade {grade_letter}**  "
        f"({S['n_pass']} pass · {S['n_flag']} flag · {S['n_fail']} fail · {S['n_na']} n/a "
        f"across {P.get('n_checks',0)} checks)",
        "",
        f"Findings: **{P.get('n_findings',0)}** — "
        f"{S['crit']} critical · {S['high']} high · {S['med']} medium · {S['low']} low.",
        "",
        "_Score = lever-weighted average of area scores (area = Σ(flag × severity weight) "
        "÷ Σ(possible) × 100; N/A excluded; weights DI 20 · AR 20 · BP 15 · AT 10 · CR 25 · "
        "CO 0 · FP 10; levers with nothing scorable excluded). "
        "Grade: A≥90, B≥75, C≥60, D≥40, else F._",
        "",
    ]

    # --- KPI scorecard ---
    if model.get("kpis"):
        L += ["## KPI scorecard", "", _row(["Metric", "Value", "Benchmark", "Flag", "Notes"]),
              _row(["---", "---", "---", "---", "---"])]
        for k in model["kpis"]:
            unit = k.get("unit", "")
            val = f"{'$' if unit=='$' else ''}{k.get('value','')}{'%' if unit=='%' else ''}"
            L.append(_row([k.get("metric", ""), val, k.get("benchmark", ""),
                           k.get("flag", ""), k.get("notes", "")]))
        L.append("")

    # --- per-lever check tables (+ optional evidence passthrough) ---
    L += ["## Audit areas", ""]
    for sec in model["sections"]:
        pct = sec.get("score_pct")
        score_txt = "n/a" if pct is None else f"{pct} / 100"
        weight = sec.get("weight")
        weight_txt = "" if weight is None else f" (weight {weight:g})"
        L += [f"### {sec.get('title','')} — {score_txt}{weight_txt}", "",
              _row(["Check", "Expected", "Severity", "Result", "Observed", "Recommendation"]),
              _row(["---", "---", "---", "---", "---", "---"])]
        for c in sec.get("checks", []):
            name = f"{c.get('id','')} — {c.get('name','')}"
            L.append(_row([name, c.get("expected", ""), c.get("severity", ""),
                           c.get("result", ""), c.get("observed", ""), c.get("recommendation", "")]))
        L.append("")
        ev = sec.get("evidence")
        if ev and ev.get("columns") and ev.get("rows"):
            cols = list(ev["columns"])
            L += ["**Evidence**", "", _row(cols), _row(["---"] * len(cols))]
            for r in ev["rows"]:
                cells = list(r or [])
                # pad/trim to the header width so the table stays well-formed
                cells = (cells + [""] * len(cols))[:len(cols)]
                L.append(_row(cells))
            L.append("")

    # --- concentration (from raw pull files; absent when not provided) ---
    C = model.get("concentration")
    if C:
        L += ["## Concentration — spend vs conversions (HHI)", "",
              "_HHI bands (merger-guideline cutoffs): <1,500 unconcentrated · "
              "1,500–2,500 moderate · >2,500 high. Effective-N reads as \"spend "
              "behaves as if only N entities exist.\"_", ""]
        for dim in C.get("dimensions", []):
            window = f" ({dim['window']})" if dim.get("window") else ""
            L += [f"### {dim.get('label','')}{window} — {dim.get('verdict','')}", "",
                  _row(["", "HHI", "Band", "Effective-N", "Gini"]),
                  _row(["---", "---", "---", "---", "---"])]
            for side, side_label in (("spend", "Spend"), ("conv", "Conversions")):
                m = dim.get(side)
                if m:
                    L.append(_row([side_label, f"{m['hhi']:,.1f}", m["band"],
                                   m["eff_n"], m["gini"]]))
                else:
                    L.append(_row([side_label, "no signal", "", "", ""]))
            L += ["", f"{dim.get('n_entities', 0)} entities "
                      f"(from {dim.get('n_rows_raw', 0)} raw rows).", ""]
            top = dim.get("top", [])
            if top:
                L += [_row(["Entity", "Spend", "Conv", "Spend %", "Conv %", "ABC"]),
                      _row(["---", "---", "---", "---", "---", "---"])]
                for t in top[:10]:
                    L.append(_row([t["name"], f"{t['spend']:,.2f}", t["conv"],
                                   f"{t['spend_share']*100:.1f}%",
                                   f"{t['conv_share']*100:.1f}%", t["abc"]]))
                tail = dim.get("tail")
                extra = len(top) - 10 if len(top) > 10 else 0
                if tail or extra:
                    n_more = (tail["n"] if tail else 0) + extra
                    spend_more = (tail["spend"] if tail else 0.0) + sum(
                        t["spend"] for t in top[10:])
                    L.append(_row([f"… plus {n_more} more",
                                   f"{spend_more:,.2f}", "", "", "", ""]))
                L.append("")
            if dim.get("caveat"):
                L += [f"_{dim['caveat']}_", ""]
        for note in C.get("notes", []):
            L += [f"_Note: {note}_", ""]

    # --- creative signals (from raw pull files; absent when not provided) ---
    CS = model.get("creative_signals")
    if CS:
        B = CS.get("baselines", {}) or {}
        Z = CS.get("zones", {}) or {}
        SM = CS.get("summary", {}) or {}
        window = f" ({CS['window']})" if CS.get("window") else ""
        L += [f"## Creative Signals — fatigue, saturation, frequency{window}", "",
              f"_Account baselines: CTR {_pct2(B.get('ctr'))} (all clicks) · "
              f"CPM {_num(B.get('cpm'))} across {B.get('n_ads', 0)} ad(s). "
              "Fatigue blends frequency pressure with CTR erosion and CPM inflation "
              "(saturated > 0.66 · watch > 0.33 · else fresh); saturation = 1 − reach ÷ "
              "impressions; ad-set frequency zones: under < 3 · effective 3–7 · "
              "oversaturated > 7._", "",
              f"Fatigue bands: **{SM.get('saturated', 0)} saturated · "
              f"{SM.get('watch', 0)} watch · {SM.get('fresh', 0)} fresh** "
              f"({SM.get('below_floor', 0)} below the impressions floor · "
              f"{SM.get('high_saturation', 0)} high-saturation).", ""]
        ads = CS.get("ads", []) or []
        if ads:
            L += [_row(["Ad", "Spend", "Impr", "Freq", "CTR", "CPM",
                        "Fatigue", "Band", "Saturation"]),
                  _row(["---"] * 9)]
            for a in ads[:10]:
                L.append(_row([a.get("name", ""), _num(a.get("spend")),
                               _num(a.get("impressions"), 0), _num(a.get("frequency")),
                               _pct2(a.get("ctr")), _num(a.get("cpm")),
                               _num(a.get("fatigue")),
                               a.get("fatigue_band") or "below floor",
                               _num(a.get("saturation"))]))
            tail = CS.get("tail")
            extra = len(ads) - 10 if len(ads) > 10 else 0
            if tail or extra:
                n_more = (tail["n"] if tail else 0) + extra
                spend_more = (tail["spend"] if tail else 0.0) + sum(
                    float(a.get("spend") or 0) for a in ads[10:])
                L.append(_row([f"… plus {n_more} more", f"{spend_more:,.2f}",
                               "", "", "", "", "", "", ""]))
            L.append("")
        L += [f"Ad-set frequency zones: under {Z.get('under', 0)} · "
              f"effective {Z.get('effective', 0)} · "
              f"oversaturated {Z.get('oversaturated', 0)}.", ""]
        zrows = Z.get("rows", []) or []
        if zrows:
            L += [_row(["Ad set", "Frequency", "Zone", "Spend"]),
                  _row(["---", "---", "---", "---"])]
            for r in zrows[:10]:
                L.append(_row([r.get("name", ""), _num(r.get("frequency")),
                               r.get("zone", ""), _num(r.get("spend"))]))
            if len(zrows) > 10:
                L.append(_row([f"… plus {len(zrows) - 10} more", "", "", ""]))
            L.append("")
        R = CS.get("rankings") or {}
        if R.get("available"):
            rsum = (R.get("summary", {}) or {}).get("weakest", {}) or {}
            L += ["**Ranking decomposition** — weakest lever: "
                  f"quality {rsum.get('quality', 0)} · "
                  f"engagement {rsum.get('engagement', 0)} · "
                  f"conversion {rsum.get('conversion', 0)}.", "",
                  _row(["Ad", "Spend", "Quality", "Engagement", "Conversion", "Weakest"]),
                  _row(["---", "---", "---", "---", "---", "---"])]
            for r in (R.get("rows", []) or [])[:10]:
                L.append(_row([r.get("name", ""), _num(r.get("spend")),
                               r.get("quality") or "—", r.get("engagement") or "—",
                               r.get("conversion") or "—", r.get("weakest") or "—"]))
            L.append("")
        for note in CS.get("notes", []) or []:
            L += [f"_Note: {note}_", ""]

    # --- findings (ranked by the model's ICE priority; bucket = roadmap) ---
    if model.get("findings"):
        d = DEFAULT_ICE
        bucket_legend = " · ".join(f"≥{t} → {label}" for t, label in ROADMAP_BUCKETS[:-1])
        bucket_legend += f" · else {ROADMAP_BUCKETS[-1][1]}"
        ranked = sorted(model["findings"], key=lambda f: -(f.get("priority") or 0))
        L += ["## Findings — prioritised by ICE",
              "",
              f"_Ranked by Impact × Confidence × Ease (missing Confidence/Ease default "
              f"to {d}); adjust in the interactive HTML report to re-rank. "
              f"Roadmap bucket: {bucket_legend}._",
              "",
              _row(["#", "Finding", "Severity", "Bucket", "Impact", "ICE", "Recommendation"]),
              _row(["---", "---", "---", "---", "---", "---", "---"])]
        for i, f in enumerate(ranked, 1):
            L.append(_row([i, f.get("title", ""), f.get("severity", ""),
                           f.get("bucket", ""), f.get("impact", 0),
                           f.get("priority", 0), f.get("recommendation", "")]))
        L.append("")

    PS = model.get("prescore")
    if PS:
        line = (f"_{len(PS.get('applied', []) or [])} of {P.get('n_checks', 0)} checks "
                "machine-scored deterministically from the data files")
        if PS.get("corrected"):
            ids = ", ".join(c["id"] for c in PS["corrected"])
            line += f" · corrections applied over the drafted findings: {ids}"
        L += [line + "._", ""]
        # Machine-vs-narrative drift belongs IN the record, not only on stderr:
        # this section is the auditor's working copy, and an unreconciled check
        # means the score and the roadmap disagree about the same account.
        unrec = PS.get("unreconciled") or []
        if unrec:
            L += ["> [!warning] Findings not reconciled with the machine results",
                  "> The Health Score reflects these corrections; the findings "
                  "below were written before them. Resolve each before sending:"]
            for u in unrec:
                # .get, not [] — the xlsx twin of this block already reads the
                # same rows defensively, and a renderer is the wrong place to
                # raise over a malformed note.
                uid, res = u.get("id", ""), u.get("result", "")
                if u.get("reason") == "cleared":
                    L.append(f"> - **{uid}** scored **{res}** by the pre-scorer, "
                             "but a finding still argues it — drop or amend that "
                             "finding.")
                else:
                    L.append(f"> - **{uid}** scored **{res}** by the pre-scorer, "
                             "but no finding covers it — add one.")
            L.append("")
    L += ["---",
          f"_Generated {P.get('generated','')} · self-contained interactive HTML and a "
          f"formula-driven .xlsx accompany this record._", ""]
    return "\n".join(L)


def build_markdown(model: dict, path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_md(model), encoding="utf-8")
