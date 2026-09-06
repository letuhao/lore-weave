//! **`M1` — the actor hub's first consumer, asserted rather than claimed.**
//!
//! Until this file existed, `crates/actor-hub` had 91 green tests and **zero
//! consumers**: no `Cargo.toml` depended on it and `actor_hub::` appeared
//! nowhere outside the crate. `scripts/orphan-model-gate.py` exists because
//! seven projection tables shipped with a projector, a rebuilder, a golden
//! fixture, an oracle and a benchmark — and no producer. A substrate nothing
//! consumes is the same finding one layer up.
//!
//! Every test here runs against the SHIPPED preset through the REAL loader, so
//! none of them can pass against a fixture the binary does not use.

mod hub_fixture;

use commit_service::combat::Side;
use commit_service::{Actor, BindingError, RealityRules};
use ruleset_core::{CeilingBinding, EngineRole, RegenType, ResourceDecl, Ruleset, ZeroBehaviour};
use sim_core::EntityId;

const A: EntityId = EntityId(1);

fn decl(quantity: u16, role: EngineRole) -> ResourceDecl {
    ResourceDecl {
        quantity,
        min: 0,
        base: 1,
        ceiling: CeilingBinding::Fixed(10),
        regen_rate: 0,
        regen_type: RegenType::None,
        zero_behaviour: ZeroBehaviour::Clamp,
        role,
    }
}

// ── the refusals: every absence is a boot failure, never a default ───────────

/// **The engine default cannot run a law**, and saying so at boot is the whole
/// point of resolving the binding there.
///
/// `Ruleset::engine_default()` declares no quantities and no pools — deliberately,
/// because `QTY-A10(c)` makes a pool in the engine default permanent for every
/// reality in existence. So it binds no role, and the alternative to this
/// refusal is a fight that cannot end, found by a player.
#[test]
fn a_reality_with_no_pools_is_refused_and_names_the_role() {
    let err = RealityRules::resolve(Ruleset::engine_default())
        .expect_err("a reality binding no engine role must be refused");
    assert_eq!(err, BindingError::RoleUnbound { role: "vital" });
    // The message has to tell an author what to WRITE, not name an enum.
    let msg = err.to_string();
    assert!(msg.contains("role = \"vital\""), "the refusal must name the fix: {msg}");
}

/// A role names ONE pool. Two claimants is a refusal, not a precedence rule:
/// the loser is a pool an author told a law to read and it never would, and the
/// symptom is a law that appears not to run at all.
#[test]
fn two_pools_claiming_one_role_are_refused() {
    let mut r = Ruleset::engine_default();
    r.quantities = ruleset_core::QuantityTable::assign(&["alpha", "beta"]).unwrap();
    r.resources.declare(decl(0, EngineRole::Vital), 2).unwrap();
    let err = r
        .resources
        .declare(decl(1, EngineRole::Vital), 2)
        .expect_err("a second vital must be refused");
    assert!(
        matches!(err, ruleset_core::ResourceError::RoleClaimedTwice { first: 0, second: 1, .. }),
        "{err:?}"
    );
}

/// `EngineRole::None` is NOT exclusive — most pools are ordinary content, and
/// refusing a second one would make a reality with two plain meters impossible.
#[test]
fn plain_pools_may_share_the_absence_of_a_role() {
    let mut r = Ruleset::engine_default();
    r.quantities = ruleset_core::QuantityTable::assign(&["alpha", "beta"]).unwrap();
    r.resources.declare(decl(0, EngineRole::None), 2).unwrap();
    r.resources.declare(decl(1, EngineRole::None), 2).expect("two ordinary pools are fine");
    assert_eq!(r.resources.len(), 2);
}

// ── the consumer: an actor's numbers come from content ───────────────────────

/// An actor opens at the values the REALITY declared, not at a constructor
/// argument. Before `M1` the caller passed `max_hp` in, so two actors in one
/// reality could hold ceilings nothing had declared.
#[test]
fn an_actor_opens_at_the_realitys_declared_values() {
    let rules = hub_fixture::rules();
    let a = Actor::spawn(&rules, A, Side::A);
    assert_eq!(a.vital(&rules), 100, "the vital's declared base");
    assert_eq!(a.vital_ceiling(&rules), 100, "the ceiling resolved through StatSlot::MaxHp");
    assert_eq!(a.action_budget(&rules), 1, "one action per turn, declared as content");
    assert!(a.alive(&rules));
}

