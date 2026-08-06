//! The declared-verb table and its codec — the collection half of [`super`].
//!
//! Same seam `resource/table.rs` uses, for the same reason: the parent is what a
//! verb IS, this is the COLLECTION and its canonical encoding. They change for
//! different reasons — a new verb field edits the parent, a schema version edits
//! this file.

use crate::canon::{Canon, CanonError, CanonReader};
use crate::quantity::QuantityName;

use super::{EffectRow, RequirementRow, TargetRole, VerbDecl, VerbError};

/// **How many verb rows THIS BINARY can hold — not how many a world may have.**
///
/// The second question is the manifest's, and it is answered by
/// [`ruleset_core::Limits`](crate::Limits) (`LIM-1`). Everything below is about
/// the first.
///
/// **Not the same number as `MAX_DECLARED_QUANTITIES`, and deliberately not an
/// alias of it.** `MAX_DECLARED_RESOURCES` IS an alias, because a pool *is* a
/// quantity and one ordinal space means one width. A verb is a different thing
/// in a different ordinal space, so tying the two would be a coincidence
/// pretending to be an invariant.
///
/// ## Why it was 16, and why 16 was wrong
///
/// The argument this doc used to carry explained why the TABLE is cheap — the
/// encoded cost is `0..n`, and the resident cost lands on a struct interned once
/// per reality (`QTY-A6.1`). Every word of that is true, and **none of it
/// explains why the number is sixteen.** It was a prose argument for
/// affordability standing in for a derivation, which is the same defect one tier
/// up that `docs/specs/2026-08-06-ordinal-spaces.md` was written to catch.
///
/// Worse, the discipline it borrowed was the wrong one. `MAX_DECLARED_QUANTITIES
/// = 32` is tight because that array is **per-ACTOR**: `[i32; 32]` is 128 B on
/// every resident actor, 1.28 MB at ten thousand. A verb table is
/// **per-RULESET**, interned once per reality. Measured, the two costs are not
/// in the same units:
///
/// ```text
/// [i32; 32]      on Actor     128 B x EVERY resident actor
/// [VerbDecl; 64] on Ruleset   4356 B ONCE per reality
/// ```
///
/// So 16 -> 64 costs ~3.2 KB per reality and **zero encoded bytes**. Sixteen
/// actions is a tight budget for a game; four kilobytes is not a budget at all.
///
/// ## Why capacity is still a compile-time constant, and not itself ingested
///
/// It is an inline array width, so making it runtime data means a heap
/// allocation — and that is forbidden by name (`QTY-A6 ⊥ QTY-A12`: boxing makes
/// `size_of` 16 bytes for every `n`, so the guards on these structs would
/// compile, always pass, and never fire again).
///
/// A per-deployment knob (`option_env!`) would dodge the allocation and is
/// **also refused**, for a sharper reason: two nodes of one cluster built with
/// different capacities would disagree about whether a manifest is valid. A
/// world that loads on one node and is refused on its neighbour is a worse
/// failure than a rebuild.
///
/// Raising it is a rebuild that **moves no existing digest** — only `0..n` is
/// encoded. Lowering it is forbidden by data, not by taste: a stored ordinal
/// past the new width is unreadable.
pub const MAX_DECLARED_VERBS: usize = 64;

/// How many distinct cue ordinals one reality may use — **`M2`, priced 2026-08-06.**
///
/// **The cue space is PER-REALITY (PO, sealed).** A cue is *"that something must
/// be SHOWN"* (`CMD-4`), and the engine carries it without ever reading it — so
/// its meaning can only come from the reality that declared it. `QTY-A14`
/// applies unchanged: cue 3 in one reality means nothing in another, and
/// presentation resolves `(reality, cue)` or resolves nothing.
///
/// **There is deliberately no cue TABLE.** A reality declares cue *numbers* on
/// its verb rows and nothing else; the words live in presentation content, in
/// whatever language the reader asked for. `AUTHOR-1` decides it — the manifest
/// author is not a developer, and a second table to write is a cost that buys
/// only what a presentation file already holds.
///
/// **DERIVED from [`MAX_DECLARED_VERBS`], not chosen.** Every cue in existence
/// comes from a verb row and there is exactly one per row, so a reality with 16
/// verbs cannot need a 17th distinct cue. Deriving it removes the thing to keep
/// in step — the move `HubRegistry`'s `LAYER_SLOTS` already makes on
/// `FoldLayer`'s own integer type, and the opposite of the `MAX_PLUGINS` alias
/// that ties a width to a table that does not force it.
///
/// ⚠️ **When a non-verb emitter arrives** — a status lapsing, an encounter
/// ending — this derivation stops being true. It must change HERE, once, with a
/// reason. That is the loud version of what would otherwise be a silent
/// widening, and it is why this is a derivation rather than a literal.
///
/// **Why it was unpriced until now:** `M2` shipped `cue: u16` with no constant,
/// no repin log and no argument, twelve lines from a constant carrying all
/// three. Nothing caught it because nothing counted ordinal spaces — which is
/// what `AF-8` had already reported about `RefKindMask` and nobody acted on.
/// See `docs/specs/2026-08-06-ordinal-spaces.md`.
pub const MAX_DECLARED_CUES: usize = MAX_DECLARED_VERBS;

