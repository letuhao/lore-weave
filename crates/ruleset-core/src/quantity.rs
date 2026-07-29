//! Q1 — L2 declared quantities: identities an author invents, ordinals the
//! engine assigns, both pinned inside the hashed ruleset.
//!
//! ## What this layer is for
//!
//! [Doc 35](../../../docs/03_planning/LLM_MMO_RPG/35_quantity_architecture.md)
//! §3: L1 (roles + derived stats) is **closed in the binary** and correctly so —
//! `MaxHp` is arithmetic, not content. L2 is the layer *beneath* it: the
//! quantities a reality declares for itself. A wuxia world declares `qi`, a
//! sci-fi world declares `heat`, and **the engine has never heard of either**.
//!
//! ## QTY-A5 — ordinals are ASSIGNED, never authored
//!
//! > *"…monotonic; never reused on removal; and the assignment table is INSIDE
//! > the hashed ruleset."*
//!
//! The last clause is the one that fixes a real defect in the prior project,
//! which derived ordinals from a `sort()` over whatever config files were
//! present — so **adding one element file renumbered every element after it**,
//! with no persisted id→ordinal map anywhere. Reproducible for one snapshot,
//! not stable across edits.
//!
//! Putting the table in the hashed bytes makes an ordinal shift *a different
//! ruleset with a different digest*, which the early-binding machinery already
//! refuses to apply to a live reality.
//!
//! ## QTY-A6 — fixed width, declared identities
//!
//! The width [`MAX_DECLARED_QUANTITIES`] is a **compile-time** constant; `n` is
//! per reality and lives in the hashed bytes. A reality uses the prefix `0..n`.
//!
//! `const fn` forced this shape and it is the shape A6 asked for: `engine_default()`
//! is `const`, a `Vec` cannot be, so the table is an array. **Only `0..n` is
//! encoded**, which buys two properties worth stating:
//!
//! * the unused tail cannot influence the digest;
//! * **raising `N` later does not move any existing digest** — `N` is genuinely
//!   in the binary. Encoding the full array would have made a capacity bump a
//!   rules change for every reality in existence.
//!
//! ## Why a linear scan and not a map
//!
//! [`QuantityTable::ordinal_of`] scans. At `N = 32` that is a handful of
//! comparisons, run **once at `create_reality`** and never inside a step — so a
//! `BTreeMap<String, u16>` would buy nothing, allocate, and land squarely in
//! `hot-path-gate`'s sights, where the honest answer would have been a pragma
//! explaining why the map is cold. **No map, no pragma, no explaining.**
//!
//! ## Why the identifier is ASCII
//!
//! These bytes are **hashed**. Unicode offers several byte sequences that
//! render identically (NFC vs NFD, and worse), so an unrestricted identifier
//! would let two authors write what looks like the same name and produce two
//! different digests — or, through a normalizing editor, silently change a
//! reality's digest on a whitespace-only save. The identifier is therefore a
//! machine key, `[a-z][a-z0-9_]*`, exactly like the `code` column pattern used
//! elsewhere in the platform.
//!
//! **This is not an English-only rule** (see the Multilingual standard): the
//! human-readable label for `qi` — *khí*, 氣, *ki* — is display content and
//! belongs with the reality's localized text, not in the digest. Separating the
//! machine key from the display name is what lets the label be translated
//! without moving a single reality's ruleset digest.

use crate::canon::{Canon, CanonError, CanonReader};

/// `N` — the compile-time ordinal capacity (QTY-A6).
///
/// Chosen at 32 because doc 35 §4.2 measured the per-actor cost of the array
/// this ordinal space will index in `Q2`: `[i32; 32]` puts `Actor` at ≈280 B
/// against 192 B today, and `[i32; 64]` at ≈408 B. Thirty-two declared
/// quantities is already far past what any of the seven worked systems needs.
///
/// Raising it is cheap and **does not move any existing digest** — only `0..n`
/// is encoded.
pub const MAX_DECLARED_QUANTITIES: usize = 32;

