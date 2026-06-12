// Package validatorsgo is the Go mirror of
// `crates/dp-kernel/src/event_validator.rs` (L2.I schema validation on write).
//
// # Contract
//
// Every Go event-append site MUST call `Registry.Validate(envelope.EventType,
// envelope.EventVersion, envelope.Payload)` BEFORE persisting the event to
// the per-reality events table. Same R03 §12C.4 rule: NO dev bypass, ALL
// envs enforced.
//
// # Field descriptor format
//
// Mirrors the Rust SchemaDescriptor / RequiredField / FieldType triple.
// Use BuildSeedRegistry() for the cycle 8 seed events (reality.created,
// npc.said v1+v2, world.tick).
package validatorsgo
