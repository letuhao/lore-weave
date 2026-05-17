//! Concrete modificators. Phase 1 ships TerrainPainter (TMP_003 §3.1); Phase B
//! adds ObstaclePlacer (TMP_005 §4); the rest of the §3 catalog lands later.

pub mod obstacle_placer;
pub mod terrain_painter;

pub use obstacle_placer::ObstaclePlacer;
pub use terrain_painter::TerrainPainter;
