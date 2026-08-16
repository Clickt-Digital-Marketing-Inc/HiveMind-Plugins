#!/usr/bin/env python3
"""Run the in-Claude tuner JS<->Python parity harness across the tunable skills.

Usage:
    python3 run_parity.py                       # every skill + the analytics gate
                                                 # + every tunable skill's kernel gate
    python3 run_parity.py budget-pacing ...     # a subset, by id
    python3 run_parity.py analytics-primitives  # just the _shared/analytics.py gate
    python3 run_parity.py conversions-tracking-kernel  # just one kernel gate

Dev-only — requires jsdom: run `npm install` in this directory first.

Per skill the harness:
  1. emits the tuner JSON               build_<x>_report.py --formats "" --emit-widget w.json
  2. assembles the widget               references/build_widget.py --data w.json --out w.html
  3. computes Python default+tuned      _compute_expected.py (isolated subprocess)
  4. drives the widget under jsdom       tuner_parity.mjs w.html expected.json
     asserting JS<->Python parity (default + tuned) and the Save direct-write prompt.

Skills whose builder has no --emit-widget yet are reported PENDING (not failed),
so the harness is green-able incrementally as the rollout lands.

The three M2 "direct JS_KERNEL" tunable skills (bidding-strategy,
competitive-analysis, conversions-tracking) don't go through that widget path —
each ships its own self-contained per-skill gate script (KERNEL_GATES below);
this harness just shells each one out and reports its OK/FAIL alongside the
SKILLS list, so one command (`run_parity.py`, no args) covers every tunable
skill's kernel (HM-571).

Exit 0 unless a runnable skill or kernel gate FAILS.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent      # .../skills/google-ads/tests
HUB = HERE.parent                           # .../skills/google-ads
SKILLS_ROOT = HUB.parent                    # .../skills
PLUGIN_ROOT = SKILLS_ROOT.parent            # .../google-ads-management
BUILD_WIDGET = HUB / "references" / "build_widget.py"
PY = sys.executable
NODE = "node"

# The shared analytics primitives (HM-532) are gated as a pseudo-skill:
# Python (_shared/analytics.py) vs its canonical JS_MIRROR on shared vectors.
ANALYTICS_ID = "analytics-primitives"

# tune_value picks are slider/number values that move a KPI for that skill's
# committed fixture (the harness fails loudly if a tune is vacuous).
SKILLS = [
    {"id": "quality-score", "skill": "google-ads-quality-score",
     "builder": "build_qs_report.py", "core": "qs_core",
     "fixture": "tests/sample-findings.json",
     "tune_key": "qs_low_threshold", "tune_value": "4", "brand": "Acme Corp"},
    {"id": "budget-pacing", "skill": "google-ads-budget-pacing",
     "builder": "build_budget_report.py", "core": "budget_core",
     "fixture": "tests/sample-findings.json",
     "tune_key": "min_budget_multiple", "tune_value": "50", "brand": "Acme Corp"},
    {"id": "keywords-search-terms", "skill": "google-ads-keywords-search-terms",
     "builder": "build_waste_filter.py", "core": "waste_filter_core",
     "fixture": "tests/sample-findings.json",
     "tune_key": "cost_multiple", "tune_value": "3.0", "brand": "Acme Corp",
     "kpi_map": {"b1": "block1", "b2": "block2"},
     # Also exercise the checkbox-group ("multi") control: unchecking PHRASE drops
     # the lone Block-1 term from scope, so b1 moves (non-vacuous). The harness
     # asserts the live JS recompute still matches Python after the toggle.
     "multi_tune": {"key": "match_types_in_scope", "drop": "PHRASE"}},
    {"id": "performance-reporting", "skill": "google-ads-performance-reporting",
     "builder": "build_perf_report.py", "core": "perf_core",
     "fixture": "tests/sample-findings.json",
     "tune_key": "roas_goal", "tune_value": "8.0", "brand": "Acme Corp"},
    # ROAS sliders are vacuous on this fixture (winner/loser ratios sit outside the
    # slider range), so tune min_cost (a control that moves KPIs) for parity.
    {"id": "pmax-campaigns", "skill": "google-ads-pmax-campaigns",
     "builder": "build_pmax_filter.py", "core": "pmax_core",
     "fixture": "tests/sample-findings-pmax.json",
     "tune_key": "min_cost", "tune_value": "500", "brand": "Acme Corp",
     "kpi_map": {"b1": "block1", "b2": "block2"}},
    {"id": "pmax-listing-groups", "skill": "google-ads-pmax-listing-groups",
     "builder": "build_pmax_listing_filter.py", "core": "pmax_listing_core",
     "fixture": "tests/sample-pmax-findings.json",
     "tune_key": "expensiveness_factor", "tune_value": "1.0", "brand": "Acme Corp"},
    {"id": "products", "skill": "google-ads-products",
     "builder": "build_product_report.py", "core": "product_filter_core",
     "fixture": "tests/product-sample-findings.json",
     "tune_key": "surge_multiple", "tune_value": "1.2", "brand": "Acme Corp"},
    # Bounded-embed (HM-339): a large fixture (860 terms) where the widget embeds
    # only the in-play envelope. `trim` turns on the extra assertions in
    # tuner_parity.mjs (embed < universe, honest counts, sensitivity + near-miss
    # parity from the trimmed embed). tune cost_multiple DOWN to flag more (2.5->1.5).
    {"id": "keywords-search-terms-large", "skill": "google-ads-keywords-search-terms",
     "builder": "build_waste_filter.py", "core": "waste_filter_core",
     "fixture": "tests/sample-findings-large.json",
     "tune_key": "cost_multiple", "tune_value": "1.5", "brand": "Acme Corp",
     "kpi_map": {"b1": "block1", "b2": "block2"}, "trim": True},
    # Bounded-embed fast-follow: products envelope = status=="scored" (drops the
    # inactive long tail; this skill has no near-miss panel so scored is complete).
    # tune surge_multiple DOWN (1.5->1.2) to flag more surging.
    {"id": "products-large", "skill": "google-ads-products",
     "builder": "build_product_report.py", "core": "product_filter_core",
     "fixture": "tests/product-sample-findings-large.json",
     "tune_key": "surge_multiple", "tune_value": "1.2", "brand": "Synthetic Store", "trim": True},
]


def run_skill(s: dict, tmp: Path):
    sdir = SKILLS_ROOT / s["skill"]
    builder = sdir / "scripts" / s["builder"]
    fixture = sdir / s["fixture"]
    if not builder.exists():
        return "FAIL", f"builder not found: {builder}"
    if "emit-widget" not in builder.read_text(encoding="utf-8"):
        return "PENDING", "builder has no --emit-widget yet"
    if not fixture.exists():
        return "FAIL", f"fixture not found: {fixture}"

    wjson = tmp / f"{s['id']}.widget.json"
    whtml = tmp / f"{s['id']}.widget.html"
    expf = tmp / f"{s['id']}.expected.json"

    r = subprocess.run([PY, str(builder), "--input", str(fixture), "--formats", "",
                        "--brand", s["brand"], "--emit-widget", str(wjson)],
                       capture_output=True, text=True)
    if r.returncode != 0 or not wjson.exists():
        return "FAIL", f"emit failed: {(r.stderr or r.stdout).strip()}"
    widget = json.loads(wjson.read_text(encoding="utf-8"))
    kpi_keys = [k["key"] for k in widget["spec"].get("kpis", [])]
    if not kpi_keys:
        return "FAIL", "emitted widget has no KPIs"

    r = subprocess.run([PY, str(BUILD_WIDGET), "--data", str(wjson), "--out", str(whtml)],
                       capture_output=True, text=True)
    if r.returncode != 0 or not whtml.exists():
        return "FAIL", f"assemble failed: {r.stderr.strip()}"

    mt = s.get("multi_tune")
    expect_cmd = [PY, str(HERE / "_compute_expected.py"), str(sdir / "scripts"),
                  s["core"], str(fixture), s["tune_key"], str(s["tune_value"])]
    if mt:
        expect_cmd += [mt["key"], mt["drop"]]
    r = subprocess.run(expect_cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return "FAIL", f"python expected failed: {r.stderr.strip()}"
    comp = json.loads(r.stdout)
    expected = {
        "skill": s["id"], "kpi_keys": kpi_keys,
        "default": comp["default"], "tuned": comp["tuned"],
        "tune_key": s["tune_key"], "tune_value": comp["tune_value"],
        "filename_stem": widget["save"]["filename_stem"],
        "kpi_map": s.get("kpi_map", {}),
    }
    if mt:
        expected["multi_tune"] = mt
        expected["multi_scope"] = comp["multi_scope"]
        expected["multi_tuned"] = comp["multi_tuned"]
    if s.get("trim"):
        expected["trim"] = True
        expected["universe_total"] = widget["embed"].get("total_rows")
        expected["sensitivity"] = comp.get("sensitivity", [])
        expected["near_miss_terms"] = comp.get("near_miss_terms", [])
    expf.write_text(json.dumps(expected), encoding="utf-8")

    r = subprocess.run([NODE, str(HERE / "tuner_parity.mjs"), str(whtml), str(expf)],
                       capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    return ("OK" if r.returncode == 0 else "FAIL"), out


# Per-skill JS<->Python kernel-parity gates for the 3 M2 "direct JS_KERNEL"
# tunable skills. Each script is self-contained (owns its own fixture +
# scenarios + node subprocess) — this harness only shells it out and reports
# OK/FAIL, never re-implements its logic.
KERNEL_GATES = [
    {"id": "bidding-strategy-kernel",
     "script": SKILLS_ROOT / "google-ads-bidding-strategy" / "tests" / "js_kernel_parity.py"},
    {"id": "competitive-analysis-kernel",
     "script": SKILLS_ROOT / "google-ads-competitive-analysis" / "tests" / "test_widget_kernel_parity.py"},
    {"id": "conversions-tracking-kernel",
     "script": SKILLS_ROOT / "google-ads-conversions-tracking" / "tests" / "js_kernel_parity.py"},
]


def run_kernel_gate(g: dict):
    script = g["script"]
    if not script.exists():
        return "FAIL", f"gate script not found: {script}"
    r = subprocess.run([PY, str(script)], capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    return ("OK" if r.returncode == 0 else "FAIL"), out


def run_analytics(tmp: Path):
    """Parity-gate the shared analytics primitives (Python vs JS_MIRROR).

    Vectors auto-discovered from _shared/tests/analytics_vectors*.json plus
    any per-skill skills/*/tests/analytics_vectors*.json (the orchestration
    pattern: parallel skill agents add fixtures, never edit this harness)."""
    vecs = sorted((PLUGIN_ROOT / "_shared" / "tests").glob("analytics_vectors*.json"))
    vecs += sorted(SKILLS_ROOT.glob("*/tests/analytics_vectors*.json"))
    if not vecs:
        return "FAIL", "no analytics_vectors*.json fixtures found"
    r = subprocess.run([PY, str(HERE / "_compute_expected.py"), "--analytics",
                        *[str(v) for v in vecs]], capture_output=True, text=True)
    if r.returncode != 0:
        return "FAIL", f"python expected failed: {r.stderr.strip()}"
    expf = tmp / "analytics.expected.json"
    expf.write_text(r.stdout, encoding="utf-8")
    r = subprocess.run([NODE, str(HERE / "tuner_parity.mjs"), "--analytics", str(expf)],
                       capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    return ("OK" if r.returncode == 0 else "FAIL"), out


def main() -> int:
    ids = sys.argv[1:]
    known = {s["id"] for s in SKILLS} | {ANALYTICS_ID} | {g["id"] for g in KERNEL_GATES}
    unknown = set(ids) - known
    if unknown:
        print("unknown skill id(s):", ", ".join(sorted(unknown)))
        print("known:", ", ".join([ANALYTICS_ID] + [s["id"] for s in SKILLS]
                                   + [g["id"] for g in KERNEL_GATES]))
        return 2
    todo = [s for s in SKILLS if not ids or s["id"] in ids]
    run_analytics_gate = not ids or ANALYTICS_ID in ids
    todo_kernel_gates = [g for g in KERNEL_GATES if not ids or g["id"] in ids]

    results = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        if run_analytics_gate:
            status, detail = run_analytics(tmp)
            head = f"[{status:7}] {ANALYTICS_ID}"
            if status == "OK":
                print(head)
                if detail:
                    print(detail)
            else:
                print(head + (f"  — {detail}" if detail else ""))
            results.append(status)
        for g in todo_kernel_gates:
            status, detail = run_kernel_gate(g)
            head = f"[{status:7}] {g['id']}"
            if status == "OK":
                print(head)
                if detail:
                    print(detail)
            else:
                print(head + (f"  — {detail}" if detail else ""))
            results.append(status)
        for s in todo:
            status, detail = run_skill(s, tmp)
            head = f"[{status:7}] {s['id']}"
            if status == "OK":
                print(head)
                if detail:
                    print(detail)
            else:
                print(head + (f"  — {detail}" if detail else ""))
            results.append(status)

    oks, pend, fails = (results.count(x) for x in ("OK", "PENDING", "FAIL"))
    print(f"\n{oks} OK · {pend} pending · {fails} failed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
