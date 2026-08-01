//! RLS-A10 — LOAD-TIME validation, and what its blast radius is.
//!
//! | Time | Owner | Sees | Blast radius |
//! |---|---|---|---|
//! | **Load** | this module | the Ruleset only | the reality is **Unloadable** |
//! | Seed | `RealityBootstrapper` | Ruleset + WorldContent | creation/fork rejected |
//! | Admission | `commit-service` | live state | **one turn** rejected |
//!
//! The three were conflated under the single phrase *"at RealityManifest
//! bootstrap"*. They are different pipelines: a load failure makes a reality
//! unloadable; an admission failure rejects one turn.
//!
//! **RLS-D12 — failure is per-reality quarantine, never process failure.** One
//! malformed reality must not take down a node hosting forty others. So every
//! function here returns errors; nothing panics, and nothing calls `exit`.
//!
//! ## Belt AND braces, deliberately
//!
//! Every rule below is *also* guarded at runtime in the laws (a floor that
//! wins, a width that saturates, a divisor clamped to ≥1). Those stay. The two
//! do different jobs: the runtime floor keeps a bad ruleset **predictable** —
//! including one stored before this validator existed, which RLS-D18 forbids
//! re-validating — and the validator stops a bad ruleset being **stored** in
//! the first place. Deleting the runtime floors "because the loader checks now"
//! would break exactly the old-artifact case.

use ruleset_core::Ruleset;

/// One reason a ruleset cannot be loaded.
///
/// Carries the offending values, not just a message: the author is looking at
/// a file and needs to know which number to change.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ValidationError {
    /// `hit_floor_pm > hit_ceiling_pm` — the clamp is inverted, so every hit
    /// chance collapses to the floor and dodge stops existing.
    HitClampInverted { floor_pm: i64, ceiling_pm: i64 },
    /// `roll_band_hi_pm < roll_band_lo_pm` — an empty variance band. The
    /// runtime saturates the width to 1, which is deterministic and silent;
    /// stored, it would make every hit roll identical forever.
    RollBandInverted { lo_pm: i64, hi_pm: i64 },
    /// `defend_divisor < 1` — a zero divides by zero inside `apply` and takes
    /// the island down as a poison pill; a negative flips defending into a
    /// damage bonus.
    DefendDivisorTooSmall { found: i64 },
    /// DF7-V1 `stat.tuning_invalid` — `speed_per_tile` is a DIVISOR.
    MoveSpeedPerTileTooSmall { found: i32 },
    /// DF7-V1 `stat.tuning_invalid` — an actor that cannot move has no legal
    /// action on a grid.
    MoveMaxTooSmall { found: i32 },
    /// DF7-V1 `stat.tuning_invalid` — `base_move <= max_move`.
    MoveBaseExceedsMax { base: i32, max: i32 },
    /// A ruleset this build cannot read at all.
    UnknownSchemaVersion { found: u32, known: u32 },
}

impl core::fmt::Display for ValidationError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            Self::HitClampInverted { floor_pm, ceiling_pm } => write!(
                f,
                "combat.hit_floor_pm ({floor_pm}) exceeds combat.hit_ceiling_pm \
                 ({ceiling_pm}): every hit chance would collapse to the floor"
            ),
            Self::RollBandInverted { lo_pm, hi_pm } => write!(
                f,
                "combat.roll_band_hi_pm ({hi_pm}) is below combat.roll_band_lo_pm \
                 ({lo_pm}): the variance band is empty, so every hit would roll the same"
            ),
            Self::DefendDivisorTooSmall { found } => write!(
                f,
                "combat.defend_divisor is {found}: it must be >= 1 (0 divides by zero \
                 inside apply; a negative turns defending into a damage bonus)"
            ),
            Self::MoveSpeedPerTileTooSmall { found } => write!(
                f,
                "stats.move_speed_per_tile is {found}: it must be >= 1, it is a divisor \
                 (DF7-V1 stat.tuning_invalid)"
            ),
            Self::MoveMaxTooSmall { found } => write!(
                f,
                "stats.move_max is {found}: it must be >= 1, or no actor can move \
                 (DF7-V1 stat.tuning_invalid)"
            ),
            Self::MoveBaseExceedsMax { base, max } => write!(
                f,
                "stats.move_base ({base}) exceeds stats.move_max ({max}) \
                 (DF7-V1 stat.tuning_invalid)"
            ),
            Self::UnknownSchemaVersion { found, known } => {
                write!(f, "ruleset schema version {found}, this build reads {known}")
            }
        }
    }
}

/// Every load-time rule, collected — ALL of them, not the first failure.
///
/// An author fixing one number at a time through six round trips is how a
/// validator earns the reputation that gets it bypassed. The cost of reporting
/// everything is a `Vec`.
pub fn validate(r: &Ruleset) -> Result<(), Vec<ValidationError>> {
    let mut errs = Vec::new();

    if r.schema_version != ruleset_core::RULESET_SCHEMA_VERSION {
        errs.push(ValidationError::UnknownSchemaVersion {
            found: r.schema_version,
            known: ruleset_core::RULESET_SCHEMA_VERSION,
        });
    }

    let c = &r.combat;
    if c.hit_floor_pm > c.hit_ceiling_pm {
        errs.push(ValidationError::HitClampInverted {
            floor_pm: c.hit_floor_pm,
            ceiling_pm: c.hit_ceiling_pm,
        });
    }
    if c.roll_band_hi_pm < c.roll_band_lo_pm {
        errs.push(ValidationError::RollBandInverted {
            lo_pm: c.roll_band_lo_pm,
            hi_pm: c.roll_band_hi_pm,
        });
    }
    if c.defend_divisor < 1 {
        errs.push(ValidationError::DefendDivisorTooSmall { found: c.defend_divisor });
    }

    let s = &r.stats;
    if s.move_speed_per_tile < 1 {
        errs.push(ValidationError::MoveSpeedPerTileTooSmall { found: s.move_speed_per_tile });
    }
    if s.move_max < 1 {
        errs.push(ValidationError::MoveMaxTooSmall { found: s.move_max });
    }
    if s.move_base > s.move_max {
        errs.push(ValidationError::MoveBaseExceedsMax { base: s.move_base, max: s.move_max });
    }

    if errs.is_empty() { Ok(()) } else { Err(errs) }
}
