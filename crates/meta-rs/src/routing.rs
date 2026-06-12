//! Routing read path.  Hot-path entry point for the Rust kernel.

use serde::{Deserialize, Serialize};
use std::str::FromStr;
use uuid::Uuid;

use crate::errors::MetaError;

/// `RealityStatus` mirrors the `reality_registry.status` CHECK enum from
/// `migrations/meta/001_reality_registry.up.sql`.
///
/// Centralized so Rust callers can match without re-encoding the string set.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RealityStatus {
    /// reality is being provisioned (DB created, but not yet seeded)
    Provisioning,
    /// reality is being seeded with starter data
    Seeding,
    /// reality is live, accepting commands
    Active,
    /// reality close has been requested but not yet finalized
    PendingClose,
    /// reality is frozen — no new commands accepted
    Frozen,
    /// reality is undergoing schema migration
    Migrating,
    /// reality has been archived (data exported)
    Archived,
    /// archive has passed 5-step verification (R9 §12I.3)
    ArchivedVerified,
    /// reality is soft-deleted (drop scheduled)
    SoftDeleted,
    /// reality has been hard-dropped (terminal)
    Dropped,
}

impl FromStr for RealityStatus {
    type Err = MetaError;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "provisioning" => Ok(Self::Provisioning),
            "seeding" => Ok(Self::Seeding),
            "active" => Ok(Self::Active),
            "pending_close" => Ok(Self::PendingClose),
            "frozen" => Ok(Self::Frozen),
            "migrating" => Ok(Self::Migrating),
            "archived" => Ok(Self::Archived),
            "archived_verified" => Ok(Self::ArchivedVerified),
            "soft_deleted" => Ok(Self::SoftDeleted),
            "dropped" => Ok(Self::Dropped),
            other => Err(MetaError::ConfigInvalid(format!(
                "unknown reality status: {other}"
            ))),
        }
    }
}

impl RealityStatus {
    /// Returns the canonical lowercase string form (matches Postgres value).
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Provisioning => "provisioning",
            Self::Seeding => "seeding",
            Self::Active => "active",
            Self::PendingClose => "pending_close",
            Self::Frozen => "frozen",
            Self::Migrating => "migrating",
            Self::Archived => "archived",
            Self::ArchivedVerified => "archived_verified",
            Self::SoftDeleted => "soft_deleted",
            Self::Dropped => "dropped",
        }
    }
}

/// `RealityRouting` is the routing-table row Rust callers actually need.
///
/// Returned by `MetaRead::get_reality_routing`.  Cached for 30 s in Redis per
/// C03 §12O.6 — caching wrapper ships alongside the Redis infra in a later
/// cycle.  This crate intentionally has no Redis dependency yet.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RealityRouting {
    /// Primary key.
    pub reality_id: Uuid,
    /// Physical Postgres host (matches `db_host` CHECK regex).
    pub db_host: String,
    /// Per-reality database name.
    pub db_name: String,
    /// Reality's current lifecycle status.
    pub status: RealityStatus,
    /// BCP-47 short form (en, en-US, ja-JP, ...).
    pub locale: String,
    /// Canary cohort 0..=99 (SR05 §12AH.4).
    pub deploy_cohort: u8,
}

impl RealityRouting {
    /// Returns true if the reality is in a status that accepts user commands.
    /// Convenience accessor for the hot-path command router.
    pub fn accepts_commands(&self) -> bool {
        matches!(
            self.status,
            RealityStatus::Active | RealityStatus::PendingClose
        )
    }
}

/// `Connection` abstracts the backend so callers can swap pgx, sqlx, or a
/// mock implementation without changing trait implementors of `MetaRead`.
///
/// Cycle 2 ships the trait only; concrete pgx/sqlx implementations follow
/// in the Rust-services cycle that adopts this crate.
pub trait Connection: Send + Sync {
    /// Fetch one `RealityRouting` row by `reality_id`.
    fn fetch_reality_routing(
        &self,
        reality_id: Uuid,
    ) -> Result<Option<RealityRouting>, MetaError>;
}

