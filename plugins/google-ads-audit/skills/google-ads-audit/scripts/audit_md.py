#!/usr/bin/env python3
# Copyright (c) 2026 Clickt Digital Marketing Inc. All rights reserved.
"""Markdown record for google-ads-audit — the LLM-readable / vault-ingestible format.

Renders the same computed model as the HTML and xlsx (so the three never disagree) into
a plain-text, Obsidian-friendly report: YAML frontmatter, the Health Score + grade, the
KPI scorecard, a table per audit area, and the findings ranked by ICE (at the neutral
default Confidence/Ease). Stdlib only; deterministic except `provenance.generated`.
"""
from __future__ import annotations

from pathlib import Path

from audit_model import DEFAULT_ICE


def _c(s) -> str:
    """Escape a markdown table cell: pipes and newlines."""
    return str("" if s is None else s).replace("|", "\\|").replace("\n", " ").strip()


def _row(cells) -> str:
    return "| " + " | ".join(_c(c) for c in cells) + " |"


def render_md(model: dict) -> str:
    P = model["provenance"]
    H = model["health"]
    S = model["summary"]
    L: list[str] = []

    # --- frontmatter ---
    L += [
        "---",
        f'title: "Google Ads Audit — {P.get("client_name","")}"',
        f'client: "{P.get("client_name","")}"',
        f'account: "{P.get("account_id","")}"',
        f"health_score: {H['score']}",
        f'grade: "{H['grade']}"',
        f'business_model: "{P.get("business_model","")}"',
        f'date_range: "{P.get("date_range","")}"',
        f'generated: "{P.get("generated","")}"',
        "tags: [google-ads, audit]",
        "---",
        "",
        f"# Google Ads Audit — {P.get('client_name','')}",
        "",
        f"**Account** {P.get('account_id','')} · **Window** {P.get('date_range','')} · "
        f"**Currency** {P.get('currency','')} · **Model** {P.get('business_model','')} · "
        f"**Audited** {P.get('audit_date','')}",
        "",
    ]

    # --- headline ---
    L += [
        "## Health Score",
        "",
        f"**{H['score']} / 100 — Grade {H['grade']}**  "
        f"({S['n_pass']} pass · {S['n_flag']} flag · {S['n_fail']} fail · {S['n_na']} n/a "
        f"across {P.get('n_checks',0)} checks)",
        "",
        f"Findings: **{P.get('n_findings',0)}** — "
        f"{S['crit']} critical · {S['high']} high · {S['med']} medium · {S['low']} low.",
        "",
        "_Score = Σ(flag × severity weight) ÷ Σ(possible) × 100; N/A excluded. "
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

    # --- per-area check tables ---
    L += ["## Audit areas", ""]
    for sec in model["sections"]:
        pct = sec.get("score_pct")
        score_txt = "n/a" if pct is None else f"{pct} / 100"
        L += [f"### {sec.get('title','')} — {score_txt}", "",
              _row(["Check", "Applies", "Severity", "Result", "Observed", "Recommendation"]),
              _row(["---", "---", "---", "---", "---", "---"])]
        for c in sec.get("checks", []):
            name = f"{c.get('id','')} — {c.get('name','')}"
            L.append(_row([name, c.get("applies_to", "Both"), c.get("severity", ""),
                           c.get("result", ""), c.get("observed", ""), c.get("recommendation", "")]))
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

    # --- findings (ranked by ICE at the neutral default) ---
    if model.get("findings"):
        d = DEFAULT_ICE
        ranked = sorted(model["findings"], key=lambda f: -(f.get("impact", 0) * d * d))
        L += ["## Findings — prioritised by ICE",
              "",
              f"_Ranked by Impact × Confidence × Ease at the neutral default "
              f"(Confidence = Ease = {d}); adjust in the interactive HTML report to re-rank._",
              "",
              _row(["#", "Finding", "Severity", "Horizon", "Impact", "ICE", "Recommendation"]),
              _row(["---", "---", "---", "---", "---", "---", "---"])]
        for i, f in enumerate(ranked, 1):
            impact = f.get("impact", 0)
            L.append(_row([i, f.get("title", ""), f.get("severity", ""),
                           f"{f.get('horizon','')}d", impact, impact * d * d,
                           f.get("recommendation", "")]))
        L.append("")

    # --- data inventory ---
    if model.get("data_inventory"):
        L += ["## Data inventory", "",
              _row(["Pull", "Resource", "Rows", "Status", "Notes"]),
              _row(["---", "---", "---", "---", "---"])]
        for d0 in model["data_inventory"]:
            L.append(_row([d0.get("pull", ""), d0.get("resource", ""), d0.get("rows", ""),
                           d0.get("status", ""), d0.get("notes", "")]))
        L.append("")

    PS = model.get("prescore")
    if PS:
        line = (f"_{len(PS.get('applied', []))} of {P.get('n_checks', 0)} checks "
                "machine-scored deterministically from the data files")
        if PS.get("corrected"):
            ids = ", ".join(c["id"] for c in PS["corrected"])
            line += f" · corrections applied over the drafted findings: {ids}"
        L += [line + "._", ""]
    L += ["---",
          f"_Generated {P.get('generated','')} · self-contained interactive HTML and a "
          f"formula-driven .xlsx accompany this record._", ""]
    return "\n".join(L)


def build_markdown(model: dict, path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_md(model), encoding="utf-8")
