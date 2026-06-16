//! Cycle 20 / L4.E — `entity_status` Rust mirror of `contracts/entity_status/` (Go).
//!
//! ## Purpose (Q-L4-1 parity)
//!
//! Same shared-kernel GetEntityStatus surface, in Rust. Rust kernel callers
//! (world-service, future translation/chat Rust services) need the same
//! 4-layer resolver cascade — PIIKek → reality_registry → reality_ancestry →
//! projections — with the same compound precedence (dropped > user_erased >
//! severed > archived > active).
//!
//! ## Q-IDs honored
//!
//! - **Q-L4-1**: byte-equal wire format with Go side (`#[serde(rename_all = "snake_case")]`
//!   on GoneState; field order matches `EntityStatusEnvelope` Go struct).
//! - **Q-L3-4**: `aggregate_version` carried through from projection rows
//!   (NOT synthesized).
//! - **load_aggregate reuse**: the [`ProjectionReader`] trait MUST be backed by
//!   cycle-12 `load_aggregate` in production wiring. Tests inject a fake.

use serde::{Deserialize, Serialize};
use std::sync::Mutex;
use std::time::{Duration, SystemTime};

/// Lifecycle state of a game entity. Wire format = canonical snake_case.
/// Mirrors `GoneState` in `contracts/entity_status/gone_state.go`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum GoneState {
    /// Entity is live and reachable.
    Active,
    /// Entity moved between realities or was disconnected from its parent.
    Severed,
    /// Entity's home reality was archived.
    Archived,
    /// Entity (or its reality) was hard-deleted. Terminal.
    Dropped,
    /// Entity's PII was crypto-shredded (GDPR Art. 17). Terminal.
    UserErased,
}

impl GoneState {
    /// Canonical snake_case string form.
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Active => "active",
            Self::Severed => "severed",
            Self::Archived => "archived",
            Self::Dropped => "dropped",
            Self::UserErased => "user_erased",
        }
    }

    /// True iff the entity is reachable for normal hot-path reads.
    pub fn is_live(&self) -> bool {
        matches!(self, Self::Active)
    }

    /// True iff the state never transitions back to `Active`.
    pub fn is_terminal(&self) -> bool {
        matches!(self, Self::Dropped | Self::UserErased)
    }
}

/// Precedence rank — higher wins. Mirrors `precedence.go::precedenceRank`.
fn precedence_rank(s: GoneState) -> u8 {
    match s {
        GoneState::Dropped => 5,
        GoneState::UserErased => 4,
        GoneState::Severed => 3,
        GoneState::Archived => 2,
        GoneState::Active => 1,
    }
}

/// Returns whichever of `(a, b)` has stronger precedence.
pub fn higher(a: GoneState, b: GoneState) -> GoneState {
    if precedence_rank(a) >= precedence_rank(b) {
        a
    } else {
        b
    }
}

/// Reduce N candidates to the strongest. Empty = `Active`.
pub fn reduce(states: &[GoneState]) -> GoneState {
    let mut winner = GoneState::Active;
    for s in states {
        winner = higher(winner, *s);
    }
    winner
}

// ── Refs + envelope ─────────────────────────────────────────────────────────

/// Aggregate type enum. Mirrors the 5 cycle-13 per-aggregate skeletons.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AggregateType {
    /// Player character.
    Pc,
    /// Non-player character.
    Npc,
    /// Region of the world map.
    Region,
    /// Free-form world key/value store.
    WorldKv,
    /// Session aggregate.
    Session,
}

impl AggregateType {
    /// Canonical snake_case string.
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Pc => "pc",
            Self::Npc => "npc",
            Self::Region => "region",
            Self::WorldKv => "world_kv",
            Self::Session => "session",
        }
    }
}

/// One entity to resolve. Mirrors `EntityRef` in Go.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct EntityRef {
    /// Aggregate primary key (UUID string).
    pub entity_id: String,
    /// Aggregate kind.
    pub aggregate_type: AggregateType,
    /// Home reality id.
    pub reality_id: String,
}

impl EntityRef {
    /// Fail-fast validate the ref shape.
    pub fn validate(&self) -> Result<(), EntityStatusError> {
        if self.entity_id.trim().is_empty() {
            return Err(EntityStatusError::BadRef("entity_id empty".into()));
        }
        if self.reality_id.trim().is_empty() {
            return Err(EntityStatusError::BadRef("reality_id empty".into()));
        }
        Ok(())
    }
}

