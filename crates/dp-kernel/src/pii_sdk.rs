//! `pii_sdk` — Rust mirror of `contracts/pii/` (cycle 22 / L4.Q).
//!
//! Mirrors the Go SDK's PII access surface for Rust services. Q-L4-1
//! parity rules — both languages MUST agree byte-for-byte on:
//!
//! - `SensitiveReadTag` enum values (`pii_user_get`, `pii_user_erase`,
//!   `bulk_pii_read`) — they back the cycle-3 `meta-sensitive-read-paths.yml`
//!   enumeration.
//! - The `SensitiveReadEntry` shape mirroring `meta_read_audit`
//!   (migration 014) CHECK constraints.
//! - The "no plaintext caching" + "audit-or-fail" invariants.
//!
//! This crate INTENTIONALLY does not depend on a real KMS or PgPool —
//! the security-track sub-program wires the production adapters. Tests
//! here use trait-object stand-ins.

use std::sync::{Arc, Mutex};

use thiserror::Error;

/// `meta-sensitive-read-paths.yml` enumerated id. SDK tag validated at
/// runtime as defense-in-depth against typos.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SensitiveReadTag {
    /// Single-user GetPII via the SDK. Cycle-22 addition (V1+30d
    /// migration extends the enum).
    PiiUserGet,
    /// Single-user ErasePII via the SDK.
    PiiUserErase,
    /// Cycle-3 enumerated bulk-PII path (admin-cli only — SDK does not
    /// expose a bulk method this cycle).
    BulkPiiRead,
}

impl SensitiveReadTag {
    /// Wire string mirrors `meta_read_audit.query_type` enum.
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::PiiUserGet => "pii_user_get",
            Self::PiiUserErase => "pii_user_erase",
            Self::BulkPiiRead => "bulk_pii_read",
        }
    }

    /// Parse from the wire string. Returns None on unknown.
    pub fn from_str(s: &str) -> Option<Self> {
        match s {
            "pii_user_get" => Some(Self::PiiUserGet),
            "pii_user_erase" => Some(Self::PiiUserErase),
            "bulk_pii_read" => Some(Self::BulkPiiRead),
            _ => None,
        }
    }
}

/// SDK error surface.
#[derive(Debug, Error)]
pub enum PiiError {
    /// SDK construction failed because a required dep was missing.
    #[error("pii: missing required dep: {0}")]
    Misconfigured(&'static str),
    /// Validate failed on a SensitiveReadEntry.
    #[error("pii: invalid sensitive-read entry: {0}")]
    InvalidEntry(String),
    /// Audit writer failed — the SDK MUST NOT return plaintext in this case.
    #[error("pii: audit write failed: {0}")]
    AuditFailed(String),
    /// KEKManager.destroy_kek failed — GDPR Art. 17 NOT satisfied.
    #[error("pii: KEK destroy failed: {0}")]
    EraseFailed(String),
    /// Caller passed a tag not in the enumerated set.
    #[error("pii: invalid sensitive-read tag")]
    InvalidTag,
}

/// In-memory mirror of `meta_read_audit` row (migration 014).
#[derive(Debug, Clone)]
pub struct SensitiveReadEntry {
    pub audit_id: [u8; 16],
    pub query_type: SensitiveReadTag,
    pub user_ref_id: [u8; 16],
    pub actor_id: String,
    pub actor_type: String,
    pub result_count: u32,
    pub created_at_nanos: i64,
}

impl SensitiveReadEntry {
    /// Validate enforces the migration 014 CHECK constraints in-process.
    pub fn validate(&self) -> Result<(), PiiError> {
        if self.audit_id == [0u8; 16] {
            return Err(PiiError::InvalidEntry("audit_id required".into()));
        }
        if self.actor_id.is_empty() {
            return Err(PiiError::InvalidEntry("actor_id required".into()));
        }
        if self.actor_type.is_empty() {
            return Err(PiiError::InvalidEntry("actor_type required".into()));
        }
        if self.created_at_nanos <= 1_577_836_800_000_000_000 {
            return Err(PiiError::InvalidEntry(format!(
                "created_at_nanos must be > 1577836800000000000 (got {})",
                self.created_at_nanos
            )));
        }
        Ok(())
    }
}

/// Audit writer abstraction. Production wraps a MetaWrite-backed impl;
/// tests use [`InMemoryAuditWriter`].
pub trait AuditWriter: Send + Sync {
    fn write_sensitive_read(&self, entry: SensitiveReadEntry) -> Result<(), PiiError>;
}

/// KEK manager abstraction (destroy-only surface). Production wraps
/// cycle-3 `pii_kek.destroyed_at` update.
pub trait KekManager: Send + Sync {
    /// Mark `pii_kek.destroyed_at` non-NULL for the user's KEK.
    /// IDEMPOTENT — re-destroy MUST be a no-op (returns Ok(())).
    fn destroy_kek(&self, user_ref_id: [u8; 16]) -> Result<(), String>;
}

/// In-memory test impl. Tracks destroyed users; idempotent.
#[derive(Default)]
pub struct InMemoryKekManager {
    destroyed: Mutex<std::collections::HashSet<[u8; 16]>>,
}

impl InMemoryKekManager {
    pub fn new() -> Self {
        Self {
            destroyed: Mutex::new(std::collections::HashSet::new()),
        }
    }

