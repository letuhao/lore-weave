//! Q1 B2b — `create_reality` → `load_reality` with the binding in Postgres.
//!
//! **This is also where `Q1`'s own exit criterion is finally discharged.** Doc
//! 35 §12 states it as:
//!
//! > *"a reality declares a quantity that does not exist in the engine and it
//! > survives **create → store → load → digest** with ordinals unchanged."*
//!
//! `B1`'s loader tests reach `create → resolve → digest`. They never store and
//! never load, so *"survives the round trip"* was still a claim. Running it
//! through the **Postgres** binding rather than the file one is deliberate: the
//! file store keeps the digest in a TOML the same process just wrote, which is
//! the weakest possible round trip. Here the digest leaves the process, becomes
//! a `text` column, comes back, and has to address the same bytes.
//!
//! Run via `scripts/meta-rs-pg-live-smoke.sh`, or:
//!
//! ```text
//! META_RS_TEST_DATABASE_URL=postgres://…/loreweave_test_meta_rs_smoke \
//!   cargo test -p commit-service --test pg_binding_live
//! ```
//!
//! No DSN ⇒ SKIP, loudly. No DELETE/TRUNCATE/DROP anywhere: isolation is a
//! fresh UUID per test, which `reality_ruleset_binding` being append-only makes
//! mandatory and which is the better answer regardless.

use commit_service::pg_binding::PgBindingStore;
use ruleset_loader::{
    activate_reality_epoch, create_reality, load_reality, parse_layer, BindingError,
    BindingStore, Layer, RealityError, RulesetStore,
};
use sqlx::postgres::PgPoolOptions;
use uuid::Uuid;

const DSN_VAR: &str = "META_RS_TEST_DATABASE_URL";
const ALLOWLIST: &str = "../../contracts/meta/events_allowlist.yaml";

fn dsn() -> Option<String> {
    let raw = std::env::var(DSN_VAR).ok()?;
    let db = raw.rsplit('/').next().unwrap_or("").split('?').next().unwrap_or("");
    assert!(
        ["test", "smoke", "scratch", "throwaway", "sandbox"]
            .iter()
            .any(|m| db.contains(m)),
        "{DSN_VAR} points at `{db}`, which carries no throwaway marker"
    );
    Some(raw)
}

/// A content store under a unique temp dir, so runs never share bytes.
fn content_store(tag: &str) -> RulesetStore {
    let dir = std::env::temp_dir().join(format!("loreweave-pgbind-{tag}"));
    let _ = std::fs::remove_dir_all(&dir);
    RulesetStore::new(dir.join("content"))
}

async fn store_for(dsn: &str) -> PgBindingStore {
    let pool = PgPoolOptions::new()
        .max_connections(2)
        .connect(dsn)
        .await
        .expect("connect");
    PgBindingStore::new(pool, ALLOWLIST, "commit-service-test").expect("allowlist loads")
}

/// **`Q1`'s exit criterion, end to end.**
///
/// `qi` and `spirit_stone` are identities this engine has never heard of. They
/// are assigned ordinals 0 and 1 at creation, hashed into the ruleset, and the
/// only thing that crosses into Postgres is the digest. Loading fetches those
/// exact bytes back out of the content store and the ordinals must be the same
/// numbers — because committed events refer to a quantity BY ORDINAL, and a
/// round trip that renumbered them would silently reinterpret history.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_declared_quantity_survives_create_store_load_with_its_ordinals() {
    let Some(dsn) = dsn() else {
        eprintln!("SKIP: {DSN_VAR} unset — run scripts/meta-rs-pg-live-smoke.sh");
        return;
    };
    let bindings = store_for(&dsn).await;
    let store = content_store("ordinals");
    let reality = Uuid::new_v4().to_string();

    let layer = parse_layer(Layer::Reality, "quantities = [\"qi\", \"spirit_stone\"]\n")
        .expect("parses");
    let (created, binding) = create_reality(&reality, &[layer], &store, &bindings)
        .expect("a reality may declare its own quantities");

    assert_eq!(binding.epoch, 1, "creation assigns epoch 1 (doc 16 §12)");
    assert_eq!(created.quantities.ordinal_of("qi"), Some(0));
    assert_eq!(created.quantities.ordinal_of("spirit_stone"), Some(1));

    // …and now the part B1 could not reach: out of the process and back.
    let (loaded, lb) = load_reality(&reality, &store, &bindings).expect("loads");
    let digest = ruleset_core::RulesetDigest::from_hex(&lb.digest).expect("64 hex");
    assert_eq!(lb.epoch, 1, "the epoch must survive the round trip, not just the digest");
    assert_eq!(
        digest.to_hex(),
        binding.digest,
        "the digest that came back out of Postgres must address the bytes that \
         went in"
    );
    assert_eq!(loaded, created, "the whole ruleset round-trips byte-identically");
    assert_eq!(
        loaded.quantities.ordinal_of("qi"),
        Some(0),
        "an ordinal that moved across a round trip would silently reinterpret \
         every committed event that referred to this quantity by number (QTY-A5)"
    );
    assert_eq!(loaded.quantities.ordinal_of("spirit_stone"), Some(1));
    assert_eq!(loaded.quantities.name_of(0).map(|n| n.as_str()), Some("qi"));
}

