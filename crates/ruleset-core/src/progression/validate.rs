//! `PROG-23`'s `ProgressionSchemaValidator`, built.
//!
//! ## Why this file exists at all
//!
//! Doc 39's first draft asserted that `PROG_001` §5.5's `CapRule` × `CurveDecl`
//! matrix was *"a real refusal surface that exists today"*. It was not.
//! `ProgressionSchemaValidator`, `progression.training.rule_invalid`,
//! `ProgressionKindDecl`, `TierDecl` and `CapRule` returned **zero hits** across
//! `crates/`, `services/` and `contracts/` — §5.5 is a markdown table containing
//! a *sentence about* a validator. The claim was read from a catalog row and
//! never checked against code, in a section whose own preamble says *"evaluated
//! against code, not from the docs."*
//!
//! `CPL-A2` requires generated content to be admitted by **the engine's own
//! validator**, and its second clause covers exactly this case: *where none
//! exists, the validator is built BEFORE the generator.* This is that build.
//!
//! ## Why the matrix cannot come from the question set
//!
//! `PGN-A2` derives the pipeline's questions from the schema, **field by
//! field**. `curve` and `cap_rule` are separate fields, answered in separate
//! rows, approved independently — so no per-field question can prevent an
//! author saying *"the ladder has stages"* (⇒ `Stage`) and *"power has an
//! absolute ceiling"* (⇒ `HardCap`) when both are true of the book and the pair
//! is illegal. A cross-field constraint has to be checked **here**, and a
//! violation is a refusal that names both halves — never a repair, because
//! either repair deletes human-approved content (`PGN-A17`).

use crate::quantity::QuantityTable;

use super::{CapRule, CurveKind, ProgressionTable, ProgressionType};

/// Why a progression table is not admissible against its ruleset.
///
/// Every variant names **which kind** and, where the defect is a relation,
/// **both sides** — a finding a human gate can act on without re-deriving it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ProgressionInvalid {
    /// The kind names a quantity ordinal this ruleset has not declared.
    UnknownQuantity { ordinal: u16, declared: usize },
    /// `PROG_001` §5.5. The pair is illegal; both halves are named.
    CapCurveMismatch { ordinal: u16, curve: &'static str, cap: &'static str, why: &'static str },
    /// `Stage` without tiers, or tiers without `Stage`.
    StageTierMismatch { ordinal: u16, why: &'static str },
    /// `initial_tier` is absent on a staged kind, present on an unstaged one,
    /// or points past the last tier.
    BadInitialTier { ordinal: u16, why: &'static str },
    /// `initial_value` exceeds what the kind's own cap allows at spawn.
    BadInitialValue { ordinal: u16, why: &'static str },
    /// A tier's `tier_max` is not greater than the one before it.
    NonMonotonicTiers { ordinal: u16, tier_index: u8 },
    /// `derives_from` points at a quantity that is not a declared kind.
    UnknownDerivationSource { ordinal: u16, source: u16 },
    /// `PROG_001` §4.5 — V1 is Skill ← Attribute only.
    BadDerivationShape { ordinal: u16, source: u16, why: &'static str },
    /// A kind derives from itself, directly or through a chain.
    DerivationCycle { ordinal: u16 },
}

impl core::fmt::Display for ProgressionInvalid {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            Self::UnknownQuantity { ordinal, declared } => write!(
                f,
                "progression kind names quantity ordinal {ordinal}, but this ruleset \
                 declares only {declared}. A kind whose identity does not exist can never \
                 be trained, displayed or referenced"
            ),
            Self::CapCurveMismatch { ordinal, curve, cap, why } => write!(
                f,
                "progression.schema.cap_curve_invalid: kind at ordinal {ordinal} declares \
                 curve `{curve}` with cap rule `{cap}`, which PROG_001 5.5 forbids - {why}. \
                 Both halves may be individually true of the book; the PAIR is what is \
                 illegal, so this is refused rather than repaired - either repair would \
                 delete a human-approved statement"
            ),
            Self::StageTierMismatch { ordinal, why } => write!(
                f,
                "progression.schema.stage_tiers_invalid: kind at ordinal {ordinal} - {why}"
            ),
            Self::BadInitialTier { ordinal, why } => write!(
                f,
                "progression.schema.initial_tier_invalid: kind at ordinal {ordinal} - {why}"
            ),
            Self::BadInitialValue { ordinal, why } => write!(
                f,
                "progression.schema.initial_value_invalid: kind at ordinal {ordinal} - {why}"
            ),
            Self::NonMonotonicTiers { ordinal, tier_index } => write!(
                f,
                "progression.schema.tiers_not_monotonic: kind at ordinal {ordinal}, tier \
                 {tier_index} does not raise tier_max above the tier before it. A ladder \
                 whose rungs do not rise is a ladder an actor can never climb"
            ),
            Self::UnknownDerivationSource { ordinal, source } => write!(
                f,
                "progression.schema.derivation_unknown: kind at ordinal {ordinal} derives \
                 from ordinal {source}, which is not a declared progression kind. Silently \
                 dropping the derivation would leave the author a declared bonus that never \
                 arrives"
            ),
            Self::BadDerivationShape { ordinal, source, why } => write!(
                f,
                "progression.schema.derivation_shape: kind at ordinal {ordinal} derives from \
                 {source} - {why} (PROG_001 4.5: V1 is Skill from Attribute only)"
            ),
            Self::DerivationCycle { ordinal } => write!(
                f,
                "progression.schema.derivation_cycle: kind at ordinal {ordinal} derives from \
                 itself through a chain. Resolving a training rate would not terminate"
            ),
        }
    }
}

impl std::error::Error for ProgressionInvalid {}

fn curve_name(c: &CurveKind) -> &'static str {
    match c {
        CurveKind::Linear { .. } => "Linear",
        CurveKind::Log { .. } => "Log",
        CurveKind::Stage => "Stage",
    }
}

fn cap_name(c: &CapRule) -> &'static str {
    match c {
        CapRule::SoftCap { .. } => "SoftCap",
        CapRule::HardCap { .. } => "HardCap",
        CapRule::TierBased => "TierBased",
        CapRule::Unbounded => "Unbounded",
    }
}

