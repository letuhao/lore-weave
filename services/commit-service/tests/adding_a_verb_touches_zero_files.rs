//! **The acceptance test** — command-hub §6, the actor hub's one level up.
//!
//! > **Adding a verb must touch ZERO files in command core.**
//! >
//! > The same test the actor hub takes, and checkable for the same reason: a
//! > feature that cannot add a field has nothing to touch.
//!
//! ## What "command core" means here, stated so the claim can be checked
//!
//! The files that RESOLVE a verb: `domain/law.rs`'s single `Declared` arm,
//! `domain/binding.rs`, `domain/payload.rs`, and `ruleset-core`'s
//! `verb/{mod,table}.rs`. Every verb in existence goes through the same arm; the
//! table it indexes is the reality's.
//!
//! **The claim is a claim about a DIFF.** Below, a verb the engine has never
//! heard of is declared entirely in test code, submitted, resolved and refused —
//! with no edit to any of those files. If a future change makes a verb need one,
//! this file stops compiling or stops passing, which is the failure being
//! visible rather than a design being quietly abandoned.
//!
//! ## And the honest bound, asserted rather than claimed
//!
//! > **It holds UP TO THE DECLARED WIDTHS.** The 17th verb touches command core
//! > — and that is a version bump, visible and costed, not a silent failure.
//!
//! The last test here is that bound.

mod hub_fixture;

use commit_service::combat::Side;
use commit_service::{
    Actor, CombatDomain, CombatEvent, CombatPayload, CombatState, RealityRules, RefusalReason,
    Vocabulary, COMBAT_V1_JSON,
};
use ruleset_loader::{parse_layer, resolve, Layer, PROVING_GROUND_TOML};
use sim_core::{
    Admitted, Class, EntityId, Fallback, Gen, InputId, Island, IslandId, Lane, Producer,
    QueuedInput, RulesetEpoch, SeenWindow, Seq, StepStatus,
};
use std::sync::Arc;

const A: EntityId = EntityId(1);

/// A verb invented entirely HERE, by an author the engine has never heard of.
///
/// `steady_breath` costs a point of focus and restores vitality. **No file in command
/// core names it**, contains its numbers, or has an arm for it — and the reality
/// it lands in is built through the real layer stack, not hand-assembled.
const AUTHORED_VERB: &str = r#"
[[verbs]]
name = "steady_breath"
cue = 7
target = "actor"
requires_quantity = "focus"
requires_at_least = 1
spend_quantity = "focus"
spend_amount = -1
effect_quantity = "vitality"
effect_amount = 4
"#;

fn reality_with(extra: &str) -> RealityRules {
    let rules = resolve(&[
        parse_layer(Layer::Preset, PROVING_GROUND_TOML).expect("the shipped preset parses"),
        parse_layer(Layer::Reality, extra).expect("the authored layer parses"),
    ])
    .expect("the stack resolves");
    RealityRules::resolve(rules).expect("every engine role stays bound")
}

fn island(rules: Arc<RealityRules>) -> Island<CombatDomain> {
    let mut state = CombatState { session_seed: 1, ..Default::default() };
    // Wounded on purpose. The verb below RESTORES vitality, and the pool's
    // ceiling is its declared one — so an actor at full health would clamp and
    // the test would measure the clamp instead of the verb. Starting below full
    // is also the only shape in which a heal means anything.
    let mut a = Actor::spawn(&rules, A, Side::A);
    a.set_vital(&rules, 50);
    state.actors.insert(A, a);
    let mut isle: Island<CombatDomain> =
        Island::new(IslandId(1), 3, RulesetEpoch(1), rules, SeenWindow::Unbounded, state);
    isle.spawn_entity(A);
    isle
}

