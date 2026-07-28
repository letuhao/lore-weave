//! `CombatRules` — the COMB_001 law-chain's CONSTANTS.
//!
//! **IMP-D1 — a law's STRUCTURE is code, a law's CONSTANTS are config.** The
//! 4-step damage chain's order, its `max(1, …)` floors and its per-mille unit
//! stay locked in `commit-service/src/combat.rs`; every *number* those laws
//! multiply by arrives from here, and therefore lands inside the digest.
//!
//! Until F1 these were Rust literals, which made the F3 test
//! (*edit one constant → the digest moves*) unwritable — the tell that
//! [XST-D5](../../../docs/03_planning/LLM_MMO_RPG/27_extensibility_stress_test.md)
//! named. `MAX_HIT` carried a `TODO(IMP-D5)` for exactly this row.

use crate::canon::{Canon, CanonEncode};

/// The numbers the COMB_001 §4 laws read.
///
/// Field names carry their unit as a suffix (`_pm` = per-mille) because a
/// unit-less rules field is how a 1000× scale error gets authored.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct CombatRules {
    // ── hit chance: clamp(base + accuracy − dodge, floor, ceiling) ──
    /// The 0.5 base, in per-mille.
    pub hit_base_pm: i64,
    /// Without a floor a high-dodge target is untouchable and the fight cannot
    /// end. The floor's EXISTENCE is structure; its value is this.
    pub hit_floor_pm: i64,
    /// Without a ceiling an accuracy-stacked build is unmissable and dodge
    /// stops being a stat.
    pub hit_ceiling_pm: i64,

    // ── the damage chain ──
    /// Variance band, inclusive: `[lo, hi]` in per-mille (850..=1150 = 0.85..1.15).
    pub roll_band_lo_pm: i64,
    /// Inclusive upper bound. XST-D3: the band is drawn at its true width
    /// (`hi − lo + 1` values), so an exclusive reading here re-introduces the
    /// −0.06 % systematic damage shortfall that fix removed.
    pub roll_band_hi_pm: i64,
    /// Elemental multiplier. V1 identity (1000‰); kept IN the chain rather than
    /// omitted so promoting it later fills in a constant instead of
    /// re-deriving where it multiplies.
    pub elem_mult_pm: i64,
    /// Damage resistance. V1 zero. Applied as `(1000 − resist_pm)`.
    pub resist_pm: i64,
    /// `defending` divides the result by this (COMB_001: consumed by the next
    /// hit). A resolution-time flag, explicitly NOT a stat modifier (DF7-A8).
    pub defend_divisor: i64,
    /// The DECLARED ceiling on a single hit (XST-D2).
    ///
    /// The chain runs in `i128` so nothing overflows, but the result must
    /// return to `i64`, which makes a ceiling unavoidable. A declared ceiling
    /// is a different object from an emergent one: it has a number, a reason,
    /// and `AttackOutcome::capped` fires when it binds. Damage above it is a
    /// content defect, not a balance choice.
    pub max_hit: i64,
    /// COMB_001 AC-8 — how many rounds a KO stays revivable before permanent.
    pub ko_duration_rounds: u8,

    // ── initiative: av = base / speed, lowest acts first ──
    /// HSR action-value numerator.
    pub av_base: i64,
    /// `slowed` — acts later, so > 1000‰.
    pub av_slowed_pm: i64,
    /// `hasted` — acts sooner, so < 1000‰.
    pub av_hasted_pm: i64,
    /// `stunned`.
    pub av_stunned_pm: i64,
    /// The initiator's first turn. Starting a fight is worth a head start, not
    /// a free round.
    pub av_initiator_first_pm: i64,
}

impl CombatRules {
    /// RLS-D2 `engine_default` — the priority-0 layer.
    ///
    /// Every value here is the literal it replaced in
    /// `commit-service/src/combat.rs`, unchanged. The migration is
    /// value-preserving by construction and the pre-existing combat suite is
    /// what proves it (a test whose expected value needed changing would be a
    /// migration bug, not a test bug).
    ///
    /// F2 turns this into a shipped, versioned artifact rather than a `const fn`
    /// — RLS-D2's *"an artifact, not prose"*. It is code here because F1 has no
    /// I/O by design, and a layer with no file is still a layer.
    pub const fn engine_default() -> Self {
        Self {
            hit_base_pm: 500,
            hit_floor_pm: 50,
            hit_ceiling_pm: 950,
            roll_band_lo_pm: 850,
            roll_band_hi_pm: 1150,
            elem_mult_pm: 1000,
            resist_pm: 0,
            defend_divisor: 2,
            max_hit: 1_000_000_000,
            ko_duration_rounds: 5,
            av_base: 10_000,
            av_slowed_pm: 1200,
            av_hasted_pm: 800,
            av_stunned_pm: 2000,
            av_initiator_first_pm: 750,
        }
    }

    /// Number of distinct values the variance band can take.
    ///
    /// Derived here rather than stored so `lo`/`hi`/`width` cannot disagree —
    /// a stored width is a third number that has to be kept consistent with
    /// two others, which is how XST-D3 happened in the first place.
    ///
    /// Saturates into `1..=u64::MAX` for EVERY `i64` pair: a ruleset with
    /// `hi < lo` yields a degenerate band rather than a panic in
    /// `range_u64(0)`. F2's validator should REFUSE `hi < lo` at load time;
    /// this is the runtime floor that keeps a bad ruleset predictable, not a
    /// licence to ship one.
    ///
    /// **Computed in `i128`.** The obvious `hi - lo + 1` in `i64` overflows on
    /// a wide band (`lo = i64::MIN`), and `[profile.release-commit]` inherits
    /// `release`, so `overflow-checks` is **off** in the shipped binary: it
    /// would WRAP, silently, and hand `range_u64` a garbage width. Tests would
    /// have panicked and production would not — the worst pairing, and the same
    /// silent-wrong-number class as XST-D2 one layer up. A floor computed by
    /// arithmetic that can itself overflow is not a floor.
    pub const fn roll_band_width(&self) -> u64 {
        let w = self.roll_band_hi_pm as i128 - self.roll_band_lo_pm as i128 + 1;
        if w < 1 {
            1
        } else if w > u64::MAX as i128 {
            u64::MAX
        } else {
            w as u64
        }
    }
}

impl CanonEncode for CombatRules {
    fn canon(&self, c: &mut Canon) {
        // EXHAUSTIVE destructuring, no `..` — adding a field to CombatRules is
        // a compile error here until it is written into the digest below.
        // See the `CanonEncode` doc for what this does and does not close.
        let Self {
            hit_base_pm,
            hit_floor_pm,
            hit_ceiling_pm,
            roll_band_lo_pm,
            roll_band_hi_pm,
            elem_mult_pm,
            resist_pm,
            defend_divisor,
            max_hit,
            ko_duration_rounds,
            av_base,
            av_slowed_pm,
            av_hasted_pm,
            av_stunned_pm,
            av_initiator_first_pm,
        } = self;

        c.i64(*hit_base_pm);
        c.i64(*hit_floor_pm);
        c.i64(*hit_ceiling_pm);
        c.i64(*roll_band_lo_pm);
        c.i64(*roll_band_hi_pm);
        c.i64(*elem_mult_pm);
        c.i64(*resist_pm);
        c.i64(*defend_divisor);
        c.i64(*max_hit);
        c.u8(*ko_duration_rounds);
        c.i64(*av_base);
        c.i64(*av_slowed_pm);
        c.i64(*av_hasted_pm);
        c.i64(*av_stunned_pm);
        c.i64(*av_initiator_first_pm);
    }
}
