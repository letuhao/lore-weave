//! GEO_001b authoring — turn a prose brief into a schema-valid `CreativeSeed`
//! via an LLM.
//!
//! The LLM call is **non-deterministic**, but it only produces the *input*
//! `CreativeSeed`; `generate(seed, creative_seed)` downstream is as pure and
//! deterministic as ever.
//!
//! **Gateway invariant (CLAUDE.md, 2026-05-30)**: LLM calls flow through the
//! `loreweave_llm` SDK via a `&dyn TextProvider` — typically
//! [`crate::shape::GatewayTextProvider`] for the real backend or
//! [`crate::shape::MockTextProvider`] for offline tests. The prior
//! `llm_json_request(llm_url, model, ...)` helper was deleted (it
//! directly POSTed to an OpenAI-compatible URL).

use serde_json::{Value, json};

use crate::creative_seed::CreativeSeed;
use crate::shape::llm::{TextPrompt, TextProvider};

/// System prompt — explains the `CreativeSeed` fields to the LLM.
const SYSTEM_PROMPT: &str = "\
You are a world-design assistant for a procedural map generator. Given a prose \
brief, produce ONE CreativeSeed JSON object matching the provided schema. Field \
meanings: world_scale = overall map size; world_archetype = genre; \
coastline_profile = landmass shape (Island/Peninsula/Coastal/Inland/Archipelago); \
hemisphere_orientation = which way the continent faces the poles; climate_bias = \
a climate zone to skew toward, or null for none; settlement_density = how dense \
settlements are; culture_count = number of distinct cultures (1-16); \
prevailing_wind = the compass direction the wind blows from, driving rain-shadow \
deserts on the lee side of mountains; \
erosion = how hard water carves the terrain (None/Light/Moderate/Heavy) — \
heavier erosion means deeper valleys, broader river networks, softer mountains; \
terrain_mode = Tectonic (a multi-continent plate-tectonic planet — the default \
and best for a whole world) or Profile (a single landmass shaped by \
coastline_profile — for a region/zone); plate_count = number of tectonic plates \
when Tectonic (3-24, ~8 for an Earth-like world); continental_fraction = share \
of plates that are land when Tectonic (0.1-0.9, ~0.4 for an ocean-rich world); \
continent_latitude_spread = how strongly continents spread across latitudes when \
Tectonic (0.0-1.0; 0 = random placement (default), 1 = land covers equator to \
both poles for a wider biome range — set ~0.6+ for a deliberately varied, \
pole-to-pole world); \
intensity = optional macro tuning knobs (each defaults to 1.0 = Earth-like; \
omit unless the brief calls for it): intensity.orogeny scales mountain-building \
(>1 = taller, more dramatic ranges/plateaus; <1 = gentler), intensity.collision_frequency \
scales how often plates collide (>1 = more mountain belts, fewer flat oceans; \
<1 = calmer), intensity.relief scales continental relief detail (>1 = more rugged/ \
jagged land; <1 = smoother), intensity.ocean_depth scales how deep the oceans are \
(>1 = deeper abyss; <1 = shallower seas). Choose values that fit the brief. \
Output only the JSON object.";

