//! R1 integration — tenancy denies + start-orchestration round-trip.
//!
//! Gated on `LOREWEAVE_TEST_PG_URL` (a reachable Postgres for `loreweave_roleplay`);
//! skips cleanly when unset so `cargo test` is green without infra. Run with:
//!   LOREWEAVE_TEST_PG_URL=postgres://loreweave:loreweave_dev@localhost:5555/loreweave_roleplay \
//!     cargo test -p roleplay-service --test integration -- --nocapture
//!
//! chat-service is mocked with wiremock; the test asserts the frozen seed
//! payload AND reads back `rp_sessions` / `rp_memory` (spec §10.6).

use axum::Router;
use axum::body::Body;
use axum::http::{Request, StatusCode, header::AUTHORIZATION, header::CONTENT_TYPE};
use jsonwebtoken::{Algorithm, EncodingKey, Header, encode};
use roleplay_service::{AppState, Config, build_router};
use serde::Serialize;
use serde_json::{Value, json};
use sqlx::postgres::PgPoolOptions;
use tower::ServiceExt;
use uuid::Uuid;
use wiremock::matchers::{method, path};
use wiremock::{Mock, MockServer, ResponseTemplate};

const SECRET: &[u8] = b"test_secret_value_at_least_32_chars_x";
const FUTURE_EXP: usize = 4_102_444_800; // 2100-01-01

#[derive(Serialize)]
struct Claims {
    sub: String,
    exp: usize,
}

fn token(uid: Uuid) -> String {
    encode(
        &Header::new(Algorithm::HS256),
        &Claims { sub: uid.to_string(), exp: FUTURE_EXP },
        &EncodingKey::from_secret(SECRET),
    )
    .unwrap()
}

fn get(uri: &str, tok: &str) -> Request<Body> {
    Request::builder().method("GET").uri(uri).header(AUTHORIZATION, format!("Bearer {tok}")).body(Body::empty()).unwrap()
}

fn body_req(m: &str, uri: &str, tok: &str, json: &Value) -> Request<Body> {
    Request::builder()
        .method(m)
        .uri(uri)
        .header(AUTHORIZATION, format!("Bearer {tok}"))
        .header(CONTENT_TYPE, "application/json")
        .body(Body::from(serde_json::to_vec(json).unwrap()))
        .unwrap()
}

async fn send(router: Router, req: Request<Body>) -> (StatusCode, Value) {
    let resp = router.oneshot(req).await.unwrap();
    let status = resp.status();
    let bytes = axum::body::to_bytes(resp.into_body(), 1 << 20).await.unwrap();
    let body = serde_json::from_slice(&bytes).unwrap_or(Value::Null);
    (status, body)
}

