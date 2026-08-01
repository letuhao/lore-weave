//! `Q2` — `QTY-A4`: a pool is not a stat.
//!
//! > **QTY-A4.** A **resource** is `{ current, max, min, base, regen_rate,
//! > regen_type, zero_behaviour, deps, tags }`. Its **current** is actor state.
//! > Its **max** is a derived value. Everything else is a **declared row**, not
//! > a slot.
//!
//! Three of those nine live somewhere other than here, and saying where is the
//! whole point of the axiom:
//!
//! | field | lives | why |
//! |---|---|---|
//! | `current` | the **actor** (`pools[ordinal]`) | it is per-actor state that changes every turn; putting it in the ruleset would make spending mana a rules change |
//! | `max` | **derived**, via [`CeilingBinding`] | a cultivation realm RAISES a ceiling (`QTY-A8`); a max baked in here could only be edited, never contributed to |
//! | everything else | **here**, in the hashed bytes | identity, bounds and regen policy are what the reality DECLARED, and they must move the digest |
//!
//! **Adding a pool is therefore a declared row, not a `SLOT_COUNT` change** —
//! which is the single most likely spine-breaking event the adversarial audit
//! identified, removed.
//!
//! ## ONE ordinal space
//!
//! A resource does not get an ordinal of its own. It **is** a declared
//! quantity — `qi` is one identity — and [`ResourceDecl::quantity`] names it by
//! the quantity ordinal `QTY-A5` already assigned.
//!
//! The first design of this slice gave a resource a *second*, separate ordinal
//! for its slot in the actor's array, so that array could be narrower than the
//! 32-wide quantity space. It was rejected, and by the axiom rather than by
//! taste: two numbering schemes for one identity, both inside the hashed bytes,
//! is exactly the thing that can silently disagree — and `QTY-A5` exists
//! because a prior project renumbered its ordinals out from under itself. The
//! actor's array is `MAX_DECLARED_QUANTITIES` wide and indexed by the quantity
//! ordinal. A reality declaring 32 quantities of which 3 are pools carries 29
//! unused `i32`s, and that is the price of one ordinal space.
//!
//! ## What this slice does NOT build, and why not building it is the decision
//!
//! `QTY-A4` also lists **`deps`** and **`tags`**. Neither has a consumer yet —
//! `deps` would order regen evaluation, `tags` would group pools for a bulk
//! effect, and no law reads either today.
//!
//! **A field in the hashed ruleset is effectively permanent.** It enters every
//! reality's digest, and `QTY-A10(c)` forbids ever removing it. Adding two
//! empty lists now would move every digest in existence to carry bytes nothing
//! reads, and then forbid taking them back out. They are not built. When a law
//! needs one, it arrives as a schema-version bump like every other addition.

use crate::quantity::MAX_DECLARED_QUANTITIES;
use crate::slots::StatSlot;

/// The pool capacity is the QUANTITY capacity — one ordinal space, one width.
///
/// Deliberately an alias rather than its own number: two constants that must
/// stay equal are two constants that can stop being equal.
pub const MAX_DECLARED_RESOURCES: usize = MAX_DECLARED_QUANTITIES;

/// Where a pool's ceiling comes from.
///
/// **Not a stored number.** `QTY-A8` distinguishes two verbs — a cultivation
/// realm *raises the ceiling*, a buff *fills toward it* — and a `max: i32`
/// baked into this row could only ever be edited, which is the god-class
/// formula edit returning by the back door. The ceiling is a **target that
/// contributions aggregate into**.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CeilingBinding {
    /// The ceiling is a derived stat slot.
    ///
    /// This is what `§6.3.1` means by *"`MaxHp`/`MaxStamina` **stay**, and
    /// become the slots a declared resource **binds its ceiling to**"* — and it
    /// is why `QTY-A10(c)` refused the original build order that deleted them.
    /// `RES_001:1083` already binds `max_value` to those slots; this is that
    /// binding, made declarable.
    Slot(StatSlot),
    /// A constant ceiling, in the hashed bytes.
    ///
    /// For a pool nothing contributes to — a fixed 100-point meter. Kept
    /// because the alternative is forcing every author to burn a stat slot on a
    /// pool that will never be raised, and slots are the closed resource here.
    Fixed(i32),
}

