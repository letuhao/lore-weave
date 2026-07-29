//! `Q0b B1b` — the epoch switch, end to end, through a real store and a real
//! binding file.
//!
//! `B1a` proved `QTY-A5`'s never-reuse arm against hand-built tables. That is
//! the law in a vacuum. These tests are the law wired to the two things that can
//! defeat it in practice: a **history that is read from storage** (if it comes
//! back short, every switch is trivially permitted) and a **content store that
//! may not hold what a prior epoch is bound to** (if a missing ruleset is
//! skipped, the check silently examines fewer epochs than it claims).
//!
//! Both of those failures return `Ok`. That is why they get tests rather than
//! trust.

use ruleset_core::{QuantityTable, Ruleset};
use ruleset_loader::{
    activate_reality_epoch, BindingError, BindingStore, EpochSwitchError, FileBindingStore,
    RulesetStore,
};

const R1: &str = "11111111-1111-4111-8111-111111111111";

struct Fixture {
    dir: std::path::PathBuf,
    bindings: FileBindingStore,
    store: RulesetStore,
}

/// Same shape as `early_binding.rs`'s `env()` — a NAMED directory wiped on
/// entry, not `tempfile`. `ruleset-loader` has three dependencies on purpose
/// (`crate-purity-gate`), and a dev-dependency is still a dependency someone
/// will later reach for from `src/`.
fn fixture(name: &str) -> Fixture {
    let dir = std::env::temp_dir().join(format!("loreweave-epoch-{name}"));
    let _ = std::fs::remove_dir_all(&dir);
    let store = RulesetStore::new(dir.join("rulesets"));
    store.ensure_root().expect("store root");
    Fixture { bindings: FileBindingStore::new(dir.join("bindings")), store, dir }
}

/// A ruleset that is `engine_default` except for its declared quantities.
fn rules_with(names: &[&str]) -> Ruleset {
    Ruleset {
        quantities: QuantityTable::assign(names).expect("valid identifiers"),
        ..Ruleset::engine_default()
    }
}

impl Fixture {
    /// Put a ruleset in the content store and return its digest.
    fn put(&self, names: &[&str]) -> ruleset_core::RulesetDigest {
        self.store.put(&rules_with(names)).expect("put")
    }

    fn create(&self, names: &[&str]) -> ruleset_core::RulesetDigest {
        let d = self.put(names);
        self.bindings.create(R1, &d).expect("create");
        d
    }

    fn switch(&self, names: &[&str]) -> Result<u32, EpochSwitchError> {
        let d = self.put(names);
        activate_reality_epoch(&self.bindings, &self.store, R1, &d, "test").map(|b| b.epoch)
    }
}

// ── the happy path, which must keep working or every refusal below is vacuous ──

#[test]
fn an_additive_switch_is_permitted_and_advances_the_epoch() {
    let f = fixture("additive");
    f.create(&["qi", "karma"]);
    assert_eq!(f.switch(&["qi", "karma", "fire"]).expect("permitted"), 2);
    assert_eq!(f.bindings.load(R1).unwrap().unwrap().epoch, 2);
    assert_eq!(f.bindings.history(R1).unwrap().len(), 2);
}

#[test]
fn history_is_ascending_and_load_returns_the_newest_epoch() {
    let f = fixture("ascending");
    f.create(&["qi"]);
    f.switch(&["qi", "karma"]).expect("2");
    f.switch(&["qi", "karma", "fire"]).expect("3");

    let h = f.bindings.history(R1).unwrap();
    assert_eq!(h.iter().map(|b| b.epoch).collect::<Vec<_>>(), vec![1, 2, 3]);
    // The whole point of `load`: a store that returned epoch 1 would pin every
    // reality to its creation rules and make an epoch switch appear to do
    // nothing at all.
    assert_eq!(f.bindings.load(R1).unwrap().unwrap().epoch, 3);
    assert_eq!(f.bindings.load(R1).unwrap().unwrap().digest, h[2].digest);
}

// ────────────────────────── the refusal, and its cost ──────────────────────────

#[test]
fn reusing_an_ordinal_is_refused_and_the_binding_is_untouched() {
    let f = fixture("refusal");
    f.create(&["qi", "karma"]);

    let err = f.switch(&["qi", "fire"]).expect_err("ordinal 1 changes meaning");
    match &err {
        EpochSwitchError::OrdinalReused(r) => {
            assert_eq!((r.ordinal, r.was.as_str(), r.now.as_str()), (1, "karma", "fire"));
        }
        other => panic!("wrong error: {other}"),
    }
    assert!(
        format!("{err}").contains("BY NUMBER"),
        "the message must say WHY, or an operator reads it as a naming rule: {err}"
    );

    // THE ASSERTION THIS TEST EXISTS FOR. A refused switch must leave the
    // reality on a working epoch. An append-then-validate would have to DELETE
    // a row from a table whose entire guarantee is that rows are never deleted.
    assert_eq!(f.bindings.history(R1).unwrap().len(), 1, "the refusal appended a row");
    assert_eq!(f.bindings.load(R1).unwrap().unwrap().epoch, 1);
}

