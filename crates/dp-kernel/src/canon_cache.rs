//! Cycle 25 / L5.E — `canon_cache` Rust mirror of
//! `contracts/prompt/canon_cache.go` + `canon_reader.go`.
//!
//! # Purpose (Q-L4-1 parity)
//!
//! Rust services (world-service, roleplay-service Rust shards) need the
//! same canon-cache contract as the Go-side prompt builder. This module
//! ships:
//!
//! - [`CacheEntry`] / [`CanonValue`] data types matching the Go wire shape
//! - [`Backend`] trait abstracting the storage (Redis prod, [`FakeBackend`] in tests)
//! - [`Cache`] + [`CanonReader`] composing cache-aside read flow
//! - [`CanonGuardrail`] trait + [`NoOpGuardrail`] / [`StubRejectGuardrail`]
//!   placeholder impls for Q-L5-5 wiring (real impl lands in
//!   `crates/contracts-prompt/canon_guardrail.rs` per L5.I.3 downstream)
//! - Q-L5-1 invalidation: PRIMARY event-driven via [`Cache::invalidate`];
//!   60s TTL fallback via [`DEFAULT_TTL_SECS`]
//!
//! # LOCKED Q-IDs honored
//!
//! - **Q-L5-1**: event-driven primary; 60s TTL fallback
//! - **Q-L5-3**: `canon_layer` field carries `"L1_axiom"` | `"L2_seeded"`
//!   verbatim (cycle 23 enum)
//! - **Q-L5-4**: this is the IN-PROCESS cache layer; the RPC contract
//!   (L5.F) lives in `contracts/api/glossary-service/` (HTTP/JSON V1)
//! - **Q-L5-5**: [`CanonGuardrail`] trait is the integration point;
//!   real impl lands downstream
//!
//! # Per-reality isolation
//!
//! Cache key shape: `canon:<reality_id>:<book_id>:<attribute_path>`. The
//! reality_id PREFIX is mandatory — see Go-side
//! `contracts/prompt/canon_cache.go` for rationale.
//!
//! # Time representation
//!
//! Timestamps are i64 epoch seconds (UTC). Matches the dp-kernel pattern
//! in `entity_status.rs` + `observability.rs` (no chrono dep — keeps
//! workspace dependency surface small).

use std::collections::HashMap;
use std::sync::Mutex;
use std::time::Duration;

use serde::{Deserialize, Serialize};
use uuid::Uuid;

/// Q-L5-1 fallback TTL (60 seconds). Event-driven invalidate is PRIMARY;
/// this exists for crash recovery / lost-signal scenarios.
pub const DEFAULT_TTL_SECS: u64 = 60;

/// Q-L5-3 canon layer enum mirror.
pub const CANON_LAYER_L1_AXIOM: &str = "L1_axiom";
pub const CANON_LAYER_L2_SEEDED: &str = "L2_seeded";

/// Cacheable attribute prefixes (matches Go side).
pub const CACHEABLE_ATTRIBUTE_PREFIXES: &[&str] = &[
    "world.",
    "faction.",
    "character.",
    "rule.",
    "lore.",
];

/// Returns true if `attribute_path` matches one of the cacheable prefixes.
pub fn is_attribute_cacheable(attribute_path: &str) -> bool {
    CACHEABLE_ATTRIBUTE_PREFIXES
        .iter()
        .any(|p| attribute_path.starts_with(p))
}

/// Cache key shape — matches Go `BuildKey`. Per-reality prefix enforces
/// isolation invariant.
pub fn build_key(reality_id: Uuid, book_id: Uuid, attribute_path: &str) -> String {
    format!("canon:{reality_id}:{book_id}:{attribute_path}")
}

/// Cache entry wire shape. JSON serialization matches Go
/// canon_cache_codec.go (epoch-second i64s, not RFC3339 strings — Go
/// side will adapt at the codec boundary if needed; cross-language wire
/// parity is a deferred concern, D-CANON-CACHE-WIRE-PARITY).
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct CacheEntry {
    pub reality_id: Uuid,
    pub canon_entry_id: Uuid,
    pub book_id: Uuid,
    pub attribute_path: String,
    /// Canonical JSON-encoded canon value (opaque bytes).
    pub value: Vec<u8>,
    /// Q-L5-3: `"L1_axiom"` | `"L2_seeded"`.
    pub canon_layer: String,
    /// Mirrors canon_projection.last_synced_at (epoch seconds UTC).
    pub last_synced_at_epoch: i64,
    /// Q-L5-1 TTL fallback deadline (epoch seconds UTC).
    pub expires_at_epoch: i64,
}

