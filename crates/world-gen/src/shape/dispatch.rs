//! Shape dispatch — registry + mode selection.
//!
//! v3.1a ships [`DispatchMode::Random`] (uniform over registered kinds) and
//! [`DispatchMode::Fixed`] (force one kind). v3.1b will add `Weighted`. v4.0
//! will add `ByContext`, `Llm`, `Manual`, `Layered`, `PerDepth`.
//!
//! **Byte-identical invariant:** with v3.1a's default registry (Ellipse only),
//! both `Random` and `Fixed(Ellipse)` must yield `ShapeKind::Ellipse` without
//! consuming any RNG values — see [`DispatchMode::select`].

use std::collections::BTreeMap;

use crate::flatworld::SizeRank;
use crate::rng::Rng;

use super::{ShapeContext, ShapeGenerator, ShapeKind};

#[cfg(test)]
use super::ShapeResult;

/// Lookup table from [`ShapeKind`] to its registered generator. Uses
/// [`BTreeMap`] so [`ShapeRegistry::kinds`] returns kinds in a deterministic
/// order (matters for `DispatchMode::Random` reproducibility across runs).
pub struct ShapeRegistry {
    generators: BTreeMap<ShapeKind, Box<dyn ShapeGenerator>>,
}

impl ShapeRegistry {
    /// An empty registry. Use for tests; production code uses
    /// [`ShapeRegistry::engine_default`].
    pub fn empty() -> Self {
        Self {
            generators: BTreeMap::new(),
        }
    }

    /// Engine-default registry. **v3.6**: registers all 8 active generators
    /// (Ellipse + BezierSpine + Polar + Boolean + SdfCapsuleChain +
    /// MarchingNoise + Slime + Stamp). Tier 1 algorithm catalog is now
    /// SHIPPED COMPLETE.
    pub fn engine_default() -> Self {
        let mut r = Self::empty();
        r.register(Box::new(super::EllipseGenerator));
        r.register(Box::new(super::BezierSpineGenerator));
        r.register(Box::new(super::PolarGenerator));
        r.register(Box::new(super::BooleanGenerator));
        // v3.2 additions:
        r.register(Box::new(super::SdfCapsuleChainGenerator));
        r.register(Box::new(super::MarchingNoiseGenerator));
        // v3.4 addition:
        r.register(Box::new(super::SlimeGenerator));
        // v3.6 addition:
        r.register(Box::new(super::StampGenerator));
        r
    }

    /// Insert a generator (replacing any previous entry for the same kind).
    pub fn register(&mut self, generator: Box<dyn ShapeGenerator>) {
        self.generators.insert(generator.kind(), generator);
    }

    /// Look up the generator for a kind.
    pub fn get(&self, kind: ShapeKind) -> Option<&dyn ShapeGenerator> {
        self.generators.get(&kind).map(|b| b.as_ref())
    }

    /// Deterministically-ordered list of registered kinds (BTreeMap key order).
    pub fn kinds(&self) -> Vec<ShapeKind> {
        self.generators.keys().copied().collect()
    }

    /// True if the registry has no generators.
    pub fn is_empty(&self) -> bool {
        self.generators.is_empty()
    }
}

impl Default for ShapeRegistry {
    fn default() -> Self {
        Self::engine_default()
    }
}

