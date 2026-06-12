//! L5.G.9 — Integration test for the reality seeder.
//!
//! RAID cycle 26. End-to-end test of the seeder driving canon ingest
//! into the per-reality projection trait, with:
//!
//! 1. Multi-page canon export (cursor pagination via L5.F.2).
//! 2. Q-L5-2 translation gate (locale mismatch fires translator).
//! 3. Idempotent re-seed (already_seeded skip).
//! 4. Partial-fail → reality marked failed_seeding + audit row.
//!
//! ## Why a `tests/` integration test vs unit tests in mod.rs?
//!
//! The unit tests in `src/reality_seeder/mod.rs` cover the orchestrator
//! shape with deterministic fakes. This integration test exercises the
//! **public re-exports** from `world_service::*` — verifying that
//! external consumers (downstream cycles, meta-worker wiring) can
//! drive the seeder using only the documented public surface. The
//! test fails closed if the re-export set in `src/lib.rs` is
//! incomplete.

use std::cell::RefCell;
use std::collections::{HashMap, HashSet};

use uuid::Uuid;
// Pull the L5.G seeder surface in via the dedicated `SeederAuditEvent`
// re-export alias (avoids collision with the cycle-16 embedding_queue
// `AuditEvent` type, which world-service also re-exports).
use world_service::{
    BookMetadata, BookReader, CanonExporter, CanonProjectionIntent, CanonProjectionWriter,
    CheckpointStore, KnowledgeReader, LifecycleTransitioner, NpcProxy, RealitySeeder,
    RealityStatus, SeedCanonEntry, SeedCheckpoint, SeedExportResult, SeedRequest,
    SeederAuditEvent, SeederAuditSink, SeederDeps, SeederError, TranslationGateway,
};

// ─── Fixtures ───────────────────────────────────────────────────────────

struct FixtureBookReader {
    books: HashMap<Uuid, BookMetadata>,
}
impl BookReader for FixtureBookReader {
    fn get_book(&self, book_id: Uuid) -> Result<BookMetadata, SeederError> {
        self.books
            .get(&book_id)
            .cloned()
            .ok_or(SeederError::BookNotFound(book_id))
    }
}

struct PaginatedCanonExporter {
    pages: RefCell<Vec<SeedExportResult>>,
}
impl CanonExporter for PaginatedCanonExporter {
    fn export(
        &self,
        _book_id: Uuid,
        _cursor: Option<String>,
    ) -> Result<SeedExportResult, SeederError> {
        let mut p = self.pages.borrow_mut();
        if p.is_empty() {
            return Err(SeederError::CanonRpc("exhausted".into()));
        }
        Ok(p.remove(0))
    }
}

struct EmptyKnowledgeReader;
impl KnowledgeReader for EmptyKnowledgeReader {}

struct CountingTranslator {
    calls: RefCell<u64>,
}
impl TranslationGateway for CountingTranslator {
    fn translate(
        &mut self,
        from: &str,
        to: &str,
        value: Vec<u8>,
    ) -> Result<Vec<u8>, SeederError> {
        *self.calls.borrow_mut() += 1;
        let mut v = value;
        v.extend(format!("[{from}->{to}]").as_bytes());
        Ok(v)
    }
}

#[derive(Default)]
struct CapturingProjectionWriter {
    writes: RefCell<Vec<CanonProjectionIntent>>,
    seeded_by_reality: RefCell<HashMap<Uuid, HashSet<Uuid>>>,
    fail_at: RefCell<Option<usize>>,
}
impl CanonProjectionWriter for CapturingProjectionWriter {
    fn upsert_canon(&mut self, intent: CanonProjectionIntent) -> Result<(), SeederError> {
        if let Some(n) = *self.fail_at.borrow() {
            if self.writes.borrow().len() == n {
                return Err(SeederError::ProjectionWrite("integration-injected".into()));
            }
        }
        self.writes.borrow_mut().push(intent);
        Ok(())
    }
    fn already_seeded(&self, reality_id: Uuid) -> HashSet<Uuid> {
        self.seeded_by_reality
            .borrow()
            .get(&reality_id)
            .cloned()
            .unwrap_or_default()
    }
}

#[derive(Default)]
struct InMemCheckpoints {
    saved: RefCell<Vec<SeedCheckpoint>>,
    stored: RefCell<HashMap<(Uuid, Uuid), SeedCheckpoint>>,
}
impl CheckpointStore for InMemCheckpoints {
    fn save(&mut self, cp: SeedCheckpoint) -> Result<(), SeederError> {
        self.saved.borrow_mut().push(cp.clone());
        self.stored
            .borrow_mut()
            .insert((cp.reality_id, cp.book_id), cp);
        Ok(())
    }
    fn load(
        &self,
        reality_id: Uuid,
        book_id: Uuid,
    ) -> Result<Option<SeedCheckpoint>, SeederError> {
        Ok(self.stored.borrow().get(&(reality_id, book_id)).cloned())
    }
}

