//! L5.G.3 — Glossary-service RPC reader trait.
//!
//! Calls the L5.F.2 `GET /v1/canon/{book_id}/seed_export` NDJSON
//! streaming endpoint shipped in cycle 25 (`contracts/api/
//! glossary-service/seed_export.yaml`). Production binds to the
//! Rust client extended in this cycle:
//! `glossary_client::Client::export_canon_for_seed`.
//!
//! ## Q-IDs honored
//!
//! - **Q-L5-4** — HTTP/JSON V1 only (NDJSON is JSON-per-line).
//! - **Q-L5-3** — `canon_layer` strings are `"L1_axiom"` or `"L2_seeded"`.
//! - **Q-L5A-1** — services/glossary-service/ NOT modified; this
//!   trait talks ONLY to the RPC contract.
//! - **Q-L1A-2** — canon SSOT lives in glossary DB; the seeder reads
//!   via RPC + writes to per-reality canon_projection.
//!
//! ## Cycle 25 binding (production)
//!
//! ```ignore
//! use glossary_client::{Client, ClientConfig, static_svid};
//!
//! struct GlossaryCanonExporter { client: Client }
//! impl CanonExporter for GlossaryCanonExporter {
//!     fn export(&self, book_id: Uuid, cursor: Option<String>)
//!         -> Result<SeedExportResult, SeederError>
//!     {
//!         let rt = tokio::runtime::Handle::current();
//!         let (entries, env) = rt.block_on(self.client.export_canon_for_seed(
//!             &book_id.to_string(),
//!             cursor.as_deref(),
//!         )).map_err(|e| SeederError::CanonRpc(e.to_string()))?;
//!         Ok(SeedExportResult {
//!             entries: entries.into_iter().map(canon_entry_from_wire).collect(),
//!             next_cursor: env.next_cursor,
//!             snapshot_at: env.snapshot_at,
//!         })
//!     }
//! }
//! ```
//!
//! The wire-to-domain mapping (`canon_entry_from_wire`) is left to the
//! production wiring layer (out of scope for foundation — keeps
//! `services/world-service/` test-friendly without a tokio dep).

use crate::reality_seeder::SeederError;
use uuid::Uuid;

/// One canon entry returned by the glossary L5.F.2 export RPC. Matches
/// the OpenAPI `CanonEntry` schema (cycle 25 seed_export.yaml).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CanonEntry {
    /// Canonical UUID — matches glossary DB `canon_entries.canon_entry_id`.
    pub canon_entry_id: Uuid,
    /// Owning book UUID.
    pub book_id: Uuid,
    /// Attribute path (e.g. `"world.climate"`, `"characters/alice/race"`).
    pub attribute_path: String,
    /// JSON bytes (the value is `any` on the wire; the seeder treats
    /// it as opaque pass-through to the per-reality projection write).
    pub value: Vec<u8>,
    /// Q-L5-3 enum: `"L1_axiom"` | `"L2_seeded"`.
    pub canon_layer: String,
    /// Lock level: `"hard" | "soft" | "archived" | "experimental"`.
    pub lock_level: String,
    /// RFC3339 timestamp from the glossary server.
    pub last_synced_at: String,
}

/// One drained page from [`CanonExporter::export`]. Mirrors the cycle-25
/// NDJSON envelope shape (`SeedExportEnvelope` in the glossary_client).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SeedExportResult {
    /// Canon entries decoded from one NDJSON page.
    pub entries: Vec<CanonEntry>,
    /// If `Some`, more pages remain; pass back as `cursor` on the next
    /// call. The L5.G orchestrator drains until `None`.
    pub next_cursor: Option<String>,
    /// Server snapshot timestamp (RFC3339). Carried on every page so
    /// checkpoints can record the snapshot at write time.
    pub snapshot_at: String,
}

/// L5.G.3 RPC trait — the seeder consumes this; production binds to
/// `glossary_client::Client::export_canon_for_seed`. Errors map to
/// [`SeederError::CanonRpc`] so the orchestrator routes them through
/// the unified mark-failed path.
pub trait CanonExporter {
    /// Drain one page of canon entries for `book_id`. The first call
    /// passes `cursor = None`; subsequent calls pass the prior page's
    /// `next_cursor` value until exhausted.
    fn export(
        &self,
        book_id: Uuid,
        cursor: Option<String>,
    ) -> Result<SeedExportResult, SeederError>;
}

#[cfg(test)]
mod tests {
    use super::*;

    struct FakeExporter {
        responses: std::cell::RefCell<Vec<SeedExportResult>>,
    }
    impl CanonExporter for FakeExporter {
        fn export(
            &self,
            _book_id: Uuid,
            _cursor: Option<String>,
        ) -> Result<SeedExportResult, SeederError> {
            let mut r = self.responses.borrow_mut();
            if r.is_empty() {
                return Err(SeederError::CanonRpc("no more pages".into()));
            }
            Ok(r.remove(0))
        }
    }

    #[test]
    fn fake_exporter_returns_pages_in_order() {
        let fixture = SeedExportResult {
            entries: vec![CanonEntry {
                canon_entry_id: Uuid::from_u128(0x1),
                book_id: Uuid::from_u128(0x2),
                attribute_path: "world.x".into(),
                value: b"\"v\"".to_vec(),
                canon_layer: "L1_axiom".into(),
                lock_level: "hard".into(),
                last_synced_at: "2026-05-29T12:00:00Z".into(),
            }],
            next_cursor: None,
            snapshot_at: "2026-05-29T12:00:00Z".into(),
        };
        let f = FakeExporter {
            responses: std::cell::RefCell::new(vec![fixture.clone()]),
        };
        let got = f.export(Uuid::from_u128(0x2), None).unwrap();
        assert_eq!(got.entries[0].canon_layer, "L1_axiom"); // Q-L5-3
        let next = f.export(Uuid::from_u128(0x2), None);
        assert!(matches!(next, Err(SeederError::CanonRpc(_))));
    }
}
