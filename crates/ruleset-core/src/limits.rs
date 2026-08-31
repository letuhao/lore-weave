//! **A reality declares how big it is. The engine only says what the binary can
//! physically hold.**
//!
//! > *"Hard ceilings should be pushed out for the reality manifest to decide,
//! > because we only build a world engine. A hardcoded number should be DATA and
//! > INGESTED, not a magic number inside the world engine."*
//! > — PO, 2026-08-06, sealed as `LIM-1`
//!
//! ## The rot this replaces
//!
//! Before this module, `QuantityTable::assign` refused with:
//!
//! ```text
//! 40 declared quantities exceeds this engine's capacity of 32
//! ```
//!
//! Read that sentence as an author would. **The engine is answering a question
//! that is not its to answer** — *how big may this world be?* — and answering it
//! with a number chosen by whoever wrote the crate. Every reality on the
//! platform inherited one developer's guess about how many quantities a world
//! needs, and had no way to say otherwise in either direction: a small reality
//! could not declare itself small, and a large one could not declare itself
//! large without a code change to a crate it does not own.
//!
//! That is one number doing two incompatible jobs:
//!
//! | | who decides | what it means | how it changes |
//! |---|---|---|---|
//! | **capacity** ([`OrdinalSpace::capacity`]) | the engine | *this binary's inline array is `N` wide* | rebuild |
//! | **limit** ([`Limits`]) | the reality's manifest | *this world declares at most `n`* | edit a `.toml` |
//!
//! **Only the second one was ever a design decision, and it was living in the
//! wrong repository.** This module separates them and hands the second to the
//! manifest.
//!
//! ## Why capacity cannot ALSO be data, stated honestly
//!
//! It is a compile-time array width. Making it runtime data means a heap
//! allocation, and a heap allocation is forbidden here by name: `QTY-A6 ⊥
//! QTY-A12` — boxing a payload makes `size_of` report 16 bytes for every `n`, so
//! the assertions that guard these structs would compile, always pass, and never
//! be able to fire again. **The correct move is not to make capacity authorable;
//! it is to stop capacity being MISTAKEN for a design ceiling** — which is what
//! [`Limits`] does, by putting the design ceiling somewhere an author can reach
//! and leaving capacity to be what it always was: a physical fact about a
//! binary, in the same class as a page size.
//!
//! So the two refusals are now different sentences with different audiences:
//!
//! * [`LimitError::AtLimit`] — *your world said 8; this is the 9th.* For the
//!   author, in the file they are editing.
//! * [`LimitError::AboveCapacity`] — *you asked for 200; this build holds 64.*
//!   For whoever deploys the binary. It names a rebuild, not a design mistake.
//!
//! ## Why limits are NOT in the digest
//!
//! A limit is read exactly once, at ingest, and never again — no law reads it,
//! no step reads it, and a resolved [`crate::Ruleset`] is immutable, so after
//! resolution there is nothing left for it to constrain. Three consequences,
//! and all three point the same way:
//!
//! 1. **`RLS-A15`'s precedent.** Provenance is excluded from the digest because
//!    the same rules from two sources are the same rules. The same rows under
//!    two different declared ceilings are, likewise, the same rules — they
//!    produce the same numbers for every actor.
//! 2. **A divergence is still visible where it matters.** If two realities with
//!    identical rows declare different limits, and an author then adds a row to
//!    each, one refuses and one accepts — and the one that accepted now has a
//!    different ROW SET, which *is* hashed. The digest moves at the moment the
//!    behaviour does, not before.
//! 3. **`QTY-A10(c)` — a hashed field can never be removed.** Hashing this would
//!    be irreversible, would move every existing reality's digest, and would buy
//!    a distinction nothing reads. When in doubt, do not hash.
//!
//! **This is why `Limits` has no [`crate::CanonEncode`] impl** — the same
//! structural exclusion `Provenance` uses. Including it would not compile, so
//! the exclusion is a property of the type rather than a promise in a comment.
//!
//! ## Why this is also the ordinal-space register
//!
//! `docs/specs/2026-08-06-ordinal-spaces.md` opened with the finding that
//! **nothing in the tree counted ordinal spaces** — which is why a cue space
//! shipped with no constant, no bound and no argument, twelve lines from a
//! constant carrying all three. [`OrdinalSpace`] is that register, in code: a
//! closed enum whose [`OrdinalSpace::ALL`] is exhaustive, so a new ordinal space
//! that forgets to declare a capacity does not compile.

use crate::quantity::MAX_DECLARED_QUANTITIES;
use crate::resource::MAX_DECLARED_RESOURCES;
use crate::verb::MAX_DECLARED_VERBS;

