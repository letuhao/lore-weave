//! GEO_001b authoring — turn a prose brief into a schema-valid `CreativeSeed`
//! via an LLM (an OpenAI-compatible `/chat/completions` endpoint).
//!
//! The LLM call is **non-deterministic**, but it only produces the *input*
//! `CreativeSeed`; `generate(seed, creative_seed)` downstream is as pure and
//! deterministic as ever.

use serde_json::{Value, json};

use crate::creative_seed::CreativeSeed;

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
heavier erosion means deeper valleys, broader river networks, softer mountains. \
Choose values that fit the brief. Output only the JSON object.";

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
                "Pocket", "Region", "Continent", "SuperContinent", "Megaplanet"
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
            "culture_count": { "type": "integer", "minimum": 1, "maximum": 16 }
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
    Ok(cs)
}

/// Extract `choices[0].message.content` from a chat-completions response body.
/// Navigates with `get`/`as_*` (never `unwrap`/index) so an error envelope or
/// a refusal (no `choices`, null `content`) returns a clear `Err`.
fn extract_message_content(response_body: &str) -> Result<String, String> {
    let v: Value = serde_json::from_str(response_body)
        .map_err(|e| format!("LLM response was not JSON: {e}"))?;
    v.get("choices")
        .and_then(Value::as_array)
        .and_then(|a| a.first())
        .and_then(|c| c.get("message"))
        .and_then(|m| m.get("content"))
        .and_then(Value::as_str)
        .map(str::to_string)
        .ok_or_else(|| "LLM response had no message content".to_string())
}

/// Request a `CreativeSeed` from an OpenAI-compatible chat endpoint.
///
/// `llm_url` is the API base (e.g. `http://localhost:1234/v1`); `model` is the
/// model id. Every failure path returns a descriptive `Err` — no panic.
pub fn request_creative_seed(
    brief: &str,
    llm_url: &str,
    model: &str,
) -> Result<CreativeSeed, String> {
    let content = llm_json_request(
        llm_url,
        model,
        SYSTEM_PROMPT,
        brief,
        creative_seed_schema(),
        "creative_seed",
    )?;
    parse_creative_seed(&content)
}

/// Shared LLM call — POST a json-schema-constrained chat completion to an
/// OpenAI-compatible endpoint and return the message `content` string. Used by
/// [`request_creative_seed`] and `crate::naming`. Every failure path returns a
/// descriptive `Err` — no panic; an explicit timeout stops a stalled endpoint
/// from hanging the CLI forever.
pub(crate) fn llm_json_request(
    llm_url: &str,
    model: &str,
    system_prompt: &str,
    user_prompt: &str,
    schema: Value,
    schema_name: &str,
) -> Result<String, String> {
    let body = json!({
        "model": model,
        "messages": [
            { "role": "system", "content": system_prompt },
            { "role": "user", "content": user_prompt }
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": true,
                "schema": schema
            }
        }
    });
    let url = format!("{}/chat/completions", llm_url.trim_end_matches('/'));
    let client = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(120))
        .build()
        .map_err(|e| format!("LLM client build failed: {e}"))?;
    let resp = client
        .post(&url)
        .json(&body)
        .send()
        .map_err(|e| format!("LLM request to {url} failed: {e}"))?;
    let status = resp.status();
    let text = resp
        .text()
        .map_err(|e| format!("reading LLM response failed: {e}"))?;
    if !status.is_success() {
        let snippet: String = text.chars().take(200).collect();
        return Err(format!("LLM HTTP {status}: {snippet}"));
    }
    extract_message_content(&text)
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
    fn extract_content_from_valid_response() {
        let resp = json!({
            "choices": [{ "message": { "content": "the seed" } }]
        })
        .to_string();
        assert_eq!(extract_message_content(&resp).unwrap(), "the seed");
    }

    #[test]
    fn request_to_unreachable_endpoint_errors_cleanly() {
        // `.invalid` is reserved never to resolve (RFC 6761) — `send()` fails
        // fast; the error contract must surface a descriptive `Err`, never
        // panic and never hang. (The common real failure: LM Studio is down.)
        let r = request_creative_seed("a brief", "http://geo-gen.invalid/v1", "m");
        assert!(r.is_err(), "unreachable endpoint must return Err, got {r:?}");
    }

    #[test]
    fn extract_content_rejects_error_envelope() {
        // a non-2xx body / refusal has no `choices`.
        let envelope = json!({ "error": { "message": "bad request" } }).to_string();
        assert!(extract_message_content(&envelope).is_err());
        // empty choices / null content.
        assert!(extract_message_content(&json!({ "choices": [] }).to_string()).is_err());
        let null_content =
            json!({ "choices": [{ "message": { "content": null } }] }).to_string();
        assert!(extract_message_content(&null_content).is_err());
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
        assert_eq!(count("world_scale"), 5, "world_scale enum count");
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
