//! DF07 — the actor stat block: closed slots, integer determinism, locked
//! layer order.
//!
//! ## The axiom that shapes every line here
//!
//! **DF7-A4 (Integer determinism):** all resolution runs in **i64 milli-units**
//! with exactly one `floor` at slot emit, and **no float anywhere in the stat
//! path**. Same inputs → byte-identical block on any machine.
//!
//! That is not stylistic. Float arithmetic is reproducible *within* a build but
//! not reliably *across* targets — different optimisation levels can fuse a
//! multiply-add, x87 can keep 80-bit intermediates — and this project replays
//! committed encounters as its recovery model (EVT-A9, CNC-D5). A stat block
//! that differs in the last bit on another machine means a replayed fight
//! diverges, which is exactly the failure the whole event-sourced design exists
//! to prevent.
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
