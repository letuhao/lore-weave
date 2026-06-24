//! Freeze a script `scenario` into the durable `charter` + the chat-service
//! `working_memory_seed`.
//!
//! The seed MUST be byte-compatible with chat-service's `WorkingMemory` model
//! (M3 anchoring + the executive read it): `{version, charter{goal, phases,
//! checklist, time_budget_min, language}, state{…}}` with an optional sibling
//! `rubric`. The scenario is a superset — interview presets carry `goal` /
//! `checklist` directly; freeform roleplay uses `premise` / `beats`. We accept
//! both (goal||premise, checklist||beats) and always emit the canonical charter.

use serde_json::{Value, json};

fn str_field(v: &Value, key: &str) -> Option<String> {
    v.get(key).and_then(Value::as_str).map(str::to_owned).filter(|s| !s.trim().is_empty())
}

fn str_array(v: &Value, key: &str) -> Vec<String> {
    v.get(key)
        .and_then(Value::as_array)
        .map(|a| a.iter().filter_map(Value::as_str).map(str::to_owned).collect())
        .unwrap_or_default()
}

/// Returns `(charter, seed)`. `charter` is stored verbatim in `rp_memory`; `seed`
/// is sent as `working_memory_seed` to chat-service. `fallback_goal` (the script
/// name) is used only when neither `goal` nor `premise` is present, since the
/// chat-service charter requires a non-empty goal.
pub fn freeze(scenario: &Value, rubric: Option<&Value>, fallback_goal: &str) -> (Value, Value) {
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

    let charter = json!({
        "goal": goal,
        "phases": phases,
        "checklist": checklist,
        "time_budget_min": time_budget_min,
        "language": language,
    });

    let mut seed = json!({
        "version": 1,
        "charter": charter.clone(),
        "state": {
            "phase": "",
            "covered": [],
            "elapsed_min": null,
            "drift_note": null,
            "redirect_hint": null,
        },
    });
    if let Some(r) = rubric {
        seed["rubric"] = r.clone();
    }

    (charter, seed)
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
        let (charter, seed) = freeze(&scenario, Some(&rubric), "FAANG SWE");
        assert_eq!(charter["goal"], "Assess senior SWE skill");
        assert_eq!(charter["phases"].as_array().unwrap().len(), 3);
        assert_eq!(charter["checklist"].as_array().unwrap().len(), 2);
        assert_eq!(charter["time_budget_min"], 45);
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
        let (charter, seed) = freeze(&scenario, None, "Freighter");
        assert_eq!(charter["goal"], "A tense negotiation aboard a derelict freighter");
        assert_eq!(charter["checklist"].as_array().unwrap().len(), 2);
        // No phases supplied → default single phase (chat charter needs ≥1).
        assert_eq!(charter["phases"], json!(["roleplay"]));
        assert_eq!(charter["language"], "en");
        assert_eq!(charter["time_budget_min"], Value::Null);
        assert!(seed.get("rubric").is_none());
    }

    #[test]
    fn empty_scenario_uses_fallback_goal() {
        let (charter, _) = freeze(&json!({}), None, "My Script");
        assert_eq!(charter["goal"], "My Script");
        assert_eq!(charter["phases"], json!(["roleplay"]));
        assert_eq!(charter["checklist"], json!([]));
    }
}
