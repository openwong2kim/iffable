#!/usr/bin/env bash
# iffable installer — copies iffable.py + instruction profiles into IFFABLE_HOME.
# It does NOT edit your settings: hook/env wiring is printed for you to merge by
# hand, because auto-editing settings.json risks the Claude Code /model migration
# bug (#22659) that strips hooks.
set -euo pipefail

DEST="${IFFABLE_HOME:-$HOME/.claude/iffable}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "iffable → installing to: $DEST"
mkdir -p "$DEST/instructions"
cp "$SRC/iffable.py" "$DEST/iffable.py"
cp "$SRC/instructions/orchestrator-fable.md" "$DEST/instructions/"
cp "$SRC/instructions/orchestrator-fallback.md" "$DEST/instructions/"
echo "  copied iffable.py + 2 instruction profiles"

echo
echo "NEXT — MERGE (do not overwrite) the hook + env wiring into your settings:"
echo "  ~/.claude/settings.local.json   (local file dodges the /model migration bug #22659)"
echo "  Source to copy from:            $SRC/settings.example.json"
echo
echo "Then start a session ON FABLE for the guards to arm:"
echo "  claude --model claude-fable-5"
echo
echo "Non-Fable sessions stay dormant by design (the Haiku ban still applies everywhere)."