/// The JSON Schema constraining the LLM output to the `CreativeSeed` shape.
///
/// MAINTENANCE: the `enum` value lists below are hand-mirrored from the Rust
/// enums — keep them in sync with `WorldScale`, `WorldArchetype` (minus
/// `Custom`), `CoastlineProfile`, `HemisphereOrientation`, `PrevailingWind`,
/// `ErosionStrength`, `SettlementDensity`, and `ClimateZone`. The
/// `schema_enums_match_rust_enums` test catches a stale or bogus entry.
pub fn creative_seed_schema() -> Value {
    json!({
        "type": "object",
        "additionalProperties": false,
        "required": [
            "world_scale", "world_archetype", "coastline_profile",
            "hemisphere_orientation", "prevailing_wind", "erosion",
            "climate_bias", "settlement_density", "culture_count"
        ],
        "properties": {
            "world_scale": { "enum": [
                "Pocket", "Region", "Continent", "SuperContinent", "Megaplanet",
                "Gigaplanet"
            ] },
            "world_archetype": { "enum": [
                "Wuxia", "HighFantasy", "LowFantasy", "Cyberpunk", "SteamPunk",
                "Postapocalyptic", "ScienceFiction", "Historical", "Mythological",
                "Romance", "Mystery"
            ] },
            "coastline_profile": { "enum": [
                "Island", "Peninsula", "Coastal", "Inland", "Archipelago"
            ] },
            "hemisphere_orientation": { "enum": [
                "Northern", "Southern", "Equatorial"
            ] },
            "prevailing_wind": { "enum": [
                "North", "NorthEast", "East", "SouthEast",
                "South", "SouthWest", "West", "NorthWest"
            ] },
            "erosion": { "enum": ["None", "Light", "Moderate", "Heavy"] },
            "climate_bias": { "enum": [
                "Polar", "Boreal", "Temperate", "Mediterranean", "Subtropical",
                "Tropical", "Arid", "Highland", null
            ] },
            "settlement_density": { "enum": ["Sparse", "Medium", "Dense"] },
            "culture_count": { "type": "integer", "minimum": 1, "maximum": 16 },
            // Phase 2 — optional (serde defaults: Tectonic / 8 / 0.4), so a
            // pre-Phase-2 brief still validates. Not in `required`.
            "terrain_mode": { "enum": ["Tectonic", "Profile"] },
            "plate_count": { "type": "integer", "minimum": 3, "maximum": 24 },
            "continental_fraction": { "type": "number", "minimum": 0.1, "maximum": 0.9 },
            "continent_latitude_spread": { "type": "number", "minimum": 0.0, "maximum": 1.0 },
            // Parameterization (P1) — optional macro intensity knobs (default 1.0).
            // The granular `tectonics` table is config-file territory; the LLM
            // dials behaviour through these.
            "intensity": {
                "type": "object",
                "additionalProperties": false,
                "properties": {
                    "orogeny": { "type": "number", "minimum": 0.0, "maximum": 3.0 },
                    "collision_frequency": { "type": "number", "minimum": 0.0, "maximum": 3.0 },
                    "relief": { "type": "number", "minimum": 0.0, "maximum": 4.0 },
                    "ocean_depth": { "type": "number", "minimum": 0.1, "maximum": 4.0 }
                }
            }
        }
    })
}

/// Parse + validate an LLM `content` string into a `CreativeSeed`. A
/// successful serde parse is the structural validation (unknown enum variants
/// / missing fields are rejected); `culture_count` is then clamped to `1..=16`.
pub fn parse_creative_seed(content: &str) -> Result<CreativeSeed, String> {
    let mut cs: CreativeSeed = serde_json::from_str(content.trim())
        .map_err(|e| format!("CreativeSeed JSON parse failed: {e}"))?;
    cs.culture_count = cs.culture_count.clamp(1, 16);
    // Phase 2 — clamp the tectonic knobs to their valid bands (the generator
    // also clamps at use; this keeps the stored CreativeSeed sane).
    cs.plate_count = cs.plate_count.clamp(3, 24);
    cs.continental_fraction = cs.continental_fraction.clamp(0.1, 0.9);
    cs.continent_latitude_spread = cs.continent_latitude_spread.clamp(0.0, 1.0);
    // Parameterization — clamp the macro knobs in the stored seed (defence in
    // depth; `TectonicsParams::resolved` also clamps at use). Granular params
    // are clamped at use by `resolved`.
    cs.intensity.orogeny = cs.intensity.orogeny.clamp(0.0, 3.0);
    cs.intensity.collision_frequency = cs.intensity.collision_frequency.clamp(0.0, 3.0);
    cs.intensity.relief = cs.intensity.relief.clamp(0.0, 4.0);
    cs.intensity.ocean_depth = cs.intensity.ocean_depth.clamp(0.1, 4.0);
    Ok(cs)
}

