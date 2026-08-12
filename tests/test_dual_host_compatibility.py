#!/usr/bin/env python3
"""Derived contract check for Claude Code and Codex marketplace compatibility."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path
from typing import Callable


REPO = Path(__file__).resolve().parents[1]
CLAUDE_ROOT = "${CLAUDE_PLUGIN_ROOT}"
CLAUDE_ROOT_UNBRACED = "$CLAUDE_PLUGIN_ROOT"
PORTABLE_ROOT = "${PLUGIN_ROOT}"
PATH_MARKER = "## Bundled path resolution"
WIDGET_FALLBACK = "If the host cannot render an inline widget"
MARKETPLACE_POLICY = {
    "installation": "AVAILABLE",
    "authentication": "ON_INSTALL",
}
INTERFACE_FIELDS = {
    "displayName",
    "shortDescription",
    "longDescription",
    "developerName",
    "category",
    "capabilities",
    "defaultPrompt",
}
CODEX_MARKETPLACE_ADD = (
    "codex plugin marketplace add "
    "Clickt-Digital-Marketing-Inc/HiveMind-Plugins --ref main"
)
CODEX_MARKETPLACE_VERIFY = "codex plugin marketplace list"
HOST_NEUTRAL_DESCRIPTIONS = {
    "google-ads-management": "conversational fallback",
}
EXPECTED_PLUGIN_ORDER = [
    "google-ads-audit",
    "meta-ads-audit",
    "shopify-cro-audit",
    "cm3-profitability",
    "google-ads-management",
    "memo",
    "project-coordinator",
    "social-media-manager",
    "morning-briefing",
    "wppc-report",
    "catch-up",
    "orchestrator",
    "clickt-reporting",
]


def _load_json(path: Path, errors: list[str]) -> dict:
    if not path.is_file():
        errors.append(f"missing JSON file: {path}")
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"invalid JSON {path}: {exc}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"JSON root must be an object: {path}")
        return {}
    return value


def _plugin_dirs(repo: Path) -> list[Path]:
    plugins = repo / "plugins"
    return sorted(
        path
        for path in plugins.iterdir()
        if path.is_dir() and (path / "skills").is_dir()
    )


def _instruction_files(plugin: Path) -> list[Path]:
    files = list(plugin.rglob("SKILL.md"))
    commands = plugin / "commands"
    if commands.is_dir():
        files.extend(commands.rglob("*.md"))
    files.extend(
        path
        for path in plugin.rglob("*")
        if path.is_file()
        and "references" in path.parts
        and path.suffix in {".md", ".json"}
    )
    return sorted(set(files))


def _owning_skill(path: Path, plugin: Path) -> Path | None:
    if path.name == "SKILL.md":
        return path
    current = path.parent
    while current != plugin.parent:
        candidate = current / "SKILL.md"
        if candidate.is_file():
            return candidate
        if current == plugin:
            break
        current = current.parent
    return None


def _catalog_names(entries: object, label: str, errors: list[str]) -> list[str]:
    if not isinstance(entries, list):
        errors.append(f"{label} marketplace plugins must be an array")
        return []
    names: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append(f"{label} marketplace entries must be objects")
            continue
        names.append(entry.get("name"))
    return names


def validate(repo: Path) -> list[str]:
    errors: list[str] = []
    plugin_dirs = _plugin_dirs(repo)
    directory_names = [path.name for path in plugin_dirs]

    claude_market = _load_json(repo / ".claude-plugin" / "marketplace.json", errors)
    codex_market = _load_json(repo / ".agents" / "plugins" / "marketplace.json", errors)
    claude_entries = claude_market.get("plugins", [])
    codex_entries = codex_market.get("plugins", [])
    claude_names = _catalog_names(claude_entries, "Claude", errors)
    codex_names = _catalog_names(codex_entries, "Codex", errors)

    if codex_market.get("name") != "hivemind-plugins":
        errors.append("Codex marketplace name must be hivemind-plugins")
    if claude_names != EXPECTED_PLUGIN_ORDER:
        errors.append(
            f"Claude marketplace order must remain {EXPECTED_PLUGIN_ORDER}, "
            f"got {claude_names}"
        )

    if sorted(claude_names) != directory_names:
        errors.append(
            f"Claude marketplace plugin set mismatch: expected {directory_names}, "
            f"got {sorted(claude_names)}"
        )
    if codex_names != claude_names:
        errors.append(
            f"Codex marketplace order must match Claude: expected {claude_names}, "
            f"got {codex_names}"
        )
    if len(codex_names) != len(set(codex_names)):
        errors.append("Codex marketplace contains duplicate plugin names")

    claude_by_name = {
        entry.get("name"): entry
        for entry in claude_entries
        if isinstance(entry, dict)
    }
    for entry in codex_entries if isinstance(codex_entries, list) else []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        expected_source = {"source": "local", "path": f"./plugins/{name}"}
        if entry.get("source") != expected_source:
            errors.append(
                f"Codex marketplace source mismatch for {name}: expected {expected_source}"
            )
        if entry.get("policy") != MARKETPLACE_POLICY:
            errors.append(
                f"Codex marketplace policy mismatch for {name}: expected {MARKETPLACE_POLICY}"
            )
        expected_category = str(claude_by_name.get(name, {}).get("category", "")).title()
        if entry.get("category") != expected_category:
            errors.append(
                f"Codex marketplace category mismatch for {name}: "
                f"expected {expected_category}"
            )

    for plugin in plugin_dirs:
        name = plugin.name
        claude_path = plugin / ".claude-plugin" / "plugin.json"
        codex_path = plugin / ".codex-plugin" / "plugin.json"
        if not claude_path.is_file():
            errors.append(f"missing Claude manifest: {name}")
            continue
        if not codex_path.is_file():
            errors.append(f"missing Codex manifest: {name}")
            continue
        claude = _load_json(claude_path, errors)
        codex = _load_json(codex_path, errors)
        for field in ("name", "version"):
            if codex.get(field) != claude.get(field):
                errors.append(f"manifest parity mismatch for {name}.{field}")
        claude_description = claude.get("description")
        codex_description = codex.get("description")
        if name not in HOST_NEUTRAL_DESCRIPTIONS and codex_description != claude_description:
            errors.append(f"manifest parity mismatch for {name}.description")
        if name in HOST_NEUTRAL_DESCRIPTIONS:
            expected_phrase = HOST_NEUTRAL_DESCRIPTIONS[name]
            if not isinstance(codex_description, str) or expected_phrase not in codex_description:
                errors.append(
                    f"{name} Codex description missing host-neutral phrase: {expected_phrase}"
                )
            if "in-Claude" in str(codex_description):
                errors.append(f"{name} Codex description retains host-specific wording")
        if codex.get("name") != name:
            errors.append(f"Codex manifest name must match plugin directory: {name}")
        if codex.get("skills") != "./skills/":
            errors.append(f"Codex manifest skills path mismatch for {name}: expected ./skills/")
        if codex.get("license") != "PolyForm-Shield-1.0.0":
            errors.append(f"Codex manifest license mismatch for {name}")
        author = codex.get("author")
        if not isinstance(author, dict) or not author.get("name"):
            errors.append(f"Codex manifest author.name is required for {name}")
        interface = codex.get("interface")
        if not isinstance(interface, dict):
            errors.append(f"Codex manifest interface is required for {name}")
        else:
            missing = sorted(field for field in INTERFACE_FIELDS if not interface.get(field))
            if missing:
                errors.append(f"Codex manifest interface fields missing for {name}: {missing}")
            prompts = interface.get("defaultPrompt")
            if not isinstance(prompts, list) or not 1 <= len(prompts) <= 3:
                errors.append(f"Codex manifest defaultPrompt must contain 1-3 prompts for {name}")

        for path in _instruction_files(plugin):
            text = path.read_text(encoding="utf-8")
            relative = path.relative_to(repo)
            if CLAUDE_ROOT in text or CLAUDE_ROOT_UNBRACED in text:
                errors.append(f"forbidden host-specific root in live instructions: {relative}")
            if "in-Claude" in text:
                errors.append(f"unqualified in-Claude wording in live instructions: {relative}")
            if "AskUserQuestion" in text:
                errors.append(f"host-specific question tool in live instructions: {relative}")
            if PORTABLE_ROOT in text:
                convention_source = path if "commands" in path.parts else _owning_skill(path, plugin)
                if (
                    convention_source is None
                    or PATH_MARKER not in convention_source.read_text(encoding="utf-8")
                ):
                    errors.append(f"portable root convention missing for live instructions: {relative}")
            if f"{PORTABLE_ROOT}/../" in text:
                errors.append(f"cross-plugin path derived from plugin root: {relative}")

    hub = repo / "plugins/google-ads-management/skills/google-ads/SKILL.md"
    hub_text = hub.read_text(encoding="utf-8") if hub.is_file() else ""
    for phrase in (
        WIDGET_FALLBACK,
        "conversational fallback",
        "Build only the output the user chooses",
        "artifact links",
    ):
        if phrase not in hub_text:
            errors.append(f"widget fallback missing behavior: {phrase}")

    project_skill = repo / "plugins/project-coordinator/skills/project-coordinator/SKILL.md"
    project_text = project_skill.read_text(encoding="utf-8") if project_skill.is_file() else ""
    if "via the Skill tool" in project_text:
        errors.append("project-coordinator retains a host-specific Skill tool invocation")

    social_skill = repo / "plugins/social-media-manager/skills/social-media-manager/SKILL.md"
    social_text = social_skill.read_text(encoding="utf-8") if social_skill.is_file() else ""
    for host_tool in ("WebSearch", "WebFetch"):
        if host_tool in social_text:
            errors.append(f"social-media-manager retains host-specific web tool: {host_tool}")
    if "If web access is unavailable" not in social_text:
        errors.append("social-media-manager web workflow missing unavailable-web fallback")

    readme_path = repo / "README.md"
    readme = readme_path.read_text(encoding="utf-8") if readme_path.is_file() else ""
    readme_contract = " ".join(readme.split())
    for phrase in (
        "### Claude Code",
        "### Codex",
        CODEX_MARKETPLACE_ADD,
        CODEX_MARKETPLACE_VERIFY,
        "Plugins Directory",
        "does not register or install the marketplace",
        "Start a new task",
    ):
        if phrase not in readme_contract:
            errors.append(f"README dual-host installation contract missing: {phrase}")
    for name in claude_names:
        claude_command = f"/plugin install {name}@hivemind-plugins"
        codex_command = f"codex plugin add {name}@hivemind-plugins"
        if claude_command not in readme_contract:
            errors.append(f"README Claude plugin install command missing: {name}")
        if codex_command not in readme_contract:
            errors.append(f"README Codex plugin install command missing: {name}")

    return errors


def _copy_contract_tree(source: Path, destination: Path) -> None:
    shutil.copy2(source / "README.md", destination / "README.md")
    shutil.copytree(source / ".agents", destination / ".agents")
    shutil.copytree(source / ".claude-plugin", destination / ".claude-plugin")
    for plugin in _plugin_dirs(source):
        target = destination / "plugins" / plugin.name
        shutil.copytree(plugin / ".claude-plugin", target / ".claude-plugin")
        shutil.copytree(plugin / ".codex-plugin", target / ".codex-plugin")
        for path in _instruction_files(plugin):
            output = target / path.relative_to(plugin)
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, output)


def _rewrite_json(path: Path, update: Callable[[dict], None]) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    update(payload)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def run_mutation_sweep(repo: Path) -> tuple[list[str], int]:
    failures: list[str] = []
    count = 0
    with tempfile.TemporaryDirectory(prefix="hm911-dual-host-") as raw:
        mutant = Path(raw)
        _copy_contract_tree(repo, mutant)

        def exercise(label: str, path: Path, mutate: Callable[[], None], expected: str) -> None:
            nonlocal count
            count += 1
            original = path.read_bytes() if path.exists() else None
            mutate()
            errors = validate(mutant)
            if not any(expected in error for error in errors):
                failures.append(
                    f"mutation {label!r} missed {expected!r}; errors were {errors}"
                )
            if original is None:
                path.unlink(missing_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(original)

        audit_manifest = mutant / "plugins/google-ads-audit/.codex-plugin/plugin.json"
        exercise(
            "missing Codex manifest",
            audit_manifest,
            audit_manifest.unlink,
            "missing Codex manifest: google-ads-audit",
        )

        market = mutant / ".agents/plugins/marketplace.json"
        exercise(
            "marketplace name",
            market,
            lambda: _rewrite_json(
                market, lambda payload: payload.update({"name": "renamed-marketplace"})
            ),
            "Codex marketplace name must be hivemind-plugins",
        )
        exercise(
            "invalid marketplace source",
            market,
            lambda: _rewrite_json(
                market,
                lambda payload: payload["plugins"][0].update({"source": "./plugins/bad"}),
            ),
            "Codex marketplace source mismatch",
        )
        exercise(
            "marketplace policy",
            market,
            lambda: _rewrite_json(
                market,
                lambda payload: payload["plugins"][0]["policy"].update(
                    {"installation": "DISABLED"}
                ),
            ),
            "Codex marketplace policy mismatch",
        )
        exercise(
            "marketplace category",
            market,
            lambda: _rewrite_json(
                market,
                lambda payload: payload["plugins"][0].update(
                    {"category": "Productivity"}
                ),
            ),
            "Codex marketplace category mismatch",
        )
        exercise(
            "catalog order drift",
            market,
            lambda: _rewrite_json(
                market,
                lambda payload: payload["plugins"].reverse(),
            ),
            "Codex marketplace order must match Claude",
        )
        exercise(
            "duplicate marketplace plugin",
            market,
            lambda: _rewrite_json(
                market,
                lambda payload: payload["plugins"][1].update(
                    {"name": payload["plugins"][0]["name"]}
                ),
            ),
            "Codex marketplace contains duplicate plugin names",
        )

        claude_market = mutant / ".claude-plugin/marketplace.json"
        exercise(
            "Claude catalog set",
            claude_market,
            lambda: _rewrite_json(
                claude_market,
                lambda payload: payload["plugins"][0].update(
                    {"name": "renamed-google-ads-audit"}
                ),
            ),
            "Claude marketplace plugin set mismatch",
        )
        exercise(
            "Claude catalog order",
            claude_market,
            lambda: _rewrite_json(
                claude_market,
                lambda payload: payload["plugins"].reverse(),
            ),
            "Claude marketplace order must remain",
        )

        audit_claude_manifest = (
            mutant / "plugins/google-ads-audit/.claude-plugin/plugin.json"
        )
        exercise(
            "missing Claude manifest",
            audit_claude_manifest,
            audit_claude_manifest.unlink,
            "missing Claude manifest: google-ads-audit",
        )
        exercise(
            "manifest version parity",
            audit_manifest,
            lambda: _rewrite_json(
                audit_manifest, lambda payload: payload.update({"version": "9.9.9"})
            ),
            "manifest parity mismatch for google-ads-audit.version",
        )
        exercise(
            "manifest description parity",
            audit_manifest,
            lambda: _rewrite_json(
                audit_manifest,
                lambda payload: payload.update({"description": "Changed description"}),
            ),
            "manifest parity mismatch for google-ads-audit.description",
        )
        exercise(
            "manifest skills path",
            audit_manifest,
            lambda: _rewrite_json(
                audit_manifest, lambda payload: payload.update({"skills": "./bad/"})
            ),
            "Codex manifest skills path mismatch for google-ads-audit",
        )
        exercise(
            "manifest license",
            audit_manifest,
            lambda: _rewrite_json(
                audit_manifest, lambda payload: payload.update({"license": "MIT"})
            ),
            "Codex manifest license mismatch for google-ads-audit",
        )
        exercise(
            "manifest author",
            audit_manifest,
            lambda: _rewrite_json(
                audit_manifest, lambda payload: payload.update({"author": {}})
            ),
            "Codex manifest author.name is required for google-ads-audit",
        )
        exercise(
            "manifest interface field",
            audit_manifest,
            lambda: _rewrite_json(
                audit_manifest,
                lambda payload: payload["interface"].pop("capabilities"),
            ),
            "Codex manifest interface fields missing for google-ads-audit",
        )
        exercise(
            "manifest default prompts",
            audit_manifest,
            lambda: _rewrite_json(
                audit_manifest,
                lambda payload: payload["interface"].update({"defaultPrompt": []}),
            ),
            "Codex manifest defaultPrompt must contain 1-3 prompts for google-ads-audit",
        )

        management_manifest = (
            mutant / "plugins/google-ads-management/.codex-plugin/plugin.json"
        )
        exercise(
            "Google Ads host-neutral description",
            management_manifest,
            lambda: _rewrite_json(
                management_manifest,
                lambda payload: payload.update(
                    {
                        "description": payload["description"].replace(
                            "conversational fallback", "host-specific fallback"
                        )
                    }
                ),
            ),
            "google-ads-management Codex description missing host-neutral phrase",
        )

        audit_skill = mutant / "plugins/google-ads-audit/skills/google-ads-audit/SKILL.md"
        exercise(
            "host-specific root",
            audit_skill,
            lambda: audit_skill.write_text(
                audit_skill.read_text(encoding="utf-8") + f"\n{CLAUDE_ROOT}\n",
                encoding="utf-8",
            ),
            "forbidden host-specific root in live instructions",
        )
        exercise(
            "unbraced host-specific root",
            audit_skill,
            lambda: audit_skill.write_text(
                audit_skill.read_text(encoding="utf-8")
                + f"\n{CLAUDE_ROOT_UNBRACED}/script.py\n",
                encoding="utf-8",
            ),
            "forbidden host-specific root in live instructions",
        )
        exercise(
            "portable root convention",
            audit_skill,
            lambda: audit_skill.write_text(
                audit_skill.read_text(encoding="utf-8").replace(PATH_MARKER, "## Removed"),
                encoding="utf-8",
            ),
            "portable root convention missing for live instructions",
        )
        exercise(
            "cross-plugin root traversal",
            audit_skill,
            lambda: audit_skill.write_text(
                audit_skill.read_text(encoding="utf-8")
                + f"\n{PORTABLE_ROOT}/../other-plugin/script.py\n",
                encoding="utf-8",
            ),
            "cross-plugin path derived from plugin root",
        )

        merge_command = mutant / "plugins/orchestrator/commands/merge-gate.md"
        exercise(
            "command instruction scan",
            merge_command,
            lambda: merge_command.write_text(
                merge_command.read_text(encoding="utf-8") + "\nAskUserQuestion\n",
                encoding="utf-8",
            ),
            "host-specific question tool in live instructions",
        )

        catch_up_skill = mutant / "plugins/catch-up/skills/catch-up-setup/SKILL.md"
        exercise(
            "host-specific question tool",
            catch_up_skill,
            lambda: catch_up_skill.write_text(
                catch_up_skill.read_text(encoding="utf-8") + "\nAskUserQuestion\n",
                encoding="utf-8",
            ),
            "host-specific question tool in live instructions",
        )
        exercise(
            "host-specific prose",
            catch_up_skill,
            lambda: catch_up_skill.write_text(
                catch_up_skill.read_text(encoding="utf-8") + "\nin-Claude flow\n",
                encoding="utf-8",
            ),
            "unqualified in-Claude wording in live instructions",
        )

        hub = mutant / "plugins/google-ads-management/skills/google-ads/SKILL.md"
        exercise(
            "widget fallback",
            hub,
            lambda: hub.write_text(
                hub.read_text(encoding="utf-8").replace(WIDGET_FALLBACK, "Fallback removed"),
                encoding="utf-8",
            ),
            "widget fallback missing behavior",
        )
        for phrase in (
            "conversational fallback",
            "Build only the output the user chooses",
            "artifact links",
        ):
            exercise(
                f"widget behavior: {phrase}",
                hub,
                lambda phrase=phrase: hub.write_text(
                    hub.read_text(encoding="utf-8").replace(phrase, "Behavior removed"),
                    encoding="utf-8",
                ),
                f"widget fallback missing behavior: {phrase}",
            )

        project_skill = mutant / "plugins/project-coordinator/skills/project-coordinator/SKILL.md"
        exercise(
            "host-specific Skill tool",
            project_skill,
            lambda: project_skill.write_text(
                project_skill.read_text(encoding="utf-8") + "\nInvoke via the Skill tool.\n",
                encoding="utf-8",
            ),
            "project-coordinator retains a host-specific Skill tool invocation",
        )

        social_skill = mutant / "plugins/social-media-manager/skills/social-media-manager/SKILL.md"
        exercise(
            "host-specific web tool",
            social_skill,
            lambda: social_skill.write_text(
                social_skill.read_text(encoding="utf-8") + "\nUse WebSearch now.\n",
                encoding="utf-8",
            ),
            "social-media-manager retains host-specific web tool: WebSearch",
        )
        exercise(
            "unavailable-web fallback",
            social_skill,
            lambda: social_skill.write_text(
                social_skill.read_text(encoding="utf-8").replace(
                    "If web access is unavailable", "When the network cannot be used"
                ),
                encoding="utf-8",
            ),
            "social-media-manager web workflow missing unavailable-web fallback",
        )

        readme = mutant / "README.md"
        exercise(
            "Codex marketplace registration",
            readme,
            lambda: readme.write_text(
                readme.read_text(encoding="utf-8").replace("--ref main", "--ref next"),
                encoding="utf-8",
            ),
            f"README dual-host installation contract missing: {CODEX_MARKETPLACE_ADD}",
        )
        for label, raw_phrase, expected_phrase in (
            ("Claude install section", "### Claude Code", "### Claude Code"),
            ("Codex install section", "### Codex", "### Codex"),
            (
                "Codex marketplace verification",
                CODEX_MARKETPLACE_VERIFY,
                CODEX_MARKETPLACE_VERIFY,
            ),
            ("Plugins Directory installation", "Plugins Directory", "Plugins Directory"),
            (
                "clone is not install",
                "does not register or install",
                "does not register or install the marketplace",
            ),
            ("new-task reload", "Start a new task", "Start a new task"),
        ):
            exercise(
                label,
                readme,
                lambda raw_phrase=raw_phrase: readme.write_text(
                    readme.read_text(encoding="utf-8").replace(
                        raw_phrase, "Contract phrase removed"
                    ),
                    encoding="utf-8",
                ),
                f"README dual-host installation contract missing: {expected_phrase}",
            )
        exercise(
            "derived install command",
            readme,
            lambda: readme.write_text(
                readme.read_text(encoding="utf-8").replace(
                    "codex plugin add clickt-reporting@hivemind-plugins",
                    "codex plugin add renamed-reporting@hivemind-plugins",
                ),
                encoding="utf-8",
            ),
            "README Codex plugin install command missing: clickt-reporting",
        )
        exercise(
            "derived Claude install command",
            readme,
            lambda: readme.write_text(
                readme.read_text(encoding="utf-8").replace(
                    "/plugin install clickt-reporting@hivemind-plugins",
                    "/plugin install renamed-reporting@hivemind-plugins",
                ),
                encoding="utf-8",
            ),
            "README Claude plugin install command missing: clickt-reporting",
        )

    return failures, count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mutation-sweep", action="store_true")
    args = parser.parse_args()

    errors = validate(REPO)
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print(f"PASS: dual-host contract covers {len(_plugin_dirs(REPO))} derived plugins")

    if args.mutation_sweep:
        failures, count = run_mutation_sweep(REPO)
        if failures:
            for failure in failures:
                print(f"FAIL: {failure}")
            return 1
        print(f"PASS: {count} compatibility mutations produced their specific red signals")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