#[derive(Default)]
struct RecordingLifecycle {
    calls: RefCell<Vec<(Uuid, RealityStatus, RealityStatus)>>,
}
impl LifecycleTransitioner for RecordingLifecycle {
    fn transition(
        &mut self,
        reality_id: Uuid,
        from: RealityStatus,
        to: RealityStatus,
        _reason: &str,
    ) -> Result<(), SeederError> {
        self.calls.borrow_mut().push((reality_id, from, to));
        Ok(())
    }
}

#[derive(Default)]
struct CollectingAudit {
    events: RefCell<Vec<SeederAuditEvent>>,
}
impl SeederAuditSink for CollectingAudit {
    fn record(&mut self, event: SeederAuditEvent) -> Result<(), SeederError> {
        self.events.borrow_mut().push(event);
        Ok(())
    }
}

fn rid() -> Uuid {
    Uuid::from_u128(0x4c5f_0026_0001)
}
fn bid() -> Uuid {
    Uuid::from_u128(0x4c5f_0026_0002)
}

fn canon_entry(n: u128, path: &str) -> SeedCanonEntry {
    SeedCanonEntry {
        canon_entry_id: Uuid::from_u128(n),
        book_id: bid(),
        attribute_path: path.into(),
        value: format!("\"value-{n}\"").into_bytes(),
        canon_layer: if n % 2 == 0 { "L1_axiom".into() } else { "L2_seeded".into() },
        lock_level: "soft".into(),
        last_synced_at: "2026-05-29T12:00:00Z".into(),
    }
}

fn make_seeder(
    pages: Vec<SeedExportResult>,
    book_locale: &str,
) -> RealitySeeder<
    FixtureBookReader,
    PaginatedCanonExporter,
    EmptyKnowledgeReader,
    CountingTranslator,
    CapturingProjectionWriter,
    InMemCheckpoints,
    RecordingLifecycle,
    CollectingAudit,
> {
    let mut books = HashMap::new();
    books.insert(
        bid(),
        BookMetadata {
            book_id: bid(),
            source_locale: book_locale.into(),
            title: "Integration Test Book".into(),
        },
    );
    let deps = SeederDeps {
        book_reader: FixtureBookReader { books },
        canon_exporter: PaginatedCanonExporter {
            pages: RefCell::new(pages),
        },
        knowledge_reader: EmptyKnowledgeReader,
        translation_gateway: CountingTranslator {
            calls: RefCell::new(0),
        },
        projection_writer: CapturingProjectionWriter::default(),
        checkpoint_store: InMemCheckpoints::default(),
        lifecycle: RecordingLifecycle::default(),
        audit: CollectingAudit::default(),
    };
    RealitySeeder::new(deps)
}

// ─── Tests ──────────────────────────────────────────────────────────────

#[test]
fn integration_multi_page_seed_populates_projection_and_transitions_active() {
    // Page 1: 3 entries with next_cursor; Page 2: 2 entries terminal.
    let pages = vec![
        SeedExportResult {
            entries: vec![
                canon_entry(0xA1, "world.climate"),
                canon_entry(0xA2, "world.gravity"),
                canon_entry(0xA3, "rule.combat"),
            ],
            next_cursor: Some("page-2".into()),
            snapshot_at: "2026-05-29T12:00:00Z".into(),
        },
        SeedExportResult {
            entries: vec![
                canon_entry(0xA4, "lore.creation"),
                canon_entry(0xA5, "faction.guild_x"),
            ],
            next_cursor: None,
            snapshot_at: "2026-05-29T12:00:00Z".into(),
        },
    ];
    let mut seeder = make_seeder(pages, "en-US");
    let report = seeder
        .run(SeedRequest {
            reality_id: rid(),
            book_id: bid(),
            reality_locale: "en-US".into(),
            book_source_locale: "en-US".into(),
            reason: "integration".into(),
        })
        .expect("ok");
    assert_eq!(report.canon_entries_written, 5);
    assert_eq!(report.canon_entries_translated, 0); // Q-L5-2: no mismatch
    // Lifecycle: seeding → active.
    let trs = seeder.deps.lifecycle.calls.borrow();
    assert_eq!(trs.len(), 1);
    assert_eq!(trs[0].2, RealityStatus::Active);
}

