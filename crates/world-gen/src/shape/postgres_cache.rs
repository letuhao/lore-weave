//! **v4.3e** Postgres-backed [`DispatchCache`] for shared LLM dispatch
//! caching across processes.
//!
//! Use case: once `world-gen` is embedded into a platform service that
//! runs Postgres anyway, sharing the dispatch cache across worker
//! processes / restarts means the second-and-later renders of a world
//! pay zero LLM round-trip cost regardless of which worker handles them.
//! Today's CLI keeps using [`InMemoryDispatchCache`] from
//! [`crate::shape::llm`]; this module is the trait validation that the
//! abstraction also serves a real DB impl.
//!
//! ## Schema
//!
//! ```sql
//! CREATE TABLE IF NOT EXISTS shape_dispatch_cache (
//!     entity_path TEXT PRIMARY KEY,
//!     kind        TEXT NOT NULL,
//!     params      JSONB NULL
//! );
//! ```
//!
//! ## Sync→async bridge
//!
//! [`DispatchCache::get`] and `put` are sync (the dispatcher is sync).
//! `sqlx` is async-only, so each call wraps the query in
//! [`tokio::runtime::Handle::block_on`] on the runtime owned by the
//! cache instance. The runtime is `current_thread` — one worker thread,
//! no spawning — which keeps the bridge predictable and zero-overhead
//! when no calls are happening.

use std::sync::Arc;

use sqlx::PgPool;
use tokio::runtime::Runtime;

use crate::shape::llm::{DispatchCache, LlmDecision};
use crate::shape::ParamOverride;

const CREATE_TABLE_SQL: &str = "
CREATE TABLE IF NOT EXISTS shape_dispatch_cache (
    entity_path TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    params      JSONB NULL
);
";

const GET_SQL: &str =
    "SELECT kind, params FROM shape_dispatch_cache WHERE entity_path = $1";

const PUT_SQL: &str = "
INSERT INTO shape_dispatch_cache (entity_path, kind, params)
VALUES ($1, $2, $3)
ON CONFLICT (entity_path) DO UPDATE SET
    kind   = EXCLUDED.kind,
    params = EXCLUDED.params;
";

/// Postgres-backed [`DispatchCache`]. Owns the [`PgPool`] **and** a
/// dedicated tokio runtime for the sync→async bridge — clone-cheap via
/// `Arc<PgPool>` / `Arc<Runtime>` if you want multiple cache handles to
/// share the pool, but typically one instance is enough per process.
pub struct PostgresDispatchCache {
    pool: Arc<PgPool>,
    rt: Arc<Runtime>,
}

impl std::fmt::Debug for PostgresDispatchCache {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("PostgresDispatchCache")
            .field("pool_size", &self.pool.size())
            .finish()
    }
}

/// Errors returned by [`PostgresDispatchCache::connect`] and
/// [`PostgresDispatchCache::init_schema`]. `DispatchCache::get` / `put`
/// **don't** propagate errors — a transient DB failure resolves to a
/// cache miss (`get -> None`) or a silent put-skip — so the LLM round-
/// trip path still works even when the cache is misbehaving. The
/// rationale: dispatch is best-effort, the deterministic Layered
/// fallback (`Weighted`) catches anything that slips through.
#[derive(Debug)]
pub enum PostgresCacheError {
    Connect(sqlx::Error),
    SchemaInit(sqlx::Error),
    Runtime(std::io::Error),
}

impl std::fmt::Display for PostgresCacheError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            PostgresCacheError::Connect(e) => write!(f, "postgres connect: {e}"),
            PostgresCacheError::SchemaInit(e) => write!(f, "postgres schema init: {e}"),
            PostgresCacheError::Runtime(e) => write!(f, "tokio runtime build: {e}"),
        }
    }
}

impl std::error::Error for PostgresCacheError {}