/// Request a `CreativeSeed` from a [`TextProvider`] (typically a
/// gateway-backed one — see [`crate::shape::GatewayTextProvider`]).
///
/// The provider must honor the attached JSON schema; the result is the raw
/// JSON string which [`parse_creative_seed`] then validates and clamps.
/// Every failure path returns a descriptive `Err` — no panic.
pub fn request_creative_seed(
    brief: &str,
    provider: &dyn TextProvider,
) -> Result<CreativeSeed, String> {
    let prompt = TextPrompt::new(SYSTEM_PROMPT, brief)
        .with_schema(creative_seed_schema(), "creative_seed");
    let content = provider
        .complete(&prompt)
        .map_err(|e| format!("CreativeSeed request failed: {e}"))?;
    parse_creative_seed(&content)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::climate::ClimateZone;
    use crate::creative_seed::{
        CoastlineProfile, ErosionStrength, HemisphereOrientation, PrevailingWind, SettlementDensity,
        WorldArchetype, WorldScale,
    };

    const VALID: &str = r#"{
        "world_scale": "Continent",
        "world_archetype": "Wuxia",
        "coastline_profile": "Coastal",
        "hemisphere_orientation": "Northern",
        "prevailing_wind": "East",
        "climate_bias": "Arid",
        "settlement_density": "Medium",
        "culture_count": 6
    }"#;

    #[test]
    fn parses_a_valid_creative_seed() {
        let cs = parse_creative_seed(VALID).expect("valid JSON should parse");
        assert_eq!(cs.world_scale, WorldScale::Continent);
        assert_eq!(cs.world_archetype, WorldArchetype::Wuxia);
        assert_eq!(cs.coastline_profile, CoastlineProfile::Coastal);
        assert_eq!(cs.hemisphere_orientation, HemisphereOrientation::Northern);
        assert_eq!(cs.prevailing_wind, PrevailingWind::East);
        assert_eq!(cs.climate_bias, Some(ClimateZone::Arid));
        assert_eq!(cs.settlement_density, SettlementDensity::Medium);
        assert_eq!(cs.culture_count, 6);
    }

    #[test]
    fn climate_bias_null_parses_as_none() {
        let json = VALID.replace("\"Arid\"", "null");
        assert_eq!(parse_creative_seed(&json).unwrap().climate_bias, None);
    }

    #[test]
    fn rejects_malformed_json() {
        assert!(parse_creative_seed("{not json").is_err());
    }

    #[test]
    fn rejects_unknown_enum_variant() {
        let json = VALID.replace("\"Wuxia\"", "\"Steampunk_typo\"");
        assert!(parse_creative_seed(&json).is_err());
    }

    #[test]
    fn clamps_out_of_range_culture_count() {
        let hi = VALID.replace("\"culture_count\": 6", "\"culture_count\": 200");
        assert_eq!(parse_creative_seed(&hi).unwrap().culture_count, 16);
        let lo = VALID.replace("\"culture_count\": 6", "\"culture_count\": 0");
        assert_eq!(parse_creative_seed(&lo).unwrap().culture_count, 1);
    }

    #[test]
    fn clamps_out_of_range_continent_latitude_spread() {
        // A garbage LLM value must be clamped to [0,1] in the stored seed
        // (defence-in-depth; the generator also clamps at use).
        let hi = VALID.replace(
            "\"culture_count\": 6",
            "\"culture_count\": 6, \"continent_latitude_spread\": 5.0",
        );
        assert!((parse_creative_seed(&hi).unwrap().continent_latitude_spread - 1.0).abs() < 1e-6);
        let lo = VALID.replace(
            "\"culture_count\": 6",
            "\"culture_count\": 6, \"continent_latitude_spread\": -2.0",
        );
        assert!(parse_creative_seed(&lo).unwrap().continent_latitude_spread.abs() < 1e-6);
    }

    #[test]
    fn request_provider_error_surfaces_clean_message() {
        // **2026-05-30 refactor**: `extract_message_content` +
        // `llm_json_request` were deleted with the direct-HTTP path.
        // Provider errors now surface via `LlmError`; this test pins
        // that the wrapper preserves the message.
        use crate::shape::llm::{LlmError, TextPrompt, TextProvider};
        #[derive(Debug)]
        struct AlwaysFailProvider;
        impl TextProvider for AlwaysFailProvider {
            fn complete(&self, _: &TextPrompt) -> Result<String, LlmError> {
                Err(LlmError::Transport("simulated unreachable gateway".into()))
            }
        }
        let r = request_creative_seed("a brief", &AlwaysFailProvider);
        let err = r.expect_err("provider failure must surface as Err");
        assert!(
            err.contains("CreativeSeed request failed"),
            "wrapper should prefix; got: {err}"
        );
    }

    #[test]
    fn schema_enums_match_rust_enums() {
        // Every enum string in the schema must deserialize into its Rust enum
        // (catches a stale/bogus hand-mirrored entry — design-r3 WARN-3).
        let schema = creative_seed_schema();
        let parses = |field: &str, de: &dyn Fn(&str) -> bool| {
            // navigate with get()/as_array — a malformed schema fails with a
            // readable message naming the field, not an opaque index panic.
            let arr = schema
                .get("properties")
                .and_then(|p| p.get(field))
                .and_then(|f| f.get("enum"))
                .and_then(Value::as_array)
                .unwrap_or_else(|| panic!("schema field {field} has no enum array"));
            for val in arr {
                if let Some(s) = val.as_str() {
                    assert!(de(s), "schema {field} enum {s:?} does not deserialize");
                }
            }
        };
        parses("world_scale", &|s| {
            serde_json::from_value::<WorldScale>(json!(s)).is_ok()
        });
        parses("world_archetype", &|s| {
            serde_json::from_value::<WorldArchetype>(json!(s)).is_ok()
        });
        parses("coastline_profile", &|s| {
            serde_json::from_value::<CoastlineProfile>(json!(s)).is_ok()
        });
        parses("hemisphere_orientation", &|s| {
            serde_json::from_value::<HemisphereOrientation>(json!(s)).is_ok()
        });
        parses("prevailing_wind", &|s| {
            serde_json::from_value::<PrevailingWind>(json!(s)).is_ok()
        });
        parses("erosion", &|s| {
            serde_json::from_value::<ErosionStrength>(json!(s)).is_ok()
        });
        parses("settlement_density", &|s| {
            serde_json::from_value::<SettlementDensity>(json!(s)).is_ok()
        });
        parses("climate_bias", &|s| {
            serde_json::from_value::<ClimateZone>(json!(s)).is_ok()
        });

        // Reverse direction: the schema must still *offer* every real variant
        // — a count check pins an accidental deletion from a hand-mirrored
        // enum list (one-directional drift; design code-review LOW-3).
        let count = |field: &str| -> usize {
            schema
                .get("properties")
                .and_then(|p| p.get(field))
                .and_then(|f| f.get("enum"))
                .and_then(Value::as_array)
                .map_or(0, Vec::len)
        };
        assert_eq!(count("world_scale"), 6, "world_scale enum count");
        assert_eq!(count("world_archetype"), 11, "world_archetype enum count (12 - Custom)");
        assert_eq!(count("coastline_profile"), 5, "coastline_profile enum count");
        assert_eq!(count("hemisphere_orientation"), 3, "hemisphere enum count");
        assert_eq!(count("prevailing_wind"), 8, "prevailing_wind enum count");
        assert_eq!(count("erosion"), 4, "erosion enum count");
        assert_eq!(count("settlement_density"), 3, "settlement_density enum count");
        assert_eq!(count("climate_bias"), 9, "climate_bias enum count (8 zones + null)");

        // No schema enum list may repeat a value — `parses` + `count` together
        // would still pass a list that duplicated one variant and dropped
        // another (review-impl finding 6).
        let no_dups = |field: &str| {
            let arr = schema
                .get("properties")
                .and_then(|p| p.get(field))
                .and_then(|f| f.get("enum"))
                .and_then(Value::as_array)
                .unwrap_or_else(|| panic!("schema field {field} has no enum array"));
            let mut seen = std::collections::HashSet::new();
            for v in arr {
                assert!(
                    seen.insert(v.to_string()),
                    "schema {field} enum repeats a value: {v}"
                );
            }
        };
        for field in [
            "world_scale",
            "world_archetype",
            "coastline_profile",
            "hemisphere_orientation",
            "prevailing_wind",
            "erosion",
            "settlement_density",
            "climate_bias",
        ] {
            no_dups(field);
        }
    }
}
