//! L4.C — Cache contract mirror of `contracts/meta/cache.go`.
//!
//! Same `KeyKind` enum, same `lw:<kind>:<scope>` wire format, same TTL
//! invariant (must be > 0; cap 24h to force event-driven invalidation for
//! anything longer). Production Redis impl lands alongside the Rust kernel's
//! redis wiring; this crate ships the trait + registry + an `InMemoryCache`
//! test fake (matches the Go side's split).

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::time::{Duration, Instant};
use std::sync::Mutex;

use crate::errors::MetaError;

/// Opaque cached bytes. Callers serialize / deserialize themselves so this
/// stays codec-agnostic (matches Go `CacheValue`).
pub type CacheValue = Vec<u8>;

/// Enumerated cache-key namespaces. Mirrors `cache.go::KeyKind`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum KeyKind {
    /// `RealityRouting` row.
    RealityRouting,
    /// Per-reality entity status read.
    EntityStatus,
    /// Sensitive-paths registry (parsed YAML).
    SensitivePaths,
    /// Per-reality canon snapshot (cycle 23 placeholder).
    CanonProjection,
}

impl KeyKind {
    /// Canonical snake_case string form (matches Postgres value + Redis key
    /// component).
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::RealityRouting => "reality_routing",
            Self::EntityStatus => "entity_status",
            Self::SensitivePaths => "sensitive_paths",
            Self::CanonProjection => "canon_projection",
        }
    }
}

/// Strongly-typed cache key with wire format `lw:<kind>:<scope>`.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct Key {
    /// Namespace kind.
    pub kind: KeyKind,
    /// Scope value (usually a reality_id or `"global"`).
    pub scope: String,
}

impl Key {
    /// Wire format.
    pub fn as_string(&self) -> String {
        format!("lw:{}:{}", self.kind.as_str(), self.scope)
    }
}

/// One row from `contracts/cache/keys.yaml`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct KeyEntry {
    /// Kind this entry registers.
    pub kind: KeyKind,
    /// Lookup TTL (> 0; <= 24h).
    pub ttl: Duration,
    /// Event name that invalidates this kind (empty = TTL-only).
    pub invalidation_trigger: String,
    /// Owning service (for CODEOWNERS routing).
    pub owner_service: String,
    /// Optional cross-link to a sensitive-paths id.
    pub sensitive_path_id: String,
}

/// In-memory key registry. Validates entries on construction.
#[derive(Debug, Clone)]
pub struct KeyRegistry {
    entries: HashMap<KeyKind, KeyEntry>,
}

impl KeyRegistry {
    /// Construct from a list of entries. Enforces:
    /// - No duplicate kinds.
    /// - TTL > 0 (matches Go 60s fallback rule).
    /// - TTL <= 24h (longer requires event-driven).
    pub fn new(entries: Vec<KeyEntry>) -> Result<Self, MetaError> {
        let mut out = HashMap::with_capacity(entries.len());
        for (i, e) in entries.into_iter().enumerate() {
            if e.ttl.is_zero() {
                return Err(MetaError::ConfigInvalid(format!(
                    "entry {i}: kind {:?} ttl must be > 0",
                    e.kind
                )));
            }
            if e.ttl > Duration::from_secs(24 * 3600) {
                return Err(MetaError::ConfigInvalid(format!(
                    "entry {i}: kind {:?} ttl exceeds 24h (use event-driven invalidation)",
                    e.kind
                )));
            }
            if out.contains_key(&e.kind) {
                return Err(MetaError::ConfigInvalid(format!(
                    "duplicate kind {:?}",
                    e.kind
                )));
            }
            out.insert(e.kind, e);
        }
        Ok(KeyRegistry { entries: out })
    }

    /// Lookup by kind. Returns [`MetaError::ConfigInvalid`] when the kind isn't
    /// registered (callers should treat this as a programmer error).
    pub fn lookup(&self, kind: KeyKind) -> Result<&KeyEntry, MetaError> {
        self.entries.get(&kind).ok_or_else(|| {
            MetaError::ConfigInvalid(format!("cache kind {kind:?} not registered"))
        })
    }

    /// All registered kinds (unsorted).
    pub fn kinds(&self) -> Vec<KeyKind> {
        self.entries.keys().copied().collect()
    }
}

/// Cache read/write surface. Matches `contracts/meta/cache.go::Cache`
/// 1:1 (Get / Set / Del / DelByPrefix).
pub trait Cache: Send + Sync {
    /// Returns `Ok(Some(value))` on hit, `Ok(None)` on clean miss.
    fn get(&self, key: &str) -> Result<Option<CacheValue>, MetaError>;
    /// Stores `value` under `key` with TTL. TTL > 0 required.
    fn set(&self, key: &str, value: CacheValue, ttl: Duration) -> Result<(), MetaError>;
    /// Removes `key` (idempotent).
    fn del(&self, key: &str) -> Result<(), MetaError>;
    /// Removes every key whose name starts with `prefix`. Returns count.
    fn del_by_prefix(&self, prefix: &str) -> Result<usize, MetaError>;
}

