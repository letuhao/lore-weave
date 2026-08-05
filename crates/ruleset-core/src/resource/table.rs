//! The `Q2` pool table — the collection half of [`super`], split out when
//! `resource.rs` crossed its `IMP-D3` ceiling.
//!
//! The seam is real and not a line-count dodge: everything in the parent is a
//! DECLARATION (what a pool is, what values it may take, why `Defeat` is not
//! among them); everything here is the COLLECTION and its CODEC (ordering,
//! canonical encoding, the refusals a stored artifact can trigger). They change
//! for different reasons — a new pool field edits the parent, a schema version
//! edits this file.

use crate::canon::{Canon, CanonError, CanonReader};
use crate::slots::StatSlot;

use super::{CeilingBinding, EngineRole, RegenType, ResourceDecl, ResourceError, ZeroBehaviour,
            MAX_DECLARED_RESOURCES};

/// The first schema version whose rows carry [`ResourceDecl::role`].
///
/// Named rather than written as a literal `6` in three places, because
/// `QTY-A11`'s round-trip (`encode_at(v, decode(b)) == b`) holds only while the
/// encoder and the decoder agree on this number — and two literals that must
/// stay equal are two literals that can stop being equal.
const ROLE_SINCE: u32 = 6;

/// The declared pools of one reality, in the hashed bytes.
///
/// Ordered by `quantity` ordinal, which makes the encoding canonical without a
/// sort at digest time and makes a lookup a scan over `0..n` — the same
/// no-map-anywhere discipline `QuantityTable` follows, and for the same reason:
/// `QTY-A9` forbids a map iteration deciding anything, and `hot-path-gate`
/// forbids a string-keyed map in a step file.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ResourceTable {
    rows: [ResourceDecl; MAX_DECLARED_RESOURCES],
    n: u16,
}

/// The row an unused tail slot holds. Never encoded — only `0..n` is — so its
/// contents cannot reach a digest.
const TAIL: ResourceDecl = ResourceDecl {
    quantity: 0,
    min: 0,
    base: 0,
    ceiling: CeilingBinding::Fixed(0),
    regen_rate: 0,
    regen_type: RegenType::None,
    zero_behaviour: ZeroBehaviour::Clamp,
    role: EngineRole::None,
};

impl ResourceTable {
    /// A reality that declares no pools. The engine default.
    pub const EMPTY: Self = Self { rows: [TAIL; MAX_DECLARED_RESOURCES], n: 0 };

    pub fn len(&self) -> usize {
        self.n as usize
    }

    pub fn is_empty(&self) -> bool {
        self.n == 0
    }

    pub fn rows(&self) -> &[ResourceDecl] {
        &self.rows[..self.n as usize]
    }

    /// The pool declared for a quantity ordinal, if any.
    ///
    /// A scan, not a map: `n <= 32`, and this runs at resolve/spawn rather than
    /// inside a step. See `QuantityTable::ordinal_of` for the full argument.
    pub fn for_quantity(&self, ordinal: u16) -> Option<&ResourceDecl> {
        self.rows().iter().find(|r| r.quantity == ordinal)
    }

    /// **The pool an engine law reads** — `Q2`'s exit criterion, as a lookup.
    ///
    /// `None` when this reality bound no pool to the role, and the CALLER
    /// refuses: a law with no number must say so at boot, where an operator can
    /// read it, rather than pick a default and run a reality whose fights never
    /// end. [`declare`](Self::declare) guarantees at most one, so this cannot
    /// silently prefer a row.
    ///
    /// `EngineRole::None` is not exclusive and this deliberately returns the
    /// first such row rather than refusing: nothing asks for it, and a lookup
    /// that panics on an argument no caller passes is a check that cannot fail.
    pub fn by_role(&self, role: EngineRole) -> Option<&ResourceDecl> {
        self.rows().iter().find(|r| r.role == role)
    }

