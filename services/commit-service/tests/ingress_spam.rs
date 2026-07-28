//! IAS-Q1 — the spam bite-test: does *"a player sends 100 attack requests"*
//! actually resolve 100 attacks?
//!
//! Doc 22 §5 asserted this from code reading. Per the repo's bite discipline
//! a read-from-code claim is a HYPOTHESIS until something executes it — and
//! patching before proving would make the patch unfalsifiable, because a
//! green test after the fix proves nothing if it was never red before.
//!
//! So this file exists to go RED first. It pins the exploit precisely:
//!
//!   * `client_request_id` (→ `proposal_id`) is **client-minted** by design —
//!     it is what makes a retry idempotent (EVT-L3). 100 requests with 100
//!     distinct ids are therefore 100 distinct INTENTS, and admission is
//!     *correct* to let all 100 through. Idempotency is not, and was never,
//!     a spam defence.
//!   * The island's I2 dedup keys on `input_id`, derived from that same
//!     triple — so it cannot collapse them either.
//!   * With `preconditions: vec![]` (admission.rs) there is no obligation for
//!     the loop to re-check, so nothing downstream gates the actor either.
//!
//! Net: 100 requests → 100 admits → 100 applied strikes.
//!
//! After IAS-D2/D6 land, `spam_is_gated_by_the_turn_economy` is the test that
//! must flip; the two above it document WHY the obvious defences don't fire
//! and must keep passing (they are statements about correct behaviour, not
//! about the bug).

use std::sync::Arc;
use std::time::Duration;

use commit_service::admission::{admit_engine_turn_end as engine_end_turn, admit_t6, AdmissionOutcome, DedupCache};
use commit_service::{
    Actor, CombatDomain, CombatEvent, Ruleset, CombatState, Vocabulary, COMBAT_V1_JSON,
};
use sim_core::{
    DiscardReason, EntityId, Island, IslandId, Lane, Outcome, PreconditionKind,
    SeenWindow, StepStatus,
};

const SPAM: usize = 100;
/// Fixed seed — replay-exact, no ambient randomness (SC-A1).
const SEED: u64 = 0x1A5_0001;

fn vocab() -> Vocabulary {
    Vocabulary::from_json(COMBAT_V1_JSON).unwrap()
}

/// One strike proposal from actor 1 at hostile 2, with a caller-chosen
/// request id — the client mints this, which is the whole point.
fn strike(client_request_id: &str) -> String {
    serde_json::json!({
        "producer_service": "game-server",
        "proposal_id": client_request_id,
        "target_channel": 1,
        "actor": 1,
        "candidates": [[2, "hostile-2"]],
        "event_category": "T1",
        "decision": {
            "vocabulary": "combat_v1",
            "tool": "strike",
            "params": {"target": "hostile-2"}
        },
    })
    .to_string()
}

/// A fresh encounter: actor 1 (the spammer) vs hostile 2 with a lot of HP,
/// so the exploit is measured in landed strikes rather than cut short by the
/// target dying.
fn island() -> Island<CombatDomain> {
    // F1 — the island runs the reality's RESOLVED ruleset, pinned by a real
    // content digest. Was `RulesetDigest([0u8; 32])`, which pinned nothing.
    let rules = Arc::new(Ruleset::engine_default());
    let mut state = CombatState::default();
    state.actors.insert(EntityId(1), Actor::new(&rules, 100));
    state.actors.insert(EntityId(2), Actor::new(&rules, 100_000));

    let mut isle: Island<CombatDomain> = Island::new(
        IslandId(1),
        SEED,
        Arc::clone(&rules),
        SeenWindow::Unbounded,
        state,
    );
    isle.spawn_entity(EntityId(1));
    isle.spawn_entity(EntityId(2));
    isle
}

/// **The defence that people ASSUME stops this — and correctly does not.**
/// EVT-L3 dedup fires only on a REPEATED triple. Distinct client-minted ids
/// are distinct intents. Kill-mutation: keying dedup on (actor, tool) instead
/// of the triple would break legitimate repeat actions across turns.
#[test]
fn distinct_client_request_ids_all_pass_idempotency() {
    let v = vocab();
    let mut dedup = DedupCache::new(Duration::from_secs(60));

    let admitted = (0..SPAM)
        .filter(|i| {
            matches!(
                admit_t6(&strike(&format!("req-{i}")), &v, &mut dedup).outcome,
                AdmissionOutcome::Admitted(_)
            )
        })
        .count();

    assert_eq!(
        admitted, SPAM,
        "idempotency is not a spam defence — and must not be mistaken for one"
    );
}