/// **The register of every author-extensible ordinal space.**
///
/// A space belongs here iff an AUTHOR can add members to it by writing rows.
/// That is the whole membership test, and it is what keeps the enum from
/// becoming a dumping ground:
///
/// * `EngineRole`, `TargetRole`, `StatSlot`, `ModifierOp` are **closed engine
///   sets** — an author picks a member and can never mint one, so there is no
///   ceiling for a manifest to declare and they are deliberately absent.
/// * `PluginOrdinal` is **engine-side** — a plugin is a compiled-in feature, not
///   an authored row. A manifest declaring a plugin ceiling would be declaring a
///   limit on the binary it is running against, which is backwards.
/// * Cues are **derived, not declared** — every cue comes from a verb row and
///   there is exactly one per row, so a reality's cue space is its verb limit.
///   See [`Limits::cues`].
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
#[repr(usize)]
pub enum OrdinalSpace {
    /// `QTY-A5` — the identities an author invents.
    Quantities = 0,
    /// `QTY-A4` — which of those identities are pools.
    Resources = 1,
    /// `CMD-1` — the declared verbs. Append-only: an ordinal IS the identity.
    Verbs = 2,
}

impl OrdinalSpace {
    pub const COUNT: usize = 3;

    /// EXHAUSTIVE. A new variant that is not listed here fails
    /// `every_space_is_in_all`, which is the mechanism keeping this register
    /// from going stale the way the cue space did.
    pub const ALL: [OrdinalSpace; Self::COUNT] =
        [OrdinalSpace::Quantities, OrdinalSpace::Resources, OrdinalSpace::Verbs];

    /// The key an author writes in `[limits]`.
    pub const fn as_str(self) -> &'static str {
        match self {
            OrdinalSpace::Quantities => "quantities",
            OrdinalSpace::Resources => "resources",
            OrdinalSpace::Verbs => "verbs",
        }
    }

    /// **What this BINARY can hold — not what a world may declare.**
    ///
    /// Widening any of these is a rebuild that **moves no existing digest**,
    /// because only `0..n` is ever encoded (`QTY-A6`). Narrowing one is
    /// forbidden by data, not by taste: a stored ordinal past the new width is
    /// unreadable, and `QTY-A14` says an ordinal is meaningless without its
    /// `(reality, digest)` — there is no safe reinterpretation.
    pub const fn capacity(self) -> u16 {
        match self {
            OrdinalSpace::Quantities => MAX_DECLARED_QUANTITIES as u16,
            OrdinalSpace::Resources => MAX_DECLARED_RESOURCES as u16,
            OrdinalSpace::Verbs => MAX_DECLARED_VERBS as u16,
        }
    }
}

// `ALL` is complete, in discriminant order, and has no gaps.
//
// **What this catches and what it does not — stated precisely, because an
// overclaimed guard is worse than none (`NV-1`).** A new variant is a COMPILE
// error in four places before it reaches here: `as_str`, `capacity`,
// `LimitsPatch::get` (it must be given an authored key) and `declared_in` (it
// must be countable). All four are exhaustive matches. What none of them catch
// is a variant added to the enum and to those matches but NOT to `ALL` — the one
// hand-maintained line — and this check catches only the two shapes of that
// mistake that are expressible: a reorder, and a gap in the discriminants. A
// variant appended past `COUNT` is caught by `Limits::get` indexing a
// `[u16; COUNT]` out of bounds, which is a panic rather than a compile error.
const _: () = {
    let mut i = 0;
    while i < OrdinalSpace::COUNT {
        assert!(OrdinalSpace::ALL[i] as usize == i);
        i += 1;
    }
};

impl core::fmt::Display for OrdinalSpace {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        f.write_str(self.as_str())
    }
}

/// **One reality's declared size**, folded from its manifest layers.
///
/// Seeded at [`Limits::CAPACITY`] so a manifest that declares nothing behaves
/// exactly as it did before this module existed. `AUTHOR-1` decides that
/// default: the manifest author is not a developer and typically generates the
/// file with an LLM, so a mandatory block on every preset would be a cost paid
/// by every author to serve the few who want a tighter bound.
///
/// **Deliberately not `Default`.** The only correct starting value is
/// [`Limits::CAPACITY`], and a `Default` impl invites `Limits::default()` at a
/// call site where the author meant "no limits" and silently got zeros — a
/// reality that can declare nothing at all, refusing its own first row.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Limits {
    by_space: [u16; OrdinalSpace::COUNT],
}

