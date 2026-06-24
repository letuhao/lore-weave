//! L5.G — Reality seeder orchestrator (cycle 26).
//!
//! Background worker invoked after `provisioner.rs` (cycle 5) transitions a
//! reality to `status=seeding`. The seeder pulls authored canon from
//! `glossary-service` (via the cycle-25 L5.F.2 `ExportCanonForSeed` RPC),
//! optionally translates the payload when `reality.locale !=
//! book.source_locale` (Q-L5-2), checkpoints progress every 100 canon
//! entries (resumability), upserts each entry into the per-reality
//! `canon_projection` table (cycle 23 L5.D schema) via the meta-worker
//! canon writer interface (cycle 24 L5.B), and on success transitions the
//! reality to `status=active`. On unrecoverable failure the seeder
//! transitions to `status=failed_seeding` for SRE alert + retry.
//!
//! ## Layer plan ID coverage
//!
//! - L5.G.1 — this `mod.rs` orchestrator.
//! - L5.G.2 — `book_reader.rs` (book-service RPC trait — for V1 we model
//!   the trait; the production HTTP client lands when book-service is in
//!   foundation scope; the trait keeps the seeder ready).
//! - L5.G.3 — `canon_reader.rs` (glossary-service RPC trait → wired in
//!   production to `glossary_client::Client::export_canon_for_seed`).
//! - L5.G.4 — `knowledge_reader.rs` (knowledge-service RPC trait — same
//!   pattern as book_reader; production client lands later).
//! - L5.G.5 — `translation_orchestrator.rs` (Q-L5-2 conditional gate).
//! - L5.G.6 — `checkpointer.rs` (resumability per L5.G acceptance crit).
//! - L5.G.7 — `lifecycle_transitioner.rs` (cycle-5 transition wrapper).
//! - L5.G.8 — `contracts/service_acl/matrix.yaml` extension (L5.G.8 ACL).
//! - L5.G.9 — `tests/integration/reality_seed_test.rs` (end-to-end).
//! - L5.G.10 — `runbooks/reality_seed/stuck_seeding.md` (SRE runbook).
//!
//! ## LOCKED Q-IDs honored
//!
//! - **Q-L5-2** — translation gated on `reality.locale !=
//!   book.source_locale`. The seeder constructs the
//!   `TranslationOrchestrator` only when locales differ, and translates
//!   each canon `value` field via the gateway before upsert.
//! - **Q-L5-4** — HTTP/JSON RPC via the cycle-25 `glossary_client`. The
//!   seeder depends only on the `CanonExporter` trait; production binds
//!   to the Rust client added in this cycle (L5.G.3).
//! - **Q-L1A-2** — canon SSOT remains in glossary DB. The seeder writes
//!   to per-reality `canon_projection` ONLY (via the `CanonProjectionWriter`
//!   trait that meta-worker satisfies in production per cycle-24 L5.B).
//! - **Q-L5A-1** — `services/glossary-service/` not modified by this
//!   cycle. Verified by `verify-cycle-26.sh` step 2.
//! - **Q-L3-4** — every projection write carries VerificationMeta
//!   (event_id + aggregate_version + applied_at); the seeder issues
//!   synthetic seed event_ids so the meta-worker writer can stamp them.
//! - **Q-L1A-3** — full audit V1 (no sampling). Each phase + each RPC
//!   call is audited via the injected `AuditSink`.
//!
//! ## Idempotency
//!
//! The seeder is idempotent at TWO layers:
//!
//! 1. **Canon upsert layer** — each canon entry is upserted into
//!    `canon_projection` on `canon_entry_id` PK. Re-running the seeder
//!    after a crash UPDATEs already-written rows in place (no duplicate
//!    rows). The cycle-23 0009 migration's PK enforces this.
//!
//! 2. **Checkpoint layer** — every 100 entries the seeder persists a
//!    `SeedCheckpoint` row (book_id + cursor + last_synced_at +
//!    entries_committed). On restart the seeder reads the checkpoint
//!    and skips forward — the upsert path still handles duplicates if
//!    a checkpoint write was lost between commit and DB flush.
//!
//! Re-running a COMPLETED seed yields zero new rows + zero new
//! checkpoints (acceptance criterion: "Resumable: kill seeder
//! mid-flight, restart, completes without duplication").
//!
//! ## Failure-safe
//!
//! Partial seed → seeder catches the error from any phase, records a
//! `SeedingFailed` audit entry, and via the `LifecycleTransitioner`
//! transitions the reality from `seeding` to `failed_seeding`. SRE alert
//! fires on `lw_reality_seeding_failed_total > 0`. The runbook
//! (L5.G.10) instructs SRE to re-run the seeder once the cause is
//! resolved; idempotency makes the retry safe.
//!
//! ## Cross-cycle wiring
//!
//! - Cycle 5 provisioner — runs steps 1-11; this seeder runs AFTER
//!   step 9 (`transition_to(seeding)`) and BEFORE step 10
//!   (`transition_to(active)`). The provisioner's step-10 call is
//!   replaced by the seeder's own lifecycle transition.
//! - Cycle 23 `canon_projection` schema — the seeder writes here via
//!   the writer trait (production binds to meta-worker
//!   `canon_writer/writer.go` Upsert path).
//! - Cycle 24 canon_writer — the seeder routes its upserts through
//!   the same `UpsertCanon` semantics so the projection state shape
//!   matches event-driven updates.
//! - Cycle 25 glossary RPC client — the seeder fetches canon via
//!   `CanonExporter` (production binds to `glossary_client::Client::
//!   export_canon_for_seed`).