/// The longest identifier an author may declare.
pub const MAX_QUANTITY_NAME_LEN: usize = 32;

/// Why a declared quantity was refused.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum QuantityError {
    /// More declarations than the binary's ordinal capacity (QTY-A6).
    TooMany { found: usize, capacity: usize },
    /// Empty, over-long, or not `[a-z][a-z0-9_]*`.
    BadName { name: String, reason: &'static str },
    /// Two declarations of the same identity. Refused rather than deduped:
    /// silently collapsing them would hide which layer's intent won.
    Duplicate { name: String },
}

impl core::fmt::Display for QuantityError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            Self::TooMany { found, capacity } => write!(
                f,
                "{found} declared quantities exceeds this engine's capacity of {capacity} \
                 (QTY-A6: the width is a compile-time constant). Raising \
                 MAX_DECLARED_QUANTITIES is a code change and moves no existing digest"
            ),
            Self::BadName { name, reason } => write!(
                f,
                "declared quantity `{name}` is not a valid identifier: {reason}. The name is a \
                 MACHINE key that gets hashed; its human-readable label is localized content \
                 and lives elsewhere"
            ),
            Self::Duplicate { name } => write!(
                f,
                "declared quantity `{name}` appears twice. Refused rather than deduped: a \
                 silent collapse would hide which layer's declaration won"
            ),
        }
    }
}

/// One declared identity: an inline, fixed-capacity ASCII key.
///
/// Inline rather than `String` because [`crate::Ruleset::engine_default`] is a
/// `const fn` — and because a heap pointer here would put the payload where
/// `size_of` cannot see it, which is the `QTY-A6 ⊥ QTY-A12` trap the red team
/// caught once already.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct QuantityName {
    bytes: [u8; MAX_QUANTITY_NAME_LEN],
    len: u8,
}

impl QuantityName {
    /// The unused tail of the table. Never encoded — only `0..n` is.
    pub const EMPTY: Self = Self { bytes: [0; MAX_QUANTITY_NAME_LEN], len: 0 };

    /// Validate and intern an identifier.
    pub fn new(name: &str) -> Result<Self, QuantityError> {
        let bad = |reason| QuantityError::BadName { name: name.to_string(), reason };
        if name.is_empty() {
            return Err(bad("it is empty"));
        }
        if name.len() > MAX_QUANTITY_NAME_LEN {
            return Err(bad("it is longer than 32 bytes"));
        }
        let b = name.as_bytes();
        if !b[0].is_ascii_lowercase() {
            return Err(bad("it must start with a lowercase ASCII letter"));
        }
        if !b.iter().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || *c == b'_') {
            return Err(bad("it may contain only [a-z0-9_]"));
        }
        let mut bytes = [0u8; MAX_QUANTITY_NAME_LEN];
        bytes[..b.len()].copy_from_slice(b);
        Ok(Self { bytes, len: b.len() as u8 })
    }

    pub fn as_bytes(&self) -> &[u8] {
        &self.bytes[..self.len as usize]
    }

    pub fn as_str(&self) -> &str {
        // Validated ASCII on construction, and decode re-validates.
        core::str::from_utf8(self.as_bytes()).unwrap_or("<invalid>")
    }
}

/// The per-reality declared set: `n` identities, ordinal = index.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct QuantityTable {
    n: u16,
    names: [QuantityName; MAX_DECLARED_QUANTITIES],
}

impl QuantityTable {
    /// The engine declares nothing. Every reality that predates `Q1` resolves to
    /// exactly this, so their behaviour is unchanged.
    pub const EMPTY: Self =
        Self { n: 0, names: [QuantityName::EMPTY; MAX_DECLARED_QUANTITIES] };

