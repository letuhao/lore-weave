//! Concrete modificators. Phase 1 ships TerrainPainter (TMP_003 §3.1); Phase B
//! adds ObstaclePlacer (TMP_005 §4); Phase C adds TreasurePlacer (TMP_006 §3);
//! Phase D adds ConnectionsPlacer (TMP_007); the rest of the §3 catalog later.

pub mod connections_placer;
pub mod decoration_placer;
pub mod obstacle_placer;
pub mod river_placer;
pub mod road_placer;
pub mod terrain_painter;
pub mod treasure_placer;

pub use connections_placer::ConnectionsPlacer;
pub use decoration_placer::DecorationPlacer;
pub use obstacle_placer::{ObstacleFillPlacer, ObstacleSourcePlacer};
pub use river_placer::RiverPlacer;
pub use road_placer::RoadPlacer;
pub use terrain_painter::TerrainPainter;
pub use treasure_placer::TreasurePlacer;