/// Layer that answered the cascade. Mirrors the Go `source_layer` field.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SourceLayer {
    /// PII KEK said the user is erased.
    PiiKek,
    /// reality_registry said the reality is dropped/archived.
    RealityRegistry,
    /// reality_ancestry said the entity is severed.
    RealityAncestry,
    /// Projection row was the authoritative answer.
    Projections,
    /// No layer fired — defaulted to Active.
    DefaultActive,
}

impl SourceLayer {
    /// Canonical snake_case string.
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::PiiKek => "pii_kek",
            Self::RealityRegistry => "reality_registry",
            Self::RealityAncestry => "reality_ancestry",
            Self::Projections => "projections",
            Self::DefaultActive => "default_active",
        }
    }
}

/// Versioned envelope. Mirrors `EntityStatusEnvelope` Go struct.
///
/// `envelope_version` is V1-stable.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct EntityStatusEnvelope {
    /// = 1 for this cycle.
    pub envelope_version: u32,
    /// Input ref echoed for forensic correlation.
    pub ref_: EntityRef,
    /// Resolved (compound-collapsed) state.
    pub state: GoneState,
    /// Which layer answered.
    pub source_layer: SourceLayer,
    /// Q-L3-4 projection version; 0 when n/a.
    #[serde(default)]
    pub aggregate_version: u64,
    /// Resolution wall-clock (unix nanos to stay codec-agnostic).
    pub resolved_at_nanos: i64,
}

/// One layer's response. `has=false` ⇒ layer has no opinion; cascade
/// continues.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct LookupResult {
    /// Did this layer authoritatively respond?
    pub has: bool,
    /// State the layer reports (only meaningful when `has`).
    pub state: GoneState,
    /// Aggregate version (only meaningful for projection layer).
    pub aggregate_version: u64,
}

impl Default for LookupResult {
    fn default() -> Self {
        Self {
            has: false,
            state: GoneState::Active,
            aggregate_version: 0,
        }
    }
}

// ── Layer traits ───────────────────────────────────────────────────────────

/// PII KEK layer. Optional — entities without PII (regions, world_kv) skip.
pub trait PiiKekReader: Send + Sync {
    /// Returns `has=true, state=UserErased` when this entity's user is erased.
    fn lookup_by_entity(&self, ref_: &EntityRef) -> Result<LookupResult, EntityStatusError>;
}

/// Reality registry layer. Mandatory.
pub trait RealityRegistryReader: Send + Sync {
    /// Returns the reality-level state.
    fn lookup_by_reality(&self, reality_id: &str) -> Result<LookupResult, EntityStatusError>;
}

/// Reality ancestry layer. Optional — V1 may not have the table yet.
pub trait RealityAncestryReader: Send + Sync {
    /// Returns severed/archived if the entity moved cross-reality.
    fn lookup_by_entity(&self, ref_: &EntityRef) -> Result<LookupResult, EntityStatusError>;
}

/// Projections layer. Mandatory — backed by cycle-12 `load_aggregate` in
/// production wiring (NOT raw SQL).
pub trait ProjectionReader: Send + Sync {
    /// Returns the projection-row state. `has=false` ⇒ row missing ⇒
    /// resolver promotes to `Dropped`.
    fn lookup_by_entity(&self, ref_: &EntityRef) -> Result<LookupResult, EntityStatusError>;
}

/// Errors emitted by the resolver.
#[derive(Debug, thiserror::Error)]
pub enum EntityStatusError {
    /// Ref failed input validation.
    #[error("entity_status: bad ref: {0}")]
    BadRef(String),

    /// One of the layer-reader calls failed.
    #[error("entity_status: layer {layer:?} failed: {detail}")]
    LayerFailure {
        /// Which layer errored.
        layer: SourceLayer,
        /// Detail (typically forwarded from the backend driver).
        detail: String,
    },

    /// Resolver was misconfigured (missing mandatory reader).
    #[error("entity_status: misconfigured: {0}")]
    Misconfigured(String),
}

// ── Resolver ───────────────────────────────────────────────────────────────

/// 4-layer cascade resolver. Mirrors the Go `Resolver`.
pub struct Resolver<'a> {
    /// Optional PII KEK reader.
    pub pii_kek: Option<&'a dyn PiiKekReader>,
    /// Mandatory reality registry reader.
    pub reality_registry: &'a dyn RealityRegistryReader,
    /// Optional reality ancestry reader.
    pub reality_ancestry: Option<&'a dyn RealityAncestryReader>,
    /// Mandatory projection reader (backed by load_aggregate).
    pub projections: &'a dyn ProjectionReader,
    /// Now function (injected for tests).
    pub now: fn() -> i64,
}

