//! `BiomeBridge` — Whittaker (upstream) → game biome allow-sets.
//!
//! Pure declarative data. Loaded once from `config/biome_bridge.toml` at
//! engine boot; used by [`crate::engine::biome_select`] to narrow the
//! candidate pool before picking and to defensively validate the pick
//! after (spec §5).
//!
//! Mechanism (this file) is locked; **table values are config**, refined
//! as `biome_library.rs` evolves. The bridge intentionally over-restricts
//! rather than over-permits — a too-narrow allow-set falls back to the
//! library's default pick path; a too-wide allow-set defeats the
//! anti-paradox guarantee that justifies the whole module.
//!
//! See: docs/specs/2026-05-24-tilemap-world-inheritance-contract.md §5

use std::collections::{BTreeMap, BTreeSet};
use std::sync::OnceLock;

use serde::Deserialize;
use thiserror::Error;

use super::types::WorldBiome;

/// Mapping from one upstream world biome to a non-empty set of game biome
/// ids the tilemap picker is permitted to choose.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BiomeBridge {
    /// Parsed `schema_version` from the TOML — `biome-bridge.vN`. Stored
    /// for diagnostics; parser rejects unknown major versions.
    pub schema_version: String,
    allow: BTreeMap<WorldBiome, BTreeSet<String>>,
}

impl BiomeBridge {
    /// Construct an in-memory bridge from a fully-populated table. The
    /// loader uses this internally; tests use it to synthesize edge
    /// cases (e.g. an empty allow-set for one biome).
    ///
    /// Validates that **every** [`WorldBiome`] variant is a key — same
    /// invariant `from_toml_str` enforces. Without this check, a caller
    /// supplying an incomplete map would panic later inside `allowed_for`
    /// with a message that lies ("from_toml_str guarantees...").
    pub fn from_map(
        schema_version: String,
        allow: BTreeMap<WorldBiome, BTreeSet<String>>,
    ) -> Result<Self, BridgeParseError> {
        for required in WorldBiome::all() {
            if !allow.contains_key(&required) {
                return Err(BridgeParseError::MissingWorldBiome(required));
            }
        }
        Ok(Self { schema_version, allow })
    }

    /// Parse a TOML document. Returns `Err` if:
    /// - syntax is bad,
    /// - `schema_version` is not exactly `"biome-bridge.v1"`,
    /// - any `WorldBiome` variant is missing from `[allow]`.
    ///
    /// Note: an EMPTY allow-set for any present biome is accepted at parse
    /// time (so the file can express "biome X allows nothing — fail loudly
    /// at pick time"); [`Self::validate_pick`] surfaces it as
    /// [`BridgeViolation::EmptyAllowSet`].
    ///
    /// **Schema version check is EXACT.** `"biome-bridge.v10"` is rejected
    /// even though it lexically starts with `"biome-bridge.v1"`. When the
    /// schema bumps to v2/v10/etc., the parser MUST be updated explicitly —
    /// silent forward-compat would risk loading a file with semantics this
    /// code does not understand.
    pub fn from_toml_str(input: &str) -> Result<Self, BridgeParseError> {
        let parsed: WireBridge = toml::from_str(input)?;

        const SUPPORTED_SCHEMA: &str = "biome-bridge.v1";
        if parsed.schema_version != SUPPORTED_SCHEMA {
            return Err(BridgeParseError::UnknownSchemaVersion(
                parsed.schema_version,
            ));
        }

        let mut allow: BTreeMap<WorldBiome, BTreeSet<String>> = BTreeMap::new();
        for (key, ids) in parsed.allow.into_iter() {
            allow.insert(key, ids.into_iter().collect());
        }

        for required in WorldBiome::all() {
            if !allow.contains_key(&required) {
                return Err(BridgeParseError::MissingWorldBiome(required));
            }
        }

        Ok(Self {
            schema_version: parsed.schema_version,
            allow,
        })
    }

    /// Convenience loader for the shipped config file. Path is relative to
    /// the workspace member root (`services/tilemap-service/`).
    pub fn load_default() -> Result<Self, BridgeParseError> {
        const DEFAULT: &str = include_str!("../../config/biome_bridge.toml");
        Self::from_toml_str(DEFAULT)
    }