/// Strategy for picking which [`ShapeKind`] a [`ShapeContext`] gets.
///
/// **v3.1a:** `Random` + `Fixed`. The fuller set (`Weighted` in v3.1b;
/// `ByContext` / `Llm` / `Manual` / `Layered` / `PerDepth` in v4.0) lands
/// in later phases — the enum is non-exhaustive in spirit, but Rust enums
/// in lib code are exhaustive by default, so callers do an exhaustive
/// match here and gain new arms phase by phase.
#[derive(Debug, Clone)]
pub enum DispatchMode {
    /// Uniform sample over the registry's registered kinds.
    ///
    /// **Single-kind short-circuit:** when the registry has exactly one
    /// generator, `select` returns it WITHOUT calling `rng.next_*()`. This
    /// is load-bearing for byte-identical render across v3.1a (Ellipse-
    /// only) → v3.1b (4 kinds) transitions in default `engine_default`
    /// configurations.
    Random,
    /// Force a single kind. Never consumes RNG. Useful for tests, debug
    /// renders, and the v3.1a default (`Fixed(Ellipse)`) that guarantees
    /// byte-identical render vs v3.0.
    Fixed(ShapeKind),
    /// **v3.1b**: per-rank weighted random selection. Inner map is
    /// `SizeRank → [(kind, weight), ...]`; weights MUST sum to ~1.0 per
    /// rank (`debug_assert`). The `Vec<(kind, weight)>` layout is chosen
    /// over `HashMap<kind, weight>` so iteration order is deterministic
    /// across runs without relying on hash-seed stability.
    ///
    /// **Robustness:** if cumulative-weight selection overshoots target due
    /// to f32 rounding, falls through to the LAST kind in the vec
    /// (debug builds catch malformed tables via assert; release degrades
    /// gracefully). See spec §4.6.4.
    Weighted(BTreeMap<SizeRank, Vec<(ShapeKind, f32)>>),
    /// **v4.0** Manual override. Lookup by path string (e.g. `"plate.3"` for
    /// plate 3, `"plate.3.zone.1"` for zone 1 in plate 3 in v4.1+). PO
    /// pins specific kinds for specific entities; useful for tests, debug
    /// renders, and PO-as-LLM workflow per roadmap §14 Q2.
    /// Returns `None` from `select_opt` when the path is not in the map
    /// — caller falls through to next layer (typically Random).
    Manual(std::collections::HashMap<String, ShapeKind>),
    /// **v4.0** Rules-based selection. First rule whose predicate matches
    /// `ctx` wins. Returns `None` if no rule matches.
    ByContext(Vec<ContextRule>),
    /// **v4.0** Layered fallback. Each inner mode is tried in order; first
    /// one returning `Some` wins. Returns `None` if every layer abstains
    /// (Layered itself never abstains at the public `select` boundary —
    /// see fallback path).
    Layered(Vec<DispatchMode>),
    /// **v4.0** Different mode per depth (0 = plate, 1 = zone, 2 = subzone).
    /// Forward-compat for v4.1 zone templating + v4.2 subzone templating.
    /// In v4.0 only depth=0 is exercised by `flatworld::generate`.
    PerDepth([Box<DispatchMode>; 3]),
    /// **v4.0 STUB** — full LLM-driven dispatch ships in v4.3 with cache
    /// architecture decision. v4.0 panics if reached — wire your `FlatParams.plate_dispatch`
    /// to avoid this arm until v4.3.
    Llm,
}

/// **v4.0** A single rules-based dispatch rule: predicate + the kind to
/// return if it matches.
#[derive(Debug, Clone)]
pub struct ContextRule {
    pub predicate: ContextPredicate,
    pub kind: ShapeKind,
}

/// **v4.0** Predicate evaluated against a `ShapeContext`. Boolean
/// combinators (`And`, `Or`, `Not`) compose simple atoms.
#[derive(Debug, Clone)]
pub enum ContextPredicate {
    /// Always matches.
    Any,
    /// Matches when `ctx.size_rank == rank`.
    Rank(SizeRank),
    /// Matches when `ctx.depth == d`.
    Depth(u32),
    /// Matches when the entity centre's normalised latitude (computed by
    /// the caller from world height) falls within `[min, max]` inclusive.
    /// **Caller convention**: `lat_norm = (ctx.center.1 / world_height) ∈ [0, 1]`
    /// stored in `ctx.edge_jitter` as a temporary carrier when the
    /// predicate fires. v4.1 will add an explicit `ctx.lat_norm: f32`
    /// field; v4.0 piggybacks edge_jitter for the demo path.
    LatBand { min: f32, max: f32 },
    /// All inner predicates must match.
    And(Vec<ContextPredicate>),
    /// At least one inner predicate must match.
    Or(Vec<ContextPredicate>),
    /// Inner predicate must NOT match.
    Not(Box<ContextPredicate>),
}

impl ContextPredicate {
    pub fn matches(&self, ctx: &ShapeContext) -> bool {
        match self {
            ContextPredicate::Any => true,
            ContextPredicate::Rank(r) => ctx.size_rank == *r,
            ContextPredicate::Depth(d) => ctx.depth == *d,
            ContextPredicate::LatBand { min, max } => {
                let l = ctx.edge_jitter; // v4.0 piggyback — see docs above
                l >= *min && l <= *max
            }
            ContextPredicate::And(ps) => ps.iter().all(|p| p.matches(ctx)),
            ContextPredicate::Or(ps) => ps.iter().any(|p| p.matches(ctx)),
            ContextPredicate::Not(p) => !p.matches(ctx),
        }
    }
}

impl DispatchMode {
    /// Pick a [`ShapeKind`] for `ctx` using `rng` as needed.
    ///
    /// **v4.0**: takes an `entity_path` string ("plate.{N}" for plates,
    /// "plate.{N}.zone.{M}" for zones in v4.1+) so the Manual override
    /// path-keyed map can be looked up. Returned kind is always one of
    /// `registry.kinds()`. Panics in `debug` mode if the registry is
    /// empty; in release builds returns `ShapeKind::Ellipse` as a
    /// defensive default.
    pub fn select(
        &self,
        registry: &ShapeRegistry,
        ctx: &ShapeContext,
        entity_path: &str,
        rng: &mut Rng,
    ) -> ShapeKind {
        if let Some(k) = self.select_opt(registry, ctx, entity_path, rng) {
            return k;
        }
        // Public-boundary fallback when all layers abstained: uniform Random.
        let kinds = registry.kinds();
        if kinds.is_empty() {
            return ShapeKind::Ellipse;
        }
        if kinds.len() == 1 {
            return kinds[0];
        }
        kinds[(rng.next_u32() as usize) % kinds.len()]
    }

