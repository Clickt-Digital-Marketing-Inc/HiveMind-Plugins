#!/usr/bin/env python3
# Copyright (c) 2026 Clickt Digital Marketing Inc. All rights reserved.
"""Markdown record for shopify-cro-audit — the LLM-readable / vault-ingestible format.

Ported from meta-ads-audit `scripts/audit_md.py`. Renders the same computed model
as the HTML and xlsx (so the three never disagree) into a plain-text,
Obsidian-friendly report: YAML frontmatter (tags [shopify, cro, audit]), the
Funnel Health 0-150 score + grade, the 11 method-steps — each with its
run/partial/not_run status line (wording mirrors the workbook's notrun banner)
and its `evidence` as a LIST of labeled tables — the Concentration and CVR
Signals sections, the findings ranked by the model's Priority = Impact x 2 +
Ease (with the Now/Next/Soon/Later bucket; NO Confidence — the framework
dropped it on purpose), and the machine-layer footer ("N analytics fields
machine-computed · M correction(s)"). Stdlib only; deterministic except
`meta.generated`.
"""
from __future__ import annotations

from pathlib import Path

from audit_model import (BENCH, DEFAULT_EASE, GRADE_CUTOFFS, HEALTH_MAX,
                         PRIORITY_BUCKETS)

_STATUS_LABEL = {"run": "Run", "partial": "Partial", "not_run": "Not run"}


def _c(s) -> str:
    """Escape a markdown table cell: pipes and newlines."""
    return str("" if s is None else s).replace("|", "\\|").replace("\n", " ").strip()


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
    """FRACTION -> percent with 2 decimals (cvr_signals block unit)."""
    if v is None or v == "":
        return "—"
    try:
        return f"{float(v) * 100:.2f}%"
    except (TypeError, ValueError):
        return str(v)


def _z(v) -> str:
    if v is None or v == "":
        return "—"
    try:
        return f"{float(v):.2f}"
    except (TypeError, ValueError):
        return str(v)


def _seg_table(lines: list, label: str, rows) -> None:
    """One CVR-signals segment table (z + significance vs same-list siblings)."""
    if not rows:
        return
    lines += [f"**{label}**", "",
              _row(["Segment", "Sessions", "Conv", "CVR", "z", "Signal"]),
              _row(["---"] * 6)]
    for r in rows:
        conv = f"{r.get('conversions', '')}" + ("\\*" if r.get("derived") else "")
        sig = "—" if r.get("z") is None else ("significant" if r.get("significant") else "ns")
        lines.append(_row([r.get("name", ""), r.get("sessions", ""), conv,
                           _pct2(r.get("cvr")), _z(r.get("z")), sig]))
    lines.append("")


