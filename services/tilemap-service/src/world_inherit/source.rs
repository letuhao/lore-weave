//! `WorldSource` — abstract loader of upstream world-gen zone facts.
//!
//! Two impls foreseen:
//!
//! - [`MockFileWorldSource`] — reads JSON fixtures from disk (shipped today)
//! - `HttpWorldSource` — calls a `world-gen-service` over docker-compose
//!   internal HTTP (Phase 2 per spec §8; deferred until post-merge)
//!
//! Both implement the same trait; templates and tests are written against
//! `&dyn WorldSource` so swapping is mechanical at wire time.

use std::path::{Path, PathBuf};
use std::sync::OnceLock;

use super::error::WorldInheritError;
use super::types::{RegionPath, WorldZoneSnapshot};
use super::wire::WorldFile;

/// Loads zone facts from the upstream world-gen contract.
///
/// `load_zone` is synchronous because the file-backed impl is local I/O
/// and the future HTTP impl can be made sync at the trait boundary too
/// (with an internal `tokio::runtime::Handle::block_on` if needed). If a
/// real async load_zone becomes necessary, this trait will get an `async_trait`
/// or split into `WorldSource` (sync) + `AsyncWorldSource` then.
pub trait WorldSource: Send + Sync {
    fn load_zone(&self, path: &RegionPath) -> Result<WorldZoneSnapshot, WorldInheritError>;
}

/// File-backed [`WorldSource`] reading a JSON fixture from disk. Lazy —
/// the file is opened the first time `load_zone` is called and cached
/// for subsequent calls. Construction never fails; a bad path surfaces as
/// `WorldInheritError::IoLoad` on the first lookup.
#[derive(Debug)]
pub struct MockFileWorldSource {
    path: PathBuf,
    cache: OnceLock<WorldFile>,
}

impl MockFileWorldSource {
    pub fn new(path: impl AsRef<Path>) -> Self {
        Self {
            path: path.as_ref().to_path_buf(),
            cache: OnceLock::new(),
        }
    }

    /// Test/diagnostic helper — is the fixture currently materialised in
    /// memory? Returns `false` before the first `load_zone`, `true` after.
    pub fn is_loaded(&self) -> bool {
        self.cache.get().is_some()
    }

    fn world(&self) -> Result<&WorldFile, WorldInheritError> {
        if let Some(w) = self.cache.get() {
            return Ok(w);
        }
        let bytes = std::fs::read(&self.path).map_err(|source| WorldInheritError::IoLoad {
            path: self.path.display().to_string(),
            source,
        })?;
        let file: WorldFile = serde_json::from_slice(&bytes)?;
        let _ = self.cache.set(file);
        Ok(self.cache.get().expect("OnceLock just set"))
    }
}