impl CacheEntry {
    /// Returns the canonical cache key for this entry.
    pub fn cache_key(&self) -> String {
        build_key(self.reality_id, self.book_id, &self.attribute_path)
    }
}

/// Cold-path canon read shape (from per-reality canon_projection
/// SELECT). Returned by [`Reader`] + [`CanonReader::read`].
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CanonValue {
    pub canon_entry_id: Uuid,
    pub reality_id: Uuid,
    pub book_id: Uuid,
    pub attribute_path: String,
    pub value: Vec<u8>,
    pub canon_layer: String,
    /// True if served from cache; false if from cold-path Reader.
    pub from_cache: bool,
}

/// Cache errors.
#[derive(Debug, thiserror::Error)]
pub enum CacheError {
    #[error("canon_cache: attribute path not in cacheable whitelist")]
    AttributeNotCacheable,
    #[error("canon_cache: miss")]
    Miss,
    #[error("canon_cache: backend error: {0}")]
    Backend(String),
    #[error("canon_cache: codec error: {0}")]
    Codec(String),
}

/// Reader-side errors (cold path).
#[derive(Debug, thiserror::Error)]
pub enum ReaderError {
    #[error("canon_reader: canon not found")]
    NotFound,
    #[error("canon_reader: cold path error: {0}")]
    ColdPath(String),
}

/// Backend trait — production wraps Redis Sentinel (cycle 5 L1.F);
/// tests use [`FakeBackend`].
pub trait Backend: Send + Sync {
    fn get_raw(&self, key: &str) -> Result<Vec<u8>, CacheError>;
    fn set_raw(&self, key: &str, value: &[u8], ttl: Duration) -> Result<(), CacheError>;
    fn delete(&self, keys: &[String]) -> Result<usize, CacheError>;
    fn scan(&self, prefix: &str) -> Result<Vec<String>, CacheError>;
}

/// Metrics sink (matches Go MetricsSink). Production binds Prometheus;
/// tests use [`FakeMetrics`].
pub trait MetricsSink: Send + Sync {
    fn inc_hit(&self, reality_id: Uuid);
    fn inc_miss(&self, reality_id: Uuid);
    fn add_invalidations(&self, reality_id: Uuid, n: usize);
}

/// No-op metrics (default).
pub struct NoOpMetrics;

impl MetricsSink for NoOpMetrics {
    fn inc_hit(&self, _: Uuid) {}
    fn inc_miss(&self, _: Uuid) {}
    fn add_invalidations(&self, _: Uuid, _: usize) {}
}

/// Clock trait — tests use [`FixedClock`].
pub trait Clock: Send + Sync {
    /// Returns epoch seconds (UTC).
    fn now_epoch(&self) -> i64;
}

/// Real wall-clock impl.
pub struct RealClock;

impl Clock for RealClock {
    fn now_epoch(&self) -> i64 {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_secs() as i64)
            .unwrap_or(0)
    }
}

/// The L5.E canon cache. Thread-safe (all interior mutability is in the
/// Backend / MetricsSink impls). One instance per process.
pub struct Cache {
    backend: Box<dyn Backend>,
    ttl: Duration,
    clock: Box<dyn Clock>,
    metrics: Box<dyn MetricsSink>,
}

/// Builder config for [`Cache::new`].
pub struct CacheConfig {
    pub backend: Box<dyn Backend>,
    pub ttl: Option<Duration>,
    pub clock: Option<Box<dyn Clock>>,
    pub metrics: Option<Box<dyn MetricsSink>>,
}

impl Cache {
    /// Constructs a Cache. Backend is required; everything else has a
    /// safe default.
    pub fn new(cfg: CacheConfig) -> Self {
        Self {
            backend: cfg.backend,
            ttl: cfg.ttl.unwrap_or(Duration::from_secs(DEFAULT_TTL_SECS)),
            clock: cfg.clock.unwrap_or_else(|| Box::new(RealClock)),
            metrics: cfg.metrics.unwrap_or_else(|| Box::new(NoOpMetrics)),
        }
    }

