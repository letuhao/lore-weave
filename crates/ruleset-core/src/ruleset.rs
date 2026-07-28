//! The resolved ruleset and its content digest (RLS-A13).

use sim_core::RulesetDigest;

use crate::canon::{Canon, CanonEncode, CanonError, CanonReader};
use crate::combat::CombatRules;
use crate::provenance::{Provenance, RulesetEpoch};
use crate::stats::StatRules;

/// Bumped when the canonical ENCODING or the field set changes in a way that
/// is not itself a rules change. Written first into every canonical stream, so
/// an encoding change can never be mistaken for a rules change: both move the
/// digest, but only one of them moves it for every reality at once.
pub const RULESET_SCHEMA_VERSION: u32 = 1;

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
    pub combat: CombatRules,
    pub stats: StatRules,
}

impl Ruleset {
    /// The priority-0 `engine_default` layer (RLS-D2), resolved with no
    /// higher layer present.
    pub const fn engine_default() -> Self {
        Self {
            schema_version: RULESET_SCHEMA_VERSION,
            combat: CombatRules::engine_default(),
            stats: StatRules::engine_default(),
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
        let mut r = CanonReader::new(bytes, Self::CANON_DOMAIN)?;
        let schema_version = r.u32()?;
        if schema_version != RULESET_SCHEMA_VERSION {
            return Err(CanonError::UnknownSchemaVersion {
                found: schema_version,
                known: RULESET_SCHEMA_VERSION,
            });
        }
        let combat = CombatRules::decode(&mut r)?;
        let stats = StatRules::decode(&mut r)?;
        r.finish()?;
        Ok(Self { schema_version, combat, stats })
    }
}

impl CanonEncode for Ruleset {
    fn canon(&self, c: &mut Canon) {
        // EXHAUSTIVE destructuring, no `..` — see `CanonEncode`.
        let Self { schema_version, combat, stats } = self;
        c.u32(*schema_version);
        combat.canon(c);
        stats.canon(c);
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
