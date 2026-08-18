"""PYR-112: pin the frozen `plugins/clickt-reporting` recovery snapshot.

PYR-66 intentionally left this downstream subtree byte-identical and
unreferenced by any active marketplace entry, as a recovery artifact. Reflect
verified its Git tree oid at the time but found the surrounding tests only
enforced that the subtree stays unreferenced/non-authoritative — they did not
fail if its *contents* drifted. This module closes that gap: it recomputes
Git's own blob/tree hashing in pure Python (no `git` subprocess dependency, so
it works the same whether or not `.git` is present) over the live subtree and
compares it, plus a per-file digest/mode table, against a pinned, reviewable
JSON contract.

Run: `python3 -m pytest -q tests/test_frozen_recovery_snapshot.py`
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUBTREE = ROOT / "plugins/clickt-reporting"
CONTRACT_PATH = ROOT / "docs/frozen-recovery-snapshot-clickt-reporting.json"
MARKETPLACE_PATH = ROOT / ".claude-plugin/marketplace.json"

PINNED_TREE_OID = "5345123e4a5703822e1f9dce39d81f360b7724ba"


def _git_blob_sha1(data: bytes) -> bytes:
    header = f"blob {len(data)}\0".encode("utf-8")
    digest = hashlib.sha1()
    digest.update(header)
    digest.update(data)
    return digest.digest()


def _git_tree_sha1(entries: list[tuple[str, bytes, bytes]]) -> bytes:
    """`entries` is a list of (mode, name_bytes, sha1_digest_bytes).

    Git sorts tree entries by raw name bytes, comparing as if directory names
    carried a trailing `/` — so a file `foo.md` sorts before a directory
    `foo/` would if `foo` existed as both, which cannot happen in one tree but
    matters for entries like `foo` (file) vs `foo-bar` (file) vs `foo/` (dir).
    """

    def sort_key(entry: tuple[str, bytes, bytes]) -> bytes:
        mode, name, _sha = entry
        return name + b"/" if mode == "40000" else name

    body = b""
    for mode, name, sha in sorted(entries, key=sort_key):
        body += mode.encode("ascii") + b" " + name + b"\0" + sha
    header = f"tree {len(body)}\0".encode("utf-8")
    digest = hashlib.sha1()
    digest.update(header)
    digest.update(body)
    return digest.digest()


def _mode_for(path: Path) -> str:
    return "100755" if os.access(path, os.X_OK) else "100644"


def compute_tree(root: Path) -> tuple[str, dict[str, dict[str, str]]]:
    """Recompute the Git tree oid and a per-file {mode, sha256} table for `root`.

    Returns (tree_oid_hex, files) where `files` keys are POSIX-style paths
    relative to `root`.
    """

    files: dict[str, dict[str, str]] = {}

    def hash_dir(directory: Path, prefix: str) -> bytes:
        entries: list[tuple[str, bytes, bytes]] = []
        for child in sorted(directory.iterdir()):
            rel = f"{prefix}{child.name}"
            if child.is_dir():
                sha = hash_dir(child, rel + "/")
                entries.append(("40000", child.name.encode("utf-8"), sha))
            elif child.is_file():
                data = child.read_bytes()
                mode = _mode_for(child)
                files[rel] = {"mode": mode, "sha256": hashlib.sha256(data).hexdigest()}
                entries.append((mode, child.name.encode("utf-8"), _git_blob_sha1(data)))
            else:
                raise AssertionError(f"unexpected non-file, non-dir entry: {child}")
        return _git_tree_sha1(entries)

    tree_sha = hash_dir(root, "")
    return tree_sha.hex(), files


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _marketplace_sources_referencing(root: Path) -> list[str]:
    marketplace = _load_json(root / ".claude-plugin/marketplace.json")
    hits: list[str] = []
    for entry in marketplace.get("plugins", []):
        if not isinstance(entry, dict):
            continue
        source = entry.get("source")
        name = entry.get("name", "<unnamed>")
        if isinstance(source, str) and "clickt-reporting" in source:
            hits.append(f"{name}: {source}")
        elif isinstance(source, dict):
            # The approved legacy shim source (PYR-66) points at
            # `.claude-plugin/legacy/clickt-reporting` inside the *canonical*
            # repository, not at this local frozen subtree — that path is
            # legitimate and must not trip this guard.
            path_value = str(source.get("path", ""))
            if "clickt-reporting" in path_value and "legacy" not in path_value:
                hits.append(f"{name}: {source}")
    return hits


def validate(root: Path) -> list[str]:
    errors: list[str] = []

    contract_path = root / "docs/frozen-recovery-snapshot-clickt-reporting.json"
    subtree_path = root / "plugins/clickt-reporting"

    try:
        contract = _load_json(contract_path)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"invalid or missing contract JSON: {exc}"]

    if contract.get("gitTreeOid") != PINNED_TREE_OID:
        errors.append("contract gitTreeOid must equal the PYR-112 pinned value")

    contract_files = contract.get("files")
    if not isinstance(contract_files, dict):
        errors.append("contract files table must be an object")
        contract_files = {}

    if contract.get("fileCount") != len(contract_files):
        errors.append("contract fileCount must match the length of its files table")

    if not subtree_path.is_dir():
        errors.append("frozen subtree plugins/clickt-reporting is missing")
        return errors

    actual_tree_oid, actual_files = compute_tree(subtree_path)

    if actual_tree_oid != PINNED_TREE_OID:
        errors.append(
            f"frozen subtree Git tree drifted: expected {PINNED_TREE_OID}, got {actual_tree_oid}"
        )

    if actual_tree_oid != contract.get("gitTreeOid"):
        errors.append("live subtree tree oid does not match the contract's recorded gitTreeOid")

    actual_paths = set(actual_files)
    contract_paths = set(contract_files)
    added = sorted(actual_paths - contract_paths)
    removed = sorted(contract_paths - actual_paths)
    if added:
        errors.append(f"frozen subtree gained path(s) not in the pinned contract: {added}")
    if removed:
        errors.append(f"frozen subtree lost pinned path(s): {removed}")

    for path in sorted(actual_paths & contract_paths):
        actual_entry = actual_files[path]
        pinned_entry = contract_files[path]
        if actual_entry.get("sha256") != pinned_entry.get("sha256"):
            errors.append(f"frozen subtree content drifted at {path}")
        if actual_entry.get("mode") != pinned_entry.get("mode"):
            errors.append(
                f"frozen subtree executable mode drifted at {path}: "
                f"expected {pinned_entry.get('mode')}, got {actual_entry.get('mode')}"
            )

    marketplace_hits = _marketplace_sources_referencing(root)
    if marketplace_hits:
        errors.append(
            "an active marketplace entry references the frozen subtree: "
            + "; ".join(marketplace_hits)
        )

    return errors


def test_frozen_snapshot_matches_pinned_contract() -> None:
    assert validate(ROOT) == []


def test_pinned_tree_oid_matches_issue_pin() -> None:
    """Belt-and-suspenders: the module constant must equal PYR-112's own text."""
    assert PINNED_TREE_OID == "5345123e4a5703822e1f9dce39d81f360b7724ba"


