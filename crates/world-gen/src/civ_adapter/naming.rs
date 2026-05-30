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
        LlmError::InvalidResponse(format!("CivNames JSON parse failed: {e}"))
    })?;

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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::creative_seed::SettlementDensity;
    use crate::flat_climate::WorldClimateParams;
    use crate::flatworld::{generate, FlatParams};
    use crate::shape::llm::MockTextProvider;

    use super::super::pipeline::build_culture;

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
    fn name_civ_via_llm_with_mock_populates_every_category() {
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
        let provider = MockTextProvider::new();
        name_civ_via_llm(
            &mut features,
            &mut political,
            &mut settlements,
            &mut culture_v,
            &provider,
            "HighFantasy",
        )
        .expect("mock should succeed");

        let named_settlements = settlements.iter().filter(|s| !s.name.is_empty()).count();
        let named_states = political.states.iter().filter(|s| !s.name.is_empty()).count();
        assert!(named_settlements >= 1);
        assert!(named_states >= 1);
    }

    #[test]
    fn name_civ_via_llm_is_deterministic_with_mock_and_archetype() {
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
        let provider = MockTextProvider::new();
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
    fn name_civ_via_llm_differs_across_archetypes_via_mock_hash() {
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
        let provider = MockTextProvider::new();
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
