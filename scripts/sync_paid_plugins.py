#!/usr/bin/env python3
"""Mechanically sync the mirror's overlapping paid-plugin payloads."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sync_lib import ROOT, blob_bytes, load_config, resolve_ref, set_executable, tracked_paths, tree_entries


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-repo", required=True, type=Path)
    parser.add_argument("--canonical-ref", help="commit/ref; defaults to sourceCommit in .canonical-sync.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config()
    canonical = args.canonical_repo.resolve()
    if ROOT.resolve() == canonical:
        print("REFUSE: mirror and canonical resolve to the same repository", file=sys.stderr)
        return 2
    ref = args.canonical_ref or config["sourceCommit"]
    commit = resolve_ref(canonical, ref)
    expected = tree_entries(canonical, commit, config["plugins"])
    overlays = set(config["overlayPaths"])
    expected = {path: entry for path, entry in expected.items() if path not in overlays}
    existing = tracked_paths(ROOT, config["plugins"]) - overlays

    removed = 0
    for relative in sorted(existing - set(expected)):
        path = ROOT / relative
        if path.exists():
            path.unlink()
            removed += 1

    written = 0
    for relative, (mode, _) in sorted(expected.items()):
        destination = ROOT / relative
        content = blob_bytes(canonical, commit, relative)
        if not destination.exists() or destination.read_bytes() != content:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            written += 1
        set_executable(destination, mode == "100755")

    print(f"SYNCED canonical={commit} written={written} removed={removed} tracked_payload_files={len(expected)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
