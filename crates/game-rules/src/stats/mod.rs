//! DF07 — the actor stat block: closed slots, integer determinism, locked
//! layer order.
//!
//! ## The axiom that shapes every line here
//!
//! **DF7-A4 (Byte-stable arithmetic):** a value entering a digest or a replayed
//! comparison must have **exactly one byte representation per value**. All
//! resolution here runs in **i64 milli-units** with exactly one `floor` at slot
//! emit. Same inputs → byte-identical block on any machine.
//!
//! That is not stylistic, but the reason is narrower than this comment used to
//! claim. It read *"float is reproducible within a build but not across
//! targets"* — **which is false for basic arithmetic**, and `crates/world-gen`
//! disproves it in this repo: 41 files use `f64` and
//! `civ_bundle_hash_is_deterministic_per_seed` hashes output derived from them.
//! IEEE 754 makes `+ - * /` and `sqrt` correctly rounded; Rust enables neither
//! fast-math nor FMA contraction; x86-64 and ARM64 both mandate SSE2/NEON, so
//! there are no 80-bit x87 intermediates left to fear.
//!
//! Fixed-point is right **here** because of what these numbers are — integers
//! on a fixed scale — so `NaN`, `-0.0` and rounding order never arise. What
//! genuinely does not reproduce, and stays forbidden on the replayed path, is
//! transcendental libm (`sin`/`cos`/`exp`/`ln`/`powf`, which IEEE 754 does not
//! require to be correctly rounded), order-dependent reductions, and
//! unnormalised `NaN`/`-0.0` reaching hashed bytes. See DF07_001 §3 DF7-A4
//! (revised 2026-08-02).
//!
//! **This corrects slice 1**, which stored `accuracy`/`dodge`/`crit` as `f64`.
//! The fractional slots are **per-mille integers** (0..1000), as DF07 specifies.
//!
//! ## Dense array, never a map (EC-3)
//!
//! `StatBlock` is `[i32; SLOT_COUNT]` indexed by slot ordinal. A `HashMap`
//! would put iteration order into the bytes the moment any consumer serialises
//! a block, breaking the DF7-V4 byte-identical assertion nondeterministically —
//! the worst kind of failure, since it passes locally and fails in CI on a
//! different seed.

// F1 — the closed slot vocabulary now lives in `ruleset-core`, because the
// ruleset declares a VALUE PER SLOT (`StatRules::slot_defaults`) and therefore
// has to be able to name the slots. Re-exported so every existing
// `commit_service::stats::StatSlot` import keeps working: one definition, two
// paths, no ordinal contract crossing a crate boundary untyped.
//
// What went with it: `default_value()`. Slot defaults are VALUES, and IMP-A1
// puts values in config — they are `StatRules::slot_defaults` now, inside the
// hashed struct, which is what makes XST-D5's *"edit a constant → the digest
// moves"* writable at all.
pub use ruleset_core::{SLOT_COUNT, StatRules, StatSlot};

mod block;
mod modifier;
mod resolve;
mod snapshot;

pub use block::StatBlock;
pub use modifier::{Clamp, ModifierOp, ModifierSource, StatModifier};
pub use resolve::resolve_block;
pub use snapshot::{StatEpoch, StatSnapshot};
