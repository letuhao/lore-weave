//! **Axis 3 — numbers off a real run, not off the design.**
//!
//! Every test here PRINTS what it measured as well as asserting it. The point
//! of a measurement is that a reader can see the number: an assertion alone
//! cannot distinguish *"the digests matched"* from *"both were empty"*, and this
//! repository has a recorded history of exactly that — a `RulesetDigest([0u8;
//! 32])` that shipped in fifteen places and *"looks like a value"*.

mod hub_fixture;

use std::sync::Arc;

use commit_service::combat::Side;
use commit_service::{
    Actor, CombatDomain, CombatEvent, CombatPayload, CombatState, RealityRules,
};
use ruleset_core::{Provenance, ResolvedRuleset};
use sim_core::{
    Admitted, Class, EntityId, Fallback, Gen, InputId, Island, IslandId, Lane, Producer,
    QueuedInput, RulesetEpoch, SeenWindow, Seq, StepStatus,
};

const HERO: EntityId = EntityId(1);
const FOE: EntityId = EntityId(2);

fn hex(b: &[u8]) -> String {
    b.iter().map(|x| format!("{x:02x}")).collect()
}

/// One deterministic encounter, returning the committed events.
///
/// The seed is fixed and the inputs are fixed, so the ONLY way two runs can
/// differ is a real non-determinism — an iteration order, a clock, a hash seed.
fn run_encounter() -> Vec<CombatEvent> {
    let rules = Arc::new(RealityRules::proving_ground());
    let mut state = CombatState { session_seed: 0xBEEF_5EED, ..Default::default() };
    state.actors.insert(HERO, hub_fixture::actor(&rules, HERO, Side::A, 100));
    state.actors.insert(FOE, hub_fixture::actor(&rules, FOE, Side::B, 100));

    let mut isle: Island<CombatDomain> =
        Island::new(IslandId(1), 0xE1CE, RulesetEpoch(1), rules, SeenWindow::Unbounded, state);
    isle.spawn_entity(HERO);
    isle.spawn_entity(FOE);

    let mut events = Vec::new();
    let script = [
        CombatPayload::Strike { attacker: HERO, target: FOE },
        CombatPayload::EndTurn,
        CombatPayload::Strike { attacker: FOE, target: HERO },
        CombatPayload::EndTurn,
        CombatPayload::Defend { actor: HERO },
        CombatPayload::EndTurn,
        CombatPayload::Strike { attacker: FOE, target: HERO },
    ];
    for (i, payload) in script.into_iter().enumerate() {
        isle.submit(
            Lane::Live,
            Admitted::unchecked(QueuedInput {
                seq: Seq(u64::MAX),
                input_id: InputId(i as u128),
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
    }
    for (_, outcome) in isle.outcomes() {
        if let sim_core::Outcome::Applied { events: evs, .. } = outcome {
            events.extend(evs.iter().cloned());
        }
    }
    events
}

/// **`A3.1` — determinism.** The same input replayed twice produces
/// byte-identical output.
///
/// The digest is over the SERIALIZED events, not over a `Debug` rendering: a
/// `Debug` string is not a contract and would make this test pass on a shape
/// no consumer reads. `CombatEvent`'s own doc makes the same call for the wire.
#[test]
fn the_same_input_replayed_twice_is_byte_identical() {
    let a = run_encounter();
    let b = run_encounter();

    let da = blake3::hash(serde_json::to_vec(&a).unwrap().as_slice());
    let db = blake3::hash(serde_json::to_vec(&b).unwrap().as_slice());

    println!("A3.1  run 1 = {}  ({} events)", hex(da.as_bytes()), a.len());
    println!("A3.1  run 2 = {}  ({} events)", hex(db.as_bytes()), b.len());
    assert!(!a.is_empty(), "an empty event stream would make any two runs agree");
    assert_eq!(da, db, "two runs of one script diverged — replay is not deterministic");
}

/// **`A3.2`, first half — the digest MOVES when the rules move.**
///
/// One balance number, which is the smallest real rules change there is.
#[test]
fn the_digest_moves_when_the_ruleset_changes() {
    let base = RealityRules::proving_ground();
    let mut edited = base.rules().clone();
    edited.combat.max_hit -= 1;
    let edited = RealityRules::resolve(edited).expect("still binds every role");

    println!("A3.2a base   = {}", hex(&base.digest().0));
    println!("A3.2a edited = {}   (max_hit - 1)", hex(&edited.digest().0));
    assert_ne!(
        base.digest(),
        edited.digest(),
        "a rules change that moves no digest is a behavioural change no boundary can see"
    );
}

/// **`A3.2`, second half — and it does NOT move when only provenance changes.**
///
/// **One half without the other proves nothing.** A digest that always moves is
/// satisfied by hashing a clock; a digest that never moves is satisfied by a
/// constant. `RLS-A15` is the pair, and it is testable precisely because
/// `Provenance` sits inside [`ResolvedRuleset`] rather than somewhere else — as
/// that struct's own doc says, with `Provenance` elsewhere this test would be
/// vacuously true.
#[test]
fn the_digest_does_not_move_when_only_provenance_changes() {
    let rules = RealityRules::proving_ground();

    let plain = ResolvedRuleset {
        ruleset: rules.rules().clone(),
        provenance: Provenance::default(),
        epoch: ruleset_core::RulesetEpoch(1),
    };
    let embellished = ResolvedRuleset {
        ruleset: rules.rules().clone(),
        provenance: Provenance {
            author_user_id: "a-different-author".into(),
            preset_ref: "some/other/preset".into(),
            preset_version: 99,
            created_at_ms: 1_754_000_000_000,
            total_llm_cost_usd_milli: 12_345,
        },
        // Ordering, not identity: the same rules at two epochs are the same
        // rules, and interning them under one digest is the point.
        epoch: ruleset_core::RulesetEpoch(7),
    };

    println!("A3.2b default provenance = {}", hex(&plain.digest().0));
    println!("A3.2b changed provenance = {}   (author, preset, clock, cost, epoch)",
        hex(&embellished.digest().0));
    assert_eq!(
        plain.digest(),
        embellished.digest(),
        "lineage entered the identity — two records of one ruleset would stop interning, \
         and a wall-clock field would make the digest non-reproducible (RLS-D13)"
    );
}

/// **`A3.4` — the counts, off the shipped reality.**
#[test]
fn the_counts_are_what_the_reality_declares() {
    let rules = RealityRules::proving_ground();
    let quantities = rules.rules().quantities.len();
    let pools = rules.rules().resources.len();
    let roles = rules
        .rules()
        .resources
        .rows()
        .iter()
        .filter(|r| r.role != ruleset_core::EngineRole::None)
        .count();

    println!(
        "A3.4  quantities declared = {quantities}  |  pools = {pools}  |  \
         engine roles bound = {roles}  |  effect doors used = 1 (Delta)"
    );
    assert_eq!(quantities, 3);
    assert_eq!(pools, 3);
    assert_eq!(roles, 3, "vital, initiative and action_budget — every law has its number");
}