fn submit(isle: &mut Island<CombatDomain>, id: u128, payload: CombatPayload) -> Vec<CombatEvent> {
    let before = isle.outcomes().len();
    isle.submit(
        Lane::Live,
        Admitted::unchecked(QueuedInput {
            seq: Seq(u64::MAX),
            input_id: InputId(id),
            class: Class::B,
            source: Producer::ScriptDecision,
            payload,
            preconditions: vec![],
            on_invalid: Fallback::Drop,
            admitted_gen: Gen(0),
            deadline: None,
        }),
    );
    while !matches!(isle.step(), StepStatus::Idle | StepStatus::Poisoned) {}
    isle.outcomes()[before..]
        .iter()
        .filter_map(|(_, o)| match o {
            sim_core::Outcome::Applied { events, .. } => Some(events.clone()),
            _ => None,
        })
        .flatten()
        .collect()
}

/// **The test.** A verb nobody in the engine has heard of, declared in a TOML
/// string, resolved end to end.
#[test]
fn a_verb_declared_only_in_content_resolves_end_to_end() {
    let rules = Arc::new(reality_with(AUTHORED_VERB));
    let ordinal = rules
        .rules()
        .verbs
        .ordinal_of("steady_breath")
        .expect("the authored verb took an ordinal");

    let mut isle = island(Arc::clone(&rules));
    let opening = isle.state().actors[&A].vital(isle.rules());

    let events = submit(&mut isle, 1, CombatPayload::Declared { verb: ordinal, actor: A });

    let acted = events
        .iter()
        .find_map(|e| match e {
            CombatEvent::Acted { verb, cue, delta, left, .. } => Some((*verb, *cue, *delta, *left)),
            _ => None,
        })
        .expect("a declared verb commits an Acted fact");

    println!(
        "A1.5  verb ordinal = {}  cue = {}  delta = {}  vital {} -> {}",
        acted.0, acted.1, acted.2, opening, acted.3
    );
    assert_eq!(acted.0, ordinal);
    // `CMD-4` — the CUE travels with the fact, and it is the author's number.
    assert_eq!(acted.1, 7, "the declared cue ordinal reached the committed fact");
    assert_eq!(acted.2, 4);
    assert_eq!(acted.3, opening + 4);

    // The SPEND was taken — the engine's conservation rule, on the author's
    // amount. Zero remaining is what the second submission below runs into.
    assert_eq!(isle.state().actors[&A].action_budget(isle.rules()), 0);
}

/// **`CMD-5`, the other half.** A substrate that only proves its happy path has
/// proved half of it: the refusal is a committed FACT with a reason ordinal.
#[test]
fn a_verb_whose_requirement_fails_commits_a_refusal_with_its_reason() {
    let rules = Arc::new(reality_with(AUTHORED_VERB));
    let ordinal = rules.rules().verbs.ordinal_of("steady_breath").unwrap();
    let mut isle = island(Arc::clone(&rules));

    // Spend the declared `focus` pool down to zero. One action per turn is the
    // ENGINE's budget (IAS-D6) and is separate from the verb's own cost, so the
    // turn boundary goes between — which is also why a verb may not spend the
    // action budget itself (`BindingError::VerbSpendsEngineBudget`).
    let opening_focus =
        rules.rules().resources.by_role(ruleset_core::EngineRole::None).unwrap().base;
    for turn in 0..opening_focus {
        submit(&mut isle, turn as u128, CombatPayload::Declared { verb: ordinal, actor: A });
        submit(&mut isle, 1000 + turn as u128, CombatPayload::EndTurn);
    }
    let vital_before_refusal = isle.state().actors[&A].vital(isle.rules());

    // Now the declared threshold no longer holds.
    let events = submit(&mut isle, 99, CombatPayload::Declared { verb: ordinal, actor: A });
    let refusal = events
        .iter()
        .find_map(|e| match e {
            CombatEvent::Refused { verb, reason, .. } => Some((*verb, *reason)),
            _ => None,
        })
        .expect("a refused verb commits a Refused fact -- silence is not an outcome");

    println!(
        "CMD-5  after {opening_focus} uses: refusal verb = {}  reason = {:?}",
        refusal.0, refusal.1
    );
    assert_eq!(refusal.0, ordinal);
    assert_eq!(refusal.1, RefusalReason::RequirementUnmet);
    assert_eq!(
        isle.state().actors[&A].vital(isle.rules()),
        vital_before_refusal,
        "a refused verb applied nothing"
    );
}

