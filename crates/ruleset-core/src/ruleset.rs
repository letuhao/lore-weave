//! The resolved ruleset and its content digest (RLS-A13).

use sim_core::RulesetDigest;

use crate::canon::{Canon, CanonEncode, CanonError};
use crate::combat::CombatRules;
use crate::provenance::{Provenance, RulesetEpoch};
use crate::quantity::QuantityTable;
use crate::resource::ResourceTable;
use crate::verb::VerbTable;
use crate::progression::ProgressionDigest;
use crate::stats::StatRules;

/// Bumped when the canonical ENCODING or the field set changes in a way that
/// is not itself a rules change. Written first into every canonical stream, so
/// an encoding change can never be mistaken for a rules change: both move the
/// digest, but only one of them moves it for every reality at once.
pub const RULESET_SCHEMA_VERSION: u32 = 7;

/// The oldest schema version this engine can still DECODE.
///
/// Versions in `SCHEMA_VERSION_OLDEST..=RULESET_SCHEMA_VERSION` each keep a
/// frozen codec (QTY-A11); anything below is gone and anything above is the
/// future, and both are refusals rather than guesses.
pub const SCHEMA_VERSION_OLDEST: u32 = 1;

/// The version of the LAWS this binary implements — the damage chain's
/// arithmetic and order, initiative, the stat resolution order.
///
/// **Bump this by hand when a law changes behaviour**, and never for a refactor
/// that cannot change a number. See [`Ruleset::law_version`] for why it exists
/// and why it is not derived from the build.
pub const LAW_VERSION: u32 = 1;

/// What a pre-`LAW_VERSION` artifact is deemed to carry.
///
/// Zero rather than one, deliberately: a v1 artifact does not assert *"I ran
/// under law version 1"* — it asserts nothing, because the concept did not
/// exist when it was written. Calling that `1` would manufacture a claim the
/// bytes never made, which is the same species as an anonymous zero digest
/// (`scripts/zero-digest-gate.py`): a declared unknown has a name, an emergent
/// one is a number nobody can explain.
pub const LAW_VERSION_UNVERSIONED: u32 = 0;