    /// Cache-aside Get. Returns the cached entry or [`CacheError::Miss`] /
    /// [`CacheError::AttributeNotCacheable`].
    pub fn get(
        &self,
        reality_id: Uuid,
        book_id: Uuid,
        attribute_path: &str,
    ) -> Result<CacheEntry, CacheError> {
        if !is_attribute_cacheable(attribute_path) {
            return Err(CacheError::AttributeNotCacheable);
        }
        let key = build_key(reality_id, book_id, attribute_path);
        let raw = match self.backend.get_raw(&key) {
            Ok(v) => v,
            Err(CacheError::Miss) => {
                self.metrics.inc_miss(reality_id);
                return Err(CacheError::Miss);
            }
            Err(e) => {
                self.metrics.inc_miss(reality_id);
                return Err(e);
            }
        };
        let entry: CacheEntry = serde_json::from_slice(&raw)
            .map_err(|e| {
                self.metrics.inc_miss(reality_id);
                CacheError::Codec(e.to_string())
            })?;
        // Q-L5-1 fallback TTL check (defense-in-depth vs clock-skew).
        if entry.expires_at_epoch <= self.clock.now_epoch() {
            self.metrics.inc_miss(reality_id);
            let _ = self.backend.delete(&[key]);
            return Err(CacheError::Miss);
        }
        self.metrics.inc_hit(reality_id);
        Ok(entry)
    }

    /// Stores entry under its canonical key with the Q-L5-1 fallback TTL.
    /// Overwrites caller-supplied `expires_at_epoch`.
    pub fn set(&self, mut entry: CacheEntry) -> Result<(), CacheError> {
        if !is_attribute_cacheable(&entry.attribute_path) {
            return Err(CacheError::AttributeNotCacheable);
        }
        entry.expires_at_epoch = self.clock.now_epoch() + self.ttl.as_secs() as i64;
        let raw = serde_json::to_vec(&entry).map_err(|e| CacheError::Codec(e.to_string()))?;
        self.backend.set_raw(&entry.cache_key(), &raw, self.ttl)
    }

    /// Q-L5-1 PRIMARY invalidation. Called by canon_writer (cycle 24)
    /// after every UPSERT into canon_projection. Idempotent.
    pub fn invalidate(&self, reality_id: Uuid, canon_entry_id: Uuid) -> Result<usize, CacheError> {
        let prefix = format!("canon:{reality_id}:");
        let keys = self.backend.scan(&prefix)?;
        if keys.is_empty() {
            return Ok(0);
        }
        let mut matched = Vec::new();
        for key in &keys {
            let raw = match self.backend.get_raw(key) {
                Ok(v) => v,
                Err(_) => continue, // best-effort
            };
            match serde_json::from_slice::<CacheEntry>(&raw) {
                Ok(e) if e.canon_entry_id == canon_entry_id => matched.push(key.clone()),
                Err(_) => matched.push(key.clone()), // corrupt — invalidate aggressively
                Ok(_) => {}
            }
        }
        if matched.is_empty() {
            return Ok(0);
        }
        let deleted = self.backend.delete(&matched)?;
        self.metrics.add_invalidations(reality_id, deleted);
        Ok(deleted)
    }

    /// Drops ALL cache entries for a reality. Used at reality lifecycle
    /// transitions / catastrophic divergence recovery.
    pub fn invalidate_reality(&self, reality_id: Uuid) -> Result<usize, CacheError> {
        let prefix = format!("canon:{reality_id}:");
        let keys = self.backend.scan(&prefix)?;
        if keys.is_empty() {
            return Ok(0);
        }
        let deleted = self.backend.delete(&keys)?;
        self.metrics.add_invalidations(reality_id, deleted);
        Ok(deleted)
    }
}

/// Cold-path Reader. Production binds sqlx on per-reality
/// canon_projection (cycle-23 L5.D); tests use [`FakeReader`].
pub trait Reader: Send + Sync {
    fn read_canon(
        &self,
        reality_id: Uuid,
        book_id: Uuid,
        attribute_path: &str,
    ) -> Result<CanonValue, ReaderError>;
}

/// Composes [`Cache`] + [`Reader`] into cache-aside read flow.
pub struct CanonReader {
    cache: Cache,
    reader: Box<dyn Reader>,
}

impl CanonReader {
    pub fn new(cache: Cache, reader: Box<dyn Reader>) -> Self {
        Self { cache, reader }
    }