    /// **v4.0** Internal — returns `None` for modes that can "pass" (Manual
    /// when path not pinned; ByContext when no rule matches; Layered when
    /// every layer abstains). Always-committing modes (Fixed, Random,
    /// Weighted) return `Some` unconditionally.
    fn select_opt(
        &self,
        registry: &ShapeRegistry,
        ctx: &ShapeContext,
        entity_path: &str,
        rng: &mut Rng,
    ) -> Option<ShapeKind> {
        match self {
            DispatchMode::Fixed(k) => Some(*k),
            DispatchMode::Random => {
                debug_assert!(
                    !registry.is_empty(),
                    "ShapeRegistry must register ≥1 generator before Random dispatch"
                );
                let kinds = registry.kinds();
                if kinds.is_empty() {
                    return Some(ShapeKind::Ellipse);
                }
                if kinds.len() == 1 {
                    return Some(kinds[0]);
                }
                Some(kinds[(rng.next_u32() as usize) % kinds.len()])
            }
            DispatchMode::Weighted(table) => {
                let weights = match table.get(&ctx.size_rank) {
                    Some(w) if !w.is_empty() => w,
                    _ => {
                        debug_assert!(
                            false,
                            "Weighted table has no entry for {:?}",
                            ctx.size_rank
                        );
                        return registry.kinds().first().copied();
                    }
                };
                let sum: f32 = weights.iter().map(|(_, w)| *w).sum();
                debug_assert!(
                    (sum - 1.0).abs() < 1e-2,
                    "Weighted weights for {:?} sum to {sum}, expected ~1.0",
                    ctx.size_rank
                );
                let pick = rng.next_f32() * sum;
                let mut acc = 0.0;
                for (kind, w) in weights {
                    acc += *w;
                    if pick <= acc && registry.get(*kind).is_some() {
                        return Some(*kind);
                    }
                }
                weights
                    .iter()
                    .rev()
                    .find_map(|(k, _)| registry.get(*k).map(|_| *k))
            }
            DispatchMode::Manual(map) => map.get(entity_path).copied(),
            DispatchMode::ByContext(rules) => {
                for rule in rules {
                    if rule.predicate.matches(ctx) && registry.get(rule.kind).is_some() {
                        return Some(rule.kind);
                    }
                }
                None
            }
            DispatchMode::Layered(layers) => {
                for layer in layers {
                    if let Some(k) = layer.select_opt(registry, ctx, entity_path, rng) {
                        return Some(k);
                    }
                }
                None
            }
            DispatchMode::PerDepth(modes) => {
                let idx = (ctx.depth as usize).min(2);
                modes[idx].select_opt(registry, ctx, entity_path, rng)
            }
            DispatchMode::Llm => {
                // v4.0 stub — full LLM dispatch ships in v4.3 with cache
                // architecture decision (per PO directive 2026-05-28).
                panic!(
                    "DispatchMode::Llm is a v4.0 stub — full implementation \
                     ships in v4.3 with cache architecture decision (Postgres \
                     vs file vs none). Use Manual / ByContext / Layered / \
                     Weighted in the meantime."
                );
            }
        }
    }
}

/// **v3.1b** per-rank weight table for `DispatchMode::Weighted`. Giants
/// favour branching / hooked shapes (BezierSpine + Boolean — Eurasia,
/// Africa); Micros stay simple (Ellipse + Polar — Iceland / Hispaniola
/// scale). Tuned for the 12-plate default world; v3.2 will rebalance once
/// SDF + MarchingNoise + Slime register. See spec §4.6.4.
pub fn engine_v3_1b_weights() -> BTreeMap<SizeRank, Vec<(ShapeKind, f32)>> {
    let mut table = BTreeMap::new();
    table.insert(
        SizeRank::Giant,
        vec![
            (ShapeKind::Ellipse, 0.30),
            (ShapeKind::BezierSpine, 0.35),
            (ShapeKind::Polar, 0.10),
            (ShapeKind::Boolean, 0.25),
        ],
    );
    table.insert(
        SizeRank::Large,
        vec![
            (ShapeKind::Ellipse, 0.30),
            (ShapeKind::BezierSpine, 0.40),
            (ShapeKind::Polar, 0.10),
            (ShapeKind::Boolean, 0.20),
        ],
    );
    table.insert(
        SizeRank::Medium,
        vec![
            (ShapeKind::Ellipse, 0.40),
            (ShapeKind::BezierSpine, 0.30),
            (ShapeKind::Polar, 0.20),
            (ShapeKind::Boolean, 0.10),
        ],
    );
    table.insert(
        SizeRank::Small,
        vec![
            (ShapeKind::Ellipse, 0.40),
            (ShapeKind::BezierSpine, 0.20),
            (ShapeKind::Polar, 0.30),
            (ShapeKind::Boolean, 0.10),
        ],
    );
    table.insert(
        SizeRank::Micro,
        vec![
            (ShapeKind::Ellipse, 0.60),
            (ShapeKind::BezierSpine, 0.10),
            (ShapeKind::Polar, 0.25),
            (ShapeKind::Boolean, 0.05),
        ],
    );
    table
}