/// A reality's resolved rules — hot, ~KB, versioned, immutable (doc 16 §2).
///
/// This is what the island holds behind `Arc<D::Rules>` and what `apply` /
/// `check` receive by reference (RLS-A12). It is deliberately NOT in
/// `D::State`: rules in state would ride along in every checkpoint, migration
/// payload and crash rebuild.
///
/// F1 carries the two groups the laws actually read today. F2 grows it —
/// races, languages, ideologies, item/ability defs, loot tables — through the
/// provider stack. Nothing here anticipates those: an empty `Vec<RaceDecl>`
/// with no producer and no consumer would be a shape nobody reads, which is
/// the anti-pattern this whole arc has been closing.
///
/// **Deliberately NOT `Copy`.** Its own design point (RLS-A13) is that
/// identical rules INTERN — one `Arc` shared across every island of a reality
/// and across every reality on the same preset. `Copy` invites exactly the
/// accidental by-value duplication that undermines. The two leaf structs stay
/// `Copy` because they are plain number bags today; the aggregate is the thing
/// that is meant to be shared, not copied.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Ruleset {
    pub schema_version: u32,
    /// **QTY-D13 — the digest must cover the LAW, not just the numbers.**
    ///
    /// Before this field, `digest()` hashed `schema_version + combat + stats`
    /// and nothing else, so **two engine builds with different `resolve_attack`
    /// arithmetic produced the IDENTICAL digest for identical rules.** RLS-A13
    /// claims an event is pinned to *the rules that produced it*; a law change
    /// moved nothing, which meant a behavioural change was **undetectable** and
    /// therefore could not trigger any boundary — neither a checkpoint nor a
    /// refusal. The pin was covering the config and calling it the rules.
    ///
    /// Bumped **by hand** whenever a law's arithmetic or its order changes
    /// (QTY-A10(b)). It is not derived from the build: a rebuild with no
    /// behavioural change must not move every reality's digest, and only a human
    /// can say which of the two happened.
    pub law_version: u32,
    pub combat: CombatRules,
    pub stats: StatRules,
    /// **Q1 — the L2 layer, and the first thing in this struct an AUTHOR names.**
    ///
    /// Everything above is engine vocabulary with author-set values. This is
    /// author-set *identity*: a reality declares `qi` and the engine, which has
    /// never heard of `qi`, assigns it ordinal 0 and hashes the assignment
    /// (QTY-A5). That is what makes the ordinal stable across edits instead of
    /// a function of file order.
    pub quantities: QuantityTable,
    /// **Q2 — QTY-A4: which of those declared identities are POOLS.**
    ///
    /// Separate from `quantities` rather than a field on each entry, because
    /// most declared quantities are not pools: a stat contribution key, a tag,
    /// a progression axis. Folding an `Option<ResourceDecl>` into every
    /// `QuantityName` would put ~24 dead bytes beside every identity and encode
    /// a discriminant for each — for a table whose whole design note is that
    /// only `0..n` is encoded.
    pub resources: ResourceTable,
    /// **`S-1b`** — the content address of this reality's progression table
    /// (`PGN-R1`), or `None` if it declares none.
    ///
    /// The one field here that is a POINTER rather than a value, and the reason
    /// is measured: `PROG_001` §5.6's own worked example is 24 tiers in one
    /// kind, and a `TierDecl` transitively owns `String`/`Vec`/`HashMap`, so it
    /// can never be `Copy`, never be `const`-constructed, and **cannot be seen
    /// by `size_of` at all** — the `QTY-A6 ⊥ QTY-A12` trap. `store.rs` already
    /// made this move one level up: *"the envelope carries the digest, not the
    /// ruleset."*
    ///
    /// **`Option`, not a zero sentinel.** `zero-digest-gate` exists because
    /// `RulesetDigest([0u8; 32])` shipped in 15 places and *"looks like a
    /// value"* — nothing distinguished *"not wired yet"* from *"genuinely
    /// none"*. `None` puts that distinction in the type system.
    ///
    /// ⚠ **`None` is the ONLY spelling of "no progression".** A `Some(d)` where
    /// `d == ProgressionTable::EMPTY.digest()` is the same behavioural state
    /// under a different pin, which would give one set of rules two digests and
    /// break `RLS-A13`. The refusal lives on the path that WRITES the pin —
    /// `ruleset_loader::ProgressionStore::put`, with `resolve_progression` as a
    /// second end for bytes that arrive by another route
    /// (`D-PROGRESSION-EMPTY-PIN`, CLOSED by `PGN-R2a`).
    pub progression: Option<ProgressionDigest>,
    /// **`M2` — `CMD-1`: the declared verbs, and their ordinals.**
    ///
    /// Inside the hashed bytes, and it has to be: two realities whose verbs
    /// differ are two different sets of rules, and `RLS-A13` says an event is
    /// pinned to the rules that produced it. A verb table living outside the
    /// digest would let a reality gain an action with nothing going red.
    ///
    /// **A TABLE and not a POINTER, unlike `progression`, and the difference is
    /// measured rather than stylistic.** A `TierDecl` transitively owns
    /// `String`/`Vec`/`HashMap`, so it can never be `Copy`, never be
    /// `const`-constructed, and cannot be seen by `size_of` at all — the
    /// `QTY-A6 ⊥ QTY-A12` trap, which is why that one is a content address. A
    /// `VerbDecl` is a fixed-size POD: a 32-byte name, two ordinals, three small
    /// rows. It fits inline, so it is inline, and `size_of` can still see it.
    pub verbs: VerbTable,
}


impl Ruleset {
    /// The priority-0 `engine_default` layer (RLS-D2), resolved with no
    /// higher layer present.
    pub const fn engine_default() -> Self {
        Self {
            schema_version: RULESET_SCHEMA_VERSION,
            law_version: LAW_VERSION,
            combat: CombatRules::engine_default(),
            stats: StatRules::engine_default(),
            // The engine declares NO quantities. Every reality created before
            // Q1 resolves to exactly this, so their digests move (a field
            // entered the bytes) but their BEHAVIOUR does not.
            quantities: QuantityTable::EMPTY,
            // The engine declares no pools either. `hp` and `stamina` are not
            // pools in this sense: they are ENGINE vitals backed by StatSlot
            // ceilings and read by the laws directly, and QTY-A10(c) is why
            // they stay exactly where they are.
            resources: ResourceTable::EMPTY,
            // The engine declares no progression. `None`, never a zero digest.
            // The engine declares no verbs. A verb in the engine default would
            // enter every reality in existence and QTY-A10(c) forbids removing
            // it -- the same call `resources` makes one field up.
            progression: None,
            verbs: VerbTable::EMPTY,
        }
    }

    /// The canonical bytes this ruleset's digest is taken over (RLS-D5).
    ///
    /// Exposed rather than private because the ENCODING is part of the
    /// contract: a test that can only observe the digest cannot tell a field
    /// that is missing from one that hashes to a colliding value, and F2's
    /// stored artifact addresses these bytes, not the struct.
    pub fn canon_bytes(&self) -> Vec<u8> {
        let mut c = Canon::new(Self::CANON_DOMAIN);
        self.canon(&mut c);
        c.finish()
    }