/// `MetaRead` is the public hot-path read surface.
///
/// Cycle 2 exposes only `get_reality_routing` — additional readers
/// (entity_status, consent) land in later cycles alongside their tables.
pub trait MetaRead {
    /// Resolve a reality_id to its physical routing record.  Returns
    /// `Ok(None)` if the reality is unknown (caller decides whether that's an
    /// error in context).
    fn get_reality_routing(
        &self,
        reality_id: Uuid,
    ) -> Result<Option<RealityRouting>, MetaError>;
}

/// `DefaultMetaRead` adapts a `Connection` into the public `MetaRead` trait
/// with no extra behavior beyond pass-through.  Callers that want caching
/// wrap this in a higher-level type.
pub struct DefaultMetaRead<C: Connection> {
    conn: C,
}

impl<C: Connection> DefaultMetaRead<C> {
    /// Construct a `DefaultMetaRead` over the supplied backend.
    pub fn new(conn: C) -> Self {
        Self { conn }
    }
}

impl<C: Connection> MetaRead for DefaultMetaRead<C> {
    fn get_reality_routing(
        &self,
        reality_id: Uuid,
    ) -> Result<Option<RealityRouting>, MetaError> {
        self.conn.fetch_reality_routing(reality_id)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;

    struct MockConn {
        // Vec so we can assert call order; Mutex for interior mutability.
        calls: Mutex<Vec<Uuid>>,
        // None => simulate "not found"; Some => return clone
        row: Option<RealityRouting>,
    }

    impl Connection for MockConn {
        fn fetch_reality_routing(
            &self,
            reality_id: Uuid,
        ) -> Result<Option<RealityRouting>, MetaError> {
            self.calls.lock().unwrap().push(reality_id);
            Ok(self.row.clone())
        }
    }

    #[test]
    fn reality_status_round_trip() {
        for s in [
            "provisioning",
            "seeding",
            "active",
            "pending_close",
            "frozen",
            "migrating",
            "archived",
            "archived_verified",
            "soft_deleted",
            "dropped",
        ] {
            let parsed: RealityStatus = s.parse().unwrap();
            assert_eq!(parsed.as_str(), s);
        }
    }

    #[test]
    fn reality_status_unknown_rejects() {
        let err = "exploded".parse::<RealityStatus>().unwrap_err();
        assert!(matches!(err, MetaError::ConfigInvalid(_)));
    }

    #[test]
    fn accepts_commands_only_in_active_states() {
        let mut r = RealityRouting {
            reality_id: Uuid::nil(),
            db_host: "pg-shard-0.internal".into(),
            db_name: "lw_reality_0".into(),
            status: RealityStatus::Active,
            locale: "en-US".into(),
            deploy_cohort: 0,
        };
        assert!(r.accepts_commands());
        r.status = RealityStatus::PendingClose;
        assert!(r.accepts_commands());
        for s in [
            RealityStatus::Provisioning,
            RealityStatus::Seeding,
            RealityStatus::Frozen,
            RealityStatus::Migrating,
            RealityStatus::Archived,
            RealityStatus::ArchivedVerified,
            RealityStatus::SoftDeleted,
            RealityStatus::Dropped,
        ] {
            r.status = s;
            assert!(!r.accepts_commands(), "{s:?} must not accept commands");
        }
    }

    #[test]
    fn default_meta_read_passthrough() {
        let row = RealityRouting {
            reality_id: Uuid::from_u128(0xdead_beef),
            db_host: "pg-shard-0.internal".into(),
            db_name: "lw_reality_0".into(),
            status: RealityStatus::Active,
            locale: "en-US".into(),
            deploy_cohort: 7,
        };
        let mock = MockConn {
            calls: Mutex::new(Vec::new()),
            row: Some(row.clone()),
        };
        let reader = DefaultMetaRead::new(mock);
        let got = reader
            .get_reality_routing(row.reality_id)
            .expect("ok")
            .expect("some");
        assert_eq!(got, row);
    }

    #[test]
    fn default_meta_read_not_found() {
        let mock = MockConn {
            calls: Mutex::new(Vec::new()),
            row: None,
        };
        let reader = DefaultMetaRead::new(mock);
        let got = reader.get_reality_routing(Uuid::nil()).expect("ok");
        assert!(got.is_none());
    }
}