impl<'a> Resolver<'a> {
    /// Run the 4-layer cascade and return the envelope.
    pub fn get_entity_status(
        &self,
        ref_: EntityRef,
    ) -> Result<EntityStatusEnvelope, EntityStatusError> {
        ref_.validate()?;

        let now_nanos = (self.now)();

        // Layer 1: PII KEK.
        if let Some(pii) = self.pii_kek {
            let res = pii.lookup_by_entity(&ref_).map_err(|e| {
                EntityStatusError::LayerFailure {
                    layer: SourceLayer::PiiKek,
                    detail: e.to_string(),
                }
            })?;
            if res.has && res.state == GoneState::UserErased {
                return Ok(EntityStatusEnvelope {
                    envelope_version: 1,
                    ref_,
                    state: GoneState::UserErased,
                    source_layer: SourceLayer::PiiKek,
                    aggregate_version: 0,
                    resolved_at_nanos: now_nanos,
                });
            }
        }

        // Layer 2: reality registry.
        let reg = self.reality_registry.lookup_by_reality(&ref_.reality_id).map_err(|e| {
            EntityStatusError::LayerFailure {
                layer: SourceLayer::RealityRegistry,
                detail: e.to_string(),
            }
        })?;
        if reg.has && reg.state == GoneState::Dropped {
            return Ok(EntityStatusEnvelope {
                envelope_version: 1,
                ref_,
                state: GoneState::Dropped,
                source_layer: SourceLayer::RealityRegistry,
                aggregate_version: 0,
                resolved_at_nanos: now_nanos,
            });
        }

        // Layer 3: reality ancestry.
        if let Some(anc_reader) = self.reality_ancestry {
            let anc = anc_reader.lookup_by_entity(&ref_).map_err(|e| {
                EntityStatusError::LayerFailure {
                    layer: SourceLayer::RealityAncestry,
                    detail: e.to_string(),
                }
            })?;
            if anc.has {
                let composite = reduce(&[reg.state, anc.state]);
                let source = if composite == reg.state && reg.has {
                    SourceLayer::RealityRegistry
                } else {
                    SourceLayer::RealityAncestry
                };
                return Ok(EntityStatusEnvelope {
                    envelope_version: 1,
                    ref_,
                    state: composite,
                    source_layer: source,
                    aggregate_version: 0,
                    resolved_at_nanos: now_nanos,
                });
            }
        }

        // Layer 4: projections (last resort).
        let proj = self.projections.lookup_by_entity(&ref_).map_err(|e| {
            EntityStatusError::LayerFailure {
                layer: SourceLayer::Projections,
                detail: e.to_string(),
            }
        })?;
        if !proj.has {
            // No projection row + reality healthy → promote to dropped.
            return Ok(EntityStatusEnvelope {
                envelope_version: 1,
                ref_,
                state: GoneState::Dropped,
                source_layer: SourceLayer::Projections,
                aggregate_version: 0,
                resolved_at_nanos: now_nanos,
            });
        }

        let composite = reduce(&[reg.state, proj.state]);
        let source = if composite != proj.state && reg.has {
            SourceLayer::RealityRegistry
        } else {
            SourceLayer::Projections
        };

        Ok(EntityStatusEnvelope {
            envelope_version: 1,
            ref_,
            state: composite,
            source_layer: source,
            aggregate_version: proj.aggregate_version,
            resolved_at_nanos: now_nanos,
        })
    }
}

/// Production now() helper (unix nanos).
pub fn now_nanos() -> i64 {
    let d = SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .unwrap_or_default();
    d.as_nanos() as i64
}

// ── Cache contract ────────────────────────────────────────────────────────

/// 60s TTL by S10 §12Z.
pub const DEFAULT_CACHE_TTL: Duration = Duration::from_secs(60);

/// Cache surface for entity_status envelopes.
pub trait EntityStatusCache: Send + Sync {
    /// Get cached envelope; `None` on miss.
    fn get(&self, ref_: &EntityRef) -> Option<EntityStatusEnvelope>;
    /// Store envelope with TTL.
    fn set(&self, ref_: &EntityRef, env: EntityStatusEnvelope, ttl: Duration);
    /// Invalidate one entity.
    fn invalidate(&self, ref_: &EntityRef);
}

/// In-memory test cache. NOT for production.
#[derive(Default)]
pub struct InMemoryEntityStatusCache {
    inner: Mutex<std::collections::HashMap<String, EntityStatusEnvelope>>,
}

