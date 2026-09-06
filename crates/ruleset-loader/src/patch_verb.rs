//! **`M2` — the AUTHORED form of a verb, and the fields an author may not write.**
//!
//! The seam `patch_resource.rs` uses: `patch.rs` folds LAYERS, this file
//! translates one authored table into one [`VerbDecl`] — which is where every
//! closed-set string is validated, and therefore where every *"you wrote X, the
//! legal values are Y"* message lives.
//!
//! ## `CMD-10`'s owed bite, discharged here
//!
//! §9.4 records it as owed: *"for a concern classified vocabulary, author a
//! member that sets an authority-bearing field and assert the build or the
//! engine REFUSES it. If no such member can be constructed, V4 was not applied —
//! it was asserted."*
//!
//! [`ruleset_core::FORBIDDEN_VERB_KEYS`] is the list and [`VerbPatch::refuse_authority_keys`]
//! is the refusal. **`deny_unknown_fields` alone would not have discharged it**:
//! it says *"unknown field"*, which is true and useless, because the field is
//! not unknown — it is very well known and simply not the author's. That
//! distinction is the whole of `FORBIDDEN_KEYS`'s reason for existing one level
//! up, and it applies unchanged here.

use ruleset_core::{
    EffectRow, QuantityName, QuantityTable, RequirementRow, TargetRole, VerbDecl, VerbError,
    FORBIDDEN_VERB_KEYS,
};

/// One authored verb.
///
/// **Every field is an OPERAND** — a value the engine's own fixed rule judges —
/// which is `CMD-10`'s V4. `amount` is judged by the conservation rule;
/// `at_least` by the comparison (`D-29`: a declared THRESHOLD, never a predicate
/// grammar); `cue` reaches no judgement at all, being consumed past the
/// authority boundary.
///
/// **Quantities are named, never numbered.** `QTY-A5` says ordinals are assigned
/// and never authored, and a TOML file containing one would bake an
/// engine-assigned number into content that a different layer stack renumbers.
#[derive(Debug, Clone, PartialEq, Eq, serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub struct VerbPatch {
    /// The author's word for it — a lookup key on the submission path, and
    /// nothing the engine branches on (`CMD-6`).
    pub name: String,
    /// **That something must be SHOWN**, as an ordinal (`CMD-4`). What it
    /// renders as is presentation's, in whatever language the reader asked for.
    #[serde(default)]
    pub cue: u16,
    /// `actor` | `other`. Absent = `actor`.
    #[serde(default)]
    pub target: Option<String>,
    /// The quantity this changes, and by how much. Signed.
    pub effect_quantity: String,
    pub effect_amount: i32,
    /// What it costs. Both or neither.
    #[serde(default)]
    pub spend_quantity: Option<String>,
    #[serde(default)]
    pub spend_amount: Option<i32>,
    /// What must hold. Both or neither.
    #[serde(default)]
    pub requires_quantity: Option<String>,
    #[serde(default)]
    pub requires_at_least: Option<i32>,
}

/// Why an authored verb could not become a declaration.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum VerbPatchError {
    /// The row carries a field that IS a judgement rather than an operand.
    /// **`CMD-10` V4**, refused by name with the reason.
    ForbiddenKey { verb: String, key: &'static str, reason: &'static str },
    /// The name is not a legal identifier.
    BadName { name: String, reason: String },
    /// A named quantity is not declared by this reality.
    UnknownQuantity { verb: String, field: &'static str, quantity: String },
    /// `target` is not a member of the closed set.
    BadTarget { verb: String, wrote: String },
    /// One half of a two-field pair without the other.
    HalfAPair { verb: String, field: &'static str },
    /// The table itself refused the resolved row.
    Table(VerbError),
}

impl core::fmt::Display for VerbPatchError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            Self::ForbiddenKey { verb, key, reason } => {
                write!(f, "verb `{verb}` sets `{key}`, which no verb row may carry: {reason}")
            }
            Self::BadName { name, reason } => write!(f, "verb name `{name}` is unusable: {reason}"),
            Self::UnknownQuantity { verb, field, quantity } => write!(
                f,
                "verb `{verb}`'s {field} names the quantity `{quantity}`, which this reality \
                 does not declare. Add it to `quantities`, or fix the spelling - an effect on \
                 a quantity that does not exist can never fire, and the verb would silently \
                 do nothing"
            ),
            Self::BadTarget { verb, wrote } => write!(
                f,
                "verb `{verb}` has target = \"{wrote}\"; the legal values are actor, other"
            ),
            Self::HalfAPair { verb, field } => write!(
                f,
                "verb `{verb}` sets {field} and not its partner. Both or neither: half a pair \
                 would have to be completed by a default, and guessing either an amount or a \
                 quantity for an author is how a verb comes to do something nobody wrote"
            ),
            Self::Table(e) => write!(f, "{e}"),
        }
    }
}