/// The same 100 requests, driven all the way through the island. This is the
/// exploit itself: 100 resolved strikes from one actor with no turn taken in
/// between.
///
/// **This test is the IAS-Q1 verdict.** It asserts the CURRENT (broken)
/// behaviour so the fix has something to flip.
#[test]
fn spam_is_gated_by_the_turn_economy() {
    let v = vocab();
    let mut dedup = DedupCache::new(Duration::from_secs(60));
    let mut isle = island();

    for i in 0..SPAM {
        let rec = admit_t6(&strike(&format!("req-{i}")), &v, &mut dedup);
        let AdmissionOutcome::Admitted(input) = rec.outcome else {
            continue;
        };
        isle.submit(Lane::Live, *input);
    }
    while matches!(isle.step(), StepStatus::Processed(_)) {}

    let landed = isle
        .outcomes()
        .iter()
        .filter(|(_, o)| match o {
            Outcome::Applied { events } => {
                events.iter().any(|e| matches!(e, CombatEvent::Struck { .. }))
            }
            _ => false,
        })
        .count();

    // ONE actor, ONE turn's worth of legitimate action. Anything above 1 is
    // the spam landing.
    assert_eq!(
        landed, 1,
        "IAS-D6: the turn economy must admit ONE action per actor per turn — \
         {landed} of {SPAM} spam strikes resolved"
    );
}

/// The 99 refusals must be RECORDED, not silently dropped (CS-D5 / EVT-L5).
/// A gate that quietly discards is indistinguishable from a gate that is
/// broken — and from the player's side, from an action that never arrived.
#[test]
fn refused_spam_is_recorded_as_a_precondition_failure() {
    let v = vocab();
    let mut dedup = DedupCache::new(Duration::from_secs(60));
    let mut isle = island();

    for i in 0..SPAM {
        if let AdmissionOutcome::Admitted(a) =
            admit_t6(&strike(&format!("req-{i}")), &v, &mut dedup).outcome
        {
            isle.submit(Lane::Live, *a);
        }
    }
    while matches!(isle.step(), StepStatus::Processed(_)) {}

    let refused = isle
        .outcomes()
        .iter()
        .filter(|(_, o)| {
            matches!(
                o,
                Outcome::Discarded { reason: DiscardReason::PreconditionFailed(v) }
                    if v.kind == PreconditionKind::ResourceAtLeast
            )
        })
        .count();
    assert_eq!(refused, SPAM - 1, "every refusal is accounted for, none silent");
}

/// **The test that stops the "fix" from being a bug.** Blocking 99 of 100 is
/// only correct if the 1 legitimate action per turn still lands — a gate that
/// refused everything would satisfy the spam test above while making the game
/// unplayable. `EndTurn` refills the slot; the next turn's action resolves.
#[test]
fn end_turn_refills_the_slot_so_legitimate_play_continues() {
    let v = vocab();
    let mut dedup = DedupCache::new(Duration::from_secs(60));
    let mut isle = island();

    let mut landed = 0usize;
    for turn in 0..5 {
        // One legitimate action for this turn.
        if let AdmissionOutcome::Admitted(a) =
            admit_t6(&strike(&format!("turn-{turn}")), &v, &mut dedup).outcome
        {
            isle.submit(Lane::Live, *a);
        }
        // …plus a spam attempt in the SAME turn, which must not land.
        if let AdmissionOutcome::Admitted(a) =
            admit_t6(&strike(&format!("turn-{turn}-spam")), &v, &mut dedup).outcome
        {
            isle.submit(Lane::Live, *a);
        }
        while matches!(isle.step(), StepStatus::Processed(_)) {}

        // Host-issued turn boundary (engine-only; no driver can ask for it).
        isle.submit(Lane::Live, engine_end_turn(turn as u64));
        while matches!(isle.step(), StepStatus::Processed(_)) {}

        landed = isle
            .outcomes()
            .iter()
            .filter(|(_, o)| match o {
                Outcome::Applied { events } => {
                    events.iter().any(|e| matches!(e, CombatEvent::Struck { .. }))
                }
                _ => false,
            })
            .count();
        assert_eq!(landed, turn + 1, "exactly one strike per turn, turn {turn}");
    }
    assert_eq!(landed, 5, "five turns, five strikes — play is not blocked");
}