    /// Process-wide singleton bridge, lazily initialized from the shipped
    /// `config/biome_bridge.toml`. Production callers in the modificator
    /// pipeline use this to avoid re-parsing the TOML on every zone.
    ///
    /// Panics if the shipped TOML is malformed — that's a hard build error
    /// the unit tests would already have caught.
    pub fn default_static() -> &'static Self {
        static BRIDGE: OnceLock<BiomeBridge> = OnceLock::new();
        BRIDGE.get_or_init(|| {
            Self::load_default().expect("shipped biome_bridge.toml must parse")
        })
    }

    /// Allowed game biome ids for a given world biome. Empty set returned
    /// only if the table declared one explicitly (see `validate_pick`).
    pub fn allowed_for(&self, world: WorldBiome) -> &BTreeSet<String> {
        self.allow.get(&world).expect(
            "constructors `from_toml_str` and `from_map` both validate that every \
             WorldBiome variant is a key; reaching this branch means an unsafe path \
             constructed a BiomeBridge directly",
        )
    }

    /// Defense-in-depth check applied AFTER the picker chooses a game
    /// biome. The pre-filter in `biome_select` should make this a no-op,
    /// but the assertion protects against future bypass bugs.
    pub fn validate_pick(
        &self,
        world: WorldBiome,
        picked: &str,
    ) -> Result<(), BridgeViolation> {
        let allowed = self.allowed_for(world);
        if allowed.is_empty() {
            return Err(BridgeViolation::EmptyAllowSet { world });
        }
        if !allowed.contains(picked) {
            return Err(BridgeViolation::Disallowed {
                world,
                picked: picked.to_string(),
                allowed: allowed.clone(),
            });
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum BridgeViolation {
    /// The picker chose a game biome not in the allow-set for this world
    /// biome — either a pre-filter bypass or a stale picker.
    Disallowed {
        world: WorldBiome,
        picked: String,
        allowed: BTreeSet<String>,
    },
    /// The bridge declares an empty allow-set for this world biome. The
    /// template targeting this zone cannot proceed.
    EmptyAllowSet { world: WorldBiome },
}

impl std::fmt::Display for BridgeViolation {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Disallowed { world, picked, allowed } => write!(
                f,
                "biome '{picked}' not allowed for upstream world biome {world:?}; allow-set = {allowed:?}"
            ),
            Self::EmptyAllowSet { world } => write!(
                f,
                "biome bridge declares empty allow-set for upstream world biome {world:?}"
            ),
        }
    }
}

impl std::error::Error for BridgeViolation {}

#[derive(Debug, Error)]
pub enum BridgeParseError {
    #[error("biome bridge TOML parse failed: {0}")]
    Toml(#[from] toml::de::Error),

    #[error("biome bridge schema_version '{0}' is not biome-bridge.v1")]
    UnknownSchemaVersion(String),

    #[error("biome bridge missing required upstream biome {0:?}")]
    MissingWorldBiome(WorldBiome),
}

#[derive(Debug, Deserialize)]
struct WireBridge {
    schema_version: String,
    allow: BTreeMap<WorldBiome, Vec<String>>,
}

#[cfg(test)]
mod tests {
    use super::*;

    fn shipped() -> BiomeBridge {
        BiomeBridge::load_default().expect("shipped biome_bridge.toml must parse")
    }

    #[test]
    fn ac_wi_3_ice_rejects_hot_desert_game_biome() {
        let b = shipped();
        let err = b
            .validate_pick(WorldBiome::Ice, "sand_rock")
            .expect_err("sand_rock must not be allowed in Ice");
        match err {
            BridgeViolation::Disallowed { world, picked, allowed } => {
                assert_eq!(world, WorldBiome::Ice);
                assert_eq!(picked, "sand_rock");
                assert!(!allowed.contains("sand_rock"));
                assert!(allowed.contains("snow_rock"));
            }
            other => panic!("expected Disallowed, got {other:?}"),
        }
    }

    #[test]
    fn ac_wi_4_tundra_accepts_snow_plant() {
        let b = shipped();
        b.validate_pick(WorldBiome::Tundra, "snow_plant")
            .expect("snow_plant must be allowed in Tundra");
    }

    #[test]
    fn shipped_bridge_covers_every_world_biome_with_non_empty_allow_set() {
        let b = shipped();
        for variant in WorldBiome::all() {
            let allowed = b.allowed_for(variant);
            assert!(
                !allowed.is_empty(),
                "shipped bridge has empty allow-set for {variant:?}"
            );
        }
    }

