//! COMB_001 L1 — the CombatEngine: deterministic, LLM-free combat law.
//!
//! Every rule here is quoted from `COMB_001_combat_foundation.md` §4, not
//! invented. That distinction matters: **COMB-A1 says the LLM never computes
//! combat math or space.** It selects an intent from a closed vocabulary and
//! the engine resolves everything, so each function below is a *law* with one
//! correct answer rather than a knob to tune.
//!
//! ## Why the RNG is derived per-roll instead of drawn from a stream
//!
//! `DetRng` is a single SplitMix64 stream, so drawing sequentially would make
//! every roll depend on **how many draws happened before it**. Adding one new
//! random call anywhere — a future ability, a loot roll — would silently
//! renumber every subsequent roll and break replay of existing encounters.
//!
//! COMB_001 Q8 specifies the alternative and it is the reason it does:
//! `(reality_id, turn_id, actor_id, action_idx, role)` with
//! `role ∈ {damage, crit, hit, position, loot}`. Each roll gets its **own**
//! stream derived from its coordinates, so rolls are independent of draw order
//! and of each other. A new role can be added without disturbing any existing
//! one.
//!
//! Consequence worth stating: combat math needs no ambient randomness at all.
//! Everything is a function of state, which is what keeps the CNC-D5
//! concurrency conformance test green.

mod attack;
mod initiative;
mod outcome;
mod rng;
mod stats;

pub use attack::{hit_chance_pm, resolve_attack, AttackOutcome};
pub use initiative::{action_value, next_actor, AvStatus};
pub use outcome::{evaluate_outcome, EncounterOutcome, Side};
pub use rng::{role_rng, SeedRole};
pub use stats::CombatStats;
