//! Freeze a script `scenario` into the durable `charter` + the chat-service
//! `working_memory_seed`.
//!
//! The seed MUST be byte-compatible with chat-service's `WorkingMemory` model
//! (M3 anchoring + the executive read it): `{version, charter{goal, phases,
//! checklist, time_budget_min, language}, state{…}}` with an optional sibling
//! `rubric`. The scenario is a superset — interview presets carry `goal` /
//! `checklist` directly; freeform roleplay uses `premise` / `beats`. We accept
//! both (goal||premise, checklist||beats) and always emit the canonical charter.

use contracts_agent_control::{Charter, WorkingMemory};
use serde_json::Value;
#[cfg(test)]
use serde_json::json;

fn str_field(v: &Value, key: &str) -> Option<String> {
    v.get(key).and_then(Value::as_str).map(str::to_owned).filter(|s| !s.trim().is_empty())
}

fn str_array(v: &Value, key: &str) -> Vec<String> {
    v.get(key)
        .and_then(Value::as_array)
        .map(|a| a.iter().filter_map(Value::as_str).map(str::to_owned).collect())
        .unwrap_or_default()
}

/// ACP A4 (RV-M4/RV-M7) — the default number of questions an INTERVIEW drives before wrapping,
/// applied at freeze-time when the scenario doesn't pin one. Defaulting by genre here (not by a
/// seed data-migration) keeps A0–A4 migration-free (RW-12) and makes EXISTING preset rows wrap
/// correctly. Freeform roleplay leaves `question_target` unset ⇒ no count-wrap.
const DEFAULT_INTERVIEW_QUESTION_TARGET: i64 = 5;