/// Test/dev fake implementation of [`Cache`]. Production code wires Redis.
#[derive(Debug, Default)]
pub struct InMemoryCache {
    inner: Mutex<HashMap<String, InMemEntry>>,
}

#[derive(Debug, Clone)]
struct InMemEntry {
    value: CacheValue,
    expires_at: Instant,
}

impl InMemoryCache {
    /// Construct an empty cache.
    pub fn new() -> Self {
        Self::default()
    }
}

impl Cache for InMemoryCache {
    fn get(&self, key: &str) -> Result<Option<CacheValue>, MetaError> {
        let mut g = self.inner.lock().unwrap();
        if let Some(e) = g.get(key).cloned() {
            if Instant::now() > e.expires_at {
                g.remove(key);
                return Ok(None);
            }
            return Ok(Some(e.value));
        }
        Ok(None)
    }

    fn set(&self, key: &str, value: CacheValue, ttl: Duration) -> Result<(), MetaError> {
        if ttl.is_zero() {
            return Err(MetaError::ConfigInvalid("ttl must be > 0".into()));
        }
        let mut g = self.inner.lock().unwrap();
        g.insert(
            key.to_string(),
            InMemEntry {
                value,
                expires_at: Instant::now() + ttl,
            },
        );
        Ok(())
    }

    fn del(&self, key: &str) -> Result<(), MetaError> {
        self.inner.lock().unwrap().remove(key);
        Ok(())
    }

    fn del_by_prefix(&self, prefix: &str) -> Result<usize, MetaError> {
        let mut g = self.inner.lock().unwrap();
        let keys: Vec<String> = g
            .keys()
            .filter(|k| k.starts_with(prefix))
            .cloned()
            .collect();
        let n = keys.len();
        for k in keys {
            g.remove(&k);
        }
        Ok(n)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::thread::sleep;

    #[test]
    fn key_wire_format() {
        let k = Key {
            kind: KeyKind::RealityRouting,
            scope: "abc".into(),
        };
        assert_eq!(k.as_string(), "lw:reality_routing:abc");
    }

    #[test]
    fn registry_rejects_zero_ttl() {
        let err = KeyRegistry::new(vec![KeyEntry {
            kind: KeyKind::RealityRouting,
            ttl: Duration::from_secs(0),
            invalidation_trigger: "".into(),
            owner_service: "world".into(),
            sensitive_path_id: "".into(),
        }])
        .unwrap_err();
        assert!(matches!(err, MetaError::ConfigInvalid(ref m) if m.contains("ttl")));
    }

    #[test]
    fn registry_rejects_ttl_over_24h() {
        let err = KeyRegistry::new(vec![KeyEntry {
            kind: KeyKind::RealityRouting,
            ttl: Duration::from_secs(25 * 3600),
            invalidation_trigger: "".into(),
            owner_service: "world".into(),
            sensitive_path_id: "".into(),
        }])
        .unwrap_err();
        assert!(matches!(err, MetaError::ConfigInvalid(ref m) if m.contains("24h")));
    }

    #[test]
    fn registry_rejects_duplicate_kind() {
        let entry = KeyEntry {
            kind: KeyKind::RealityRouting,
            ttl: Duration::from_secs(30),
            invalidation_trigger: "".into(),
            owner_service: "world".into(),
            sensitive_path_id: "".into(),
        };
        let err = KeyRegistry::new(vec![entry.clone(), entry]).unwrap_err();
        assert!(matches!(err, MetaError::ConfigInvalid(ref m) if m.contains("duplicate")));
    }

    #[test]
    fn in_memory_cache_get_set_del() {
        let c = InMemoryCache::new();
        c.set("k1", b"v1".to_vec(), Duration::from_secs(60)).unwrap();
        let v = c.get("k1").unwrap().unwrap();
        assert_eq!(v, b"v1");
        c.del("k1").unwrap();
        assert!(c.get("k1").unwrap().is_none());
    }

    #[test]
    fn in_memory_cache_ttl_expires() {
        let c = InMemoryCache::new();
        c.set("k1", b"v1".to_vec(), Duration::from_millis(50)).unwrap();
        sleep(Duration::from_millis(100));
        assert!(c.get("k1").unwrap().is_none());
    }

    #[test]
    fn in_memory_cache_del_by_prefix() {
        let c = InMemoryCache::new();
        c.set("lw:reality_routing:a", b"1".to_vec(), Duration::from_secs(60)).unwrap();
        c.set("lw:reality_routing:b", b"2".to_vec(), Duration::from_secs(60)).unwrap();
        c.set("lw:entity_status:x", b"3".to_vec(), Duration::from_secs(60)).unwrap();
        let n = c.del_by_prefix("lw:reality_routing:").unwrap();
        assert_eq!(n, 2);
        assert!(c.get("lw:reality_routing:a").unwrap().is_none());
        assert!(c.get("lw:entity_status:x").unwrap().is_some());
    }
}