/// **The two-epochs-ago trap, through storage.** Against epoch 2 alone this
/// looks fine; only the union over every prior epoch catches it. This is the
/// end-to-end version of `an_ordinal_freed_two_epochs_ago_is_still_not_available`
/// and the reason `history()` exists at all.
#[test]
fn an_ordinal_freed_two_epochs_ago_is_still_refused_through_the_store() {
    let f = fixture("twoback");
    f.create(&["qi", "karma"]);
    assert_eq!(f.switch(&["qi"]).expect("dropping from the tail is permitted"), 2);

    let err = f.switch(&["qi", "fire"]).expect_err("epoch 1 still means karma by ordinal 1");
    match err {
        EpochSwitchError::OrdinalReused(r) => assert_eq!((r.ordinal, r.was.as_str()), (1, "karma")),
        other => panic!("wrong error: {other}"),
    }
    assert_eq!(f.bindings.history(R1).unwrap().len(), 2);
}

// ───────────────── the two ways the check silently examines less ─────────────────

/// A prior epoch's ruleset missing from the store must REFUSE, not skip.
///
/// Skipping would return `Ok` for exactly the reality whose history cannot be
/// verified — a check reporting coverage it does not have.
#[test]
fn a_missing_prior_ruleset_refuses_rather_than_checking_fewer_epochs() {
    let f = fixture("missingprior");
    let first = f.create(&["qi", "karma"]);
    f.switch(&["qi"]).expect("2");

    // Delete epoch 1's bytes. Its ordinals are now unknown.
    std::fs::remove_file(f.store.path_for(&first)).expect("remove");

    let err = f.switch(&["qi", "fire"]).expect_err("history is unverifiable");
    match &err {
        EpochSwitchError::PriorRulesetMissing { epoch, .. } => assert_eq!(*epoch, 1),
        other => panic!("wrong error: {other}"),
    }
    assert!(format!("{err}").contains("partial history"), "{err}");
}

#[test]
fn switching_to_a_ruleset_that_is_not_in_the_store_is_refused() {
    let f = fixture("orphan");
    f.create(&["qi"]);
    // A digest of a ruleset never `put`.
    let orphan = rules_with(&["qi", "karma"]).digest();
    let err = activate_reality_epoch(&f.bindings, &f.store, R1, &orphan, "test")
        .expect_err("bytes do not exist");
    assert!(matches!(err, EpochSwitchError::NewRulesetMissing { .. }), "{err}");
}

#[test]
fn switching_an_unbound_reality_is_not_bound_rather_than_a_silent_first_epoch() {
    let f = fixture("unbound");
    let d = f.put(&["qi"]);
    // No `create`. With an empty history the never-reuse check has nothing to
    // compare against and would permit ANY table — so an unbound reality must
    // be refused before the check, not by it.
    let err = activate_reality_epoch(&f.bindings, &f.store, R1, &d, "test")
        .expect_err("never created");
    assert!(
        matches!(err, EpochSwitchError::Binding(BindingError::NotBound { .. })),
        "{err}"
    );
    assert!(f.bindings.history(R1).unwrap().is_empty());
}

// ──────────────────────────── the on-disk shape ────────────────────────────

/// The file store used to write ONE binding at the top level. `read_history`
/// still accepts it, or every reality created before today becomes unloadable.
#[test]
fn the_one_binding_file_shape_still_reads_as_a_one_epoch_history() {
    let f = fixture("legacy");
    let d = f.put(&["qi"]);
    let root = f.dir.join("bindings");
    std::fs::create_dir_all(&root).unwrap();
    std::fs::write(
        root.join(format!("{R1}.toml")),
        format!("reality_id = \"{R1}\"\nepoch = 1\ndigest = \"{}\"\n", d.to_hex()),
    )
    .unwrap();

    let h = f.bindings.history(R1).expect("legacy shape");
    assert_eq!(h.len(), 1);
    assert_eq!(h[0].epoch, 1);
    assert_eq!(f.bindings.load(R1).unwrap().unwrap().digest, d.to_hex());
    // …and it can still be switched, which is the thing that would actually
    // break: a legacy file that reads but cannot advance is not compatible.
    assert_eq!(f.switch(&["qi", "karma"]).expect("advances"), 2);
    assert_eq!(f.bindings.history(R1).unwrap().len(), 2);
}

/// Re-activating the SAME ruleset is permitted. Without this, every test above
/// would also pass for an implementation that refused every switch — which would
/// make an epoch switch impossible rather than safe.
#[test]
fn re_activating_identical_rules_is_permitted() {
    let f = fixture("identical");
    f.create(&["qi", "karma"]);
    assert_eq!(f.switch(&["qi", "karma"]).expect("no ordinal changed meaning"), 2);
}

/// A hand-edited binding file with a corrupt digest must say **that**, not
/// "the ruleset is missing". Both refuse; only one tells the operator the right
/// thing to fix.
#[test]
fn a_corrupt_digest_in_the_history_is_a_binding_error_not_a_missing_ruleset() {
    let f = fixture("corrupt");
    f.create(&["qi", "karma"]);
    let path = f.dir.join("bindings").join(format!("{R1}.toml"));
    let body = std::fs::read_to_string(&path).unwrap();
    let corrupted = body.replace(
        &f.bindings.load(R1).unwrap().unwrap().digest,
        "not-a-digest",
    );
    std::fs::write(&path, corrupted).unwrap();

    let d = f.put(&["qi", "karma", "fire"]);
    let err = activate_reality_epoch(&f.bindings, &f.store, R1, &d, "test")
        .expect_err("the history cannot be read");
    assert!(
        matches!(err, EpochSwitchError::Binding(BindingError::BadDigest(_))),
        "a corrupt row must not be reported as missing bytes: {err}"
    );
}
