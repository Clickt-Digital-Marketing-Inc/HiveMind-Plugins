#!/usr/bin/env python3
"""Shared, stdlib-only primitives for the canonical marketplace sync."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / ".canonical-sync.json"


def run_git(repo: Path, *args: str, text: bool = True) -> str | bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=text,
    )
    if result.returncode:
        stderr = result.stderr if text else result.stderr.decode("utf-8", "replace")
        raise RuntimeError(f"git {' '.join(args)} failed in {repo}: {stderr.strip()}")
    return result.stdout


def load_config(path: Path = CONFIG_PATH) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    required = {"sourceRepository", "sourceCommit", "plugins", "overlayPaths", "overlayReasons", "overlayPrefixes"}
    missing = required - set(data)
    if missing:
        raise ValueError(f"{path}: missing keys: {sorted(missing)}")
    if not data["plugins"] or len(data["plugins"]) != len(set(data["plugins"])):
        raise ValueError(f"{path}: plugins must be a non-empty unique list")
    if len(data["overlayPaths"]) != len(set(data["overlayPaths"])):
        raise ValueError(f"{path}: overlayPaths contains duplicates")
    if set(data["overlayPaths"]) != set(data["overlayReasons"]):
        raise ValueError(f"{path}: overlayPaths and overlayReasons must have identical keys")
    roots = tuple(f"plugins/{name}/" for name in data["plugins"])
    for overlay in data["overlayPaths"]:
        if not overlay.startswith(roots):
            raise ValueError(f"{path}: overlay outside synced roots: {overlay}")
    for prefix, reason in data["overlayPrefixes"].items():
        if not prefix.startswith(roots) or not prefix.endswith("/") or not reason:
            raise ValueError(f"{path}: invalid overlay prefix: {prefix}")
    return data


def is_overlay(path: str, config: dict) -> bool:
    return path in set(config["overlayPaths"]) or any(
        path.startswith(prefix) for prefix in config["overlayPrefixes"]
    )


def resolve_ref(repo: Path, ref: str) -> str:
    return str(run_git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}" )).strip()


def tree_entries(repo: Path, ref: str, plugins: list[str]) -> dict[str, tuple[str, str]]:
    roots = [f"plugins/{name}" for name in plugins]
    raw = str(run_git(repo, "ls-tree", "-r", ref, "--", *roots))
    entries: dict[str, tuple[str, str]] = {}
    for line in raw.splitlines():
        metadata, path = line.split("\t", 1)
        mode, kind, object_id = metadata.split()
        if kind == "blob":
            entries[path] = (mode, object_id)
    return entries


def tracked_paths(repo: Path, plugins: list[str]) -> set[str]:
    roots = [f"plugins/{name}" for name in plugins]
    raw = str(run_git(repo, "ls-files", "--", *roots))
    return set(raw.splitlines())


def blob_bytes(repo: Path, ref: str, path: str) -> bytes:
    return bytes(run_git(repo, "show", f"{ref}:{path}", text=False))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def payload_paths(repo: Path, plugin: str) -> list[Path]:
    root = repo / "plugins" / plugin
    manifest = root / ".claude-plugin" / "plugin.json"
    return sorted(
        (
            path
        for path in root.rglob("*")
        if path.is_file()
        and path != manifest
        and "__pycache__" not in path.parts
        and ".pytest_cache" not in path.parts
        and path.name != ".DS_Store"
        ),
        key=lambda path: path.relative_to(repo).as_posix(),
    )


def payload_digest(repo: Path, plugin: str) -> str:
    digest = hashlib.sha256()
    for path in payload_paths(repo, plugin):
        relative = path.relative_to(repo).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
        executable = bool(path.stat().st_mode & 0o111)
        digest.update(b"x" if executable else b"-")
    return digest.hexdigest()


def base_payload_digest(repo: Path, base_ref: str, plugin: str) -> str:
    prefix = f"plugins/{plugin}/"
    manifest = f"{prefix}.claude-plugin/plugin.json"
    raw = str(run_git(repo, "ls-tree", "-r", base_ref, "--", prefix.rstrip("/")))
    items: list[tuple[str, str, str]] = []
    for line in raw.splitlines():
        metadata, path = line.split("\t", 1)
        mode, kind, object_id = metadata.split()
        if kind == "blob" and path != manifest and not path.endswith("/.DS_Store"):
            items.append((path, mode, object_id))
    digest = hashlib.sha256()
    for path, mode, object_id in sorted(items):
        relative = path.encode("utf-8")
        content = bytes(run_git(repo, "cat-file", "blob", object_id, text=False))
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
        digest.update(b"x" if mode == "100755" else b"-")
    return digest.hexdigest()


def set_executable(path: Path, executable: bool) -> None:
    mode = path.stat().st_mode
    if executable:
        os.chmod(path, mode | 0o111)
    else:
        os.chmod(path, mode & ~0o111)
