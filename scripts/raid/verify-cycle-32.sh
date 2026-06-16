#!/usr/bin/env bash
# verify-cycle-32.sh — L7.E + L7.G Logging + Tracing libs (2 DPS).
#
# Acceptance gate. Exit 0 = pass; non-zero = fail.
#
# Cycle 32 scope (2 DPS — L, L7 layer begins):
#
#   DPS 1 (L7.E — Structured Logging library):
#     * contracts/logging/doc.go
#     * contracts/logging/go.mod
#     * contracts/logging/level.go
#     * contracts/logging/field.go
#     * contracts/logging/redactor.go               (cycle 22 PII SDK seam)
#     * contracts/logging/compile_guard.go          (dev: IsProdBuild=false)
#     * contracts/logging/compile_guard_prod.go     (prod: IsProdBuild=true)
#     * contracts/logging/trace_correlation.go      (bridge to L7.G)
#     * contracts/logging/helpers.go                (PII/Sensitive/Normal)
#     * contracts/logging/logger.go                 (JSONLogger + Logger iface)
#     * contracts/logging/logger_test.go
#     * contracts/logging/prod_test.go              (+build prod)
#     * crates/dp-kernel/src/logging.rs             (Rust mirror, Q-L4-1)
#     * scripts/logging-discipline-lint.sh
#
#   DPS 2 (L7.G — Distributed Tracing library):
#     * contracts/tracing/doc.go
#     * contracts/tracing/go.mod
#     * contracts/tracing/context.go                (W3C traceparent parse/format)
#     * contracts/tracing/propagation.go            (Inject/Extract over MapHeaders)
#     * contracts/tracing/span.go                   (Span iface + InMemorySpan)
#     * contracts/tracing/sampler.go                (Probabilistic + Always)
#     * contracts/tracing/exporter.go               (Exporter iface + InMemory)
#     * contracts/tracing/redactor.go               (cycle 22 PII SDK seam)
#     * contracts/tracing/tracer.go                 (Tracer iface + Noop)
#     * contracts/tracing/tracing_test.go
#     * crates/dp-kernel/src/tracing.rs             (Rust mirror, Q-L4-1)
#     * scripts/tracing-completeness-lint.sh
#
#   Both:
#     * contracts/observability/inventory.yaml      (3 new metrics, shipped_cycle 32)
#     * crates/dp-kernel/Cargo.toml                  (prod feature gate)
#     * crates/dp-kernel/src/lib.rs                  (mod logging + mod tracing)
#
# LOCKED decisions enforced:
#   Q-L7F-1 — Loki self-hosted V1 (informs cycle 33; not implemented here)
#   Q-L7-3  — NO service mesh; tracing via library not Istio/Linkerd
#   Q-L7-4  — Frontend RUM owned by frontend-game team; foundation backend only
#   Cycle 22 L4.Q PII SDK — Redactor interface, no bare regex
#   Cycle 19 L4.H — Log.Sensitive helper shape + span-name regex
#   Cycle 8 envelope — trace context propagates via Metadata map (carry-forward)

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$repo_root"

step=0
pass() { step=$((step+1)); echo "[verify-cycle-32] step $step PASS: $1"; }
fail() { step=$((step+1)); echo "[verify-cycle-32] step $step FAIL: $1" >&2; exit 1; }
note() { echo "[verify-cycle-32] note: $1"; }

# ─────────────────────────────────────────────────────────────────────────
# 1. File presence — DPS 1 (L7.E logging)
# ─────────────────────────────────────────────────────────────────────────
for f in \
    contracts/logging/doc.go \
    contracts/logging/go.mod \
    contracts/logging/level.go \
    contracts/logging/field.go \
    contracts/logging/redactor.go \
    contracts/logging/compile_guard.go \
    contracts/logging/compile_guard_prod.go \
    contracts/logging/trace_correlation.go \
    contracts/logging/helpers.go \
    contracts/logging/logger.go \
    contracts/logging/logger_test.go \
    contracts/logging/prod_test.go \
    crates/dp-kernel/src/logging.rs \
    scripts/logging-discipline-lint.sh ; do
    [[ -f "$f" ]] || fail "cycle-32 DPS 1 (L7.E) file missing: $f"
