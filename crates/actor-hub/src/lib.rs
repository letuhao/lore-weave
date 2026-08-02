//! `actor-hub` — **feature #1 of roughly a thousand.**
//!
//! > **Features are PLUGINS. The actor is the HUB.**
//!
//! The hub holds a being's identity and what is **intrinsic** to it, tracks
//! **which plugins are attached**, and **folds** their contributions. **It knows
//! nothing about what any contribution means.**
//!
//! Its job is to make adding feature #2 cheap — **not to pre-empt it.**
//!
//! ## The contract this crate implements
//!
//! | file | owns |
//! |---|---|
//! | `docs/specs/2026-08-02-actor-hub/2026-08-02-actor-hub.md` | identity · intrinsic quantities · existence · attachment · the fold · the contribution seam |
//! | `docs/specs/2026-08-02-actor-hub/2026-08-02-engine-substrate.md` | the layer beneath: ordinals, the fold arithmetic, what is never silent |
//!
//! **Those two files are the specification. Nothing else is.** The derivation
//! record under `analysis/` explains *how* each line was reached and binds
//! nobody.
//!
//! ## The scope test, which decided every judgement call
//!
//! > **身外之物** — *a thing outside the body.* Strip the actor naked and move
//! > them to another world. What travels with them?
//!
//! Body, pools, statuses, lifespan and memories travel. Money, items, rank,
//! reputation and position stay behind. **If a datum would not travel, it does
//! not belong in the actor** — however convenient it is to put it there.
//!
//! The test applies to **quantities and state**. It does not rank *identity*
//! (which is what the test is about, so asking is circular) or *record
//! lifecycle* (a property of the row, not of the being).
//!
//! ## What the hub holds — five things
//!
//! ```text
//! 1  IDENTITY             EntityId                      — shipped: sim-core
//! 2  INTRINSIC QUANTITIES [i32; MAX_DECLARED_QUANTITIES] — the domain says how to read a slot
//! 3  EXISTENCE            GoneState                     — shipped: dp-kernel
//! 4  ATTACHMENT           PluginSet — a u32 bitmask over plugin ordinals
//! 5  THE FOLD             aggregate contributions, and know NOTHING about what they mean
//! ```
//!
//! ## Purity, and why it is a crate
//!
//! The fold is a function of `(actor, declarations, rows)` with one correct
//! answer. Making the hub a **crate** rather than a module means a future `use`
//! statement that would let it read a file is a **link error** instead of a
//! broken promise — the same reasoning `IMP-Q2` applied to `game-rules`.
//! `scripts/crate-purity-gate.py` is what keeps it true.
//!
//! **This crate does not depend on `game-rules`.** The hub sits *beneath* the
//! features, and combat is a feature; a dependency in that direction becomes a
//! cycle the day combat is rewritten as a plugin.

// `fold` and `report` are PUBLIC modules, not private ones with re-exports.
//
// Their module docs ARE part of the contract a plugin author reads — the fold
// formula, the three-pass limit, the totality argument, the `S-18` correction,
// and substrate §7's two verbs. As private modules none of that reached
// `cargo doc`, and three `[crate::fold]` links resolved to the 3-line *function*
// instead. All three now say `mod@crate::fold`; the first fix pass caught two and
// left the one inside `report.rs` -- which `cargo doc` cannot flag, because an
// ambiguous link that resolves to SOMETHING is not a warning. That is why the
// count in this sentence is load-bearing rather than decorative.
// `D-311` argues the hub's SDK IS its public crate surface; a page a plugin
// author cannot open is not on it.
mod actor;
pub mod fold;
mod ordinal;
mod plugin_set;
pub mod report;
mod registry;
mod rows;

pub use actor::{Actor, AttachError, DetachError};
pub use entity_existence::GoneState;
pub use fold::fold;
pub use report::{
    CapSite, Capped, Contribution, Explanation, FoldReport, Refused, RowRef,
};
pub use ordinal::{MAX_PLUGINS, PluginOrdinal, QuantityOrdinal};
pub use plugin_set::PluginSet;
pub use registry::{HubRegistry, PluginDecl, QuantityDecl, RegistryError, RowRefusal};
pub use rows::{ContributionBound, DerivationRow, FoldLayer, ModifierRow};

// The contribution ops, re-exported so a plugin author submitting rows does not
// also need a direct `ruleset-core` dependency. One definition — see
// `ruleset-core/src/modifier.rs` for why it lives beneath both the hub and the
// laws rather than in either.
pub use ruleset_core::{ModifierOp, OpKind};

// Item 1 of the five. Re-exported so a consumer naming an actor does not also
// need a direct `sim-core` dependency — the same courtesy `ruleset-core`
// extends for `RulesetDigest`.
//
// **The shipped engine has never known what an "actor" is; it holds things by
// `EntityId`.** A faction, a world, a place and a person are all entities.
// Which kinds exist is the actor and social features' vocabulary, not the
// hub's.
pub use sim_core::EntityId;

// Item 2's width, re-exported for the same reason: the actor's array is this
// wide, and a caller sizing anything against it should read one constant.
pub use ruleset_core::MAX_DECLARED_QUANTITIES;