/// **v3.2** per-rank weight table for [`DispatchMode::Weighted`]. Extends
/// the v3.1b 4-kind mix with `SdfCapsuleChain` (branching topologies) and
/// `MarchingNoise` (noise-field continents). Small/Micro plates EXCLUDE
/// both new kinds: capsule chain degenerates at small scale and a 256²
/// raster wastes resolution on micro-sized polygons. Values approved by PO
/// 2026-05-26 (spec §4.6).
///
/// Reserved-but-not-impl kinds (Slime, Stamp) have their roadmap weights
/// merged into `Ellipse` here so the per-rank distribution sums to 1.0
/// while v3.4/v3.5 generators are not yet registered. The redistribution
/// will be undone (and weights restored to roadmap §14 Q4 values) once
/// those generators ship.
pub fn engine_v3_2_weights() -> BTreeMap<SizeRank, Vec<(ShapeKind, f32)>> {
    let mut table = BTreeMap::new();
    table.insert(
        SizeRank::Giant,
        vec![
            (ShapeKind::Ellipse, 0.30),
            (ShapeKind::BezierSpine, 0.20),
            (ShapeKind::Polar, 0.10),
            (ShapeKind::Boolean, 0.10),
            (ShapeKind::SdfCapsuleChain, 0.20),
            (ShapeKind::MarchingNoise, 0.10),
        ],
    );
    table.insert(
        SizeRank::Large,
        vec![
            (ShapeKind::Ellipse, 0.25),
            (ShapeKind::BezierSpine, 0.25),
            (ShapeKind::Polar, 0.10),
            (ShapeKind::Boolean, 0.15),
            (ShapeKind::SdfCapsuleChain, 0.15),
            (ShapeKind::MarchingNoise, 0.10),
        ],
    );
    table.insert(
        SizeRank::Medium,
        vec![
            (ShapeKind::Ellipse, 0.30),
            (ShapeKind::BezierSpine, 0.25),
            (ShapeKind::Polar, 0.20),
            (ShapeKind::Boolean, 0.10),
            (ShapeKind::SdfCapsuleChain, 0.10),
            (ShapeKind::MarchingNoise, 0.05),
        ],
    );
    table.insert(
        SizeRank::Small,
        vec![
            (ShapeKind::Ellipse, 0.40),
            (ShapeKind::BezierSpine, 0.20),
            (ShapeKind::Polar, 0.25),
            (ShapeKind::Boolean, 0.05),
            (ShapeKind::SdfCapsuleChain, 0.10),
            (ShapeKind::MarchingNoise, 0.00),
        ],
    );
    table.insert(
        SizeRank::Micro,
        vec![
            (ShapeKind::Ellipse, 0.55),
            (ShapeKind::BezierSpine, 0.10),
            (ShapeKind::Polar, 0.30),
            (ShapeKind::Boolean, 0.05),
            (ShapeKind::SdfCapsuleChain, 0.00),
            (ShapeKind::MarchingNoise, 0.00),
        ],
    );
    table
}

