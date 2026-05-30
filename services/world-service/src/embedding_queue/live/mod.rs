//! Live (production) wiring for the embedding queue — DEFERRED-059 **core**.
//!
//! The `embedding_queue` parent module is pure library code over abstract IO
//! traits ([`super::EmbeddingProvider`], [`super::EmbeddingWriter`],
//! [`super::AuditWriter`]). This `live` submodule binds those traits to real
//! infrastructure that exists at foundation level **today**:
//!
//! | Trait              | Live impl                       | Backed by |
//! |--------------------|---------------------------------|-----------|
//! | `EmbeddingWriter`  | [`SqlxEmbeddingWriter`]         | per-reality `npc_session_memory_embedding` (pgvector, migration 0006+0008) |
//! | `AuditWriter`      | [`MetaAuditWriter`]             | meta `service_to_service_audit` (migration 016) |
//! | `EmbeddingProvider`| [`NotWiredProvider`] (fail-closed) | — (the BYOK provider-gateway binding is the deferred `D-EMBEDDING-PROVIDER-WIRING` task) |
//!
//! Plus the ops surface: [`Metrics`] + [`MetricsAuditWriter`] (prometheus),
//! [`router`] (axum `/healthz`+`/readyz`+`/metrics`), and [`run_worker_loop`]
//! (tokio interval ticker + graceful shutdown).
//!
//! ## What is deliberately NOT here (tracked deferrals)
//!
//! - **Provider gateway** — `D-EMBEDDING-PROVIDER-WIRING`: a reqwest client to
//!   provider-registry-service `POST /internal/embed` (route + internal s2s
//!   auth already exist) + `reality_id → owner user_id` resolution (BYOK
//!   credential selection) + `model_ref` selection. First `reqwest` use in
//!   world-service; its own task (cross-service + BYOK billing attribution).
//! - **Enqueue trigger** — no `ProjectionRunner` exists at foundation level to
//!   call [`super::Queue::enqueue`]; stays under the domain-projection work (069/079).
//! - **Integrity re-enqueue** — blocked on `dp_kernel::load_aggregate` (same
//!   blocker as the integrity-checker).

pub mod audit_writer;
pub mod config;
pub mod metrics;
pub mod provider;
pub mod server;
pub mod sqlx_writer;
pub mod worker_loop;

pub use audit_writer::MetaAuditWriter;
pub use config::Config;
pub use metrics::{Metrics, MetricsAuditWriter};
pub use provider::NotWiredProvider;
pub use server::{AppState, router};
pub use sqlx_writer::SqlxEmbeddingWriter;
pub use worker_loop::run as run_worker_loop;