/// Admit a table against the ruleset that declares its identities.
///
/// Returns **every** finding, not the first. A gate that can only report one
/// defect per run makes a human fix one thing, re-run, and find another — and
/// with `PGN-A11`'s ~29 approval decisions upstream, that loop is where a
/// reviewer starts approving to make the noise stop.
pub fn validate(
    table: &ProgressionTable,
    quantities: &QuantityTable,
) -> Result<(), Vec<ProgressionInvalid>> {
    let mut out = Vec::new();
    let declared = quantities.len();

    for k in table.rows() {
        let ord = k.quantity;

        if usize::from(ord) >= declared {
            out.push(ProgressionInvalid::UnknownQuantity { ordinal: ord, declared });
            // Everything below reads this kind's own fields, which are still
            // meaningful; only cross-references need the ordinal to exist.
        }

        // ── PROG_001 §5.5, the matrix ───────────────────────────────────────
        match (&k.curve, &k.cap_rule) {
            (CurveKind::Stage, CapRule::TierBased) => {}
            (CurveKind::Stage, cap) => out.push(ProgressionInvalid::CapCurveMismatch {
                ordinal: ord,
                curve: curve_name(&k.curve),
                cap: cap_name(cap),
                why: "a staged ladder's ceiling IS its current tier's tier_max, so any other \
                      cap rule would give one kind two ceilings that disagree",
            }),
            (CurveKind::Linear { .. }, CapRule::TierBased) => {
                out.push(ProgressionInvalid::CapCurveMismatch {
                    ordinal: ord,
                    curve: curve_name(&k.curve),
                    cap: "TierBased",
                    why: "TierBased reads a tier's tier_max and a Linear kind has no tiers",
                })
            }
            (CurveKind::Log { .. }, CapRule::TierBased) => {
                out.push(ProgressionInvalid::CapCurveMismatch {
                    ordinal: ord,
                    curve: curve_name(&k.curve),
                    cap: "TierBased",
                    why: "TierBased reads a tier's tier_max and a Log kind has no tiers",
                })
            }
            (CurveKind::Log { .. }, CapRule::Unbounded) => {
                out.push(ProgressionInvalid::CapCurveMismatch {
                    ordinal: ord,
                    curve: curve_name(&k.curve),
                    cap: "Unbounded",
                    why: "a Log curve approaches a ceiling asymptotically, so it is only \
                          defined relative to one - Unbounded leaves the approach with no \
                          target",
                })
            }
            _ => {}
        }

        // ── staged-ness is one fact, declared in three places ───────────────
        let staged = matches!(k.curve, CurveKind::Stage);
        if staged && k.tiers.is_empty() {
            out.push(ProgressionInvalid::StageTierMismatch {
                ordinal: ord,
                why: "curve is Stage but no tiers are declared - a ladder with no rungs",
            });
        }
        if !staged && !k.tiers.is_empty() {
            out.push(ProgressionInvalid::StageTierMismatch {
                ordinal: ord,
                why: "tiers are declared but the curve is not Stage, so nothing would ever \
                      read them - a silent drop wearing the shape of a declaration",
            });
        }

        for w in k.tiers.windows(2) {
            if w[1].tier_max <= w[0].tier_max {
                out.push(ProgressionInvalid::NonMonotonicTiers {
                    ordinal: ord,
                    tier_index: w[1].tier_index,
                });
            }
        }

        match (staged, k.initial_tier) {
            (true, None) => out.push(ProgressionInvalid::BadInitialTier {
                ordinal: ord,
                why: "a staged kind must say where an ordinary person starts",
            }),
            (false, Some(_)) => out.push(ProgressionInvalid::BadInitialTier {
                ordinal: ord,
                why: "initial_tier is set on a kind that has no tiers",
            }),
            (true, Some(t)) if usize::from(t) >= k.tiers.len() => {
                out.push(ProgressionInvalid::BadInitialTier {
                    ordinal: ord,
                    why: "initial_tier points past the last declared tier",
                })
            }
            _ => {}
        }

        // ── the spawn value must be reachable ───────────────────────────────
        let spawn_ceiling = match (&k.cap_rule, k.initial_tier) {
            (CapRule::SoftCap { cap }, _) | (CapRule::HardCap { cap }, _) => Some(*cap),
            (CapRule::TierBased, Some(t)) => k.tiers.get(usize::from(t)).map(|d| d.tier_max),
            _ => None,
        };
        if let Some(ceiling) = spawn_ceiling {
            if k.initial_value > ceiling {
                out.push(ProgressionInvalid::BadInitialValue {
                    ordinal: ord,
                    why: "initial_value is above the ceiling that applies at spawn, so every \
                          actor would be created already clamped and the declared start \
                          value would be unobservable",
                });
            }
        }

        // ── derives_from ────────────────────────────────────────────────────
        if let Some(d) = &k.derives_from {
            match table.for_quantity(d.source_quantity) {
                None => out.push(ProgressionInvalid::UnknownDerivationSource {
                    ordinal: ord,
                    source: d.source_quantity,
                }),
                Some(src) => {
                    if d.source_quantity == ord {
                        out.push(ProgressionInvalid::DerivationCycle { ordinal: ord });
                    } else if k.progression_type != ProgressionType::Skill {
                        out.push(ProgressionInvalid::BadDerivationShape {
                            ordinal: ord,
                            source: d.source_quantity,
                            why: "only a Skill may derive",
                        });
                    } else if src.progression_type != ProgressionType::Attribute {
                        out.push(ProgressionInvalid::BadDerivationShape {
                            ordinal: ord,
                            source: d.source_quantity,
                            why: "a Skill may derive only from an Attribute",
                        });
                    }
                }
            }
        }
    }

    // ── cycles through a chain ──────────────────────────────────────────────
    //
    // The Skill←Attribute rule above already makes a cycle unreachable for a
    // VALID table — an Attribute never derives, so no chain closes. This walk
    // exists because that argument depends on a rule enforced two branches
    // away, and `NV-4` is the class where one correct decision quietly defeats
    // another's guard. If the shape rule is ever relaxed to allow Skill←Skill,
    // this is already here and already tested.
    for k in table.rows() {
        let mut seen = vec![k.quantity];
        let mut cur = k.derives_from.as_ref().map(|d| d.source_quantity);
        while let Some(next) = cur {
            if seen.contains(&next) {
                if !out.iter().any(|e| matches!(e, ProgressionInvalid::DerivationCycle { ordinal } if *ordinal == k.quantity))
                {
                    out.push(ProgressionInvalid::DerivationCycle { ordinal: k.quantity });
                }
                break;
            }
            seen.push(next);
            cur = table.for_quantity(next).and_then(|s| s.derives_from.as_ref()).map(|d| d.source_quantity);
        }
    }

    if out.is_empty() {
        Ok(())
    } else {
        Err(out)
    }
}
