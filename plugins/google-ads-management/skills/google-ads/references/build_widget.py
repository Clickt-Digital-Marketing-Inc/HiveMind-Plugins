#!/usr/bin/env python3
"""Assemble the in-Claude tuner widget (show_widget fragment) from a skill's
emitted widget-data JSON + the explorer-widget.html template.

Mirrors _shared/render/html.py's marker substitution exactly (no eval): the
data goes in as a JSON literal at /*__DATA__*/, and the skill's compute kernel +
extra renderer are inlined as code at /*__KERNEL__*/ and /*__EXTRA__*/. The "</"
escape keeps an embedded string from closing the <script> element early.

Usage:
    python3 build_widget.py --data qs_widget.json [--template explorer-widget.html] [--out widget.html]

With no --out, prints the assembled widget to stdout (ready for show_widget).
Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def assemble(data: dict, template: str) -> str:
    payload = {"embed": data["embed"], "spec": data["spec"], "save": data["save"],
               "charts": data.get("charts", [])}
    data_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = template.replace("/*__DATA__*/", data_json)
    html = html.replace("/*__KERNEL__*/", data.get("kernel", "") or "")
    html = html.replace("/*__EXTRA__*/", data.get("extra", "") or "")
    return html


def main() -> int:
    ap = argparse.ArgumentParser(description="Assemble the in-Claude tuner widget.")
    ap.add_argument("--data", required=True, help="widget-data JSON from build_*_report.py --emit-widget")
    ap.add_argument("--template", default=str(HERE / "explorer-widget.html"))
    ap.add_argument("--out", default=None, help="output path (default: stdout)")
    args = ap.parse_args()

    try:
        data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        sys.stderr.write(f"ERROR: cannot read widget data: {e}\n")
        return 1
    for key in ("embed", "spec", "save"):
        if key not in data:
            sys.stderr.write(f"ERROR: widget data missing '{key}'\n")
            return 1
    template = Path(args.template).read_text(encoding="utf-8")
    html = assemble(data, template)

    if args.out:
        Path(args.out).write_text(html, encoding="utf-8")
        print(f"Wrote {args.out} ({len(html):,} bytes)")
    else:
        sys.stdout.write(html)
    return 0


if __name__ == "__main__":
    sys.exit(main())
