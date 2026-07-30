//! F1 verification — the digest is real, it covers everything it claims to,
//! and it covers nothing it must not.
//!
//! The exit criterion doc 26 §6 states for F1 is *"a digest is computed from
//! bytes and two different rulesets are distinguishable"*. That is `v3_*`
//! below. Everything else exists because a digest which is merely *computed*
//! can still be wrong in three ways this suite is built to catch:
//!
//! 1. it covers **less** than it appears to (a field never reaches `canon`),
//! 2. it covers **more** than it should (provenance leaks in and identical
//!    realities stop deduping),
//! 3. it is **unstable** (the same rules hash differently twice, so every
//!    replay reports a mismatch that is not one — RLS-D5's *fails loudly and
//!    wrongly*).

use ruleset_core::{CanonEncode, CombatRules, Provenance, ResolvedRuleset, Ruleset, RulesetEpoch, StatRules};

/// One row of a perturbation table: a field name and a mutator for it.
type Perturb<T> = (&'static str, fn(&mut T));

fn hex(d: &[u8; 32]) -> String {
    d.iter().map(|b| format!("{b:02x}")).collect()
}

// ── V1 · the golden digest ──────────────────────────────────────────────────

/// Pin the engine default's digest.
///
/// **This is the test F3 is built on.** *"Edit one constant → the digest
/// moves"* was unwritable while the constants were Rust literals; it is now
/// this assertion going red. Any change to any rules value, to the canonical
/// encoding, or to `RULESET_SCHEMA_VERSION` reds it — which is the point, not
/// an inconvenience. Update the hex only together with a deliberate answer to
/// *"what rule did I just change for every reality?"*
///
/// It also guards the one hand-maintained list in this design: adding a field
/// to `CombatRules`/`StatRules` is forced through `canon` by the exhaustive
/// destructuring, which moves this hex — and the reader updating it is the
/// moment to add the field's perturbation row below.
/// ## Repin log — the deliberate answer, each time
///
/// * `807d5b52…` → `76d7045e…`, **2026-07-29, `LAW_VERSION` (QTY-D13)**. The
///   answer to *"what rule did I just change for every reality?"* is: **none of
///   the numbers, and that is exactly the problem this closed.** The digest
///   hashed `schema_version + combat + stats` and nothing else, so two engine
///   builds with different `resolve_attack` arithmetic produced the IDENTICAL
///   digest for identical rules — a behavioural change moved nothing and could
///   therefore trigger nothing. `law_version` entering the hashed bytes is what
///   makes RLS-A13's *"pinned to the rules that produced it"* cover the laws
///   rather than only the config, and **this hex moving is the proof it is
///   inside the bytes rather than beside them.**
/// * `76d7045e…` → `7b75c111…`, **2026-07-29, `Q1` L2 declared quantities
///   (QTY-A5/A6)**. The answer: **none of the numbers changed and no law
///   changed** — `RULESET_SCHEMA_VERSION` went 2 → 3 and a `quantities` table
///   entered the hashed bytes, declaring `n = 0` for the engine default.
///
///   A reality that declares nothing behaves *identically* to before; only its
///   digest moves, which is correct — the ruleset it resolves to now has a
///   field it did not have, and RLS-D18 says a stored artifact is never
///   reinterpreted. Old artifacts keep their old digests and keep loading,
///   because v1/v2 are decoded at their own offsets and re-encoded at their own
///   version (QTY-A11); `a_v1_artifact_survives_put_and_get` and the v2
///   equivalent are what hold that down.
///
///   Note what did NOT move: only `0..n` is encoded, so
///   `MAX_DECLARED_QUANTITIES` is absent from the bytes and raising it later
///   will move nothing. That is `QTY-A6`'s *"`n` is in the hashed bytes, `N` is
///   in the binary"* made literal.
/// * `7b75c111…` → `9560a74a…`, **2026-07-30, `Q2` L2 declared resources
///   (QTY-A4)**. The answer: **none of the numbers changed and no law changed** —
///   `RULESET_SCHEMA_VERSION` went 3 → 4 and a `resources` table entered the
///   hashed bytes, declaring `n = 0` for the engine default. Four bytes: one
///   length prefix.
///
///   **The defeat law is untouched, which is `Q2`'s stated exit criterion.** A
///   declared pool cannot end an encounter — `ZeroBehaviour` has no `Defeat`
///   variant, deliberately, and the loader refuses `zero_behaviour = "defeat"`
///   by name so an author is told why rather than left guessing. So a reality
///   that declares nothing behaves identically, and a reality that declares
///   `qi` gains a pool without changing what kills anyone.
///
///   The same `N`-is-in-the-binary property holds here and is now load-bearing
///   twice over: the pool table is indexed by the QUANTITY ordinal — one
///   ordinal space, not two — so raising `MAX_DECLARED_QUANTITIES` widens both
///   at once and still moves no digest.
/// * `9560a74a…` → `4cbff832…`, **2026-07-30, `S-1b` the progression pin
///   (`PGN-R1`)**. The answer: **none of the numbers changed and no law
///   changed** — `RULESET_SCHEMA_VERSION` went 4 → 5 and a `progression` field
///   entered the hashed bytes as `None`. **One byte:** a presence flag.
///
///   This one differs in kind from the three above and the difference is the
///   point. `quantities` and `resources` put a TABLE in the bytes; this puts a
///   POINTER — the content address of a table that lives in a store. So the
///   engine default pays one byte while a reality that declares a 24-tier
///   ladder pays 33, and the ladder itself is hashed exactly once no matter how
///   many realities share the preset.
///
///   **Why the pointer moves the digest at all, and why that is the whole
///   design:** because it is INSIDE these bytes, editing a tier ladder changes
///   the progression digest, which changes the ruleset digest, which means
///   `Q0b B3`'s epoch switch already covers a progression change — no second
///   hash on the binding, no second version axis, no new column. That is what
///   `CanonEncode`'s exhaustive destructure bought here: the field could not
///   silently stay out.
///
///   ⚠ `None` is the only spelling of "no progression". A `Some(d)` where `d`
///   is the digest of an EMPTY table is the same behavioural state under a
///   different pin — one set of rules, two digests, which `RLS-A13` forbids.
///   Refusing it belongs on the path that writes the pin, and that path does
///   not exist yet: see
///   `an_empty_table_must_never_be_pinned_and_nothing_enforces_it_yet`.
#[test]
fn v1_engine_default_digest_is_pinned() {
    let d = Ruleset::engine_default().digest();
    assert_eq!(
        hex(&d.0),
        "4cbff832d13382c89cb6f2470f15c96568e2fbb250d2e4e215073ef419beab2f",
        "the engine-default ruleset digest moved — a rules value, the canonical \
         encoding, the schema version, or LAW_VERSION changed. That is a rules \
         change for EVERY reality; confirm it was intended before repinning, and \
         add a line to the repin log above saying which."
    );
}

// ── V2 · every field is actually covered ────────────────────────────────────

/// Mutate one field at a time; the digest must move for each.
///
/// Catches the half the exhaustive destructuring cannot: a field that is bound
/// in the pattern but then encoded from the wrong binding (an unused binding is
/// only a warning, so that compiles).
///
/// This table IS a hand-written companion list, with the residual that shape
/// always has — a NEW field has no row here until someone writes one. It is not
/// described as a guard; `v1` is what makes forgetting hard, by reddening the
/// moment the struct changes.
#[test]
fn v2_every_combat_field_reaches_the_digest() {
    let base = Ruleset::engine_default();
    let baseline = base.digest();

    let mutations: Vec<Perturb<CombatRules>> = vec![
        ("hit_base_pm", |r| r.hit_base_pm += 1),
        ("hit_floor_pm", |r| r.hit_floor_pm += 1),
        ("hit_ceiling_pm", |r| r.hit_ceiling_pm -= 1),
        ("roll_band_lo_pm", |r| r.roll_band_lo_pm += 1),
        ("roll_band_hi_pm", |r| r.roll_band_hi_pm += 1),
        ("elem_mult_pm", |r| r.elem_mult_pm += 1),
        ("resist_pm", |r| r.resist_pm += 1),
        ("defend_divisor", |r| r.defend_divisor += 1),
        ("max_hit", |r| r.max_hit += 1),
        ("ko_duration_rounds", |r| r.ko_duration_rounds += 1),
        ("av_base", |r| r.av_base += 1),
        ("av_slowed_pm", |r| r.av_slowed_pm += 1),
        ("av_hasted_pm", |r| r.av_hasted_pm += 1),
        ("av_stunned_pm", |r| r.av_stunned_pm += 1),
        ("av_initiator_first_pm", |r| r.av_initiator_first_pm += 1),
    ];

    let mut seen = std::collections::BTreeSet::new();
    for (name, mutate) in &mutations {
        let mut r = base.clone();
        mutate(&mut r.combat);
        let d = r.digest();
        assert_ne!(
            d, baseline,
            "changing CombatRules::{name} did NOT move the digest — it is not \
             reaching the canonical encoding, so the pin does not cover it"
        );
        assert!(
            seen.insert(hex(&d.0)),
            "two different CombatRules mutations produced the SAME digest \
             (at {name}) — a field is being encoded twice while another is \
             dropped, which the destructuring cannot catch"
        );
    }
}

#[test]
fn v2_every_stat_field_reaches_the_digest() {
    let base = Ruleset::engine_default();
    let baseline = base.digest();

    let mutations: Vec<Perturb<StatRules>> = vec![
        ("slot_defaults[0]", |r| r.slot_defaults[0] += 1),
        // The LAST slot specifically: an encoder that writes a prefix of the
        // array (a hand-unrolled loop, an off-by-one) still covers slot 0.
        ("slot_defaults[last]", |r| {
            let n = r.slot_defaults.len();
            r.slot_defaults[n - 1] += 1
        }),
        ("move_base", |r| r.move_base += 1),
        ("move_speed_per_tile", |r| r.move_speed_per_tile += 1),
        ("move_max", |r| r.move_max += 1),
        ("melee_archetype[0]", |r| r.melee_archetype[0] += 1),
        ("melee_archetype[last]", |r| {
            let n = r.melee_archetype.len();
            r.melee_archetype[n - 1] += 1
        }),
    ];

    let mut seen = std::collections::BTreeSet::new();
    for (name, mutate) in &mutations {
        let mut r = base.clone();
        mutate(&mut r.stats);
        let d = r.digest();
        assert_ne!(d, baseline, "changing StatRules::{name} did NOT move the digest");
        assert!(seen.insert(hex(&d.0)), "collision at StatRules::{name}");
    }
}

#[test]
fn v2_schema_version_reaches_the_digest() {
    let mut r = Ruleset::engine_default();
    let baseline = r.digest();
    r.schema_version += 1;
    assert_ne!(
        r.digest(),
        baseline,
        "an ENCODING change must be distinguishable from a rules change; the \
         schema version is what carries that, so it has to be hashed"
    );
}

// ── V3 · doc 26 §6's exit criterion, literally ──────────────────────────────

#[test]
fn v3_two_different_rulesets_are_distinguishable() {
    let a = Ruleset::engine_default();
    let mut b = a.clone();
    // The smallest possible rules difference: one point of hit floor.
    b.combat.hit_floor_pm += 1;

    assert_ne!(a.digest(), b.digest(), "two different rulesets must be distinguishable");
    assert_ne!(a.canon_bytes(), b.canon_bytes(), "…and so must their canonical bytes");
}

#[test]
fn v3_digest_is_computed_from_the_bytes_not_from_the_struct() {
    // The digest MUST be blake3 of exactly `canon_bytes()`. If it were taken
    // over anything else — a Debug string, a serde blob, a subset — F2's stored
    // artifact (which addresses the BYTES, RLS-D18) would not match the digest
    // the events were pinned with.
    let r = Ruleset::engine_default();
    let expected = blake3_of(&r.canon_bytes());
    assert_eq!(r.digest().0, expected);
}

fn blake3_of(bytes: &[u8]) -> [u8; 32] {
    // An independent recomputation rather than a call back into `digest()`,
    // which would assert the function equals itself.
    let mut h = blake3::Hasher::new();
    h.update(bytes);
    *h.finalize().as_bytes()
}

// ── V4 · provenance must NOT reach the digest (RLS-A15) ─────────────────────

/// Two behaviourally identical realities, authored by different users at
/// different times for different money, must dedupe onto one digest.
///
/// Non-vacuous **because `Provenance` lives inside `ResolvedRuleset`**: this
/// exercises a real container. If provenance lived elsewhere entirely the
/// assertion would be trivially true and would prove nothing.
#[test]
fn v4_provenance_and_epoch_are_excluded() {
    let mut a = ResolvedRuleset::engine_default();
    let mut b = ResolvedRuleset::engine_default();

    a.provenance = Provenance {
        author_user_id: "user-a".into(),
        preset_ref: "wuxia".into(),
        preset_version: 3,
        created_at_ms: 1_700_000_000_000,
        total_llm_cost_usd_milli: 12_345,
    };
    b.provenance = Provenance {
        author_user_id: "user-b".into(),
        preset_ref: "modern".into(),
        preset_version: 9,
        created_at_ms: 1_800_000_000_000,
        total_llm_cost_usd_milli: 999,
    };
    a.epoch = RulesetEpoch(0);
    b.epoch = RulesetEpoch(41);

    assert_eq!(
        a.digest(),
        b.digest(),
        "identical rules with different authoring lineage must dedupe — \
         otherwise re-authoring emits a spurious epoch for a change that \
         altered no rule (RLS-A15)"
    );

    // …and the container still tracks a REAL rules difference.
    b.ruleset.combat.max_hit -= 1;
    assert_ne!(a.digest(), b.digest());
}

// ── V5 · stability ──────────────────────────────────────────────────────────

#[test]
fn v5_digest_is_stable_across_calls_and_copies() {
    let r = Ruleset::engine_default();
    let first = r.digest();
    for _ in 0..64 {
        assert_eq!(r.digest(), first, "the encoding is not deterministic");
    }
    let clone = r.clone();
    assert_eq!(clone.digest(), first);

    // Independently reconstructed rather than copied: `engine_default()` must
    // be a pure constant, not something that picks up ambient state.
    assert_eq!(Ruleset::engine_default().digest(), first);
}

// ── encoding shape ──────────────────────────────────────────────────────────

#[test]
fn canonical_stream_is_domain_separated() {
    // The domain tag is written first, length-prefixed. Without it a future
    // artifact with the same integer layout could collide onto one digest.
    let bytes = Ruleset::engine_default().canon_bytes();
    let tag = b"loreweave.ruleset.v1";
    assert_eq!(&bytes[..4], &(tag.len() as u32).to_be_bytes(), "length prefix");
    assert_eq!(&bytes[4..4 + tag.len()], tag, "domain separation tag");
}

#[test]
fn canonical_encoding_has_no_ambiguous_concatenation() {
    // Every field is fixed-width or length-prefixed, so a value moving between
    // two adjacent fields must change the bytes. `("ab","c")` vs `("a","bc")`.
    let mut a = Ruleset::engine_default();
    let mut b = a.clone();
    a.combat.hit_base_pm = 500;
    a.combat.hit_floor_pm = 50;
    b.combat.hit_base_pm = 50;
    b.combat.hit_floor_pm = 500;
    assert_ne!(a.canon_bytes(), b.canon_bytes(), "field order must be observable");
}

#[test]
fn roll_band_width_is_derived_not_stored() {
    let r = CombatRules::engine_default();
    // 850..=1150 inclusive == 301 values. XST-D3's fix depends on this being
    // the INCLUSIVE width; an exclusive reading reinstates the −0.06 % bias.
    assert_eq!(r.roll_band_width(), 301);

    // A degenerate ruleset yields a degenerate band, never a panic in
    // `range_u64(0)`. F2's validator should refuse this at load time.
    let mut bad = r;
    bad.roll_band_hi_pm = bad.roll_band_lo_pm - 100;
    assert_eq!(bad.roll_band_width(), 1);
}

#[test]
fn engine_default_values_match_the_literals_they_replaced() {
    // The migration must be VALUE-PRESERVING. These are the literals as they
    // stood in commit-service/src/{combat,stats}.rs before F1; the combat suite
    // proves the laws still produce the same numbers, and this proves the
    // supply is the same rather than the laws having been re-tuned to match.
    let c = CombatRules::engine_default();
    assert_eq!(
        (c.hit_base_pm, c.hit_floor_pm, c.hit_ceiling_pm),
        (500, 50, 950)
    );
    assert_eq!((c.roll_band_lo_pm, c.roll_band_hi_pm), (850, 1150));
    assert_eq!((c.elem_mult_pm, c.resist_pm, c.defend_divisor), (1000, 0, 2));
    assert_eq!(c.max_hit, 1_000_000_000);
    assert_eq!(c.ko_duration_rounds, 5);
    assert_eq!(
        (c.av_base, c.av_slowed_pm, c.av_hasted_pm, c.av_stunned_pm, c.av_initiator_first_pm),
        (10_000, 1200, 800, 2000, 750)
    );

    let s = StatRules::engine_default();
    assert_eq!(s.slot_defaults, [100, 100, 10, 0, 250, 50, 50, 1500, 100, 5]);
    assert_eq!((s.move_base, s.move_speed_per_tile, s.move_max), (3, 50, 10));
    // archetype_melee's overrides, on top of the defaults.
    assert_eq!(s.melee_archetype, [100, 100, 12, 2, 450, 100, 50, 1500, 100, 5]);
}

#[test]
fn canon_encode_is_reachable_for_downstream_artifacts() {
    // F2 encodes stored artifacts through this trait; keep it public and
    // usable, or the loader grows its own second encoder and the two drift.
    let mut c = ruleset_core::Canon::new("test.domain");
    CombatRules::engine_default().canon(&mut c);
    assert!(!c.as_bytes().is_empty());
}