/// How a pool refills. Closed: regen is arithmetic the engine performs, so a
/// new mode is an engine release (`QTY-A10`), not a declared row.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum RegenType {
    /// No passive regeneration. The pool moves only when something spends or
    /// grants it.
    None = 0,
    /// `+regen_rate` per tick, clamped to the ceiling.
    Flat = 1,
    /// `+regen_rate` per-mille OF THE CEILING per tick — the same per-mille
    /// convention `StatSlot::is_per_mille` uses, so a reader does not have to
    /// remember two scales.
    PerMille = 2,
}

/// What happens when a pool reaches its floor.
///
/// **There is no `Defeat` variant, and its absence is the load-bearing part.**
/// Defeat is an engine law that reads `hp`, and `Q2`'s exit criterion is *"a
/// reality binds `Vital → qi` and the defeat law is **unchanged**"*. A declared
/// pool that could trigger defeat would change which value ends an encounter —
/// that is a behavioural change to a law (`QTY-A10(b)`), it needs the encounter
/// law's attention rather than a config field, and it is not this slice.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum ZeroBehaviour {
    /// Clamp at the floor and carry on.
    Clamp = 0,
    /// Clamp, and refuse any action whose cost this pool cannot pay.
    BlockCosts = 1,
}

/// One declared pool.
///
/// `Copy` and inline for the same reason [`crate::quantity::QuantityName`] is:
/// `Ruleset::engine_default` is a `const fn`, and a heap pointer here would put
/// the payload where `size_of` cannot see it — the `QTY-A6 ⊥ QTY-A12` trap.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ResourceDecl {
    /// The declared quantity this pool IS, by its `QTY-A5` ordinal.
    pub quantity: u16,
    /// The floor. Usually 0; signed because a pool may model debt.
    pub min: i32,
    /// The value an actor starts at.
    ///
    /// Distinct from `min` on purpose: a mana pool starts full and floors at 0,
    /// a corruption meter starts empty and floors at 0. Collapsing the two
    /// would make one of those inexpressible.
    pub base: i32,
    pub ceiling: CeilingBinding,
    pub regen_rate: i32,
    pub regen_type: RegenType,
    pub zero_behaviour: ZeroBehaviour,
}

/// Why a declared resource was refused.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ResourceError {
    /// More pools than the ordinal space holds.
    TooMany { found: usize, capacity: usize },
    /// The row names a quantity ordinal this ruleset has not declared.
    ///
    /// Refused rather than ignored: a pool whose identity does not exist is a
    /// pool nothing can ever name, spend or display, and silently dropping it
    /// would make the author's declaration vanish without a word.
    UnknownQuantity { ordinal: u16, declared: usize },
    /// Two rows for one quantity. Refused rather than deduped — a silent
    /// collapse would hide which layer's declaration won, the same call
    /// `QuantityError::Duplicate` makes.
    Duplicate { ordinal: u16 },
    /// `base` is outside `[min, ceiling]`, or `min` exceeds a fixed ceiling.
    ///
    /// Caught at declaration because the alternative is catching it per actor
    /// per spawn, forever, in code that has no way to report which row is wrong.
    BadBounds { ordinal: u16, reason: &'static str },
}

impl core::fmt::Display for ResourceError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            Self::TooMany { found, capacity } => write!(
                f,
                "{found} declared resources exceeds this engine's capacity of {capacity}. \
                 Raising MAX_DECLARED_QUANTITIES is a code change and moves no existing \
                 digest - only 0..n is encoded"
            ),
            Self::UnknownQuantity { ordinal, declared } => write!(
                f,
                "a resource row names quantity ordinal {ordinal}, but this ruleset declares \
                 only {declared} ({}). A pool whose identity does not exist can never be \
                 named, spent or displayed",
                if *declared == 0 { "none".into() } else { format!("0..{}", declared - 1) }
            ),
            Self::Duplicate { ordinal } => write!(
                f,
                "quantity ordinal {ordinal} has two resource rows. Refused rather than \
                 deduped: a silent collapse would hide which layer's declaration won"
            ),
            Self::BadBounds { ordinal, reason } => {
                write!(f, "the resource row for quantity ordinal {ordinal} is unusable: {reason}")
            }
        }
    }
}

mod table;
pub use table::ResourceTable;
