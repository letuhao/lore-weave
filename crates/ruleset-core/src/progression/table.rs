//! The collection, its canonical encoding, and its own digest.
//!
//! Split from [`super`] on the same line `resource/` was: *what a declaration
//! IS* there, *how a set of them is stored and hashed* here.
//!
//! ## This table has a digest of its own
//!
//! Unlike every other declared table in this crate, these bytes are **not**
//! inside `Ruleset`'s encoding. `Ruleset` will carry
//! `progression_digest: [u8; 32]` and the bytes live in a content-addressed
//! store (`PGN-R1`). So the digest computed here is the *content address*, and
//! it is what makes an edit to a tier ladder move the reality's ruleset digest
//! — which is what lets `Q0b B3`'s epoch switch cover a progression change with
//! no second version axis and no new binding column.

use crate::canon::{Canon, CanonError, CanonReader};

use super::{
    BodyOrSoul, BreakthroughCondition, CapRule, CurveKind, Derivation, ProgressionKindDecl,
    ProgressionDigest, ProgressionType, TierDecl, WithinTierCurve,
    MAX_DECLARED_PROGRESSION_KINDS, MAX_TIERS_PER_KIND,
};

const DOMAIN: &str = "lw.ruleset.progression.v1";

/// Every progression kind a reality declares, in **quantity-ordinal order**.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct ProgressionTable {
    rows: Vec<ProgressionKindDecl>,
}

/// Why a set of declarations was refused at construction.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ProgressionTableError {
    /// More kinds than the ordinal space holds.
    TooMany { found: usize, capacity: usize },
    /// Two rows for one quantity ordinal.
    ///
    /// Refused rather than deduped, the same call
    /// `QuantityError::Duplicate` and `ResourceError::Duplicate` make: a silent
    /// collapse hides which layer's declaration won.
    Duplicate { ordinal: u16 },
}

impl core::fmt::Display for ProgressionTableError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            Self::TooMany { found, capacity } => write!(
                f,
                "{found} declared progression kinds exceeds this engine's capacity of \
                 {capacity}. Raising MAX_DECLARED_PROGRESSION_KINDS is a code change and \
                 moves no existing digest - only 0..n is encoded"
            ),
            Self::Duplicate { ordinal } => write!(
                f,
                "two progression kinds declared for quantity ordinal {ordinal}. Refused \
                 rather than deduped: a silent collapse would hide which layer's \
                 declaration won"
            ),
        }
    }
}

impl std::error::Error for ProgressionTableError {}

impl ProgressionTable {
    /// The engine declares nothing. Every reality that predates `S-1` resolves
    /// to exactly this, so their behaviour is unchanged.
    pub const EMPTY: Self = Self { rows: Vec::new() };

    pub fn len(&self) -> usize {
        self.rows.len()
    }

    pub fn is_empty(&self) -> bool {
        self.rows.is_empty()
    }

    pub fn rows(&self) -> &[ProgressionKindDecl] {
        &self.rows
    }

    /// The kind declared for `ordinal`, if any. Most declared quantities are
    /// not progression kinds.
    pub fn for_quantity(&self, ordinal: u16) -> Option<&ProgressionKindDecl> {
        self.rows.iter().find(|r| r.quantity == ordinal)
    }

    /// Build a table from authored rows.
    ///
    /// **Sorts into ordinal order**, so the encoding is canonical without a sort
    /// at digest time and two files differing only in the order they list kinds
    /// produce the same digest. If this sorted at `canon()` instead, a reformat
    /// of a TOML file would strand a running reality — the exact property
    /// `Q2 B1` pinned for resources.
    ///
    /// Structural legality (the `CapRule` × `CurveKind` matrix, tier ordering,
    /// `derives_from` targets) is [`super::validate`]'s job, not this one:
    /// construction needs the quantity table to check anything real, and
    /// mixing "is this set well-formed" with "does it agree with its ruleset"
    /// would give one function two failure surfaces.
    pub fn declare(
        mut rows: Vec<ProgressionKindDecl>,
    ) -> Result<Self, ProgressionTableError> {
        if rows.len() > MAX_DECLARED_PROGRESSION_KINDS {
            return Err(ProgressionTableError::TooMany {
                found: rows.len(),
                capacity: MAX_DECLARED_PROGRESSION_KINDS,
            });
        }
        rows.sort_by_key(|r| r.quantity);
        for pair in rows.windows(2) {
            if pair[0].quantity == pair[1].quantity {
                return Err(ProgressionTableError::Duplicate { ordinal: pair[0].quantity });
            }
        }
        Ok(Self { rows })
    }

