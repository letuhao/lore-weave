//! **`M2` — a verb is a declared ROW, and the engine never branches on its name.**
//!
//! > **Verbs are declared by FEATURES. The command substrate is the HUB that
//! > resolves them — and it knows nothing about what any of them MEAN.**
//! > — `docs/specs/2026-08-06-command-hub.md`, sealed
//!
//! That is the actor hub's sentence one level up, and deliberately so: the hub
//! folds a quantity contribution without knowing what the quantity means; the
//! substrate resolves a verb declaration without knowing what the verb means.
//! **If the two sentences stop being the same sentence, one of the two designs
//! has drifted.**
//!
//! ## The closure rule, which is what makes this set non-arbitrary
//!
//! `CMD-3`: an effect is a row from a **closed primitive set**, and a primitive
//! exists **iff the substrate already built the door it goes through**. Measured
//! 2026-08-06, **one door of seven is open** — `Delta`, a signed write to a
//! declared quantity, built by the actor hub in `M1`. `StatusPropose`,
//! `EdgeMove`, `LifecycleRequest`, `ClockAdvance`, `Materialise` and `Oracle`
//! are prose with zero implementation.
//!
//! **So [`EffectRow`] has no `kind` field.** There is nothing to discriminate: a
//! one-variant enum would be a discriminant byte in every reality's hashed bytes
//! forever, encoding a choice that does not exist, and `QTY-A10(c)` forbids ever
//! taking it back out. The kind arrives with the second door, as a schema bump —
//! which is loud, and is supposed to be.
//!
//! ## What an author may NOT write, and why that is the load-bearing part
//!
//! `CMD-10`'s fourth classification question:
//!
//! > **V4 · Does every authored field enter the engine as an OPERAND — a value
//! > the engine's own fixed rule then judges — or can a field BE the
//! > judgement?**
//!
//! Every field here is an operand. `amount` is a number the engine's own
//! conservation rule applies; `at_least` is a threshold the engine's own
//! comparison judges (`D-29`: *a condition is a declared **threshold**, never a
//! **predicate grammar***); `cue` is consumed past the authority boundary and
//! reaches no judgement at all.
//!
//! **`submitter_class` and `may_submit_engine_verbs` are ABSENT, and their
//! absence is `CMD-10`'s owed bite discharged.** `CMD-10`'s own table marks them
//! ❌ — *"the author supplies the verdict of the authorisation rule"*. They are
//! not merely unimplemented: [`crate::FORBIDDEN_VERB_KEYS`] makes writing one a
//! REFUSAL with a reason, so an author who reaches for authority is told why
//! rather than told "unknown field".

use crate::quantity::QuantityName;

mod table;
pub use table::{VerbTable, MAX_DECLARED_CUES, MAX_DECLARED_VERBS};

/// **The one built effect primitive: a signed write to a declared quantity.**
///
/// See the module doc for why there is no `kind` discriminant.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct EffectRow {
    /// The `QTY-A5` ordinal of the quantity this changes.
    pub quantity: u16,
    /// Signed. The engine clamps against the pool's own declared bounds; the
    /// author supplies the magnitude and nothing else.
    pub amount: i32,
}

/// **A legality threshold — `D-29`, sealed: a condition is a declared
/// THRESHOLD, never a predicate grammar.**
///
/// One comparison, one direction, no operators the author picks. An author who
/// could write the comparison would be writing the rule; writing the number is
/// writing an operand.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RequirementRow {
    pub quantity: u16,
    /// The verb is legal only while the actor's quantity is at least this.
    pub at_least: i32,
}

/// Who the effect lands on. **A closed ENGINE set** — the author picks a member,
/// never adds one, because each member is an engine dispatch and minting one
/// would change what the engine can dispatch (`CMD-10`, the ref-kind row).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum TargetRole {
    /// The submitting actor. Needs no offer, which is why `M2`'s first verb is
    /// one: `CMD-11`/`CMD-12`'s offer registry is not built.
    Actor = 0,
    /// Another actor, named in the submission. **Requires the offer registry**
    /// to be safe — see [`VerbError::TargetNeedsOfferRegistry`].
    Other = 1,
}

impl TargetRole {
    pub const ALL: [TargetRole; 2] = [TargetRole::Actor, TargetRole::Other];

    pub const fn as_str(self) -> &'static str {
        match self {
            TargetRole::Actor => "actor",
            TargetRole::Other => "other",
        }
    }

    pub fn from_str(s: &str) -> Option<Self> {
        Self::ALL.into_iter().find(|t| t.as_str() == s)
    }
}

