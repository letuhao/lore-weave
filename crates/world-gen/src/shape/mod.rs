//! Shape generation module — multi-algorithm polygon generation for plates,
//! zones, and sub-zones. Introduced in **v3.1a** (foundation; Ellipse only).
//!
//! Roadmap path: v3.1a (this) → v3.1b (Bezier/Polar/Boolean) → v3.2 (SDF +
//! marching squares) → v3.3 (multi-component) → v3.4 (slime) → v3.5 (stamps)
//! → v4.0 (full DispatchMode set) → v4.1+ (zone + sub-zone application).
//!
//! Spec: `docs/specs/2026-05-25-flatworld-v3-1-shape-dispatcher.md`.
//!
//! ## Core types
//!
//! - [`ShapeKind`] — enum of the 8 reserved algorithm tags.
//! - [`ShapeContext`] — per-shape input bundle (depth, center, envelope,
//!   size_rank, seed, jitter, vertex_count_range, plate_salt).
//! - [`ShapeGenerator`] — trait every algorithm impl satisfies.
//! - [`Polygon`] — re-export of `flatworld::Polygon` (closed ring of
//!   `(f32, f32)` vertices, ordered counter-clockwise around its centre).
//!
//! See [`dispatch`] for [`ShapeRegistry`] and [`DispatchMode`] (the wire-up).
//! See [`ellipse`] for the v3.0 algorithm extracted as [`ellipse::EllipseGenerator`].

pub mod anthropic;
pub mod coastline;
pub mod csg;
pub mod dispatch;
pub mod ellipse;
pub mod llm;
pub mod ollama;
pub mod openai;
pub mod polar;
pub mod postgres_cache;
pub mod raster;
pub mod sdf;
pub mod slime;
pub mod spine;
pub mod stamp;

pub use coastline::{FractalizeConfig, fractalize_polygon};
pub use csg::{BooleanGenerator, BooleanTemplate};
pub use dispatch::{
    DispatchMode, ShapeRegistry, engine_v3_1b_weights, engine_v3_2_weights,
    engine_v3_4_weights, engine_v3_6_weights,
};
pub use ellipse::EllipseGenerator;
pub use anthropic::AnthropicProvider;
pub use llm::{
    DispatchCache, InMemoryDispatchCache, LlmDecision, LlmError, LlmProvider, LlmPrompt,
    MockLlmProvider, MockTextProvider, TextPrompt, TextProvider,
};
pub use ollama::OllamaProvider;
pub use openai::OpenAIProvider;
pub use postgres_cache::{PostgresCacheError, PostgresDispatchCache};
pub use polar::{PolarGenerator, PolarTemplate};
pub use raster::MarchingNoiseGenerator;
pub use sdf::{CapsuleTemplate, SdfCapsuleChainGenerator};
pub use slime::{SlimeGenerator, SlimeTemplate};
pub use spine::{BezierSpineGenerator, BezierTemplate};
pub use stamp::{StampGenerator, StampTemplate};

use crate::flatworld::{Polygon, SizeRank};
use crate::rng::Rng;

/// Tag identifying which algorithm produced a polygon. Stored on
/// `flatworld::Plate.shape_kind` from v3.1a onward.
///
/// `Ellipse` is the only variant actually implemented in v3.1a; the rest
/// are reserved so the enum's serde shape is stable across v3.1b → v3.5.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, serde::Serialize, serde::Deserialize)]
pub enum ShapeKind {
    /// Anisotropic ellipsoid + multi-octave fbm warp (v3.0 default, v3.1a impl).
    Ellipse,
    /// Cubic Bezier spine + variable-radius sweep (v3.1b impl).
    BezierSpine,
    /// Polar / superformula closed curve (v3.1b impl).
    Polar,
    /// Boolean polygon ops (union / difference / intersection) via geo-clipper
    /// (v3.1b impl).
    Boolean,
    /// Signed-distance capsule chain + smooth-min (v3.2 reserved).
    SdfCapsuleChain,
    /// Marching-squares contour of a noise field (v3.2 / v3.3 reserved).
    MarchingNoise,
    /// Multi-agent slime / Physarum walk + concave hull (v3.4 reserved).
    Slime,
    /// Hand-authored stamp polygon (v3.5 reserved).
    Stamp,
}