/// `RLS-A3`: creation happens ONCE. Through Postgres this is enforced by
/// migration 033's trigger rather than by a `path.exists()` check, so unlike the
/// file store it holds between two nodes racing to create the same reality — the
/// refusal comes from the same statement that would have performed the write.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_second_creation_is_refused_by_the_database() {
    let Some(dsn) = dsn() else {
        eprintln!("SKIP: {DSN_VAR} unset");
        return;
    };
    let bindings = store_for(&dsn).await;
    let store = content_store("twice");
    let reality = Uuid::new_v4().to_string();
    let layer = || parse_layer(Layer::Reality, "quantities = [\"qi\"]\n").unwrap();

    let (_, first) = create_reality(&reality, &[layer()], &store, &bindings).expect("first");

    let err = create_reality(&reality, &[layer()], &store, &bindings)
        .expect_err("RLS-A3 binds once");
    match err {
        RealityError::Binding(BindingError::AlreadyBound { existing, .. }) => {
            assert!(
                existing.contains(&first.digest),
                "the refusal must name what the reality is ALREADY bound to, or an \
                 operator cannot tell a duplicate create from a corrupted one: {existing}"
            );
        }
        other => panic!("expected AlreadyBound, got {other}"),
    }
}

/// Loading a reality nobody created must be an error, not an empty default.
/// A `Ruleset::engine_default()` returned here would start an island on rules
/// that are not the reality's, with a digest that does not match its events.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn loading_an_unknown_reality_is_refused_rather_than_defaulted() {
    let Some(dsn) = dsn() else {
        eprintln!("SKIP: {DSN_VAR} unset");
        return;
    };
    let bindings = store_for(&dsn).await;
    let store = content_store("unknown");
    let reality = Uuid::new_v4().to_string();

    let err = load_reality(&reality, &store, &bindings).expect_err("never created");
    assert!(
        matches!(err, RealityError::Binding(BindingError::NotBound { .. })),
        "got {err}"
    );
}

/// The `--meta-url` path must reject a reality id that is not a UUID **before**
/// it reaches the database. The column is `uuid`; without this the operator's
/// typo comes back as a Postgres type error from inside a transaction.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_non_uuid_reality_id_is_refused_before_any_sql() {
    let Some(dsn) = dsn() else {
        eprintln!("SKIP: {DSN_VAR} unset");
        return;
    };
    let bindings = store_for(&dsn).await;
    let store = content_store("baduuid");
    let layer = parse_layer(Layer::Reality, "quantities = [\"qi\"]\n").unwrap();

    let err = create_reality("not-a-uuid", &[layer], &store, &bindings).expect_err("refused");
    let msg = format!("{err}");
    assert!(msg.contains("not a uuid"), "{msg}");
}

// ═══════════════════ Q0b B1b — the epoch switch, in Postgres ═══════════════════
//
// The loader tests prove the law against a TOML file the same process wrote.
// Everything that can actually defeat the never-reuse check lives on the other
// side of the wire: `history()` is a QUERY, and a query that comes back short
// makes every switch trivially permitted while still returning `Ok`.