    /// Assign ordinals to `names` **in the order given** (QTY-A5: assigned,
    /// never authored).
    ///
    /// The caller is the loader, which folds layers in ascending priority, so
    /// the order is deterministic: a quantity's ordinal is fixed by **where it
    /// first appears** across the merged stack, and a later layer re-declaring
    /// an existing name is a [`QuantityError::Duplicate`] rather than a silent
    /// renumber.
    pub fn assign(names: &[&str]) -> Result<Self, QuantityError> {
        if names.len() > MAX_DECLARED_QUANTITIES {
            return Err(QuantityError::TooMany {
                found: names.len(),
                capacity: MAX_DECLARED_QUANTITIES,
            });
        }
        let mut out = Self::EMPTY;
        for name in names {
            let q = QuantityName::new(name)?;
            if out.names[..out.n as usize].iter().any(|e| e == &q) {
                return Err(QuantityError::Duplicate { name: (*name).to_string() });
            }
            out.names[out.n as usize] = q;
            out.n += 1;
        }
        Ok(out)
    }

    /// Append one identity if it is not already declared (RLS-A4 `UnionByIdOverride`).
    ///
    /// `Ok(true)` = appended and given the next ordinal; `Ok(false)` = already
    /// declared, so nothing moved.
    ///
    /// **Re-declaring is a NO-OP, not an error, and that is what makes the merge
    /// a union.** A quantity carries no payload beyond its identity, so a higher
    /// layer "overriding" one has nothing to override — and refusing the re-
    /// declaration would stop a reality from restating a preset's `qi` while
    /// adding its own `fire`, which is the ordinary authoring shape.
    ///
    /// The important half is what this makes **inexpressible**: there is no
    /// remove. `AdditiveOnly` (RLS-A17) is therefore enforced BY CONSTRUCTION
    /// rather than by a validator that could be forgotten — a lower layer's
    /// declaration cannot be dropped by any higher one, because the merge has no
    /// verb for it.
    pub fn push(&mut self, name: &str) -> Result<bool, QuantityError> {
        let q = QuantityName::new(name)?;
        if self.names().iter().any(|e| e == &q) {
            return Ok(false);
        }
        if self.n as usize >= MAX_DECLARED_QUANTITIES {
            return Err(QuantityError::TooMany {
                found: self.n as usize + 1,
                capacity: MAX_DECLARED_QUANTITIES,
            });
        }
        self.names[self.n as usize] = q;
        self.n += 1;
        Ok(true)
    }

    pub fn len(&self) -> usize {
        self.n as usize
    }

    pub fn is_empty(&self) -> bool {
        self.n == 0
    }

    /// The declared identities, in ordinal order.
    pub fn names(&self) -> &[QuantityName] {
        &self.names[..self.n as usize]
    }

    /// Resolve an identity to its ordinal. Linear by design — see the module doc.
    pub fn ordinal_of(&self, name: &str) -> Option<u16> {
        self.names()
            .iter()
            .position(|q| q.as_str() == name)
            .map(|i| i as u16)
    }

    /// The identity an ordinal names, if the reality declared one.
    ///
    /// **`QTY-A14`: an ordinal is meaningless without its `(reality, digest)`.**
    /// This resolves against *one* table; a caller holding an ordinal from
    /// elsewhere must first prove the digest matches, or refuse the datum. The
    /// failure this prevents is silent: reality A's ordinal 3 (`qi`) read
    /// against reality B's table (`mana`) resolves *successfully* and grants the
    /// wrong thing forever.
    pub fn name_of(&self, ordinal: u16) -> Option<&QuantityName> {
        self.names().get(ordinal as usize)
    }

    /// Encode `0..n` — never the tail. See the module doc for why.
    pub(crate) fn canon(&self, c: &mut Canon) {
        c.seq_len(self.len());
        for q in self.names() {
            c.bytes(q.as_bytes());
        }
    }