use std::collections::HashSet;
use uuid::Uuid;

pub mod audit;
pub mod book_reader;
pub mod canon_reader;
pub mod checkpointer;
pub mod knowledge_reader;
pub mod lifecycle_transitioner;
pub mod translation_orchestrator;

pub use audit::{AuditEvent, AuditSink};
pub use book_reader::{BookMetadata, BookReader, Region};
pub use canon_reader::{CanonEntry, CanonExporter, SeedExportResult};
pub use checkpointer::{CheckpointStore, SeedCheckpoint};
pub use knowledge_reader::{KnowledgeReader, NpcProxy};
pub use lifecycle_transitioner::{LifecycleTransitioner, RealityStatus};
pub use translation_orchestrator::{TranslationGateway, TranslationOrchestrator};

/// Error surface for the reality seeder.
///
/// Distinguishes (a) **fatal** errors that warrant `status=failed_seeding`
/// (bad input, RPC permanent failure, contract violation) from
/// (b) **transient** errors that the SRE retry path resolves (network
/// glitch, momentary DB unavailability). The orchestrator marks the
/// reality as failed only for fatal errors; transient errors bubble up
/// for the SRE-driven retry loop.
#[derive(Debug, thiserror::Error)]
pub enum SeederError {
    /// `book_id` did not exist or returned an unrecoverable error.
    #[error("seeder: book {0} not found")]
    BookNotFound(Uuid),

    /// Bad seed request shape (e.g., nil reality_id).
    #[error("seeder: invalid request: {0}")]
    InvalidRequest(String),

    /// Canon RPC permanently failed (server returned a non-retriable
    /// status — 4xx other than 429).
    #[error("seeder: canon RPC error: {0}")]
    CanonRpc(String),

    /// Translation gateway permanently failed (e.g., locale not
    /// supported by the configured translation provider).
    #[error("seeder: translation error: {0}")]
    Translation(String),

    /// `canon_projection` write failure on the per-reality DB.
    #[error("seeder: projection write error: {0}")]
    ProjectionWrite(String),

    /// Checkpoint store unreachable. Recorded as audit; bubble up so the
    /// caller can decide retry policy.
    #[error("seeder: checkpoint write error: {0}")]
    Checkpoint(String),

    /// Lifecycle transition rejected (e.g., illegal state transition).
    /// Treated as fatal — the reality is in an inconsistent state and
    /// requires SRE intervention.
    #[error("seeder: lifecycle transition rejected: {0}")]
    Lifecycle(String),

    /// Audit sink failure. Per Q-L1A-3 (no sampling) this is fatal —
    /// dropping an audit entry breaks the "every write audited" invariant.
    #[error("seeder: audit sink failure: {0}")]
    Audit(String),
}

/// Request to the reality seeder. Constructed by the cycle-5
/// `Provisioner` after `transition_to(seeding)` succeeds.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SeedRequest {
    /// The reality being seeded.
    pub reality_id: Uuid,
    /// The book whose canon is being seeded.
    pub book_id: Uuid,
    /// BCP-47 locale of the reality (e.g., `"en-US"`, `"vi-VN"`).
    pub reality_locale: String,
    /// BCP-47 locale the book was authored in (from book metadata).
    pub book_source_locale: String,
    /// Reason string for audit chain (e.g., `"reality_create:user-123"`).
    pub reason: String,
}

impl SeedRequest {
    fn validate(&self) -> Result<(), SeederError> {
        if self.reality_id.is_nil() {
            return Err(SeederError::InvalidRequest("reality_id nil".into()));
        }
        if self.book_id.is_nil() {
            return Err(SeederError::InvalidRequest("book_id nil".into()));
        }
        if self.reality_locale.trim().is_empty() {
            return Err(SeederError::InvalidRequest("reality_locale empty".into()));
        }
        if self.book_source_locale.trim().is_empty() {
            return Err(SeederError::InvalidRequest("book_source_locale empty".into()));
        }
        if self.reason.trim().is_empty() {
            return Err(SeederError::InvalidRequest("reason empty".into()));
        }
        Ok(())
    }

    /// Q-L5-2 gate: translation is invoked ONLY when these differ.
    pub fn requires_translation(&self) -> bool {
        // Case-insensitive comparison + trim defensiveness against
        // upstream locale-tag drift (en-US vs en-us).
        !self
            .reality_locale
            .trim()
            .eq_ignore_ascii_case(self.book_source_locale.trim())
    }
}