/// One declared verb.
///
/// **The ordinal is the row's INDEX**, assigned like a quantity's and for the
/// same reason (`QTY-A5`: assigned, never authored) — append-only, never reused,
/// which is `CMD-1`.
///
/// `Copy` and inline, so `Ruleset::engine_default` stays a `const fn` and
/// `size_of` can still see the payload — the `QTY-A6 ⊥ QTY-A12` trap.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct VerbDecl {
    /// The author's word for it. **The engine never branches on this** — it is a
    /// lookup key on the submission path and nothing else (`CMD-6`).
    ///
    /// The same validated identifier type a quantity uses. One charset rule for
    /// every authored name: two rules for one concept is exactly the thing
    /// `QTY-A5` calls able to silently disagree.
    pub name: QuantityName,
    /// **That something must be SHOWN** — an ordinal on a channel of its own
    /// (`CMD-4`). The engine carries it and never reads it; what it renders as
    /// is presentation's, in whatever language the reader asked for.
    ///
    /// **PER-REALITY, and bounded by [`MAX_DECLARED_CUES`]** (PO, sealed
    /// 2026-08-06). Because the engine never reads it, its meaning can only come
    /// from the reality that declared it — so `QTY-A14` applies unchanged: cue 3
    /// in one reality means nothing in another.
    pub cue: u16,
    /// What must hold. `None` = always legal.
    pub requires: Option<RequirementRow>,
    /// What it costs. `None` = free.
    ///
    /// **Spend is NOT rolled back on a refused effect** — `O-CI-4`. A verb whose
    /// cost is taken and whose effect is refused is a fact about a real attempt,
    /// not a transaction to undo.
    pub spend: Option<EffectRow>,
    /// What it changes.
    pub effect: EffectRow,
    pub target: TargetRole,
}

/// Why a declared verb was refused. **Every one is a BUILD refusal** — at
/// reality creation, where the message reaches whoever authored it, never at
/// submission where it would reach a player.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum VerbError {
    TooMany { found: usize, capacity: usize },
    /// Two rows for one name. Refused rather than deduped, the same call
    /// `QuantityError::Duplicate` makes: a silent collapse hides which layer's
    /// declaration won.
    Duplicate { name: String },
    /// A row names a quantity ordinal this ruleset never declared.
    ///
    /// Refused because an effect on a quantity that does not exist can never
    /// fire, and an author who wrote it would see a verb that silently does
    /// nothing — the `QTY-Q5` class this whole tier exists to refuse.
    UnknownQuantity { verb: String, ordinal: u16, declared: usize },
    /// A verb whose effect targets another actor, in a build with no offer
    /// registry.
    ///
    /// **`CMD-11`/`CMD-12` are PARKED, not built.** Accepting this row would let
    /// a submission name any entity id it liked, and the MAC'd offer that is
    /// supposed to make a target legitimate does not exist. Refusing is the only
    /// honest answer: the alternative is a verb that works and is unauthorised.
    TargetNeedsOfferRegistry { verb: String },
    /// A cue ordinal past the reality's declared cue space.
    ///
    /// The cue space is **per-reality** and bounded (see [`MAX_DECLARED_CUES`]).
    /// An author's typo would otherwise be stored as a number presentation can
    /// never resolve — a fact on the log pointing at nothing.
    CueOutOfRange { verb: String, cue: u16, capacity: usize },
}

impl core::fmt::Display for VerbError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            Self::TooMany { found, capacity } => write!(
                f,
                "{found} declared verbs exceeds this engine's capacity of {capacity}. \
                 Raising MAX_DECLARED_VERBS is a code change and moves no existing digest \
                 - only 0..n is encoded"
            ),
            Self::Duplicate { name } => write!(
                f,
                "two verb rows are both called `{name}`. Refused rather than deduped: a \
                 silent collapse would hide which layer's declaration won, and the losing \
                 row is a verb its author believes exists"
            ),
            Self::UnknownQuantity { verb, ordinal, declared } => write!(
                f,
                "verb `{verb}` names quantity ordinal {ordinal}, but this reality declares \
                 only {declared}. An effect on a quantity that does not exist can never \
                 fire, and the verb would silently do nothing"
            ),
            Self::CueOutOfRange { verb, cue, capacity } => write!(
                f,
                "verb `{verb}` declares cue {cue}, past this reality's cue space of                  {capacity}. A cue is PER-REALITY and bounded; a number outside it is one                  presentation can never resolve, so the fact would point at nothing"
            ),
            Self::TargetNeedsOfferRegistry { verb } => write!(
                f,
                "verb `{verb}` targets another actor, and this build has no offer registry \
                 (CMD-11/CMD-12 are parked). Without one a submission may name any entity \
                 it likes, so accepting the row would ship a verb that works and is \
                 unauthorised. Use target = \"actor\" until the registry exists"
            ),
        }
    }
}
