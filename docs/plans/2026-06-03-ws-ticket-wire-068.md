# Plan — 068 D-WS-TICKET-WIRE: WS ticket-hash base64 wire fix + Envelope seq≥1

**Date:** 2026-06-03 · **Size:** XL (cross-language wire contract) · **Branch:** mmo-rpg/foundation-mega-task
**Workflow:** v2.2 + cold-start `/review-impl` before commit (load-bearing wire contract, cross-track kernel touch). No push without approval. This is the **prerequisite** for 077's WS ticket validation.

## Context

`contracts/ws/v1.yaml` (frozen contract) declares `Ticket.origin_hash` + `client_fingerprint_hash` as `{type: string, format: byte}` = **base64** ("32 raw bytes base64"), and `Envelope.seq` as `{int64, minimum: 1}` (required for data, omitted for control). Two drifts (D-WS-TICKET-WIRE / 068):

1. **Go `contracts/ws/ticket.go`** stores the hashes as `[32]byte` **arrays**. Go's `encoding/json` marshals a `[N]byte` *array* as a **JSON int-array** (`[12,34,…]`); only `[]byte` *slices* base64-encode. So Go emits an int-array, not the spec's base64 string → a TS/Go client cannot interop per spec.
2. **`Envelope.Validate` enforces neither `seq≥1` for data frames** (Go `envelope.go` nor Rust `dp-kernel/ws.rs`).

The Rust `Ticket` (dp-kernel/ws.rs) has **no `Serialize`/`Deserialize` derive** (server-side mirror; it consumes the `Envelope`, not the ticket-over-wire), so the int-array worry does NOT manifest there — the only Rust change is the `seq` rule.

**Direction (resolves 068's "base64 OR int-array" fork): align CODE to the frozen contract = base64.** Contract-first (CLAUDE.md). No working client interops today ("cannot interop per spec" + "before WS goes cross-process"), so there's nothing to break.

## Scope

| Change | File | Status |
|---|---|---|
| `Hash32 [32]byte` type w/ base64 `Marshal/UnmarshalJSON` (UnmarshalJSON enforces exactly 32 decoded bytes) | `contracts/ws/ticket.go` | REAL |
| `Ticket.OriginHash`/`ClientFingerprintHash` → `Hash32`; `Validate` zero-checks; `BindsTo*` signatures | `contracts/ws/ticket.go` | REAL |
| `WSSession.OriginHash`/`ClientFingerprint` → `Hash32` (server-side only, never serialized → type-consistency, no wire impact) | `contracts/ws/session_store.go` | REAL |
| `Envelope.Validate`: add `KindData ⇒ seq≥1` | `contracts/ws/envelope.go` | REAL |
| `Envelope::validate`: add `Data ⇒ seq≥1` (the ONLY kernel touch — surgical) | `crates/dp-kernel/src/ws.rs` | REAL |
| Tests: base64 round-trip (hash is a base64 string, NOT int-array; 32-byte enforce) + data-requires-seq (Go + Rust) | `ticket_test.go`, `envelope_test.go`, `ws.rs` | REAL |
| Test-literal updates `[32]byte{…}` → `Hash32{…}` | `ticket_test.go`, `session_store_test.go` | mechanical |

**No `ws/v1.yaml` change** (the spec is correct; the code drifted). base64 = `StdEncoding` (OpenAPI `format: byte` default, with padding; Node `Buffer.from(s,'base64')` reads it).

## Verification
- `go test ./...` in `contracts/ws` (incl. new base64 round-trip + seq tests); `gofmt`.
- `cargo test -p dp-kernel ws` (incl. new data-requires-seq); `cargo fmt --check` + `clippy` for ws.rs.
- Relevant lints: `lint-contract.sh` (OpenAPI unchanged → still valid), `language-rule` (contracts/crates unaffected), `lint-foundation` subset.
- **Cross-language parity:** the round-trip test pins Go's base64 shape; Rust Envelope round-trip already tested; the `seq≥1` rule added to BOTH `Validate`s in lockstep (Q-L4-1).
- **Live smoke:** N/A (pure contract/lib; no process). The real cross-process interop (auth-service issue → game-server/TS redeem) lands with 077.

## Workflow / guardrails
- Cross-track note: the Rust `dp-kernel/ws.rs` touch is ONE validation rule + ONE test — surgical, flagged at POST-REVIEW for the kernel/transport track owner. No other dp-kernel code touched.
- Stage only changed files (no `-A`). Co-author trailer. No push without approval.
- After 068: present a concrete **077** plan (game-server TS ticket redemption/validation against the now-correct base64 ticket, per-conn/per-user rate caps [clears 035], connection-lifecycle audit [structured-log interim], AWS-SG doc).
