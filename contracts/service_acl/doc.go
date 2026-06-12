// Package service_acl is the canonical service-to-service Access Control
// matrix SDK. It loads the matrix.yaml registry shipped alongside this
// package (a copy is kept at the repo root for cycle-6 lint compatibility),
// then exposes the two runtime primitives that every inbound RPC handler
// MUST traverse:
//
//   - CheckRPCAllowed(caller, callee, rpc) — default-DENY authorization gate.
//   - EmitAudit(...)                       — full audit row writer (Q-L1A-3
//     locked NO sampling) into the meta `service_to_service_audit` table.
//
// L4.M (cycle 22) FORMALIZES the schema that cycle-6 seeded with raw YAML.
// The cycle-6 file (`contracts/service_acl/matrix.yaml`) used a permissions
// shape keyed by table-name (e.g., `meta_write_audit: [INSERT]`). That shape
// still works for the cycle-6 lint and for Postgres role-grant generation,
// but it CANNOT answer the SR11 RPC-level question "is caller X allowed to
// call rpc Y on callee Z?" — which is what the SVID verifier middleware
// needs at request time.
//
// L4.M.1 therefore extends each service entry with an OPTIONAL `rpcs` map:
//
//	services:
//	  - name: meta-worker
//	    rpcs:
//	      MetaWrite:       { allowed_callers: [publisher, world-service, ...] }
//	      MetaWriteBatch:  { allowed_callers: [migration-orchestrator] }
//
// `allowed_callers` is the authoritative answer. Missing `rpcs` map ⇒ no
// RPCs declared (so all RPC checks return Deny by default). Missing entry
// in a present `rpcs` map ⇒ Deny (default-DENY invariant). This is the
// behavior the SVID verifier (L4.M.4 — middleware skeleton) relies on.
//
// Q-L1A-3 LOCKED — full audit. EmitAudit constructs a
// `service_to_service_audit` row for EVERY check (allow + deny + error +
// timeout). No sampling. Callers integrate via the cycle-2 MetaWrite() path
// (one row per call); this package only constructs the typed audit value.
//
// SPIFFE / SVID. Production deployments will issue SPIFFE-ID-bearing SVIDs
// to each service; the inbound middleware verifies the SVID, extracts the
// caller's service name, then calls CheckRPCAllowed. This package ships
// the deterministic ALLOW/DENY decision; the SVID issuance + verification
// cryptography ships in a separate security-track sub-program (see
// docs/plans/2026-05-29-foundation-mega-task/L4_sdk_kernel_api.md §L4.M.3).
//
// Rust mirror — Q-L4-1: see `crates/dp-kernel::service_acl` for Go+Rust
// parity. Decision semantics MUST match byte-for-byte (same default-DENY,
// same field names in the audit row).
package service_acl
