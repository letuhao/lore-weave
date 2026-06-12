//! Integration test for `#[derive(Aggregate)]` + `#[handles_event(...)]`.
//!
//! Validates:
//!  1. The derive emits a working `Aggregate` impl (apply bumps `version`).
//!  2. The derive emits a working `AggregateMeta` impl (`id()` + type tag).
//!  3. `#[aggregate_type = "..."]` overrides the default lowercased name.
//!  4. `#[handles_event("...")]` is accepted as an inert-but-validated
//!     attribute on impl methods.
//!  5. The default `aggregate_type` lowercases the struct ident.

use dp_kernel::{Aggregate, AggregateMeta, EventEnvelope};
use dp_kernel_macros::{handles_event, Aggregate};
use serde::{Deserialize, Serialize};
use serde_json::json;
use uuid::Uuid;

// ── Case 1: default aggregate_type = lowercased struct name ───────────────
#[derive(Default, Serialize, Deserialize, Aggregate)]
struct Counter {
    id: String,
    version: u64,
    value: i64,
}

// User-side dispatch lives on the impl block, NOT the derive. The
// `#[handles_event(...)]` attribute is informational (Q-L4B-1 syntax).
impl Counter {
    #[handles_event("counter.incremented")]
    pub fn apply_incremented(&mut self, env: &EventEnvelope) -> Result<(), String> {
        let delta = env
            .payload
            .get("delta")
            .and_then(|v| v.as_i64())
            .ok_or_else(|| "missing 'delta'".to_string())?;
        self.value += delta;
        // Delegate to the derived apply() for version-bump.
        <Self as Aggregate>::apply(self, env)
    }

    #[handles_event("counter.reset")]
    #[handles_event("counter.zeroed")] // multiple attrs OK
    pub fn apply_reset(&mut self, env: &EventEnvelope) -> Result<(), String> {
        self.value = 0;
        <Self as Aggregate>::apply(self, env)
    }
}

// ── Case 2: explicit aggregate_type override ──────────────────────────────
#[derive(Default, Serialize, Deserialize, Aggregate)]
#[aggregate_type = "geo_region"]
struct Region {
    id: String,
    version: u64,
    name: String,
}

// ── Case 3: list-syntax override (tolerated) ──────────────────────────────
#[derive(Default, Serialize, Deserialize, Aggregate)]
#[aggregate_type("npc_session")]
struct NpcSession {
    id: String,
    version: u64,
}

fn env(event_type: &str, agg_type: &str, agg_id: &str, version: u64, payload: serde_json::Value) -> EventEnvelope {
    EventEnvelope {
        event_id: Uuid::from_u128(version as u128),
        event_type: event_type.into(),
        event_version: 1,
        aggregate_id: agg_id.into(),
        aggregate_type: agg_type.into(),
        aggregate_version: version,
        reality_id: Uuid::from_u128(0xDEAD),
        occurred_at: "2026-05-29T00:00:00Z".into(),
        recorded_at: "2026-05-29T00:00:00Z".into(),
        payload,
        metadata: None,
    }
}

#[test]
fn derive_emits_aggregate_meta_with_lowercased_default() {
    assert_eq!(Counter::aggregate_type(), "counter");
    let c = Counter { id: "c-1".into(), ..Default::default() };
    assert_eq!(c.id(), "c-1");
}

#[test]
fn derive_emits_aggregate_apply_bumps_version() {
    let mut c = Counter { id: "c-1".into(), ..Default::default() };
    <Counter as Aggregate>::apply(&mut c, &env("counter.incremented", "counter", "c-1", 5, json!({"delta": 7}))).unwrap();
    assert_eq!(c.aggregate_version(), 5);
}

#[test]
fn user_impl_with_handles_event_works() {
    let mut c = Counter { id: "c-1".into(), ..Default::default() };
    c.apply_incremented(&env("counter.incremented", "counter", "c-1", 1, json!({"delta": 5}))).unwrap();
    assert_eq!(c.value, 5);
    c.apply_incremented(&env("counter.incremented", "counter", "c-1", 2, json!({"delta": -3}))).unwrap();
    assert_eq!(c.value, 2);
    c.apply_reset(&env("counter.reset", "counter", "c-1", 3, json!({}))).unwrap();
    assert_eq!(c.value, 0);
    assert_eq!(c.aggregate_version(), 3);
}

#[test]
fn explicit_aggregate_type_override_name_value() {
    assert_eq!(Region::aggregate_type(), "geo_region");
    let r = Region { id: "r-1".into(), name: "Forest".into(), ..Default::default() };
    assert_eq!(r.id(), "r-1");
}

#[test]
fn explicit_aggregate_type_override_list() {
    assert_eq!(NpcSession::aggregate_type(), "npc_session");
}

#[test]
fn aggregate_meta_id_accepts_string_field() {
    // Compile-only: `id: String` should satisfy AsRef<str> path the macro emits.
    let c = Counter { id: "c-99".into(), ..Default::default() };
    let s: &str = c.id();
    assert_eq!(s, "c-99");
}
