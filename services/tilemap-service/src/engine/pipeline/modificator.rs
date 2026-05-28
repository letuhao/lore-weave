//! TMP_003 §2 — the `Modificator` trait + its execution context.

use crate::engine::build_state::TilemapBuildState;
use crate::registry::Registry;
use crate::seed::TilemapSeed;
use crate::types::template::TilemapTemplate;
use crate::types::tilemap::GridSize;

/// The execution context a [`Modificator`] pass operates on (TMP_003 §2.2,
/// spec D1).
///
/// Zone *placement* is read-only input (the placement engine already produced
/// the zones); a modificator mutates the shared [`TilemapBuildState`] — the
/// `TileState` grid, terrain layer, placed objects, distance oracle, and
/// per-zone build records. The engine is single-threaded (spec D4), so the
/// §2.2 per-(zone, modificator) instance model with `RwLock` state is not
/// needed — one `process` call iterates every zone.
///
/// V2 — `registry` carries the active TerrainKindDef / ObjectKindDef
/// dictionary. Modificators look up tag → primitive / footprint via
/// `ctx.registry.get_object(tag)` / `ctx.registry.get_terrain(tag)`.
#[derive(Debug)]
pub struct ModificatorContext<'a> {
    /// The authoring template — modificators read `ZoneSpec` detail (e.g.
    /// `terrain_types`, `treasure_tiers`) by zone id.
    pub template: &'a TilemapTemplate,
    pub grid: GridSize,
    pub seed: TilemapSeed,
    /// The mutable generation state — the `TileState` grid, terrain layer,
    /// `object_placements`, the nearest-object-distance oracle, and per-zone
    /// build records.
    pub state: &'a mut TilemapBuildState,
    /// V2 — the active terrain + object registry. Default is
    /// `Registry::load_default()` (lw: namespace); per-book registries
    /// override at `place_tilemap_with_registry` entry.
    pub registry: &'a Registry,
}

/// A single generation pass (TMP_003 §2 — the Strategy pattern, Gamma 1994).
///
/// **Phase-1 cut:** `process` takes `&self` (passes are stateless) and
/// dependencies are declared statically via [`Modificator::dependencies`]
/// rather than the §2 per-zone `init` hook. The thread-pool `Send + Sync`
/// bound is omitted — Phase 1 runs single-threaded (spec D6).
pub trait Modificator {
    /// Stable name — the topological-sort key and dependency-edge identifier.
    /// Names MUST be unique within a registry.
    fn name(&self) -> &str;

    /// Names of modificators this one must run *after*. A name not registered
    /// in the pipeline is treated as already satisfied (spec D7) — this is what
    /// lets a single-modificator pipeline run even though TerrainPainter
    /// declares dependencies on modificators that do not yet exist.
    fn dependencies(&self) -> Vec<&str> {
        Vec::new()
    }

    /// The generation step — mutates the build state in `ctx`.
    fn process(&self, ctx: &mut ModificatorContext<'_>) -> crate::Result<()>;
}