impl WorldSource for MockFileWorldSource {
    fn load_zone(&self, path: &RegionPath) -> Result<WorldZoneSnapshot, WorldInheritError> {
        let world = self.world()?;
        if path.depth() != 2 {
            return Err(WorldInheritError::MissingZone {
                path: format!("{path} (only zone-depth paths are supported in v1; got depth {})", path.depth()),
            });
        }
        let parts = path.as_slice();
        let plate_id = parts[0];
        for plate in &world.plates {
            if plate.path.first() == Some(&plate_id) {
                for zone in &plate.zones {
                    if zone.path == parts {
                        return zone.to_snapshot();
                    }
                }
                break;
            }
        }
        Err(WorldInheritError::MissingZone {
            path: path.to_string(),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::world_inherit::types::WorldBiome;
    use std::collections::HashSet;

    fn fixture(name: &str) -> PathBuf {
        let manifest = env!("CARGO_MANIFEST_DIR");
        PathBuf::from(manifest)
            .join("tests")
            .join("fixtures")
            .join("world-mock")
            .join(name)
    }

    #[test]
    fn ac_wi_1_loads_zone_with_typed_biome_from_diverse_biomes_fixture() {
        let src = MockFileWorldSource::new(fixture("diverse-biomes.json"));
        let snap = src
            .load_zone(&RegionPath::new(vec![0, 1]))
            .expect("zone [0, 1] should be Tundra");
        assert_eq!(snap.climate.biome_name, WorldBiome::Tundra);
        assert_eq!(snap.climate.biome_tag, 1);
        assert_eq!(snap.path.as_slice(), &[0, 1]);
    }

    #[test]
    fn ac_wi_2_diverse_biomes_fixture_covers_all_ten_world_biomes() {
        let src = MockFileWorldSource::new(fixture("diverse-biomes.json"));
        let mut seen: HashSet<WorldBiome> = HashSet::new();
        for plate_id in 0..5u32 {
            for zone_id in 0..2u32 {
                let snap = src
                    .load_zone(&RegionPath::new(vec![plate_id, zone_id]))
                    .unwrap_or_else(|e| panic!("zone [{plate_id}, {zone_id}] should parse: {e}"));
                seen.insert(snap.climate.biome_name);
            }
        }
        for variant in WorldBiome::all() {
            assert!(
                seen.contains(&variant),
                "diverse-biomes.json missing {variant:?} (covered set: {seen:?})"
            );
        }
        assert_eq!(seen.len(), 10, "expected exactly 10 distinct biomes");
    }

    #[test]
    fn minimal_fixture_parses_and_yields_six_biomes() {
        let src = MockFileWorldSource::new(fixture("minimal.json"));
        let mut seen: HashSet<WorldBiome> = HashSet::new();
        for plate_id in 0..3u32 {
            for zone_id in 0..2u32 {
                let snap = src
                    .load_zone(&RegionPath::new(vec![plate_id, zone_id]))
                    .unwrap_or_else(|e| panic!("zone [{plate_id}, {zone_id}] should parse: {e}"));
                seen.insert(snap.climate.biome_name);
            }
        }
        assert_eq!(seen.len(), 6, "minimal.json should cover 6 distinct biomes; got {seen:?}");
    }

    #[test]
    fn missing_zone_returns_missing_zone_error() {
        let src = MockFileWorldSource::new(fixture("diverse-biomes.json"));
        let err = src
            .load_zone(&RegionPath::new(vec![9, 9]))
            .expect_err("zone [9, 9] does not exist");
        match err {
            WorldInheritError::MissingZone { path } => {
                assert!(path.contains("/9/9"), "expected path in error, got {path}");
            }
            other => panic!("expected MissingZone, got {other:?}"),
        }
    }

    #[test]
    fn nonexistent_file_surfaces_io_load_error_lazily() {
        let src = MockFileWorldSource::new("/does/not/exist/at/all.json");
        assert!(!src.is_loaded(), "construction must not read the file");
        let err = src
            .load_zone(&RegionPath::new(vec![0, 0]))
            .expect_err("missing file should produce IoLoad");
        assert!(matches!(err, WorldInheritError::IoLoad { .. }));
    }

    #[test]
    fn cache_keeps_file_loaded_once_across_load_zone_calls() {
        let src = MockFileWorldSource::new(fixture("diverse-biomes.json"));
        assert!(!src.is_loaded(), "fresh source must be unloaded");
        let _ = src.load_zone(&RegionPath::new(vec![0, 0])).unwrap();
        assert!(src.is_loaded(), "first load_zone should populate cache");
        let _ = src.load_zone(&RegionPath::new(vec![4, 1])).unwrap();
        assert!(src.is_loaded(), "cache stays loaded across calls");
    }

    #[test]
    fn biome_tag_name_mismatch_surfaces_at_load_time() {
        // LOW-4 regression: WireZone::to_snapshot's defensive cross-check
        // had no test coverage. Synthesize a tag/name mismatch inline and
        // assert the load path errors with BiomeTagMismatch (not the
        // misleading UnknownBiomeTag, which now only fires for out-of-range
        // tags).
        let bad_json = r#"{
            "schema_version": "world-gen.v1+climate.v1+polygon.v1",
            "generator": "test@mismatch",
            "world": {
                "width": 1024, "height": 640, "seed": 1, "plate_count": 1,
                "base_level": 0.35, "void_level": 0.0, "collision_gain": 0.35
            },
            "plates": [{
                "path": [0],
                "center": [100.0, 100.0],
                "velocity": [0.0, 0.0],
                "boundary": [[0.0, 0.0], [200.0, 0.0], [200.0, 200.0], [0.0, 200.0]],
                "zones": [{
                    "path": [0, 0],
                    "site": [100.0, 100.0],
                    "base_elevation": 0.4,
                    "boundary": [[0.0, 0.0], [200.0, 0.0], [200.0, 200.0], [0.0, 200.0]],
                    "climate": {
                        "temp_mean": -10.0,
                        "precip_annual": 100.0,
                        "biome_tag": 5,
                        "biome_name": "tundra"
                    },
                    "subzones": []
                }]
            }]
        }"#;
        let tmp = std::env::temp_dir().join("world_inherit_mismatch_test.json");
        std::fs::write(&tmp, bad_json).expect("write tmp fixture");
        let src = MockFileWorldSource::new(&tmp);
        let err = src
            .load_zone(&RegionPath::new(vec![0, 0]))
            .expect_err("mismatched tag/name must surface");
        let _ = std::fs::remove_file(&tmp);
        match err {
            WorldInheritError::BiomeTagMismatch { tag, name } => {
                assert_eq!(tag, 5);
                assert_eq!(name, WorldBiome::Tundra);
            }
            other => panic!("expected BiomeTagMismatch, got {other:?}"),
        }
    }

    #[test]
    fn nonzone_depth_path_rejected() {
        let src = MockFileWorldSource::new(fixture("minimal.json"));
        let err = src
            .load_zone(&RegionPath::new(vec![0]))
            .expect_err("plate-depth path not supported in v1");
        assert!(matches!(err, WorldInheritError::MissingZone { .. }));
        let err = src
            .load_zone(&RegionPath::new(vec![0, 0, 0]))
            .expect_err("subzone-depth path not supported in v1");
        assert!(matches!(err, WorldInheritError::MissingZone { .. }));
    }
}
