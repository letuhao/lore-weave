//! Feature naming — turn an unnamed `WorldMap` into a named one via an LLM.
//!
//! Non-deterministic (the LLM call), so this is a **separate authoring step**:
//! `generate` stays pure, and the `name` fields are excluded from
//! `content_hash`. A short LLM response leaves the surplus features unnamed;
//! a failed request returns `Err` and leaves the map untouched.
//!
//! **Gateway invariant (CLAUDE.md, 2026-05-30)**: LLM calls flow through the
//! `loreweave_llm` SDK via a `&dyn TextProvider` — typically
//! [`crate::shape::GatewayTextProvider`] for the real backend or
//! [`crate::shape::MockTextProvider`] for offline tests. The prior
//! signature `(llm_url, model)` directly POSTed to an OpenAI-compatible
//! URL via `author::llm_json_request`, which the invariant forbids.

use serde::Deserialize;
use serde_json::{Value, json};

use crate::creative_seed::WorldArchetype;
use crate::shape::llm::{LlmError, TextPrompt, TextProvider};
use crate::world_map::WorldMap;

/// System prompt — instructs the LLM on the naming task.
const SYSTEM_PROMPT: &str = "\
You are a world-naming assistant for a procedural fantasy-map generator. Given \
a world's genre and the counts of its features, produce ONE JSON object of \
name lists matching the provided schema. For each category produce exactly the \
requested number of distinct, evocative proper names that fit the genre: place \
names for settlements, realm names for states, region names for provinces, \
people names for cultures, and natural-feature names for mountain ranges, \
rivers, and water bodies. Output only the JSON object.";

/// The LLM's name lists, one array per feature category. Each field is
/// `#[serde(default)]` so an omitted category just leaves those features
/// unnamed rather than failing the whole parse.
#[derive(Debug, Deserialize)]
struct WorldNames {
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

/// The JSON Schema constraining the LLM output to the `WorldNames` shape —
/// seven arrays of strings.
fn world_names_schema() -> Value {
    let str_array = || json!({ "type": "array", "items": { "type": "string" } });
    json!({
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
            "water_bodies": str_array()
        }
    })
}

/// Name every feature of `map` in place via a [`TextProvider`]. The map's
/// geometry is untouched, so `content_hash` (which excludes names) still
/// verifies.
///
/// A short LLM response leaves the surplus features unnamed; a failed
/// request returns [`Err`] and leaves the map unchanged.
///
/// **Soft-truncation contract preserved**: this naming step intentionally
/// accepts partial responses (see [`apply_names_tolerates_a_short_list`]
/// test). The civ-layer adapter (`civ_adapter::naming::name_civ_via_llm`)
/// has the opposite contract (errors on under-delivery) because it
/// follows a synthetic-naming pass that fills gaps; sphere `name_world`
/// has no synthetic fallback, so partial-named is the documented design.
pub fn name_world(
    map: &mut WorldMap,
    archetype: WorldArchetype,
    provider: &dyn TextProvider,
) -> Result<(), LlmError> {
    let user_prompt = format!(
        "Genre: {archetype:?}. Name these features — produce exactly the given \
         count of distinct names per category:\n\
         - settlements: {}\n- states: {}\n- provinces: {}\n- cultures: {}\n\
         - mountain_ranges: {}\n- rivers: {}\n- water_bodies: {}",
        map.settlements.len(),
        map.states.len(),
        map.provinces.len(),
        map.culture_regions.len(),
        map.mountain_ranges.len(),
        map.rivers.len(),
        map.water_bodies.len(),
    );
    let prompt = TextPrompt::new(SYSTEM_PROMPT, user_prompt)
        .with_schema(world_names_schema(), "world_names");
    let content = provider.complete(&prompt)?;
    let names: WorldNames = serde_json::from_str(content.trim())
        .map_err(|e| LlmError::InvalidResponse(format!("WorldNames JSON parse failed: {e}")))?;
    apply_names(map, &names);
    Ok(())
}

