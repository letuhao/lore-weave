//! RLS-A3 early binding — creation resolves, load does not.
//!
//! Doc 16 §12 draws reality creation and island Cold→Hot as two separate
//! columns. F2.1 built the left one and used it for both: `spine` re-resolved
//! the layer files at every start, so an edit to `reality.toml` — or a deploy
//! that changed `engine_default` — silently changed the rules of a reality that
//! was already running. The store held the old bytes and nothing read them.
//!
//! Every test here is about that arrow.

use ruleset_core::Ruleset;
use ruleset_loader::{
    create_reality, load_reality, parse_layer, BindingError, FileBindingStore, Layer,
    RealityError, RulesetStore,
};

struct Env {
    store: RulesetStore,
    bindings: FileBindingStore,
}

fn env(name: &str) -> Env {
    let dir = std::env::temp_dir().join(format!("loreweave-binding-{name}"));
    let _ = std::fs::remove_dir_all(&dir);
    Env {
        store: RulesetStore::new(dir.join("rulesets")),
        bindings: FileBindingStore::new(dir.join("bindings")),
    }
}

/// **The property that was broken.**
///
/// Create a reality from a file, then edit the file. What loads must be what
/// was created — not what the file now says. This is RLS-A3's *"a later edit to
/// the `wuxia` preset never touches a reality that already exists"*, and it is
/// what makes replay-safety STRUCTURAL rather than procedural: with this
/// property there is no path by which a reality's rules change without an event
/// in its own log.
#[test]
fn editing_the_layer_file_after_creation_does_not_change_the_reality() {
    let e = env("edit-after-create");
    let before = parse_layer(Layer::Reality, "[combat]\nmax_hit = 500\n").unwrap();
    let (created, binding) =
        create_reality("r-1", &[before], &e.store, &e.bindings).expect("creates");
    assert_eq!(created.combat.max_hit, 500);
    assert_eq!(binding.epoch, 1, "the first binding is epoch 1 (doc 16 §12)");

    // The author edits the file — or a deploy changes engine_default. Either
    // way the LAYERS now say something else.
    let after = parse_layer(Layer::Reality, "[combat]\nmax_hit = 9_999\n").unwrap();
    assert_eq!(
        ruleset_loader::resolve(&[after]).unwrap().combat.max_hit,
        9_999,
        "re-resolving the layers WOULD produce different rules"
    );

    // …and the reality does not care, because loading never looks at a layer.
    let (loaded, binding) = load_reality("r-1", &e.store, &e.bindings).expect("loads");
    let digest = ruleset_core::RulesetDigest::from_hex(&binding.digest).expect("64 hex");
    assert_eq!(binding.epoch, 1, "load must surface the epoch, not just the digest");
    assert_eq!(
        loaded.combat.max_hit, 500,
        "a reality that already exists must run the rules it was CREATED with"
    );
    assert_eq!(loaded, created);
    assert_eq!(digest, created.digest());
}

/// Creation happens ONCE. A second create would silently re-resolve, which is
/// the bug; changing a live reality's rules is an epoch switch — an ordered
/// event (doc 16 §9) — not a re-create.
#[test]
fn a_reality_cannot_be_created_twice() {
    let e = env("create-twice");
    let l = parse_layer(Layer::Reality, "[combat]\nmax_hit = 500\n").unwrap();
    create_reality("r-1", std::slice::from_ref(&l), &e.store, &e.bindings).unwrap();

    let err = create_reality("r-1", &[l], &e.store, &e.bindings).unwrap_err();
    assert!(matches!(err, RealityError::Binding(BindingError::AlreadyBound { .. })), "{err}");
    assert!(format!("{err}").contains("epoch switch"), "the diagnostic must say what to do instead");
}

/// Loading a reality that was never created is a refusal, not a silent fall
/// back to the engine default — which would be the same bug wearing a friendlier
/// face: a reality quietly running rules nobody chose for it.
#[test]
fn loading_an_uncreated_reality_is_refused() {
    let e = env("never-created");
    let err = load_reality("ghost", &e.store, &e.bindings).unwrap_err();
    assert!(matches!(err, RealityError::Binding(BindingError::NotBound { .. })), "{err}");
    assert!(format!("{err}").contains("never created"));
}

/// RLS-D12 — a reality bound to a ruleset the store no longer has is
/// `Unloadable`, loudly. Resuming it would mean running it under rules its own
/// log does not describe, and no default is the right guess.
#[test]
fn a_missing_stored_ruleset_makes_that_reality_unloadable() {
    let e = env("pruned");
    let l = parse_layer(Layer::Reality, "[combat]\nmax_hit = 500\n").unwrap();
    let (created, _) = create_reality("r-1", &[l], &e.store, &e.bindings).unwrap();

    // Somebody pruned the store — which RLS-D6 says must never happen, and this
    // is what it costs when it does.
    let path = std::env::temp_dir()
        .join("loreweave-binding-pruned")
        .join("rulesets")
        .join(format!("{}.canon", created.digest().to_hex()));
    std::fs::remove_file(&path).unwrap();

    let err = load_reality("r-1", &e.store, &e.bindings).unwrap_err();
    assert!(matches!(err, RealityError::RulesetMissing { .. }), "{err}");
    let msg = format!("{err}");
    assert!(msg.contains("UNLOADABLE"), "{msg}");
    assert!(msg.contains("append-only"), "the message must say why this is not supposed to happen");
}

/// Two realities on one node, created from different files, stay distinct
/// through the store — the multi-tenant case the whole design exists for.
#[test]
fn two_realities_on_one_node_keep_their_own_rules() {
    let e = env("two-realities");
    let gritty = parse_layer(Layer::Reality, "[combat]\nmax_hit = 250\n").unwrap();
    let heroic = parse_layer(Layer::Reality, "[combat]\nmax_hit = 1_000_000\n").unwrap();

    create_reality("r-gritty", &[gritty], &e.store, &e.bindings).unwrap();
    create_reality("r-heroic", &[heroic], &e.store, &e.bindings).unwrap();

    let (g, gb) = load_reality("r-gritty", &e.store, &e.bindings).unwrap();
    let dg = ruleset_core::RulesetDigest::from_hex(&gb.digest).unwrap();
    let (h, hb) = load_reality("r-heroic", &e.store, &e.bindings).unwrap();
    let dh = ruleset_core::RulesetDigest::from_hex(&hb.digest).unwrap();
    assert_eq!(g.combat.max_hit, 250);
    assert_eq!(h.combat.max_hit, 1_000_000);
    assert_ne!(dg, dh, "their events must be distinguishable by pin");
}

/// A reality created with no layers at all is bound to the engine default —
/// by DIGEST, like any other. "Uses the defaults" is a resolved decision
/// recorded at creation, not an absence that re-resolves later.
#[test]
fn a_default_reality_is_still_bound_by_digest() {
    let e = env("defaults");
    let (created, _) = create_reality("r-plain", &[], &e.store, &e.bindings).unwrap();
    assert_eq!(created, Ruleset::engine_default());

    let (loaded, pb) = load_reality("r-plain", &e.store, &e.bindings).unwrap();
    let digest = ruleset_core::RulesetDigest::from_hex(&pb.digest).unwrap();
    assert_eq!(loaded, Ruleset::engine_default());
    assert_eq!(digest, Ruleset::engine_default().digest());
    assert!(e.store.contains(&digest), "even the default is STORED, or a future replay cannot resolve it");
}