/// Returns `(charter, seed)`. `charter` is stored verbatim in `rp_memory`; `seed`
/// is sent as `working_memory_seed` to chat-service. `fallback_goal` (the script
/// name) is used only when neither `goal` nor `premise` is present, since the
/// chat-service charter requires a non-empty goal. `genre` supplies the interview
/// `question_target` default (A4).
pub fn freeze(
    scenario: &Value,
    rubric: Option<&Value>,
    fallback_goal: &str,
    genre: &str,
) -> (Value, Value) {
    let goal = str_field(scenario, "goal")
        .or_else(|| str_field(scenario, "premise"))
        .unwrap_or_else(|| fallback_goal.to_string());

    // chat-service requires phases min_length=1 — default to a single generic
    // phase so a sparse pasted scenario still produces a valid seed.
    let mut phases = str_array(scenario, "phases");
    if phases.is_empty() {
        phases = vec!["roleplay".to_string()];
    }

    let mut checklist = str_array(scenario, "checklist");
    if checklist.is_empty() {
        checklist = str_array(scenario, "beats");
    }

    let language = str_field(scenario, "language").unwrap_or_else(|| "en".to_string());
    let time_budget_min = scenario.get("time_budget_min").and_then(Value::as_i64);
    // A4 — the scenario may pin question_target; else an interview genre defaults to 5, a
    // freeform roleplay leaves it None (no count-wrap).
    let question_target = scenario.get("question_target").and_then(Value::as_i64).or({
        if genre == "interview" { Some(DEFAULT_INTERVIEW_QUESTION_TARGET) } else { None }
    });

    // ACP A3 — build the charter + seed via the shared TYPED contract structs (not hand-rolled
    // JSON), so the producer can't drift from chat/knowledge's WorkingMemory (the comment above
    // warned about exactly this). The serialized Value is byte-identical to the prior json! for a
    // non-interview charter; an interview charter additionally carries question_target (A4).
    let charter = Charter { goal, phases, checklist, time_budget_min, language, question_target };
    let seed = WorkingMemory::seed(charter.clone(), rubric.cloned());
    (
        serde_json::to_value(&charter).expect("charter serializes"),
        serde_json::to_value(&seed).expect("seed serializes"),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn interview_scenario_maps_goal_and_checklist() {
        let scenario = json!({
            "goal": "Assess senior SWE skill",
            "phases": ["warmup", "coding", "wrap"],
            "checklist": ["clarifies the problem", "states complexity"],
            "time_budget_min": 45,
            "language": "en"
        });
        let rubric = json!({"dimensions": ["clarity"]});
        let (charter, seed) = freeze(&scenario, Some(&rubric), "FAANG SWE", "interview");
        assert_eq!(charter["goal"], "Assess senior SWE skill");
        assert_eq!(charter["phases"].as_array().unwrap().len(), 3);
        assert_eq!(charter["checklist"].as_array().unwrap().len(), 2);
        assert_eq!(charter["time_budget_min"], 45);
        // A4 — an interview genre defaults question_target to 5 (the scenario pinned none).
        assert_eq!(charter["question_target"], 5);
        // Seed must match the chat-service WorkingMemory shape exactly.
        assert_eq!(seed["version"], 1);
        assert_eq!(seed["charter"], charter);
        assert_eq!(seed["state"]["phase"], "");
        assert!(seed["state"]["covered"].as_array().unwrap().is_empty());
        assert!(seed["state"].get("elapsed_min").is_some()); // present as null
        assert_eq!(seed["rubric"], rubric);
    }

    #[test]
    fn roleplay_scenario_maps_premise_and_beats() {
        let scenario = json!({
            "premise": "A tense negotiation aboard a derelict freighter",
            "beats": ["establish leverage", "reveal the hidden cargo"],
        });
        let (charter, seed) = freeze(&scenario, None, "Freighter", "roleplay");
        assert_eq!(charter["goal"], "A tense negotiation aboard a derelict freighter");
        assert_eq!(charter["checklist"].as_array().unwrap().len(), 2);
        // No phases supplied → default single phase (chat charter needs ≥1).
        assert_eq!(charter["phases"], json!(["roleplay"]));
        assert_eq!(charter["language"], "en");
        assert_eq!(charter["time_budget_min"], Value::Null);
        assert!(seed.get("rubric").is_none());
        // A4 — a freeform roleplay leaves question_target unset (no count-wrap).
        assert!(charter.get("question_target").is_none());
    }

    #[test]
    fn empty_scenario_uses_fallback_goal() {
        let (charter, _) = freeze(&json!({}), None, "My Script", "roleplay");
        assert_eq!(charter["goal"], "My Script");
        assert_eq!(charter["phases"], json!(["roleplay"]));
        assert_eq!(charter["checklist"], json!([]));
    }

    // ── ACP A0.3 / RW-8 — the PRODUCER side of the working_memory contract ──────
    // roleplay-service freezes the seed that chat/knowledge consume. This validates
    // the REAL `freeze()` output (not a fixture) against the shared JSON Schema
    // contract, machine-READING the schema (so a schema change propagates — no
    // hand-mirrored rules). Covers the drift modes RW-8 targets: a required key
    // missing, and an UNDECLARED top-level key (additionalProperties:false) — the
    // exact class that surfaced `rubric` was unmodelled by the schema.

    fn load_schema() -> Value {
        // CARGO_MANIFEST_DIR = services/roleplay-service ; repo root is two up.
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../contracts/agent-control/working_memory.schema.json");
        let text = std::fs::read_to_string(&path)
            .unwrap_or_else(|e| panic!("read schema {}: {e}", path.display()));
        serde_json::from_str(&text).expect("schema is valid JSON")
    }

    /// Does `value` match a schema `type` node (a string like "array", or a union
    /// array like ["integer","null"])? Reads the allowed type(s) FROM the schema.
    fn type_matches(value: &Value, type_node: &Value) -> bool {
        let allowed: Vec<&str> = match type_node {
            Value::String(s) => vec![s.as_str()],
            Value::Array(a) => a.iter().filter_map(Value::as_str).collect(),
            Value::Null => return true, // no `type` declared ⇒ unconstrained
            _ => return true,
        };
        allowed.iter().any(|t| match *t {
            "null" => value.is_null(),
            "string" => value.is_string(),
            "integer" => value.is_i64() || value.is_u64(),
            "number" => value.is_number(),
            "boolean" => value.is_boolean(),
            "array" => value.is_array(),
            "object" => value.is_object(),
            _ => true,
        })
    }

    /// Structural + TYPE check of one object level against its schema node: every
    /// `required` key present; (when `additionalProperties:false`) no key outside
    /// the declared `properties`; and each present declared property matches its
    /// declared `type` (MED-1 fix — catches type drift, not just key drift). Reads
    /// all rules FROM the schema (no hand-mirror).
    fn assert_level_conforms(instance: &Value, schema_node: &Value, path: &str) {
        let obj = instance
            .as_object()
            .unwrap_or_else(|| panic!("{path}: expected an object"));
        for req in schema_node["required"].as_array().into_iter().flatten() {
            let key = req.as_str().unwrap();
            assert!(obj.contains_key(key), "{path}: missing required key '{key}'");
        }
        let props = schema_node["properties"].as_object();
        let closed = schema_node
            .get("additionalProperties")
            .and_then(Value::as_bool)
            == Some(false);
        if closed {
            let p = props.expect("closed object must declare properties");
            for key in obj.keys() {
                assert!(
                    p.contains_key(key),
                    "{path}: undeclared key '{key}' (additionalProperties:false) — producer/schema drift"
                );
            }
        }
        // Type-check each present declared property against its schema `type`.
        if let Some(p) = props {
            for (key, val) in obj {
                if let Some(prop_schema) = p.get(key) {
                    assert!(
                        type_matches(val, &prop_schema["type"]),
                        "{path}.{key}: value {val} does not match declared type {} — producer/schema type drift",
                        prop_schema["type"]
                    );
                }
            }
        }
    }

    fn assert_seed_conforms(seed: &Value, schema: &Value) {
        assert_level_conforms(seed, schema, "seed");
        assert_level_conforms(&seed["charter"], &schema["properties"]["charter"], "seed.charter");
        assert_level_conforms(&seed["state"], &schema["properties"]["state"], "seed.state");
    }

    #[test]
    fn freeze_output_conforms_to_working_memory_schema() {
        let schema = load_schema();
        // The 3 System interview presets, mirrored from the migration seed, WITH a
        // rubric sidecar (the case that exposed the schema gap).
        let presets = [
            (
                json!({"goal":"Assess senior software-engineering skill through a coding/problem-solving interview","phases":["warmup","coding","followup","wrap"],"checklist":["clarifies the problem before coding","states an approach and its complexity"],"time_budget_min":45,"language":"en"}),
                json!({"dimensions":["problem clarification","algorithmic approach","code correctness","communication"]}),
                "FAANG SWE Interview",
            ),
            (
                json!({"goal":"Assess behavioral fit through STAR stories","phases":["warmup","stories","followup","wrap"],"checklist":["gives a concrete Situation and Task"],"time_budget_min":40,"language":"en"}),
                json!({"dimensions":["STAR structure","specificity","ownership","reflection"]}),
                "Behavioral (HR) Interview",
            ),
            (
                json!({"goal":"Assess senior system-design skill","phases":["requirements","high_level","deep_dive","wrap"],"checklist":["clarifies functional and scale requirements"],"time_budget_min":50,"language":"en"}),
                json!({"dimensions":["requirements","architecture","scalability","trade-off reasoning"]}),
                "System Design Interview",
            ),
        ];
        for (scenario, rubric, name) in presets {
            let (_charter, seed) = freeze(&scenario, Some(&rubric), name, "interview");
            // The interview seed carries the rubric sidecar top-level (schema models it as of A0.3).
            assert!(seed.get("rubric").is_some(), "{name}: interview seed should carry a rubric");
            assert_seed_conforms(&seed, &schema);
        }
        // A freeform (no-rubric) seed must also conform.
        let (_c, seed) = freeze(&json!({"premise":"tense negotiation","beats":["establish leverage"]}), None, "Freighter", "roleplay");
        assert_seed_conforms(&seed, &schema);
    }

    #[test]
    fn conformance_check_actually_bites_on_drift() {
        let schema = load_schema();
        // (a) an undeclared top-level key must be caught.
        let (_c, mut seed) = freeze(&json!({"goal":"x","phases":["a"],"language":"en"}), None, "X", "roleplay");
        seed["surprise_field"] = json!("drift");
        let s1 = seed.clone();
        assert!(
            std::panic::catch_unwind(move || assert_seed_conforms(&s1, &schema)).is_err(),
            "must FAIL on an undeclared top-level key"
        );
        // (b) MED-1: a TYPE drift on a declared field must be caught too.
        let schema2 = load_schema();
        let (_c2, mut seed2) = freeze(&json!({"goal":"x","phases":["a"],"language":"en"}), None, "X", "roleplay");
        seed2["version"] = json!("not-an-integer"); // schema says integer
        assert!(
            std::panic::catch_unwind(move || assert_seed_conforms(&seed2, &schema2)).is_err(),
            "must FAIL on a declared-field TYPE drift (version as string)"
        );
    }
}
