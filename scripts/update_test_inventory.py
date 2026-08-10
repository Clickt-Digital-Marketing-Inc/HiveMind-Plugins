#!/usr/bin/env python3
"""Regenerate the stable inventory used by the collision-safe test runner."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
files = sorted(
    path.relative_to(ROOT).as_posix()
    for path in (ROOT / "plugins").glob("*/**/test_*.py")
    if "__pycache__" not in path.parts
)
(ROOT / ".test-inventory.json").write_text(
    json.dumps({"schemaVersion": 1, "files": files}, indent=2) + "\n",
    encoding="utf-8",
)
print(f"WROTE .test-inventory.json: files={len(files)}")
