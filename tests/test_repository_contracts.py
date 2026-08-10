from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MARKETPLACE = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
PLUGIN_NAMES = sorted(entry["name"] for entry in MARKETPLACE["plugins"])


def test_marketplace_population_matches_plugin_directories() -> None:
    directories = sorted(
        path.name
        for path in (ROOT / "plugins").iterdir()
        if path.is_dir() and (path / ".claude-plugin/plugin.json").is_file()
    )
    assert PLUGIN_NAMES == directories


def test_readme_documents_every_installable_plugin_and_private_access() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "repository is private" in readme
    assert "granted read" in readme and "access" in readme
    assert "public and every plugin" not in readme
    assert "No signup" not in readme
    for name in PLUGIN_NAMES:
        assert f"**{name}**" in readme
        assert f"/plugin install {name}@hivemind-plugins" in readme
    for required in (
        "Python >=3.11", "pandas>=2.0", "pyyaml>=6.0", "click>=8.1",
        "openpyxl>=3.1", "vl-convert-python==1.7.0",
    ):
        assert required in readme


def test_plugin_manifest_versions_match_marketplace() -> None:
    for entry in MARKETPLACE["plugins"]:
        manifest = json.loads(
            (ROOT / entry["source"] / ".claude-plugin/plugin.json").read_text(encoding="utf-8")
        )
        assert manifest["name"] == entry["name"]
        assert manifest["version"] == entry["version"]


def test_local_markdown_links_resolve() -> None:
    broken: list[str] = []
    pattern = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
    for markdown in sorted(ROOT.rglob("*.md")):
        if ".git" in markdown.parts or "node_modules" in markdown.parts or markdown.name.endswith(".template.md"):
            continue
        for raw in pattern.findall(markdown.read_text(encoding="utf-8", errors="replace")):
            if raw.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target = raw.split("#", 1)[0]
            if target and "{{" not in target and not (markdown.parent / target).exists():
                broken.append(f"{markdown.relative_to(ROOT)} -> {raw}")
    assert not broken, "broken local Markdown links:\n" + "\n".join(broken)


def test_google_ads_hub_advertises_only_marketplace_plugins() -> None:
    catalog_path = ROOT / "plugins/google-ads-management/skills/google-ads/references/catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    advertised = {task["plugin"] for task in catalog["tasks"]}
    assert advertised <= set(PLUGIN_NAMES)
    surfaces = [
        ROOT / "plugins/google-ads-management/README.md",
        ROOT / "plugins/google-ads-management/skills/google-ads/SKILL.md",
        catalog_path,
    ]
    for surface in surfaces:
        assert "MediaMetrics" not in surface.read_text(encoding="utf-8")


def test_clickt_reporting_onboarding_has_no_personal_or_client_defaults() -> None:
    root = ROOT / "plugins/clickt-reporting"
    banned = (
        "PantryLot", "John's", "John ", "/Users/" + "johngreenhow",
        "5.161.204.210", "root@", "544-317-0313", "5443170313",
        "318-624-6648", "581-043-2788", "1182016997374640",
        "507568174", "507576481",
    )
    failures: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or "node_modules" in path.parts:
            continue
        if path.suffix.lower() not in {".md", ".json", ".sh", ".mjs", ".js"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in banned:
            if token in text:
                failures.append(f"{path.relative_to(ROOT)} contains {token!r}")
    assert not failures, "\n".join(failures)


def test_deploy_and_vault_contracts_are_fail_closed() -> None:
    deploy = (
        ROOT / "plugins/clickt-reporting/templates/report-package/deploy/deploy.sh"
    ).read_text(encoding="utf-8")
    assert "REPORTS_HOST" not in deploy
    assert "--destination" in deploy
    assert "--confirm" in deploy
    actual_sync_lines = [line.strip() for line in deploy.splitlines() if line.strip().startswith("rsync ")]
    assert actual_sync_lines == [
        'rsync -azn --itemize-changes "dist/${CLIENT}/" "${NORMALIZED_DESTINATION}/"',
        'rsync -az "dist/${CLIENT}/" "${NORMALIZED_DESTINATION}/"',
    ]

    hub = (ROOT / "plugins/google-ads-management/skills/google-ads/SKILL.md").read_text(encoding="utf-8")
    assert "exclusive-create semantics" in hub
    assert "Never replace an existing source by default" in hub
    assert "overwrite = supersede" not in hub


def test_ci_routes_through_the_root_verification_command() -> None:
    workflow = (ROOT / ".github/workflows/verify.yml").read_text(encoding="utf-8")
    assert "run: ./verify" in workflow
    assert "HIVEMIND_MARKETING_SKILLS_TOKEN" in workflow
    verify = (ROOT / "verify").read_text(encoding="utf-8")
    assert "scripts/check_canonical_drift.py" in verify
    assert "scripts/check_payload_versions.py" in verify
    assert 'pytest -q tests' in verify