done
pass "L7.E files present (logging lib + Rust mirror + lint)"

# ─────────────────────────────────────────────────────────────────────────
# 2. File presence — DPS 2 (L7.G tracing)
# ─────────────────────────────────────────────────────────────────────────
for f in \
    contracts/tracing/doc.go \
    contracts/tracing/go.mod \
    contracts/tracing/context.go \
    contracts/tracing/propagation.go \
    contracts/tracing/span.go \
    contracts/tracing/sampler.go \
    contracts/tracing/exporter.go \
    contracts/tracing/redactor.go \
    contracts/tracing/tracer.go \
    contracts/tracing/tracing_test.go \
    crates/dp-kernel/src/tracing.rs \
    scripts/tracing-completeness-lint.sh ; do
    [[ -f "$f" ]] || fail "cycle-32 DPS 2 (L7.G) file missing: $f"
done
pass "L7.G files present (tracing lib + Rust mirror + lint)"

# ─────────────────────────────────────────────────────────────────────────
# 3. Q-L7-3 — NO service mesh introduction (Istio / Linkerd)
# ─────────────────────────────────────────────────────────────────────────
if [ -d infra/istio ] || [ -d infra/linkerd ] || [ -d infra/envoy ] ; then
    fail "Q-L7-3 violation: service-mesh infra introduced (foundation V1 = no mesh)"
fi
# also grep for sidecar config patterns
if git grep -E 'kind:[[:space:]]*(VirtualService|DestinationRule|ServiceMeshController)' -- 'infra/**' 2>/dev/null | grep -v existing-prod | head -1 | grep -q . ; then
    fail "Q-L7-3 violation: service-mesh CRD references in infra/"
fi
pass "Q-L7-3 honored: no service-mesh infra (foundation = in-library tracing only)"

# ─────────────────────────────────────────────────────────────────────────
# 4. Q-L7-4 — NO frontend tracing in this cycle's diff
# ─────────────────────────────────────────────────────────────────────────
if git diff --name-only HEAD 2>/dev/null | grep -E '^frontend-game/' | grep -i trac 2>/dev/null | head -1 | grep -q . ; then
    fail "Q-L7-4 violation: frontend-game tracing touched (foundation = backend only)"
fi
pass "Q-L7-4 honored: no frontend RUM in cycle-32 (foundation backend only)"