/// Put a ruleset carrying exactly these quantities into the content store.
fn put_quantities(store: &RulesetStore, names: &[&str]) -> ruleset_core::RulesetDigest {
    let toml = format!(
        "quantities = [{}]\n",
        names.iter().map(|n| format!("\"{n}\"")).collect::<Vec<_>>().join(", ")
    );
    let layer = parse_layer(Layer::Reality, &toml).expect("parses");
    let resolved = ruleset_loader::resolve(&[layer]).expect("resolves");
    store.put(&resolved).expect("put")
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn an_epoch_switch_appends_a_row_and_history_comes_back_ascending() {
    let Some(dsn) = dsn() else {
        eprintln!("SKIP: {DSN_VAR} unset — run scripts/meta-rs-pg-live-smoke.sh");
        return;
    };
    let bindings = store_for(&dsn).await;
    let store = content_store("switch-append");
    let reality = Uuid::new_v4().to_string();

    let layer = parse_layer(Layer::Reality, "quantities = [\"qi\"]\n").expect("parses");
    create_reality(&reality, &[layer], &store, &bindings).expect("created");

    let d2 = put_quantities(&store, &["qi", "karma"]);
    let d3 = put_quantities(&store, &["qi", "karma", "fire"]);
    assert_eq!(
        activate_reality_epoch(&bindings, &store, &reality, &d2, "test switch 2")
            .expect("additive")
            .epoch,
        2
    );
    assert_eq!(
        activate_reality_epoch(&bindings, &store, &reality, &d3, "test switch 3")
            .expect("additive")
            .epoch,
        3
    );

    // The query, not the in-process value. Three rows, ascending, none lost —
    // this is what migration 033's one-row-per-epoch shape exists to make true,
    // and what a mutable `ruleset_digest` column would have destroyed.
    let history = bindings.history(&reality).expect("history");
    assert_eq!(history.iter().map(|b| b.epoch).collect::<Vec<_>>(), vec![1, 2, 3]);
    assert_eq!(history[2].digest, d3.to_hex());
    assert_eq!(
        bindings.load(&reality).expect("load").expect("bound").epoch,
        3,
        "load must return the NEWEST epoch, or an epoch switch appears to do nothing"
    );
}

/// **The refusal, computed over a history that came out of Postgres.**
///
/// `karma` is declared at epoch 1, dropped at epoch 2, and epoch 3 tries to put
/// `fire` on the ordinal it freed. Against epoch 2 alone this looks legal. Only
/// the union over every row catches it — so this test fails the moment
/// `history()` grows a `LIMIT`, which is the realistic way this breaks.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn the_never_reuse_refusal_holds_over_a_history_read_from_postgres() {
    let Some(dsn) = dsn() else {
        eprintln!("SKIP: {DSN_VAR} unset — run scripts/meta-rs-pg-live-smoke.sh");
        return;
    };
    let bindings = store_for(&dsn).await;
    let store = content_store("switch-refuse");
    let reality = Uuid::new_v4().to_string();

    let layer = parse_layer(Layer::Reality, "quantities = [\"qi\", \"karma\"]\n").expect("parses");
    create_reality(&reality, &[layer], &store, &bindings).expect("created");

    let dropped = put_quantities(&store, &["qi"]);
    activate_reality_epoch(&bindings, &store, &reality, &dropped, "drop karma")
        .expect("dropping from the tail is permitted");

    let reused = put_quantities(&store, &["qi", "fire"]);
    let err = activate_reality_epoch(&bindings, &store, &reality, &reused, "reuse")
        .expect_err("epoch 1 still means karma by ordinal 1");
    assert!(
        matches!(err, ruleset_loader::EpochSwitchError::OrdinalReused(ref r)
                 if r.ordinal == 1 && r.was == "karma"),
        "{err}"
    );

    // The refusal must not have written. `reality_ruleset_binding` is
    // append-only with an ENABLE ALWAYS trigger, so a row appended by a
    // validate-after-append design could not be taken back.
    assert_eq!(bindings.history(&reality).expect("history").len(), 2);
    assert_eq!(bindings.load(&reality).expect("load").expect("bound").epoch, 2);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn switching_a_reality_that_was_never_created_is_refused() {
    let Some(dsn) = dsn() else {
        eprintln!("SKIP: {DSN_VAR} unset — run scripts/meta-rs-pg-live-smoke.sh");
        return;
    };
    let bindings = store_for(&dsn).await;
    let store = content_store("switch-unbound");
    let reality = Uuid::new_v4().to_string();
    let d = put_quantities(&store, &["qi"]);

    let err = activate_reality_epoch(&bindings, &store, &reality, &d, "no create")
        .expect_err("never created");
    assert!(
        matches!(err, ruleset_loader::EpochSwitchError::Binding(BindingError::NotBound { .. })),
        "{err}"
    );
    assert!(bindings.history(&reality).expect("history").is_empty());
}
