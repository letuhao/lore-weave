//! `S-1a` — the progression table survives declare → encode → decode → digest,
//! and `PROG_001` §5.5's matrix is a real refusal surface.
//!
//! Doc 39 v1 claimed that matrix *"exists today"*. It did not: the whole
//! vocabulary returned zero hits across the tree. These tests are what turn the
//! sentence into a fact.

use ruleset_core::{
    validate_progression, BodyOrSoul, BreakthroughCondition, CapRule, CurveKind, Derivation,
    ProgressionInvalid, ProgressionKindDecl, ProgressionTable, ProgressionType, QuantityTable,
    TierDecl, WithinTierCurve,
};

/// The 武俠 fixture's three quantity ordinals, in declaration order.
fn quantities() -> QuantityTable {
    QuantityTable::assign(&["internal_energy", "swordsmanship", "comprehension"]).unwrap()
}

const INTERNAL_ENERGY: u16 = 0;
const SWORDSMANSHIP: u16 = 1;
const COMPREHENSION: u16 = 2;

fn tier(i: u8, max: u64) -> TierDecl {
    TierDecl {
        tier_index: i,
        tier_max: max,
        within_tier_curve: WithinTierCurve::Linear { rate_milli: 1000 },
        breakthrough: BreakthroughCondition::AtMax,
        initial_value_on_advance: 0,
    }
}

