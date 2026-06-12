//! L4.A — `AggregateMeta` extension trait on top of the cycle-12
//! [`crate::load_aggregate::Aggregate`] trait.
//!
//! ## Why a new trait instead of editing cycle 12's?
//!
//! Cycle 12 (`load_aggregate.rs`) shipped `Aggregate { apply, aggregate_version }`
//! as the contract callers depend on (snapshot loader, projections, rebuilder
//! across cycles 13+14). That signature is the CANONICAL one — we re-export
//! it here unchanged.
//!
//! L4.A wants two more accessors (`aggregate_type()` + `id()`) so the
//! generated `#[derive(Aggregate)]` macro (L4.B) can emit a value-shaped
//! identity for hashing / metrics. We supply them via a SEPARATE extension
//! trait so the cycle-12 `Aggregate` callers remain untouched and don't have
//! to satisfy the new methods.
//!
//! Concrete types CAN implement both — the `#[derive(Aggregate)]` macro will
//! emit BOTH impls when applied to a struct, so callers get the full surface.
//!
//! ## What ships in cycle 17
//!
//! 1. Re-export of cycle 12's [`crate::load_aggregate::Aggregate`] at
//!    `crate::aggregate::Aggregate` — single canonical path going forward.
//! 2. [`AggregateMeta`] — additive trait providing `aggregate_type` + `id`.
//! 3. Tests demonstrating that a struct can implement both at once and that
//!    the cycle-12 traits remain unaffected.
//!
//! ## What does NOT ship here
//!
//! - `Aggregate::aggregate_type()` / `Aggregate::id()` as REQUIRED methods on
//!   the cycle-12 trait. That would force cycle-13 callers (5 projection
//!   crates) to implement them, breaking semver. The whole point of the
//!   `AggregateMeta` split is to avoid that.

pub use crate::load_aggregate::Aggregate;

/// Extension surface added in L4.A. Carries the type + id accessors that
/// the macro emits.
///
/// `#[derive(Aggregate)]` from `dp-kernel-macros` implements BOTH this trait
/// AND [`Aggregate`] in one pass. Hand-written aggregates that only need the
/// cycle-12 surface can skip this trait.
pub trait AggregateMeta: Aggregate {
    /// Stable type tag for this aggregate. Must match the value used by the
    /// EventStore + projection table prefix (e.g. `world`, `npc`, `pc`).
    fn aggregate_type() -> &'static str
    where
        Self: Sized;

    /// Per-instance identity (matches `EventEnvelope.aggregate_id`).
    fn id(&self) -> &str;
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::envelope::EventEnvelope;
    use serde::{Deserialize, Serialize};
    use serde_json::json;
    use uuid::Uuid;

    #[derive(Default, Serialize, Deserialize)]
    struct World {
        id: String,
        tick: u64,
        version: u64,
    }

    impl Aggregate for World {
        fn apply(&mut self, env: &EventEnvelope) -> Result<(), String> {
            if env.event_type != "world.tick_advanced" {
                return Err(format!("unknown {}", env.event_type));
            }
            self.tick = env
                .payload
                .get("tick")
                .and_then(|v| v.as_u64())
                .ok_or_else(|| "missing 'tick'".to_string())?;
            self.version = env.aggregate_version;
            Ok(())
        }
        fn aggregate_version(&self) -> u64 {
            self.version
        }
    }

    impl AggregateMeta for World {
        fn aggregate_type() -> &'static str {
            "world"
        }
        fn id(&self) -> &str {
            &self.id
        }
    }

    fn env(tick: u64, version: u64) -> EventEnvelope {
        EventEnvelope {
            event_id: Uuid::from_u128(version as u128),
            event_type: "world.tick_advanced".into(),
            event_version: 1,
            aggregate_id: "world-1".into(),
            aggregate_type: "world".into(),
            aggregate_version: version,
            reality_id: Uuid::from_u128(0xDEAD),
            occurred_at: "2026-05-29T00:00:00Z".into(),
            recorded_at: "2026-05-29T00:00:00Z".into(),
            payload: json!({ "tick": tick }),
            metadata: None,
        }
    }

    #[test]
    fn world_implements_both_traits() {
        let mut w = World { id: "world-1".into(), ..Default::default() };
        w.apply(&env(5, 1)).unwrap();
        assert_eq!(w.tick, 5);
        assert_eq!(w.aggregate_version(), 1);
        assert_eq!(World::aggregate_type(), "world");
        assert_eq!(w.id(), "world-1");
    }

    #[test]
    fn aggregate_re_export_is_same_trait() {
        // If this compiles, our re-export is binary-equivalent to
        // load_aggregate::Aggregate (i.e. the macro can use either path).
        fn takes_aggregate<A: Aggregate>(_a: &A) {}
        fn takes_load_aggregate<A: crate::load_aggregate::Aggregate>(_a: &A) {}
        let w = World { id: "world-1".into(), ..Default::default() };
        takes_aggregate(&w);
        takes_load_aggregate(&w);
    }
}
