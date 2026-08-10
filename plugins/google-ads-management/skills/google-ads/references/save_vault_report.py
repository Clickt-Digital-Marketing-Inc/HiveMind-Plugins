#!/usr/bin/env python3
"""Save a Markdown report to a vault without overwriting an existing source."""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


SAFE_PART = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--vault", required=True, type=Path)
    parser.add_argument("--stem", required=True)
    parser.add_argument("--version", help="safe filename component; defaults to UTC timestamp")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    version = args.version or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    if not SAFE_PART.fullmatch(args.stem) or not SAFE_PART.fullmatch(version):
        print("REFUSE: stem and version must be safe filename components", file=sys.stderr)
        return 2
    if not args.source.is_file() or args.source.suffix.lower() != ".md":
        print("REFUSE: source must be an existing Markdown file", file=sys.stderr)
        return 2
    if not args.vault.is_dir():
        print("REFUSE: vault must be an existing directory", file=sys.stderr)
        return 2
    destination_dir = args.vault / "raw" / "reports"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{args.stem}-{version}.md"
    try:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        print(f"REFUSE: destination already exists: {destination}", file=sys.stderr)
        return 3
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(args.source.read_bytes())
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
