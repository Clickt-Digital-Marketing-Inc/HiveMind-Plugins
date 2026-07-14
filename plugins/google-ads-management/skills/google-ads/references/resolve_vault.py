#!/usr/bin/env python3
"""Resolve the HiveMind (SilverBullet) vault root for a direct file write.

Precedence mirrors the HiveMind MCP binary's own resolution:
  1. $HIVEMIND_VAULT (explicit override)
  2. the HiveMind app config.json `vaultPath`
       macOS:  ~/Library/Application Support/com.hivemind.app/config.json
       Linux:  ~/.config/com.hivemind.app/config.json
  3. none -> exit 3 (the caller should ask the operator for the path)

Prints the absolute vault root on success. Stdlib only.
The MCP is read-only and returns vault-RELATIVE paths, so a direct write needs
this resolver — the absolute root is not available from the MCP tools.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _ok(p) -> str | None:
    try:
        q = Path(p).expanduser()
        return str(q) if q.is_dir() else None
    except OSError:
        return None


def resolve() -> str | None:
    env = os.environ.get("HIVEMIND_VAULT")
    if env:
        root = _ok(env)
        if root:
            return root
    candidates = [
        Path.home() / "Library" / "Application Support" / "com.hivemind.app" / "config.json",
        Path.home() / ".config" / "com.hivemind.app" / "config.json",
    ]
    for cfg in candidates:
        if cfg.is_file():
            try:
                vp = json.loads(cfg.read_text(encoding="utf-8")).get("vaultPath")
            except (OSError, json.JSONDecodeError):
                continue
            if vp:
                root = _ok(vp)
                if root:
                    return root
    return None


if __name__ == "__main__":
    root = resolve()
    if not root:
        sys.stderr.write(
            "ERROR: could not resolve the HiveMind vault root. "
            "Set $HIVEMIND_VAULT, or ensure the HiveMind app config.json has a valid vaultPath, "
            "or ask the operator for the vault directory.\n")
        sys.exit(3)
    print(root)
