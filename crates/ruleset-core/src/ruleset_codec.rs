//! The VERSIONED codec: how a `Ruleset` is read back at the version it was
//! written at, and re-encoded to exactly those bytes.
//!
//! Split from [`crate::ruleset`] at `IMP-D3`'s 400-line ceiling, on the seam
//! `Q1` already used for `digest.rs` → `versioning.rs`: **what is IN the bytes**
//! lives there, **the decoder that reads them** lives here. `CanonEncode for
//! Ruleset` stays with the struct because it is the single definition of
//! *current*; everything historical is here.
//!
//! The property this file exists to hold is `QTY-A11`'s:
//! `encode_at(v, decode(b)) == b` for any `b` written at `v`. It survives only
//! while an upcast is purely ADDITIVE — a field with no representation at `v` is
//! simply not written there. An upcast that CHANGED an existing field would
//! break it, and that is the signature of a behavioural change (`QTY-A10(b)`),
//! which is supposed to be loud.

use crate::canon::{Canon, CanonEncode, CanonError, CanonReader};
use crate::combat::CombatRules;
use crate::progression::ProgressionDigest;
use crate::quantity::QuantityTable;
use crate::resource::ResourceTable;
use crate::ruleset::{Ruleset, LAW_VERSION_UNVERSIONED, RULESET_SCHEMA_VERSION, SCHEMA_VERSION_OLDEST};
use crate::stats::StatRules;
use sim_core::RulesetDigest;

/// A presence byte, then the 32 bytes — never a zero sentinel, for the reason
/// on the field. Shared by `canon` and `canon_bytes_at` so the two cannot drift.
pub(crate) fn canon_progression(c: &mut Canon, p: &Option<ProgressionDigest>) {
    match p {
        Some(d) => {
            c.u8(1);
            c.bytes(&d.0);
        }
        None => c.u8(0),
    }
}

impl Ruleset {

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
        // v1..v3 predate declared pools. An artifact from before Q2 declared
        // none, and `EMPTY` states that rather than guessing it.
        let resources =
            if schema_version >= 4 { ResourceTable::decode(&mut r)? } else { ResourceTable::EMPTY };
        // v1..v4 predate the progression pin. An artifact from before S-1b
        // declared none, and `None` states that rather than guessing it.
        let progression = if schema_version >= 5 {
            match r.u8()? {
                0 => None,
                1 => {
                    let b = r.bytes()?;
                    let arr: [u8; 32] = b.try_into().map_err(|_| CanonError::LengthMismatch {
                        field: "progression digest",
                        expected: 32,
                        found: b.len(),
                    })?;
                    Some(ProgressionDigest(arr))
                }
                v => {
                    return Err(CanonError::LengthMismatch {
                        field: "progression presence byte",
                        expected: 1,
                        found: usize::from(v),
                    })
                }
            }
        } else {
            None
        };
        r.finish()?;

        // Upcast: the value handed back is always the current shape. Note it
        // does NOT adopt the current `LAW_VERSION` — an old artifact ran under
        // whatever laws it ran under, and overwriting that would erase the one
        // fact this field exists to record.
        let upcast = Self {
            schema_version: RULESET_SCHEMA_VERSION,
            law_version,
            combat,
            stats,
            quantities,
            resources,
            progression,
        };
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
        let Self {
            schema_version: _, law_version, combat, stats, quantities, resources, progression,
        } = self;
        c.u32(version);
        if version >= 2 {
            c.u32(*law_version);
        }
        combat.canon(&mut c);
        stats.canon(&mut c);
        if version >= 3 {
            quantities.canon(&mut c);
        }
        if version >= 4 {
            resources.canon(&mut c);
        }
        if version >= 5 {
            canon_progression(&mut c, progression);
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