    /// Declare a pool. `declared_quantities` is the reality's `n` from
    /// [`crate::quantity::QuantityTable`], which is what makes
    /// [`ResourceError::UnknownQuantity`] checkable at all.
    pub fn declare(
        &mut self,
        row: ResourceDecl,
        declared_quantities: usize,
    ) -> Result<(), ResourceError> {
        if (row.quantity as usize) >= declared_quantities {
            return Err(ResourceError::UnknownQuantity {
                ordinal: row.quantity,
                declared: declared_quantities,
            });
        }
        if self.for_quantity(row.quantity).is_some() {
            return Err(ResourceError::Duplicate { ordinal: row.quantity });
        }
        // An exclusive role names ONE pool. Checked here rather than at
        // resolve, because `declare` is the single door every layer's rows come
        // through — a check on the resolved table would be one a Forge override
        // could route around.
        if row.role.is_exclusive()
            && let Some(first) = self.by_role(row.role)
        {
            return Err(ResourceError::RoleClaimedTwice {
                role: row.role,
                first: first.quantity,
                second: row.quantity,
            });
        }
        if self.n as usize >= MAX_DECLARED_RESOURCES {
            return Err(ResourceError::TooMany {
                found: self.n as usize + 1,
                capacity: MAX_DECLARED_RESOURCES,
            });
        }
        if row.base < row.min {
            return Err(ResourceError::BadBounds {
                ordinal: row.quantity,
                reason: "base is below min, so an actor would spawn already clamped",
            });
        }
        if let CeilingBinding::Fixed(max) = row.ceiling {
            if max < row.min {
                return Err(ResourceError::BadBounds {
                    ordinal: row.quantity,
                    reason: "the fixed ceiling is below min, so the pool has no legal value",
                });
            }
            if row.base > max {
                return Err(ResourceError::BadBounds {
                    ordinal: row.quantity,
                    reason: "base is above the fixed ceiling, so an actor would spawn clamped",
                });
            }
        }
        // Inserted in ordinal order so the encoding is canonical WITHOUT a sort
        // at digest time. A sort there would make the digest depend on the
        // sort's stability, which is one more thing to be right about forever.
        let at = self.rows().iter().position(|r| r.quantity > row.quantity).unwrap_or(self.len());
        let mut i = self.n as usize;
        while i > at {
            self.rows[i] = self.rows[i - 1];
            i -= 1;
        }
        self.rows[at] = row;
        self.n += 1;
        Ok(())
    }

    /// Encode at a SPECIFIC schema version — `QTY-A11`'s round-trip lives here.
    ///
    /// The version parameter exists because [`ResourceDecl::role`] arrived at
    /// v6: a v5 artifact's rows have no role byte, so re-encoding a decoded v5
    /// ruleset must not write one, or `RulesetStore::get` re-digests it and
    /// rejects the store's own artifact. That is the failure the codec's module
    /// doc calls *"self-defeating"*, and it is why this takes a version rather
    /// than always writing the current shape.
    pub(crate) fn canon_at(&self, c: &mut Canon, version: u32) {
        c.seq_len(self.len());
        for r in self.rows() {
            c.u32(r.quantity as u32);
            c.i32(r.min);
            c.i32(r.base);
            match r.ceiling {
                // The DISCRIMINANT is encoded, not just the payload. Without it
                // `Slot(0)` and `Fixed(0)` would hash identically while meaning
                // "bound to MaxHp" and "capped at zero" — a collision between a
                // working pool and a dead one.
                CeilingBinding::Slot(s) => {
                    c.u8(0);
                    c.u32(s as u32);
                }
                CeilingBinding::Fixed(v) => {
                    c.u8(1);
                    c.i32(v);
                }
            }
            c.i32(r.regen_rate);
            c.u8(r.regen_type as u8);
            c.u8(r.zero_behaviour as u8);
            if version >= ROLE_SINCE {
                c.u8(r.role as u8);
            }
        }
    }

