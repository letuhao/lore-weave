//! Civilization naming — deterministic synthetic names (Ship 7) +
//! LLM-driven naming via the `TextProvider` trait (Ship 7b).
//!
//! Synthetic naming is deterministic per seed and used as the default;
//! LLM naming via [`name_civ_via_llm`] is opt-in and non-deterministic
//! (real providers; the [`crate::shape::MockTextProvider`] is
//! deterministic for testing).

use crate::culture::Culture;
use crate::feature::Features;
use crate::political::Political;
use crate::rng::Rng;
use crate::shape::llm::{LlmError, TextPrompt, TextProvider};
use crate::world_map::Settlement;

// ---------- Synthetic name pools ----------

const SETTLEMENT_NAMES: &[&str] = &[
    "Aetherholt", "Brightford", "Cinderwatch", "Dawnreach", "Embervale",
    "Frostmere", "Goldenhall", "Hollowbarrow", "Ironkeep", "Jadewood",
    "Kingsford", "Larkspur", "Mistmoor", "Northwatch", "Oakenshield",
    "Pinevale", "Quietwater", "Ravenholm", "Stonehearth", "Thornbury",
    "Umbergate", "Vinewreath", "Willowbrook", "Yewglen", "Zephyrport",
];

const STATE_NAMES: &[&str] = &[
    "Aelvarra", "Brennor", "Caldaris", "Drakhalim", "Eronthel",
    "Faerondale", "Glenwarde", "Hjarsgrad", "Iskandar", "Jorvik",
    "Kelmarine", "Lirenoth", "Mythraal", "Northkin", "Ostralia",
    "Parthenor", "Querion", "Rikhalim", "Sundarial", "Thalassia",
];

const PROVINCE_PREFIXES: &[&str] = &[
    "Vale of", "March of", "Reach of", "Hold of", "Span of", "Realm of",
    "Domain of", "Land of",
];

const PROVINCE_ROOTS: &[&str] = &[
    "Ashwynne", "Briarfall", "Caelwood", "Deepford", "Elder Pines",
    "Falconcrest", "Glimmerlake", "Hawthorn", "Ironbark", "Larkmere",
    "Mistgate", "Nightspire", "Oldhollow", "Pondbridge", "Quartzcliff",
    "Redmoor", "Silverbrook", "Twilight Glade", "Umbra", "Whitewater",
];

const CULTURE_NAMES: &[&str] = &[
    "Aelir", "Brenn", "Caelori", "Dhuran", "Eldari",
    "Fenni", "Gwynar", "Hjorl", "Iskari", "Jolvik",
    "Kelmar", "Lirthen", "Myrran", "Norval", "Ostren",
];

const MOUNTAIN_DESCRIPTORS: &[&str] = &[
    "Cloudpiercer", "Frostfang", "Sunspear", "Stormcrown", "Ashpeak",
    "Greyhorn", "Ironreach", "Mistwall", "Skyforge", "Thunderridge",
];

const RIVER_DESCRIPTORS: &[&str] = &[
    "Quickwater", "Silvercourse", "Black", "Goldrun", "Whisper",
    "Coldstream", "Greenway", "Bright", "Stillrun", "Hollow",
];

const WATER_BODY_DESCRIPTORS: &[&str] = &[
    "Whitecap Sea", "Sunken Bay", "Twilight Reach", "Sapphire Strait",
    "Mistwarden Sea", "Forgotten Bay", "Crystal Reach", "Halcyon Sound",
    "Verdant Coast", "Stormwatch Sea",
];

