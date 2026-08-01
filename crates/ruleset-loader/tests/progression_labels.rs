//! `PGN-A18` — the names, and the property that makes them a SIDECAR rather
//! than part of the hashed bytes.
//!
//! Split from `progression_authoring.rs` at `IMP-D3`'s 400-line ceiling. The
//! seam is the artifact: that file tests what becomes the HASHED table, this one
//! tests what deliberately does not.

use ruleset_loader::{
    parse_layer, resolve_and_pin, LabelStore, Layer, LoadError, ProgressionStore,
};

fn store(name: &str) -> (ProgressionStore, LabelStore) {
    let d = std::env::temp_dir().join(format!("lw-prog-lbl-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&d);
    (ProgressionStore::new(&d), LabelStore::new(&d))
}

fn reality(
    toml: &str,
) -> Result<(ruleset_core::Ruleset, ProgressionStore, LabelStore), LoadError> {
    let (s, l) = store(&format!("{:x}", toml.bytes().map(u64::from).sum::<u64>()));
    let layer = parse_layer(Layer::Reality, toml)?;
    let r = resolve_and_pin(&[layer], &s, &l)?;
    Ok((r, s, l))
}

// ── PGN-A18: the names, and the property that makes them a SIDECAR ──────────

/// **The headline, and the whole reason labels are not hashed.** Correcting a
/// translation must not move the reality's digest — if it did, every fix to a
/// Vietnamese string would be a rules change and would strand a running world.
#[test]
fn correcting_a_translation_moves_no_digest() {
    let (r, _s, l) = reality(
        "quantities = [\"qi\"]\n[[progression_kinds]]\nname = \"內功\"\nquantity = \"qi\"\n\
         type = \"skill\"\ncurve = \"linear\"\ncap = \"unbounded\"\n",
    )
    .expect("loads");
    let before = r.digest();
    let pin = r.progression.unwrap();

    // A translator fixes the name in place.
    let mut labels = l.get(&pin).unwrap().expect("labels were written at pin time");
    assert_eq!(labels.name_of(0), Some("內功"));
    labels = ruleset_loader::ProgressionLabels::from_rows(vec![(
        0,
        "內功（修訂）".to_string(),
        None,
        vec![],
    )]);
    l.put(&pin, &labels).expect("labels OVERWRITE - that is the point");

    assert_eq!(l.get(&pin).unwrap().unwrap().name_of(0), Some("內功（修訂）"));
    assert_eq!(r.digest(), before, "the RULESET digest must not have moved");
    assert_eq!(r.progression, Some(pin), "and neither did the progression pin");
}

/// `T10`, which doc 39 shipped as **NOT ENFORCED**. A reality could load a
/// 24-tier ladder with no names and show a player `tier_9`.
#[test]
fn a_reality_whose_labels_are_missing_does_not_load() {
    use ruleset_loader::{binding_store, load_reality, BindingStore, RealityError, RulesetStore};

    let root = std::env::temp_dir().join(format!("lw-lbl-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&root);
    let rules = RulesetStore::new(root.join("rules"));
    let prog = ProgressionStore::new(root.join("rules"));
    let labels = LabelStore::new(root.join("rules"));
    let bindings = binding_store(&root.join("bind"));

    let layer = parse_layer(
        Layer::Reality,
        "quantities = [\"qi\"]\n[[progression_kinds]]\nname = \"內功\"\nquantity = \"qi\"\n\
         type = \"skill\"\ncurve = \"linear\"\ncap = \"unbounded\"\n",
    )
    .unwrap();
    let r = resolve_and_pin(&[layer], &prog, &labels).unwrap();
    let d = rules.put(&r).unwrap();
    bindings.create("r1", &d).unwrap();
    load_reality("r1", &rules, &bindings).expect("with labels present it loads");

    // The names are deleted. The rules and the ladder are both intact.
    std::fs::remove_file(labels.path_for(&r.progression.unwrap())).unwrap();
    let e = load_reality("r1", &rules, &bindings)
        .expect_err("a ladder with no names must not reach a player");
    assert!(matches!(e, RealityError::Labels(_)), "{e}");
    let msg = format!("{e}");
    assert!(msg.contains("tier_9"), "the message must say what a player would SEE: {msg}");
    assert!(msg.contains("moves no digest"), "and that the fix is cheap: {msg}");
}

/// A name that exists and is empty is worse than a missing one: every coverage
/// check reads it as present, and it renders as nothing.
#[test]
fn an_empty_name_is_refused_more_loudly_than_a_missing_one() {
    let empty =
        ruleset_loader::ProgressionLabels::from_rows(vec![(0, "   ".to_string(), None, vec![])]);
    let table = ruleset_core::ProgressionTable::declare(vec![ruleset_core::ProgressionKindDecl {
        quantity: 0,
        progression_type: ruleset_core::ProgressionType::Skill,
        body_or_soul: ruleset_core::BodyOrSoul::Body,
        curve: ruleset_core::CurveKind::Linear { rate_milli: 1000 },
        tiers: vec![],
        cap_rule: ruleset_core::CapRule::Unbounded,
        initial_value: 0,
        initial_tier: None,
        derives_from: None,
    }])
    .unwrap();
    let e = empty.covers(&table).expect_err("an all-whitespace name is not a name");
    assert!(format!("{e}").contains("EMPTY"), "{e}");
}

/// A staged kind must name every tier it declares, not just itself.
#[test]
fn a_tier_with_no_name_is_refused() {
    // Refused at PARSE, the earliest point that can see it: `TierPatch.name` is
    // required rather than optional, because a nameless tier renders as `tier_9`
    // and an optional field is one every author forgets exactly once.
    let e = parse_layer(
        Layer::Reality,
        "quantities = [\"qi\"]
[[progression_kinds]]
name = \"內功\"
quantity = \"qi\"
         type = \"stage\"
curve = \"stage\"
cap = \"tier_based\"
initial_tier = 0
         [[progression_kinds.tiers]]
tier_max = 10
",
    )
    .expect_err("a tier with no name must not parse");
    assert!(format!("{e}").contains("name"), "{e}");
}
