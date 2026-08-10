#!/usr/bin/env python3
"""Require payload/version integrity and a SemVer bump for changed plugins."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from sync_lib import ROOT, base_payload_digest, load_config, payload_digest, run_git


LOCK_PATH = ROOT / ".payload-lock.json"
MARKETPLACE_PATH = ROOT / ".claude-plugin" / "marketplace.json"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument("--write-lock", action="store_true")
    return parser.parse_args()


def version_tuple(value: str) -> tuple[int, int, int]:
    match = SEMVER.fullmatch(value)
    if not match:
        raise ValueError(f"not strict SemVer: {value!r}")
    return tuple(int(part) for part in match.groups())


def manifest_at(ref: str, plugin: str) -> dict:
    raw = str(run_git(ROOT, "show", f"{ref}:plugins/{plugin}/.claude-plugin/plugin.json"))
    return json.loads(raw)


def main() -> int:
    args = parse_args()
    marketplace = json.loads(MARKETPLACE_PATH.read_text(encoding="utf-8"))
    entries = marketplace.get("plugins", [])
    by_name = {entry.get("name"): entry for entry in entries}
    failures: list[str] = []
    if len(by_name) != len(entries):
        failures.append("marketplace plugin names are missing or duplicated")

    current: dict[str, dict[str, str]] = {}
    changed: list[str] = []
    for name, entry in sorted(by_name.items()):
        manifest_path = ROOT / "plugins" / name / ".claude-plugin" / "plugin.json"
        if not manifest_path.is_file():
            failures.append(f"{name}: missing plugin manifest")
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_version = manifest.get("version")
        marketplace_version = entry.get("version")
        try:
            current_version = version_tuple(str(manifest_version))
        except ValueError as exc:
            failures.append(f"{name}: {exc}")
            continue
        if manifest_version != marketplace_version:
            failures.append(
                f"{name}: manifest version {manifest_version!r} != marketplace version {marketplace_version!r}"
            )
        digest = payload_digest(ROOT, name)
        current[name] = {"version": str(manifest_version), "payloadSha256": digest}
        try:
            old_manifest = manifest_at(args.base_ref, name)
            old_digest = base_payload_digest(ROOT, args.base_ref, name)
        except RuntimeError:
            continue
        if digest != old_digest:
            changed.append(name)
            old_version_value = str(old_manifest.get("version"))
            try:
                old_version = version_tuple(old_version_value)
            except ValueError as exc:
                failures.append(f"{name} base: {exc}")
                continue
            if current_version <= old_version:
                failures.append(
                    f"{name}: payload changed from {args.base_ref} but version did not increase "
                    f"({old_version_value} -> {manifest_version})"
                )

    if failures:
        print("PAYLOAD VERSION FAIL:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    if args.write_lock:
        lock = {"schemaVersion": 1, "plugins": current}
        LOCK_PATH.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"WROTE {LOCK_PATH.name}: plugins={len(current)} changed_from_base={len(changed)}")
        return 0

    if not LOCK_PATH.is_file():
        print(f"PAYLOAD VERSION FAIL: missing {LOCK_PATH.name}", file=sys.stderr)
        return 1
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    if lock.get("schemaVersion") != 1 or lock.get("plugins") != current:
        print(
            "PAYLOAD VERSION FAIL: payload/manifest state does not match .payload-lock.json; "
            "bump changed versions and regenerate the lock",
            file=sys.stderr,
        )
        return 1
    print(f"PAYLOAD VERSION OK: plugins={len(current)} changed_from_base={len(changed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
