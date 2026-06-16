// Package supply_chain — L4.J (RAID cycle 19) — formalizes the
// canonical schema, loader, and runtime provenance helpers for the
// dep-pinning + SBOM + license-allowlist policy that cycle 7 first
// shipped as a CI lint (`scripts/dep-pinning-lint.sh`).
//
// Scope (SR10 §12AM):
//
//   - policy.yaml — declares: dep-pinning requirements per ecosystem
//     (Go/Rust/Python/JS/Docker), license allowlist, banned packages,
//     SBOM format (CycloneDX-1.5 default).
//   - sbom.go — emit a CycloneDX-shaped SBOM row per build into the
//     `supply_chain_events` (meta) table. The full meta-DB writer
//     ships cycle 20+ (contracts/meta/); this package ships the typed
//     row + buffer + Verify helper.
//   - provenance.go — Provenance.Verify(artifact, signature) hook
//     surface. Cycle-19 ships a stub interface that returns
//     ErrSignatureUnverified for any input; cycle 21+ wires
//     cosign/sigstore implementations behind the interface.
//
// Companion lints:
//   - scripts/dep-pinning-lint.sh (L1.K.8, shipped cycle 7) — file-
//     existence checks for lockfiles. Cycle 19 keeps this as-is and
//     does NOT replace it.
//   - cycle 18 carry-forward: lints should eventually flip from warn
//     to error once the 30-day adoption window closes. Cycle 19 marks
//     the migration: dep-pinning-lint.sh already exits non-zero on
//     missing lockfiles (already error mode); Docker FROM-tag warning
//     remains warn-only and is the next flip candidate per cycle 22+.
//
// Q-L4-1 parity: Rust mirror lives in `crates/dp-kernel/src/supply_chain.rs`.
// Schema field names + enum wire strings are 1-for-1.
package supply_chain
