//! contracts-agent-control — the typed Rust mirror of the Agent Control Plane contracts
//! (`contracts/agent-control/*.schema.json`). ACP A3.
//!
//! The working-memory / charter block a Rust agent-runtime PRODUCES (roleplay-service freezes
//! it; a future world-model would too) and any consumer reads. Typed here so a producer builds
//! it via serde structs instead of hand-rolled `serde_json::json!` — the drift the charter.rs
//! comment warned about ("MUST be byte-compatible with chat-service's WorkingMemory"). The
//! shapes mirror the shared JSON Schema exactly; `working_memory_schema_conformance` proves it.
//!
//! Deferred (D-ACP-RUST-CLIENT): the reqwest executive/probe HTTP client — no Rust runtime calls
//! the executive today (roleplay is a producer; game-server is TypeScript). Added when a Rust
//! consumer needs it.

use serde::{Deserialize, Serialize};
use serde_json::Value;

/// The committed goal — written ONLY by the goal authority; frozen for interview. The executive
/// can never write this. Mirrors `working_memory.schema.json#/properties/charter`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Charter {
    pub goal: String,
    pub phases: Vec<String>,
    #[serde(default)]
    pub checklist: Vec<String>,
    /// Present-but-null when the scenario declares no budget (the schema is `["integer","null"]`).
    pub time_budget_min: Option<i64>,
    pub language: String,
    /// ACP A4 (RV-M4) — the fixed question count an interview drives before wrapping. OMITTED
    /// (skip) when absent so non-interview charters stay byte-identical; interview presets set it.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub question_target: Option<i64>,
}

/// The mutable progress estimate the executive rewrites (safe-when-wrong). `covered` is monotonic.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct State {
    pub phase: String,
    pub covered: Vec<String>,
    pub elapsed_min: Option<i64>,
    pub drift_note: Option<String>,
    pub redirect_hint: Option<String>,
}

impl Default for State {
    /// The seed's initial state: empty, nothing covered, nothing elapsed.
    fn default() -> Self {
        State {
            phase: String::new(),
            covered: Vec::new(),
            elapsed_min: None,
            drift_note: None,
            redirect_hint: None,
        }
    }
}

/// The pinned goal-state block sent as `working_memory_seed` + stored durably. Mirrors the
/// schema's top level: `{version, charter, state}` + an optional `rubric` sidecar (the debrief
/// rubric that rides the seed; `/evaluate` reads it — RW-8).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct WorkingMemory {
    pub version: u32,
    pub charter: Charter,
    pub state: State,
    /// Optional debrief rubric — ABSENT (not null) when the scenario has none.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub rubric: Option<Value>,
}

impl WorkingMemory {
    /// Build a seed from a frozen charter (+ optional rubric), with the initial empty state.
    /// This is the typed replacement for roleplay's hand-rolled seed JSON.
    pub fn seed(charter: Charter, rubric: Option<Value>) -> Self {
        WorkingMemory { version: 1, charter, state: State::default(), rubric }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    /// The typed structs serialize to instances that CONFORM to the shared JSON Schema — the
    /// same schema chat/knowledge validate against (ACP-6, both-sides). Reads the schema's
    /// required keys + declared properties FROM the file (no hand-mirrored rules).
    #[test]
    fn working_memory_schema_conformance() {
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../contracts/agent-control/working_memory.schema.json");
        let schema: Value =
            serde_json::from_str(&std::fs::read_to_string(&path).expect("read schema")).unwrap();

        let charter = Charter {
            goal: "Assess senior SWE skill".into(),
            phases: vec!["warmup".into(), "coding".into(), "wrap".into()],
            checklist: vec!["clarifies the problem".into()],
            time_budget_min: Some(45),
            language: "en".into(),
            question_target: Some(5),  // A4 — an interview charter carries it
        };
        let wm = WorkingMemory::seed(charter, Some(json!({"dimensions": ["clarity"]})));
        let inst = serde_json::to_value(&wm).unwrap();

        assert_level(&inst, &schema, "wm");
        assert_level(&inst["charter"], &schema["properties"]["charter"], "charter");
        assert_level(&inst["state"], &schema["properties"]["state"], "state");
        assert_eq!(inst["charter"]["question_target"], 5);  // A4 — carried through
        // the rubric sidecar is present + an object (schema models it as of A0.3)
        assert!(inst.get("rubric").map_or(false, Value::is_object));

        // a freeform seed (no rubric, no question_target) OMITS both keys and still conforms.
        let free = WorkingMemory::seed(
            Charter { goal: "x".into(), phases: vec!["a".into()], checklist: vec![],
                      time_budget_min: None, language: "en".into(), question_target: None },
            None,
        );
        let free_inst = serde_json::to_value(&free).unwrap();
        assert!(free_inst.get("rubric").is_none(), "no-rubric seed must omit the key");
        assert!(free_inst["charter"].get("question_target").is_none(), "no-target charter omits it");
        assert_level(&free_inst, &schema, "free");
    }

    /// A struct round-trips through JSON unchanged (serialize → parse → equal).
    #[test]
    fn round_trips_through_json() {
        let wm = WorkingMemory::seed(
            Charter { goal: "g".into(), phases: vec!["p".into()], checklist: vec!["c".into()],
                      time_budget_min: Some(30), language: "vi".into(), question_target: Some(5) },
            None,
        );
        let back: WorkingMemory = serde_json::from_str(&serde_json::to_string(&wm).unwrap()).unwrap();
        assert_eq!(wm, back);
    }

    fn assert_level(inst: &Value, node: &Value, path: &str) {
        let obj = inst.as_object().unwrap_or_else(|| panic!("{path}: not an object"));
        for req in node["required"].as_array().into_iter().flatten() {
            assert!(obj.contains_key(req.as_str().unwrap()), "{path}: missing {req}");
        }
        if node.get("additionalProperties").and_then(Value::as_bool) == Some(false) {
            let props = node["properties"].as_object().unwrap();
            for k in obj.keys() {
                assert!(props.contains_key(k), "{path}: undeclared key '{k}'");
            }
        }
    }
}