/// An ordinal naming no verb is refused, not ignored. Reachable across an epoch
/// switch: a submission stamped under old rules can pop under new ones.
#[test]
fn an_ordinal_that_names_no_verb_is_refused() {
    let rules = Arc::new(reality_with(AUTHORED_VERB));
    let mut isle = island(rules);
    let events = submit(&mut isle, 1, CombatPayload::Declared { verb: 999, actor: A });
    assert!(events
        .iter()
        .any(|e| matches!(e, CombatEvent::Refused { reason: RefusalReason::UnknownVerb, .. })));
}

/// **`CMD-6` — the name is resolved ONCE, on the submission path, and the engine
/// carries an ordinal.**
///
/// The tool vocabulary has four hardcoded arms and none of them is this verb.
/// It resolves anyway, because a declared name is looked up in the reality's
/// table before the manifest is consulted.
#[test]
fn the_submission_path_resolves_a_declared_name_with_no_arm() {
    let rules = reality_with(AUTHORED_VERB);
    let vocab = Vocabulary::from_json(COMBAT_V1_JSON).unwrap();
    assert!(
        !vocab.contains("steady_breath"),
        "the tool manifest must NOT know this verb, or the test proves nothing"
    );

    let payload = vocab
        .validate(A, "steady_breath", "{}", &[], &rules.rules().verbs)
        .expect("a declared verb resolves without a manifest entry");
    let expected = rules.rules().verbs.ordinal_of("steady_breath").unwrap();
    assert_eq!(payload, CombatPayload::Declared { verb: expected, actor: A });
}

/// **`CMD-10`'s owed bite, discharged.**
///
/// §9.4: *"for a concern classified vocabulary, author a member that sets an
/// authority-bearing field and assert the build or the engine REFUSES it. If no
/// such member can be constructed, V4 was not applied — it was asserted."*
///
/// Here is the member. Three of them, one per forbidden key, and each refusal
/// names the verb, the key and the reason — not *"unknown field"*, which is true
/// and no help, because the field is not unknown.
#[test]
fn a_verb_that_writes_an_authority_field_is_refused_by_name() {
    for (key, value) in [
        ("submitter_class", "\"host\""),
        ("may_submit_engine_verbs", "true"),
        ("pays_spend", "true"),
    ] {
        let src = format!(
            "[[verbs]]\nname = \"usurp\"\n{key} = {value}\n\
             effect_quantity = \"vitality\"\neffect_amount = 1\n"
        );
        let err = parse_layer(Layer::Reality, &src)
            .expect_err("an authority-bearing field must be REFUSED at the door");
        let msg = err.to_string();
        println!("CMD-10 V4  {key} -> {msg}");
        assert!(msg.contains(key), "the refusal must name the key: {msg}");
        assert!(msg.contains("usurp"), "the refusal must name the verb: {msg}");
        assert!(
            msg.len() > 120,
            "the refusal must carry the REASON, not just the name: {msg}"
        );
    }
}

/// A verb targeting another actor is refused while the offer registry is
/// unbuilt. Accepting it would ship a verb that works and is unauthorised.
#[test]
fn a_verb_targeting_another_actor_is_refused_until_the_offer_registry_exists() {
    let src = "[[verbs]]\nname = \"smite\"\ntarget = \"other\"\n\
               effect_quantity = \"vitality\"\neffect_amount = -5\n";
    let err = resolve(&[
        parse_layer(Layer::Preset, PROVING_GROUND_TOML).unwrap(),
        parse_layer(Layer::Reality, src).unwrap(),
    ])
    .expect_err("CMD-11/CMD-12 are parked, so `other` has no authorised path");
    let msg = err.to_string();
    println!("offer registry  -> {msg}");
    assert!(msg.contains("smite") && msg.contains("offer registry"), "{msg}");
}