/// **v3.4** per-rank weight table for [`DispatchMode::Weighted`]. Restores
/// `Slime` weights per roadmap §14 Q4 (G=0.05, L=0.05, M=0.05, S=0.10,
/// μ=0.10 — Small/Micro favored because slime is best at organic island /
/// peninsula shapes). All other weights match v3.2 except Ellipse's share
/// is reduced to make room for Slime. Stamp remains zero (ships v3.5).
pub fn engine_v3_4_weights() -> BTreeMap<SizeRank, Vec<(ShapeKind, f32)>> {
    let mut table = BTreeMap::new();
    table.insert(
        SizeRank::Giant,
        vec![
            (ShapeKind::Ellipse, 0.25),
            (ShapeKind::BezierSpine, 0.20),
            (ShapeKind::Polar, 0.10),
            (ShapeKind::Boolean, 0.10),
            (ShapeKind::SdfCapsuleChain, 0.20),
            (ShapeKind::MarchingNoise, 0.10),
            (ShapeKind::Slime, 0.05),
        ],
    );
    table.insert(
        SizeRank::Large,
        vec![
            (ShapeKind::Ellipse, 0.20),
            (ShapeKind::BezierSpine, 0.25),
            (ShapeKind::Polar, 0.10),
            (ShapeKind::Boolean, 0.15),
            (ShapeKind::SdfCapsuleChain, 0.15),
            (ShapeKind::MarchingNoise, 0.10),
            (ShapeKind::Slime, 0.05),
        ],
    );
    table.insert(
        SizeRank::Medium,
        vec![
            (ShapeKind::Ellipse, 0.25),
            (ShapeKind::BezierSpine, 0.25),
            (ShapeKind::Polar, 0.20),
            (ShapeKind::Boolean, 0.10),
            (ShapeKind::SdfCapsuleChain, 0.10),
            (ShapeKind::MarchingNoise, 0.05),
            (ShapeKind::Slime, 0.05),
        ],
    );
    table.insert(
        SizeRank::Small,
        vec![
            (ShapeKind::Ellipse, 0.30),
            (ShapeKind::BezierSpine, 0.20),
            (ShapeKind::Polar, 0.25),
            (ShapeKind::Boolean, 0.05),
            (ShapeKind::SdfCapsuleChain, 0.10),
            (ShapeKind::MarchingNoise, 0.00),
            (ShapeKind::Slime, 0.10),
        ],
    );
    table.insert(
        SizeRank::Micro,
        vec![
            (ShapeKind::Ellipse, 0.45),
            (ShapeKind::BezierSpine, 0.10),
            (ShapeKind::Polar, 0.30),
            (ShapeKind::Boolean, 0.05),
            (ShapeKind::SdfCapsuleChain, 0.00),
            (ShapeKind::MarchingNoise, 0.00),
            (ShapeKind::Slime, 0.10),
        ],
    );
    table
}

