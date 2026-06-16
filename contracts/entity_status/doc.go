// Package entity_status — L4.E shared-kernel surface for resolving the
// lifecycle state of any addressable game entity (PC, NPC, region, world_kv).
//
// # Why a shared kernel
//
// Multiple services (chat-service, knowledge-service, world-service, gateway)
// need to answer the same question: "is this entity still active, severed,
// archived, dropped, or user-erased?". The naive approach (each service
// rewrites the lookup against its own projection rows) leads to drift:
// chat-service treats a `severed` entity as `active`; knowledge-service treats
// `archived` as `dropped`. We ship ONE GetEntityStatus surface here so every
// caller answers consistently.
//
// # Resolution order (S10 §12Z)
//
// We resolve in priority order and STOP at the first match:
//
//	1. pii_kek         — user_erased? (GDPR Art. 17 crypto-shred)
//	2. reality_registry — reality dropped / soft_deleted / frozen?
//	3. reality_ancestry — entity moved between realities? (severed/archived)
//	4. projections     — straight read from the 10 L3.A projection tables
//	                     (cycle 13) via load_aggregate / direct PK lookup
//
// # Compound precedence
//
// If an entity matches multiple states, precedence wins:
//
//	dropped > user_erased > severed > archived > active
//
// # Cache
//
// 60s Redis cache; invalidated event-driven via MetaWrite outbox events on
// reality_registry (cycle 2) + pii_kek (cycle 3). Cache misses MUST resolve
// against the projections layer.
//
// # What this package ships in cycle 20 (L4.E)
//
//   - GoneState enum (5 variants — active, severed, archived, dropped, user_erased)
//   - EntityStatusEnvelope (versioned wire format)
//   - Resolver interface + DefaultResolver (uses cycle-12 load_aggregate pattern)
//   - Compound precedence helper
//   - 60s cache contract (CacheReader / CacheWriter)
//
// # Q-IDs honored
//
//   - Q-L4-1: Rust mirror lives in crates/dp-kernel/src/entity_status.rs
//   - Q-L3-4: EnvelopeVersion field carries forward verification metadata when
//     the projection row has it (passes through; not synthesized here)
//
// # What is NOT in cycle 20
//
//   - Concrete sql.DB-backed resolver bindings — caller-supplied via the
//     ProjectionReader interface (matches the contracts/meta driver-agnostic
//     pattern). Wired in service cycles 23+.
//   - Redis adapter — caller-supplied via CacheReader/CacheWriter.
//   - reality_ancestry table itself (cycle 5 + 27).
package entity_status
