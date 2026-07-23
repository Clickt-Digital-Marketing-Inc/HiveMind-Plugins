#!/bin/bash
# checkout-guard: PreToolUse hook on Bash (see checkout-guard.py for the logic).
# Fails open if python3 is unavailable. stdin (the hook JSON) passes through
# to the python script untouched.
command -v python3 >/dev/null 2>&1 || exit 0
DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
exec python3 "$DIR/checkout-guard.py"
