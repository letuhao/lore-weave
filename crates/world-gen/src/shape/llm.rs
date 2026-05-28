//! **v4.3a SCAFFOLD** — LLM-driven dispatch trait + cache trait + reference
//! implementations.
//!
//! v4.3a wires the abstraction skeleton; v4.3b adds typed parameter
//! overrides; v4.3c plugs the first real provider (Anthropic Claude via
//! tool-use); v4.3d adds OpenAI + Ollama; v4.3e adds the Postgres cache
//! when platform integration ships.
//!
//! ## Concept
//!
//! `DispatchMode::Llm` consults an [`LlmProvider`] for a `ShapeKind` (and,
//! from v4.3b on, parameter overrides) per dispatched entity. Calls are
//! routed through a [`DispatchCache`] keyed by `entity_path` so a re-run
//! over the same world is byte-deterministic and free of round-trip cost.
//!
//! The interfaces are intentionally `Send + Sync` and reference-counted via
//! `Arc` so a single provider/cache pair can be shared across all the
//! dispatch sites in a `flatworld::generate` call without copies.

use std::collections::HashMap;
use std::fmt;
use std::sync::Mutex;

use crate::shape::{ParamOverride, ShapeContext, ShapeKind, SizeRank};

/// What the LLM gets as input. Captures the dispatch context as a
/// provider-agnostic struct so a single provider impl can serve every
/// dispatch site (plates, zones, sub-zones) without leaking
/// world-gen-specific types into the provider crate.
#[derive(Debug, Clone)]
pub struct LlmPrompt {
    /// Stable string identity (e.g. `"plate.0"`, `"plate.3.zone.1.subzone.0"`)
    /// — the cache key and the LLM's "what is this entity" handle.
    pub entity_path: String,
    /// `0` = plate, `1` = zone, `2` = sub-zone. Lets the LLM bias by depth.
    pub depth: u32,
    pub size_rank: SizeRank,
    /// Normalised latitude in `[0, 1]` (`0` = north, `1` = south) — handed
    /// in by the dispatcher from `ctx.edge_jitter` per the v4.0 piggyback
    /// convention. v4.1 will add a typed `ctx.lat_norm` field; until then
    /// this carries the current world's lat for the prompt builder.
    pub lat_norm: f32,
    /// Parent identity path (e.g. `[plate_id]` for a zone, `[plate_id,
    /// zone_id]` for a sub-zone). Empty for plates. Helps the LLM keep
    /// stylistic coherence per family.
    pub parent_path: Vec<usize>,
    /// Which kinds the registry actually has registered — the LLM MUST
    /// return one of these (provider impls should grammar-constrain the
    /// decode). Listed in registry insertion order.
    pub allowed_kinds: Vec<ShapeKind>,
}

impl LlmPrompt {
    /// Build a prompt from the dispatcher's per-call context.
    pub fn from_context(ctx: &ShapeContext, entity_path: &str, allowed_kinds: Vec<ShapeKind>) -> Self {
        LlmPrompt {
            entity_path: entity_path.to_string(),
            depth: ctx.depth,
            size_rank: ctx.size_rank,
            lat_norm: ctx.edge_jitter, // v4.0 piggyback convention
            parent_path: ctx.parent_path.clone(),
            allowed_kinds,
        }
    }
}

/// What the LLM returns. `kind` is the selected `ShapeKind`; `params` is
/// the typed [`ParamOverride`] that the matching generator reads from
/// [`ShapeContext::params`] when the dispatcher threads the decision
/// through.
#[derive(Debug, Clone)]
pub struct LlmDecision {
    pub kind: ShapeKind,
    /// **v4.3b**: typed per-generator parameter override. Set to a variant
    /// matching `kind` (e.g. `kind = Ellipse` → `params =
    /// Some(ParamOverride::Ellipse { .. })`). `None` means "use generator
    /// defaults". Mismatched variant + kind pairings are silently ignored
    /// by generators — they only match their own variant. v4.3b ships
    /// variants for Ellipse / Boolean / Stamp; remaining generators
    /// receive `None` until v4.3d.
    pub params: Option<ParamOverride>,
}