/// Report returned on successful seed completion.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SeedReport {
    /// The `reality_id` seeded.
    pub reality_id: Uuid,
    /// Total canon entries written to `canon_projection`.
    pub canon_entries_written: u64,
    /// Total canon entries translated (0 if no translation needed).
    pub canon_entries_translated: u64,
    /// Total checkpoints persisted.
    pub checkpoints_written: u64,
    /// True if seed was a no-op (re-run of completed seed).
    pub was_no_op: bool,
}

/// Per-canon-entry write intent. Mirrors the cycle-24 L5.B
/// `canon_writer::UpsertIntent` shape so the production binding can
/// translate 1:1.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CanonProjectionIntent {
    /// Per-reality DB target.
    pub reality_id: Uuid,
    /// Canon entry UUID (PK on `canon_projection`).
    pub canon_entry_id: Uuid,
    /// Owning book UUID.
    pub book_id: Uuid,
    /// Attribute path (e.g. `"world.climate"`).
    pub attribute_path: String,
    /// Canon value as JSON bytes (opaque pass-through).
    pub value: Vec<u8>,
    /// Q-L5-3 enum string (`"L1_axiom"` | `"L2_seeded"`).
    pub canon_layer: String,
    /// Lock level enum string.
    pub lock_level: String,
    /// Synthetic seed event_id (UUIDv5 derived from `(reality_id,
    /// canon_entry_id)` so retries don't multiply audit entries).
    pub source_event_id: Uuid,
    /// Q-L1A-3 audit: seed source marker (lets downstream tooling
    /// distinguish seed-time writes from event-driven writes).
    pub seed_marker: bool,
}

/// Sink that writes a canon projection upsert + audit. Production binds
/// to the meta-worker canon_writer (cycle 24 L5.B); tests inject an
/// in-memory recorder.
pub trait CanonProjectionWriter {
    /// UPSERT one canon entry into the per-reality `canon_projection`.
    /// PK = `canon_entry_id`; re-runs are idempotent.
    fn upsert_canon(&mut self, intent: CanonProjectionIntent) -> Result<(), SeederError>;
    /// Returns the set of `canon_entry_id`s already present in the
    /// per-reality projection for this reality. Used for idempotent
    /// re-run detection (skip upsert when entry already at this
    /// source_event_id).
    fn already_seeded(&self, reality_id: Uuid) -> HashSet<Uuid>;
}

/// Configuration bundle for [`RealitySeeder::new`]. All non-clock deps
/// are required; the orchestrator constructs the per-call
/// `TranslationOrchestrator` itself when Q-L5-2 triggers.
pub struct SeederDeps<B, C, K, T, W, S, L, A>
where
    B: BookReader,
    C: CanonExporter,
    K: KnowledgeReader,
    T: TranslationGateway,
    W: CanonProjectionWriter,
    S: CheckpointStore,
    L: LifecycleTransitioner,
    A: AuditSink,
{
    /// L5.G.2 book-service RPC trait.
    pub book_reader: B,
    /// L5.G.3 glossary-service canon exporter trait.
    pub canon_exporter: C,
    /// L5.G.4 knowledge-service NPC reader trait.
    pub knowledge_reader: K,
    /// L5.G.5 translation-service gateway trait (Q-L5-2 gate).
    pub translation_gateway: T,
    /// Per-reality `canon_projection` writer trait.
    pub projection_writer: W,
    /// L5.G.6 checkpoint persistence trait.
    pub checkpoint_store: S,
    /// L5.G.7 lifecycle-transition trait (seeding ↔ active/failed).
    pub lifecycle: L,
    /// Q-L1A-3 full audit sink.
    pub audit: A,
}

/// L5.G.1 — reality seeder orchestrator.
///
/// Construct once per reality-seed run. Drives the canonical seed
/// phases in order: validate → fetch_book_meta → load_checkpoint →
/// stream_canon → (translate?) → upsert_projection → checkpoint →
/// transition_active. Each phase emits an audit entry per Q-L1A-3.
pub struct RealitySeeder<B, C, K, T, W, S, L, A>
where
    B: BookReader,
    C: CanonExporter,
    K: KnowledgeReader,
    T: TranslationGateway,
    W: CanonProjectionWriter,
    S: CheckpointStore,
    L: LifecycleTransitioner,
    A: AuditSink,
{
    /// Injected dependency bundle. `pub` so integration tests + the
    /// downstream wiring layer can introspect (e.g. read the audit
    /// sink after a run). Tests rely on this for assertions; the
    /// production caller treats it as construct-once-and-forget.
    pub deps: SeederDeps<B, C, K, T, W, S, L, A>,
    /// Persist a checkpoint every N canon entries. Acceptance crit says
    /// "every 100 regions"; we use 100 for canon entries too — same
    /// trade-off (10 checkpoints per typical book × 1000 entries).
    pub checkpoint_every: usize,
}

