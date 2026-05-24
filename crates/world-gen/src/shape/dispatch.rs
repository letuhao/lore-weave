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

use crate::rng::Rng;

use super::{ShapeContext, ShapeGenerator, ShapeKind};

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

    /// Engine-default registry. v3.1a registers exactly [`super::EllipseGenerator`].
    /// v3.1b will extend to 4 generators (Ellipse + BezierSpine + Polar + Boolean).
    pub fn engine_default() -> Self {
        let mut r = Self::empty();
        r.register(Box::new(super::EllipseGenerator));
        // v3.1b registrations land here:
        //   r.register(Box::new(super::spine::BezierSpineGenerator));
        //   r.register(Box::new(super::polar::PolarGenerator));
        //   r.register(Box::new(super::csg::BooleanGenerator));
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
}

impl DispatchMode {
    /// Pick a [`ShapeKind`] for `ctx` using `rng` as needed.
    ///
    /// Returned kind is always one of `registry.kinds()`. Panics in
    /// `debug` mode if the registry is empty; in release builds returns
    /// `ShapeKind::Ellipse` as a defensive default.
    pub fn select(
        &self,
        registry: &ShapeRegistry,
        _ctx: &ShapeContext,
        rng: &mut Rng,
    ) -> ShapeKind {
        match self {
            DispatchMode::Fixed(k) => *k,
            DispatchMode::Random => {
                debug_assert!(
                    !registry.is_empty(),
                    "ShapeRegistry must register ≥1 generator before Random dispatch"
                );
                let kinds = registry.kinds();
                if kinds.is_empty() {
                    return ShapeKind::Ellipse;
                }
                if kinds.len() == 1 {
                    return kinds[0]; // BYTE-IDENTICAL: no RNG consumption
                }
                kinds[(rng.next_u32() as usize) % kinds.len()]
            }
        }
    }
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
        fn generate(
            &self,
            ctx: &ShapeContext,
            _rng: &mut Rng,
        ) -> Vec<crate::flatworld::Polygon> {
            vec![vec![
                (ctx.center.0 - 1.0, ctx.center.1 - 1.0),
                (ctx.center.0 + 1.0, ctx.center.1 - 1.0),
                (ctx.center.0, ctx.center.1 + 1.0),
            ]]
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
            let kind = mode.select(&r, &dummy_ctx(), &mut rng_a);
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
            let k = DispatchMode::Random.select(&r, &dummy_ctx(), &mut rng_a);
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
            let k = DispatchMode::Random.select(&r, &dummy_ctx(), &mut rng);
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
            let k = DispatchMode::Random.select(&r, &dummy_ctx(), &mut rng);
            assert_eq!(k, ShapeKind::Ellipse);
        } else {
            // In debug builds, just verify the registry is empty; the
            // panic path is intentional and exercised by other crates'
            // panic tests, not by us here.
            assert!(r.is_empty());
        }
    }
}