impl VerbPatch {
    /// **`CMD-10`'s bite.** Refuse an authority-bearing key BY NAME, before
    /// deserialization, with the reason it is not the author's to set.
    ///
    /// Takes the raw TOML table rather than the deserialized struct, and that is
    /// what makes it survive: a check that depended on the field being absent
    /// from [`VerbPatch`] would be silently defeated the day someone added the
    /// field for an unrelated purpose — `NV-4`, a guard defeated by an adjacent
    /// decision, which this repository has shipped before.
    pub fn refuse_authority_keys(
        row: &toml::value::Table,
        verb: &str,
    ) -> Result<(), VerbPatchError> {
        for (key, reason) in FORBIDDEN_VERB_KEYS {
            if row.contains_key(*key) {
                return Err(VerbPatchError::ForbiddenKey {
                    verb: verb.to_string(),
                    key,
                    reason,
                });
            }
        }
        Ok(())
    }

    /// Resolve the authored row against the reality's declared quantities.
    pub fn to_decl(&self, quantities: &QuantityTable) -> Result<VerbDecl, VerbPatchError> {
        let name = QuantityName::new(&self.name).map_err(|e| VerbPatchError::BadName {
            name: self.name.clone(),
            reason: format!("{e:?}"),
        })?;

        let ordinal = |q: &str, field: &'static str| -> Result<u16, VerbPatchError> {
            quantities.ordinal_of(q).ok_or_else(|| VerbPatchError::UnknownQuantity {
                verb: self.name.clone(),
                field,
                quantity: q.to_string(),
            })
        };

        let effect = EffectRow {
            quantity: ordinal(&self.effect_quantity, "effect_quantity")?,
            amount: self.effect_amount,
        };

        let spend = match (&self.spend_quantity, self.spend_amount) {
            (None, None) => None,
            (Some(q), Some(a)) => {
                Some(EffectRow { quantity: ordinal(q, "spend_quantity")?, amount: a })
            }
            (Some(_), None) => {
                return Err(VerbPatchError::HalfAPair {
                    verb: self.name.clone(),
                    field: "spend_quantity",
                })
            }
            (None, Some(_)) => {
                return Err(VerbPatchError::HalfAPair {
                    verb: self.name.clone(),
                    field: "spend_amount",
                })
            }
        };

        let requires = match (&self.requires_quantity, self.requires_at_least) {
            (None, None) => None,
            (Some(q), Some(a)) => {
                Some(RequirementRow { quantity: ordinal(q, "requires_quantity")?, at_least: a })
            }
            (Some(_), None) => {
                return Err(VerbPatchError::HalfAPair {
                    verb: self.name.clone(),
                    field: "requires_quantity",
                })
            }
            (None, Some(_)) => {
                return Err(VerbPatchError::HalfAPair {
                    verb: self.name.clone(),
                    field: "requires_at_least",
                })
            }
        };

        let target = match self.target.as_deref() {
            None | Some("actor") => TargetRole::Actor,
            Some(s) => TargetRole::from_str(s).ok_or_else(|| VerbPatchError::BadTarget {
                verb: self.name.clone(),
                wrote: s.to_string(),
            })?,
        };

        Ok(VerbDecl { name, cue: self.cue, requires, spend, effect, target })
    }
}