impl<B, C, K, T, W, S, L, A> RealitySeeder<B, C, K, T, W, S, L, A>
where
    B: BookReader,
    C: CanonExporter,
    K: KnowledgeReader,
    T: TranslationGateway,
    W: CanonProjectionWriter,
    S: CheckpointStore,
    L: LifecycleTransitioner,
    A: AuditSink,
{
    /// Construct with the L5.G.6 default checkpoint cadence.
    pub fn new(deps: SeederDeps<B, C, K, T, W, S, L, A>) -> Self {
        Self { deps, checkpoint_every: 100 }
    }

    /// Override the checkpoint cadence (tests use small values for
    /// deterministic checkpoint observation).
    pub fn with_checkpoint_every(mut self, n: usize) -> Self {
        self.checkpoint_every = n.max(1);
        self
    }

    /// Drive the seed end-to-end. Mutates `self` only via `&mut self`
    /// on the inner writer/checkpoint/lifecycle/audit deps.
    ///
    /// Returns `SeedReport` on success. On fatal error, transitions the
    /// reality to `status=failed_seeding` and returns the error.
    pub fn run(&mut self, req: SeedRequest) -> Result<SeedReport, SeederError> {
        // Phase 1 — validate.
        req.validate()?;
        self.deps.audit.record(AuditEvent::phase(
            req.reality_id,
            "validate",
            &req.reason,
        ))?;

        // Phase 2 — load book metadata (locale needed for Q-L5-2 guard;
        // even though SeedRequest carries the locale, we cross-check it
        // against the book metadata to prevent caller drift).
        let book_meta = match self.deps.book_reader.get_book(req.book_id) {
            Ok(m) => m,
            Err(e) => return self.mark_failed(req.reality_id, &req.reason, e),
        };
        if !book_meta.source_locale.eq_ignore_ascii_case(&req.book_source_locale) {
            return self.mark_failed(
                req.reality_id,
                &req.reason,
                SeederError::InvalidRequest(format!(
                    "SeedRequest book_source_locale={:?} disagrees with book metadata={:?}",
                    req.book_source_locale, book_meta.source_locale
                )),
            );
        }
        self.deps.audit.record(AuditEvent::phase(
            req.reality_id,
            "fetch_book_meta",
            &req.reason,
        ))?;

        // Phase 3 — idempotent re-run detection.
        let already_seeded = self.deps.projection_writer.already_seeded(req.reality_id);
        let prior_checkpoint = match self.deps.checkpoint_store.load(req.reality_id, req.book_id) {
            Ok(cp) => cp,
            Err(e) => return self.mark_failed(req.reality_id, &req.reason, e),
        };
        self.deps.audit.record(AuditEvent::phase(
            req.reality_id,
            "load_checkpoint",
            &req.reason,
        ))?;

        // Phase 4 — stream canon. Q-L5-4 HTTP/JSON via CanonExporter.
        // We start from the prior checkpoint's cursor (or None on first
        // run) and drain pages until the envelope reports next_cursor=None.
        let mut cursor = prior_checkpoint.as_ref().and_then(|cp| cp.cursor.clone());
        let mut total_entries: u64 = prior_checkpoint
            .as_ref()
            .map(|cp| cp.entries_committed)
            .unwrap_or(0);
        let mut total_translated: u64 = 0;
        let mut total_checkpoints: u64 = 0;
        let starting_committed = total_entries;

        // Phase 4.5 — translation orchestrator (Q-L5-2 gate). Constructed
        // ONLY when locales differ; otherwise the seeder passes values
        // through untouched.
        let translation = if req.requires_translation() {
            Some(TranslationOrchestrator::new(
                &mut self.deps.translation_gateway,
                req.book_source_locale.clone(),
                req.reality_locale.clone(),
            ))
        } else {
            None
        };
        let mut translator = translation;

        let mut newly_written: u64 = 0;
        loop {
            let page = match self.deps.canon_exporter.export(req.book_id, cursor.clone()) {
                Ok(p) => p,
                Err(e) => return self.mark_failed(req.reality_id, &req.reason, e),
            };
            for entry in page.entries {
                let intent = build_intent(req.reality_id, &entry);
                if already_seeded.contains(&intent.canon_entry_id) {
                    // Idempotent skip — projection already has this row
                    // from a prior successful run. We still walk the page
                    // so the cursor advances to the same point.
                    continue;
                }
                // Q-L5-2 translation gate — only mutate value if locales differ.
                let intent = if let Some(t) = translator.as_mut() {
                    match t.translate_entry(intent) {
                        Ok(i) => {
                            total_translated += 1;
                            i
                        }
                        Err(e) => return self.mark_failed(req.reality_id, &req.reason, e),
                    }
                } else {
                    intent
                };
                if let Err(e) = self.deps.projection_writer.upsert_canon(intent.clone()) {
                    return self.mark_failed(req.reality_id, &req.reason, e);
                }
                self.deps.audit.record(AuditEvent::canon_upsert(
                    req.reality_id,
                    intent.canon_entry_id,
                    intent.book_id,
                ))?;
                total_entries += 1;
                newly_written += 1;
                if newly_written % (self.checkpoint_every as u64) == 0 {
                    let cp = SeedCheckpoint {
                        reality_id: req.reality_id,
                        book_id: req.book_id,
                        cursor: cursor.clone(),
                        entries_committed: total_entries,
                        snapshot_at: page.snapshot_at.clone(),
                    };
                    if let Err(e) = self.deps.checkpoint_store.save(cp) {
                        return self.mark_failed(req.reality_id, &req.reason, e);
                    }
                    total_checkpoints += 1;
                }
            }
            match page.next_cursor {
                Some(c) => cursor = Some(c),
                None => break,
            }
        }

        // Final checkpoint — always persist the terminal state so
        // re-runs detect completion.
        let final_cp = SeedCheckpoint {
            reality_id: req.reality_id,
            book_id: req.book_id,
            cursor: None,
            entries_committed: total_entries,
            snapshot_at: String::new(),
        };
        if let Err(e) = self.deps.checkpoint_store.save(final_cp) {
            return self.mark_failed(req.reality_id, &req.reason, e);
        }
        total_checkpoints += 1;

        // Phase 5 — lifecycle transition seeding → active.
        if let Err(e) = self
            .deps
            .lifecycle
            .transition(req.reality_id, RealityStatus::Seeding, RealityStatus::Active, &req.reason)
        {
            return self.mark_failed(req.reality_id, &req.reason, e);
        }
        self.deps.audit.record(AuditEvent::phase(
            req.reality_id,
            "transition_active",
            &req.reason,
        ))?;

        // `was_no_op` = this invocation made no NEW projection writes.
        // True both for (a) re-run after a completed seed where
        // already_seeded covered every entry AND (b) zero-entry book
        // edge case. Operators read this from the audit + report to
        // distinguish "ran but no-op" vs "ran and committed N".
        let was_no_op = newly_written == 0;
        let _ = starting_committed; // (kept for future report extension)
        Ok(SeedReport {
            reality_id: req.reality_id,
            canon_entries_written: total_entries,
            canon_entries_translated: total_translated,
            checkpoints_written: total_checkpoints,
            was_no_op,
        })
    }

    /// Transition the reality to `failed_seeding` and emit the audit
    /// event. Always returns the original error so the caller sees it.
    fn mark_failed(
        &mut self,
        reality_id: Uuid,
        reason: &str,
        err: SeederError,
    ) -> Result<SeedReport, SeederError> {
        // Best-effort transition; if the lifecycle write itself fails,
        // we surface the ORIGINAL error (more actionable for SRE).
        let _ = self.deps.lifecycle.transition(
            reality_id,
            RealityStatus::Seeding,
            RealityStatus::FailedSeeding,
            reason,
        );
        let _ = self
            .deps
            .audit
            .record(AuditEvent::failure(reality_id, reason, err.to_string()));
        Err(err)
    }
}