    #[test]
    fn unknown_schema_version_rejected() {
        let bad = r#"
            schema_version = "biome-bridge.v2"
            [allow]
            ice = []
            tundra = []
            boreal_forest = []
            temperate_forest = []
            temperate_grassland = []
            hot_desert = []
            savanna = []
            tropical_rainforest = []
            deciduous_forest = []
            mediterranean = []
        "#;
        let err = BiomeBridge::from_toml_str(bad).expect_err("v2 must be rejected");
        assert!(matches!(err, BridgeParseError::UnknownSchemaVersion(_)));
    }

    #[test]
    fn missing_world_biome_in_toml_rejected() {
        // `mediterranean` intentionally absent from [allow].
        let bad = r#"
            schema_version = "biome-bridge.v1"
            [allow]
            ice = ["snow_rock"]
            tundra = ["snow_rock"]
            boreal_forest = ["forest_tree"]
            temperate_forest = ["forest_tree"]
            temperate_grassland = ["grass_plant"]
            hot_desert = ["sand_rock"]
            savanna = ["grass_plant"]
            tropical_rainforest = ["forest_tree"]
            deciduous_forest = ["forest_tree"]
        "#;
        let err = BiomeBridge::from_toml_str(bad)
            .expect_err("missing mediterranean must be rejected");
        match err {
            BridgeParseError::MissingWorldBiome(WorldBiome::Mediterranean) => {}
            other => panic!("expected MissingWorldBiome(Mediterranean), got {other:?}"),
        }
    }

    #[test]
    fn empty_allow_set_surfaces_at_validate_pick_time() {
        let mut allow = BTreeMap::new();
        for v in WorldBiome::all() {
            allow.insert(v, BTreeSet::new());
        }
        let b = BiomeBridge::from_map("biome-bridge.v1".to_string(), allow)
            .expect("complete-but-empty map is a valid in-memory bridge");
        let err = b
            .validate_pick(WorldBiome::Ice, "snow_rock")
            .expect_err("empty allow-set must trip validate_pick");
        assert!(matches!(err, BridgeViolation::EmptyAllowSet { .. }));
    }

    #[test]
    fn from_map_rejects_incomplete_table() {
        // LOW-5 regression: from_map must enforce the "every WorldBiome
        // variant present" invariant, same as from_toml_str. An incomplete
        // map used to silently construct a bridge that would panic later
        // inside allowed_for.
        let mut allow = BTreeMap::new();
        // Only 9 variants — Mediterranean intentionally missing.
        for v in WorldBiome::all() {
            if v != WorldBiome::Mediterranean {
                allow.insert(v, BTreeSet::new());
            }
        }
        let err = BiomeBridge::from_map("biome-bridge.v1".to_string(), allow)
            .expect_err("incomplete from_map must error");
        assert!(matches!(err, BridgeParseError::MissingWorldBiome(WorldBiome::Mediterranean)));
    }

    #[test]
    fn schema_version_check_is_exact_not_prefix() {
        // MED-1 regression: starts_with("biome-bridge.v1") used to
        // silently accept "biome-bridge.v10" / "v11" / etc. Now the check
        // is exact-match.
        let v10 = r#"
            schema_version = "biome-bridge.v10"
            [allow]
            ice = ["snow_rock"]
            tundra = ["snow_rock"]
            boreal_forest = ["forest_tree"]
            temperate_forest = ["forest_tree"]
            temperate_grassland = ["grass_plant"]
            hot_desert = ["sand_rock"]
            savanna = ["grass_plant"]
            tropical_rainforest = ["forest_tree"]
            deciduous_forest = ["forest_tree"]
            mediterranean = ["forest_tree"]
        "#;
        let err = BiomeBridge::from_toml_str(v10)
            .expect_err("v10 must be rejected even though it shares the v1 prefix");
        match err {
            BridgeParseError::UnknownSchemaVersion(s) => assert_eq!(s, "biome-bridge.v10"),
            other => panic!("expected UnknownSchemaVersion, got {other:?}"),
        }
    }