/// The declared verbs of one reality, in the hashed bytes.
///
/// Ordered by DECLARATION, not sorted — unlike [`crate::ResourceTable`], and the
/// difference is `CMD-1`: **a verb's ordinal is its identity, append-only and
/// never reused.** Sorting would renumber every verb the moment an author added
/// one whose name sorts earlier, and a stored `verb 3` in committed history
/// would then name a different verb. The resource table can sort because a
/// pool's identity is its QUANTITY ordinal, which is assigned elsewhere.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct VerbTable {
    rows: [VerbDecl; MAX_DECLARED_VERBS],
    n: u16,
}

/// The row an unused tail slot holds. Never encoded — only `0..n` is — so its
/// contents cannot reach a digest.
const TAIL: VerbDecl = VerbDecl {
    name: QuantityName::EMPTY,
    cue: 0,
    requires: None,
    spend: None,
    effect: EffectRow { quantity: 0, amount: 0 },
    target: TargetRole::Actor,
};

impl VerbTable {
    /// A reality that declares no verbs. **The engine default, and it must stay
    /// that way**: a verb in `engine_default` would enter every reality in
    /// existence and `QTY-A10(c)` forbids removing it.
    pub const EMPTY: Self = Self { rows: [TAIL; MAX_DECLARED_VERBS], n: 0 };

    pub fn len(&self) -> usize {
        self.n as usize
    }

    pub fn is_empty(&self) -> bool {
        self.n == 0
    }

    pub fn rows(&self) -> &[VerbDecl] {
        &self.rows[..self.n as usize]
    }

    /// Resolve a name to its ordinal — the ONE place a verb's name is read.
    ///
    /// Linear, and for the reason `QuantityTable::ordinal_of` gives: `n <= 16`,
    /// and this runs on the submission path once per proposal, not inside the
    /// fold. `hot-path-gate` refuses a string-keyed map in a step file.
    pub fn ordinal_of(&self, name: &str) -> Option<u16> {
        self.rows().iter().position(|v| v.name.as_str() == name).map(|i| i as u16)
    }

    pub fn get(&self, ordinal: u16) -> Option<&VerbDecl> {
        self.rows().get(ordinal as usize)
    }

    /// Declare a verb. `declared_quantities` is the reality's own `n`, which is
    /// what makes [`VerbError::UnknownQuantity`] checkable at all.
    ///
    /// `offer_registry` says whether this build can authorise a target that is
    /// not the submitter. It is a PARAMETER rather than a constant so the
    /// refusal disappears by itself the day `CMD-11` lands — a hardcoded `false`
    /// would be a check that outlives its reason, which is the pragma failure
    /// `non-vacuity.md` names fourth.
    pub fn declare(
        &mut self,
        row: VerbDecl,
        declared_quantities: usize,
        offer_registry: bool,
    ) -> Result<(), VerbError> {
        if self.ordinal_of(row.name.as_str()).is_some() {
            return Err(VerbError::Duplicate { name: row.name.as_str().to_string() });
        }
        if self.n as usize >= MAX_DECLARED_VERBS {
            return Err(VerbError::TooMany {
                found: self.n as usize + 1,
                capacity: MAX_DECLARED_VERBS,
            });
        }
        // Every quantity a row names, checked in one place — the effect, the
        // spend and the requirement all address the same ordinal space.
        let mut named = vec![row.effect.quantity];
        if let Some(s) = row.spend {
            named.push(s.quantity);
        }
        if let Some(r) = row.requires {
            named.push(r.quantity);
        }
        for q in named {
            if (q as usize) >= declared_quantities {
                return Err(VerbError::UnknownQuantity {
                    verb: row.name.as_str().to_string(),
                    ordinal: q,
                    declared: declared_quantities,
                });
            }
        }
        // The cue is an ordinal like any other and is bounded like one. An
        // author's typo (`cue = 70000`) is refused rather than stored — and a
        // stored one would be a number presentation could never resolve.
        if (row.cue as usize) >= MAX_DECLARED_CUES {
            return Err(VerbError::CueOutOfRange {
                verb: row.name.as_str().to_string(),
                cue: row.cue,
                capacity: MAX_DECLARED_CUES,
            });
        }
        if row.target == TargetRole::Other && !offer_registry {
            return Err(VerbError::TargetNeedsOfferRegistry {
                verb: row.name.as_str().to_string(),
            });
        }
        self.rows[self.n as usize] = row;
        self.n += 1;
        Ok(())
    }