    /// The content address of these bytes.
    pub fn digest(&self) -> ProgressionDigest {
        ProgressionDigest(*blake3::hash(&self.canon_bytes()).as_bytes())
    }

    pub fn canon_bytes(&self) -> Vec<u8> {
        let mut c = Canon::new(DOMAIN);
        self.canon(&mut c);
        c.finish()
    }

    pub(crate) fn canon(&self, c: &mut Canon) {
        c.seq_len(self.rows.len());
        for r in &self.rows {
            c.u32(u32::from(r.quantity));
            c.u8(r.progression_type as u8);
            c.u8(r.body_or_soul as u8);
            canon_curve(c, &r.curve);
            c.seq_len(r.tiers.len());
            for t in &r.tiers {
                c.u8(t.tier_index);
                c.u64(t.tier_max);
                canon_within(c, &t.within_tier_curve);
                c.u8(t.breakthrough as u8);
                c.u64(t.initial_value_on_advance);
            }
            canon_cap(c, &r.cap_rule);
            c.u64(r.initial_value);
            // Option is encoded as a presence byte, never as a sentinel value:
            // tier 0 is a legal initial tier and 0 is also the obvious "none".
            match r.initial_tier {
                Some(t) => {
                    c.u8(1);
                    c.u8(t);
                }
                None => c.u8(0),
            }
            match &r.derives_from {
                Some(d) => {
                    c.u8(1);
                    c.u32(u32::from(d.source_quantity));
                    c.u32(d.rate_factor_milli);
                }
                None => c.u8(0),
            }
        }
    }

    pub fn decode(buf: &[u8]) -> Result<Self, CanonError> {
        let mut r = CanonReader::new(buf, DOMAIN)?;
        let out = Self::decode_from(&mut r)?;
        r.finish()?;
        Ok(out)
    }

    pub(crate) fn decode_from(r: &mut CanonReader<'_>) -> Result<Self, CanonError> {
        let n = r.u32()? as usize;
        if n > MAX_DECLARED_PROGRESSION_KINDS {
            return Err(CanonError::LengthMismatch {
                field: "progression.rows",
                expected: MAX_DECLARED_PROGRESSION_KINDS,
                found: n,
            });
        }
        let mut rows = Vec::with_capacity(n);
        let mut prev: Option<u16> = None;
        for _ in 0..n {
            let raw = r.u32()?;
            let quantity = u16::try_from(raw).map_err(|_| CanonError::LengthMismatch {
                field: "progression.quantity",
                expected: usize::from(u16::MAX),
                found: raw as usize,
            })?;
            // Strictly ascending. `declare` guarantees it on the write side, so
            // a buffer that violates it was not produced by this engine — and
            // accepting it would let a re-encode produce different bytes from
            // what we read, which breaks the store's digest-verify-on-read.
            if let Some(p) = prev {
                if quantity <= p {
                    return Err(CanonError::LengthMismatch {
                        field: "progression.quantity: rows must be strictly ascending",
                        expected: usize::from(p) + 1,
                        found: usize::from(quantity),
                    });
                }
            }
            prev = Some(quantity);

            let progression_type = match r.u8()? {
                0 => ProgressionType::Attribute,
                1 => ProgressionType::Skill,
                2 => ProgressionType::Stage,
                v => return Err(bad("progression.progression_type", v, 2)),
            };
            let body_or_soul = match r.u8()? {
                0 => BodyOrSoul::Body,
                1 => BodyOrSoul::Soul,
                2 => BodyOrSoul::Both,
                v => return Err(bad("progression.body_or_soul", v, 2)),
            };
            let curve = decode_curve(r)?;

            let tn = r.u32()? as usize;
            if tn > MAX_TIERS_PER_KIND {
                return Err(CanonError::LengthMismatch {
                    field: "progression.tiers",
                    expected: MAX_TIERS_PER_KIND,
                    found: tn,
                });
            }
            let mut tiers = Vec::with_capacity(tn);
            for i in 0..tn {
                let tier_index = r.u8()?;
                if usize::from(tier_index) != i {
                    return Err(bad("progression.tier_index", tier_index, i));
                }
                let tier_max = r.u64()?;
                let within_tier_curve = decode_within(r)?;
                let breakthrough = match r.u8()? {
                    0 => BreakthroughCondition::AtMax,
                    1 => BreakthroughCondition::AuthorOnly,
                    v => return Err(bad("progression.breakthrough", v, 1)),
                };
                let initial_value_on_advance = r.u64()?;
                tiers.push(TierDecl {
                    tier_index,
                    tier_max,
                    within_tier_curve,
                    breakthrough,
                    initial_value_on_advance,
                });
            }

            let cap_rule = decode_cap(r)?;
            let initial_value = r.u64()?;
            let initial_tier = match r.u8()? {
                0 => None,
                1 => Some(r.u8()?),
                v => return Err(bad("progression.initial_tier.present", v, 1)),
            };
            let derives_from = match r.u8()? {
                0 => None,
                1 => {
                    let src = r.u32()?;
                    Some(Derivation {
                        source_quantity: u16::try_from(src).map_err(|_| {
                            CanonError::LengthMismatch {
                                field: "progression.derives_from.source",
                                expected: usize::from(u16::MAX),
                                found: src as usize,
                            }
                        })?,
                        rate_factor_milli: r.u32()?,
                    })
                }
                v => return Err(bad("progression.derives_from.present", v, 1)),
            };

            rows.push(ProgressionKindDecl {
                quantity,
                progression_type,
                body_or_soul,
                curve,
                tiers,
                cap_rule,
                initial_value,
                initial_tier,
                derives_from,
            });
        }
        Ok(Self { rows })
    }
}

