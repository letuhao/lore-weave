//! The encounter the S3a spine demonstrates: one NPC against two.
//!
//! # Why this is a module and not twenty lines in the binary
//!
//! `bin/spine.rs` sits on its `IMP-D3` ceiling, and the cap's own comment gives
//! the rule: *"a cap left at its old value after a split is a silent licence to
//! regrow into it."* Its history is three extractions on exactly this trigger —
//! `ruleset_boot` when `Q1 B2b` gave the binary a startup responsibility,
//! `spine_args` and `reality_bind` when `3E` gave it another. `SEALED-SUBJECT`
//! gives it a fourth (`crate::subject::SubjectSource`), and this block is what
//! moved to pay for it.
//!
//! It is also the block that least belongs there. Everything else in that file
//! is WIRING — a bus, a lease, a writer, a loop. This is FIXTURE: three
//! hardcoded entities and a hardcoded vitality, chosen to make a demo turn
//! resolve. Its being in the binary is why `EntityId(1..3)` are the only actors
//! the running system has, which is the fact that stopped `P2` until the
//! registry existed.

use std::sync::Arc;

use sim_core::{EntityId, Island, IslandId, RulesetEpoch, SeenWindow};

use crate::combat::Side;
use crate::domain::RealityRules;
use crate::{Actor, CombatDomain, CombatState};

/// The NPC's island id. `1`, and the registry can now ADOPT it under a real
/// actor row — which is how a human comes to drive this demo at all.
pub const NPC: EntityId = EntityId(1);
/// The two it faces.
pub const FOES: [EntityId; 2] = [EntityId(2), EntityId(3)];
/// What each foe starts with. A fixture number, named rather than inline so it
/// is obvious this is a demo constant and not a rule.
const FOE_VITAL: i64 = 40;

/// Build the demo island for `channel`, pinned to `epoch`.
///
/// `epoch` COMES FROM THE BINDING, never a default. An island that started at 1
/// for a reality bound at 5 would compute `RLS-I1` monotonicity against the
/// wrong number, and a redelivered switch to an epoch between them would be
/// accepted.
///
/// The island derives its digest pin from `rules` via `Domain::rules_digest`,
/// so it cannot report a digest for rules it is not running.
pub fn island(
    rules: Arc<RealityRules>,
    epoch: RulesetEpoch,
    channel: i64,
) -> Island<CombatDomain> {
    let mut state = CombatState::default();
    state.actors.insert(NPC, Actor::spawn(&rules, NPC, Side::A));
    for h in FOES {
        let mut a = Actor::spawn(&rules, h, Side::B);
        a.set_vital(&rules, FOE_VITAL);
        state.actors.insert(h, a);
    }
    let mut isle: Island<CombatDomain> = Island::new(
        IslandId(channel as u64),
        0x53A5_71DE,
        epoch,
        rules,
        SeenWindow::TtlTicks(300),
        state,
    );
    isle.spawn_entity(NPC);
    for h in FOES {
        isle.spawn_entity(h);
    }
    isle
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The three entities the registry has to be able to adopt.
    ///
    /// Not decoration: `P2` stopped because the only actors in the running
    /// system were these, hardcoded, with no durable identity. If this set ever
    /// changes, whatever adopts them into `actors` has to change with it, and
    /// the constant is now the one place to look.
    #[test]
    fn the_demo_has_exactly_three_entities_and_they_are_1_2_3() {
        let mut ids: Vec<u64> = std::iter::once(NPC).chain(FOES).map(|e| e.0).collect();
        ids.sort_unstable();
        assert_eq!(ids, vec![1, 2, 3]);
    }
}