impl PostgresDispatchCache {
    /// Connect to `database_url` (libpq format,
    /// `postgres://user:pass@host:port/db`) and prepare a connection
    /// pool. Doesn't create the schema — call [`init_schema`] right
    /// after if you want CREATE TABLE IF NOT EXISTS to run.
    pub fn connect(database_url: &str) -> Result<Self, PostgresCacheError> {
        let rt = Runtime::new().map_err(PostgresCacheError::Runtime)?;
        let pool = rt
            .block_on(async {
                sqlx::postgres::PgPoolOptions::new()
                    .max_connections(8)
                    .connect(database_url)
                    .await
            })
            .map_err(PostgresCacheError::Connect)?;
        Ok(Self {
            pool: Arc::new(pool),
            rt: Arc::new(rt),
        })
    }

    /// Create the `shape_dispatch_cache` table if missing. Idempotent —
    /// safe to call on every process start.
    pub fn init_schema(&self) -> Result<(), PostgresCacheError> {
        let pool = self.pool.clone();
        self.rt
            .block_on(async move {
                sqlx::query(CREATE_TABLE_SQL).execute(pool.as_ref()).await
            })
            .map(|_| ())
            .map_err(PostgresCacheError::SchemaInit)
    }
}

impl DispatchCache for PostgresDispatchCache {
    fn get(&self, key: &str) -> Option<LlmDecision> {
        let pool = self.pool.clone();
        let key_owned = key.to_string();
        let row: Result<(String, Option<serde_json::Value>), sqlx::Error> =
            self.rt.block_on(async move {
                sqlx::query_as::<_, (String, Option<serde_json::Value>)>(GET_SQL)
                    .bind(&key_owned)
                    .fetch_one(pool.as_ref())
                    .await
            });
        let (kind_str, params_json) = row.ok()?;
        let kind = crate::shape::llm::parse_shape_kind_str(&kind_str).ok()?;
        let params = decode_params_json(kind, params_json);
        Some(LlmDecision { kind, params })
    }

    fn put(&self, key: &str, value: LlmDecision) {
        let pool = self.pool.clone();
        let key_owned = key.to_string();
        let kind_str = format!("{:?}", value.kind);
        let params_json = encode_params_json(value.params.as_ref());
        // Best-effort: ignore DB write failure — Layered fallback in the
        // dispatcher still produces a valid kind from the Weighted layer.
        let _: Result<_, sqlx::Error> = self.rt.block_on(async move {
            sqlx::query(PUT_SQL)
                .bind(&key_owned)
                .bind(&kind_str)
                .bind(&params_json)
                .execute(pool.as_ref())
                .await
        });
    }
}

fn encode_params_json(params: Option<&ParamOverride>) -> Option<serde_json::Value> {
    use crate::shape::csg::BooleanTemplate;
    Some(match params? {
        ParamOverride::Ellipse { aspect_ratio } => {
            let mut obj = serde_json::Map::new();
            if let Some(r) = aspect_ratio {
                obj.insert(
                    "aspect_ratio".to_string(),
                    serde_json::Value::from(*r as f64),
                );
            }
            serde_json::json!({ "ellipse": serde_json::Value::Object(obj) })
        }
        ParamOverride::Boolean { template } => {
            let mut obj = serde_json::Map::new();
            if let Some(t) = template {
                let s = match t {
                    BooleanTemplate::EllipseUnion => "EllipseUnion",
                    BooleanTemplate::EllipseDifference => "EllipseDifference",
                    BooleanTemplate::WedgeCut => "WedgeCut",
                    BooleanTemplate::Ring => "Ring",
                };
                obj.insert("template".to_string(), serde_json::Value::from(s));
            }
            serde_json::json!({ "boolean": serde_json::Value::Object(obj) })
        }
        ParamOverride::Stamp { template_id } => {
            let mut obj = serde_json::Map::new();
            if let Some(id) = template_id {
                obj.insert("template_id".to_string(), serde_json::Value::from(*id));
            }
            serde_json::json!({ "stamp": serde_json::Value::Object(obj) })
        }
    })
}

