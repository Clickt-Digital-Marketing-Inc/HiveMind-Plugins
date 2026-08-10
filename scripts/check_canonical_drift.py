#!/usr/bin/env python3
"""Fail when declared paid-plugin payloads diverge from canonical."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

from sync_lib import ROOT, blob_bytes, is_overlay, load_config, resolve_ref, tracked_paths, tree_entries


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-repo", required=True, type=Path)
    parser.add_argument("--canonical-ref", default="HEAD")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config()
    canonical = args.canonical_repo.resolve()
    if ROOT.resolve() == canonical:
        print("REFUSE: mirror and canonical resolve to the same repository", file=sys.stderr)
        return 2
    commit = resolve_ref(canonical, args.canonical_ref)
    source = {
        path: entry
        for path, entry in tree_entries(canonical, commit, config["plugins"]).items()
        if not is_overlay(path, config)
    }
    mirror_paths = {path for path in tracked_paths(ROOT, config["plugins"]) if not is_overlay(path, config)}
    missing = sorted(set(source) - mirror_paths)
    extra = sorted(mirror_paths - set(source))
    different = []
    for relative in sorted(set(source) & mirror_paths):
        mirror_path = ROOT / relative
        expected = blob_bytes(canonical, commit, relative)
        if not mirror_path.is_file() or hashlib.sha256(mirror_path.read_bytes()).digest() != hashlib.sha256(expected).digest():
            different.append(relative)

    if missing or extra or different:
        print(f"CANONICAL DRIFT: canonical={commit}", file=sys.stderr)
        for label, paths in (("missing", missing), ("extra", extra), ("different", different)):
            for path in paths:
                print(f"  {label}: {path}", file=sys.stderr)
        return 1
    print(
        f"CANONICAL DRIFT OK: canonical={commit} synced_payload_files={len(source)} "
        f"overlay_paths={len(config['overlayPaths'])} overlay_prefixes={len(config['overlayPrefixes'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
