//! `PGN-R2a` — the progression store, and the **nested** verify that
//! `RulesetStore::get` does not do.
//!
//! The headline these tests exist for: a `Ruleset` whose progression pin names
//! absent or corrupt bytes comes back from `RulesetStore::get` **completely
//! clean**, because the pin is 32 bytes *inside* the bytes that check out.
//! Everything below is about the second check that has to exist because of it.

use ruleset_core::{
    BodyOrSoul, BreakthroughCondition, CapRule, CurveKind, ProgressionDigest, ProgressionKindDecl,
    ProgressionTable, ProgressionType, Ruleset, TierDecl, WithinTierCurve,
};
use ruleset_loader::{
    resolve_progression, ProgressionStore, ProgressionStoreError, RulesetStore,
};

fn tmp(name: &str) -> std::path::PathBuf {
    let d = std::env::temp_dir().join(format!("lw-prog-store-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&d);
    d
}

/// 內功 — a staged ladder, so the stored table is never empty.
fn nei_gong() -> ProgressionKindDecl {
    ProgressionKindDecl {
        quantity: 0,
        progression_type: ProgressionType::Stage,
        body_or_soul: BodyOrSoul::Body,
        curve: CurveKind::Stage,
        tiers: vec![
            TierDecl {
                tier_index: 0,
                tier_max: 100,
                within_tier_curve: WithinTierCurve::Linear { rate_milli: 1000 },
                breakthrough: BreakthroughCondition::AtMax,
                initial_value_on_advance: 0,
            },
            TierDecl {
                tier_index: 1,
                tier_max: 300,
                within_tier_curve: WithinTierCurve::Linear { rate_milli: 1000 },
                breakthrough: BreakthroughCondition::AtMax,
                initial_value_on_advance: 0,
            },
        ],
        cap_rule: CapRule::TierBased,
        initial_value: 0,
        initial_tier: Some(0),
        derives_from: None,
    }
}

fn table() -> ProgressionTable {
    ProgressionTable::declare(vec![nei_gong()]).unwrap()
}

fn pinned(store: &ProgressionStore) -> Ruleset {
    let d = store.put(&table()).unwrap();
    let mut r = Ruleset::engine_default();
    r.progression = Some(d);
    r
}

// ── the store itself ────────────────────────────────────────────────────────

#[test]
fn a_table_survives_put_and_get() {
    let s = ProgressionStore::new(tmp("roundtrip"));
    let d = s.put(&table()).unwrap();
    assert!(s.contains(&d));
    assert_eq!(s.get(&d).unwrap().unwrap(), table());
}

#[test]
fn put_is_idempotent_and_never_overwrites() {
    let s = ProgressionStore::new(tmp("idem"));
    let a = s.put(&table()).unwrap();
    let b = s.put(&table()).unwrap();
    assert_eq!(a, b, "content addressing means two puts of equal content are one file");
}

#[test]
fn an_unstored_digest_is_none_not_an_error() {
    let s = ProgressionStore::new(tmp("absent"));
    s.ensure_root().unwrap();
    assert!(s.get(&table().digest()).unwrap().is_none(), "`not stored` is not corruption");
}

/// **`T8`.** A store that trusts its own filenames is a directory with
/// suggestive names. `get` re-digests the DECODED value, so substituted bytes
/// are refused rather than served under a name they do not match.
#[test]
fn substituted_bytes_are_refused_not_served() {
    let s = ProgressionStore::new(tmp("swap"));
    let d = s.put(&table()).unwrap();

    // A DIFFERENT, genuinely valid table written under the first one's name —
    // the substitution a raw byte-length check would miss.
    let mut other = nei_gong();
    other.tiers[1].tier_max = 999;
    let other = ProgressionTable::declare(vec![other]).unwrap();
    assert_ne!(other.digest(), d);
    std::fs::write(s.path_for(&d), other.canon_bytes()).unwrap();

    match s.get(&d) {
        Err(ProgressionStoreError::DigestMismatch { requested, actual }) => {
            assert_eq!(requested, d);
            assert_eq!(actual, other.digest());
        }
        other => panic!("expected DigestMismatch, got {other:?}"),
    }
}

#[test]
fn undecodable_bytes_are_refused() {
    let s = ProgressionStore::new(tmp("garbage"));
    let d = table().digest();
    s.ensure_root().unwrap();
    std::fs::write(s.path_for(&d), b"not a progression table").unwrap();
    assert!(matches!(s.get(&d), Err(ProgressionStoreError::Malformed(_))));
}

// ── D-PROGRESSION-EMPTY-PIN, now enforced ───────────────────────────────────

/// **The deferral closes here.** `None` and `Some(digest_of_empty)` are the same
/// behavioural state under two pins — one set of rules, two digests, which
/// `RLS-A13` forbids. `put` is the only place an empty pin can be minted, so it
/// is where the refusal goes.
#[test]
fn an_empty_table_cannot_be_pinned() {
    let s = ProgressionStore::new(tmp("emptypin"));
    let e = s.put(&ProgressionTable::EMPTY).expect_err("an empty pin must be refused");
    let msg = format!("{e}");
    assert!(msg.contains("D-PROGRESSION-EMPTY-PIN"), "{msg}");
    assert!(
        msg.contains("`None` is the only spelling"),
        "the refusal must say what to write INSTEAD, or an author just retries: {msg}"
    );
}

/// Defence in depth. `put` refuses to mint one, but bytes arrive in stores by
/// other routes — a restored backup, an operator copy, a future writer — and a
/// rule enforced at exactly one end holds only until someone adds a second end.
#[test]
fn an_empty_pin_that_reached_the_store_anyway_is_refused_at_resolve() {
    let s = ProgressionStore::new(tmp("emptyresolve"));
    s.ensure_root().unwrap();
    let empty = ProgressionTable::EMPTY;
    let d = empty.digest();
    std::fs::write(s.path_for(&d), empty.canon_bytes()).unwrap(); // bypasses `put`

    let mut r = Ruleset::engine_default();
    r.progression = Some(d);
    assert!(matches!(resolve_progression(&r, &s), Err(ProgressionStoreError::EmptyPin)));
}

// ── the nested resolve ──────────────────────────────────────────────────────

#[test]
fn no_pin_resolves_to_none() {
    let s = ProgressionStore::new(tmp("nopin"));
    assert!(resolve_progression(&Ruleset::engine_default(), &s).unwrap().is_none());
}

#[test]
fn a_good_pin_resolves_to_its_table() {
    let s = ProgressionStore::new(tmp("goodpin"));
    let r = pinned(&s);
    assert_eq!(resolve_progression(&r, &s).unwrap().unwrap(), table());
}

/// **The `QTY-Q5` case, at load time, for a whole progression system.**
/// Returning `Ok(None)` here would make an UNLOADABLE reality indistinguishable
/// from one that declares no progression: every ladder vanishes and the run
/// stays green.
#[test]
fn a_dangling_pin_is_an_error_never_none() {
    let s = ProgressionStore::new(tmp("dangling"));
    s.ensure_root().unwrap();
    let mut r = Ruleset::engine_default();
    let d = table().digest();
    r.progression = Some(d); // never stored

    match resolve_progression(&r, &s) {
        Err(ProgressionStoreError::Dangling { digest }) => {
            assert_eq!(digest, d);
            let msg = format!("{}", ProgressionStoreError::Dangling { digest });
            assert!(msg.contains("UNLOADABLE"), "{msg}");
            assert!(
                msg.contains("silently missing"),
                "the message must name the alternative it is refusing: {msg}"
            );
        }
        other => panic!("a dangling pin must NEVER be Ok(None); got {other:?}"),
    }
}

// ── the seam this module exists for ─────────────────────────────────────────

/// **The whole reason `resolve_progression` is a separate call.**
///
/// A `Ruleset` with a dangling progression pin round-trips through
/// `RulesetStore` with no complaint whatsoever: its own digest verifies,
/// because the pin is 32 bytes INSIDE the bytes that verified. Only the nested
/// resolve can see it. If this test ever fails because `RulesetStore::get`
/// started catching it, that is good news — and this file should be re-read
/// rather than the assertion flipped.
#[test]
fn the_outer_store_cannot_see_a_dangling_inner_pin() {
    let outer = RulesetStore::new(tmp("outer"));
    let inner = ProgressionStore::new(tmp("inner"));
    inner.ensure_root().unwrap();

    let mut r = Ruleset::engine_default();
    r.progression = Some(table().digest()); // pin to bytes that were never stored

    let d = outer.put(&r).unwrap();
    let back = outer.get(&d).expect("the OUTER artifact is intact").expect("stored");
    assert_eq!(back.progression, r.progression, "and the pin survived verbatim");

    assert!(
        matches!(resolve_progression(&back, &inner), Err(ProgressionStoreError::Dangling { .. })),
        "the outer store said fine; only the nested resolve catches it"
    );
}

/// `ProgressionDigest` and `RulesetDigest` address different artifacts, and the
/// newtype is what stops one being passed where the other belongs. This asserts
/// the two stores do not collide on a shared root — the `.canon` / `.prog`
/// split is by construction, not by policy.
#[test]
fn the_two_stores_share_a_root_without_colliding() {
    let root = tmp("shared");
    let outer = RulesetStore::new(&root);
    let inner = ProgressionStore::new(&root);

    let t = table();
    let pd = inner.put(&t).unwrap();
    let mut r = Ruleset::engine_default();
    r.progression = Some(pd);
    let rd = outer.put(&r).unwrap();

    assert_eq!(outer.get(&rd).unwrap().unwrap().progression, Some(pd));
    assert_eq!(inner.get(&pd).unwrap().unwrap(), t);
    assert_ne!(
        inner.path_for(&pd),
        outer.path_for(&rd),
        "different artifact kinds must never contend for one filename"
    );
    // And the same 32 bytes read as either digest still land on different paths.
    let same_bytes = ProgressionDigest(rd.0);
    assert_ne!(inner.path_for(&same_bytes), outer.path_for(&rd));
}