    /// RLS-A13 — BLAKE3 over the canonical normalized encoding.
    ///
    /// **Computed on demand, never cached.** A cached digest is a staleness bug
    /// waiting for someone to add a mutation path; the whole artifact is ~200
    /// bytes and this is called once per island creation, so there is nothing
    /// to buy.
    pub fn digest(&self) -> RulesetDigest {
        RulesetDigest(*blake3::hash(&self.canon_bytes()).as_bytes())
    }
}

impl Ruleset {
    /// The domain-separation tag every ruleset stream begins with.
    pub(crate) const CANON_DOMAIN: &'static str = "loreweave.ruleset.v1";

    /// Decode a ruleset from the exact bytes [`Self::canon_bytes`] produces.
    ///
    /// **This is what makes RLS-D18 true rather than aspirational** — *"the
    /// digest addresses the STORED BYTES, not the upcast form"*. Without a
    /// decoder the store can only write; with one, `digest(decode(bytes))` can
    /// be checked against `blake3(bytes)`, which is exactly how
    /// `RulesetStore::get` refuses a tampered artifact.
    ///
    /// Refuses rather than guesses: wrong tag, unknown schema version, short
    /// read, or trailing bytes. An unknown schema version is a REFUSAL and not
    /// a best-effort read, because RLS-D18 says a stored ruleset is never
    /// reinterpreted — and reading a v2 artifact with v1 field offsets would be
    /// reinterpretation of the worst kind: silent, and numerically plausible.
    pub fn from_canon_bytes(bytes: &[u8]) -> Result<Self, CanonError> {
        Self::from_canon_bytes_versioned(bytes).map(|(r, _)| r)
    }
}

impl CanonEncode for Ruleset {
    /// The CURRENT (v2) layout. Historical layouts live in
    /// [`Ruleset::canon_bytes_at`], which is the only other place a `Ruleset`
    /// may be encoded — keeping this impl the single definition of "current"
    /// while still letting an old artifact be re-encoded for verification.
    fn canon(&self, c: &mut Canon) {
        // EXHAUSTIVE destructuring, no `..` — see `CanonEncode`. Adding
        // `law_version` broke this line until it was named here, which is the
        // mechanism doing its job: a new field cannot silently stay out of the
        // digest.
        let Self {
            schema_version,
            law_version,
            combat,
            stats,
            quantities,
            resources,
            progression,
            verbs,
        } = self;
        c.u32(*schema_version);
        c.u32(*law_version);
        combat.canon(c);
        stats.canon(c);
        quantities.canon(c);
        // The version is passed explicitly rather than read from `self`:
        // `schema_version` is destructured above and is the CURRENT constant by
        // construction here, while `canon_bytes_at` must be able to ask for an
        // older layout. One encoder, two callers, no branch on a struct field
        // that a decoded-then-upcast value would have already overwritten.
        resources.canon_at(c, crate::ruleset::RULESET_SCHEMA_VERSION);
        crate::ruleset_codec::canon_progression(c, progression);
        verbs.canon_at(c, crate::ruleset::RULESET_SCHEMA_VERSION);
    }
}


/// What F2 stores and what a reality is created from: the rules, the lineage
/// that must not affect identity, and the ordering epoch.
///
/// The three-way split is what makes RLS-A15's exclusion **testable rather than
/// asserted**: because `Provenance` sits inside this container, "same rules +
/// different provenance ⇒ same digest" is a claim about a real code path. With
/// `Provenance` living somewhere else entirely, that test would be vacuously
/// true and would prove nothing.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ResolvedRuleset {
    pub ruleset: Ruleset,
    /// Excluded from [`Self::digest`] by construction — `Provenance` has no
    /// `CanonEncode` impl, so including it would not compile.
    pub provenance: Provenance,
    /// Ordering, not identity (RLS-A13). Also excluded: the same rules resolved
    /// at two epochs are the same rules, and interning them under one digest is
    /// the point.
    pub epoch: RulesetEpoch,
}

impl ResolvedRuleset {
    /// The engine-default ruleset with empty lineage at epoch 0 — what a
    /// binary uses before F2's loader exists.
    pub fn engine_default() -> Self {
        Self {
            ruleset: Ruleset::engine_default(),
            provenance: Provenance::default(),
            epoch: RulesetEpoch(0),
        }
    }

    pub fn digest(&self) -> RulesetDigest {
        self.ruleset.digest()
    }
}

