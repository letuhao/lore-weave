//! TMP_003 §2 — the `Modificator` trait + its execution context.

use crate::engine::placement::ZoneTiles;
use crate::seed::TilemapSeed;
use crate::types::template::TilemapTemplate;
use crate::types::tile::TerrainKind;
use crate::types::tilemap::GridSize;

/// Mutable build state a [`Modificator`] pass operates on.
///
/// **Phase-1 shape:** zone *placement* is read-only input (the placement engine
/// already produced `zones`); modificators write the tilemap-wide
/// `terrain_layer` and the per-zone primary terrain. The TMP_003 §2.2
/// per-(zone, modificator) instance model — with `init` and cross-zone
/// `RwLock` state — is a Phase-2 refinement for the full 7-modificator set.
#[derive(Debug)]
pub struct ModificatorContext<'a> {
    /// The placed zones — id, role, centre, `assigned_tiles`, `free_paths`.
    pub zones: &'a [ZoneTiles],
    /// The authoring template — modificators read `ZoneSpec` detail (e.g.
    /// `terrain_types`) by zone id.
    pub template: &'a TilemapTemplate,
    pub grid: GridSize,
    pub seed: TilemapSeed,
    /// Flat terrain layer — index `y * width + x`, value `TerrainKind as u8`.
    /// Length is `grid.tile_count()`.
    pub terrain_layer: &'a mut Vec<u8>,
    /// Per-zone primary terrain, index-aligned with `zones`; `None` until a
    /// modificator paints it.
    pub zone_terrain: &'a mut Vec<Option<TerrainKind>>,
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
