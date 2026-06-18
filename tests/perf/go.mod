module github.com/loreweave/foundation/tests/perf

go 1.24.0

// S7 (perf harness). Standalone module — mirrors tests/workload-gen's pattern
// (no published modules in the monorepo). gonum is already a vetted workspace
// dependency (auth/book/catalog/glossary services pin v0.17.0); the USL
// curve-fitter uses gonum/optimize for the nonlinear least-squares refine.
require gonum.org/v1/gonum v0.17.0

require (
	github.com/google/uuid v1.6.0
	github.com/loreweave/foundation/contracts/events v0.0.0
)

require (
	golang.org/x/tools v0.30.0 // indirect
	gopkg.in/yaml.v3 v3.0.1 // indirect
)

// Monorepo pattern (mirrors tests/workload-gen): cross-module deps use a local
// replace. The F2 micro-benchmarks exercise the REAL event wire path so the
// benchmarked code is byte-identical to production (no drift).
replace github.com/loreweave/foundation/contracts/events => ../../contracts/events