    pub(crate) fn decode(r: &mut CanonReader<'_>) -> Result<Self, CanonError> {
        let n = r.u32()? as usize;
        if n > MAX_DECLARED_QUANTITIES {
            // Refuse rather than truncate. An artifact declaring more than this
            // binary can hold is not something to read a prefix of — the actor
            // arrays that index this space are `MAX_DECLARED_QUANTITIES` wide,
            // so a prefix read would silently drop identities that stored state
            // may already reference by ordinal.
            return Err(CanonError::LengthMismatch {
                field: "quantities",
                expected: MAX_DECLARED_QUANTITIES,
                found: n,
            });
        }
        let mut out = Self::EMPTY;
        for _ in 0..n {
            let raw = r.bytes()?;
            let name = core::str::from_utf8(raw)
                .ok()
                .and_then(|s| QuantityName::new(s).ok())
                .ok_or(CanonError::LengthMismatch {
                    field: "quantities.name",
                    expected: 0,
                    found: raw.len(),
                })?;
            out.names[out.n as usize] = name;
            out.n += 1;
        }
        Ok(out)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ordinals_follow_declaration_order_and_resolve_both_ways() {
        let t = QuantityTable::assign(&["qi", "mana", "heat"]).unwrap();
        assert_eq!(t.ordinal_of("qi"), Some(0));
        assert_eq!(t.ordinal_of("heat"), Some(2));
        assert_eq!(t.name_of(1).unwrap().as_str(), "mana");
        assert_eq!(t.ordinal_of("nope"), None, "an undeclared name has no ordinal");
        assert_eq!(t.name_of(3), None, "an ordinal past `n` names nothing");
    }

    #[test]
    fn the_engine_declares_nothing_and_that_is_the_identity() {
        assert!(QuantityTable::EMPTY.is_empty());
        assert_eq!(QuantityTable::assign(&[]).unwrap(), QuantityTable::EMPTY);
    }

    #[test]
    fn capacity_is_refused_not_truncated() {
        let many: Vec<String> = (0..MAX_DECLARED_QUANTITIES + 1).map(|i| format!("q{i}")).collect();
        let refs: Vec<&str> = many.iter().map(String::as_str).collect();
        assert!(matches!(
            QuantityTable::assign(&refs),
            Err(QuantityError::TooMany { found, capacity })
                if found == MAX_DECLARED_QUANTITIES + 1 && capacity == MAX_DECLARED_QUANTITIES
        ));
        // …and exactly at capacity is legal, so the refusal is a boundary and
        // not an off-by-one that forbids the last usable ordinal.
        let ok: Vec<&str> = refs[..MAX_DECLARED_QUANTITIES].to_vec();
        assert_eq!(QuantityTable::assign(&ok).unwrap().len(), MAX_DECLARED_QUANTITIES);
    }

    #[test]
    fn a_duplicate_is_refused_rather_than_deduped() {
        assert!(matches!(
            QuantityTable::assign(&["qi", "mana", "qi"]),
            Err(QuantityError::Duplicate { name }) if name == "qi"
        ));
    }

    /// Each rule refuses its own bad name, and a good name is accepted — the
    /// second half is what stops this being a validator that refuses everything.
    #[test]
    fn the_identifier_charset_is_closed() {
        for (name, why) in [
            ("", "empty"),
            ("Qi", "uppercase"),
            ("1qi", "leading digit"),
            ("_qi", "leading underscore"),
            ("qi-pool", "hyphen"),
            ("qi pool", "space"),
            ("khí", "non-ASCII"),
            ("氣", "CJK"),
        ] {
            assert!(
                QuantityName::new(name).is_err(),
                "`{name}` ({why}) must be refused: these bytes are HASHED, and Unicode offers \
                 several byte sequences that render identically"
            );
        }
        for good in ["qi", "spirit_energy", "q0", "a"] {
            assert!(QuantityName::new(good).is_ok(), "`{good}` must be accepted");
        }
        let too_long = "q".repeat(MAX_QUANTITY_NAME_LEN + 1);
        assert!(QuantityName::new(&too_long).is_err());
        assert!(QuantityName::new(&"q".repeat(MAX_QUANTITY_NAME_LEN)).is_ok());
    }
}