/// An unknown discriminant is a REFUSAL, not a default.
///
/// Reuses `LengthMismatch` rather than adding a `BadEnum` variant, because
/// `resource/table.rs::slot_from_u32` already made this exact call for the same
/// reason and a second spelling of "this byte is not a legal variant" is a
/// second thing that can drift. `expected` carries the highest legal
/// discriminant, so the message still says what WOULD have been readable.
fn bad(field: &'static str, value: u8, highest: usize) -> CanonError {
    CanonError::LengthMismatch { field, expected: highest, found: usize::from(value) }
}

fn canon_curve(c: &mut Canon, k: &CurveKind) {
    match k {
        CurveKind::Linear { rate_milli } => {
            c.u8(0);
            c.u32(*rate_milli);
        }
        CurveKind::Log { base_rate_milli, difficulty_milli } => {
            c.u8(1);
            c.u32(*base_rate_milli);
            c.u32(*difficulty_milli);
        }
        CurveKind::Stage => c.u8(2),
    }
}

fn decode_curve(r: &mut CanonReader<'_>) -> Result<CurveKind, CanonError> {
    Ok(match r.u8()? {
        0 => CurveKind::Linear { rate_milli: r.u32()? },
        1 => CurveKind::Log { base_rate_milli: r.u32()?, difficulty_milli: r.u32()? },
        2 => CurveKind::Stage,
        v => return Err(bad("progression.curve", v, 2)),
    })
}

fn canon_within(c: &mut Canon, k: &WithinTierCurve) {
    match k {
        WithinTierCurve::Linear { rate_milli } => {
            c.u8(0);
            c.u32(*rate_milli);
        }
        WithinTierCurve::Log { base_rate_milli, difficulty_milli } => {
            c.u8(1);
            c.u32(*base_rate_milli);
            c.u32(*difficulty_milli);
        }
    }
}

fn decode_within(r: &mut CanonReader<'_>) -> Result<WithinTierCurve, CanonError> {
    Ok(match r.u8()? {
        0 => WithinTierCurve::Linear { rate_milli: r.u32()? },
        1 => WithinTierCurve::Log { base_rate_milli: r.u32()?, difficulty_milli: r.u32()? },
        v => return Err(bad("progression.within_tier_curve", v, 1)),
    })
}

fn canon_cap(c: &mut Canon, k: &CapRule) {
    match k {
        CapRule::SoftCap { cap } => {
            c.u8(0);
            c.u64(*cap);
        }
        CapRule::HardCap { cap } => {
            c.u8(1);
            c.u64(*cap);
        }
        CapRule::TierBased => c.u8(2),
        CapRule::Unbounded => c.u8(3),
    }
}

fn decode_cap(r: &mut CanonReader<'_>) -> Result<CapRule, CanonError> {
    Ok(match r.u8()? {
        0 => CapRule::SoftCap { cap: r.u64()? },
        1 => CapRule::HardCap { cap: r.u64()? },
        2 => CapRule::TierBased,
        3 => CapRule::Unbounded,
        v => return Err(bad("progression.cap_rule", v, 3)),
    })
}