/// Error returned by [`LlmProvider::pick`]. `DispatchMode::Llm` treats any
/// error as an abstain so the caller's `Layered` fallback can recover
/// (typical pairing: `Layered([Llm, Weighted(...)])`).
#[derive(Debug)]
pub enum LlmError {
    /// Network or transport failure.
    Transport(String),
    /// Provider returned a value that wasn't a registered `ShapeKind`.
    InvalidResponse(String),
    /// Provider refused to answer (rate-limit, content policy, etc.).
    Refused(String),
    /// Catch-all for impl-specific errors.
    Other(String),
}

impl fmt::Display for LlmError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            LlmError::Transport(m) => write!(f, "LLM transport error: {m}"),
            LlmError::InvalidResponse(m) => write!(f, "LLM invalid response: {m}"),
            LlmError::Refused(m) => write!(f, "LLM refused: {m}"),
            LlmError::Other(m) => write!(f, "LLM error: {m}"),
        }
    }
}

impl std::error::Error for LlmError {}

/// The provider-side interface. v4.3a ships [`MockLlmProvider`]; v4.3c
/// adds `AnthropicProvider`; v4.3d adds OpenAI + Ollama.
///
/// Implementations MUST be `Send + Sync` so a single `Arc<dyn LlmProvider>`
/// can be cloned across the per-plate Rayon par-iter in
/// `flatworld::generate`. Implementations MUST be `Debug` so
/// `DispatchMode` keeps its `Debug` derive.
pub trait LlmProvider: fmt::Debug + Send + Sync {
    fn pick(&self, prompt: &LlmPrompt) -> Result<LlmDecision, LlmError>;
}

/// The cache-side interface. `get` returns a previously-stored decision;
/// `put` stores a fresh one. Interior mutability (the impl owns the lock)
/// so the dispatcher can borrow the cache shared.
pub trait DispatchCache: fmt::Debug + Send + Sync {
    fn get(&self, key: &str) -> Option<LlmDecision>;
    fn put(&self, key: &str, value: LlmDecision);
}

/// In-process `HashMap`-backed cache. The CLI uses this; the platform will
/// add a `PostgresDispatchCache` in v4.3e once the dispatcher is invoked
/// from a deployed service.
#[derive(Debug, Default)]
pub struct InMemoryDispatchCache {
    inner: Mutex<HashMap<String, LlmDecision>>,
}

impl InMemoryDispatchCache {
    pub fn new() -> Self {
        Self::default()
    }

    /// Test helper: number of cached entries.
    pub fn len(&self) -> usize {
        self.inner.lock().expect("cache mutex poisoned").len()
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
}

impl DispatchCache for InMemoryDispatchCache {
    fn get(&self, key: &str) -> Option<LlmDecision> {
        self.inner
            .lock()
            .expect("cache mutex poisoned")
            .get(key)
            .cloned()
    }