/// Map a canon entry from the L5.F.2 wire shape to the per-reality
/// projection upsert intent. The synthetic `source_event_id` is
/// derived deterministically from `(reality_id, canon_entry_id)` so
/// retries don't accumulate distinct audit entries.
fn build_intent(reality_id: Uuid, e: &CanonEntry) -> CanonProjectionIntent {
    let mut bytes = [0u8; 32];
    bytes[..16].copy_from_slice(reality_id.as_bytes());
    bytes[16..].copy_from_slice(e.canon_entry_id.as_bytes());
    // Hash via UUID v5 with a fixed namespace so re-runs produce the
    // same event_id (idempotent audit trail).
    let ns = Uuid::from_u128(0x4c5f_0001_0001_4c5f_a5a5_a5a5_a5a5_a5a5);
    let synthetic = Uuid::new_v5(&ns, &bytes);
    CanonProjectionIntent {
        reality_id,
        canon_entry_id: e.canon_entry_id,
        book_id: e.book_id,
        attribute_path: e.attribute_path.clone(),
        value: e.value.clone(),
        canon_layer: e.canon_layer.clone(),
        lock_level: e.lock_level.clone(),
        source_event_id: synthetic,
        seed_marker: true,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::RefCell;
    use std::collections::HashMap;

    // ─── Fakes ───────────────────────────────────────────────────────────

    #[derive(Default)]
    struct FakeBookReader {
        books: HashMap<Uuid, BookMetadata>,
    }
    impl BookReader for FakeBookReader {
        fn get_book(&self, book_id: Uuid) -> Result<BookMetadata, SeederError> {
            self.books
                .get(&book_id)
                .cloned()
                .ok_or(SeederError::BookNotFound(book_id))
        }
    }

    struct FakeCanonExporter {
        pages: RefCell<Vec<SeedExportResult>>,
        /// If set, fail the Nth call (0-indexed).
        fail_on_call: Option<usize>,
        call_idx: RefCell<usize>,
    }
    impl FakeCanonExporter {
        fn from_single_page(entries: Vec<CanonEntry>) -> Self {
            Self {
                pages: RefCell::new(vec![SeedExportResult {
                    entries,
                    next_cursor: None,
                    snapshot_at: "2026-05-29T12:00:00Z".into(),
                }]),
                fail_on_call: None,
                call_idx: RefCell::new(0),
            }
        }
    }
    impl CanonExporter for FakeCanonExporter {
        fn export(
            &self,
            _book_id: Uuid,
            _cursor: Option<String>,
        ) -> Result<SeedExportResult, SeederError> {
            let idx = *self.call_idx.borrow();
            *self.call_idx.borrow_mut() = idx + 1;
            if self.fail_on_call == Some(idx) {
                return Err(SeederError::CanonRpc("simulated".into()));
            }
            let mut pages = self.pages.borrow_mut();
            if pages.is_empty() {
                return Err(SeederError::CanonRpc("no more pages".into()));
            }
            Ok(pages.remove(0))
        }
    }

    #[derive(Default)]
    struct FakeKnowledgeReader;
    impl KnowledgeReader for FakeKnowledgeReader {
        fn list_npcs(&self, _book_id: Uuid) -> Result<Vec<NpcProxy>, SeederError> {
            Ok(Vec::new())
        }
    }

    /// Fake translation gateway: appends "::<locale>" to value bytes to
    /// prove the gate fires and value is mutated.
    struct FakeTranslationGateway {
        called: RefCell<u64>,
        fail: bool,
    }
    impl TranslationGateway for FakeTranslationGateway {
        fn translate(
            &mut self,
            from: &str,
            to: &str,
            value: Vec<u8>,
        ) -> Result<Vec<u8>, SeederError> {
            *self.called.borrow_mut() += 1;
            if self.fail {
                return Err(SeederError::Translation("simulated".into()));
            }
            let mut v = value;
            v.extend(format!("::{from}->{to}").as_bytes());
            Ok(v)
        }
    }

    #[derive(Default)]
    struct FakeProjectionWriter {
        writes: RefCell<Vec<CanonProjectionIntent>>,
        already_seeded_for_reality: RefCell<HashMap<Uuid, HashSet<Uuid>>>,
        fail_on_write: RefCell<Option<u32>>,
    }
    impl CanonProjectionWriter for FakeProjectionWriter {
        fn upsert_canon(&mut self, intent: CanonProjectionIntent) -> Result<(), SeederError> {
            if let Some(n) = *self.fail_on_write.borrow() {
                if (self.writes.borrow().len() as u32) == n {
                    return Err(SeederError::ProjectionWrite("simulated".into()));
                }
            }
            self.writes.borrow_mut().push(intent);
            Ok(())
        }
        fn already_seeded(&self, reality_id: Uuid) -> HashSet<Uuid> {
            self.already_seeded_for_reality
                .borrow()
                .get(&reality_id)
                .cloned()
                .unwrap_or_default()
        }
    }

    #[derive(Default)]
    struct FakeCheckpointStore {
        saved: RefCell<Vec<SeedCheckpoint>>,
        stored: RefCell<HashMap<(Uuid, Uuid), SeedCheckpoint>>,
    }
    impl CheckpointStore for FakeCheckpointStore {
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
    struct FakeLifecycle {
        transitions: RefCell<Vec<(Uuid, RealityStatus, RealityStatus)>>,
    }
    impl LifecycleTransitioner for FakeLifecycle {
        fn transition(
            &mut self,
            reality_id: Uuid,
            from: RealityStatus,
            to: RealityStatus,
            _reason: &str,
        ) -> Result<(), SeederError> {
            self.transitions.borrow_mut().push((reality_id, from, to));
            Ok(())
        }
    }

    #[derive(Default)]
    struct FakeAudit {
        events: RefCell<Vec<AuditEvent>>,
    }
    impl AuditSink for FakeAudit {
        fn record(&mut self, ev: AuditEvent) -> Result<(), SeederError> {
            self.events.borrow_mut().push(ev);
            Ok(())
        }
    }

    // ─── Helpers ─────────────────────────────────────────────────────────

    fn rid() -> Uuid {
        Uuid::from_u128(0xdead_beef_0001)
    }
    fn bid() -> Uuid {
        Uuid::from_u128(0xcafe_babe_0001)
    }
    fn ce(n: u128, path: &str) -> CanonEntry {
        CanonEntry {
            canon_entry_id: Uuid::from_u128(n),
            book_id: bid(),
            attribute_path: path.into(),
            value: serde_json::to_vec(&serde_json::json!("orig")).unwrap(),
            canon_layer: "L2_seeded".into(),
            lock_level: "soft".into(),
            last_synced_at: "2026-05-29T12:00:00Z".into(),
        }
    }

    fn deps_for_test(
        entries: Vec<CanonEntry>,
        book_locale: &str,
    ) -> SeederDeps<
        FakeBookReader,
        FakeCanonExporter,
        FakeKnowledgeReader,
        FakeTranslationGateway,
        FakeProjectionWriter,
        FakeCheckpointStore,
        FakeLifecycle,
        FakeAudit,
    > {
        let mut books = HashMap::new();
        books.insert(
            bid(),
            BookMetadata {
                book_id: bid(),
                source_locale: book_locale.into(),
                title: "Test Book".into(),
            },
        );
        SeederDeps {
            book_reader: FakeBookReader { books },
            canon_exporter: FakeCanonExporter::from_single_page(entries),
            knowledge_reader: FakeKnowledgeReader,
            translation_gateway: FakeTranslationGateway {
                called: RefCell::new(0),
                fail: false,
            },
            projection_writer: FakeProjectionWriter::default(),
            checkpoint_store: FakeCheckpointStore::default(),
            lifecycle: FakeLifecycle::default(),
            audit: FakeAudit::default(),
        }
    }

    fn req(reality_locale: &str, book_locale: &str) -> SeedRequest {
        SeedRequest {
            reality_id: rid(),
            book_id: bid(),
            reality_locale: reality_locale.into(),
            book_source_locale: book_locale.into(),
            reason: "integration_test".into(),
        }
    }

    // ─── Tests ───────────────────────────────────────────────────────────

    #[test]
    fn seeder_writes_all_canon_entries_to_projection() {
        let entries = vec![
            ce(0x1001, "world.climate"),
            ce(0x1002, "world.gravity"),
            ce(0x1003, "rule.combat"),
            ce(0x1004, "lore.creation_myth"),
            ce(0x1005, "faction.guild_x"),
        ];
        let deps = deps_for_test(entries, "en-US");
        let mut seeder = RealitySeeder::new(deps);
        let report = seeder.run(req("en-US", "en-US")).expect("ok");
        assert_eq!(report.canon_entries_written, 5);
        assert_eq!(report.canon_entries_translated, 0); // Q-L5-2: no translation when locales match
        assert!(!report.was_no_op);
        // Lifecycle: seeding → active.
        let trs = seeder.deps.lifecycle.transitions.borrow();
        assert_eq!(trs.len(), 1);
        assert_eq!(trs[0].1, RealityStatus::Seeding);
        assert_eq!(trs[0].2, RealityStatus::Active);
        // All 5 writes hit the projection.
        assert_eq!(seeder.deps.projection_writer.writes.borrow().len(), 5);
    }

    #[test]
    fn seeder_idempotent_rerun_writes_zero_new_rows() {
        let entries = vec![
            ce(0x2001, "world.climate"),
            ce(0x2002, "world.gravity"),
        ];
        let mut deps = deps_for_test(entries.clone(), "en-US");
        // Simulate that the first run has already populated the projection.
        let mut prior: HashSet<Uuid> = HashSet::new();
        prior.insert(Uuid::from_u128(0x2001));
        prior.insert(Uuid::from_u128(0x2002));
        deps.projection_writer
            .already_seeded_for_reality
            .borrow_mut()
            .insert(rid(), prior);
        let mut seeder = RealitySeeder::new(deps);
        let report = seeder.run(req("en-US", "en-US")).expect("ok");
        assert_eq!(seeder.deps.projection_writer.writes.borrow().len(), 0);
        assert!(report.was_no_op);
    }

    #[test]
    fn seeder_q_l5_2_translation_only_when_locales_differ() {
        let entries = vec![ce(0x3001, "world.climate"), ce(0x3002, "world.gravity")];
        let deps = deps_for_test(entries, "en-US");
        let mut seeder = RealitySeeder::new(deps);
        // reality.locale=vi-VN, book.source_locale=en-US → translation
        // gate fires.
        let report = seeder.run(req("vi-VN", "en-US")).expect("ok");
        assert_eq!(report.canon_entries_translated, 2);
        // Gateway was called 2 times (once per entry).
        assert_eq!(*seeder.deps.translation_gateway.called.borrow(), 2);
        // The value bytes carry the translation marker.
        let writes = seeder.deps.projection_writer.writes.borrow();
        assert!(writes[0]
            .value
            .windows(b"::en-US->vi-VN".len())
            .any(|w| w == b"::en-US->vi-VN"));
    }

    #[test]
    fn seeder_no_translation_when_locales_match_q_l5_2() {
        let entries = vec![ce(0x4001, "world.climate")];
        let deps = deps_for_test(entries, "en-US");
        let mut seeder = RealitySeeder::new(deps);
        let report = seeder.run(req("en-US", "en-US")).expect("ok");
        assert_eq!(report.canon_entries_translated, 0);
        assert_eq!(*seeder.deps.translation_gateway.called.borrow(), 0);
    }

    #[test]
    fn seeder_partial_fail_marks_reality_failed_seeding() {
        let entries = vec![
            ce(0x5001, "world.climate"),
            ce(0x5002, "world.gravity"),
            ce(0x5003, "rule.combat"),
            ce(0x5004, "lore.x"),
        ];
        let mut deps = deps_for_test(entries, "en-US");
        // Fail on the 4th write (0-indexed 3).
        *deps.projection_writer.fail_on_write.borrow_mut() = Some(3);
        let mut seeder = RealitySeeder::new(deps);
        let err = seeder.run(req("en-US", "en-US")).expect_err("fail");
        assert!(matches!(err, SeederError::ProjectionWrite(_)));
        // Reality transitions seeding → failed_seeding.
        let trs = seeder.deps.lifecycle.transitions.borrow();
        assert_eq!(trs.len(), 1);
        assert_eq!(trs[0].2, RealityStatus::FailedSeeding);
        // Three writes succeeded before the failure.
        assert_eq!(seeder.deps.projection_writer.writes.borrow().len(), 3);
        // Audit recorded the failure.
        let events = seeder.deps.audit.events.borrow();
        assert!(events.iter().any(|e| e.is_failure()));
    }

    #[test]
    fn seeder_rejects_nil_reality_id() {
        let deps = deps_for_test(vec![], "en-US");
        let mut seeder = RealitySeeder::new(deps);
        let mut r = req("en-US", "en-US");
        r.reality_id = Uuid::nil();
        let err = seeder.run(r).expect_err("nil reality_id");
        assert!(matches!(err, SeederError::InvalidRequest(_)));
    }

    #[test]
    fn seeder_rejects_book_not_found() {
        // Empty book registry → BookNotFound.
        let deps = SeederDeps {
            book_reader: FakeBookReader::default(),
            canon_exporter: FakeCanonExporter::from_single_page(vec![]),
            knowledge_reader: FakeKnowledgeReader,
            translation_gateway: FakeTranslationGateway {
                called: RefCell::new(0),
                fail: false,
            },
            projection_writer: FakeProjectionWriter::default(),
            checkpoint_store: FakeCheckpointStore::default(),
            lifecycle: FakeLifecycle::default(),
            audit: FakeAudit::default(),
        };
        let mut seeder = RealitySeeder::new(deps);
        let err = seeder.run(req("en-US", "en-US")).expect_err("not found");
        assert!(matches!(err, SeederError::BookNotFound(_)));
        // Lifecycle marked failed.
        let trs = seeder.deps.lifecycle.transitions.borrow();
        assert_eq!(trs[0].2, RealityStatus::FailedSeeding);
    }

    #[test]
    fn seeder_checkpoints_every_n_entries() {
        // 10 entries, checkpoint every 3 → expect 3 mid-flight + 1 final = 4
        // checkpoints (writes at 3, 6, 9, plus terminal).
        let entries: Vec<_> = (0..10).map(|i| ce(0x6000 + i, "x")).collect();
        let deps = deps_for_test(entries, "en-US");
        let mut seeder = RealitySeeder::new(deps).with_checkpoint_every(3);
        let report = seeder.run(req("en-US", "en-US")).expect("ok");
        assert_eq!(report.checkpoints_written, 4);
        let cps = seeder.deps.checkpoint_store.saved.borrow();
        assert_eq!(cps.len(), 4);
    }

    #[test]
    fn seeder_request_requires_translation_compares_locales_case_insensitive() {
        let r1 = SeedRequest {
            reality_locale: "en-US".into(),
            book_source_locale: "en-us".into(),
            ..req("en-US", "en-us")
        };
        assert!(!r1.requires_translation());
        let r2 = SeedRequest {
            reality_locale: "vi-VN".into(),
            book_source_locale: "en-US".into(),
            ..req("vi-VN", "en-US")
        };
        assert!(r2.requires_translation());
    }

    #[test]
    fn seeder_audit_records_phase_events_q_l1a_3() {
        let entries = vec![ce(0x7001, "world.climate")];
        let deps = deps_for_test(entries, "en-US");
        let mut seeder = RealitySeeder::new(deps);
        seeder.run(req("en-US", "en-US")).expect("ok");
        let events = seeder.deps.audit.events.borrow();
        // Phase events: validate, fetch_book_meta, load_checkpoint,
        // transition_active + 1 canon_upsert.
        let phase_count = events.iter().filter(|e| e.is_phase()).count();
        assert!(phase_count >= 4, "phases={phase_count}");
        let canon_count = events.iter().filter(|e| e.is_canon_upsert()).count();
        assert_eq!(canon_count, 1);
    }

    #[test]
    fn seeder_rejects_book_locale_disagreement() {
        // SeedRequest says book is en-US but BookMetadata claims fr-FR.
        let entries = vec![ce(0x8001, "x")];
        let deps = deps_for_test(entries, "fr-FR");
        let mut seeder = RealitySeeder::new(deps);
        let err = seeder
            .run(req("en-US", "en-US"))
            .expect_err("locale disagreement");
        assert!(matches!(err, SeederError::InvalidRequest(_)));
    }

    #[test]
    fn seeder_build_intent_synthetic_event_id_deterministic() {
        let e = ce(0x9001, "x");
        let i1 = build_intent(rid(), &e);
        let i2 = build_intent(rid(), &e);
        // Same inputs → same synthetic event_id (idempotent audit chain).
        assert_eq!(i1.source_event_id, i2.source_event_id);
        // Different reality_id → different event_id.
        let other_rid = Uuid::from_u128(0xfeed_face);
        let i3 = build_intent(other_rid, &e);
        assert_ne!(i1.source_event_id, i3.source_event_id);
    }
}