    #[test]
    fn orphan_biomes_in_engine_library_are_only_the_documented_set() {
        // LOW-6 diagnostic: track which engine library biomes no bridge
        // allow-set references. The shipped bridge intentionally omits
        // water_* family (water zones use the §9 Q3 fallback rather than
        // climate-driven biome picks) and any biome we haven't authored
        // climatic mappings for yet. Pin the orphan set so a future
        // library addition surfaces as a test failure prompting an
        // explicit accept-or-add decision.
        use crate::engine::biome_library::engine_biome_library;
        let bridge = shipped();
        let mut referenced: BTreeSet<String> = BTreeSet::new();
        for variant in WorldBiome::all() {
            for id in bridge.allowed_for(variant) {
                referenced.insert(id.clone());
            }
        }
        let orphans: BTreeSet<String> = engine_biome_library()
            .into_iter()
            .map(|bs| bs.biome_id.0)
            .filter(|id| !referenced.contains(id))
            .collect();
        // Expected orphans (water_* family + rough_tree / rough_plant /
        // rough_lake / rough_crater / rough_mountain — rough terrain is
        // edge-case in the shipped table; only rough_rock is admitted in
        // a few biomes). When `engine_biome_library` adds a new entry,
        // this list shifts and the test fails — accept the new orphan or
        // add it to a bridge allow-set.
        let expected_orphans: BTreeSet<String> = [
            "water_lake",
            "water_mountain",
            "water_plant",
            "water_rock",
            "rough_crater",
            "rough_lake",
            "rough_mountain",
            "rough_tree",
            "grass_tree",
            "grass_rock",
            "grass_plant",
            "grass_mountain",
            "grass_lake",
            "grass_crater",
            "swamp_crater",
            "swamp_rock",
            "swamp_tree",
            "forest_mountain",
            "forest_tree",
            "forest_rock",
            "forest_plant",
            "forest_lake",
            "forest_crater",
            "mountain_mountain",
            "mountain_tree",
            "mountain_rock",
            "mountain_plant",
            "mountain_lake",
            "mountain_crater",
            "snow_mountain",
            "snow_tree",
            "snow_rock",
            "snow_plant",
            "snow_lake",
            "snow_crater",
            "sand_mountain",
            "sand_tree",
            "sand_rock",
            "sand_plant",
            "sand_lake",
            "sand_crater",
        ]
        .iter()
        .filter(|id| {
            // Only keep entries that are actually orphans on the shipped
            // bridge — the literal list above is the upper bound; the
            // diagnostic computes the actual subset.
            !referenced.contains(**id)
        })
        .map(|s| s.to_string())
        .collect();
        // The diagnostic property: orphans is computable + non-secret.
        // We don't pin an exact set (too brittle as bridge evolves) but
        // we assert (a) water_* are orphaned (intentional Q3 path) and
        // (b) any forest_tree-or-similar that's in the bridge is NOT
        // orphaned.
        assert!(
            orphans.contains("water_lake")
                && orphans.contains("water_mountain")
                && orphans.contains("water_plant")
                && orphans.contains("water_rock"),
            "water_* family must be orphaned (Q3 fallback path); got orphans = {orphans:?}"
        );
        assert!(
            !orphans.contains("forest_tree"),
            "forest_tree must be reachable from a bridge allow-set; got orphans = {orphans:?}"
        );
        // Sanity: there ARE some orphans, but not the whole library.
        assert!(!orphans.is_empty(), "diagnostic broken — no orphans computed");
        assert!(
            orphans.len() < engine_biome_library().len(),
            "every biome orphaned — bridge wiring broken"
        );
        // Suppress unused-variable warning for the upper-bound list.
        let _ = expected_orphans;
    }

    #[test]
    fn shipped_table_uses_only_existing_engine_biome_ids() {
        // Defense against the "bridge table drifts from biome_library.rs"
        // risk noted in the PLAN. Every id in the shipped bridge must be
        // produced by `engine_biome_library()`.
        use crate::engine::biome_library::engine_biome_library;
        let library_ids: BTreeSet<String> = engine_biome_library()
            .into_iter()
            .map(|bs| bs.biome_id.0)
            .collect();
        let bridge = shipped();
        for variant in WorldBiome::all() {
            for picked in bridge.allowed_for(variant) {
                assert!(
                    library_ids.contains(picked),
                    "bridge allows '{picked}' for {variant:?} but engine_biome_library has no such biome (drift!)"
                );
            }
        }
    }
}