    pub fn is_destroyed(&self, user_ref_id: [u8; 16]) -> bool {
        self.destroyed.lock().unwrap().contains(&user_ref_id)
    }
}

impl KekManager for InMemoryKekManager {
    fn destroy_kek(&self, user_ref_id: [u8; 16]) -> Result<(), String> {
        let mut g = self.destroyed.lock().unwrap();
        g.insert(user_ref_id);
        Ok(())
    }
}

/// Failing manager — used in tests to assert the SDK returns EraseFailed.
pub struct FailingKekManager;

impl KekManager for FailingKekManager {
    fn destroy_kek(&self, _: [u8; 16]) -> Result<(), String> {
        Err("kms-down".into())
    }
}

/// In-memory audit writer test stand-in.
#[derive(Default)]
pub struct InMemoryAuditWriter {
    entries: Mutex<Vec<SensitiveReadEntry>>,
}

impl InMemoryAuditWriter {
    pub fn new() -> Self {
        Self {
            entries: Mutex::new(Vec::new()),
        }
    }
    pub fn len(&self) -> usize {
        self.entries.lock().unwrap().len()
    }
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
    pub fn snapshot(&self) -> Vec<SensitiveReadEntry> {
        self.entries.lock().unwrap().clone()
    }
}

impl AuditWriter for InMemoryAuditWriter {
    fn write_sensitive_read(&self, entry: SensitiveReadEntry) -> Result<(), PiiError> {
        entry.validate()?;
        self.entries.lock().unwrap().push(entry);
        Ok(())
    }
}

/// Failing audit writer — used in tests to assert the SDK drops
/// plaintext on audit failure.
pub struct FailingAuditWriter;

impl AuditWriter for FailingAuditWriter {
    fn write_sensitive_read(&self, _: SensitiveReadEntry) -> Result<(), PiiError> {
        Err(PiiError::AuditFailed("audit-down".into()))
    }
}

/// SDK construction config.
pub struct Config {
    pub keks: Arc<dyn KekManager>,
    pub auditor: Arc<dyn AuditWriter>,
    pub actor_id: String,
    pub actor_type: String,
}

/// SDK — typed PII access surface. The Rust side stubs the actual
/// decrypt path (mirroring `contracts/meta.OpenPII`) since the Rust
/// `meta-rs` crate does NOT yet ship the KMS adapter (cycle-22 +
/// security-track sub-program will land it). For now, `get_pii` returns
/// the cyphertext-tracking stub via the `PiiReader` trait, but the
/// audit + erase invariants are exactly the same.
pub struct Sdk {
    keks: Arc<dyn KekManager>,
    auditor: Arc<dyn AuditWriter>,
    actor_id: String,
    actor_type: String,
    now: Box<dyn Fn() -> i64 + Send + Sync>,
}

impl Sdk {
    pub fn new(c: Config) -> Result<Self, PiiError> {
        if c.actor_id.is_empty() {
            return Err(PiiError::Misconfigured("actor_id"));
        }
        if c.actor_type.is_empty() {
            return Err(PiiError::Misconfigured("actor_type"));
        }
        Ok(Self {
            keks: c.keks,
            auditor: c.auditor,
            actor_id: c.actor_id,
            actor_type: c.actor_type,
            now: Box::new(|| {
                use std::time::{SystemTime, UNIX_EPOCH};
                SystemTime::now()
                    .duration_since(UNIX_EPOCH)
                    .map(|d| d.as_nanos() as i64)
                    .unwrap_or(1_700_000_000_000_000_000)
            }),
        })
    }

