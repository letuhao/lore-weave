#!/usr/bin/env bash
# Install agentic-workflow into target project
# Usage: bash /path/to/agentic-workflow/install.sh [target_dir]
#
# What it does:
# 1. Copies scripts/workflow-gate.sh
# 2. Copies .claude/settings.json (merges if exists)
# 3. Adds .workflow-state.json to .gitignore
# 4. Prints next steps

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET="${1:-.}"

echo "Installing agentic-workflow into: $TARGET"
echo ""

# 1. Copy script
mkdir -p "$TARGET/scripts"
cp "$SCRIPT_DIR/scripts/workflow-gate.sh" "$TARGET/scripts/workflow-gate.sh"
chmod +x "$TARGET/scripts/workflow-gate.sh"
echo "[x] scripts/workflow-gate.sh"

# 2. Copy hooks
mkdir -p "$TARGET/.claude"
if [[ -f "$TARGET/.claude/settings.json" ]]; then
  echo "[!] .claude/settings.json already exists — NOT overwriting"
  echo "    Merge hooks manually from: $SCRIPT_DIR/.claude/settings.json"
else
  cp "$SCRIPT_DIR/.claude/settings.json" "$TARGET/.claude/settings.json"
  echo "[x] .claude/settings.json"
fi

# 3. Update .gitignore
if [[ -f "$TARGET/.gitignore" ]]; then
  if grep -q "workflow-state.json" "$TARGET/.gitignore"; then
    echo "[x] .gitignore already has .workflow-state.json"
  else
    echo "" >> "$TARGET/.gitignore"
    echo "# Workflow state (per-session, not committed)" >> "$TARGET/.gitignore"
    echo ".workflow-state.json" >> "$TARGET/.gitignore"
    echo "[x] Added .workflow-state.json to .gitignore"
  fi
else
  echo ".workflow-state.json" > "$TARGET/.gitignore"
  echo "[x] Created .gitignore with .workflow-state.json"
fi

echo ""
echo "Done! Next steps:"
echo "  1. Copy WORKFLOW.md content into your CLAUDE.md"
echo "     (or use CLAUDE.md.snippet for the minimal version)"
echo "  2. Test: cd $TARGET && bash scripts/workflow-gate.sh status"
echo ""
