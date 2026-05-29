#!/usr/bin/env bash
# L4.N dependency-registry-lint.sh — SR06 §12AI.2
#
# Every outbound dependency client (HTTP/DB/Redis) MUST be constructed
# via contracts/dependencies/ClientFactory. Raw http.Client{}, sql.Open,
# redis.NewClient calls outside the factory bypass the matrix.yaml
# governance and are blocked by this lint.
#
# The contracts/resilience/ + contracts/dependencies/ packages themselves
# are exempt (they ARE the factory). The factory in turn produces
# WrappedClientConfig which service code consumes.
#
# Heuristic — may produce false positives in tests; *_test.go is allowlisted.
#
# Cycle 18 ships this lint in WARN mode (exit 0) because services have
# not yet been refactored to route through the factory. Cycle 19+ flips
# to ERROR mode once all consumers are migrated. The matrix.yaml schema +
# loader + factory ARE landing today (the gate-flip is purely process).
#
# Exit 0 = clean OR warn-mode active; 1 = violations + error-mode active.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
mode="${DEPENDENCY_REGISTRY_LINT_MODE:-warn}"   # warn | error
violations=0

# Raw Go HTTP client construction outside the contracts/* tree.
hits=$(grep -rnE '\b(http\.Client\{|http\.NewRequest\b|sql\.Open\b|redis\.NewClient\b)' \
  --include='*.go' "$repo_root/services" 2>/dev/null \
  | grep -vE '_test\.go:' \
  | grep -vE 'contracts/(resilience|dependencies)/' \
  || true)
if [[ -n "$hits" ]]; then
  echo "[dependency-registry] raw client constructors outside ClientFactory:"
  echo "$hits" | sed 's/^/  /'
  violations=$((violations + 1))
fi

# Raw Rust reqwest::Client::new / sqlx::PgPool::connect outside crates/dp-kernel
hits=$(grep -rnE '\b(reqwest::Client::new\b|sqlx::PgPool::connect\b)' \
  --include='*.rs' "$repo_root/services" "$repo_root/crates" 2>/dev/null \
  | grep -vE 'mod tests' \
  | grep -vE '/tests/' \
  | grep -vE '_test\.rs:' \
  | grep -vE 'crates/dp-kernel/' \
  || true)
if [[ -n "$hits" ]]; then
  echo "[dependency-registry] raw Rust client constructors outside ClientFactory:"
  echo "$hits" | sed 's/^/  /'
  violations=$((violations + 1))
fi

if [[ $violations -gt 0 ]]; then
  if [[ "$mode" == "error" ]]; then
    echo "[dependency-registry] FAIL — $violations raw client construction(s) (SR06 §12AI.2)"
    exit 1
  fi
  echo "[dependency-registry] WARN — $violations raw client construction(s) (cycle 18 warn-mode; cycle 19+ flips to error after consumer migration)"
  exit 0
fi
echo "[dependency-registry] PASS"
exit 0