impl InMemoryEntityStatusCache {
    /// Construct an empty cache.
    pub fn new() -> Self {
        Self::default()
    }
}

fn cache_key(ref_: &EntityRef) -> String {
    format!(
        "{}:{}:{}",
        ref_.reality_id,
        ref_.aggregate_type.as_str(),
        ref_.entity_id
    )
}

impl EntityStatusCache for InMemoryEntityStatusCache {
    fn get(&self, ref_: &EntityRef) -> Option<EntityStatusEnvelope> {
        self.inner.lock().unwrap().get(&cache_key(ref_)).cloned()
    }
    fn set(&self, ref_: &EntityRef, env: EntityStatusEnvelope, _ttl: Duration) {
        self.inner.lock().unwrap().insert(cache_key(ref_), env);
    }
    fn invalidate(&self, ref_: &EntityRef) {
        self.inner.lock().unwrap().remove(&cache_key(ref_));
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU32, Ordering};

    fn sample_ref() -> EntityRef {
        EntityRef {
            entity_id: "11111111-2222-3333-4444-555555555555".into(),
            aggregate_type: AggregateType::Pc,
            reality_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee".into(),
        }
    }

    fn fixed_now() -> i64 {
        1_700_000_000_000_000_000
    }

    struct FakeReader(LookupResult);
    impl PiiKekReader for FakeReader {
        fn lookup_by_entity(&self, _: &EntityRef) -> Result<LookupResult, EntityStatusError> {
            Ok(self.0)
        }
    }
    impl RealityRegistryReader for FakeReader {
        fn lookup_by_reality(&self, _: &str) -> Result<LookupResult, EntityStatusError> {
            Ok(self.0)
        }
    }
    impl RealityAncestryReader for FakeReader {
        fn lookup_by_entity(&self, _: &EntityRef) -> Result<LookupResult, EntityStatusError> {
            Ok(self.0)
        }
    }
    impl ProjectionReader for FakeReader {
        fn lookup_by_entity(&self, _: &EntityRef) -> Result<LookupResult, EntityStatusError> {
            Ok(self.0)
        }
    }

    #[test]
    fn parity_gone_state_strings_match_go() {
        for (s, want) in [
            (GoneState::Active, "active"),
            (GoneState::Severed, "severed"),
            (GoneState::Archived, "archived"),
            (GoneState::Dropped, "dropped"),
            (GoneState::UserErased, "user_erased"),
        ] {
            assert_eq!(s.as_str(), want);
        }
    }

    #[test]
    fn gone_state_serializes_as_snake_case() {
        let s = serde_json::to_string(&GoneState::UserErased).unwrap();
        assert_eq!(s, "\"user_erased\"");
    }

    #[test]
    fn precedence_dropped_wins_over_user_erased() {
        assert_eq!(higher(GoneState::Dropped, GoneState::UserErased), GoneState::Dropped);
    }

    #[test]
    fn reduce_picks_strongest() {
        let r = reduce(&[GoneState::Active, GoneState::Severed, GoneState::Archived]);
        assert_eq!(r, GoneState::Severed);
    }

    #[test]
    fn reduce_empty_is_active() {
        assert_eq!(reduce(&[]), GoneState::Active);
    }

    #[test]
    fn validate_rejects_empty_entity_id() {
        let mut r = sample_ref();
        r.entity_id = "".into();
        assert!(r.validate().is_err());
    }

    #[test]
    fn resolver_short_circuits_on_user_erased() {
        let pii = FakeReader(LookupResult {
            has: true,
            state: GoneState::UserErased,
            aggregate_version: 0,
        });
        let reg = FakeReader(LookupResult::default());
        let proj = FakeReader(LookupResult::default());
        let r = Resolver {
            pii_kek: Some(&pii),
            reality_registry: &reg,
            reality_ancestry: None,
            projections: &proj,
            now: fixed_now,
        };
        let env = r.get_entity_status(sample_ref()).unwrap();
        assert_eq!(env.state, GoneState::UserErased);
        assert_eq!(env.source_layer, SourceLayer::PiiKek);
        assert_eq!(env.envelope_version, 1);
    }

    #[test]
    fn resolver_short_circuits_on_dropped_reality() {
        let reg = FakeReader(LookupResult {
            has: true,
            state: GoneState::Dropped,
            aggregate_version: 0,
        });
        let proj = FakeReader(LookupResult::default());
        let r = Resolver {
            pii_kek: None,
            reality_registry: &reg,
            reality_ancestry: None,
            projections: &proj,
            now: fixed_now,
        };
        let env = r.get_entity_status(sample_ref()).unwrap();
        assert_eq!(env.state, GoneState::Dropped);
        assert_eq!(env.source_layer, SourceLayer::RealityRegistry);
    }

