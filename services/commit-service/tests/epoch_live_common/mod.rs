//! Shared harness for the `Q0b B3` live tests.
//!
//! A `tests/<dir>/mod.rs` is NOT compiled as its own integration-test binary —
//! only files directly under `tests/` are — so this is the idiomatic place for
//! a fixture two test files share. It exists because `epoch_activation_live.rs`
//! crossed its `IMP-D3` ceiling and the answer to that is a split, never a
//! raised allowlist: the harness (DSN guards, content store, island builder,
//! the channel-log query) is a different concern from the assertions, and it is
//! the half a second live file would otherwise copy.

#![allow(dead_code)] // each test file uses a subset; unused-in-one is not dead.

use std::sync::Arc;

use commit_service::pg_binding::PgBindingStore;
use commit_service::ruleset_boot::RulesetBoot;
use commit_service::{Actor, CombatDomain, CombatState};
use ruleset_loader::{parse_layer, Layer, RulesetStore};
use sim_core::{EntityId, Island, IslandId, RulesetEpoch, SeenWindow};
use sqlx::postgres::PgPoolOptions;
use sqlx::Row;
use uuid::Uuid;

pub const META_DSN_VAR: &str = "EPOCH_META_TEST_DATABASE_URL";
pub const CHANNEL_DSN_VAR: &str = "EPOCH_CHANNEL_TEST_DATABASE_URL";
pub const ALLOWLIST: &str = "../../contracts/meta/events_allowlist.yaml";

/// Refuse a DSN whose database name does not announce itself as disposable.
///
/// This runs BEFORE anything touches the server. The rule it enforces is the
/// one an unscoped `DELETE FROM books` broke once, against the real book DB,
/// unrecoverably: a test fixture may only point at a throwaway.
pub fn guarded(var: &str) -> Option<String> {
    let raw = std::env::var(var).ok()?;
    let db = raw.rsplit('/').next().unwrap_or("").split('?').next().unwrap_or("");
    assert!(
        ["test", "smoke", "scratch", "throwaway", "sandbox"].iter().any(|m| db.contains(m)),
        "{var} points at `{db}`, which carries no throwaway marker"
    );
    Some(raw)
}

pub fn dsns() -> Option<(String, String)> {
    Some((guarded(META_DSN_VAR)?, guarded(CHANNEL_DSN_VAR)?))
}

pub fn content_store(tag: &str) -> RulesetStore {
    let dir = std::env::temp_dir().join(format!("loreweave-epoch-{tag}"));
    let _ = std::fs::remove_dir_all(&dir);
    RulesetStore::new(dir.join("content"))
}

/// A ruleset carrying exactly these quantities — distinct names ⇒ distinct
/// bytes ⇒ a distinct digest, which is what makes an epoch switch observable.
pub fn put_quantities(store: &RulesetStore, names: &[&str]) -> ruleset_core::RulesetDigest {
    let toml = format!(
        "quantities = [{}]\n",
        names.iter().map(|n| format!("\"{n}\"")).collect::<Vec<_>>().join(", ")
    );
    let layer = parse_layer(Layer::Reality, &toml).expect("parses");
    store.put(&ruleset_loader::resolve(&[layer]).expect("resolves")).expect("put")
}

pub async fn boot_for(meta_dsn: &str, tag: &str) -> RulesetBoot {
    let pool = PgPoolOptions::new().max_connections(2).connect(meta_dsn).await.expect("meta");
    RulesetBoot {
        store: content_store(tag),
        bindings: Box::new(
            PgBindingStore::new(pool, ALLOWLIST, "commit-service-test").expect("allowlist"),
        ),
        provenance: "test meta DB".into(),
    }
}

pub fn island(rules: Arc<ruleset_core::Ruleset>, epoch: RulesetEpoch, channel: i64) -> Island<CombatDomain> {
    let mut state = CombatState::default();
    state.actors.insert(EntityId(1), Actor::new(&rules, 100));
    let mut isle = Island::new(
        IslandId(channel as u64),
        0x53A5_71DE,
        epoch,
        rules,
        SeenWindow::TtlTicks(300),
        state,
    );
    isle.spawn_entity(EntityId(1));
    isle
}

/// Every `ruleset.epoch_activated` row this channel holds, oldest first, as
/// `(event_type, payload, ruleset_digest, metadata)`.
pub async fn activation_rows(
    pool: &sqlx::PgPool,
    reality: Uuid,
) -> Vec<(String, serde_json::Value, Option<String>, serde_json::Value)> {
    sqlx::query(
        "SELECT event_type, payload, ruleset_digest, metadata FROM events \
         WHERE reality_id = $1 AND event_type = 'ruleset.epoch_activated' \
         ORDER BY aggregate_version ASC",
    )
    .bind(reality)
    .fetch_all(pool)
    .await
    .expect("read the channel log")
    .into_iter()
    .map(|r| {
        (
            r.get::<String, _>("event_type"),
            r.get::<serde_json::Value, _>("payload"),
            r.try_get::<Option<String>, _>("ruleset_digest").unwrap_or(None),
            r.try_get::<Option<serde_json::Value>, _>("metadata")
                .ok()
                .flatten()
                .unwrap_or(serde_json::Value::Null),
        )
    })
    .collect()
}
