#!/usr/bin/env bash
# iffable installer — copies hook scripts + instruction profiles into
# ~/.claude/orchestrator/. It does NOT touch your settings.json: hook/env
# wiring is printed for you to merge by hand, because auto-editing
# settings.json risks the Claude Code migration bug that strips hooks.
set -euo pipefail

DEST="${CLAUDE_ORCH_ROOT:-$HOME/.claude/orchestrator}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "iffable → installing to: $DEST"
mkdir -p "$DEST/scripts" "$DEST/instructions"
cp "$SRC/scripts/"*.py "$DEST/scripts/"
cp "$SRC/instructions/"*.md "$DEST/instructions/"
echo "  copied 4 hook scripts + 2 instruction profiles"

echo
echo "NEXT — merge the hook + env wiring into your settings:"
echo "  ~/.claude/settings.json   (or settings.local.json to survive /model migrations)"
echo "  Source to copy from:      $SRC/settings.example.json"
echo
echo "Then start a session ON FABLE for the guard to arm:"
echo "  claude --model claude-fable-5"
echo
echo "Non-Fable sessions stay dormant by design."