fn decode_params_json(
    kind: crate::shape::ShapeKind,
    params_json: Option<serde_json::Value>,
) -> Option<ParamOverride> {
    let val = params_json?;
    crate::shape::llm::parse_params_from_value(kind, Some(&val)).ok().flatten()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shape::csg::BooleanTemplate;
    use crate::shape::ShapeKind;

    #[test]
    fn schema_sql_creates_required_columns() {
        // Sanity-check the schema string: the columns the trait depends
        // on must be named and typed correctly.
        assert!(CREATE_TABLE_SQL.contains("shape_dispatch_cache"));
        assert!(CREATE_TABLE_SQL.contains("entity_path TEXT PRIMARY KEY"));
        assert!(CREATE_TABLE_SQL.contains("kind        TEXT NOT NULL"));
        assert!(CREATE_TABLE_SQL.contains("params      JSONB NULL"));
        assert!(CREATE_TABLE_SQL.contains("IF NOT EXISTS"));
    }

    #[test]
    fn put_sql_upserts_via_on_conflict() {
        // `put` must overwrite, not duplicate-key-error, when the same
        // entity_path is written twice. ON CONFLICT clause is the contract.
        assert!(PUT_SQL.contains("ON CONFLICT (entity_path)"));
        assert!(PUT_SQL.contains("EXCLUDED.kind"));
        assert!(PUT_SQL.contains("EXCLUDED.params"));
    }

    #[test]
    fn get_sql_filters_by_entity_path() {
        assert!(GET_SQL.contains("WHERE entity_path = $1"));
        assert!(GET_SQL.contains("SELECT kind, params"));
    }

    #[test]
    fn encode_decode_ellipse_round_trips() {
        let params = ParamOverride::Ellipse { aspect_ratio: Some(1.75) };
        let encoded = encode_params_json(Some(&params)).expect("Ellipse should encode");
        let decoded = decode_params_json(ShapeKind::Ellipse, Some(encoded))
            .expect("Ellipse should decode");
        match decoded {
            ParamOverride::Ellipse { aspect_ratio: Some(r) } => {
                assert!((r - 1.75).abs() < 1e-4, "aspect_ratio drift: got {r}");
            }
            other => panic!("expected Ellipse, got {other:?}"),
        }
    }

    #[test]
    fn encode_decode_boolean_round_trips() {
        let params = ParamOverride::Boolean {
            template: Some(BooleanTemplate::WedgeCut),
        };
        let encoded = encode_params_json(Some(&params)).expect("Boolean should encode");
        let decoded = decode_params_json(ShapeKind::Boolean, Some(encoded))
            .expect("Boolean should decode");
        assert!(matches!(
            decoded,
            ParamOverride::Boolean { template: Some(BooleanTemplate::WedgeCut) }
        ));
    }

    #[test]
    fn encode_decode_stamp_round_trips() {
        let params = ParamOverride::Stamp { template_id: Some(5) };
        let encoded = encode_params_json(Some(&params)).expect("Stamp should encode");
        let decoded = decode_params_json(ShapeKind::Stamp, Some(encoded))
            .expect("Stamp should decode");
        assert!(matches!(
            decoded,
            ParamOverride::Stamp { template_id: Some(5) }
        ));
    }

    #[test]
    fn encode_returns_none_for_none_params() {
        assert!(encode_params_json(None).is_none());
    }

    /// Integration test against a real Postgres. Enable with
    /// `TEST_DATABASE_URL=postgres://... cargo test --lib -p world-gen --
    /// shape::postgres_cache::tests::round_trip_against_real_postgres
    /// --ignored`. CI skips it by default.
    #[test]
    #[ignore = "requires TEST_DATABASE_URL; not run by default CI"]
    fn round_trip_against_real_postgres() {
        let url = std::env::var("TEST_DATABASE_URL")
            .expect("set TEST_DATABASE_URL=postgres://... to run this test");
        let cache = PostgresDispatchCache::connect(&url)
            .expect("connect should succeed against TEST_DATABASE_URL");
        cache.init_schema().expect("schema init should succeed");
        let key = format!("test.{}", std::process::id());
        assert!(cache.get(&key).is_none(), "cold path should miss");
        cache.put(
            &key,
            LlmDecision {
                kind: ShapeKind::Stamp,
                params: Some(ParamOverride::Stamp { template_id: Some(3) }),
            },
        );
        let hit = cache.get(&key).expect("warm path should hit");
        assert_eq!(hit.kind, ShapeKind::Stamp);
        assert!(matches!(
            hit.params,
            Some(ParamOverride::Stamp { template_id: Some(3) })
        ));
    }
}
