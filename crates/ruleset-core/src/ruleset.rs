//! The resolved ruleset and its content digest (RLS-A13).

use sim_core::RulesetDigest;

use crate::canon::{Canon, CanonEncode, CanonError, CanonReader};
use crate::combat::CombatRules;
use crate::provenance::{Provenance, RulesetEpoch};
use crate::quantity::QuantityTable;
use crate::stats::StatRules;

/// Bumped when the canonical ENCODING or the field set changes in a way that
/// is not itself a rules change. Written first into every canonical stream, so
/// an encoding change can never be mistaken for a rules change: both move the
/// digest, but only one of them moves it for every reality at once.
pub const RULESET_SCHEMA_VERSION: u32 = 3;

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
const _: () = assert!(core::mem::size_of::<Ruleset>() <= 1280);

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
    const CANON_DOMAIN: &'static str = "loreweave.ruleset.v1";

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

    /// Decode, and report WHICH schema version the bytes were written at
    /// (QTY-A11).
    ///
    /// The returned `Ruleset` is always in the CURRENT shape — upcast if the
    /// artifact was older — so callers never branch on layout. The version is
    /// returned separately because one caller genuinely needs it:
    /// [`RulesetStore::get`] verifies content against name by RE-ENCODING, and
    /// it must re-encode at the artifact's own version or every older artifact
    /// looks corrupt.
    ///
    /// ## Why this is a dispatch and not a tolerant read
    ///
    /// The refusal this replaces carried the right reasoning and it is kept:
    /// *reading a v2 artifact with v1 field offsets would be reinterpretation of
    /// the worst kind — silent, and numerically plausible.* So a version NEWER
    /// than this engine is still a refusal; only versions whose layout is frozen
    /// in code may be read, and each is read at its own offsets.
    ///
    /// The first draft of QTY-A11 said something else — accept a short array and
    /// fill the tail — and that was **self-defeating**: `get` re-digests the
    /// DECODED value, so a widened decode re-encodes to different bytes and the
    /// store rejects its own artifact. The axiom written to stop a reality
    /// becoming `Unloadable` would have made every reality `Unloadable` on the
    /// first slot addition.
    pub fn from_canon_bytes_versioned(bytes: &[u8]) -> Result<(Self, u32), CanonError> {
        let mut r = CanonReader::new(bytes, Self::CANON_DOMAIN)?;
        let schema_version = r.u32()?;
        if !(SCHEMA_VERSION_OLDEST..=RULESET_SCHEMA_VERSION).contains(&schema_version) {
            return Err(CanonError::UnknownSchemaVersion {
                found: schema_version,
                known: RULESET_SCHEMA_VERSION,
            });
        }

        // v1 had no `law_version`. Reading zero here would be a guess; the
        // NAMED constant says the artifact makes no claim (see its docs).
        let law_version = if schema_version >= 2 { r.u32()? } else { LAW_VERSION_UNVERSIONED };

        let combat = CombatRules::decode(&mut r)?;
        let stats = StatRules::decode(&mut r)?;
        // v1 and v2 predate L2 entirely. An artifact from before Q1 declared
        // nothing, and `EMPTY` states that rather than guessing it.
        let quantities =
            if schema_version >= 3 { QuantityTable::decode(&mut r)? } else { QuantityTable::EMPTY };
        r.finish()?;

        // Upcast: the value handed back is always the current shape. Note it
        // does NOT adopt the current `LAW_VERSION` — an old artifact ran under
        // whatever laws it ran under, and overwriting that would erase the one
        // fact this field exists to record.
        let upcast =
            Self { schema_version: RULESET_SCHEMA_VERSION, law_version, combat, stats, quantities };
        Ok((upcast, schema_version))
    }

    /// Encode at a SPECIFIC schema version, for verification of a stored
    /// artifact against the name it is filed under.
    ///
    /// `None` for a version this engine has no codec for. The round-trip
    /// property every frozen version must satisfy —
    /// `encode_at(v, decode(b)) == b` for any `b` written at `v` — is what makes
    /// [`Self::digest_at`] meaningful, and it holds only while an upcast is
    /// purely ADDITIVE: a field with no representation at `v` is simply not
    /// written there. A future upcast that CHANGED an existing field would break
    /// it, and that is the signature of a behavioural change (QTY-A10(b)), which
    /// is supposed to be loud.
    pub fn canon_bytes_at(&self, version: u32) -> Option<Vec<u8>> {
        if !(SCHEMA_VERSION_OLDEST..=RULESET_SCHEMA_VERSION).contains(&version) {
            return None;
        }
        let mut c = Canon::new(Self::CANON_DOMAIN);
        // EXHAUSTIVE destructuring, same discipline as `canon` — a new field
        // must be considered here too, if only to decide it is not written at
        // an older version.
        let Self { schema_version: _, law_version, combat, stats, quantities } = self;
        c.u32(version);
        if version >= 2 {
            c.u32(*law_version);
        }
        combat.canon(&mut c);
        stats.canon(&mut c);
        if version >= 3 {
            quantities.canon(&mut c);
        }
        Some(c.finish())
    }

    /// The digest this ruleset WOULD have if written at `version`.
    ///
    /// For the current version this equals [`Self::digest`]. For an older one it
    /// reproduces the digest the artifact was originally filed under, which is
    /// exactly what a content-addressed store needs to check a name it did not
    /// choose.
    pub fn digest_at(&self, version: u32) -> Option<RulesetDigest> {
        self.canon_bytes_at(version)
            .map(|b| RulesetDigest(*blake3::hash(&b).as_bytes()))
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
        let Self { schema_version, law_version, combat, stats, quantities } = self;
        c.u32(*schema_version);
        c.u32(*law_version);
        combat.canon(c);
        stats.canon(c);
        quantities.canon(c);
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