def _make_mutant(tmp_path: Path) -> Path:
    mutant_root = tmp_path / "repo-mutant"
    mutant_root.mkdir()
    shutil.copytree(SUBTREE, mutant_root / "plugins/clickt-reporting")
    (mutant_root / "docs").mkdir()
    shutil.copy2(CONTRACT_PATH, mutant_root / "docs/frozen-recovery-snapshot-clickt-reporting.json")
    (mutant_root / ".claude-plugin").mkdir()
    shutil.copy2(MARKETPLACE_PATH, mutant_root / ".claude-plugin/marketplace.json")
    return mutant_root


def test_mutation_content_drift_is_detected(tmp_path: Path) -> None:
    mutant_root = _make_mutant(tmp_path)
    target = mutant_root / "plugins/clickt-reporting/README.md"
    target.write_text(target.read_text(encoding="utf-8") + "\nmutated for PYR-112 coverage\n", encoding="utf-8")

    errors = validate(mutant_root)
    assert any("frozen subtree Git tree drifted" in e for e in errors), errors
    assert any("content drifted at README.md" in e for e in errors), errors


def test_mutation_path_addition_is_detected(tmp_path: Path) -> None:
    mutant_root = _make_mutant(tmp_path)
    extra = mutant_root / "plugins/clickt-reporting/commands/report-extra.md"
    extra.write_text("# injected command\n", encoding="utf-8")

    errors = validate(mutant_root)
    assert any("frozen subtree Git tree drifted" in e for e in errors), errors
    assert any("gained path(s)" in e and "commands/report-extra.md" in e for e in errors), errors


