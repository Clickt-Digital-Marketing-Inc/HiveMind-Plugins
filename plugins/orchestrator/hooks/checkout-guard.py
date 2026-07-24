#!/usr/bin/env python3
"""checkout-guard: PreToolUse hook logic (invoked via checkout-guard.sh).

Blocks `git checkout` / `git switch` when they would run in the PROJECT ROOT
(the live tree, which must stay on its base branch), while allowing them
inside worktree paths, other repos, and file-restore forms. Conservative by
design: on any doubt (unparsable input, cd in the command, -C targeting
another path), it allows.
"""
import json
import os
import re
import sys

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)  # unparsable -> allow

cmd = (data.get("tool_input") or {}).get("command", "") or ""
if "git" not in cmd:
    sys.exit(0)

root = os.environ.get("CLAUDE_PROJECT_DIR") or ""
if not root:
    sys.exit(0)
root = os.path.realpath(root)

cwd = data.get("cwd") or os.getcwd()
try:
    cwd = os.path.realpath(cwd)
except Exception:
    sys.exit(0)

# Only guard commands whose shell starts in the project root itself.
if cwd != root:
    sys.exit(0)

# If the command changes directory anywhere, we can't be sure where git runs -> allow.
if re.search(r"(^|[;&|]\s*|\b)cd\s", cmd):
    sys.exit(0)

m = re.search(
    r"\bgit\s+(?:-C\s+(\"[^\"]+\"|'[^']+'|\S+)\s+)?(?:-\S+\s+)*(checkout|switch)\b(.*)",
    cmd,
    re.S,
)
if not m:
    sys.exit(0)

c_target, sub, rest = m.group(1), m.group(2), m.group(3) or ""

# git -C <path> targeting somewhere other than the project root -> allow.
if c_target:
    t = c_target.strip("\"'")
    try:
        t = os.path.realpath(os.path.expanduser(t))
    except Exception:
        sys.exit(0)
    if t != root:
        sys.exit(0)

# `git checkout -- <paths>` (file restore, no branch switch) -> allow.
if sub == "checkout" and re.match(r"\s+--(\s|$)", rest):
    sys.exit(0)

sys.stderr.write(
    "checkout-guard: blocked `git %s` in the project root. The live tree stays on its "
    "base branch (worktree rule). Do branch work in a worktree instead:\n"
    '  git worktree add "$TMPDIR/<issue>-worktree" -b <branch>\n'
    "then run checkout/switch inside that worktree path (or use `git -C <worktree> ...`).\n"
    % sub
)
sys.exit(2)