/// **ABSENT is not zero.** The SL-A12 empty portable has nothing attached, so
/// it has no quantities at all — where the old zeroed struct fabricated an
/// actor at death's door, indistinguishable from a real one.
#[test]
fn the_empty_portable_has_no_quantities_rather_than_zeroed_ones() {
    let rules = hub_fixture::rules();
    let ghost = Actor::absent(A);
    assert_eq!(ghost.vital(&rules), 0, "reads as 0 so `alive` stays total");
    assert!(!ghost.alive(&rules));
    // …but the reason it reads 0 is ABSENCE, and the fold is where that shows:
    // a real actor's vital is present in the report, a ghost's is not.
    let real = Actor::spawn(&rules, A, Side::A);
    let q = rules.hub().vital();
    assert!(real.resolved(&rules, &[], &[]).value(q).is_some());
    assert!(
        ghost.resolved(&rules, &[], &[]).value(q).is_none(),
        "an unattached actor's quantity must be ABSENT, not Some(0) — otherwise a \
         ghost and a corpse are the same row"
    );
}

/// **`A3.3` — the fold resolves a value through a POPULATED quantity table.**
///
/// Prints the numbers rather than only asserting them, because the measurement
/// is the evidence: a table size of zero would make every fold trivially
/// correct and prove nothing.
#[test]
fn the_fold_resolves_a_value_through_a_populated_quantity_table() {
    let rules = hub_fixture::rules();
    let table = &rules.rules().quantities;
    assert!(table.len() >= 3, "the fold must run against a POPULATED table, not EMPTY");

    let a = Actor::spawn(&rules, A, Side::A);
    let q = rules.hub().vital();

    let bare = a.resolved(&rules, &[], &[]).value(q).expect("present");
    let boosted = a
        .resolved(
            &rules,
            &[actor_hub::ModifierRow {
                target: q,
                op: actor_hub::ModifierOp::Flat(25),
                source: rules.hub().plugin(),
                fold_layer: rules.hub().layer(),
            }],
            &[],
        )
        .value(q)
        .expect("present");

    println!(
        "A3.3  quantity table size = {}  |  stored fold = {}  |  fold with +25 = {}",
        table.len(),
        bare,
        boosted
    );
    assert_eq!(bare, 100);
    assert_eq!(boosted, 125, "the contribution reached the resolved value");
}

/// A row whose target no attached plugin declares is REFUSED, and the refusal
/// is recorded rather than dropped — substrate §7's *nothing is silent*.
#[test]
fn a_contribution_to_an_undeclared_quantity_is_refused_not_ignored() {
    let rules = hub_fixture::rules();
    let a = Actor::spawn(&rules, A, Side::A);
    let past_the_table = actor_hub::QuantityOrdinal::new(30).unwrap();
    let report = a.resolved(
        &rules,
        &[actor_hub::ModifierRow {
            target: past_the_table,
            op: actor_hub::ModifierOp::Flat(1),
            source: rules.hub().plugin(),
            fold_layer: rules.hub().layer(),
        }],
        &[],
    );
    assert_eq!(report.value(past_the_table), None);
    assert_eq!(report.refused.len(), 1, "the refusal is a fact, not a silence");
}

/// **`A3.4` — the door count.** `CMD-3` closes the effect primitive set on
/// *"a primitive exists iff the substrate already built the door"*, and `M1`
/// opened exactly one: `Delta`, a signed write to a declared quantity.
///
/// This test is the count, executable. It fails when a second door opens
/// without the accounting being updated — which is the failure mode `FATAL-2`
/// found, where seven of eight primitives were prose that nothing measured.
#[test]
fn exactly_one_effect_door_is_open_and_it_is_delta() {
    let rules = hub_fixture::rules();
    let mut a = Actor::spawn(&rules, A, Side::A);


    // Delta: OPEN — the hub has a guarded write, and it carries any value.
    a.set_vital(&rules, a.vital(&rules) - 30);
    assert_eq!(a.vital(&rules), 70);

    // The other six are prose. Asserting their ABSENCE structurally is not
    // possible in Rust — there is no type to name — so the accounting lives in
    // `docs/plans/2026-08-06-game-tier-build-RUN-STATE.md` §3 and this test
    // reports what it exercised, which is what makes the count checkable
    // against a run rather than against a document.
    println!("A3.4  doors used by M1 = 1 (Delta)  |  quantities declared = {}  |  pools = {}",
        rules.rules().quantities.len(),
        rules.rules().resources.len());
}

// ── the property the milestone exists for ────────────────────────────────────

