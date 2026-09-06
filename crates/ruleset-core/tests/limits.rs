//! `LIM-1` — the ordinal-space register and the declared-size type, at the crate
//! that owns them. The LOADER's `tests/limits.rs` covers ingest; this covers the
//! type's own algebra, which has no manifest in it.

use ruleset_core::{LimitError, Limits, OrdinalSpace};

/// The register is a register: every space has a distinct authored key that
/// round-trips, and its capacity is the constant it claims to be.
#[test]
fn every_space_has_a_distinct_key_and_a_real_capacity() {
    let mut seen: Vec<&str> = Vec::new();
    for space in OrdinalSpace::ALL {
        let key = space.as_str();
        assert!(!seen.contains(&key), "two ordinal spaces share the key `{key}`");
        seen.push(key);
        assert!(space.capacity() > 0, "{space} has no capacity at all");
        assert_eq!(format!("{space}"), key, "Display must be the authored key");
    }
    assert_eq!(seen.len(), OrdinalSpace::COUNT);
}

/// **The default IS capacity**, which is what makes `[limits]` optional. A
/// `Default` impl returning zeros would give a reality that refuses its own
/// first row — which is why `Limits` deliberately has none.
#[test]
fn the_starting_value_is_this_builds_capacity() {
    for space in OrdinalSpace::ALL {
        assert_eq!(Limits::CAPACITY.get(space), space.capacity());
    }
}

/// **The cue space is DERIVED from the verb limit, not declared beside it.**
///
/// Every cue comes from a verb row and there is exactly one per row, so a
/// reality that narrows its verbs narrows its cues with them — with no second
/// number to keep in step. This test is what notices the day a non-verb emitter
/// makes that derivation false.
#[test]
fn the_cue_space_follows_the_verb_limit() {
    let mut l = Limits::CAPACITY;
    assert_eq!(l.cues(), OrdinalSpace::Verbs.capacity());
    l.declare(OrdinalSpace::Verbs, 5, 0).expect("5 verbs");
    assert_eq!(l.cues(), 5, "narrowing verbs must narrow cues");
}

/// `declare` refuses in both directions and moves nothing when it refuses. The
/// second half matters: a partially-applied limit would leave the fold holding a
/// ceiling nobody authored.
#[test]
fn a_refused_declaration_leaves_the_limits_untouched() {
    for space in OrdinalSpace::ALL {
        let mut l = Limits::CAPACITY;
        let before = l;

        let too_big = space.capacity() + 1;
        assert!(matches!(
            l.declare(space, too_big, 0),
            Err(LimitError::AboveCapacity { asked, .. }) if asked == too_big
        ));
        assert_eq!(l, before, "an AboveCapacity refusal moved {space}");

        assert!(matches!(
            l.declare(space, 2, 3),
            Err(LimitError::BelowDeclared { asked: 2, declared: 3, .. })
        ));
        assert_eq!(l, before, "a BelowDeclared refusal moved {space}");
    }
}

/// `room_for` is the per-row arm, and it is off-by-one sensitive in the
/// direction that matters: at a limit of `n`, row index `n-1` fits and `n` does
/// not. Asserted for every space, because the array indexing behind `get` is
/// where a wrong space would hide.
#[test]
fn room_for_admits_exactly_the_declared_count() {
    for space in OrdinalSpace::ALL {
        let mut l = Limits::CAPACITY;
        l.declare(space, 3, 0).expect("3 is under every capacity");
        for declared in 0..3usize {
            l.room_for(space, declared, "row").unwrap_or_else(|e| {
                panic!("{space}: row {declared} of 3 should fit, got {e}")
            });
        }
        let err = l.room_for(space, 3, "row").expect_err("the 4th must not fit");
        assert!(matches!(err, LimitError::AtLimit { limit: 3, .. }));
    }
}

/// **A TRIPWIRE for the one author-extensible space `LIM-1` did NOT cover.**
///
/// Progression has two ceilings of exactly the same class —
/// `MAX_DECLARED_PROGRESSION_KINDS` and `MAX_TIERS_PER_KIND` — and they are
/// absent from `[limits]` for a structural reason, not an oversight: a
/// progression kind folds into a TABLE that is stored and referenced by digest
/// (`S-1b`), not into the `Ruleset` the limits fold walks. Wiring it needs
/// `resolve_and_pin`'s store path, which is a different arm.
///
/// Recorded as `D-PROGRESSION-LIMITS-UNDECLARED`. **This test is its wake-up
/// call, not a comment about it:** the moment progression joins `OrdinalSpace`,
/// the assertion below reds and whoever added it must come here and say so.
/// Until then a manifest that writes `[limits] progression_kinds` is REFUSED by
/// name (`deny_unknown_fields`, asserted in the loader suite) rather than
/// silently ignored — which is the failure that would actually hurt.
#[test]
fn progression_is_the_one_space_limits_does_not_yet_reach() {
    assert_eq!(
        OrdinalSpace::COUNT,
        3,
        "an ordinal space was added or removed - if it is progression, delete this tripwire \
         and clear D-PROGRESSION-LIMITS-UNDECLARED; if it is something else, say why it is \
         not here"
    );
    assert!(
        !OrdinalSpace::ALL.iter().any(|s| s.as_str().contains("progression")
            || s.as_str().contains("tier")),
        "progression joined the register - this tripwire has done its job and must go"
    );
    // The constants it is about really do exist, so this test cannot pass by
    // being about nothing (`NV-2`: the subject must be able to vary).
    assert!(ruleset_core::MAX_DECLARED_PROGRESSION_KINDS > 0);
    assert!(ruleset_core::MAX_TIERS_PER_KIND > 0);
}

/// **A limit of zero is legal and means what it says.**
///
/// A reality with no verbs is an ordinary thing — the engine default is one —
/// and a world that declares itself verb-free should be held to it. Written
/// because the obvious defensive move (treat 0 as "unset") would make the
/// declaration silently do nothing, which is the failure mode `[limits]` exists
/// to remove.
#[test]
fn zero_is_a_real_limit_and_not_an_absent_one() {
    let mut l = Limits::CAPACITY;
    l.declare(OrdinalSpace::Verbs, 0, 0).expect("a world may declare itself verb-free");
    assert_eq!(l.get(OrdinalSpace::Verbs), 0);
    assert!(l.room_for(OrdinalSpace::Verbs, 0, "gather").is_err(), "0 must admit no rows");
}