impl Limits {
    /// Every space at this binary's physical capacity — what a manifest that
    /// declares no `[limits]` block gets.
    pub const CAPACITY: Self = Self {
        by_space: [
            MAX_DECLARED_QUANTITIES as u16,
            MAX_DECLARED_RESOURCES as u16,
            MAX_DECLARED_VERBS as u16,
        ],
    };

    pub const fn get(self, space: OrdinalSpace) -> u16 {
        self.by_space[space as usize]
    }

    /// **The cue space, DERIVED from the verb limit rather than declared.**
    ///
    /// Every cue in existence comes from a verb row and there is exactly one per
    /// row, so a reality with 8 verbs cannot need a 9th distinct cue. Deriving
    /// removes a number to keep in step, and keeps one key out of the authored
    /// surface (`AUTHOR-1`).
    ///
    /// ⚠️ When a non-verb emitter arrives — a status lapsing, an encounter
    /// ending — this derivation stops being true and must change HERE, once,
    /// with a reason.
    pub const fn cues(self) -> u16 {
        self.get(OrdinalSpace::Verbs)
    }

    /// Apply an authored `[limits]` value for one space.
    ///
    /// `declared` is how many rows the fold has already accepted, so a layer
    /// cannot narrow the world out from under rows a lower layer already put in
    /// it — that would leave the resolved ruleset holding an ordinal past its
    /// own declared ceiling, which is a state no later check would catch.
    pub fn declare(
        &mut self,
        space: OrdinalSpace,
        value: u16,
        declared: usize,
    ) -> Result<(), LimitError> {
        let capacity = space.capacity();
        if value > capacity {
            return Err(LimitError::AboveCapacity { space, asked: value, capacity });
        }
        if (value as usize) < declared {
            return Err(LimitError::BelowDeclared { space, asked: value, declared });
        }
        self.by_space[space as usize] = value;
        Ok(())
    }

    /// Refuse the row about to be declared if this reality has no room left.
    ///
    /// Called BEFORE the push rather than after the loop, so the message names
    /// the row that did not fit. An author reading *"9 verbs exceeds 8"* has to
    /// work out which one is the ninth; an author reading *"verb `parry` does
    /// not fit"* does not.
    pub fn room_for(self, space: OrdinalSpace, declared: usize, row: &str) -> Result<(), LimitError> {
        if declared >= self.get(space) as usize {
            return Err(LimitError::AtLimit {
                space,
                limit: self.get(space),
                row: row.to_string(),
            });
        }
        Ok(())
    }
}

/// Why a declared size, or a row against it, was refused.
///
/// **Three variants, two audiences, and that split is the point of this whole
/// module.** [`Self::AtLimit`] and [`Self::BelowDeclared`] are for the AUTHOR:
/// their world said a number and their file disagrees with it. [`Self::
/// AboveCapacity`] is for whoever DEPLOYS: the world is fine, the binary is too
/// small, and the fix is a rebuild rather than an edit.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum LimitError {
    /// The manifest asked for a ceiling this build cannot physically hold.
    AboveCapacity { space: OrdinalSpace, asked: u16, capacity: u16 },
    /// The manifest asked for a ceiling below what layers have already declared.
    BelowDeclared { space: OrdinalSpace, asked: u16, declared: usize },
    /// A row did not fit inside the ceiling the reality declared for itself.
    AtLimit { space: OrdinalSpace, limit: u16, row: String },
}

impl core::fmt::Display for LimitError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            Self::AboveCapacity { space, asked, capacity } => write!(
                f,
                "this reality declares a limit of {asked} {space}, and this BUILD can hold \
                 {capacity}. That is a deployment fact, not an authoring mistake: the number \
                 is a compile-time array width, and raising it is a rebuild that moves no \
                 existing digest (only 0..n is encoded). Run a build with a larger capacity, \
                 or declare a smaller limit"
            ),
            Self::BelowDeclared { space, asked, declared } => write!(
                f,
                "this layer narrows {space} to {asked}, but {declared} are already declared by \
                 layers below it. Refused rather than clamped: accepting it would leave the \
                 resolved ruleset holding an ordinal past its own declared ceiling, which no \
                 later check looks for. Raise the limit, or remove the rows"
            ),
            Self::AtLimit { space, limit, row } => write!(
                f,
                "`{row}` does not fit: this reality declares a limit of {limit} {space}. This \
                 is YOUR world's number, not the engine's - raise `[limits] {space}` in the \
                 manifest (up to this build's capacity of {}), or drop a row",
                space.capacity()
            ),
        }
    }
}