    /// Encode at a SPECIFIC schema version — `QTY-A11`'s round-trip.
    ///
    /// **The version parameter is here BEFORE it is needed, and that is the
    /// point.** `ResourceTable::canon_at` acquired one at v6 because a field
    /// arrived, and its doc explains what the version-free form would have done:
    /// re-encode a decoded older artifact in the NEW shape, so `RulesetStore::get`
    /// re-digests it and rejects the store's own artifact.
    ///
    /// This table shipped without one. A cold-start reviewer measured the trap:
    /// the moment a field is added to `VerbDecl` at v8, an unversioned encoder
    /// writes the v8 shape at v7 and breaks the round-trip for every v7
    /// artifact. **The sibling already learned this; the cost of learning it
    /// twice is a corrupted store.** So the parameter is threaded now, while it
    /// is free.
    pub(crate) fn canon_at(&self, c: &mut Canon, _version: u32) {
        c.seq_len(self.len());
        for v in self.rows() {
            c.bytes(v.name.as_bytes());
            c.u32(v.cue as u32);
            canon_opt_requirement(c, &v.requires);
            canon_opt_effect(c, &v.spend);
            c.u32(v.effect.quantity as u32);
            c.i32(v.effect.amount);
            c.u8(v.target as u8);
        }
    }

    /// Decode at a SPECIFIC schema version — the other half of [`Self::canon_at`].
    pub(crate) fn decode_at(r: &mut CanonReader<'_>, _version: u32) -> Result<Self, CanonError> {
        let n = r.u32()? as usize;
        if n > MAX_DECLARED_VERBS {
            // Refuse rather than truncate: a stored fact may already name a verb
            // ordinal in the tail, and a prefix read would silently resolve it to
            // a different verb.
            return Err(CanonError::LengthMismatch {
                field: "verbs",
                expected: MAX_DECLARED_VERBS,
                found: n,
            });
        }
        let mut out = Self::EMPTY;
        for _ in 0..n {
            let name = QuantityName::new(
                core::str::from_utf8(r.bytes()?).map_err(|_| CanonError::LengthMismatch {
                    field: "verbs: name is not UTF-8",
                    expected: 1,
                    found: 0,
                })?,
            )
            .map_err(|_| CanonError::LengthMismatch {
                field: "verbs: name is not a legal identifier",
                expected: 1,
                found: 0,
            })?;
            let cue = r.u32()? as u16;
            // Refused on the way IN too, on the argument the ascending-ordinal
            // check above makes: an artifact carrying an out-of-range cue was
            // not written by `declare`, and accepting it would store a number
            // presentation can never resolve.
            if (cue as usize) >= MAX_DECLARED_CUES {
                return Err(CanonError::LengthMismatch {
                    field: "verbs: cue ordinal",
                    expected: MAX_DECLARED_CUES,
                    found: cue as usize,
                });
            }
            let requires = decode_opt_requirement(r)?;
            let spend = decode_opt_effect(r)?;
            let effect = EffectRow { quantity: r.u32()? as u16, amount: r.i32()? };
            let target = match r.u8()? {
                0 => TargetRole::Actor,
                1 => TargetRole::Other,
                // A REFUSAL, not a default. An unknown role read as `Actor`
                // would land an effect on the wrong being and be visible only as
                // a wrong number.
                other => {
                    return Err(CanonError::LengthMismatch {
                        field: "verbs: target role ordinal",
                        expected: TargetRole::ALL.len(),
                        found: other as usize,
                    })
                }
            };
            out.rows[out.n as usize] =
                VerbDecl { name, cue, requires, spend, effect, target };
            out.n += 1;
        }
        Ok(out)
    }
}

/// A presence byte, then the fields — never a zero sentinel, for the reason
/// `progression`'s `Option` gives: *"not wired yet"* and *"genuinely none"* must
/// not be the same bytes.
fn canon_opt_effect(c: &mut Canon, e: &Option<EffectRow>) {
    match e {
        Some(x) => {
            c.u8(1);
            c.u32(x.quantity as u32);
            c.i32(x.amount);
        }
        None => c.u8(0),
    }
}

fn canon_opt_requirement(c: &mut Canon, e: &Option<RequirementRow>) {
    match e {
        Some(x) => {
            c.u8(1);
            c.u32(x.quantity as u32);
            c.i32(x.at_least);
        }
        None => c.u8(0),
    }
}

fn decode_opt_effect(r: &mut CanonReader<'_>) -> Result<Option<EffectRow>, CanonError> {
    match r.u8()? {
        0 => Ok(None),
        1 => Ok(Some(EffectRow { quantity: r.u32()? as u16, amount: r.i32()? })),
        v => Err(CanonError::LengthMismatch {
            field: "verbs: spend presence byte",
            expected: 1,
            found: usize::from(v),
        }),
    }
}

fn decode_opt_requirement(r: &mut CanonReader<'_>) -> Result<Option<RequirementRow>, CanonError> {
    match r.u8()? {
        0 => Ok(None),
        1 => Ok(Some(RequirementRow { quantity: r.u32()? as u16, at_least: r.i32()? })),
        v => Err(CanonError::LengthMismatch {
            field: "verbs: requirement presence byte",
            expected: 1,
            found: usize::from(v),
        }),
    }
}
