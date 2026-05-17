//! Concrete modificators. Phase 1 ships TerrainPainter (TMP_003 §3.1); Phase B
//! adds ObstaclePlacer (TMP_005 §4); Phase C adds TreasurePlacer (TMP_006 §3);
//! the rest of the §3 catalog lands later.

pub mod obstacle_placer;
pub mod terrain_painter;
pub mod treasure_placer;

pub use obstacle_placer::ObstaclePlacer;
pub use terrain_painter::TerrainPainter;
pub use treasure_placer::TreasurePlacer;