/// Apply the LLM name lists to the map's features by position. A list shorter
/// than its feature vec leaves the surplus features unnamed (`zip` stops); a
/// longer list is truncated.
fn apply_names(map: &mut WorldMap, names: &WorldNames) {
    for (s, n) in map.settlements.iter_mut().zip(&names.settlements) {
        s.name = n.clone();
    }
    for (s, n) in map.states.iter_mut().zip(&names.states) {
        s.name = n.clone();
    }
    for (p, n) in map.provinces.iter_mut().zip(&names.provinces) {
        p.name = n.clone();
    }
    for (c, n) in map.culture_regions.iter_mut().zip(&names.cultures) {
        c.name = n.clone();
    }
    for (mr, n) in map.mountain_ranges.iter_mut().zip(&names.mountain_ranges) {
        mr.name = n.clone();
    }
    for (rv, n) in map.rivers.iter_mut().zip(&names.rivers) {
        rv.name = n.clone();
    }
    for (wb, n) in map.water_bodies.iter_mut().zip(&names.water_bodies) {
        wb.name = n.clone();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::creative_seed::CreativeSeed;
    use crate::generate;

    fn names_of_len(prefix: &str, n: usize) -> Vec<String> {
        (0..n).map(|i| format!("{prefix}{i}")).collect()
    }

    #[test]
    fn apply_names_assigns_by_position_and_keeps_the_hash() {
        let mut map = generate(7, &CreativeSeed::default());
        let names = WorldNames {
            settlements: names_of_len("Town", map.settlements.len()),
            states: names_of_len("Realm", map.states.len()),
            provinces: names_of_len("Shire", map.provinces.len()),
            cultures: names_of_len("Folk", map.culture_regions.len()),
            mountain_ranges: names_of_len("Peaks", map.mountain_ranges.len()),
            rivers: names_of_len("River", map.rivers.len()),
            water_bodies: names_of_len("Sea", map.water_bodies.len()),
        };
        apply_names(&mut map, &names);
        for (i, s) in map.settlements.iter().enumerate() {
            assert_eq!(s.name, format!("Town{i}"));
        }
        for (i, s) in map.states.iter().enumerate() {
            assert_eq!(s.name, format!("Realm{i}"));
        }
        // Naming must not disturb the hashed geometry.
        assert!(map.verify_hash(), "naming changed the hashed geometry");
    }

    #[test]
    fn apply_names_tolerates_a_short_list() {
        let mut map = generate(7, &CreativeSeed::default());
        assert!(map.settlements.len() > 1, "test needs >= 2 settlements");
        let names = WorldNames {
            settlements: vec!["Only".to_string()], // shorter than the vec
            states: Vec::new(),
            provinces: Vec::new(),
            cultures: Vec::new(),
            mountain_ranges: Vec::new(),
            rivers: Vec::new(),
            water_bodies: Vec::new(),
        };
        apply_names(&mut map, &names);
        assert_eq!(map.settlements[0].name, "Only");
        assert_eq!(map.settlements[1].name, "", "a surplus feature must stay unnamed");
    }

    #[test]
    fn schema_lists_every_category() {
        let schema = world_names_schema();
        let props = schema
            .get("properties")
            .and_then(Value::as_object)
            .expect("schema must have a properties object");
        for cat in [
            "settlements",
            "states",
            "provinces",
            "cultures",
            "mountain_ranges",
            "rivers",
            "water_bodies",
        ] {
            assert!(props.contains_key(cat), "schema is missing category {cat}");
        }
    }

    #[test]
    fn apply_names_truncates_a_long_list() {
        // An LLM list longer than the feature vec — the extras are dropped,
        // no panic, and every feature is still named in order.
        let mut map = generate(7, &CreativeSeed::default());
        let names = WorldNames {
            settlements: Vec::new(),
            states: names_of_len("Realm", map.states.len() + 5),
            provinces: Vec::new(),
            cultures: Vec::new(),
            mountain_ranges: Vec::new(),
            rivers: Vec::new(),
            water_bodies: Vec::new(),
        };
        apply_names(&mut map, &names);
        for (i, s) in map.states.iter().enumerate() {
            assert_eq!(s.name, format!("Realm{i}"), "state {i} mis-named");
        }
    }

    #[test]
    fn name_world_provider_error_leaves_map_untouched() {
        // **2026-05-30 refactor**: the old `--llm-url unreachable-endpoint`
        // path is dead; the equivalent SDK-era contract is that any
        // TextProvider returning Err leaves the map unchanged. Verified
        // with an inline always-failing provider.
        use crate::shape::llm::{LlmError, TextPrompt, TextProvider};
        #[derive(Debug)]
        struct AlwaysFailProvider;
        impl TextProvider for AlwaysFailProvider {
            fn complete(&self, _: &TextPrompt) -> Result<String, LlmError> {
                Err(LlmError::Transport("simulated unreachable gateway".into()))
            }
        }
        let mut map = generate(7, &CreativeSeed::default());
        let before = map.clone();
        let r = name_world(&mut map, WorldArchetype::HighFantasy, &AlwaysFailProvider);
        assert!(r.is_err(), "failed provider must return Err, got {r:?}");
        assert_eq!(map, before, "a failed naming call must leave the map unchanged");
    }
}