#[tokio::test]
async fn r1_tenancy_and_start_roundtrip() {
    let Ok(pg_url) = std::env::var("LOREWEAVE_TEST_PG_URL") else {
        eprintln!("SKIP r1_tenancy_and_start_roundtrip: LOREWEAVE_TEST_PG_URL unset");
        return;
    };

    // Mock chat-service internal create-session.
    let chat = MockServer::start().await;
    let sid = Uuid::new_v4();
    Mock::given(method("POST"))
        .and(path("/internal/chat/sessions"))
        .respond_with(ResponseTemplate::new(201).set_body_json(json!({"session_id": sid.to_string()})))
        .expect(1)
        .mount(&chat)
        .await;

    let pool = PgPoolOptions::new().max_connections(4).connect(&pg_url).await.expect("connect test pg");
    sqlx::migrate!("./migrations").run(&pool).await.expect("migrate");

    let config = Config {
        bind: "0.0.0.0:7110".parse().unwrap(),
        database_url: pg_url.clone(),
        jwt_secret: String::from_utf8(SECRET.to_vec()).unwrap(),
        internal_token: "tok".into(),
        chat_url: chat.uri(),
    };
    let state = AppState::new(pool.clone(), &config);
    let router = build_router(state);

    let user_a = Uuid::new_v4();
    let user_b = Uuid::new_v4();
    let code = format!("itest_{}", Uuid::new_v4().simple());
    let model_ref = Uuid::new_v4();

    // --- create as A (carry a model so /start resolves without an override) ---
    let create_body = json!({
        "code": code, "name": "ITest", "system_prompt": "sp",
        "model_source": "user_model", "model_ref": model_ref,
        "scenario": {"premise": "p", "beats": ["b1"]}
    });
    let (st, body) = send(router.clone(), body_req("POST", "/v1/roleplay/scripts", &token(user_a), &create_body)).await;
    assert_eq!(st, StatusCode::CREATED, "create failed: {body}");
    let script_id = body["script_id"].as_str().unwrap().to_string();
    assert_eq!(body["tier"], "user");
    assert_eq!(body["owner_user_id"], user_a.to_string());

    // --- tenancy: A sees own; B does not; B cannot patch; System cannot be patched ---
    let (st, _) = send(router.clone(), get(&format!("/v1/roleplay/scripts/{script_id}"), &token(user_a))).await;
    assert_eq!(st, StatusCode::OK, "A must see own script");

    let (st, _) = send(router.clone(), get(&format!("/v1/roleplay/scripts/{script_id}"), &token(user_b))).await;
    assert_eq!(st, StatusCode::NOT_FOUND, "cross-user GET must 404");

    let (st, _) = send(
        router.clone(),
        body_req("PATCH", &format!("/v1/roleplay/scripts/{script_id}"), &token(user_b), &json!({"name": "hax"})),
    )
    .await;
    assert_eq!(st, StatusCode::NOT_FOUND, "cross-user PATCH must 404");

    let sys: (Uuid,) = sqlx::query_as(
        "SELECT script_id FROM roleplay_scripts WHERE code='faang_swe' AND owner_user_id IS NULL",
    )
    .fetch_one(&pool)
    .await
    .expect("System faang_swe seeded");
    let (st, _) = send(
        router.clone(),
        body_req("PATCH", &format!("/v1/roleplay/scripts/{}", sys.0), &token(user_a), &json!({"name": "hax"})),
    )
    .await;
    assert_eq!(st, StatusCode::NOT_FOUND, "System PATCH must 404");
    let sys_name: (String,) = sqlx::query_as("SELECT name FROM roleplay_scripts WHERE script_id=$1")
        .bind(sys.0)
        .fetch_one(&pool)
        .await
        .unwrap();
    assert_eq!(sys_name.0, "FAANG SWE Interview", "System row must be untouched");

    // --- create with NO scenario → defaults to {} (not null / not a 500) ---
    let code2 = format!("itest2_{}", Uuid::new_v4().simple());
    let (st, body2) = send(
        router.clone(),
        body_req("POST", "/v1/roleplay/scripts", &token(user_a),
            &json!({"code": code2, "name": "NoScenario", "system_prompt": "sp"})),
    )
    .await;
    assert_eq!(st, StatusCode::CREATED, "create without scenario must succeed: {body2}");
    assert_eq!(body2["scenario"], json!({}), "omitted scenario must default to {{}}, got {}", body2["scenario"]);
    let _ = sqlx::query("DELETE FROM roleplay_scripts WHERE script_id=$1")
        .bind(Uuid::parse_str(body2["script_id"].as_str().unwrap()).unwrap())
        .execute(&pool).await;

    // --- list merge: a user script shadows a System script of the same code ---
    let shadow = send(
        router.clone(),
        body_req("POST", "/v1/roleplay/scripts", &token(user_a),
            &json!({"code": "faang_swe", "name": "My FAANG override", "system_prompt": "sp"})),
    )
    .await;
    assert_eq!(shadow.0, StatusCode::CREATED, "user may create a script with a System code: {}", shadow.1);
    let shadow_id = shadow.1["script_id"].as_str().unwrap().to_string();
    let (_, list) = send(router.clone(), get("/v1/roleplay/scripts", &token(user_a))).await;
    let faang_rows: Vec<&Value> = list.as_array().unwrap().iter().filter(|s| s["code"] == "faang_swe").collect();
    assert_eq!(faang_rows.len(), 1, "DISTINCT ON (code) must collapse to one faang_swe row");
    assert_eq!(faang_rows[0]["owner_user_id"], user_a.to_string(), "the user's row must shadow the System one");
    assert_eq!(faang_rows[0]["name"], "My FAANG override");
    let _ = sqlx::query("DELETE FROM roleplay_scripts WHERE script_id=$1")
        .bind(Uuid::parse_str(&shadow_id).unwrap()).execute(&pool).await;

    // --- start-orchestration round-trip ---
    let (st, body) = send(
        router.clone(),
        body_req("POST", &format!("/v1/roleplay/scripts/{script_id}/start"), &token(user_a), &json!({})),
    )
    .await;
    assert_eq!(st, StatusCode::CREATED, "start failed: {body}");
    assert_eq!(body["session_id"], sid.to_string());

    // rp_memory read-back (§10.6): charter frozen from the scenario.
    let mem: (Value,) = sqlx::query_as("SELECT charter FROM rp_memory WHERE session_id=$1")
        .bind(sid)
        .fetch_one(&pool)
        .await
        .expect("rp_memory row written");
    assert_eq!(mem.0["goal"], "p", "premise → goal");
    assert_eq!(mem.0["checklist"], json!(["b1"]), "beats → checklist");

    let sess: (Uuid,) = sqlx::query_as("SELECT owner_user_id FROM rp_sessions WHERE session_id=$1")
        .bind(sid)
        .fetch_one(&pool)
        .await
        .expect("rp_sessions row written");
    assert_eq!(sess.0, user_a);

    // chat-service received the frozen seed with the JWT owner (not the body).
    let reqs = chat.received_requests().await.unwrap();
    assert_eq!(reqs.len(), 1);
    let sent: Value = serde_json::from_slice(&reqs[0].body).unwrap();
    assert_eq!(sent["owner_user_id"], user_a.to_string());
    assert_eq!(sent["model_source"], "user_model");
    assert_eq!(sent["working_memory_seed"]["charter"]["goal"], "p");
    assert_eq!(sent["working_memory_seed"]["version"], 1);

    // cleanup
    let _ = sqlx::query("DELETE FROM rp_memory WHERE session_id=$1").bind(sid).execute(&pool).await;
    let _ = sqlx::query("DELETE FROM rp_sessions WHERE session_id=$1").bind(sid).execute(&pool).await;
    let _ = sqlx::query("DELETE FROM roleplay_scripts WHERE script_id=$1")
        .bind(Uuid::parse_str(&script_id).unwrap())
        .execute(&pool)
        .await;
}
