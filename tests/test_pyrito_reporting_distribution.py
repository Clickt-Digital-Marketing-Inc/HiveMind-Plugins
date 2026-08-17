"""PYR-66 canonical-to-distribution and compatibility contracts.

Run: `python3 -m pytest -q tests/test_pyrito_reporting_distribution.py`
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
PIN = "dcb19312a1285bcbf0f2db2d1309919f39789997"
CANONICAL_TREE = "ec1b9ff3575f99a5439592ec0625ddf4b5f15248"
LEGACY_TREE = "fbc99cf2673d8e90dd69a5c83de3ce0e8a52f80f"
ENGINE_SHA256 = "84613b8c65767f654776e44a316c524920abc3bb5803dd786e213e89b5affdec"
HOSTNAME = "reports.gethivemind.co"
LEGACY_FILE_SHA256 = {
    ".claude-plugin/plugin.json": "c4f3d1787504e4f23cd7c296cc6f22497aae6be3e6676019f0c38b04c80c9b8f",
    "commands/report-monthly.md": "9bea0a61b0ec86ccd059e5d9fdad1a82221ddb45c61f7992f8cd536972e3d201",
    "commands/report-setup.md": "e2d87379b6756027bbf8f807d9c203830dd18d5848298de4486176732cdec0c7",
    "commands/report-weekly.md": "ef8232cbf2e899cb308018d4d6ac941778d8d751e2b549fe215b00971b0df5de",
}


def _load_json(path: Path, errors: list[str]) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"invalid JSON {path.relative_to(path.parents[2])}: {exc}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"JSON root must be an object: {path.name}")
        return {}
    return value


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    marketplace = _load_json(root / ".claude-plugin/marketplace.json", errors)
    contract = _load_json(root / "docs/pyrito-reporting-1.5.0.json", errors)
    readme = (root / "README.md").read_text(encoding="utf-8")
    notes = (root / "docs/pyrito-reporting-1.5.0.md").read_text(encoding="utf-8")
    readme_contract = " ".join(readme.split())
    notes_contract = " ".join(notes.split())

    entries = marketplace.get("plugins", [])
    if not isinstance(entries, list):
        errors.append("marketplace plugins must be an array")
        entries = []
    names = [entry.get("name") for entry in entries if isinstance(entry, dict)]
    if len(names) != len(set(names)):
        errors.append("marketplace plugin names must be unique")
    by_name = {
        entry.get("name"): entry
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    }

    canonical = by_name.get("pyrito-reporting")
    expected_canonical_source = {
        "source": "url",
        "url": "https://github.com/Pyrito-ai/Pyrito-Reporting.git",
        "sha": PIN,
    }
    if not isinstance(canonical, dict):
        errors.append("canonical pyrito-reporting marketplace entry is required")
    else:
        if canonical.get("source") != expected_canonical_source:
            errors.append("canonical source must be the exact pinned private HTTPS Git commit")
        if canonical.get("version") != "1.5.0":
            errors.append("canonical catalog version must be 1.5.0")
        if HOSTNAME not in str(canonical.get("description", "")):
            errors.append("canonical catalog description must name the production hostname")

    legacy = by_name.get("clickt-reporting")
    expected_legacy_source = {
        "source": "git-subdir",
        "url": "https://github.com/Pyrito-ai/Pyrito-Reporting.git",
        "path": ".claude-plugin/legacy/clickt-reporting",
        "sha": PIN,
    }
    if not isinstance(legacy, dict):
        errors.append("legacy clickt-reporting marketplace entry is required")
    else:
        if legacy.get("source") != expected_legacy_source:
            errors.append("legacy source must be the exact pinned canonical shim")
        if legacy.get("version") != "1.5.0":
            errors.append("legacy catalog version must be 1.5.0, never stale v1.0.x")
        if legacy.get("strict") is not True:
            errors.append("legacy shim must use strict manifest authority")

    canonical_contract = contract.get("canonical", {})
    if canonical_contract.get("repository") != "Pyrito-ai/Pyrito-Reporting":
        errors.append("contract canonical repository mismatch")
    if canonical_contract.get("commit") != PIN:
        errors.append("contract canonical commit mismatch")
    if canonical_contract.get("treeOid") != CANONICAL_TREE:
        errors.append("contract canonical tree mismatch")
    if canonical_contract.get("fileCount") != 66:
        errors.append("contract canonical file count mismatch")
    if canonical_contract.get("engineSha256") != ENGINE_SHA256:
        errors.append("contract canonical engine digest mismatch")

    legacy_contract = contract.get("legacyShim", {})
    if legacy_contract.get("sourcePath") != ".claude-plugin/legacy/clickt-reporting":
        errors.append("contract legacy source path mismatch")
    if legacy_contract.get("treeOid") != LEGACY_TREE:
        errors.append("contract legacy tree mismatch")
    if legacy_contract.get("fileCount") != 4:
        errors.append("contract legacy file count mismatch")
    files = legacy_contract.get("files")
    if files != LEGACY_FILE_SHA256:
        errors.append("contract legacy byte digests mismatch")

    if contract.get("productionHostname") != HOSTNAME:
        errors.append("contract production hostname mismatch")
    if contract.get("deferredDomainMigration") is not True:
        errors.append("contract must keep domain migration deferred")
    if contract.get("compatibilityRetirementIssue") != "PYR-73":
        errors.append("contract compatibility retirement issue mismatch")
    if contract.get("compatibilityRetirementRequiresHumanApproval") is not True:
        errors.append("contract must require separate human retirement approval")

    required_readme = (
        "/plugin marketplace add Pyrito-ai/Pyrito-Reporting",
        "/plugin install pyrito-reporting@pyrito-reporting",
        "codex plugin marketplace add Pyrito-ai/Pyrito-Reporting --ref main",
        "codex plugin add pyrito-reporting@pyrito-reporting",
        "/plugin install pyrito-reporting@hivemind-plugins",
        "/plugin install clickt-reporting@hivemind-plugins",
        "/clickt-reporting:report-setup",
        "/clickt-reporting:report-weekly",
        "/clickt-reporting:report-monthly",
        HOSTNAME,
        "PYR-73",
        "Domain migration is explicitly deferred",
    )
    for phrase in required_readme:
        if phrase not in readme_contract:
            errors.append(f"README distribution contract missing: {phrase}")

    required_notes = (
        PIN,
        CANONICAL_TREE,
        LEGACY_TREE,
        ENGINE_SHA256,
        HOSTNAME,
        "two consecutive tagged releases",
        "separate human approval",
        "Domain migration is explicitly deferred",
        "no marketplace entry references it",
    )
    for phrase in required_notes:
        if phrase not in notes_contract:
            errors.append(f"release notes distribution contract missing: {phrase}")

    return errors


def _copy_contract_tree(destination: Path) -> None:
    shutil.copy2(ROOT / "README.md", destination / "README.md")
    shutil.copytree(ROOT / ".claude-plugin", destination / ".claude-plugin")
    shutil.copytree(ROOT / "docs", destination / "docs")


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_distribution_contract() -> None:
    assert validate(ROOT) == []


def test_mutation_sweep_proves_every_distribution_gate(tmp_path: Path) -> None:
    mutant = tmp_path / "marketplace"
    mutant.mkdir()
    _copy_contract_tree(mutant)

    marketplace_path = mutant / ".claude-plugin/marketplace.json"
    contract_path = mutant / "docs/pyrito-reporting-1.5.0.json"
    readme_path = mutant / "README.md"
    notes_path = mutant / "docs/pyrito-reporting-1.5.0.md"

    def marketplace() -> dict:
        return json.loads(marketplace_path.read_text(encoding="utf-8"))

    def contract() -> dict:
        return json.loads(contract_path.read_text(encoding="utf-8"))

    def entry(payload: dict, name: str) -> dict:
        return next(item for item in payload["plugins"] if item["name"] == name)

    def exercise(
        mutate: Callable[[], None], expected: str, paths: tuple[Path, ...]
    ) -> None:
        originals = {path: path.read_bytes() for path in paths}
        mutate()
        errors = validate(mutant)
        assert any(expected in error for error in errors), (expected, errors)
        for path, value in originals.items():
            path.write_bytes(value)

    exercise(
        lambda: (
            lambda payload: (
                entry(payload, "pyrito-reporting")["source"].update({"sha": "0" * 40}),
                _write_json(marketplace_path, payload),
            )
        )(marketplace()),
        "canonical source must be the exact pinned private HTTPS Git commit",
        (marketplace_path,),
    )
    exercise(
        lambda: (
            lambda payload: (
                entry(payload, "clickt-reporting").update(
                    {"source": "./plugins/clickt-reporting"}
                ),
                _write_json(marketplace_path, payload),
            )
        )(marketplace()),
        "legacy source must be the exact pinned canonical shim",
        (marketplace_path,),
    )
    exercise(
        lambda: (
            lambda payload: (
                entry(payload, "clickt-reporting").update({"version": "1.0.0"}),
                _write_json(marketplace_path, payload),
            )
        )(marketplace()),
        "legacy catalog version must be 1.5.0, never stale v1.0.x",
        (marketplace_path,),
    )
    exercise(
        lambda: (
            lambda payload: (
                payload["plugins"].__setitem__(
                    slice(None),
                    [item for item in payload["plugins"] if item["name"] != "clickt-reporting"],
                ),
                _write_json(marketplace_path, payload),
            )
        )(marketplace()),
        "legacy clickt-reporting marketplace entry is required",
        (marketplace_path,),
    )

    for key, value, expected in (
        ("commit", "0" * 40, "contract canonical commit mismatch"),
        ("treeOid", "0" * 40, "contract canonical tree mismatch"),
        ("engineSha256", "0" * 64, "contract canonical engine digest mismatch"),
    ):
        exercise(
            lambda key=key, value=value: (
                lambda payload: (
                    payload["canonical"].update({key: value}),
                    _write_json(contract_path, payload),
                )
            )(contract()),
            expected,
            (contract_path,),
        )

    exercise(
        lambda: (
            lambda payload: (
                payload["legacyShim"].update({"treeOid": "0" * 40}),
                _write_json(contract_path, payload),
            )
        )(contract()),
        "contract legacy tree mismatch",
        (contract_path,),
    )
    exercise(
        lambda: (
            lambda payload: (
                payload["legacyShim"]["files"].update(
                    {"commands/report-weekly.md": "0" * 64}
                ),
                _write_json(contract_path, payload),
            )
        )(contract()),
        "contract legacy byte digests mismatch",
        (contract_path,),
    )
    exercise(
        lambda: readme_path.write_text(
            readme_path.read_text(encoding="utf-8").replace(
                "codex plugin add pyrito-reporting@pyrito-reporting", "codex plugin add removed"
            ),
            encoding="utf-8",
        ),
        "README distribution contract missing: codex plugin add pyrito-reporting@pyrito-reporting",
        (readme_path,),
    )
    exercise(
        lambda: notes_path.write_text(
            notes_path.read_text(encoding="utf-8").replace(HOSTNAME, "host.invalid"),
            encoding="utf-8",
        ),
        f"release notes distribution contract missing: {HOSTNAME}",
        (notes_path,),
    )
    exercise(
        lambda: notes_path.write_text(
            notes_path.read_text(encoding="utf-8").replace(
                "Domain migration is explicitly deferred", "Domain work is pending"
            ),
            encoding="utf-8",
        ),
        "release notes distribution contract missing: Domain migration is explicitly deferred",
        (notes_path,),
    )