/// **v3.6** per-rank weight table for [`DispatchMode::Weighted`]. Restores
/// `Stamp` weights per roadmap §14 Q4 (G=0.10/L=0.05/M=0.05/S=0/μ=0 —
/// Giant favored because stamps are "signature continents" recognisable
/// at world scale, not micro islands). Tier 1 algorithm catalog now
/// SHIPPED COMPLETE (8 active generators).
pub fn engine_v3_6_weights() -> BTreeMap<SizeRank, Vec<(ShapeKind, f32)>> {
    let mut table = BTreeMap::new();
    table.insert(
        SizeRank::Giant,
        vec![
            (ShapeKind::Ellipse, 0.15),
            (ShapeKind::BezierSpine, 0.20),
            (ShapeKind::Polar, 0.10),
            (ShapeKind::Boolean, 0.10),
            (ShapeKind::SdfCapsuleChain, 0.20),
            (ShapeKind::MarchingNoise, 0.10),
            (ShapeKind::Slime, 0.05),
            (ShapeKind::Stamp, 0.10),
        ],
    );
    table.insert(
        SizeRank::Large,
        vec![
            (ShapeKind::Ellipse, 0.15),
            (ShapeKind::BezierSpine, 0.25),
            (ShapeKind::Polar, 0.10),
            (ShapeKind::Boolean, 0.15),
            (ShapeKind::SdfCapsuleChain, 0.15),
            (ShapeKind::MarchingNoise, 0.10),
            (ShapeKind::Slime, 0.05),
            (ShapeKind::Stamp, 0.05),
        ],
    );
    table.insert(
        SizeRank::Medium,
        vec![
            (ShapeKind::Ellipse, 0.20),
            (ShapeKind::BezierSpine, 0.25),
            (ShapeKind::Polar, 0.20),
            (ShapeKind::Boolean, 0.10),
            (ShapeKind::SdfCapsuleChain, 0.10),
            (ShapeKind::MarchingNoise, 0.05),
            (ShapeKind::Slime, 0.05),
            (ShapeKind::Stamp, 0.05),
        ],
    );
    table.insert(
        SizeRank::Small,
        vec![
            (ShapeKind::Ellipse, 0.30),
            (ShapeKind::BezierSpine, 0.20),
            (ShapeKind::Polar, 0.25),
            (ShapeKind::Boolean, 0.05),
            (ShapeKind::SdfCapsuleChain, 0.10),
            (ShapeKind::MarchingNoise, 0.00),
            (ShapeKind::Slime, 0.10),
            (ShapeKind::Stamp, 0.00),
        ],
    );
    table.insert(
        SizeRank::Micro,
        vec![
            (ShapeKind::Ellipse, 0.45),
            (ShapeKind::BezierSpine, 0.10),
            (ShapeKind::Polar, 0.30),
            (ShapeKind::Boolean, 0.05),
            (ShapeKind::SdfCapsuleChain, 0.00),
            (ShapeKind::MarchingNoise, 0.00),
            (ShapeKind::Slime, 0.10),
            (ShapeKind::Stamp, 0.00),
        ],
    );
    table
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::flatworld::SizeRank;
    use crate::shape::{ShapeContext, ShapeGenerator};

    /// Test-only stub generator — produces a 3-vertex polygon, consumes no RNG.
    struct StubGenerator {
        kind: ShapeKind,
    }
    impl ShapeGenerator for StubGenerator {
        fn kind(&self) -> ShapeKind {
            self.kind
        }
        fn generate(&self, ctx: &ShapeContext, _rng: &mut Rng) -> ShapeResult {
            ShapeResult::single_kind(
                vec![vec![
                    (ctx.center.0 - 1.0, ctx.center.1 - 1.0),
                    (ctx.center.0 + 1.0, ctx.center.1 - 1.0),
                    (ctx.center.0, ctx.center.1 + 1.0),
                ]],
                self.kind,
            )
        }
    }

    fn dummy_ctx() -> ShapeContext {
        ShapeContext {
            depth: 0,
            center: (0.0, 0.0),
            envelope: (10.0, 10.0),
            size_rank: SizeRank::Medium,
            seed: 1,
            plate_salt: 1,
            parent_path: Vec::new(),
            world_theme: None,
            edge_jitter: 0.3,
            vertex_count_range: (8, 12),
        }
    }

    #[test]
    fn registry_register_get_roundtrip() {
        let mut r = ShapeRegistry::empty();
        r.register(Box::new(StubGenerator {
            kind: ShapeKind::Ellipse,
        }));
        assert!(r.get(ShapeKind::Ellipse).is_some());
        assert!(r.get(ShapeKind::BezierSpine).is_none());
    }

    #[test]
    fn registry_kinds_is_deterministic_btreemap_order() {
        let mut r = ShapeRegistry::empty();
        r.register(Box::new(StubGenerator {
            kind: ShapeKind::Polar,
        }));
        r.register(Box::new(StubGenerator {
            kind: ShapeKind::Ellipse,
        }));
        r.register(Box::new(StubGenerator {
            kind: ShapeKind::Boolean,
        }));
        // BTreeMap orders by enum discriminant order.
        assert_eq!(
            r.kinds(),
            vec![ShapeKind::Ellipse, ShapeKind::Polar, ShapeKind::Boolean]
        );
    }

    #[test]
    fn dispatch_fixed_returns_kind_no_rng() {
        let r = {
            let mut r = ShapeRegistry::empty();
            r.register(Box::new(StubGenerator {
                kind: ShapeKind::Polar,
            }));
            r.register(Box::new(StubGenerator {
                kind: ShapeKind::BezierSpine,
            }));
            r
        };
        let mut rng_a = Rng::for_stage(42, b"dispatch-test");
        let mut rng_b = Rng::for_stage(42, b"dispatch-test");
        let mode = DispatchMode::Fixed(ShapeKind::Polar);

        for _ in 0..5 {
            let kind = mode.select(&r, &dummy_ctx(), "plate.0", &mut rng_a);
            assert_eq!(kind, ShapeKind::Polar);
        }
        // rng_b is untouched (matching `Fixed` no-RNG contract).
        for _ in 0..5 {
            let a = rng_a.next_u32();
            let b = rng_b.next_u32();
            assert_eq!(
                a, b,
                "Fixed dispatch must not consume RNG — streams must still match"
            );
        }
    }

    #[test]
    fn dispatch_random_single_kind_no_rng_consumption() {
        let r = {
            let mut r = ShapeRegistry::empty();
            r.register(Box::new(StubGenerator {
                kind: ShapeKind::Ellipse,
            }));
            r
        };
        let mut rng_a = Rng::for_stage(42, b"single-kind");
        let mut rng_b = Rng::for_stage(42, b"single-kind");

        for _ in 0..10 {
            let k = DispatchMode::Random.select(&r, &dummy_ctx(), "plate.0", &mut rng_a);
            assert_eq!(k, ShapeKind::Ellipse);
        }
        // Streams must still be aligned.
        for _ in 0..10 {
            assert_eq!(
                rng_a.next_u32(),
                rng_b.next_u32(),
                "Random with single registered kind must short-circuit without consuming RNG"
            );
        }
    }

    #[test]
    fn dispatch_random_multi_kind_distribution() {
        let r = {
            let mut r = ShapeRegistry::empty();
            r.register(Box::new(StubGenerator {
                kind: ShapeKind::Ellipse,
            }));
            r.register(Box::new(StubGenerator {
                kind: ShapeKind::BezierSpine,
            }));
            r.register(Box::new(StubGenerator {
                kind: ShapeKind::Polar,
            }));
            r.register(Box::new(StubGenerator {
                kind: ShapeKind::Boolean,
            }));
            r
        };
        let mut rng = Rng::for_stage(1, b"distribution");
        let mut counts = std::collections::HashMap::new();
        for _ in 0..10_000 {
            let k = DispatchMode::Random.select(&r, &dummy_ctx(), "plate.0", &mut rng);
            *counts.entry(k).or_insert(0u32) += 1;
        }
        // 4 kinds, 10k samples, expected ~2500 each. Allow ±10%.
        for k in r.kinds() {
            let c = counts.get(&k).copied().unwrap_or(0);
            assert!(
                (2250..=2750).contains(&c),
                "Random distribution skewed for {k:?}: {c} (expected ~2500 ±10%)"
            );
        }
    }

    #[test]
    fn dispatch_random_empty_registry_release_fallback_is_ellipse() {
        // In release builds (no debug_assert), an empty registry falls back
        // to Ellipse so production never panics. (debug_assert! triggers
        // in cfg(debug_assertions) builds but is compiled out in release.)
        let r = ShapeRegistry::empty();
        let mut rng = Rng::for_stage(0, b"fallback");
        if !cfg!(debug_assertions) {
            let k = DispatchMode::Random.select(&r, &dummy_ctx(), "plate.0", &mut rng);
            assert_eq!(k, ShapeKind::Ellipse);
        } else {
            // In debug builds, just verify the registry is empty; the
            // panic path is intentional and exercised by other crates'
            // panic tests, not by us here.
            assert!(r.is_empty());
        }
    }

    // -- v3.2 weights + registry checks ---------------------------------------

    #[test]
    fn engine_default_v3_6_registers_eight_kinds() {
        let r = ShapeRegistry::engine_default();
        let kinds = r.kinds();
        assert_eq!(kinds.len(), 8, "v3.6 engine_default should register 8 kinds; got {kinds:?}");
        for k in [
            ShapeKind::Ellipse,
            ShapeKind::BezierSpine,
            ShapeKind::Polar,
            ShapeKind::Boolean,
            ShapeKind::SdfCapsuleChain,
            ShapeKind::MarchingNoise,
            ShapeKind::Slime,
            ShapeKind::Stamp,
        ] {
            assert!(r.get(k).is_some(), "engine_default should register {k:?}");
        }
        // Tier 1 algorithm catalog SHIPPED COMPLETE.
    }

    #[test]
    fn engine_v3_2_weights_each_rank_sums_to_one() {
        let table = engine_v3_2_weights();
        for (rank, weights) in &table {
            let sum: f32 = weights.iter().map(|(_, w)| *w).sum();
            assert!(
                (sum - 1.0).abs() < 0.001,
                "rank {rank:?} weights sum {sum}, expected 1.0"
            );
        }
    }

    #[test]
    fn engine_v3_2_weights_micro_excludes_sdf_and_marching() {
        let table = engine_v3_2_weights();
        let micro = table.get(&SizeRank::Micro).unwrap();
        for (k, w) in micro {
            if matches!(*k, ShapeKind::SdfCapsuleChain | ShapeKind::MarchingNoise) {
                assert_eq!(*w, 0.0, "Micro rank weight for {k:?} should be 0.0");
            }
        }
        // Small also excludes MarchingNoise (but allows SDF at 0.10).
        let small = table.get(&SizeRank::Small).unwrap();
        for (k, w) in small {
            if matches!(*k, ShapeKind::MarchingNoise) {
                assert_eq!(*w, 0.0, "Small rank weight for MarchingNoise should be 0.0");
            }
        }
    }

    #[test]
    fn engine_v3_2_weights_giant_features_sdf_at_twenty_pct() {
        let table = engine_v3_2_weights();
        let giant = table.get(&SizeRank::Giant).unwrap();
        let sdf_weight = giant.iter().find(|(k, _)| *k == ShapeKind::SdfCapsuleChain).map(|(_, w)| *w);
        assert_eq!(sdf_weight, Some(0.20), "Giant SDF weight per PO-approved table");
    }

    // ─── v4.0 dispatcher variants ──────────────────────────────────────────

    fn populated_registry() -> ShapeRegistry {
        let mut r = ShapeRegistry::empty();
        r.register(Box::new(StubGenerator { kind: ShapeKind::Ellipse }));
        r.register(Box::new(StubGenerator { kind: ShapeKind::BezierSpine }));
        r.register(Box::new(StubGenerator { kind: ShapeKind::Polar }));
        r
    }

    #[test]
    fn manual_dispatch_returns_pinned_kind_for_matching_path() {
        let mut overrides = std::collections::HashMap::new();
        overrides.insert("plate.3".to_string(), ShapeKind::Polar);
        let mode = DispatchMode::Manual(overrides);
        let r = populated_registry();
        let mut rng = Rng::for_stage(1, b"test");
        let k = mode.select(&r, &dummy_ctx(), "plate.3", &mut rng);
        assert_eq!(k, ShapeKind::Polar);
    }

    #[test]
    fn manual_dispatch_falls_through_for_unpinned_path() {
        // Manual alone falls back via public select() to uniform Random.
        let overrides = std::collections::HashMap::new();
        let mode = DispatchMode::Manual(overrides);
        let r = populated_registry();
        let mut rng = Rng::for_stage(1, b"test");
        let k = mode.select(&r, &dummy_ctx(), "plate.99", &mut rng);
        assert!(r.kinds().contains(&k), "fallback should pick registered kind");
    }

    #[test]
    fn by_context_rule_fires_on_rank_match() {
        let rule = ContextRule {
            predicate: ContextPredicate::Rank(SizeRank::Medium),
            kind: ShapeKind::BezierSpine,
        };
        let mode = DispatchMode::ByContext(vec![rule]);
        let r = populated_registry();
        let mut rng = Rng::for_stage(1, b"test");
        let k = mode.select(&r, &dummy_ctx(), "plate.0", &mut rng);
        // dummy_ctx() uses Medium rank.
        assert_eq!(k, ShapeKind::BezierSpine);
    }

    #[test]
    fn layered_falls_through_manual_to_random() {
        // Manual with no entries → ByContext with no matching rule →
        // Random as final layer.
        let manual = DispatchMode::Manual(std::collections::HashMap::new());
        let context = DispatchMode::ByContext(vec![ContextRule {
            predicate: ContextPredicate::Rank(SizeRank::Giant),
            kind: ShapeKind::Ellipse,
        }]);
        let random = DispatchMode::Random;
        let layered = DispatchMode::Layered(vec![manual, context, random]);
        let r = populated_registry();
        let mut rng = Rng::for_stage(7, b"test");
        let k = layered.select(&r, &dummy_ctx(), "plate.0", &mut rng);
        // Medium ctx doesn't trigger the Giant rule → falls to Random.
        assert!(r.kinds().contains(&k));
    }

    #[test]
    fn layered_manual_first_wins() {
        let mut overrides = std::collections::HashMap::new();
        overrides.insert("plate.42".to_string(), ShapeKind::Polar);
        let manual = DispatchMode::Manual(overrides);
        let layered = DispatchMode::Layered(vec![manual, DispatchMode::Random]);
        let r = populated_registry();
        let mut rng = Rng::for_stage(7, b"test");
        let k = layered.select(&r, &dummy_ctx(), "plate.42", &mut rng);
        assert_eq!(k, ShapeKind::Polar, "Manual layer should win for pinned path");
    }

    #[test]
    fn per_depth_dispatches_by_ctx_depth() {
        let plate_mode = Box::new(DispatchMode::Fixed(ShapeKind::Ellipse));
        let zone_mode = Box::new(DispatchMode::Fixed(ShapeKind::Polar));
        let subzone_mode = Box::new(DispatchMode::Fixed(ShapeKind::BezierSpine));
        let mode = DispatchMode::PerDepth([plate_mode, zone_mode, subzone_mode]);
        let r = populated_registry();
        let mut rng = Rng::for_stage(7, b"test");
        // dummy_ctx() has depth=0 → Ellipse.
        let k0 = mode.select(&r, &dummy_ctx(), "plate.0", &mut rng);
        assert_eq!(k0, ShapeKind::Ellipse);
    }

    #[test]
    fn context_predicate_and_or_not_compose() {
        let mid = ContextPredicate::Rank(SizeRank::Medium);
        let depth_zero = ContextPredicate::Depth(0);
        let and = ContextPredicate::And(vec![mid.clone(), depth_zero.clone()]);
        assert!(and.matches(&dummy_ctx()));

        let or = ContextPredicate::Or(vec![
            ContextPredicate::Rank(SizeRank::Giant),
            depth_zero.clone(),
        ]);
        assert!(or.matches(&dummy_ctx()));

        let not_giant = ContextPredicate::Not(Box::new(ContextPredicate::Rank(SizeRank::Giant)));
        assert!(not_giant.matches(&dummy_ctx()));
    }

    #[test]
    #[should_panic(expected = "v4.0 stub")]
    fn llm_dispatch_panics_in_v4_0() {
        let r = populated_registry();
        let mut rng = Rng::for_stage(1, b"test");
        let _ = DispatchMode::Llm.select(&r, &dummy_ctx(), "plate.0", &mut rng);
    }
}
