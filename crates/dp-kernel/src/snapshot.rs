//! L4.A — `Snapshot` trait.
//!
//! ## Scope distinction (vs cycle 12)
//!
//! Cycle 12 shipped two snapshot-related symbols:
//!
//! - [`crate::load_aggregate::SnapshotStore`] — I/O abstraction over the
//!   `aggregate_snapshots` table (LATEST-snapshot SELECT).
//! - [`crate::load_aggregate::SnapshotRecord`] — the row shape.
//!
//! L4.A adds [`Snapshot`] — the **encoder/decoder** half of the equation.
//! Where cycle-12 talks about "where does the snapshot live" (the STORE),
//! L4.A talks about "how does the aggregate become snapshot bytes + back"
//! (the SHAPE on disk).
//!
//! Together the three live happily side-by-side:
//!
//! ```text
//!   Aggregate (cycle 12)  --serialize-->  Snapshot bytes (L4.A)
//!                                              |
//!                                              v
//!                                      SnapshotStore (cycle 12) -> Postgres row
//! ```
//!
//! ## Why not just `serde::Serialize` directly?
//!
//! Most aggregates ARE `Serialize + DeserializeOwned` and cycle 12's loader
//! already exploits that via `serde_json::to_value` round-trips. But L4.A
//! formalizes the schema-version pin: when an aggregate's snapshot shape
//! changes, the loader must be able to distinguish "old shape" vs "new
//! shape" payloads in the `aggregate_snapshots` table. [`Snapshot::version`]
//! is the explicit version field; the loader (cycle 14+) checks it before
//! deserializing.
//!
//! Default impl: `version() = 1` — most aggregates never bump, and writing
//! `Snapshot::version(_) -> 1` exhaustively at every implementor is noise.

use serde::{de::DeserializeOwned, Serialize};

use crate::load_aggregate::Aggregate;

/// Encoder/decoder for an aggregate's snapshot bytes. Default impls use
/// JSON via `serde_json` — concrete types only override when they need a
/// custom format (e.g. CBOR for large aggregates) or a non-1 schema version.
pub trait Snapshot: Aggregate + Serialize + DeserializeOwned {
    /// Snapshot schema version. Bump when the SHAPE of the aggregate's
    /// serialized form changes (NOT when business logic in `apply` changes).
    fn version() -> u32
    where
        Self: Sized,
    {
        1
    }

    /// Serialize the aggregate state to bytes. Default: `serde_json::to_vec`.
    /// Implementors can override (e.g. `bincode`, `cbor4ii`) when the
    /// snapshot row is hot enough to warrant a non-JSON format.
    fn to_snapshot_bytes(&self) -> Result<Vec<u8>, String> {
        serde_json::to_vec(self).map_err(|e| e.to_string())
    }

    /// Inverse of [`Self::to_snapshot_bytes`]. Default: `serde_json::from_slice`.
    fn from_snapshot_bytes(bytes: &[u8]) -> Result<Self, String>
    where
        Self: Sized,
    {
        serde_json::from_slice(bytes).map_err(|e| e.to_string())
    }

    /// JSON-Value convenience — useful because cycle 12's
    /// `SnapshotRecord.snapshot_data` is `serde_json::Value`, so callers that
    /// go through that path don't need bytes.
    fn to_snapshot_value(&self) -> Result<serde_json::Value, String> {
        serde_json::to_value(self).map_err(|e| e.to_string())
    }

    /// JSON-Value inverse.
    fn from_snapshot_value(v: &serde_json::Value) -> Result<Self, String>
    where
        Self: Sized,
    {
        serde_json::from_value(v.clone()).map_err(|e| e.to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::envelope::EventEnvelope;
    use serde::Deserialize;
    use serde_json::json;
    use uuid::Uuid;

    #[derive(Default, Serialize, Deserialize, Debug, PartialEq, Eq)]
    struct Counter {
        value: i64,
        version: u64,
    }

    impl Aggregate for Counter {
        fn apply(&mut self, env: &EventEnvelope) -> Result<(), String> {
            self.value += env
                .payload
                .get("delta")
                .and_then(|v| v.as_i64())
                .ok_or_else(|| "missing 'delta'".to_string())?;
            self.version = env.aggregate_version;
            Ok(())
        }
        fn aggregate_version(&self) -> u64 {
            self.version
        }
    }

    // Default Snapshot impl: JSON + version 1.
    impl Snapshot for Counter {}

    fn env(delta: i64, ver: u64) -> EventEnvelope {
        EventEnvelope {
            event_id: Uuid::from_u128(ver as u128),
            event_type: "counter.incremented".into(),
            event_version: 1,
            aggregate_id: "c-1".into(),
            aggregate_type: "counter".into(),
            aggregate_version: ver,
            reality_id: Uuid::from_u128(1),
            occurred_at: "2026-05-29T00:00:00Z".into(),
            recorded_at: "2026-05-29T00:00:00Z".into(),
            payload: json!({ "delta": delta }),
            metadata: None,
        }
    }

    #[test]
    fn snapshot_bytes_round_trip() {
        let mut c = Counter::default();
        c.apply(&env(5, 1)).unwrap();
        c.apply(&env(7, 2)).unwrap();
        let bytes = c.to_snapshot_bytes().unwrap();
        let back = Counter::from_snapshot_bytes(&bytes).unwrap();
        assert_eq!(c, back);
    }

    #[test]
    fn snapshot_value_round_trip_matches_cycle12_loader() {
        let c = Counter { value: 42, version: 7 };
        let v = c.to_snapshot_value().unwrap();
        // Compatible with cycle 12 SnapshotRecord.snapshot_data shape.
        let back = Counter::from_snapshot_value(&v).unwrap();
        assert_eq!(c, back);
    }

    #[test]
    fn default_version_is_one() {
        assert_eq!(<Counter as Snapshot>::version(), 1);
    }

    // Custom snapshot version + custom encoder.
    #[derive(Default, Serialize, Deserialize, Debug, PartialEq, Eq)]
    struct Big {
        version: u64,
        rows: Vec<u64>,
    }
    impl Aggregate for Big {
        fn apply(&mut self, _env: &EventEnvelope) -> Result<(), String> {
            Ok(())
        }
        fn aggregate_version(&self) -> u64 {
            self.version
        }
    }
    impl Snapshot for Big {
        fn version() -> u32 {
            3
        }
        // Use a fake "binary" encoding (just JSON with a magic header) to
        // prove overrides compose with the default helpers.
        fn to_snapshot_bytes(&self) -> Result<Vec<u8>, String> {
            let mut out = b"BIG\0".to_vec();
            out.extend(serde_json::to_vec(self).map_err(|e| e.to_string())?);
            Ok(out)
        }
        fn from_snapshot_bytes(bytes: &[u8]) -> Result<Self, String> {
            if !bytes.starts_with(b"BIG\0") {
                return Err("missing BIG magic".into());
            }
            serde_json::from_slice(&bytes[4..]).map_err(|e| e.to_string())
        }
    }

    #[test]
    fn custom_version_and_encoder_round_trip() {
        let b = Big { version: 5, rows: vec![1, 2, 3] };
        let bytes = b.to_snapshot_bytes().unwrap();
        assert!(bytes.starts_with(b"BIG\0"));
        let back = Big::from_snapshot_bytes(&bytes).unwrap();
        assert_eq!(b, back);
        assert_eq!(<Big as Snapshot>::version(), 3);
    }
}