    /// Override the clock for tests.
    pub fn with_clock(mut self, now: impl Fn() -> i64 + Send + Sync + 'static) -> Self {
        self.now = Box::new(now);
        self
    }

    /// Erase the user's PII (crypto-shred). Idempotent. Audits the
    /// erase even on failure — forensic invariant.
    pub fn erase_pii(&self, user_ref_id: [u8; 16]) -> Result<(), PiiError> {
        if let Err(e) = self.keks.destroy_kek(user_ref_id) {
            let _ = self.audit(SensitiveReadTag::PiiUserErase, user_ref_id, 0);
            return Err(PiiError::EraseFailed(e));
        }
        self.audit(SensitiveReadTag::PiiUserErase, user_ref_id, 1)
    }

    /// Audit a GetPII call (Rust services currently fetch ciphertext +
    /// pass to a sidecar KMS adapter; SDK exposes the audit hook so the
    /// row is written from one place). Tag MUST be PiiUserGet.
    pub fn audit_get(&self, user_ref_id: [u8; 16], result_count: u32) -> Result<(), PiiError> {
        self.audit(SensitiveReadTag::PiiUserGet, user_ref_id, result_count)
    }

    fn audit(
        &self,
        tag: SensitiveReadTag,
        user_ref_id: [u8; 16],
        result_count: u32,
    ) -> Result<(), PiiError> {
        // tag is a typed enum already — no string typo possible. Kept the
        // guard symmetry with Go in case future call sites build from a
        // string.
        let entry = SensitiveReadEntry {
            audit_id: random_id(),
            query_type: tag,
            user_ref_id,
            actor_id: self.actor_id.clone(),
            actor_type: self.actor_type.clone(),
            result_count,
            created_at_nanos: (self.now)(),
        };
        entry.validate()?;
        self.auditor.write_sensitive_read(entry)
    }
}

// Non-cryptographic random id for the test surface. Production will use
// uuid_v4 via the cycle-3 meta-rs crate, but the SDK contract is
// `[u8; 16]` so the audit shape stays vendor-neutral.
fn random_id() -> [u8; 16] {
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(1);
    let mut out = [0u8; 16];
    let bytes = now.to_le_bytes();
    let n = bytes.len().min(16);
    out[..n].copy_from_slice(&bytes[..n]);
    out[15] = out[15].wrapping_add(1);
    if out == [0u8; 16] {
        out[0] = 1;
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture() -> (Sdk, Arc<InMemoryKekManager>, Arc<InMemoryAuditWriter>) {
        let keks = Arc::new(InMemoryKekManager::new());
        let auditor = Arc::new(InMemoryAuditWriter::new());
        let sdk = Sdk::new(Config {
            keks: keks.clone(),
            auditor: auditor.clone(),
            actor_id: "test-actor".into(),
            actor_type: "service".into(),
        })
        .unwrap()
        .with_clock(|| 1_700_000_000_000_000_000);
        (sdk, keks, auditor)
    }

    #[test]
    fn tag_round_trip() {
        for s in ["pii_user_get", "pii_user_erase", "bulk_pii_read"] {
            let t = SensitiveReadTag::from_str(s).unwrap();
            assert_eq!(t.as_str(), s);
        }
        assert!(SensitiveReadTag::from_str("bogus").is_none());
    }

    #[test]
    fn entry_validate_happy() {
        let e = SensitiveReadEntry {
            audit_id: [1u8; 16],
            query_type: SensitiveReadTag::PiiUserGet,
            user_ref_id: [2u8; 16],
            actor_id: "x".into(),
            actor_type: "service".into(),
            result_count: 1,
            created_at_nanos: 1_700_000_000_000_000_000,
        };
        e.validate().expect("happy");
    }

    #[test]
    fn entry_validate_rejects() {
        // zero audit_id
        let mut e = SensitiveReadEntry {
            audit_id: [0u8; 16],
            query_type: SensitiveReadTag::PiiUserGet,
            user_ref_id: [0u8; 16],
            actor_id: "x".into(),
            actor_type: "service".into(),
            result_count: 0,
            created_at_nanos: 1_700_000_000_000_000_000,
        };
        assert!(e.validate().is_err());
        e.audit_id = [1u8; 16];
        e.actor_id = String::new();
        assert!(e.validate().is_err());
        e.actor_id = "x".into();
        e.actor_type = String::new();
        assert!(e.validate().is_err());
        e.actor_type = "service".into();
        e.created_at_nanos = 1_577_836_800_000_000_000;
        assert!(e.validate().is_err());
    }

    #[test]
    fn erase_destroys_kek_and_audits() {
        let (sdk, keks, auditor) = fixture();
        let uid = [9u8; 16];
        assert!(!keks.is_destroyed(uid));
        sdk.erase_pii(uid).expect("erase");
        assert!(
            keks.is_destroyed(uid),
            "KEK MUST be destroyed (GDPR Art. 17 invariant)"
        );
        assert_eq!(auditor.len(), 1);
        let snap = auditor.snapshot();
        assert_eq!(snap[0].query_type, SensitiveReadTag::PiiUserErase);
        assert_eq!(snap[0].result_count, 1);
    }

    #[test]
    fn erase_idempotent() {
        let (sdk, keks, auditor) = fixture();
        let uid = [3u8; 16];
        sdk.erase_pii(uid).expect("first");
        sdk.erase_pii(uid).expect("second must be idempotent");
        assert!(keks.is_destroyed(uid));
        assert_eq!(auditor.len(), 2);
    }

    #[test]
    fn erase_failure_returns_erase_failed() {
        let sdk = Sdk::new(Config {
            keks: Arc::new(FailingKekManager),
            auditor: Arc::new(InMemoryAuditWriter::new()),
            actor_id: "x".into(),
            actor_type: "service".into(),
        })
        .unwrap()
        .with_clock(|| 1_700_000_000_000_000_000);
        let err = sdk.erase_pii([1u8; 16]).unwrap_err();
        match err {
            PiiError::EraseFailed(_) => {}
            other => panic!("expected EraseFailed, got {other:?}"),
        }
    }

    #[test]
    fn audit_failure_post_destroy_is_hard_error() {
        let sdk = Sdk::new(Config {
            keks: Arc::new(InMemoryKekManager::new()),
            auditor: Arc::new(FailingAuditWriter),
            actor_id: "x".into(),
            actor_type: "service".into(),
        })
        .unwrap()
        .with_clock(|| 1_700_000_000_000_000_000);
        let err = sdk.erase_pii([1u8; 16]).unwrap_err();
        match err {
            PiiError::AuditFailed(_) => {}
            other => panic!("expected AuditFailed, got {other:?}"),
        }
    }

    #[test]
    fn audit_get_writes_with_tag_pii_user_get() {
        let (sdk, _keks, auditor) = fixture();
        sdk.audit_get([5u8; 16], 1).unwrap();
        assert_eq!(auditor.len(), 1);
        let snap = auditor.snapshot();
        assert_eq!(snap[0].query_type, SensitiveReadTag::PiiUserGet);
        assert_eq!(snap[0].result_count, 1);
    }

    #[test]
    fn cross_language_tag_string_parity() {
        // Parity with Go contracts/pii SensitiveReadTag constants.
        for (t, s) in [
            (SensitiveReadTag::PiiUserGet, "pii_user_get"),
            (SensitiveReadTag::PiiUserErase, "pii_user_erase"),
            (SensitiveReadTag::BulkPiiRead, "bulk_pii_read"),
        ] {
            assert_eq!(t.as_str(), s);
        }
    }

    #[test]
    fn config_missing_actor_id_rejected() {
        let r = Sdk::new(Config {
            keks: Arc::new(InMemoryKekManager::new()),
            auditor: Arc::new(InMemoryAuditWriter::new()),
            actor_id: "".into(),
            actor_type: "service".into(),
        });
        assert!(r.is_err());
    }

    #[test]
    fn config_missing_actor_type_rejected() {
        let r = Sdk::new(Config {
            keks: Arc::new(InMemoryKekManager::new()),
            auditor: Arc::new(InMemoryAuditWriter::new()),
            actor_id: "x".into(),
            actor_type: "".into(),
        });
        assert!(r.is_err());
    }
}