fn pick<'a>(pool: &'a [&'a str], rng: &mut Rng) -> &'a str {
    pool[(rng.next_u32() as usize) % pool.len()]
}

/// **Civ Ship 7** — assign deterministic synthetic names. Seeded RNG
/// picks each name from a small per-category pool; settlement IDs
/// disambiguate when pool < feature count (e.g. `"Brightford-7"`).
///
/// **NOT an LLM call.** Use [`name_civ_via_llm`] for LLM-driven naming
/// at the cost of non-determinism.
#[allow(clippy::too_many_arguments)]
pub fn apply_synthetic_names(
    features: &mut Features,
    political: &mut Political,
    settlements: &mut [Settlement],
    culture: &mut Culture,
    seed: u64,
) {
    let mut rng = Rng::for_stage(seed, b"civ-naming");
    for (i, s) in settlements.iter_mut().enumerate() {
        s.name = format!("{}-{i}", pick(SETTLEMENT_NAMES, &mut rng));
    }
    for (i, st) in political.states.iter_mut().enumerate() {
        st.name = format!("{}-{i}", pick(STATE_NAMES, &mut rng));
    }
    for (i, p) in political.provinces.iter_mut().enumerate() {
        let prefix = pick(PROVINCE_PREFIXES, &mut rng);
        let root = pick(PROVINCE_ROOTS, &mut rng);
        p.name = format!("{prefix} {root}-{i}");
    }
    for (i, c) in culture.culture_regions.iter_mut().enumerate() {
        c.name = format!("{}-{i}", pick(CULTURE_NAMES, &mut rng));
    }
    for (i, mr) in features.mountain_ranges.iter_mut().enumerate() {
        mr.name = format!(
            "{} Mountains-{i}",
            pick(MOUNTAIN_DESCRIPTORS, &mut rng)
        );
    }
    for (i, rv) in features.rivers.iter_mut().enumerate() {
        rv.name = format!("{} River-{i}", pick(RIVER_DESCRIPTORS, &mut rng));
    }
    for (i, wb) in features.water_bodies.iter_mut().enumerate() {
        wb.name = format!("{}-{i}", pick(WATER_BODY_DESCRIPTORS, &mut rng));
    }
}

// ---------- LLM-driven naming ----------

/// JSON schema the LLM-driven naming caller asks the [`TextProvider`]
/// to fill. One string array per named-feature category.
fn civ_names_schema() -> serde_json::Value {
    let str_array = || serde_json::json!({ "type": "array", "items": { "type": "string" } });
    serde_json::json!({
        "type": "object",
        "additionalProperties": false,
        "required": [
            "settlements", "states", "provinces", "cultures",
            "mountain_ranges", "rivers", "water_bodies"
        ],
        "properties": {
            "settlements": str_array(),
            "states": str_array(),
            "provinces": str_array(),
            "cultures": str_array(),
            "mountain_ranges": str_array(),
            "rivers": str_array(),
            "water_bodies": str_array(),
        }
    })
}

#[derive(Debug, serde::Deserialize)]
struct CivNames {
    #[serde(default)]
    settlements: Vec<String>,
    #[serde(default)]
    states: Vec<String>,
    #[serde(default)]
    provinces: Vec<String>,
    #[serde(default)]
    cultures: Vec<String>,
    #[serde(default)]
    mountain_ranges: Vec<String>,
    #[serde(default)]
    rivers: Vec<String>,
    #[serde(default)]
    water_bodies: Vec<String>,
}

/// **Civ Ship 7b** — name civilization features via a
/// [`TextProvider`]. Builds a structured prompt with feature counts +
/// archetype, parses the JSON reply, applies names by position.
///
/// **NOT deterministic when using a real LLM.** Use
/// [`apply_synthetic_names`] for the deterministic alternative.
pub fn name_civ_via_llm(
    features: &mut Features,
    political: &mut Political,
    settlements: &mut [Settlement],
    culture: &mut Culture,
    provider: &dyn TextProvider,
    archetype: &str,
) -> Result<(), LlmError> {
    let system = "You are a world-naming assistant for a procedural fantasy-map \
                  generator. Given a world's archetype and the counts of its \
                  features, produce ONE JSON object of name lists matching the \
                  provided schema. For each category produce exactly the \
                  requested number of distinct, evocative proper names that \
                  fit the archetype. Output only the JSON object.";
    let user = format!(
        "Archetype: {archetype}.\n\
         Name these features — produce exactly the given count of distinct \
         names per category:\n\
         - settlements: {}\n\
         - states: {}\n\
         - provinces: {}\n\
         - cultures: {}\n\
         - mountain_ranges: {}\n\
         - rivers: {}\n\
         - water_bodies: {}",
        settlements.len(),
        political.states.len(),
        political.provinces.len(),
        culture.culture_regions.len(),
        features.mountain_ranges.len(),
        features.rivers.len(),
        features.water_bodies.len(),
    );

    let prompt = TextPrompt::new(system, user).with_schema(civ_names_schema(), "world_names");
    let raw = provider.complete(&prompt)?;
    let names: CivNames = serde_json::from_str(raw.trim()).map_err(|e| {
        let excerpt: String = raw.chars().take(200).collect();
        LlmError::InvalidResponse(format!(
            "CivNames JSON parse failed: {e}; first 200 chars: {excerpt}"
        ))
    })?;

    // **MED-1 fix (review 2026-05-30)**: zip-shortest silently truncates
    // when LLM under-delivers (`#[serde(default)]` on every CivNames field
    // means missing categories deserialize to empty Vec, no parse error).
    // Reject so the CLI's fall-through to `apply_synthetic_names` fires
    // for partial responses rather than leaving land features unnamed.
    let shortfalls = [
        ("settlements", names.settlements.len(), settlements.len()),
        ("states", names.states.len(), political.states.len()),
        ("provinces", names.provinces.len(), political.provinces.len()),
        ("cultures", names.cultures.len(), culture.culture_regions.len()),
        ("mountain_ranges", names.mountain_ranges.len(), features.mountain_ranges.len()),
        ("rivers", names.rivers.len(), features.rivers.len()),
        ("water_bodies", names.water_bodies.len(), features.water_bodies.len()),
    ];
    for (label, got, wanted) in shortfalls {
        if got < wanted {
            return Err(LlmError::InvalidResponse(format!(
                "LLM returned {got}/{wanted} names for `{label}` — under-delivery"
            )));
        }
    }

    for (s, n) in settlements.iter_mut().zip(&names.settlements) {
        s.name = n.clone();
    }
    for (s, n) in political.states.iter_mut().zip(&names.states) {
        s.name = n.clone();
    }
    for (p, n) in political.provinces.iter_mut().zip(&names.provinces) {
        p.name = n.clone();
    }
    for (c, n) in culture.culture_regions.iter_mut().zip(&names.cultures) {
        c.name = n.clone();
    }
    for (mr, n) in features.mountain_ranges.iter_mut().zip(&names.mountain_ranges) {
        mr.name = n.clone();
    }
    for (rv, n) in features.rivers.iter_mut().zip(&names.rivers) {
        rv.name = n.clone();
    }
    for (wb, n) in features.water_bodies.iter_mut().zip(&names.water_bodies) {
        wb.name = n.clone();
    }
    Ok(())
}

// ---------- COSMETIC-2: CivBundle in-place renamer helper ----------

/// **COSMETIC-2 fix (review 2026-05-30)** — rename a [`CivBundle`]
/// in-place via a [`TextProvider`], hiding the field-shuffle dance
/// (the CLI previously inlined 8× `std::mem::take` calls + repack).
///
/// On success: features / political / culture vectors are renamed
/// according to the provider's reply, then `content_hash` is
/// recomputed so the bundle remains hash-coherent.
///
/// On failure (transport error / parse error / under-delivery):
/// fields are repacked unchanged from `bundle_civ`'s synthetic-named
/// state, `content_hash` is left untouched, and the `LlmError` is
/// returned for the caller's fall-through to handle (typical CLI
/// pattern: log the error and keep synthetic names).
pub fn rename_bundle_in_place(
    bundle: &mut super::bundle::CivBundle,
    provider: &dyn TextProvider,
    archetype: &str,
) -> Result<(), LlmError> {
    let mut features = crate::feature::Features {
        mountain_ranges: std::mem::take(&mut bundle.mountain_ranges),
        rivers: std::mem::take(&mut bundle.rivers),
        water_bodies: std::mem::take(&mut bundle.water_bodies),
    };
    let mut political = crate::political::Political {
        province_of: std::mem::take(&mut bundle.province_of),
        provinces: std::mem::take(&mut bundle.provinces),
        states: std::mem::take(&mut bundle.states),
    };
    let mut culture = crate::culture::Culture {
        culture_of: std::mem::take(&mut bundle.culture_of),
        culture_regions: std::mem::take(&mut bundle.culture_regions),
    };
    let result = name_civ_via_llm(
        &mut features,
        &mut political,
        &mut bundle.settlements,
        &mut culture,
        provider,
        archetype,
    );
    // Repack regardless of result so the bundle is back in a valid
    // state for downstream renderers.
    bundle.mountain_ranges = features.mountain_ranges;
    bundle.rivers = features.rivers;
    bundle.water_bodies = features.water_bodies;
    bundle.province_of = political.province_of;
    bundle.provinces = political.provinces;
    bundle.states = political.states;
    bundle.culture_of = culture.culture_of;
    bundle.culture_regions = culture.culture_regions;
    if result.is_ok() {
        bundle.content_hash = super::bundle::compute_civ_hash(bundle);
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::creative_seed::SettlementDensity;
    use crate::flat_climate::WorldClimateParams;
    use crate::flatworld::{generate, FlatParams};

    use super::super::pipeline::build_culture;

    /// Test-only [`TextProvider`] that always returns 200 entries per array
    /// field — large enough to satisfy the **MED-1** truncation guard for
    /// any test world we generate. Names are FNV-keyed on the user message
    /// so determinism per prompt is preserved (same as
    /// [`MockTextProvider`]) but archetype changes still produce different
    /// names (the archetype string is part of the user message).
    ///
    /// Used by the post-MED-1 happy-path tests; the un-sized
    /// [`MockTextProvider`] is still used by
    /// [`name_civ_via_llm_rejects_under_delivery`] to exercise the new
    /// guard on a default-size world.
    #[derive(Debug, Clone)]
    struct OverFillTextProvider;

    impl TextProvider for OverFillTextProvider {
        fn complete(&self, prompt: &TextPrompt) -> Result<String, LlmError> {
            let mut h: u32 = 0x811C_9DC5;
            for byte in prompt.user.as_bytes() {
                h ^= *byte as u32;
                h = h.wrapping_mul(0x0100_0193);
            }
            const N: usize = 200;
            let fill = |key: &str| {
                (0..N)
                    .map(|i| {
                        serde_json::Value::String(format!(
                            "{}-{:08x}-{i}",
                            key,
                            h.wrapping_add(i as u32),
                        ))
                    })
                    .collect::<Vec<_>>()
            };
            let payload = serde_json::json!({
                "settlements": fill("S"),
                "states": fill("ST"),
                "provinces": fill("P"),
                "cultures": fill("C"),
                "mountain_ranges": fill("MR"),
                "rivers": fill("R"),
                "water_bodies": fill("WB"),
            });
            Ok(serde_json::to_string(&payload).expect("overfill JSON"))
        }
    }

    #[test]
    fn synthetic_names_populate_every_named_feature() {
        let world = generate(&FlatParams::default());
        let (_view, mut features, mut political, _hyd, mut settlements, _routes_v, mut culture_v) =
            build_culture(
                &world,
                &WorldClimateParams::default(),
                64,
                42,
                SettlementDensity::Medium,
                5,
            );
        apply_synthetic_names(
            &mut features,
            &mut political,
            &mut settlements,
            &mut culture_v,
            42,
        );
        for s in &settlements {
            assert!(!s.name.is_empty(), "settlement {} unnamed", s.cell);
        }
        for st in &political.states {
            assert!(!st.name.is_empty(), "state {} unnamed", st.id);
        }
        for p in &political.provinces {
            assert!(!p.name.is_empty(), "province {} unnamed", p.id);
        }
        for c in &culture_v.culture_regions {
            assert!(!c.name.is_empty(), "culture {} unnamed", c.id);
        }
        for mr in &features.mountain_ranges {
            assert!(!mr.name.is_empty(), "mountain {} unnamed", mr.id);
        }
        for wb in &features.water_bodies {
            assert!(!wb.name.is_empty(), "water body {} unnamed", wb.id);
        }
    }

    #[test]
    fn synthetic_names_are_deterministic_per_seed() {
        let world = generate(&FlatParams::default());

        let make_bundle = || {
            let (_, f, p, _, s, _, c) = build_culture(
                &world,
                &WorldClimateParams::default(),
                32,
                99,
                SettlementDensity::Medium,
                5,
            );
            (f, p, s, c)
        };
        let (mut fa, mut pa, mut sa, mut ca) = make_bundle();
        let (mut fb, mut pb, mut sb, mut cb) = make_bundle();
        apply_synthetic_names(&mut fa, &mut pa, &mut sa, &mut ca, 99);
        apply_synthetic_names(&mut fb, &mut pb, &mut sb, &mut cb, 99);
        for (a, b) in sa.iter().zip(sb.iter()) {
            assert_eq!(a.name, b.name);
        }
        for (a, b) in pa.provinces.iter().zip(pb.provinces.iter()) {
            assert_eq!(a.name, b.name);
        }
    }

    #[test]
    fn synthetic_names_differ_across_seeds() {
        let world = generate(&FlatParams::default());

        let make_bundle = || {
            let (_, f, p, _, s, _, c) = build_culture(
                &world,
                &WorldClimateParams::default(),
                32,
                7,
                SettlementDensity::Medium,
                5,
            );
            (f, p, s, c)
        };
        let (mut fa, mut pa, mut sa, mut ca) = make_bundle();
        let (mut fb, mut pb, mut sb, mut cb) = make_bundle();
        apply_synthetic_names(&mut fa, &mut pa, &mut sa, &mut ca, 1);
        apply_synthetic_names(&mut fb, &mut pb, &mut sb, &mut cb, 999);
        let differ = sa.iter().zip(sb.iter()).any(|(a, b)| a.name != b.name);
        assert!(differ, "two distinct seeds produced identical settlement names");
    }

    #[test]
    fn name_civ_via_llm_with_overfill_populates_every_entity() {
        // **COSMETIC-1 fix (review 2026-05-30)**: previous test bar was
        // `>= 1` named — passed even when only 5/N got renamed under the
        // pre-MED-1 silent-truncation bug. Now: full delivery from
        // `OverFillTextProvider` MUST rename every entity in every
        // category.
        let world = generate(&FlatParams::default());
        let (_, mut features, mut political, _, mut settlements, _routes_v, mut culture_v) =
            build_culture(
                &world,
                &WorldClimateParams::default(),
                64,
                42,
                SettlementDensity::Medium,
                5,
            );
        let provider = OverFillTextProvider;
        name_civ_via_llm(
            &mut features,
            &mut political,
            &mut settlements,
            &mut culture_v,
            &provider,
            "HighFantasy",
        )
        .expect("overfill should succeed");

        let unnamed_settlements = settlements.iter().filter(|s| s.name.is_empty()).count();
        let unnamed_states = political.states.iter().filter(|s| s.name.is_empty()).count();
        let unnamed_provinces = political.provinces.iter().filter(|p| p.name.is_empty()).count();
        let unnamed_cultures =
            culture_v.culture_regions.iter().filter(|c| c.name.is_empty()).count();
        let unnamed_mountains =
            features.mountain_ranges.iter().filter(|m| m.name.is_empty()).count();
        let unnamed_rivers = features.rivers.iter().filter(|r| r.name.is_empty()).count();
        let unnamed_water =
            features.water_bodies.iter().filter(|w| w.name.is_empty()).count();
        assert_eq!(unnamed_settlements, 0, "settlements unnamed");
        assert_eq!(unnamed_states, 0, "states unnamed");
        assert_eq!(unnamed_provinces, 0, "provinces unnamed");
        assert_eq!(unnamed_cultures, 0, "cultures unnamed");
        assert_eq!(unnamed_mountains, 0, "mountain ranges unnamed");
        assert_eq!(unnamed_rivers, 0, "rivers unnamed");
        assert_eq!(unnamed_water, 0, "water bodies unnamed");
    }

    #[test]
    fn name_civ_via_llm_rejects_under_delivery() {
        // **MED-1 (review 2026-05-30)**: when LLM returns fewer names than
        // features, the function MUST error so the CLI's fall-through to
        // synthetic naming fires. `EmptyArraysTextProvider` returns an
        // empty array for every category — under-delivers as long as the
        // world has ≥1 feature in any category, which the default world
        // always does (≥1 settlement post Ship 4 settlement wire-up).
        #[derive(Debug)]
        struct EmptyArraysTextProvider;
        impl TextProvider for EmptyArraysTextProvider {
            fn complete(&self, _: &TextPrompt) -> Result<String, LlmError> {
                Ok(r#"{"settlements":[],"states":[],"provinces":[],"cultures":[],"mountain_ranges":[],"rivers":[],"water_bodies":[]}"#.to_string())
            }
        }

        let world = generate(&FlatParams::default());
        let (_, mut features, mut political, _, mut settlements, _, mut culture_v) =
            build_culture(
                &world,
                &WorldClimateParams::default(),
                64,
                42,
                SettlementDensity::Medium,
                5,
            );
        assert!(
            !settlements.is_empty() || !political.provinces.is_empty(),
            "test premise: default world must yield ≥1 feature somewhere",
        );
        let err = name_civ_via_llm(
            &mut features,
            &mut political,
            &mut settlements,
            &mut culture_v,
            &EmptyArraysTextProvider,
            "HighFantasy",
        )
        .expect_err("under-delivery must error");
        let LlmError::InvalidResponse(msg) = err else {
            panic!("expected InvalidResponse, got {err:?}");
        };
        assert!(
            msg.contains("under-delivery"),
            "error should name the under-delivery condition, got: {msg}"
        );
    }

    #[test]
    fn name_civ_via_llm_is_deterministic_with_overfill_and_archetype() {
        let world = generate(&FlatParams::default());

        let make_bundle = || {
            let (_, f, p, _, s, _, c) = build_culture(
                &world,
                &WorldClimateParams::default(),
                32,
                99,
                SettlementDensity::Medium,
                5,
            );
            (f, p, s, c)
        };
        let (mut fa, mut pa, mut sa, mut ca) = make_bundle();
        let (mut fb, mut pb, mut sb, mut cb) = make_bundle();
        let provider = OverFillTextProvider;
        name_civ_via_llm(&mut fa, &mut pa, &mut sa, &mut ca, &provider, "HighFantasy").unwrap();
        name_civ_via_llm(&mut fb, &mut pb, &mut sb, &mut cb, &provider, "HighFantasy").unwrap();
        for (a, b) in sa.iter().zip(sb.iter()) {
            assert_eq!(a.name, b.name);
        }
        for (a, b) in pa.provinces.iter().zip(pb.provinces.iter()) {
            assert_eq!(a.name, b.name);
        }
    }

    #[test]
    fn name_civ_via_llm_differs_across_archetypes_via_overfill_hash() {
        let world = generate(&FlatParams::default());

        let make_bundle = || {
            let (_, f, p, _, s, _, c) = build_culture(
                &world,
                &WorldClimateParams::default(),
                32,
                7,
                SettlementDensity::Medium,
                5,
            );
            (f, p, s, c)
        };
        let (mut fa, mut pa, mut sa, mut ca) = make_bundle();
        let (mut fb, mut pb, mut sb, mut cb) = make_bundle();
        let provider = OverFillTextProvider;
        name_civ_via_llm(&mut fa, &mut pa, &mut sa, &mut ca, &provider, "HighFantasy").unwrap();
        name_civ_via_llm(&mut fb, &mut pb, &mut sb, &mut cb, &provider, "Cyberpunk").unwrap();
        let differ = sa.iter().zip(sb.iter()).any(|(a, b)| a.name != b.name);
        assert!(differ);
    }

    #[test]
    fn name_civ_via_llm_returns_invalid_response_on_garbage() {
        #[derive(Debug)]
        struct GarbageProvider;
        impl TextProvider for GarbageProvider {
            fn complete(&self, _: &TextPrompt) -> Result<String, LlmError> {
                Ok("definitely not json {".to_string())
            }
        }

        let world = generate(&FlatParams::default());
        let (_, mut features, mut political, _, mut settlements, _, mut culture_v) =
            build_culture(
                &world,
                &WorldClimateParams::default(),
                32,
                7,
                SettlementDensity::Medium,
                5,
            );
        let err = name_civ_via_llm(
            &mut features,
            &mut political,
            &mut settlements,
            &mut culture_v,
            &GarbageProvider,
            "HighFantasy",
        )
        .expect_err("garbage should fail");
        assert!(matches!(err, LlmError::InvalidResponse(_)));
    }
}