/// 內功 — `Stage`/Body, the only staged kind in the fixture.
fn nei_gong() -> ProgressionKindDecl {
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
fn wu_xing() -> ProgressionKindDecl {
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
fn jian_shu() -> ProgressionKindDecl {
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

fn fixture_table() -> ProgressionTable {
    ProgressionTable::declare(vec![nei_gong(), jian_shu(), wu_xing()]).unwrap()
}

// ── the headline ────────────────────────────────────────────────────────────

/// **The slice's exit criterion.** The 武俠 fixture's three systems — all three
/// `ProgressionType`s, both `BodyOrSoul` values, one derivation edge — form a
/// table this engine admits.
#[test]
fn the_wuxia_fixtures_three_systems_are_admissible() {
    let t = fixture_table();
    validate_progression(&t, &quantities()).expect("the fixture's own systems must admit");
    assert_eq!(t.len(), 3);
    assert_eq!(
        t.for_quantity(COMPREHENSION).unwrap().body_or_soul,
        BodyOrSoul::Soul,
        "悟性 follows the SOUL — the one kind that survives a body swap"
    );
}

#[test]
fn a_table_survives_encode_decode_unchanged() {
    let t = fixture_table();
    let decoded = ProgressionTable::decode(&t.canon_bytes()).expect("round trip");
    assert_eq!(t, decoded);
    assert_eq!(t.digest(), decoded.digest());
}

/// Rows are stored in ordinal order regardless of authoring order, so two files
/// that differ only in the order they list kinds produce the SAME digest. If
/// these differed, reformatting a TOML file would strand a running reality.
#[test]
fn authoring_order_does_not_move_the_digest() {
    let a = ProgressionTable::declare(vec![nei_gong(), jian_shu(), wu_xing()]).unwrap();
    let b = ProgressionTable::declare(vec![wu_xing(), nei_gong(), jian_shu()]).unwrap();
    assert_eq!(a.digest(), b.digest());
    assert_eq!(a.rows()[0].quantity, INTERNAL_ENERGY, "and the rows are in ordinal order");
}

/// The digest must be a function of the CONTENT. A one-unit change to a single
/// tier's ceiling has to move it, or a ladder edit could ride into a live
/// reality with nothing going red.
#[test]
fn a_single_tier_edit_moves_the_digest() {
    let before = fixture_table().digest();
    let mut k = nei_gong();
    k.tiers[1].tier_max += 1;
    let after = ProgressionTable::declare(vec![k, jian_shu(), wu_xing()]).unwrap().digest();
    assert_ne!(before, after, "an edit nothing hashes is an edit no epoch switch can carry");
}

// ── PROG_001 §5.5 — the matrix that did not exist ───────────────────────────

fn only_error(k: ProgressionKindDecl) -> ProgressionInvalid {
    let t = ProgressionTable::declare(vec![k]).unwrap();
    let mut e = validate_progression(&t, &quantities()).expect_err("must refuse");
    assert_eq!(e.len(), 1, "expected exactly one finding, got {e:?}");
    e.remove(0)
}

/// Doc 39 §7's own worked example: *"`Stage` curve with `HardCap` is rejected."*
#[test]
fn a_staged_ladder_with_an_absolute_cap_is_refused() {
    let mut k = nei_gong();
    k.cap_rule = CapRule::HardCap { cap: 900 };
    let e = only_error(k);
    let msg = format!("{e}");
    assert!(msg.contains("cap_curve_invalid"), "{msg}");
    assert!(msg.contains("Stage") && msg.contains("HardCap"), "both halves must be named: {msg}");
    assert!(
        msg.contains("refused rather than repaired"),
        "the message must say WHY it is not repaired - either repair deletes a \
         human-approved statement: {msg}"
    );
}

#[test]
fn a_tierless_curve_with_a_tier_based_cap_is_refused() {
    let mut k = wu_xing();
    k.cap_rule = CapRule::TierBased;
    assert!(matches!(only_error(k), ProgressionInvalid::CapCurveMismatch { .. }));
}

/// `Log` approaches a ceiling asymptotically, so `Unbounded` leaves the approach
/// with no target. `PROG_001` §5.5 forbids the pair; the message says why.
#[test]
fn a_log_curve_without_a_ceiling_is_refused() {
    let mut k = jian_shu();
    k.cap_rule = CapRule::Unbounded;
    // 劍術 derives from 悟性, and `only_error` builds a one-row table — so the
    // derivation source would be absent and we would be asserting on the wrong
    // finding. The matrix is what is under test here, so the edge comes off.
    k.derives_from = None;
    let e = only_error(k);
    assert!(format!("{e}").contains("no target"), "{e}");
}

#[test]
fn the_legal_pairs_are_actually_legal() {
    for (curve, cap) in [
        (CurveKind::Linear { rate_milli: 1000 }, CapRule::SoftCap { cap: 10 }),
        (CurveKind::Linear { rate_milli: 1000 }, CapRule::HardCap { cap: 10 }),
        (CurveKind::Linear { rate_milli: 1000 }, CapRule::Unbounded),
        (CurveKind::Log { base_rate_milli: 1, difficulty_milli: 1 }, CapRule::SoftCap { cap: 10 }),
        (CurveKind::Log { base_rate_milli: 1, difficulty_milli: 1 }, CapRule::HardCap { cap: 10 }),
    ] {
        let mut k = wu_xing();
        k.curve = curve;
        k.cap_rule = cap;
        k.initial_value = 0;
        let t = ProgressionTable::declare(vec![k]).unwrap();
        validate_progression(&t, &quantities())
            .expect("PROG_001 5.5 lists this pair as valid; a validator that refuses it is worse than none");
    }
}

// ── staged-ness is one fact declared in three places ────────────────────────

#[test]
fn a_staged_kind_with_no_tiers_is_refused() {
    let mut k = nei_gong();
    k.tiers.clear();
    k.initial_tier = None;
    let t = ProgressionTable::declare(vec![k]).unwrap();
    let e = validate_progression(&t, &quantities()).unwrap_err();
    assert!(e.iter().any(|x| matches!(x, ProgressionInvalid::StageTierMismatch { .. })));
}

/// Tiers on an unstaged kind would be read by nothing. Refused rather than
/// ignored — a silent drop wearing the shape of a declaration.
#[test]
fn tiers_on_an_unstaged_kind_are_refused_not_ignored() {
    let mut k = wu_xing();
    k.tiers = vec![tier(0, 10)];
    let e = only_error(k);
    assert!(format!("{e}").contains("nothing would ever read them"), "{e}");
}

#[test]
fn a_ladder_whose_rungs_do_not_rise_is_refused() {
    let mut k = nei_gong();
    k.tiers[2].tier_max = k.tiers[1].tier_max;
    let e = only_error(k);
    assert!(matches!(e, ProgressionInvalid::NonMonotonicTiers { tier_index: 2, .. }), "{e:?}");
}

#[test]
fn a_staged_kind_must_say_where_an_ordinary_person_starts() {
    let mut k = nei_gong();
    k.initial_tier = None;
    assert!(matches!(only_error(k), ProgressionInvalid::BadInitialTier { .. }));
}

#[test]
fn an_initial_tier_past_the_last_rung_is_refused() {
    let mut k = nei_gong();
    k.initial_tier = Some(9);
    assert!(matches!(only_error(k), ProgressionInvalid::BadInitialTier { .. }));
}

/// An actor created already clamped makes the declared start value
/// unobservable — caught once at declaration rather than per actor per spawn,
/// forever, in code with no way to say which row is wrong.
#[test]
fn an_initial_value_above_the_spawn_ceiling_is_refused() {
    let mut k = wu_xing();
    k.initial_value = 5_000;
    let e = only_error(k);
    assert!(format!("{e}").contains("unobservable"), "{e}");
}

// ── derives_from ────────────────────────────────────────────────────────────

#[test]
fn deriving_from_an_undeclared_kind_is_refused_not_dropped() {
    let mut k = jian_shu();
    k.derives_from = Some(Derivation { source_quantity: 31, rate_factor_milli: 50 });
    let t = ProgressionTable::declare(vec![k, wu_xing()]).unwrap();
    let e = validate_progression(&t, &quantities()).unwrap_err();
    let msg = format!("{}", e[0]);
    assert!(msg.contains("derivation_unknown"), "{msg}");
    assert!(
        msg.contains("a declared bonus that never arrives"),
        "the QTY-Q5 silent-drop class is exactly what this refusal exists to prevent: {msg}"
    );
}

/// `PROG_001` §4.5 — V1 is Skill ← Attribute. Both halves are checked, because
/// checking one and assuming the other is how the pair drifts.
#[test]
fn only_a_skill_may_derive_and_only_from_an_attribute() {
    let mut attr_derives = wu_xing();
    attr_derives.derives_from =
        Some(Derivation { source_quantity: SWORDSMANSHIP, rate_factor_milli: 50 });
    let t = ProgressionTable::declare(vec![attr_derives, jian_shu()]).unwrap();
    let e = validate_progression(&t, &quantities()).unwrap_err();
    assert!(e.iter().any(|x| matches!(x, ProgressionInvalid::BadDerivationShape { .. })));

    let mut from_skill = jian_shu();
    from_skill.derives_from =
        Some(Derivation { source_quantity: INTERNAL_ENERGY, rate_factor_milli: 50 });
    let t = ProgressionTable::declare(vec![from_skill, nei_gong()]).unwrap();
    let e = validate_progression(&t, &quantities()).unwrap_err();
    assert!(e
        .iter()
        .any(|x| matches!(x, ProgressionInvalid::BadDerivationShape { why, .. }
            if why.contains("only from an Attribute"))));
}

#[test]
fn a_kind_that_derives_from_itself_is_refused() {
    let mut k = jian_shu();
    k.derives_from = Some(Derivation { source_quantity: SWORDSMANSHIP, rate_factor_milli: 50 });
    let t = ProgressionTable::declare(vec![k]).unwrap();
    let e = validate_progression(&t, &quantities()).unwrap_err();
    assert!(e.iter().any(|x| matches!(x, ProgressionInvalid::DerivationCycle { .. })));
}

// ── the ruleset it is validated AGAINST ─────────────────────────────────────

#[test]
fn a_kind_naming_an_undeclared_quantity_is_refused() {
    let mut k = wu_xing();
    k.quantity = 30;
    let t = ProgressionTable::declare(vec![k]).unwrap();
    let e = validate_progression(&t, &quantities()).unwrap_err();
    assert!(e
        .iter()
        .any(|x| matches!(x, ProgressionInvalid::UnknownQuantity { ordinal: 30, declared: 3 })));
}

/// **Every finding, not the first.** A gate that reports one defect per run
/// makes a human fix, re-run, and find another — and that loop is where a
/// reviewer starts approving to make the noise stop.
#[test]
fn validate_reports_every_finding_not_just_the_first() {
    let mut k = nei_gong();
    k.cap_rule = CapRule::HardCap { cap: 900 }; // matrix violation
    k.tiers[2].tier_max = 1; // non-monotonic
    k.initial_tier = Some(9); // out of range
    let t = ProgressionTable::declare(vec![k]).unwrap();
    let e = validate_progression(&t, &quantities()).unwrap_err();
    assert!(e.len() >= 3, "expected at least 3 findings, got {e:?}");
}

// ── the codec refuses what it did not write ─────────────────────────────────

#[test]
fn two_kinds_for_one_quantity_are_refused_not_deduped() {
    let e = ProgressionTable::declare(vec![nei_gong(), nei_gong()]).unwrap_err();
    assert!(format!("{e}").contains("hide which layer's declaration won"));
}

#[test]
fn an_unknown_discriminant_is_refused_rather_than_defaulted() {
    let mut bytes = fixture_table().canon_bytes();
    // The first row's progression_type byte: domain tag + row count + quantity.
    let idx = bytes.len() - 1;
    bytes[idx] = 0xEE; // the trailing derives_from presence byte
    assert!(
        ProgressionTable::decode(&bytes).is_err(),
        "a discriminant this engine does not know was written by a NEWER engine; \
         reading it as a default would silently change what the rules say"
    );
}

#[test]
fn a_truncated_buffer_is_refused() {
    let bytes = fixture_table().canon_bytes();
    assert!(ProgressionTable::decode(&bytes[..bytes.len() - 4]).is_err());
}

#[test]
fn trailing_bytes_are_refused() {
    let mut bytes = fixture_table().canon_bytes();
    bytes.push(0);
    assert!(
        ProgressionTable::decode(&bytes).is_err(),
        "refusing to decode a prefix and call it the whole table"
    );
}

#[test]
fn an_empty_table_round_trips() {
    let t = ProgressionTable::EMPTY;
    assert!(t.is_empty());
    assert_eq!(ProgressionTable::decode(&t.canon_bytes()).unwrap(), t);
    validate_progression(&t, &quantities()).expect("declaring no progression is a valid reality");
}