    /// Cache-aside read (Q-L5-1 flow).
    pub fn read(
        &self,
        reality_id: Uuid,
        book_id: Uuid,
        attribute_path: &str,
    ) -> Result<CanonValue, ReaderError> {
        // Step 1 — cache lookup.
        if is_attribute_cacheable(attribute_path) {
            match self.cache.get(reality_id, book_id, attribute_path) {
                Ok(entry) => {
                    return Ok(CanonValue {
                        canon_entry_id: entry.canon_entry_id,
                        reality_id: entry.reality_id,
                        book_id: entry.book_id,
                        attribute_path: entry.attribute_path,
                        value: entry.value,
                        canon_layer: entry.canon_layer,
                        from_cache: true,
                    });
                }
                Err(_) => {
                    // fall through to cold path (miss / not-cacheable /
                    // backend / codec all degrade to cold path)
                }
            }
        }
        // Step 2 — cold path.
        let mut val = self.reader.read_canon(reality_id, book_id, attribute_path)?;
        // Step 3 — populate cache (best-effort).
        if is_attribute_cacheable(attribute_path) {
            let entry = CacheEntry {
                reality_id: val.reality_id,
                canon_entry_id: val.canon_entry_id,
                book_id: val.book_id,
                attribute_path: val.attribute_path.clone(),
                value: val.value.clone(),
                canon_layer: val.canon_layer.clone(),
                last_synced_at_epoch: self.cache.clock.now_epoch(),
                expires_at_epoch: 0, // overwritten by Cache::set
            };
            let _ = self.cache.set(entry);
        }
        val.from_cache = false;
        Ok(val)
    }