impl ShapeKind {
    /// Stable string tag (for logs, debug renders, eval per-kind metrics).
    pub fn as_str(self) -> &'static str {
        match self {
            ShapeKind::Ellipse => "Ellipse",
            ShapeKind::BezierSpine => "BezierSpine",
            ShapeKind::Polar => "Polar",
            ShapeKind::Boolean => "Boolean",
            ShapeKind::SdfCapsuleChain => "SdfCapsuleChain",
            ShapeKind::MarchingNoise => "MarchingNoise",
            ShapeKind::Slime => "Slime",
            ShapeKind::Stamp => "Stamp",
        }
    }
}

impl Default for ShapeKind {
    /// `Ellipse` — preserves v3.0 behaviour when a default Plate is
    /// constructed (e.g. JSON deserialise of a pre-v3.1a sidecar).
    fn default() -> Self {
        ShapeKind::Ellipse
    }
}

/// Input bundle a [`ShapeGenerator`] receives. Generators read `ctx` +
/// consume `rng` to produce 1+ closed polygons rendered around `center`,
/// fitting within `envelope`.
///
/// At each pipeline depth the meaning of `envelope` and `parent_path` shifts:
///
/// | depth | envelope | parent_path |
/// |------:|----------|-------------|
/// | 0 (plate)   | `(pitch, pitch)` | `[]` |
/// | 1 (zone)    | parent plate bbox half-extents | `[plate_id]` |
/// | 2 (subzone) | parent zone bbox half-extents | `[plate_id, zone_id]` |
#[derive(Debug, Clone)]
pub struct ShapeContext {
    /// 0 = plate, 1 = zone (v4.1+), 2 = subzone (v4.2+).
    pub depth: u32,
    /// World-space centre the generated polygon is anchored at.
    pub center: (f32, f32),
    /// Maximum (x, y) extent the polygon should occupy from its centre.
    /// For plates this is `(pitch, pitch)` where pitch is the world's
    /// nominal grid spacing `sqrt(area / plate_count)`.
    pub envelope: (f32, f32),
    /// Drives per-rank parameter bands (radius, aspect, etc.).
    pub size_rank: SizeRank,
    /// Per-shape RNG seed (matches `Plate::shape_seed`). Generators that
    /// need an *internal* RNG (independent of the caller's stream) MUST
    /// derive it from this via `Rng::for_stage(seed as u64, b"<algo-tag>")`;
    /// generators that share the caller's stream (e.g. Ellipse for byte-
    /// identical compat) consume `rng` directly in the documented order.
    pub seed: u32,
    /// fbm noise salt preserved from v3.0's per-plate `plate_salt`
    /// derivation so the Ellipse extraction is bit-identical post-refactor.
    /// Non-Ellipse generators may ignore this.
    pub plate_salt: u32,
    /// Hierarchy path. `[]` for plates, `[plate_id]` for zones, etc.
    pub parent_path: Vec<usize>,
    /// Optional theme hint for LLM dispatch (v4.3+); ignored in v3.1.
    pub world_theme: Option<&'static str>,
    /// Per-vertex jitter magnitude `[0, 1]`. The Ellipse generator routes
    /// this into the same residual-shrink formula as v3.0.
    pub edge_jitter: f32,
    /// Inclusive vertex-count range. Generators clamp to `[3, range.1.max(3)]`.
    pub vertex_count_range: (usize, usize),
    /// **v4.3b** typed parameter override. When `Some(ParamOverride::Foo {..})`
    /// is set AND the dispatched generator matches `Foo`, the generator
    /// reads the override fields. Non-matching variants are ignored;
    /// generators without override support drop this silently. Populated
    /// by `DispatchMode::Llm` from its provider's [`LlmDecision`]; all
    /// non-LLM modes leave it `None`.
    pub params: Option<ParamOverride>,
}