# ─────────────────────────────────────────────────────────────────────────
# 5. Cycle 22 PII SDK seam — Redactor INTERFACE, no bare regex in logging
# ─────────────────────────────────────────────────────────────────────────
# Logging library must NOT contain regex-based PII detection (that pattern
# was explicitly rejected by cycle 22 in favor of the typed Redactor seam).
if grep -nE 'regexp\.MustCompile\(' contracts/logging/*.go ; then
    fail "cycle 22 invariant: bare regex in logging library (use Redactor interface)"
fi
grep -q 'Redactor' contracts/logging/redactor.go \
    || fail "cycle 22 seam: contracts/logging/redactor.go must define Redactor interface"
grep -q 'cycle 22' contracts/logging/redactor.go \
    || fail "cycle 22 seam: redactor.go must cite the LOCKED decision"
pass "Cycle 22 PII SDK seam: Redactor interface (no bare regex in logging)"

# ─────────────────────────────────────────────────────────────────────────
# 6. Compile-time prod guard — both files present + flip the const
# ─────────────────────────────────────────────────────────────────────────
grep -q '//go:build !prod' contracts/logging/compile_guard.go \
    || fail "compile_guard.go missing !prod build tag"
grep -q 'const IsProdBuild = false' contracts/logging/compile_guard.go \
    || fail "compile_guard.go must set IsProdBuild = false in dev"
grep -q '//go:build prod' contracts/logging/compile_guard_prod.go \
    || fail "compile_guard_prod.go missing prod build tag"
grep -q 'const IsProdBuild = true' contracts/logging/compile_guard_prod.go \
    || fail "compile_guard_prod.go must set IsProdBuild = true"
pass "Compile-time prod guard: both build-tagged files present + flip IsProdBuild"

# ─────────────────────────────────────────────────────────────────────────
# 7. W3C traceparent format — strict 55-char regex
# ─────────────────────────────────────────────────────────────────────────
grep -qF '^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$' contracts/tracing/context.go \
    || fail "tracing: W3C traceparent regex not strict (must pin version=00 + lowercase hex + segment lengths)"
grep -qF 'len(s) != 55' contracts/tracing/context.go \
    || fail "tracing: traceparent length not 55 (W3C spec)"
pass "W3C traceparent: strict 55-char format + lowercase hex + version=00"

# ─────────────────────────────────────────────────────────────────────────
# 8. Cycle 8 envelope carry-forward — Metadata-as-Headers via MapHeaders
# ─────────────────────────────────────────────────────────────────────────
grep -q 'type MapHeaders map\[string\]string' contracts/tracing/propagation.go \
    || fail "tracing: MapHeaders type missing (cycle-8 envelope carrier)"
grep -q 'Inject' contracts/tracing/propagation.go \
    || fail "tracing: Inject helper missing"
grep -q 'Extract' contracts/tracing/propagation.go \
    || fail "tracing: Extract helper missing"
pass "Cycle 8 envelope: trace context propagates via MapHeaders Inject/Extract"

# ─────────────────────────────────────────────────────────────────────────
# 9. Cycle 19 span-name convention — snake_case.dot regex pinned
# ─────────────────────────────────────────────────────────────────────────
grep -qF '[a-z][a-z0-9_]*' contracts/tracing/span.go \
    || fail "tracing: span-name regex not pinned (cycle-19 L4.H convention)"
pass "Cycle 19 span-name convention pinned in tracing/span.go"

# ─────────────────────────────────────────────────────────────────────────
# 10. Q-L4D-1 OPAQUE payload — no direct OTel/OpenTelemetry SDK imports
# ─────────────────────────────────────────────────────────────────────────
if grep -rE '"go\.opentelemetry\.io/otel(/[^"]*)?"' contracts/tracing/ 2>/dev/null ; then
    fail "Q-L4D-1: direct go.opentelemetry.io/otel import (foundation ships interface, services bind adapter)"
fi
if grep -rE '"github\.com/open-telemetry' contracts/tracing/ 2>/dev/null ; then
    fail "Q-L4D-1: direct OpenTelemetry SDK import detected"
fi
pass "Q-L4D-1 honored: tracing library is OPAQUE — no OTel SDK dep"

# ─────────────────────────────────────────────────────────────────────────
# 11. Cycle 22 carry-forward — tracing also uses Redactor interface
# ─────────────────────────────────────────────────────────────────────────
grep -q 'type Redactor interface' contracts/tracing/redactor.go \
    || fail "cycle 22 seam: contracts/tracing/redactor.go must define Redactor interface"
grep -q 'PIIAttributeKeys' contracts/tracing/tracer.go \
    || fail "tracing: PIIAttributeKeys allow-list missing (cycle 22 Redactor wiring)"
pass "Cycle 22 carry-forward: tracing PII attribute allow-list + Redactor interface"

# ─────────────────────────────────────────────────────────────────────────
# 12. Go build + test — contracts/logging (dev build)
# ─────────────────────────────────────────────────────────────────────────
if command -v go >/dev/null 2>&1; then
    (cd contracts/logging && go vet ./... && go test ./... > /tmp/c32-log-dev.log 2>&1) \
        || { cat /tmp/c32-log-dev.log; fail "contracts/logging dev-build vet/test failed"; }
    pass "contracts/logging go vet + test (dev build)"
else
    note "go absent — skipping logging dev test"
fi

# ─────────────────────────────────────────────────────────────────────────
# 13. Go test — contracts/logging (prod build, IsProdBuild=true)
# ─────────────────────────────────────────────────────────────────────────
if command -v go >/dev/null 2>&1; then
    (cd contracts/logging && go test -tags=prod ./... > /tmp/c32-log-prod.log 2>&1) \
        || { cat /tmp/c32-log-prod.log; fail "contracts/logging prod-build test failed"; }
    pass "contracts/logging go test (prod build — IsProdBuild=true honored)"
fi

# ─────────────────────────────────────────────────────────────────────────
# 14. Go build + test — contracts/tracing
# ─────────────────────────────────────────────────────────────────────────
if command -v go >/dev/null 2>&1; then
    (cd contracts/tracing && go vet ./... && go test ./... > /tmp/c32-trace.log 2>&1) \
        || { cat /tmp/c32-trace.log; fail "contracts/tracing vet/test failed"; }
    pass "contracts/tracing go vet + test"
fi

# ─────────────────────────────────────────────────────────────────────────
# 15. Rust mirror — dp-kernel logging + tracing modules (default features)
# ─────────────────────────────────────────────────────────────────────────
if command -v cargo >/dev/null 2>&1; then
    cargo test -p dp-kernel --lib logging:: > /tmp/c32-rs-log.log 2>&1 \
        || { cat /tmp/c32-rs-log.log; fail "dp-kernel logging:: tests failed"; }
    pass "dp-kernel logging:: Rust tests (default features)"

    cargo test -p dp-kernel --lib tracing:: > /tmp/c32-rs-trace.log 2>&1 \
        || { cat /tmp/c32-rs-trace.log; fail "dp-kernel tracing:: tests failed"; }
    pass "dp-kernel tracing:: Rust tests"
else
    note "cargo absent — skipping Rust mirror tests"
fi

# ─────────────────────────────────────────────────────────────────────────
# 16. Rust prod feature — dp-kernel logging::prod_drops_debug
# ─────────────────────────────────────────────────────────────────────────
if command -v cargo >/dev/null 2>&1; then
    cargo test -p dp-kernel --lib --features=prod logging:: > /tmp/c32-rs-log-prod.log 2>&1 \
        || { cat /tmp/c32-rs-log-prod.log; fail "dp-kernel logging:: prod feature failed"; }
    pass "dp-kernel logging:: Rust prod-feature build + test"
fi

# ─────────────────────────────────────────────────────────────────────────
# 17. inventory.yaml — 3 new metrics with shipped_cycle: 32
# ─────────────────────────────────────────────────────────────────────────
for metric in lw_log_redactions_total lw_trace_spans_total lw_trace_sampling_decisions_total ; do
    grep -qE "^  - name: ${metric}$" contracts/observability/inventory.yaml \
        || fail "inventory.yaml missing metric: ${metric}"
    if ! awk -v m="${metric}" '/^  - name: /{cur=$NF} cur==m && /shipped_cycle:/{print; exit}' \
        contracts/observability/inventory.yaml | grep -q 'shipped_cycle: 32'; then
        fail "inventory.yaml: ${metric} must have shipped_cycle: 32"
    fi
done
pass "inventory.yaml: 3 new L7.E + L7.G metrics declared with shipped_cycle: 32"

# ─────────────────────────────────────────────────────────────────────────
# 18. observability-inventory-lint regression
# ─────────────────────────────────────────────────────────────────────────
if [ -x scripts/observability-inventory-lint.sh ]; then
    if scripts/observability-inventory-lint.sh > /tmp/c32-inv-lint.log 2>&1; then
        pass "scripts/observability-inventory-lint.sh"
    else
        cat /tmp/c32-inv-lint.log
        fail "scripts/observability-inventory-lint.sh"
    fi
else
    note "observability-inventory-lint.sh not executable — skipping"
fi

# ─────────────────────────────────────────────────────────────────────────
# 19. logging-discipline-lint must run clean OR warn (mode default = warn)
# ─────────────────────────────────────────────────────────────────────────
if bash scripts/logging-discipline-lint.sh > /tmp/c32-log-lint.log 2>&1 ; then
    pass "scripts/logging-discipline-lint.sh (warn mode, exit 0)"
else
    cat /tmp/c32-log-lint.log
    fail "scripts/logging-discipline-lint.sh"
fi

# ─────────────────────────────────────────────────────────────────────────
# 20. tracing-completeness-lint must run clean OR warn (mode default = warn)
# ─────────────────────────────────────────────────────────────────────────
if bash scripts/tracing-completeness-lint.sh > /tmp/c32-trace-lint.log 2>&1 ; then
    pass "scripts/tracing-completeness-lint.sh (warn mode, exit 0)"
else
    cat /tmp/c32-trace-lint.log
    fail "scripts/tracing-completeness-lint.sh"
fi

# ─────────────────────────────────────────────────────────────────────────
# 21. B5 prod-isolation-lint — no edits to infra/existing-prod/
# ─────────────────────────────────────────────────────────────────────────
if [ -d infra/existing-prod ]; then
    if ! git diff --quiet HEAD -- infra/existing-prod/ 2>/dev/null; then
        fail "B5 prod-isolation: infra/existing-prod/ touched"
    fi
fi
pass "B5 prod-isolation-lint (no existing-prod/ edits)"

# ─────────────────────────────────────────────────────────────────────────
# 22. B6 secret-scan — extra strict, logging is a leak surface
# ─────────────────────────────────────────────────────────────────────────
banned='AKIA[0-9A-Z]\{16,\}\|AIza[0-9A-Za-z_-]\{35,\}\|-----BEGIN [A-Z ]*PRIVATE KEY-----\|api_key=\|password=.\{8,\}'
# also block real-looking emails in logging library source (PII slice scan)
pii_pattern='[a-z][a-z0-9_.-]\{2,\}@[a-z][a-z0-9.-]\{2,\}\.[a-z]\{2,\}'
for f in \
    contracts/logging/doc.go \
    contracts/logging/level.go \
    contracts/logging/field.go \
    contracts/logging/redactor.go \
    contracts/logging/compile_guard.go \
    contracts/logging/compile_guard_prod.go \
    contracts/logging/trace_correlation.go \
    contracts/logging/helpers.go \
    contracts/logging/logger.go \
    contracts/tracing/doc.go \
    contracts/tracing/context.go \
    contracts/tracing/propagation.go \
    contracts/tracing/span.go \
    contracts/tracing/sampler.go \
    contracts/tracing/exporter.go \
    contracts/tracing/redactor.go \
    contracts/tracing/tracer.go ; do
    [[ -f "$f" ]] || continue
    if grep -qE "$banned" "$f"; then
        fail "B6 secret-scan: $f contains banned pattern"
    fi
    if grep -qE "$pii_pattern" "$f"; then
        fail "B6 PII slice scan: $f contains real-looking email"
    fi
done
pass "B6 secret-scan: no banned patterns + no PII strings in cycle-32 src"

# ─────────────────────────────────────────────────────────────────────────
# 23. Cycle-21 invariants — contracts/prompt SDK signatures preserved
# ─────────────────────────────────────────────────────────────────────────
grep -q 'AssemblePrompt(ctx context.Context, pc PromptContext, sections SectionMap) (PromptBundle, error)' \
    contracts/prompt/composer.go \
    || fail "cycle-21 invariant: AssemblePrompt signature changed"
pass "cycle-21 invariants preserved (AssemblePrompt signature intact)"

# ─────────────────────────────────────────────────────────────────────────
# 24. Cycle-22 invariants — contracts/pii SDK signatures preserved
# ─────────────────────────────────────────────────────────────────────────
grep -q 'TagPIIUserGet' contracts/pii/sdk.go \
    || fail "cycle-22 invariant: TagPIIUserGet enum changed"
grep -q 'KEKManager' contracts/pii/sdk.go \
    || fail "cycle-22 invariant: KEKManager interface changed"
pass "cycle-22 invariants preserved (PII SDK signatures intact)"

# ─────────────────────────────────────────────────────────────────────────
echo
echo "[verify-cycle-32] all $step checks PASS"
exit 0