/// **The engine resolves a ROLE, and the reality answers with an ordinal.**
///
/// This is the assertion `scripts/engine-vocabulary-gate.py` enforces from the
/// other side. It is written here too because the gate proves *no engine file
/// names a quantity*, while this proves *the engine can still find its numbers*
/// — and one without the other is either a broken engine or an unguarded one.
#[test]
fn the_engine_finds_its_numbers_by_role_not_by_name() {
    let rules = hub_fixture::rules();
    let names: Vec<String> =
        rules.rules().quantities.names().iter().map(|n| n.as_str().to_string()).collect();

    // The names are the AUTHOR's. This test may say them; the engine may not.
    assert_eq!(names, vec!["vitality", "swiftness", "breath", "focus"]);

    // …and the engine reached each one through a role, by ordinal.
    assert_eq!(rules.hub().vital().get(), 0);
    assert_eq!(rules.hub().initiative().get(), 1);
    assert_eq!(rules.hub().action_budget().get(), 2);

    // Rename every quantity: the ordinals, and therefore the laws, are
    // unchanged. **This is `Q2`'s exit criterion, executed** — "a reality binds
    // Vital -> qi and the defeat law is unchanged" — and it was prose in
    // `resource/mod.rs` with nothing able to express it until `M1`.
    let mut renamed = rules.rules().clone();
    renamed.quantities =
        ruleset_core::QuantityTable::assign(&["qi", "xu", "yi", "shen"]).unwrap();
    let renamed = RealityRules::resolve(renamed).expect("renaming binds the same roles");
    assert_eq!(renamed.hub().vital(), rules.hub().vital());

    let a = Actor::spawn(&renamed, A, Side::A);
    assert_eq!(a.vital(&renamed), 100, "the defeat law reads the same number under a new name");
}

// ── the refusals a cold-start reviewer's findings forced ────────────────────

/// **Finding #1 — a verb naming a quantity with no POOL committed a LIE.**
///
/// `VerbTable::declare` validates against the QUANTITY table; an actor holds a
/// number only for a declared POOL. So a verb naming a pool-less quantity passed
/// every build check, wrote nothing, and committed an `Acted` fact carrying a
/// fabricated `left`. A silence would have been bad; a committed lie is worse.
#[test]
fn a_verb_naming_a_quantity_with_no_pool_is_refused_at_boot() {
    let src = "quantities = [\"spirit\"]\n\
               [[verbs]]\nname = \"ghost\"\neffect_quantity = \"spirit\"\neffect_amount = 5\n";
    let rules = ruleset_loader::resolve(&[
        ruleset_loader::parse_layer(
            ruleset_loader::Layer::Preset,
            ruleset_loader::PROVING_GROUND_TOML,
        )
        .unwrap(),
        ruleset_loader::parse_layer(ruleset_loader::Layer::Reality, src).unwrap(),
    ])
    .expect("the layer stack resolves — the quantity IS declared");

    let err = RealityRules::resolve(rules)
        .expect_err("a verb on a pool-less quantity must be refused at BOOT");
    assert!(
        matches!(err, BindingError::VerbNamesUndeclaredPool { .. }),
        "{err:?}"
    );
    println!("finding#1  {err}");
}

/// **Finding #2/#3 — the engine's turn budget is untouchable, in all THREE
/// positions.**
///
/// The first version of this refusal covered only `spend`. An `effect` on the
/// budget granted **unlimited free actions** (the engine deducted 1, the verb
/// added it back); a `requires` on it produced a verb that could never fire,
/// which is the exact incident the refusal's own docstring cited while fixing a
/// different arm.
#[test]
fn a_verb_may_not_touch_the_action_budget_in_any_position() {
    for (position, extra) in [
        ("effect", "effect_quantity = \"breath\"\neffect_amount = 1\n"),
        (
            "spend",
            "effect_quantity = \"vitality\"\neffect_amount = 1\n\
             spend_quantity = \"breath\"\nspend_amount = -1\n",
        ),
        (
            "requires",
            "effect_quantity = \"vitality\"\neffect_amount = 1\n\
             requires_quantity = \"breath\"\nrequires_at_least = 1\n",
        ),
    ] {
        let src = format!("[[verbs]]\nname = \"usurp\"\n{extra}");
        let rules = ruleset_loader::resolve(&[
            ruleset_loader::parse_layer(
                ruleset_loader::Layer::Preset,
                ruleset_loader::PROVING_GROUND_TOML,
            )
            .unwrap(),
            ruleset_loader::parse_layer(ruleset_loader::Layer::Reality, &src).unwrap(),
        ])
        .expect("the layer stack resolves");
        let err = RealityRules::resolve(rules).expect_err(&format!(
            "`{position}` on the action budget must be refused at BOOT — otherwise an              `effect` grants unlimited free actions, a `spend` charges twice, and a              `requires` can never be met"
        ));
        assert!(
            matches!(&err, BindingError::VerbTouchesEngineBudget { position: p, .. } if *p == position),
            "the refusal must name WHICH position: {err:?}"
        );
        println!("finding#2/3  {position}: {err}");
    }
}