    fn put(&self, key: &str, value: LlmDecision) {
        self.inner
            .lock()
            .expect("cache mutex poisoned")
            .insert(key.to_string(), value);
    }
}

/// Deterministic stand-in provider for testing + offline runs. Picks a
/// `ShapeKind` by hashing `prompt.entity_path` mod `allowed_kinds.len()`
/// so the same path always produces the same kind (the property the
/// real provider must preserve via cache + temperature=0). `params` is
/// always `None` for v4.3a; v4.3b extends this with a generator-aware
/// stub.
#[derive(Debug, Clone)]
pub struct MockLlmProvider;

impl MockLlmProvider {
    pub fn new() -> Self {
        Self
    }
}

impl Default for MockLlmProvider {
    fn default() -> Self {
        Self::new()
    }
}

impl LlmProvider for MockLlmProvider {
    fn pick(&self, prompt: &LlmPrompt) -> Result<LlmDecision, LlmError> {
        if prompt.allowed_kinds.is_empty() {
            return Err(LlmError::InvalidResponse(
                "registry has no kinds".to_string(),
            ));
        }
        // FNV-1a 32-bit so the choice is stable across runs without
        // pulling in a hash crate.
        let mut h: u32 = 0x811C_9DC5;
        for byte in prompt.entity_path.as_bytes() {
            h ^= *byte as u32;
            h = h.wrapping_mul(0x0100_0193);
        }
        let kind = prompt.allowed_kinds[(h as usize) % prompt.allowed_kinds.len()];
        // **v4.3b**: populate `params` per kind for the variants v4.3b
        // wires up (Ellipse / Boolean / Stamp). Other kinds receive
        // `None` — generators ignore unmatched variants anyway, so the
        // contract stays clean as more generators get LLM-tunable knobs.
        let params = mock_params_for_kind(kind, h);
        Ok(LlmDecision { kind, params })
    }
}

/// Deterministic mock parameters for a given kind + entity-path hash.
/// `kind` selects the variant; `h` seeds the per-variant choice so different
/// paths get different param values. Pure function of inputs — calling it
/// twice with the same args returns the same params.
fn mock_params_for_kind(kind: ShapeKind, h: u32) -> Option<ParamOverride> {
    match kind {
        ShapeKind::Ellipse => {
            // aspect_ratio cycles through 1.0 / 1.5 / 2.0 / 2.5 across
            // adjacent entity paths so a default render visibly varies.
            let ratios = [1.0_f32, 1.5, 2.0, 2.5];
            Some(ParamOverride::Ellipse {
                aspect_ratio: Some(ratios[(h as usize) % ratios.len()]),
            })
        }
        ShapeKind::Boolean => {
            use crate::shape::csg::BooleanTemplate;
            let templates = [
                BooleanTemplate::EllipseUnion,
                BooleanTemplate::WedgeCut,
                BooleanTemplate::EllipseDifference,
            ];
            Some(ParamOverride::Boolean {
                template: Some(templates[(h as usize) % templates.len()]),
            })
        }
        ShapeKind::Stamp => Some(ParamOverride::Stamp {
            template_id: Some(h % 10),
        }),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shape::ShapeContext;

    fn ctx() -> ShapeContext {
        ShapeContext {
            depth: 0,
            center: (100.0, 100.0),
            envelope: (50.0, 50.0),
            size_rank: SizeRank::Medium,
            seed: 42,
            plate_salt: 7,
            parent_path: vec![],
            world_theme: None,
            edge_jitter: 0.5,
            vertex_count_range: (32, 96),
            params: None,
        }
    }

    #[test]
    fn mock_provider_is_deterministic_per_path() {
        let mock = MockLlmProvider::new();
        let kinds = vec![ShapeKind::Ellipse, ShapeKind::BezierSpine, ShapeKind::Polar];
        let prompt = LlmPrompt::from_context(&ctx(), "plate.7", kinds.clone());
        let a = mock.pick(&prompt).expect("mock should pick");
        let b = mock.pick(&prompt).expect("mock should pick");
        assert_eq!(a.kind, b.kind, "same entity_path must yield same kind");
    }

    #[test]
    fn mock_provider_spreads_across_paths() {
        // Across many paths the mock should hit ≥2 distinct kinds — proves
        // the FNV hash isn't degenerate.
        let mock = MockLlmProvider::new();
        let kinds = vec![ShapeKind::Ellipse, ShapeKind::BezierSpine, ShapeKind::Polar];
        let picked: std::collections::HashSet<ShapeKind> = (0..32)
            .map(|i| {
                let prompt = LlmPrompt::from_context(&ctx(), &format!("plate.{i}"), kinds.clone());
                mock.pick(&prompt).expect("mock should pick").kind
            })
            .collect();
        assert!(picked.len() >= 2, "mock provider should not collapse to one kind across 32 paths");
    }

    #[test]
    fn mock_provider_rejects_empty_registry() {
        let mock = MockLlmProvider::new();
        let prompt = LlmPrompt::from_context(&ctx(), "plate.0", vec![]);
        assert!(matches!(mock.pick(&prompt), Err(LlmError::InvalidResponse(_))));
    }

    #[test]
    fn in_memory_cache_round_trips_a_decision() {
        let cache = InMemoryDispatchCache::new();
        assert!(cache.is_empty());
        let decision = LlmDecision { kind: ShapeKind::Stamp, params: None };
        cache.put("plate.0.zone.0", decision.clone());
        let hit = cache.get("plate.0.zone.0").expect("cache should hit");
        assert_eq!(hit.kind, ShapeKind::Stamp);
        assert!(cache.get("plate.0.zone.1").is_none(), "cold path");
        assert_eq!(cache.len(), 1);
    }

    #[test]
    fn in_memory_cache_overwrites_on_repeat_put() {
        let cache = InMemoryDispatchCache::new();
        cache.put("plate.0", LlmDecision { kind: ShapeKind::Ellipse, params: None });
        cache.put("plate.0", LlmDecision { kind: ShapeKind::Slime, params: None });
        assert_eq!(cache.get("plate.0").unwrap().kind, ShapeKind::Slime);
        assert_eq!(cache.len(), 1, "second put must overwrite, not append");
    }

    #[test]
    fn v4_3b_mock_populates_ellipse_aspect_ratio() {
        // Mock provider must hand back `ParamOverride::Ellipse { aspect_ratio: Some(_) }`
        // whenever it picks `ShapeKind::Ellipse`.
        let mock = MockLlmProvider::new();
        // Force kind=Ellipse via allowed_kinds == [Ellipse].
        let prompt = LlmPrompt::from_context(&ctx(), "plate.0", vec![ShapeKind::Ellipse]);
        let d = mock.pick(&prompt).expect("mock should pick");
        assert_eq!(d.kind, ShapeKind::Ellipse);
        let params = d.params.expect("Ellipse kind should carry params");
        match params {
            ParamOverride::Ellipse { aspect_ratio: Some(r) } => {
                assert!(r >= 0.5 && r <= 3.0, "aspect_ratio {r} out of expected mock range");
            }
            _ => panic!("expected ParamOverride::Ellipse with aspect_ratio, got {params:?}"),
        }
    }

    #[test]
    fn v4_3b_mock_populates_boolean_template() {
        let mock = MockLlmProvider::new();
        let prompt = LlmPrompt::from_context(&ctx(), "plate.5", vec![ShapeKind::Boolean]);
        let d = mock.pick(&prompt).expect("mock should pick");
        assert_eq!(d.kind, ShapeKind::Boolean);
        let params = d.params.expect("Boolean kind should carry params");
        assert!(
            matches!(params, ParamOverride::Boolean { template: Some(_) }),
            "expected ParamOverride::Boolean with template, got {params:?}"
        );
    }

    #[test]
    fn v4_3b_mock_populates_stamp_template_id() {
        let mock = MockLlmProvider::new();
        let prompt = LlmPrompt::from_context(&ctx(), "plate.7", vec![ShapeKind::Stamp]);
        let d = mock.pick(&prompt).expect("mock should pick");
        assert_eq!(d.kind, ShapeKind::Stamp);
        let params = d.params.expect("Stamp kind should carry params");
        match params {
            ParamOverride::Stamp { template_id: Some(id) } => {
                assert!(id < 10, "mock template_id {id} should be in [0, 9]");
            }
            _ => panic!("expected ParamOverride::Stamp with template_id, got {params:?}"),
        }
    }

    #[test]
    fn v4_3b_mock_returns_none_params_for_unwired_kinds() {
        // BezierSpine / Polar / SDF / MarchingNoise / Slime are not wired
        // for LLM params yet — Mock must return None for those.
        let mock = MockLlmProvider::new();
        for kind in [
            ShapeKind::BezierSpine,
            ShapeKind::Polar,
            ShapeKind::SdfCapsuleChain,
            ShapeKind::MarchingNoise,
            ShapeKind::Slime,
        ] {
            let prompt = LlmPrompt::from_context(&ctx(), "plate.0", vec![kind]);
            let d = mock.pick(&prompt).expect("mock should pick");
            assert_eq!(d.kind, kind);
            assert!(
                d.params.is_none(),
                "kind {kind:?} should have None params in v4.3b, got {:?}",
                d.params,
            );
        }
    }
}