/// **The honest bound.** Sixteen verbs fit; the seventeenth is a version bump,
/// visible and costed, not a silent failure.
#[test]
fn the_seventeenth_verb_is_refused_rather_than_dropped() {
    let mut src = String::new();
    for i in 0..=ruleset_core::MAX_DECLARED_VERBS {
        src.push_str(&format!(
            "[[verbs]]\nname = \"v{i}\"\neffect_quantity = \"vitality\"\neffect_amount = 1\n\n"
        ));
    }
    let err = resolve(&[
        parse_layer(Layer::Preset, PROVING_GROUND_TOML).unwrap(),
        parse_layer(Layer::Reality, &src).unwrap(),
    ])
    .expect_err("past the declared width is a REFUSAL, never a silent truncation");
    println!("width bound  -> {err}");
    assert!(err.to_string().contains("capacity"));
}

// ── the claim itself, mechanised ────────────────────────────────────────────

/// **`CMD-6`, as a CHECK rather than a comment.**
///
/// `substrate.rs`'s own header says *"If either appears, the acceptance test is
/// false and the substrate has become the thing it replaced."* **Nothing checked
/// it.** A cold-start reviewer's sharpest finding was that every test above
/// would stay green if someone added `match verb { 0 => …, _ => … }` tomorrow —
/// so the load-bearing claim of `M2` was prose sitting under a file named for
/// it.
///
/// This reads the source at RUNTIME, which is the same call
/// `TestOpenAPIRouteConformance` makes for the contract-first rule: a check that
/// is compiled in cannot see the file it is about.
///
/// It is narrow on purpose. It does not try to understand Rust; it looks for the
/// two shapes a per-verb branch can take — a `match` whose scrutinee is the verb
/// ordinal, and a comparison of it against a literal — which is exactly the
/// discriminator `hub-vocabulary-gate` settled on one contract down, for the
/// same reason: *an ordinal is an ADDRESS; comparing one against a LITERAL asks
/// "is this the address I mean", which is a name.*
#[test]
fn the_substrate_never_branches_on_a_verb() {
    const CORE: &[&str] = &[
        "src/domain/substrate.rs",
        "src/domain/binding.rs",
        "src/domain/law.rs",
    ];
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"));
    let mut findings = Vec::new();

    for rel in CORE {
        let src = std::fs::read_to_string(root.join(rel))
            .unwrap_or_else(|e| panic!("command core file {rel} is unreadable: {e}"));
        for (i, line) in src.lines().enumerate() {
            let code = line.split("//").next().unwrap_or("").trim();
            if code.is_empty() {
                continue;
            }
            let branches_on_verb = code.starts_with("match verb")
                || code.contains("match verb {")
                || code.contains("matches!(verb")
                || (code.contains("verb ==") && code.split("verb ==").nth(1)
                    .is_some_and(|r| r.trim_start().starts_with(|c: char| c.is_ascii_digit())))
                || (code.contains("verb !=") && code.split("verb !=").nth(1)
                    .is_some_and(|r| r.trim_start().starts_with(|c: char| c.is_ascii_digit())));
            if branches_on_verb {
                findings.push(format!("{rel}:{}: {code}", i + 1));
            }
        }
    }

    assert!(
        findings.is_empty(),
        "command core branches on a verb ordinal, so `adding a verb touches zero files` is \
         FALSE — the substrate has become the `match` it replaced (CMD-6):\n  {}",
        findings.join("\n  ")
    );
    println!("CMD-6  {} command-core file(s) scanned; none branches on a verb", CORE.len());
}