    pub(crate) fn decode_at(r: &mut CanonReader<'_>, version: u32) -> Result<Self, CanonError> {
        let n = r.u32()? as usize;
        if n > MAX_DECLARED_RESOURCES {
            // Refuse rather than truncate, for the reason `QuantityTable`
            // gives: the actor arrays that index this space are fixed-width, so
            // a prefix read would silently drop pools that stored state may
            // already reference by ordinal.
            return Err(CanonError::LengthMismatch {
                field: "resources",
                expected: MAX_DECLARED_RESOURCES,
                found: n,
            });
        }
        let mut out = Self::EMPTY;
        let mut prev: Option<u16> = None;
        for _ in 0..n {
            let quantity = r.u32()? as u16;
            // STRICTLY ascending, checked on the way in. The encoder emits
            // ordinal order (see `declare`), so an artifact that is not sorted
            // was not written by this encoder — and accepting it would produce a
            // value whose re-encode differs from its own bytes, which
            // `RulesetStore::get` re-digests and would then reject as corrupt,
            // with a message about hashes rather than about order.
            if prev.is_some_and(|p| quantity <= p) {
                return Err(CanonError::LengthMismatch {
                    field: "resources: ordinals must be strictly ascending",
                    expected: prev.unwrap() as usize + 1,
                    found: quantity as usize,
                });
            }
            prev = Some(quantity);
            let min = r.i32()?;
            let base = r.i32()?;
            let ceiling = match r.u8()? {
                0 => CeilingBinding::Slot(slot_from_u32(r.u32()?)?),
                1 => CeilingBinding::Fixed(r.i32()?),
                other => {
                    return Err(CanonError::UnknownSchemaVersion {
                        found: other as u32,
                        known: 1,
                    })
                }
            };
            let regen_rate = r.i32()?;
            let regen_type = match r.u8()? {
                0 => RegenType::None,
                1 => RegenType::Flat,
                2 => RegenType::PerMille,
                other => {
                    return Err(CanonError::UnknownSchemaVersion { found: other as u32, known: 2 })
                }
            };
            let zero_behaviour = match r.u8()? {
                0 => ZeroBehaviour::Clamp,
                1 => ZeroBehaviour::BlockCosts,
                other => {
                    return Err(CanonError::UnknownSchemaVersion { found: other as u32, known: 1 })
                }
            };
            // v1..v5 predate the role binding. `None` states that rather than
            // guessing it — the same call every other version gate in this codec
            // makes. An UNKNOWN ordinal is refused, not defaulted: reading role
            // 9 as `None` would unbind an engine law from its number and show up
            // only as a law that appears never to run.
            let role = if version >= ROLE_SINCE {
                let raw = r.u8()?;
                EngineRole::ALL.into_iter().find(|x| *x as u8 == raw).ok_or(
                    CanonError::LengthMismatch {
                        field: "resources: engine role ordinal",
                        expected: EngineRole::ALL.len(),
                        found: raw as usize,
                    },
                )?
            } else {
                EngineRole::None
            };
            // Exclusivity re-checked on the way IN, on the same argument the
            // ascending-ordinal check above makes: an artifact carrying two
            // vitals was not written by `declare`, and accepting it would hand
            // a law two numbers with no basis to choose. Decode does not route
            // through `declare` (it must preserve stored order exactly), so
            // without this line the refusal would be reachable only from the
            // authoring side.
            if role.is_exclusive()
                && let Some(first) = out.rows().iter().find(|x| x.role == role)
            {
                return Err(CanonError::LengthMismatch {
                    field: "resources: an engine role names ONE pool",
                    expected: first.quantity as usize,
                    found: quantity as usize,
                });
            }
            out.rows[out.n as usize] = ResourceDecl {
                quantity,
                min,
                base,
                ceiling,
                regen_rate,
                regen_type,
                zero_behaviour,
                role,
            };
            out.n += 1;
        }
        Ok(out)
    }
}

/// Decode a `StatSlot` from its hashed ordinal.
///
/// An unknown ordinal is a REFUSAL, not a default. `DF7-A1` closes the slot
/// vocabulary, so an artifact naming slot 11 was written by a newer engine —
/// and silently reading it as `MaxHp` would bind a pool's ceiling to the wrong
/// stat and be visible only as wrong numbers.
fn slot_from_u32(v: u32) -> Result<StatSlot, CanonError> {
    StatSlot::ALL
        .into_iter()
        .find(|s| *s as u32 == v)
        .ok_or(CanonError::LengthMismatch {
            field: "resources: ceiling slot ordinal",
            expected: StatSlot::ALL.len(),
            found: v as usize,
        })
}
