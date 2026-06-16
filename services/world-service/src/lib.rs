//! `world-service` — geography substrate service for the LLM MMO RPG.
//!
//! ## Cycle 5 (L1.C + L1.G.3) surface
//!
//! Cycle 5 of the foundation mega-task lands the per-reality DB lifecycle
//! infrastructure described in `docs/plans/2026-05-29-foundation-mega-task/
//! L1C_to_L_infrastructure.md` §1 (L1.C) + §5 (L1.G):
//!
//! | Module              | Layer plan ID | Purpose                                                                    |
//! |---------------------|---------------|----------------------------------------------------------------------------|
//! | [`provisioner`]     | L1.C.1        | 11-step `provision_reality()` flow per R04 §12D.1                          |
//! | [`deprovisioner`]   | L1.C.2        | 6-step `deprovision_reality()` flow (idempotent)                           |
//! | [`capacity_planner`]| L1.C.3        | Shard allocator — picks the least-full shard within capacity thresholds    |
//! | [`db_pool`]         | L1.G.3        | App-side pool wrapper — 1 pool per shard host (NOT per DB) for pgbouncer   |
//! | binary `orphan_scanner` | L1.C.4    | Nightly cron — 7-day grace, then drop                                      |
//!
//! The GEO_001 aggregate behavior is still blocked on the DP-kernel (cycle 17).
//! What you see here is the **infrastructure** plumbing — provisioner/db_pool
//! call into the meta library (`crates/meta-rs`) for `RealityRouting` reads
//! and (in a later cycle) MetaWrite via RPC to the meta-worker.
//!
//! ## Cycle 26 (L5.G) surface
//!
//! RAID cycle 26 adds the L5.G reality seeder module per
//! `docs/plans/2026-05-29-foundation-mega-task/L5_inbound_canon.md` §L5.G:
//!
//! | Module                        | Layer plan ID | Purpose                                                          |
//! |-------------------------------|---------------|------------------------------------------------------------------|
//! | [`reality_seeder`]            | L5.G.1        | Background orchestrator: seeding → active flow                   |
//! | [`reality_seeder::book_reader`]      | L5.G.2 | book-service RPC trait (regions + locale)                        |
//! | [`reality_seeder::canon_reader`]     | L5.G.3 | glossary-service RPC trait (binds to L5.F.2 ExportCanonForSeed) |
//! | [`reality_seeder::knowledge_reader`] | L5.G.4 | knowledge-service RPC trait (NPC proxies)                        |
//! | [`reality_seeder::translation_orchestrator`] | L5.G.5 | Q-L5-2 translation gate (when locales differ)            |
//! | [`reality_seeder::checkpointer`]     | L5.G.6 | Per-100-entry checkpoint for resumability                        |
//! | [`reality_seeder::lifecycle_transitioner`] | L5.G.7 | Wraps AttemptStateTransition (cycle-5 contract)            |
//! | [`reality_seeder::audit`]            | L5.G    | Q-L1A-3 full audit sink (per-phase + per-write)                  |
//!
//! The seeder hands off canon entries via the cycle-24 L5.B meta-worker
//! `canon_writer` interface — the seeder's `CanonProjectionWriter` trait
//! aligns 1:1 with the meta-worker writer's `UpsertCanon` shape so the
//! production binding is a one-line adapter.
//!
//! ## Why Rust here
//!
//! Per CLAUDE.md "Language rule: Go for domain services, Python for AI/LLM
//! services, **Rust for game-engine / hot-path domain**". The provisioner is
//! the entry point for per-reality lifecycle commands originating from the
//! kernel side, so it lives in Rust alongside the upcoming world-service
//! command handlers. Go services that need to write to `reality_registry`
//! use the existing `contracts/meta` library; this Rust surface complements
//! it, not replaces it.

#![forbid(unsafe_code)]
#![warn(missing_docs, rust_2018_idioms)]

pub mod capacity_planner;
pub mod db_pool;
pub mod deprovisioner;
pub mod embedding_queue;
pub mod errors;
pub mod provisioner;
pub mod reality_seeder;
pub mod rebuild;
pub mod replay_aggregate;

pub use capacity_planner::{CapacityPlanner, CapacityThresholds, ShardCapacity, ShardId};
pub use db_pool::{DbPoolKey, DbPoolRegistry, ShardHost};
pub use deprovisioner::{DeprovisionReport, DeprovisionRequest, Deprovisioner};
// L3.I cycle 16 — embedding queue (Q-L3-1 V1: in world-service).
pub use embedding_queue::{
    AuditEvent, AuditOutcome, AuditWriter, CountingAuditWriter, EMBEDDING_DIM, EmbedResult,
    EmbeddingProvider, EmbeddingWriter, MemoryRef, Queue as EmbeddingQueue,
    Worker as EmbeddingWorker,
};
// DEFERRED-059 core — embedding-queue live wiring (sqlx writer + meta audit +
// fail-closed provider + axum/prometheus ops surface + tokio drain loop).
pub use embedding_queue::live::{
    Config as EmbeddingWorkerConfig, MetaAuditWriter, Metrics as EmbeddingMetrics,
    MetricsAuditWriter, NotWiredProvider, SqlxEmbeddingWriter,
};
pub use errors::ProvisionerError;
pub use provisioner::{ProvisionReport, ProvisionRequest, Provisioner};
// L5.G cycle 26 — reality seeder + supporting traits.
pub use reality_seeder::{
    AuditEvent as SeederAuditEvent, AuditSink as SeederAuditSink, BookMetadata, BookReader,
    CanonEntry as SeedCanonEntry, CanonExporter, CanonProjectionIntent, CanonProjectionWriter,
    CheckpointStore, KnowledgeReader, LifecycleTransitioner, NpcProxy, RealitySeeder,
    RealityStatus, Region, SeedCheckpoint, SeedExportResult, SeedReport, SeedRequest, SeederDeps,
    SeederError, TranslationGateway, TranslationOrchestrator,
};
