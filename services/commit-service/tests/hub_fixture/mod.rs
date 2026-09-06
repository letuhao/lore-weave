//! The one place a test builds a reality and an actor.
//!
//! **`M1`.** Six integration tests each constructed `Ruleset::engine_default()`
//! and `Actor::new(&rules, 100)`. Both are gone: the engine default declares no
//! pools, so it binds no engine role and no law can run on it, and an actor's
//! opening vital is content rather than a constructor argument.
//!
//! Shared rather than copied six times so a test cannot drift onto a reality
//! the binary does not run. It goes through the real layer stack, which is the
//! difference between exercising the authoring path and asserting against a
//! fixture that bypasses it.
#![allow(dead_code)]

use commit_service::combat::Side;
use commit_service::{Actor, RealityRules};
use sim_core::EntityId;

/// The shipped preset, resolved through the real loader.
pub fn rules() -> RealityRules {
    RealityRules::proving_ground()
}

/// A combatant whose opening vital the FEATURE sets, rather than the reality's
/// declared `base`.
///
/// Two steps on purpose, and they are the division of labour `M1` establishes:
/// [`Actor::spawn`] takes every opening value from content, and the write that
/// follows is the feature deciding a number — through the hub's guarded verb,
/// which refuses a plugin that does not own the quantity.
pub fn actor(rules: &RealityRules, id: EntityId, side: Side, vital: i64) -> Actor {
    let mut a = Actor::spawn(rules, id, side);
    a.set_vital(rules, vital);
    a
}
