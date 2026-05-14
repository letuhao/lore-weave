#!/usr/bin/env bash
# Install agentic-workflow into target project
# Usage: bash /path/to/agentic-workflow/install.sh [target_dir] [--no-amaw]
#
# What it does:
# 1. Copies scripts/workflow-gate.sh
# 2. Copies .claude/settings.json (merges if exists)
# 3. Copies .claude/commands/review-impl.md (default mode) + amaw.md (opt-in)
# 4. Copies AMAW.md spec to target docs/ (unless --no-amaw)
# 5. Adds .workflow-state.json to .gitignore + optionally creates docs/audit/
# 6. Prints next steps

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET="${1:-.}"
NO_AMAW=0
for arg in "$@"; do
  if [[ "$arg" == "--no-amaw" ]]; then NO_AMAW=1; fi
done

echo "Installing agentic-workflow bundle v2.3 into: $TARGET"
echo "  AMAW opt-in extension: $([ $NO_AMAW -eq 1 ] && echo 'EXCLUDED' || echo 'INCLUDED')"
echo ""

# 1. Copy scripts (both .sh wrapper and .py implementation)
mkdir -p "$TARGET/scripts"
cp "$SCRIPT_DIR/scripts/workflow-gate.sh" "$TARGET/scripts/workflow-gate.sh"
cp "$SCRIPT_DIR/scripts/workflow-gate.py" "$TARGET/scripts/workflow-gate.py"
chmod +x "$TARGET/scripts/workflow-gate.sh" "$TARGET/scripts/workflow-gate.py"
echo "[x] scripts/workflow-gate.sh (bash wrapper)"
echo "[x] scripts/workflow-gate.py (cross-platform implementation)"

# 2. Copy hooks (don't overwrite)
mkdir -p "$TARGET/.claude"
if [[ -f "$TARGET/.claude/settings.json" ]]; then
  echo "[!] .claude/settings.json already exists — NOT overwriting"
  echo "    Merge hooks manually from: $SCRIPT_DIR/.claude/settings.json"
else
  cp "$SCRIPT_DIR/.claude/settings.json" "$TARGET/.claude/settings.json"
  echo "[x] .claude/settings.json"
fi

# 3a. /review-impl slash command (default mode)
mkdir -p "$TARGET/.claude/commands"
if [[ -f "$TARGET/.claude/commands/review-impl.md" ]]; then
  echo "[!] .claude/commands/review-impl.md already exists — NOT overwriting"
else
  cp "$SCRIPT_DIR/.claude/commands/review-impl.md" "$TARGET/.claude/commands/review-impl.md"
  echo "[x] .claude/commands/review-impl.md (default-mode on-demand review)"
fi

# 3b. /amaw slash command (opt-in)
if [[ $NO_AMAW -eq 0 ]]; then
  if [[ -f "$TARGET/.claude/commands/amaw.md" ]]; then
    echo "[!] .claude/commands/amaw.md already exists — NOT overwriting"
  else
    cp "$SCRIPT_DIR/.claude/commands/amaw.md" "$TARGET/.claude/commands/amaw.md"
    echo "[x] .claude/commands/amaw.md (opt-in AMAW activator)"
  fi
fi

# 4. Doc dirs: specs, plans, audit, deferred
# Both default v2.2 and AMAW use docs/specs/ + docs/plans/ for CLARIFY/DESIGN/PLAN artifacts.
# audit/ + deferred/ are AMAW-specific but cheap to stub even without /amaw.
mkdir -p "$TARGET/docs/specs" "$TARGET/docs/plans"
[[ ! -f "$TARGET/docs/specs/.gitkeep" ]] && touch "$TARGET/docs/specs/.gitkeep" && echo "[x] docs/specs/ (for CLARIFY spec files)"
[[ ! -f "$TARGET/docs/plans/.gitkeep" ]] && touch "$TARGET/docs/plans/.gitkeep" && echo "[x] docs/plans/ (for PLAN decomposition files)"

if [[ $NO_AMAW -eq 0 ]]; then
  mkdir -p "$TARGET/docs"
  if [[ -f "$TARGET/docs/amaw-workflow.md" ]]; then
    echo "[!] docs/amaw-workflow.md already exists — NOT overwriting"
  else
    cp "$SCRIPT_DIR/AMAW.md" "$TARGET/docs/amaw-workflow.md"
    echo "[x] docs/amaw-workflow.md (AMAW v3.0 opt-in spec)"
  fi

  # 4b. Stub the AUDIT_LOG.jsonl directory + .gitkeep
  mkdir -p "$TARGET/docs/audit"
  if [[ ! -f "$TARGET/docs/audit/.gitkeep" ]]; then
    touch "$TARGET/docs/audit/.gitkeep"
    echo "[x] docs/audit/.gitkeep (AUDIT_LOG.jsonl will be created on first AMAW run)"
  fi

  # 4c. Stub DEFERRED.md
  mkdir -p "$TARGET/docs/deferred"
  if [[ ! -f "$TARGET/docs/deferred/DEFERRED.md" ]]; then
    cat > "$TARGET/docs/deferred/DEFERRED.md" <<'EOF'
# Deferred Items

<!-- Managed by Scribe (AMAW) or main session (default mode). Do not edit manually unless cleaning up. -->
<!-- Next ID: 001 -->

(no deferred items yet)
EOF
    echo "[x] docs/deferred/DEFERRED.md (stub)"
  fi
fi

# 5. Update .gitignore
if [[ -f "$TARGET/.gitignore" ]]; then
  if grep -q "workflow-state.json" "$TARGET/.gitignore"; then
    echo "[x] .gitignore already has .workflow-state.json"
  else
    echo "" >> "$TARGET/.gitignore"
    echo "# Workflow state (per-session, not committed)" >> "$TARGET/.gitignore"
    echo ".workflow-state.json" >> "$TARGET/.gitignore"
    echo "" >> "$TARGET/.gitignore"
    echo "# Deprecated per-phase gate files (AMAW v1.0 → v1.1 uses AUDIT_LOG.jsonl instead)" >> "$TARGET/.gitignore"
    echo ".phase-gates/" >> "$TARGET/.gitignore"
    echo "[x] Added .workflow-state.json + .phase-gates/ to .gitignore"
  fi
else
  cat > "$TARGET/.gitignore" <<'EOF'
# Workflow state (per-session, not committed)
.workflow-state.json

# Deprecated per-phase gate files (AMAW v1.0 → v1.1 uses AUDIT_LOG.jsonl instead)
.phase-gates/
EOF
  echo "[x] Created .gitignore"
fi

echo ""
echo "Done! Next steps:"
echo "  1. Paste agentic-workflow/WORKFLOW.md (or CLAUDE.md.snippet) into your CLAUDE.md"
if [[ $NO_AMAW -eq 0 ]]; then
  echo "  2. (Optional) Read docs/amaw-workflow.md to learn when to invoke /amaw"
  echo "  3. For everyday tasks, default v2.2 just works. For data migrations / schema /"
  echo "     security paths, type '/amaw' to enable cold-start sub-agent reviews."
fi
echo "  4. Test: cd $TARGET && bash scripts/workflow-gate.sh status"
echo ""
