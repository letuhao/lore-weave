//! `PGN-R2b` — the authored TOML form of a progression kind.
//!
//! ## The naming asymmetry, which is load-bearing
//!
//! An author writes `[[progression_kinds]]` — **rows**. The `Ruleset` field is
//! `progression` — a **computed digest**. The two names differ on purpose: the
//! digest is in `FORBIDDEN_KEYS`, because nobody authors a content address, and
//! that row stays honest only while the authored key is something else.
//!
//! `resources` has no such split because its field IS its table. Progression's
//! field is a pointer to a table that lives in a store, so the asymmetry is the
//! design showing through rather than an inconsistency to tidy away.
//!
//! ## Every closed-set value is refused BY NAME
//!
//! Same discipline as [`crate::patch_resource`], and the same reason: an author
//! who writes `type = "stage"` and silently gets `Attribute` spends an afternoon
//! wondering why nothing tiers. Each refusal lists what IS legal, so the message
//! is a fix rather than a verdict.

use ruleset_core::{
    BodyOrSoul, BreakthroughCondition, CapRule, CurveKind, Derivation, ProgressionKindDecl,
    ProgressionType, TierDecl, WithinTierCurve,
};

/// Why an authored progression row could not become a declaration.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProgressionPatchError {
    /// The `quantity` name as the author wrote it — the only handle they have
    /// on the row, since ordinals are assigned and a row number moves when the
    /// file is reordered.
    pub kind: String,
    pub reason: String,
}

impl core::fmt::Display for ProgressionPatchError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        write!(f, "progression kind `{}`: {}", self.kind, self.reason)
    }
}

impl std::error::Error for ProgressionPatchError {}

/// One authored tier. **No name** — see [`super::progression_store`] and
/// `PGN-A18`: tier names are localized content and live outside the digest, or
/// fixing a translation would strand a running reality.
// No `Eq`: the authored form carries decimals. The DECLARATION it produces is
// fully `Eq`, which is what the digest actually rests on - the decimals exist
// only between the TOML and `RLS-A7` normalization.
#[derive(Debug, Clone, PartialEq, serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TierPatch {
    pub tier_max: u64,
    /// `linear` | `log`.
    #[serde(default = "default_curve_name")]
    pub curve: String,
    /// `linear`: gain per train unit, as a decimal (`1.0`). Normalized to
    /// milli-units at load (`RLS-A7`) because floats in a replayed engine are a
    /// determinism liability (`DF7-A4`).
    #[serde(default)]
    pub rate: Option<f64>,
    #[serde(default)]
    pub base_rate: Option<f64>,
    #[serde(default)]
    pub difficulty: Option<f64>,
    /// `at_max` | `author_only`.
    #[serde(default = "default_breakthrough")]
    pub breakthrough: String,
    #[serde(default)]
    pub carry_over: u64,
}

fn default_curve_name() -> String {
    "linear".into()
}
fn default_breakthrough() -> String {
    "at_max".into()
}

/// One authored progression kind.
#[derive(Debug, Clone, PartialEq, serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ProgressionKindPatch {
    /// The declared quantity this kind IS, by NAME. Must appear in
    /// `quantities` — in this layer or a lower one, since the fold is a union.
    pub quantity: String,
    /// `attribute` | `skill` | `stage`.
    #[serde(rename = "type")]
    pub kind_type: String,
    /// `body` | `soul` | `both`. Defaults to `body` per `PROG_001` §4.3.
    #[serde(default = "default_body")]
    pub body_or_soul: String,
    /// `linear` | `log` | `stage`.
    pub curve: String,
    #[serde(default)]
    pub rate: Option<f64>,
    #[serde(default)]
    pub base_rate: Option<f64>,
    #[serde(default)]
    pub difficulty: Option<f64>,
    /// `soft_cap` | `hard_cap` | `tier_based` | `unbounded`.
    pub cap: String,
    #[serde(default)]
    pub cap_value: Option<u64>,
    #[serde(default)]
    pub tiers: Vec<TierPatch>,
    #[serde(default)]
    pub initial_value: u64,
    #[serde(default)]
    pub initial_tier: Option<u8>,
    /// The kind this one derives from, by NAME. `PROG_001` §4.5: Skill ←
    /// Attribute, training-rate only.
    #[serde(default)]
    pub derives_from: Option<String>,
    #[serde(default)]
    pub derive_factor: Option<f64>,
}

fn default_body() -> String {
    "body".into()
}

/// Decimals → fixed-point milli-units (`RLS-A7` normalization).
///
/// Refuses a negative or non-finite value rather than saturating: a rate of
/// `NaN` that becomes `0` is a kind that never trains, and the author would
/// have no way to see why.
fn milli(v: f64, what: &str, kind: &str) -> Result<u32, ProgressionPatchError> {
    if !v.is_finite() || v < 0.0 {
        return Err(ProgressionPatchError {
            kind: kind.into(),
            reason: format!("{what} must be a finite non-negative decimal, got {v}"),
        });
    }
    let scaled = (v * 1000.0).round();
    if scaled > f64::from(u32::MAX) {
        return Err(ProgressionPatchError {
            kind: kind.into(),
            reason: format!("{what} is too large once scaled to milli-units ({scaled})"),
        });
    }
    Ok(scaled as u32)
}