def test_mutation_path_removal_is_detected(tmp_path: Path) -> None:
    mutant_root = _make_mutant(tmp_path)
    victim = mutant_root / "plugins/clickt-reporting/commands/report-weekly.md"
    victim.unlink()

    errors = validate(mutant_root)
    assert any("frozen subtree Git tree drifted" in e for e in errors), errors
    assert any("lost pinned path(s)" in e and "commands/report-weekly.md" in e for e in errors), errors


def test_mutation_path_rename_is_detected(tmp_path: Path) -> None:
    mutant_root = _make_mutant(tmp_path)
    source = mutant_root / "plugins/clickt-reporting/commands/report-weekly.md"
    source.rename(source.with_name("report-weekly-renamed.md"))

    errors = validate(mutant_root)
    assert any("frozen subtree Git tree drifted" in e for e in errors), errors
    assert any("lost pinned path(s)" in e and "commands/report-weekly.md" in e for e in errors), errors
    assert any(
        "gained path(s)" in e and "commands/report-weekly-renamed.md" in e for e in errors
    ), errors


def test_mutation_executable_mode_flip_is_detected(tmp_path: Path) -> None:
    mutant_root = _make_mutant(tmp_path)
    deploy = mutant_root / "plugins/clickt-reporting/templates/report-package/deploy/deploy.sh"
    assert os.access(deploy, os.X_OK), "fixture assumption: deploy.sh starts executable"
    mode = deploy.stat().st_mode
    deploy.chmod(mode & ~stat.S_IXUSR & ~stat.S_IXGRP & ~stat.S_IXOTH)
    assert not os.access(deploy, os.X_OK)

    errors = validate(mutant_root)
    assert any("frozen subtree Git tree drifted" in e for e in errors), errors
    assert any(
        "executable mode drifted at templates/report-package/deploy/deploy.sh" in e for e in errors
    ), errors


def test_mutation_non_executable_gains_executable_bit_is_detected(tmp_path: Path) -> None:
    mutant_root = _make_mutant(tmp_path)
    readme = mutant_root / "plugins/clickt-reporting/README.md"
    assert not os.access(readme, os.X_OK), "fixture assumption: README.md starts non-executable"
    mode = readme.stat().st_mode
    readme.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    errors = validate(mutant_root)
    assert any("frozen subtree Git tree drifted" in e for e in errors), errors
    assert any("executable mode drifted at README.md" in e for e in errors), errors


def test_marketplace_reference_to_frozen_subtree_is_detected(tmp_path: Path) -> None:
    mutant_root = _make_mutant(tmp_path)
    marketplace_path = mutant_root / ".claude-plugin/marketplace.json"
    payload = _load_json(marketplace_path)
    payload["plugins"].append(
        {
            "name": "clickt-reporting-leak",
            "source": "./plugins/clickt-reporting",
            "version": "1.5.0",
        }
    )
    marketplace_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    errors = validate(mutant_root)
    assert any("an active marketplace entry references the frozen subtree" in e for e in errors), errors
