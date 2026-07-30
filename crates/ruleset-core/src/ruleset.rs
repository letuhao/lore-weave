//! The resolved ruleset and its content digest (RLS-A13).

use sim_core::RulesetDigest;

use crate::canon::{Canon, CanonEncode, CanonError};
use crate::combat::CombatRules;
use crate::provenance::{Provenance, RulesetEpoch};
use crate::quantity::QuantityTable;
use crate::resource::ResourceTable;
use crate::progression::ProgressionDigest;
use crate::stats::StatRules;

/// Bumped when the canonical ENCODING or the field set changes in a way that
/// is not itself a rules change. Written first into every canonical stream, so
/// an encoding change can never be mistaken for a rules change: both move the
/// digest, but only one of them moves it for every reality at once.
pub const RULESET_SCHEMA_VERSION: u32 = 5;

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
    /// break `RLS-A13`. Refusing it belongs on the path that WRITES the pin —
    /// the loader — and that path does not exist yet (`PGN-R2`);
    /// `an_empty_table_must_never_be_pinned_and_nothing_enforces_it_yet` is the
    /// asserted trigger that reds when it arrives.
    pub progression: Option<ProgressionDigest>,
}

// QTY-A12 (doc 35 §6.4) — see the rationale on `StatBlock` in
// `services/commit-service/src/stats.rs`.
//
// A ruleset is interned per reality, not per actor, so its budget is generous
// by comparison — but it is the struct L2 will grow (declared quantities, the
// ordinal table, the O(n^2) element interaction table which QTY-A6.1 places
// HERE and not on the actor). It also backs a claim with an expiry date:
// `digest()` recomputes BLAKE3 on every call and justifies that with "the whole
// artifact is ~200 bytes". Watch this number.
//
// REPIN LOG — each entry is a decision someone had to write down, which is the
// entire mechanism. The assertion is not here to forbid growth.
//
// * 216 -> 224, 2026-07-29 (`Q0a`), for `law_version` (QTY-D13). Four bytes of
//   field, eight of struct after alignment. It bit on the very next slice after
//   it was added, which is the only evidence that a guard works.
// * 224 -> 1280, 2026-07-29 (`Q1`), for `quantities: QuantityTable` — and this
//   is the growth the paragraph above PREDICTED BY NAME. A 32-entry table of
//   32-byte identifiers is ~1 KB.
//
//   **Why that is affordable here and would not be on `Actor`:** QTY-A6.1 —
//   `O(n)` per ACTOR, `O(n²)` per RULESET. A `Ruleset` is interned once per
//   reality; ten thousand resident actors pay nothing for it. The same 1 KB on
//   `Actor` would be 10 MB and would be the exact mistake chaos made, where a
//   `[[f64;50];50]` interaction matrix sat INLINE on every actor and consumed
//   47 % of the struct.
//
//   **Boxing the table to keep the number small is FORBIDDEN.** That is
//   `QTY-A6 ⊥ QTY-A12` (non-vacuity register row 6): a heap pointer makes
//   `size_of` 16 bytes for every `n`, so this assertion would compile, always
//   pass, and never be able to fire again — for every future slice, not just
//   this one.
//
// * 1280 -> 2312, 2026-07-30 (`Q2`), for `resources: ResourceTable` — 32 rows
//   of a 32-byte `ResourceDecl`, plus its length. Measured, not estimated.
//
//   `ResourceDecl` is 32 B rather than the ~20 its fields sum to, because
//   `CeilingBinding::Slot(StatSlot)` inherits `StatSlot`'s `#[repr(usize)]`
//   8-byte alignment. Storing the slot as a bare `u8` would recover ~256 B
//   across the table and was NOT done: it would put an untyped ordinal in the
//   hashed bytes with nothing checking it against the enum, which is precisely
//   the drift `slots.rs` exists to prevent — and 256 B on a struct interned
//   ONCE PER REALITY is not worth buying with an untyped index.
//
//   **The paragraph above about `digest()` and "~200 bytes" is now stale, and
//   the distinction it glosses matters more than the number.** The STRUCT is
//   2.3 KB; the ENCODED bytes are not, because only `0..n` is written. A
//   reality declaring no pools encodes one extra length prefix over Q1 — four
//   bytes — and BLAKE3 hashes what is encoded, not what is resident. Watch the
//   encoded size, which is what `digest()` actually pays for.
// * 2312 -> 2344, 2026-07-30 (`S-1b`), for `progression: Option<ProgressionDigest>`.
//   Measured by probe, not estimated: `Option<[u8; 32]>` is 33 bytes and
//   `Ruleset` aligns to 8, so 2312 + 33 rounds to 2344.
//
//   **This is the whole reason progression is a POINTER and not a table.** The
//   old bound was `<= 2312` and `size_of` was EXACTLY 2312 — zero headroom,
//   which a bite-test confirmed (`<= 2311` fails to compile). Inlining even one
//   `TierDecl` was never on the table: `PROG_001` §5.6's worked example is 24
//   tiers in one kind, and a `TierDecl` transitively owns `String`/`Vec`/
//   `HashMap`, so it can never be `Copy`, never be `const`-constructed, and
//   cannot be measured by `size_of` AT ALL — the `QTY-A6 ⊥ QTY-A12` trap. 33
//   bytes of pointer buys a table of unbounded shape without giving up the
//   property this assertion exists to hold.
const _: () = assert!(core::mem::size_of::<Ruleset>() <= 2344);

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
            progression: None,
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
        let Self { schema_version, law_version, combat, stats, quantities, resources, progression } =
            self;
        c.u32(*schema_version);
        c.u32(*law_version);
        combat.canon(c);
        stats.canon(c);
        quantities.canon(c);
        resources.canon(c);
        crate::ruleset_codec::canon_progression(c, progression);
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
