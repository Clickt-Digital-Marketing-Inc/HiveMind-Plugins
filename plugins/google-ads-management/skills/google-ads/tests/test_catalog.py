#!/usr/bin/env python3
"""Guard the Google Ads hub catalog against drift.

Asserts every catalog task maps to a real installed skill (by SKILL.md `name:`),
that every enum-ish field uses an allowed value, and that the `tunable` flag
stays in sync with reality: a skill is `tunable` iff some builder wires
`--emit-widget` (a bundle scripts/build_*.py, or a bespoke flat builder like
cm3's cm3_by_product.py), and any tunable task must list `html` in formats and
define tuner controls (a *_spec.py HTML_CONTROLS, or a bespoke
build_widget_fragment). Stdlib only.

Run: python3 tests/test_catalog.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
SKILL_DIR = HERE.parents[1]                 # .../skills/google-ads
CATALOG = SKILL_DIR / "references" / "catalog.json"
REPO_ROOT = HERE.parents[5]                 # repo root
PLUGINS = REPO_ROOT / "plugins"

ALLOWED_GROUPS = {"Management", "Audit", "Profitability"}
ALLOWED_INPUTS = {"mcp", "csv"}
ALLOWED_FORMATS = {"md", "html", "xlsx", "pptx", "csv"}
REQUIRED_TASK_KEYS = {"id", "skill", "plugin", "group", "label", "blurb", "inputs", "window", "formats"}


def skill_name(skill_md: Path):
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    front = text[3:end] if end != -1 else text
    for line in front.splitlines():
        if line.strip().startswith("name:"):
            return line.split(":", 1)[1].strip()
    return None


def installed_skill_names():
    names = set()
    for md in PLUGINS.glob("*/skills/*/SKILL.md"):
        n = skill_name(md)
        if n:
            names.add(n)
    return names


def skill_dir_map():
    """name (SKILL.md `name:`) -> skill directory."""
    out = {}
    for md in PLUGINS.glob("*/skills/*/SKILL.md"):
        n = skill_name(md)
        if n:
            out[n] = md.parent
    return out


def _any_file_contains(paths, needle):
    for p in paths:
        try:
            if needle in p.read_text(encoding="utf-8"):
                return True
        except OSError:
            continue
    return False


def run():
    failures = []

    def check(cond, msg):
        if not cond:
            failures.append(msg)

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    marketplace = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    marketplace_plugins = {entry["name"] for entry in marketplace["plugins"]}
    names = installed_skill_names()
    dirs = skill_dir_map()
    check(bool(names), "no installed skills discovered under plugins/*/skills/*/SKILL.md")

    # route templates — on-demand mcp/csv analyze first (no {formats}); *_upfront
    # templates build directly and carry {formats}.
    rt = catalog.get("routeTemplates", {})
    for kind in ("mcp", "csv"):
        check(kind in rt, f"routeTemplates missing '{kind}'")
        tpl = rt.get(kind, "")
        for tok in ("{skill}", "{notes}"):
            check(tok in tpl, f"routeTemplates['{kind}'] missing placeholder {tok}")
    check("{account}" in rt.get("mcp", ""), "mcp template missing {account}")
    check("{window}" in rt.get("mcp", ""), "mcp template missing {window}")
    check("{files}" in rt.get("csv", ""), "csv template missing {files}")
    for key, tpl in rt.items():
        if key.endswith("_upfront"):
            for tok in ("{skill}", "{formats}", "{notes}"):
                check(tok in tpl, f"routeTemplates['{key}'] missing placeholder {tok}")

    ids = set()
    for t in catalog.get("tasks", []):
        tid = t.get("id", "<no id>")
        missing = REQUIRED_TASK_KEYS - set(t)
        check(not missing, f"task '{tid}' missing keys: {sorted(missing)}")
        check(tid not in ids, f"duplicate task id '{tid}'")
        ids.add(tid)
        check(t.get("skill") in names,
              f"task '{tid}' -> skill '{t.get('skill')}' not found among installed skills")
        check(t.get("plugin") in marketplace_plugins,
              f"task '{tid}' advertises plugin '{t.get('plugin')}' absent from this marketplace")
        check(t.get("group") in ALLOWED_GROUPS, f"task '{tid}' bad group '{t.get('group')}'")
        check(t.get("group") in catalog.get("groups", []),
              f"task '{tid}' group '{t.get('group')}' not in catalog.groups")
        check(t.get("inputs") in ALLOWED_INPUTS, f"task '{tid}' bad inputs '{t.get('inputs')}'")
        check(isinstance(t.get("window"), bool), f"task '{tid}' window must be bool")
        fmts = t.get("formats", [])
        check(bool(fmts) and set(fmts) <= ALLOWED_FORMATS,
              f"task '{tid}' formats {fmts} not subset of {sorted(ALLOWED_FORMATS)}")
        for f in t.get("optIn", []):
            check(f in fmts, f"task '{tid}' optIn '{f}' not in its formats")
        # formats_upfront tasks pick formats in the launcher -> need a matching template
        fu = t.get("formats_upfront")
        if fu is not None:
            check(isinstance(fu, bool), f"task '{tid}' formats_upfront must be bool, got {fu!r}")
        if fu:
            upkey = f"{t.get('inputs')}_upfront"
            check(upkey in rt, f"task '{tid}' formats_upfront but no routeTemplates['{upkey}']")
            check(not t.get("tunable"), f"task '{tid}' can't be both tunable and formats_upfront")
        if t.get("inputs") == "csv":
            files = t.get("files", [])
            check(bool(files), f"csv task '{tid}' has no files[]")
            for f in files:
                check("key" in f and "label" in f, f"task '{tid}' file entry missing key/label")

        # --- tunable drift guard (layout-agnostic: bundle scripts/ or bespoke flat) ---
        tunable = t.get("tunable")
        if tunable is not None:
            check(isinstance(tunable, bool), f"task '{tid}' tunable must be bool, got {tunable!r}")
        sdir = dirs.get(t.get("skill"))
        scripts = (sdir / "scripts") if sdir else None
        # Candidate builder/spec/renderer files: skill-root *.py (bespoke, e.g. cm3's
        # cm3_by_product.py + cm3_html.py) plus scripts/*.py (bundle build_*.py + *_spec.py).
        # tests/ and __pycache__ are excluded by construction (only direct globs).
        py_files = []
        if sdir:
            py_files += sorted(sdir.glob("*.py"))
            if scripts and scripts.is_dir():
                py_files += sorted(scripts.glob("*.py"))
        # The catalog flag must match reality: tunable iff some builder wires --emit-widget.
        emit = _any_file_contains(py_files, "emit-widget")
        check(bool(tunable) == emit,
              f"task '{tid}' tunable={bool(tunable)} but a builder with --emit-widget present={emit} "
              f"(the catalog flag must match the wired tuner)")
        if tunable:
            check("html" in fmts, f"tunable task '{tid}' must list 'html' in formats, got {fmts}")
            # Tuner controls live either in a bundle *_spec.py (HTML_CONTROLS) or in a
            # bespoke renderer's build_widget_fragment (cm3's cm3_html.py).
            has_controls = (_any_file_contains(py_files, "HTML_CONTROLS")
                            or _any_file_contains(py_files, "build_widget_fragment"))
            check(has_controls,
                  f"tunable task '{tid}' defines no tuner controls "
                  f"(a scripts/*_spec.py with HTML_CONTROLS, or a bespoke build_widget_fragment)")

    if failures:
        print("FAIL — %d problem(s):" % len(failures))
        for f in failures:
            print("  - " + f)
        return 1
    n_tunable = sum(1 for t in catalog.get("tasks", []) if t.get("tunable"))
    print("OK — %d tasks, all map to installed skills; enums valid; "
          "%d tunable, each matching its wired --emit-widget builder + HTML_CONTROLS."
          % (len(catalog.get("tasks", [])), n_tunable))
    return 0


if __name__ == "__main__":
    sys.exit(run())
