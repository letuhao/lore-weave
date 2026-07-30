//! Shared 武俠-fixture builders for the progression test files.
//!
//! Split out when `tests/progression.rs` crossed `IMP-D3`'s 400-line ceiling.
//! The seam is the same one `resource/` and `progression/` already use: the
//! TABLE's own behaviour (declare / encode / validate) in one file, the PIN on
//! `Ruleset` (`S-1b`) in another. These three kinds are what both files build
//! on, and duplicating them would let the two drift into testing different
//! fixtures under the same names.

#![allow(dead_code)] // each test file uses a subset; the module is shared.

use ruleset_core::{
    BodyOrSoul, BreakthroughCondition, CapRule, CurveKind, Derivation, ProgressionKindDecl,
    ProgressionTable, ProgressionType, QuantityTable, TierDecl, WithinTierCurve,
};

pub const INTERNAL_ENERGY: u16 = 0;
pub const SWORDSMANSHIP: u16 = 1;
pub const COMPREHENSION: u16 = 2;

/// The 武俠 fixture's three quantity ordinals, in declaration order.
pub fn quantities() -> QuantityTable {
    QuantityTable::assign(&["internal_energy", "swordsmanship", "comprehension"]).unwrap()
}


pub fn tier(i: u8, max: u64) -> TierDecl {
    TierDecl {
        tier_index: i,
        tier_max: max,
        within_tier_curve: WithinTierCurve::Linear { rate_milli: 1000 },
        breakthrough: BreakthroughCondition::AtMax,
        initial_value_on_advance: 0,
    }
}

/// 內功 — `Stage`/Body, the only staged kind in the fixture.
pub fn nei_gong() -> ProgressionKindDecl {
    ProgressionKindDecl {
        quantity: INTERNAL_ENERGY,
        progression_type: ProgressionType::Stage,
        body_or_soul: BodyOrSoul::Body,
        curve: CurveKind::Stage,
        tiers: vec![tier(0, 100), tier(1, 300), tier(2, 900)],
        cap_rule: CapRule::TierBased,
        initial_value: 0,
        initial_tier: Some(0),
        derives_from: None,
    }
}

/// 悟性 — `Attribute`/**Soul**, the xuyên-không case.
pub fn wu_xing() -> ProgressionKindDecl {
    ProgressionKindDecl {
        quantity: COMPREHENSION,
        progression_type: ProgressionType::Attribute,
        body_or_soul: BodyOrSoul::Soul,
        curve: CurveKind::Linear { rate_milli: 1000 },
        tiers: vec![],
        cap_rule: CapRule::SoftCap { cap: 100 },
        initial_value: 10,
        initial_tier: None,
        derives_from: None,
    }
}

/// 劍術 — `Skill`/Body, deriving from 悟性. The one cross-system edge in scope.
pub fn jian_shu() -> ProgressionKindDecl {
    ProgressionKindDecl {
        quantity: SWORDSMANSHIP,
        progression_type: ProgressionType::Skill,
        body_or_soul: BodyOrSoul::Body,
        curve: CurveKind::Log { base_rate_milli: 1500, difficulty_milli: 1200 },
        tiers: vec![],
        cap_rule: CapRule::SoftCap { cap: 1000 },
        initial_value: 0,
        initial_tier: None,
        derives_from: Some(Derivation {
            source_quantity: COMPREHENSION,
            rate_factor_milli: 50,
        }),
    }
}

pub fn fixture_table() -> ProgressionTable {
    ProgressionTable::declare(vec![nei_gong(), jian_shu(), wu_xing()]).unwrap()
}