/// **v4.3b** typed parameter override returned by [`LlmProvider::pick`]
/// alongside a `ShapeKind`. One variant per generator that exposes
/// LLM-tunable knobs. Variants are intentionally minimal in v4.3b —
/// they cover the load-bearing creative knobs only:
///
/// - [`ParamOverride::Ellipse`] — `aspect_ratio` (1.0 = circle, 2.0 = 2:1)
/// - [`ParamOverride::Boolean`] — template variant (Union / WedgeCut /
///   etc.) plus an optional `pieces_kept`
/// - [`ParamOverride::Stamp`] — `template_id` (selects which signature
///   continent silhouette to render)
///
/// Generators not listed here ignore params entirely in v4.3b; v4.3d
/// extends the enum as more generators get LLM-tunable knobs (Slime
/// template, SDF template, MarchingNoise island_count, Polar `m`).
#[derive(Debug, Clone)]
pub enum ParamOverride {
    Ellipse {
        /// Major / minor axis ratio. `1.0` = circle. Clamped to `[0.5,
        /// 3.0]` by the generator before use.
        aspect_ratio: Option<f32>,
    },
    Boolean {
        /// Pick a specific [`BooleanTemplate`] instead of the per-seed
        /// default selection.
        template: Option<crate::shape::csg::BooleanTemplate>,
    },
    Stamp {
        /// Pick a specific stamp template by zero-based index.
        /// Out-of-range falls back to the seed-driven default.
        template_id: Option<u32>,
    },
}

/// Output of [`ShapeGenerator::generate`]. Carries the rendered polygons
/// plus the **effective** [`ShapeKind`] — equal to `generator.kind()`
/// on the happy path, but possibly downgraded on a fallback (e.g.
/// [`BooleanGenerator`] returning a clean ellipse when `geo-clipper`
/// produces a degenerate result).
///
/// Plate / Zone / SubZone code stores `effective_kind` on
/// `Plate.shape_kind` so telemetry, downstream eval, and future LLM
/// dispatch see the kind that was **actually rendered**, not the kind the
/// dispatcher asked for.
#[derive(Debug, Clone)]
pub struct ShapeResult {
    pub polygons: Vec<Polygon>,
    pub effective_kind: ShapeKind,
}

impl ShapeResult {
    /// Build a result whose effective kind equals the requested kind.
    /// Use for happy-path generator returns.
    pub fn single_kind(polygons: Vec<Polygon>, kind: ShapeKind) -> Self {
        Self {
            polygons,
            effective_kind: kind,
        }
    }
}

/// Generate one or more closed polygons for a `ShapeContext`. Each impl
/// MUST be deterministic in `(ctx, rng)` and produce simple (non-self-
/// intersecting) polygons under typical jitter.
///
/// `Send + Sync` is required so `Box<dyn ShapeGenerator>` can live in a
/// shared [`ShapeRegistry`] across threads (rayon-friendly).
pub trait ShapeGenerator: Send + Sync {
    /// The kind tag — must match the [`ShapeKind`] variant this impl is
    /// registered under in a [`ShapeRegistry`].
    fn kind(&self) -> ShapeKind;

    /// Produce 1+ closed polygon rings.
    ///
    /// **v3.1 invariant:** every implementation MUST return exactly one
    /// component (`result.polygons.len() == 1`). Multi-component output
    /// (true archipelagos) is reserved for v3.3's marching-squares
    /// pipeline.
    ///
    /// `result.effective_kind` reports the kind that was actually rendered:
    /// equals `self.kind()` on the happy path; may differ on a fallback
    /// (currently only [`BooleanGenerator`] downgrades to `Ellipse` when
    /// `geo-clipper` fails).
    fn generate(&self, ctx: &ShapeContext, rng: &mut Rng) -> ShapeResult;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn shape_kind_all_variants_have_str_tags() {
        // Smoke test: each variant has a non-empty stable tag.
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
            let s = k.as_str();
            assert!(!s.is_empty(), "ShapeKind::{k:?} has empty tag");
        }
    }

    #[test]
    fn shape_kind_default_is_ellipse() {
        assert_eq!(ShapeKind::default(), ShapeKind::Ellipse);
    }

    #[test]
    fn shape_kind_serde_roundtrip() {
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
            let s = serde_json::to_string(&k).unwrap();
            let back: ShapeKind = serde_json::from_str(&s).unwrap();
            assert_eq!(k, back, "serde round-trip broke for {k:?}");
        }
    }
}
