//! AGT-A2 closed-vocabulary bite-tests — each names its kill-mutation.

use commit_service::{CombatPayload, Stance, Vocabulary, COMBAT_V1_JSON};
use sim_core::EntityId;

fn vocab() -> Vocabulary {
    Vocabulary::from_json(COMBAT_V1_JSON).expect("contract file parses")
}

fn candidates() -> Vec<(EntityId, String)> {
    vec![
        (EntityId(2), "hostile-2 (healthy)".into()),
        (EntityId(3), "hostile-3 (critical)".into()),
    ]
}

/// Contract self-check: combat_v1 declares its fallback inside its own set.
/// Kill-mutation: constructor skipping the membership check.
#[test]
fn fallback_tool_is_in_the_closed_set() {
    let v = vocab();
    assert_eq!(v.fallback_tool, "defend");
    assert!(v.contains(&v.fallback_tool));
    assert!(Vocabulary::from_json(
        &COMBAT_V1_JSON.replace("\"fallback_tool\": \"defend\"", "\"fallback_tool\": \"pray\"")
    )
    .is_err(), "an out-of-set fallback must not load");
}

/// The chaos limiter: an off-vocabulary tool REJECTS (→ fallback), never
/// passes through. Kill-mutation: validate() skipping the membership gate.
#[test]
fn unknown_tool_rejects() {
    let err = vocab()
        .validate(EntityId(1), "cast_meteor", "{}", &candidates())
        .unwrap_err();
    assert!(err.to_string().contains("cast_meteor"));
}

/// THR-A4: strike may only name an OFFERED candidate — a hallucinated target
/// (even a real entity id not offered this turn) rejects. Kill-mutation:
/// matching target against all entities instead of the offered list.
#[test]
fn strike_target_must_be_offered() {
    let v = vocab();
    let ok = v.validate(
        EntityId(1),
        "strike",
        r#"{"target":"hostile-2 (healthy)"}"#,
        &candidates(),
    );
    assert_eq!(ok.unwrap(), CombatPayload::Strike { attacker: EntityId(1), target: EntityId(2) });

    let err = v.validate(
        EntityId(1),
        "strike",
        r#"{"target":"the-king"}"#,
        &candidates(),
    );
    assert!(err.is_err(), "unoffered target must reject");
}

/// Closed-set arg discipline: stance outside the TG-A4 enum rejects.
/// Kill-mutation: accepting any string as a stance.
#[test]
fn move_stance_enum_is_closed() {
    let v = vocab();
    assert_eq!(
        v.validate(EntityId(1), "move", r#"{"stance":"kite"}"#, &candidates()).unwrap(),
        CombatPayload::Move { actor: EntityId(1), stance: Stance::Kite }
    );
    assert!(v.validate(EntityId(1), "move", r#"{"stance":"teleport"}"#, &candidates()).is_err());
}

/// Zero-arg tools accept an EMPTY arguments string (providers often stream
/// nothing for {}). Kill-mutation: parsing "" as JSON unconditionally.
#[test]
fn zero_arg_tools_accept_empty_arguments() {
    let v = vocab();
    assert_eq!(
        v.validate(EntityId(1), "defend", "", &candidates()).unwrap(),
        CombatPayload::Defend { actor: EntityId(1) }
    );
    assert_eq!(
        v.validate(EntityId(1), "flee", "", &candidates()).unwrap(),
        CombatPayload::Flee { actor: EntityId(1) }
    );
}

/// Malformed argument JSON is a REJECT (→ fallback), not a crash.
#[test]
fn malformed_arguments_reject() {
    assert!(vocab()
        .validate(EntityId(1), "strike", r#"{"target": "#, &candidates())
        .is_err());
}

/// The OpenAI tool projection carries all four tools with their schemas —
/// the model sees exactly the contract file. Kill-mutation: projecting a
/// hardcoded subset.
#[test]
fn openai_tools_mirror_the_contract() {
    let tools = vocab().openai_tools();
    assert_eq!(tools.len(), 4);
    let names: Vec<&str> = tools
        .iter()
        .map(|t| t["function"]["name"].as_str().unwrap())
        .collect();
    assert_eq!(names, ["strike", "defend", "move", "flee"]);
    assert_eq!(
        tools[2]["function"]["parameters"]["properties"]["stance"]["enum"],
        serde_json::json!(["kite", "flank", "cover", "hold"]),
        "the enum reaches the model verbatim"
    );
}