def render_md(model: dict) -> str:
    P = model["meta"]
    H = model["health"]
    S = model["summary"]
    grade_letter = H["grade"]
    score_txt = "n/a" if H["score"] is None else str(H["score"])
    grade_legend = " · ".join(f"{letter}≥{cutoff}"
                              for cutoff, letter in GRADE_CUTOFFS[:-1])
    grade_legend += f" · else {GRADE_CUTOFFS[-1][1]}"
    L: list[str] = []

    # --- frontmatter ---
    L += [
        "---",
        f'title: "Shopify CRO Audit — {P.get("store_name","")}"',
        f'client: "{P.get("store_name","")}"',
        f'store: "{P.get("store_url","")}"',
        f"health_score: {'' if H['score'] is None else H['score']}",
        f"health_max: {HEALTH_MAX}",
        f'grade: "{grade_letter}"',
        f'window: "{P.get("date_range","")}"',
        f'generated: "{P.get("generated","")}"',
        "tags: [shopify, cro, audit]",
        "---",
        "",
        f"# Shopify CRO Audit — {P.get('store_name','')}",
        "",
        f"**Store** {P.get('store_url','')} · **Window** {P.get('date_range','')} · "
        f"**Currency** {P.get('currency','')} · **Audited** {P.get('generated_for_date','')}",
        "",
    ]

    # --- headline ---
    L += [
        "## Funnel Health",
        "",
        f"**{score_txt} / {HEALTH_MAX} — Grade {grade_letter}**  "
        f"({S['n_run']} of {P.get('n_steps', 0)} steps run · {S['n_partial']} partial · "
        f"{S['n_not_run']} not run)",
        "",
        f"Findings: **{P.get('n_findings',0)}** — "
        f"{S['crit']} critical · {S['high']} high · {S['med']} medium · {S['low']} low.",
        "",
        f"_Score = MIN({HEALTH_MAX}, 100 × mean(rate ÷ benchmark over the MEASURED funnel "
        f"stages — unmeasured stages excluded, never scored 0)); benchmarks (FY2025 DTC): "
        f"added-to-cart {BENCH['atc']}% · checkout {BENCH['checkout']}% · "
        f"purchase {BENCH['cvr']}%. Grade: {grade_legend}._",
        "",
    ]

    # --- the 11 method-steps: status + evidence-table LIST ---
    L += ["## Audit steps", ""]
    for sec in model["sections"]:
        status = sec.get("status", "not_run")
        reason = str(sec.get("reason", "") or "")
        L += [f"### {sec.get('title','')} — {_STATUS_LABEL.get(status, status)}", ""]
        # Status wording mirrors build_cro_workbook.notrun_banner_if_needed.
        if status == "partial":
            L += [f"> PARTIAL — limited data provided.{(' ' + reason) if reason else ''}", ""]
        elif status != "run":
            L += [f"> NOT RUN — data not provided.{(' ' + reason) if reason else ''}", ""]
        elif reason:
            L += [f"_{reason}_", ""]
        evidence = sec.get("evidence") or []
        for ev in evidence:
            cols = list(ev.get("columns") or [])
            if not cols:
                continue
            L += [f"**{ev.get('label','')}**", "", _row(cols), _row(["---"] * len(cols))]
            for r in ev.get("rows") or []:
                cells = list(r or [])
                # pad/trim to the header width so the table stays well-formed
                cells = (cells + [""] * len(cols))[:len(cols)]
                L.append(_row(cells))
            L.append("")
        if not evidence and sec.get("step") == 11:
            L += ["_The prioritised findings below ARE this step — the testing roadmap._", ""]

    # --- concentration (from raw pull / CSV files; absent when not provided) ---
    C = model.get("concentration")
    if C:
        L += ["## Concentration — weight vs outcomes (HHI)", "",
              "_HHI bands (merger-guideline cutoffs): <1,500 unconcentrated · "
              "1,500–2,500 moderate · >2,500 high. Effective-N reads as \"the weight "
              "behaves as if only N entities exist.\" Dimensions pair a weight with its "
              "outcome — products: revenue vs orders · landing pages: sessions vs "
              "conversions · channels: sessions vs revenue (or conversions)._", ""]
        for dim in C.get("dimensions", []):
            window = f" ({dim['window']})" if dim.get("window") else ""
            L += [f"### {dim.get('label','')}{window} — {dim.get('verdict','')}", "",
                  _row(["", "HHI", "Band", "Effective-N", "Gini"]),
                  _row(["---", "---", "---", "---", "---"])]
            for side, side_label in (("spend", "Weight"), ("conv", "Outcome")):
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
                L += [_row(["Entity", "Weight", "Outcome", "Weight %", "Outcome %", "ABC"]),
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

    # --- CVR signals (fractions rendered x100 — display only, no math) ---
    V = model.get("cvr_signals")
    if V:
        site = V.get("site", {}) or {}
        prior = V.get("prior", {}) or {}
        seg = V.get("segments", {}) or {}
        ci = site.get("ci") or [None, None]
        window = f" ({V['window']})" if V.get("window") else ""
        L += [f"## CVR Signals{window}", "",
              f"_Site CVR **{_pct2(site.get('cvr'))}** (95% Wilson CI "
              f"{_pct2(ci[0])} – {_pct2(ci[1])}) on {site.get('sessions', 0):,} sessions / "
              f"{site.get('conversions', 0):,} conversions. Significance gate "
              f"n* = {V.get('min_sessions', 0):,} sessions (a zero-conversion page below "
              f"n* cannot yet be called a loser); empirical-Bayes shrinkage prior "
              f"k = {_num(prior.get('k'), 1)} ({prior.get('basis','')}). "
              "|z| ≥ 1.96 = significant at 95% vs same-list siblings._", ""]
        hz = seg.get("headline_device_z")
        if hz:
            sig = "significant" if hz.get("significant") else "not significant"
            L += [f"Mobile vs desktop: z = **{_z(hz.get('z'))}** ({sig}; "
                  "positive z = mobile converts higher).", ""]
        _seg_table(L, "Device", seg.get("device"))
        _seg_table(L, "Channels", seg.get("channels"))
        _seg_table(L, "New vs returning", seg.get("new_vs_returning"))
        pages = V.get("pages") or []
        if pages:
            U = V.get("pages_universe", {}) or {}
            L += [f"**Landing pages — raw vs shrunk vs Wilson lower bound** "
                  f"(top {len(pages)} by sessions of {U.get('n', 0)} pages · "
                  f"{U.get('gated_n', 0)} below the gate)", "",
                  _row(["Page", "Sessions", "Conv", "CVR raw", "CVR shrunk",
                        "Wilson LB", "Gate"]),
                  _row(["---"] * 7)]
            for p in pages:
                conv = f"{p.get('conversions', '')}" + ("\\*" if p.get("derived") else "")
                L.append(_row([p.get("page", ""), p.get("sessions", ""), conv,
                               _pct2(p.get("cvr_raw")), _pct2(p.get("cvr_shrunk")),
                               _pct2(p.get("wilson_lb")),
                               "gated" if p.get("gated") else "ok"]))
            L.append("")
        all_rows = ((seg.get("device") or []) + (seg.get("channels") or [])
                    + (seg.get("new_vs_returning") or []) + pages)
        if any(r.get("derived") for r in all_rows):
            L += ["_\\* conversion count derived from sessions × CVR (half-up) — "
                  "the export shipped a rate without a count._", ""]
        for note in V.get("notes", []) or []:
            L += [f"_Note: {note}_", ""]

    # --- findings (ranked by the model's Priority = Impact x 2 + Ease) ---
    if model.get("findings"):
        bucket_legend = " · ".join(f"≥{t} → {label}" for t, label in PRIORITY_BUCKETS[:-1])
        bucket_legend += f" · else {PRIORITY_BUCKETS[-1][1]}"
        ranked = sorted(model["findings"], key=lambda f: -(f.get("priority") or 0))
        L += ["## Findings — prioritised by Impact × 2 + Ease",
              "",
              f"_Ranked by Priority = (Impact × 2) + Ease (missing Impact defaults from "
              f"severity, missing Ease to {DEFAULT_EASE}; NO Confidence — triangulation "
              f"already encodes it); adjust Impact/Ease in the interactive HTML report "
              f"to re-rank. Bucket: {bucket_legend}._",
              "",
              _row(["#", "Finding", "Severity", "Bucket", "Impact", "Ease",
                    "Priority", "Recommendation"]),
              _row(["---"] * 8)]
        for i, f in enumerate(ranked, 1):
            L.append(_row([i, f.get("title", ""), f.get("severity", ""),
                           f.get("bucket", ""), f.get("impact", 0), f.get("ease", 0),
                           f.get("priority", 0), f.get("recommendation", "")]))
        L.append("")

    # --- machine-layer footer ---
    MB = model.get("machine")
    if MB:
        line = (f"_{len(MB.get('applied', []) or [])} analytics fields machine-computed · "
                f"{len(MB.get('corrected', []) or [])} correction(s) applied over the "
                "transcribed payload._")
        L += [line, ""]
        for note in MB.get("notes", []) or []:
            L += [f"_Machine note: {note}_", ""]
    L += ["---",
          f"_Generated {P.get('generated','')} · self-contained interactive HTML and a "
          f"formula-driven .xlsx accompany this record._", ""]
    return "\n".join(L)


def build_markdown(model: dict, path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_md(model), encoding="utf-8")