    /// Pass-through for [`Cache::invalidate`].
    pub fn invalidate(&self, reality_id: Uuid, canon_entry_id: Uuid) -> Result<usize, CacheError> {
        self.cache.invalidate(reality_id, canon_entry_id)
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Guardrail (Q-L5-5).
// ─────────────────────────────────────────────────────────────────────────

/// Q-L5-5 guardrail interface — roleplay-service / world-service call
/// `check_proposed_write` BEFORE writing a proposed L3 event. Returns
/// `Err(GuardrailViolation)` if the proposal conflicts with L1 canon.
///
/// Cycle 25 ships ONLY the interface + [`NoOpGuardrail`] /
/// [`StubRejectGuardrail`] placeholders. Real impl lands downstream
/// (`crates/contracts-prompt/canon_guardrail.rs`, L5.I.3).
pub trait CanonGuardrail: Send + Sync {
    fn check_proposed_write(&self, proposal: &GuardrailProposal) -> Result<(), GuardrailViolation>;
}

/// Input to [`CanonGuardrail::check_proposed_write`].
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GuardrailProposal {
    pub reality_id: Uuid,
    pub book_id: Uuid,
    pub attribute_path: String,
    pub proposed_value: Vec<u8>,
    pub source_event_type: String,
}

/// Returned (as Err) when a proposed write conflicts with L1 axiom.
#[derive(Debug, Clone, thiserror::Error)]
#[error("canon_guardrail: L1 axiom violated for {book_id}.{attribute_path} (reason={reason})")]
pub struct GuardrailViolation {
    pub book_id: Uuid,
    pub attribute_path: String,
    pub proposed_value: Vec<u8>,
    pub reason: String,
}

/// Cycle-25 default impl: always allows.
pub struct NoOpGuardrail;

impl CanonGuardrail for NoOpGuardrail {
    fn check_proposed_write(&self, _: &GuardrailProposal) -> Result<(), GuardrailViolation> {
        Ok(())
    }
}

/// Always returns a violation — used by tests to assert wiring.
pub struct StubRejectGuardrail {
    pub reason: String,
}

impl CanonGuardrail for StubRejectGuardrail {
    fn check_proposed_write(&self, p: &GuardrailProposal) -> Result<(), GuardrailViolation> {
        Err(GuardrailViolation {
            book_id: p.book_id,
            attribute_path: p.attribute_path.clone(),
            proposed_value: p.proposed_value.clone(),
            reason: self.reason.clone(),
        })
    }
}

// ─────────────────────────────────────────────────────────────────────────
// In-process FakeBackend / FakeMetrics / FixedClock for tests.
// ─────────────────────────────────────────────────────────────────────────

/// Test-only in-process Backend.
pub struct FakeBackend {
    inner: Mutex<FakeBackendInner>,
    clock: Box<dyn Clock>,
}

struct FakeBackendInner {
    store: HashMap<String, Vec<u8>>,
    expires_epoch: HashMap<String, i64>,
}

impl FakeBackend {
    pub fn new(clock: Box<dyn Clock>) -> Self {
        Self {
            inner: Mutex::new(FakeBackendInner {
                store: HashMap::new(),
                expires_epoch: HashMap::new(),
            }),
            clock,
        }
    }

    pub fn size(&self) -> usize {
        self.inner.lock().unwrap().store.len()
    }
}

impl Backend for FakeBackend {
    fn get_raw(&self, key: &str) -> Result<Vec<u8>, CacheError> {
        let mut g = self.inner.lock().unwrap();
        if let Some(exp) = g.expires_epoch.get(key).copied() {
            if exp <= self.clock.now_epoch() {
                g.store.remove(key);
                g.expires_epoch.remove(key);
                return Err(CacheError::Miss);
            }
        }
        g.store.get(key).cloned().ok_or(CacheError::Miss)
    }

    fn set_raw(&self, key: &str, value: &[u8], ttl: Duration) -> Result<(), CacheError> {
        let mut g = self.inner.lock().unwrap();
        g.store.insert(key.to_string(), value.to_vec());
        if !ttl.is_zero() {
            g.expires_epoch
                .insert(key.to_string(), self.clock.now_epoch() + ttl.as_secs() as i64);
        }
        Ok(())
    }

    fn delete(&self, keys: &[String]) -> Result<usize, CacheError> {
        let mut g = self.inner.lock().unwrap();
        let mut count = 0;
        for k in keys {
            if g.store.remove(k).is_some() {
                count += 1;
                g.expires_epoch.remove(k);
            }
        }
        Ok(count)
    }

    fn scan(&self, prefix: &str) -> Result<Vec<String>, CacheError> {
        let g = self.inner.lock().unwrap();
        Ok(g.store
            .keys()
            .filter(|k| k.starts_with(prefix))
            .cloned()
            .collect())
    }
}

/// Test-only FixedClock.
pub struct FixedClock {
    inner: Mutex<i64>,
}

impl FixedClock {
    pub fn new(epoch: i64) -> Self {
        Self {
            inner: Mutex::new(epoch),
        }
    }

    pub fn advance(&self, d: Duration) {
        let mut g = self.inner.lock().unwrap();
        *g += d.as_secs() as i64;
    }
}

impl Clock for FixedClock {
    fn now_epoch(&self) -> i64 {
        *self.inner.lock().unwrap()
    }
}

/// Test-only FakeMetrics (counters).
#[derive(Default)]
pub struct FakeMetrics {
    inner: Mutex<FakeMetricsInner>,
}

#[derive(Default)]
struct FakeMetricsInner {
    hits: HashMap<Uuid, usize>,
    misses: HashMap<Uuid, usize>,
    invalidations: HashMap<Uuid, usize>,
}

impl FakeMetrics {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn hits(&self, reality_id: Uuid) -> usize {
        *self
            .inner
            .lock()
            .unwrap()
            .hits
            .get(&reality_id)
            .unwrap_or(&0)
    }

    pub fn misses(&self, reality_id: Uuid) -> usize {
        *self
            .inner
            .lock()
            .unwrap()
            .misses
            .get(&reality_id)
            .unwrap_or(&0)
    }

    pub fn invalidations(&self, reality_id: Uuid) -> usize {
        *self
            .inner
            .lock()
            .unwrap()
            .invalidations
            .get(&reality_id)
            .unwrap_or(&0)
    }
}

impl MetricsSink for FakeMetrics {
    fn inc_hit(&self, reality_id: Uuid) {
        *self
            .inner
            .lock()
            .unwrap()
            .hits
            .entry(reality_id)
            .or_insert(0) += 1;
    }
    fn inc_miss(&self, reality_id: Uuid) {
        *self
            .inner
            .lock()
            .unwrap()
            .misses
            .entry(reality_id)
            .or_insert(0) += 1;
    }
    fn add_invalidations(&self, reality_id: Uuid, n: usize) {
        *self
            .inner
            .lock()
            .unwrap()
            .invalidations
            .entry(reality_id)
            .or_insert(0) += n;
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Tests.
// ─────────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Arc;

    const FIXED_EPOCH: i64 = 1_780_000_000; // ~2026-05-29

    fn sample_entry(reality_id: Uuid, attribute: &str) -> CacheEntry {
        CacheEntry {
            reality_id,
            canon_entry_id: Uuid::new_v4(),
            book_id: Uuid::new_v4(),
            attribute_path: attribute.to_string(),
            value: b"{\"name\":\"Aldarion\"}".to_vec(),
            canon_layer: CANON_LAYER_L2_SEEDED.to_string(),
            last_synced_at_epoch: FIXED_EPOCH,
            expires_at_epoch: FIXED_EPOCH,
        }
    }

    // FixedClockWrapper lets us share an Arc<FixedClock> as the Clock
    // dep for both the Cache and the Backend without giving up ownership.
    struct FixedClockWrapper(Arc<FixedClock>);
    impl Clock for FixedClockWrapper {
        fn now_epoch(&self) -> i64 {
            self.0.now_epoch()
        }
    }

    fn new_cache_for_test() -> (Cache, Arc<FixedClock>) {
        let clk = Arc::new(FixedClock::new(FIXED_EPOCH));
        let backend = FakeBackend::new(Box::new(FixedClockWrapper(clk.clone())));
        let cache = Cache::new(CacheConfig {
            backend: Box::new(backend),
            ttl: Some(Duration::from_secs(60)),
            clock: Some(Box::new(FixedClockWrapper(clk.clone()))),
            metrics: Some(Box::new(FakeMetrics::new())),
        });
        (cache, clk)
    }

    #[test]
    fn whitelist_classification() {
        assert!(is_attribute_cacheable("world.climate"));
        assert!(is_attribute_cacheable("faction.allegiance"));
        assert!(is_attribute_cacheable("character.eye_color"));
        assert!(is_attribute_cacheable("rule.combat"));
        assert!(is_attribute_cacheable("lore.intro"));
        assert!(!is_attribute_cacheable("chapter.prose.body"));
        assert!(!is_attribute_cacheable("history.recent"));
        assert!(!is_attribute_cacheable(""));
        assert!(!is_attribute_cacheable("world")); // no dot
    }

    #[test]
    fn build_key_per_reality_isolation() {
        let r1 = Uuid::new_v4();
        let r2 = Uuid::new_v4();
        let b = Uuid::new_v4();
        let k1 = build_key(r1, b, "world.climate");
        let k2 = build_key(r2, b, "world.climate");
        assert_ne!(k1, k2, "per-reality isolation BROKEN");
        assert!(k1.starts_with(&format!("canon:{r1}:")));
    }

    #[test]
    fn set_rejects_non_cacheable() {
        let (cache, _) = new_cache_for_test();
        let entry = sample_entry(Uuid::new_v4(), "chapter.prose.body");
        let err = cache.set(entry).expect_err("expected AttributeNotCacheable");
        assert!(matches!(err, CacheError::AttributeNotCacheable));
    }

    #[test]
    fn get_returns_miss_for_empty_cache() {
        let (cache, _) = new_cache_for_test();
        let err = cache
            .get(Uuid::new_v4(), Uuid::new_v4(), "world.climate")
            .expect_err("expected miss");
        assert!(matches!(err, CacheError::Miss));
    }

    #[test]
    fn set_then_get_hit_flow() {
        let (cache, _) = new_cache_for_test();
        let reality_id = Uuid::new_v4();
        let entry = sample_entry(reality_id, "world.climate");
        cache.set(entry.clone()).expect("set");
        let got = cache
            .get(reality_id, entry.book_id, &entry.attribute_path)
            .expect("hit");
        assert_eq!(got.canon_entry_id, entry.canon_entry_id);
        assert_eq!(got.canon_layer, CANON_LAYER_L2_SEEDED);
    }

    #[test]
    fn ttl_fallback_expired_entry_is_miss() {
        let (cache, clk) = new_cache_for_test();
        let reality_id = Uuid::new_v4();
        let entry = sample_entry(reality_id, "faction.allegiance");
        cache.set(entry.clone()).expect("set");

        clk.advance(Duration::from_secs(61));

        let err = cache
            .get(reality_id, entry.book_id, &entry.attribute_path)
            .expect_err("expected miss after TTL");
        assert!(matches!(err, CacheError::Miss));
    }

    #[test]
    fn invalidate_primary_path() {
        let (cache, _) = new_cache_for_test();
        let reality_id = Uuid::new_v4();
        let book_id = Uuid::new_v4();
        let canon_entry_id = Uuid::new_v4();

        for attr in &["world.climate", "faction.allegiance", "lore.intro"] {
            let mut e = sample_entry(reality_id, attr);
            e.book_id = book_id;
            e.canon_entry_id = canon_entry_id;
            cache.set(e).expect("set");
        }
        // Unrelated entry — must survive.
        let mut other = sample_entry(reality_id, "rule.combat");
        other.book_id = book_id;
        cache.set(other.clone()).expect("set other");

        let deleted = cache.invalidate(reality_id, canon_entry_id).expect("inv");
        assert_eq!(deleted, 3);

        // Other entry survives.
        let got = cache
            .get(reality_id, book_id, &other.attribute_path)
            .expect("other survives");
        assert_eq!(got.canon_entry_id, other.canon_entry_id);

        // Idempotent.
        let deleted2 = cache.invalidate(reality_id, canon_entry_id).expect("idem");
        assert_eq!(deleted2, 0);
    }

    #[test]
    fn invalidate_per_reality_isolation() {
        let (cache, _) = new_cache_for_test();
        let reality_a = Uuid::new_v4();
        let reality_b = Uuid::new_v4();
        let book_id = Uuid::new_v4();
        let canon_entry_id = Uuid::new_v4();

        for r in &[reality_a, reality_b] {
            let mut e = sample_entry(*r, "world.climate");
            e.book_id = book_id;
            e.canon_entry_id = canon_entry_id;
            cache.set(e).expect("set");
        }

        let deleted = cache.invalidate(reality_a, canon_entry_id).expect("inv A");
        assert_eq!(deleted, 1);

        // Reality B survives.
        let got_b = cache
            .get(reality_b, book_id, "world.climate")
            .expect("B survives");
        assert_eq!(got_b.reality_id, reality_b);
    }

    #[test]
    fn invalidate_reality_drops_all() {
        let (cache, _) = new_cache_for_test();
        let reality_id = Uuid::new_v4();
        for attr in &[
            "world.climate",
            "world.geo",
            "faction.banner",
            "lore.intro",
            "rule.combat",
        ] {
            cache.set(sample_entry(reality_id, attr)).expect("set");
        }
        let other = Uuid::new_v4();
        let other_entry = sample_entry(other, "world.climate");
        let book_id_other = other_entry.book_id;
        cache.set(other_entry.clone()).expect("set other");

        let deleted = cache.invalidate_reality(reality_id).expect("inv-reality");
        assert_eq!(deleted, 5);

        // Other reality survives.
        let got = cache.get(other, book_id_other, "world.climate");
        assert!(got.is_ok(), "other reality cache dropped");
    }

    // CanonReader (cache-aside) tests.
    struct FakeReader {
        rows: Mutex<HashMap<String, CanonValue>>,
        calls: Mutex<usize>,
    }

    impl FakeReader {
        fn new() -> Self {
            Self {
                rows: Mutex::new(HashMap::new()),
                calls: Mutex::new(0),
            }
        }

        fn insert(&self, reality_id: Uuid, book_id: Uuid, attr: &str, v: CanonValue) {
            self.rows
                .lock()
                .unwrap()
                .insert(build_key(reality_id, book_id, attr), v);
        }

        fn calls(&self) -> usize {
            *self.calls.lock().unwrap()
        }
    }

    impl Reader for FakeReader {
        fn read_canon(
            &self,
            reality_id: Uuid,
            book_id: Uuid,
            attribute_path: &str,
        ) -> Result<CanonValue, ReaderError> {
            *self.calls.lock().unwrap() += 1;
            self.rows
                .lock()
                .unwrap()
                .get(&build_key(reality_id, book_id, attribute_path))
                .cloned()
                .ok_or(ReaderError::NotFound)
        }
    }

    struct ArcReader(Arc<FakeReader>);
    impl Reader for ArcReader {
        fn read_canon(&self, r: Uuid, b: Uuid, a: &str) -> Result<CanonValue, ReaderError> {
            self.0.read_canon(r, b, a)
        }
    }

    #[test]
    fn canon_reader_hits_cache_on_second_read() {
        let (cache, _) = new_cache_for_test();
        let rd = Arc::new(FakeReader::new());
        let reality_id = Uuid::new_v4();
        let book_id = Uuid::new_v4();
        let val = CanonValue {
            canon_entry_id: Uuid::new_v4(),
            reality_id,
            book_id,
            attribute_path: "world.climate".into(),
            value: b"{\"climate\":\"arid\"}".to_vec(),
            canon_layer: CANON_LAYER_L1_AXIOM.into(),
            from_cache: false,
        };
        rd.insert(reality_id, book_id, "world.climate", val);

        let cr = CanonReader::new(cache, Box::new(ArcReader(rd.clone())));

        let v1 = cr.read(reality_id, book_id, "world.climate").expect("first");
        assert!(!v1.from_cache);
        assert_eq!(rd.calls(), 1);

        let v2 = cr.read(reality_id, book_id, "world.climate").expect("second");
        assert!(v2.from_cache);
        assert_eq!(rd.calls(), 1);
        assert_eq!(v2.canon_layer, CANON_LAYER_L1_AXIOM);
    }

    #[test]
    fn canon_reader_not_cacheable_always_reader() {
        let (cache, _) = new_cache_for_test();
        let rd = Arc::new(FakeReader::new());
        let reality_id = Uuid::new_v4();
        let book_id = Uuid::new_v4();
        rd.insert(
            reality_id,
            book_id,
            "chapter.prose.body",
            CanonValue {
                canon_entry_id: Uuid::new_v4(),
                reality_id,
                book_id,
                attribute_path: "chapter.prose.body".into(),
                value: b"...".to_vec(),
                canon_layer: CANON_LAYER_L2_SEEDED.into(),
                from_cache: false,
            },
        );
        let cr = CanonReader::new(cache, Box::new(ArcReader(rd.clone())));

        for _ in 0..3 {
            let v = cr
                .read(reality_id, book_id, "chapter.prose.body")
                .expect("read");
            assert!(!v.from_cache);
        }
        assert_eq!(rd.calls(), 3);
    }

    #[test]
    fn canon_reader_not_found_propagates() {
        let (cache, _) = new_cache_for_test();
        let rd = Arc::new(FakeReader::new());
        let cr = CanonReader::new(cache, Box::new(ArcReader(rd)));
        let err = cr
            .read(Uuid::new_v4(), Uuid::new_v4(), "world.climate")
            .expect_err("expected NotFound");
        assert!(matches!(err, ReaderError::NotFound));
    }

    #[test]
    fn canon_reader_invalidate_forces_reader_fetch() {
        let (cache, _) = new_cache_for_test();
        let rd = Arc::new(FakeReader::new());
        let reality_id = Uuid::new_v4();
        let book_id = Uuid::new_v4();
        let canon_entry_id = Uuid::new_v4();
        rd.insert(
            reality_id,
            book_id,
            "world.climate",
            CanonValue {
                canon_entry_id,
                reality_id,
                book_id,
                attribute_path: "world.climate".into(),
                value: b"{\"v\":1}".to_vec(),
                canon_layer: CANON_LAYER_L2_SEEDED.into(),
                from_cache: false,
            },
        );
        let cr = CanonReader::new(cache, Box::new(ArcReader(rd.clone())));

        let _ = cr.read(reality_id, book_id, "world.climate").unwrap();
        assert_eq!(rd.calls(), 1);
        let _ = cr.read(reality_id, book_id, "world.climate").unwrap();
        assert_eq!(rd.calls(), 1);

        let n = cr.invalidate(reality_id, canon_entry_id).unwrap();
        assert_eq!(n, 1);

        // Update reader to return v=2.
        rd.insert(
            reality_id,
            book_id,
            "world.climate",
            CanonValue {
                canon_entry_id,
                reality_id,
                book_id,
                attribute_path: "world.climate".into(),
                value: b"{\"v\":2}".to_vec(),
                canon_layer: CANON_LAYER_L2_SEEDED.into(),
                from_cache: false,
            },
        );
        let v = cr.read(reality_id, book_id, "world.climate").unwrap();
        assert_eq!(rd.calls(), 2);
        assert_eq!(v.value, b"{\"v\":2}");
    }

    // Guardrail tests (Q-L5-5).
    #[test]
    fn noop_guardrail_allows() {
        let g: Box<dyn CanonGuardrail> = Box::new(NoOpGuardrail);
        g.check_proposed_write(&GuardrailProposal {
            reality_id: Uuid::new_v4(),
            book_id: Uuid::new_v4(),
            attribute_path: "world.climate".into(),
            proposed_value: b"\"arid\"".to_vec(),
            source_event_type: "l3.event.recorded".into(),
        })
        .expect("noop should allow");
    }

    #[test]
    fn stub_reject_guardrail_returns_violation() {
        let g: Box<dyn CanonGuardrail> = Box::new(StubRejectGuardrail {
            reason: "test reject".into(),
        });
        let p = GuardrailProposal {
            reality_id: Uuid::new_v4(),
            book_id: Uuid::new_v4(),
            attribute_path: "world.climate".into(),
            proposed_value: b"\"tropical\"".to_vec(),
            source_event_type: "l3.event.recorded".into(),
        };
        let err = g.check_proposed_write(&p).expect_err("expected violation");
        assert_eq!(err.reason, "test reject");
        assert_eq!(err.book_id, p.book_id);
    }
}