    #[test]
    fn resolver_falls_through_to_projections() {
        let reg = FakeReader(LookupResult {
            has: true,
            state: GoneState::Active,
            aggregate_version: 0,
        });
        let proj = FakeReader(LookupResult {
            has: true,
            state: GoneState::Active,
            aggregate_version: 17,
        });
        let r = Resolver {
            pii_kek: None,
            reality_registry: &reg,
            reality_ancestry: None,
            projections: &proj,
            now: fixed_now,
        };
        let env = r.get_entity_status(sample_ref()).unwrap();
        assert_eq!(env.state, GoneState::Active);
        assert_eq!(env.source_layer, SourceLayer::Projections);
        assert_eq!(env.aggregate_version, 17);
    }

    #[test]
    fn resolver_missing_projection_promotes_to_dropped() {
        let reg = FakeReader(LookupResult {
            has: true,
            state: GoneState::Active,
            aggregate_version: 0,
        });
        let proj = FakeReader(LookupResult::default()); // has=false
        let r = Resolver {
            pii_kek: None,
            reality_registry: &reg,
            reality_ancestry: None,
            projections: &proj,
            now: fixed_now,
        };
        let env = r.get_entity_status(sample_ref()).unwrap();
        assert_eq!(env.state, GoneState::Dropped);
    }

    #[test]
    fn resolver_compound_severed_beats_archived() {
        let reg = FakeReader(LookupResult {
            has: true,
            state: GoneState::Archived,
            aggregate_version: 0,
        });
        let anc = FakeReader(LookupResult {
            has: true,
            state: GoneState::Severed,
            aggregate_version: 0,
        });
        let proj = FakeReader(LookupResult::default());
        let r = Resolver {
            pii_kek: None,
            reality_registry: &reg,
            reality_ancestry: Some(&anc),
            projections: &proj,
            now: fixed_now,
        };
        let env = r.get_entity_status(sample_ref()).unwrap();
        assert_eq!(env.state, GoneState::Severed);
    }

    #[test]
    fn cache_get_set_roundtrip() {
        let cache = InMemoryEntityStatusCache::new();
        let r = sample_ref();
        let env = EntityStatusEnvelope {
            envelope_version: 1,
            ref_: r.clone(),
            state: GoneState::Active,
            source_layer: SourceLayer::Projections,
            aggregate_version: 5,
            resolved_at_nanos: 0,
        };
        cache.set(&r, env.clone(), DEFAULT_CACHE_TTL);
        let got = cache.get(&r).unwrap();
        assert_eq!(got.state, GoneState::Active);
        cache.invalidate(&r);
        assert!(cache.get(&r).is_none());
    }

    #[test]
    fn aggregate_type_round_trip() {
        for at in [
            AggregateType::Pc,
            AggregateType::Npc,
            AggregateType::Region,
            AggregateType::WorldKv,
            AggregateType::Session,
        ] {
            let s = serde_json::to_string(&at).unwrap();
            let back: AggregateType = serde_json::from_str(&s).unwrap();
            assert_eq!(back, at);
        }
    }

    #[test]
    fn resolver_counter_calls_projections_only_when_other_layers_quiet() {
        // Concrete counter via AtomicU32 confirms cascade short-circuit.
        struct CountingProj(AtomicU32);
        impl ProjectionReader for CountingProj {
            fn lookup_by_entity(&self, _: &EntityRef) -> Result<LookupResult, EntityStatusError> {
                self.0.fetch_add(1, Ordering::SeqCst);
                Ok(LookupResult {
                    has: true,
                    state: GoneState::Active,
                    aggregate_version: 1,
                })
            }
        }
        let counter = CountingProj(AtomicU32::new(0));
        let reg = FakeReader(LookupResult {
            has: true,
            state: GoneState::Dropped,
            aggregate_version: 0,
        });
        let r = Resolver {
            pii_kek: None,
            reality_registry: &reg,
            reality_ancestry: None,
            projections: &counter,
            now: fixed_now,
        };
        let env = r.get_entity_status(sample_ref()).unwrap();
        assert_eq!(env.state, GoneState::Dropped);
        // Projections not consulted because reality short-circuited.
        assert_eq!(counter.0.load(Ordering::SeqCst), 0);
    }
}