impl ProgressionKindPatch {
    /// Resolve to a declaration. `quantity` and `source` are the ordinals the
    /// fold assigned to this row's `quantity` name and its `derives_from` name.
    pub fn to_decl(
        &self,
        quantity: u16,
        source: Option<u16>,
    ) -> Result<ProgressionKindDecl, ProgressionPatchError> {
        let k = &self.quantity;
        let bad = |reason: String| ProgressionPatchError { kind: k.clone(), reason };

        let progression_type = match self.kind_type.as_str() {
            "attribute" => ProgressionType::Attribute,
            "skill" => ProgressionType::Skill,
            "stage" => ProgressionType::Stage,
            other => {
                return Err(bad(format!(
                    "`type = \"{other}\"` is not a progression type. Legal: attribute, skill, stage"
                )))
            }
        };
        let body_or_soul = match self.body_or_soul.as_str() {
            "body" => BodyOrSoul::Body,
            "soul" => BodyOrSoul::Soul,
            "both" => BodyOrSoul::Both,
            other => {
                return Err(bad(format!(
                    "`body_or_soul = \"{other}\"` is not legal. Legal: body, soul, both. This \
                     decides whether the kind follows the BODY or the SOUL through a xuyên \
                     không transfer, so guessing it would silently move a character's \
                     abilities to the wrong person"
                )))
            }
        };

        let curve = match self.curve.as_str() {
            "linear" => CurveKind::Linear {
                rate_milli: milli(self.rate.unwrap_or(1.0), "rate", k)?,
            },
            "log" => CurveKind::Log {
                base_rate_milli: milli(self.base_rate.unwrap_or(1.0), "base_rate", k)?,
                difficulty_milli: milli(self.difficulty.unwrap_or(1.0), "difficulty", k)?,
            },
            "stage" => CurveKind::Stage,
            other => {
                return Err(bad(format!(
                    "`curve = \"{other}\"` is not a curve. Legal: linear, log, stage"
                )))
            }
        };

        let cap = match (self.cap.as_str(), self.cap_value) {
            ("soft_cap", Some(c)) => CapRule::SoftCap { cap: c },
            ("hard_cap", Some(c)) => CapRule::HardCap { cap: c },
            ("soft_cap" | "hard_cap", None) => {
                return Err(bad(format!(
                    "`cap = \"{}\"` needs a `cap_value`. There is no default ceiling: an \
                     unbounded kind and a zero-capped one are both plausible readings of \
                     \"no value given\", and both are wrong to guess",
                    self.cap
                )))
            }
            ("tier_based", None) => CapRule::TierBased,
            ("unbounded", None) => CapRule::Unbounded,
            ("tier_based" | "unbounded", Some(_)) => {
                return Err(bad(format!(
                    "`cap = \"{}\"` takes no `cap_value` - tier_based reads the current \
                     tier's tier_max and unbounded has no ceiling at all, so the number \
                     would be silently ignored",
                    self.cap
                )))
            }
            (other, _) => {
                return Err(bad(format!(
                    "`cap = \"{other}\"` is not a cap rule. Legal: soft_cap, hard_cap, \
                     tier_based, unbounded. NOTE soft_cap and hard_cap are OPPOSITES - one \
                     is a slow grind past the ceiling, the other refuses training at it"
                )))
            }
        };

        let mut tiers = Vec::with_capacity(self.tiers.len());
        for (i, t) in self.tiers.iter().enumerate() {
            let idx = u8::try_from(i).map_err(|_| {
                bad(format!("more than {} tiers", u8::MAX))
            })?;
            let within = match t.curve.as_str() {
                "linear" => WithinTierCurve::Linear {
                    rate_milli: milli(t.rate.unwrap_or(1.0), "tier rate", k)?,
                },
                "log" => WithinTierCurve::Log {
                    base_rate_milli: milli(t.base_rate.unwrap_or(1.0), "tier base_rate", k)?,
                    difficulty_milli: milli(t.difficulty.unwrap_or(1.0), "tier difficulty", k)?,
                },
                other => {
                    return Err(bad(format!(
                        "tier {i}: `curve = \"{other}\"` is not legal here. Legal: linear, log \
                         (a tier cannot itself be `stage`)"
                    )))
                }
            };
            let breakthrough = match t.breakthrough.as_str() {
                "at_max" => BreakthroughCondition::AtMax,
                "author_only" => BreakthroughCondition::AuthorOnly,
                other => {
                    return Err(bad(format!(
                        "tier {i}: `breakthrough = \"{other}\"` is not legal. Legal: at_max, \
                         author_only. `at_max_plus` is NOT available - every one of its fields \
                         is a cross-element reference (an item, a place, an actor class, a \
                         fiction-time window) and none of those modules exists yet (PGN-A20)"
                    )))
                }
            };
            tiers.push(TierDecl {
                tier_index: idx,
                tier_max: t.tier_max,
                within_tier_curve: within,
                breakthrough,
                initial_value_on_advance: t.carry_over,
            });
        }

        let derives_from = match (&self.derives_from, source) {
            (None, _) => None,
            (Some(_), Some(src)) => Some(Derivation {
                source_quantity: src,
                rate_factor_milli: milli(self.derive_factor.unwrap_or(0.0), "derive_factor", k)?,
            }),
            (Some(name), None) => {
                return Err(bad(format!(
                    "`derives_from = \"{name}\"` names a quantity this ruleset does not \
                     declare. Silently dropping the derivation would leave a declared bonus \
                     that never arrives"
                )))
            }
        };

        Ok(ProgressionKindDecl {
            quantity,
            progression_type,
            body_or_soul,
            curve,
            tiers,
            cap_rule: cap,
            initial_value: self.initial_value,
            initial_tier: self.initial_tier,
            derives_from,
        })
    }
}