#[test]
fn integration_q_l5_2_translation_invoked_on_locale_mismatch() {
    let pages = vec![SeedExportResult {
        entries: vec![
            canon_entry(0xB1, "world.climate"),
            canon_entry(0xB2, "lore.creation"),
        ],
        next_cursor: None,
        snapshot_at: "2026-05-29T12:00:00Z".into(),
    }];
    let mut seeder = make_seeder(pages, "en-US");
    seeder
        .run(SeedRequest {
            reality_id: rid(),
            book_id: bid(),
            reality_locale: "vi-VN".into(), // mismatch
            book_source_locale: "en-US".into(),
            reason: "integration-translate".into(),
        })
        .expect("ok");
    // Translation gateway called exactly once per entry.
    assert_eq!(*seeder.deps.translation_gateway.calls.borrow(), 2);
    // Each upserted value carries the translator's marker.
    let writes = seeder.deps.projection_writer.writes.borrow();
    assert_eq!(writes.len(), 2);
    for w in writes.iter() {
        assert!(w
            .value
            .windows(b"[en-US->vi-VN]".len())
            .any(|chunk| chunk == b"[en-US->vi-VN]"));
    }
}

#[test]
fn integration_idempotent_reseed_writes_zero_new_rows() {
    // Pre-populate seeded set so all 3 entries are "already there".
    let pages = vec![SeedExportResult {
        entries: vec![
            canon_entry(0xC1, "world.climate"),
            canon_entry(0xC2, "world.gravity"),
            canon_entry(0xC3, "rule.combat"),
        ],
        next_cursor: None,
        snapshot_at: "2026-05-29T12:00:00Z".into(),
    }];
    let mut seeder = make_seeder(pages, "en-US");
    let mut prior = HashSet::new();
    prior.insert(Uuid::from_u128(0xC1));
    prior.insert(Uuid::from_u128(0xC2));
    prior.insert(Uuid::from_u128(0xC3));
    seeder
        .deps
        .projection_writer
        .seeded_by_reality
        .borrow_mut()
        .insert(rid(), prior);
    let report = seeder
        .run(SeedRequest {
            reality_id: rid(),
            book_id: bid(),
            reality_locale: "en-US".into(),
            book_source_locale: "en-US".into(),
            reason: "integration-reseed".into(),
        })
        .expect("ok");
    assert!(report.was_no_op);
    assert_eq!(seeder.deps.projection_writer.writes.borrow().len(), 0);
    // Lifecycle still transitions to active (idempotent re-runs are
    // legitimate completion signals).
    let trs = seeder.deps.lifecycle.calls.borrow();
    assert_eq!(trs.len(), 1);
    assert_eq!(trs[0].2, RealityStatus::Active);
}

#[test]
fn integration_partial_fail_marks_failed_seeding_and_audits() {
    // 4 entries; fail on the 3rd write.
    let pages = vec![SeedExportResult {
        entries: vec![
            canon_entry(0xD1, "world.climate"),
            canon_entry(0xD2, "world.gravity"),
            canon_entry(0xD3, "rule.combat"),
            canon_entry(0xD4, "lore.creation"),
        ],
        next_cursor: None,
        snapshot_at: "2026-05-29T12:00:00Z".into(),
    }];
    let mut seeder = make_seeder(pages, "en-US");
    *seeder.deps.projection_writer.fail_at.borrow_mut() = Some(2);
    let err = seeder
        .run(SeedRequest {
            reality_id: rid(),
            book_id: bid(),
            reality_locale: "en-US".into(),
            book_source_locale: "en-US".into(),
            reason: "integration-fail".into(),
        })
        .expect_err("fatal");
    assert!(matches!(err, SeederError::ProjectionWrite(_)));
    // Lifecycle: seeding → failed_seeding.
    let trs = seeder.deps.lifecycle.calls.borrow();
    assert_eq!(trs.len(), 1);
    assert_eq!(trs[0].2, RealityStatus::FailedSeeding);
    // Audit captured the failure.
    let events = seeder.deps.audit.events.borrow();
    assert!(events.iter().any(|e| e.is_failure()));
    // 2 writes succeeded before the failure (0xD1, 0xD2).
    assert_eq!(seeder.deps.projection_writer.writes.borrow().len(), 2);
}

// Suppress dead-code warning on the NpcProxy import — it's part of the
// public re-export surface this integration test asserts is intact.
#[test]
fn integration_npc_proxy_type_is_exported() {
    let _np = NpcProxy {
        proxy_id: Uuid::nil(),
        glossary_entity_id: None,
        display_name: "x".into(),
        role_tags: vec![],
    };
}
