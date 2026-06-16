// Package events is the LoreWeave Event Schema Registry (R03 schema-as-code).
//
// L2.F (RAID cycle 8) — authoritative location for every event_type emitted
// across the platform. Each event is declared as a Go struct with annotation
// doc-comments parsed by the `tools/eventgen` codegen (L2.G):
//
//	// @event npc.said
//	// @version 1
//	// @description NPC utters a line of dialogue in-world.
//	type NpcSaidV1 struct {
//	    NpcId    uuid.UUID `json:"npc_id"`
//	    Text     string    `json:"text"`
//	    SceneId  uuid.UUID `json:"scene_id"`
//	}
//
// The active list lives in `_registry.yaml` (see registry.LoadRegistry).
// Adding a field is a v-bump; breaking changes require a NEW event_type
// (R03 §12C.5 — additive-first, deprecation cooldown).
//
// # Generated outputs (L2.G eventgen)
//
//   - `contracts/events/generated/registry_generated.go`  — Go dispatch table
//   - `contracts/events/generated/ts/`                    — TypeScript interfaces (frontend + gateway)
//   - `contracts/events/generated/python/`                — Pydantic models (chat / knowledge / roleplay)
//   - `contracts/events/generated/rust/`                  — Rust structs (world / travel / roleplay-rust)
//
// Polyglot scope per Q-L4-1 LOCKED: Rust + Go + Python runtime types; TS for
// frontend events + WS envelope.
//
// # Upcasters (L2.H)
//
// Cross-version transforms live in `contracts/events/upcasters_go/` (Go) and
// `crates/dp-kernel/src/upcaster.rs` (Rust). The eventgen tool stitches
// individual `@upcast` declarations into chains (v1→v2→v3) at build time.
//
// # Validation on write (L2.I)
//
// `crates/dp-kernel/src/event_validator.rs` + `contracts/events/validators_go/`
// reject malformed event payloads at append time (not at projection rebuild).
// Enforced in ALL envs — no dev bypass per R03 §12C.4.
package events
