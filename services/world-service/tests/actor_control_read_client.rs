//! `RA2` — the Rust half of the audited cross-user read.
//!
//! `D-PC-NO-RUST-READ-AUDIT`. `BridgeClient::read_actor_control` is the ONLY way
//! Rust may ask *who drives this actor*: the answer lives in
//! `actor_control_binding`, and a read of it keyed by actor with no user
//! predicate is `actor_binding_cross_user` — a sensitive path whose
//! `meta_read_audit` row is written on the Go side. A `SELECT` here would be a
//! second read with no audit row.
//!
//! So the round trip is the point, and these tests pin the round trip: the
//! REQUEST the client sends and how it reads each REPLY. A stub server rather
//! than a live bridge, because what can go wrong here is the client's own
//! parsing — the live proof that the audit row lands belongs to the bridge.

use uuid::Uuid;
use wiremock::matchers::{body_json, header, method, path};
use wiremock::{Mock, MockServer, ResponseTemplate};

use world_service::provisioner_live::BridgeClient;

const REALITY: &str = "11111111-1111-4111-8111-111111111111";
const ACTOR: &str = "22222222-2222-4222-8222-222222222222";
const DRIVER: &str = "33333333-3333-4333-8333-333333333333";

fn ids() -> (Uuid, Uuid) {
    (Uuid::parse_str(REALITY).unwrap(), Uuid::parse_str(ACTOR).unwrap())
}

/// The request: right route, right token, right body — and NO user field.
///
/// The absent user is the assertion that matters. A read carrying one would be
/// owner-scoped, which is a different question with different audit rules; this
/// one is deliberately the cross-user form, and `body_json` fails if an extra
/// field appears.
#[tokio::test]
async fn the_request_is_the_cross_user_form() {
    let server = MockServer::start().await;
    Mock::given(method("POST"))
        .and(path("/internal/provisioner/read-actor-control"))
        .and(header("X-Service-Token", "tok"))
        .and(body_json(serde_json::json!({
            "reality_id": REALITY,
            "actor_id": ACTOR,
        })))
        .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
            "driven": true, "user_ref_id": DRIVER, "binding_id": Uuid::new_v4().to_string(),
        })))
        .expect(1)
        .mount(&server)
        .await;

    let (r, a) = ids();
    let got = BridgeClient::new(server.uri(), String::from("tok")).read_actor_control(r, a).await;
    assert_eq!(
        got.as_ref().ok().and_then(|o| *o),
        Some(Uuid::parse_str(DRIVER).unwrap()),
        "a driven actor must resolve to its driver, got {got:?}"
    );
}

/// `driven: false` is `None` — an ANSWER, not an error.
#[tokio::test]
async fn an_undriven_actor_is_none_and_not_an_error() {
    let server = MockServer::start().await;
    Mock::given(method("POST"))
        .respond_with(ResponseTemplate::new(200)
            .set_body_json(serde_json::json!({ "driven": false })))
        .mount(&server)
        .await;

    let (r, a) = ids();
    let got = BridgeClient::new(server.uri(), String::from("tok")).read_actor_control(r, a).await;
    assert!(
        matches!(got, Ok(None)),
        "an undriven actor must be Ok(None), got {got:?}"
    );
}

/// `driven: true` with no user is a CONTRADICTION and must NOT read as `None`.
///
/// This is the one wrong answer the function must never give. `None` means the
/// slot is free; returning it when the bridge just said the actor is taken would
/// tell a grant preview to go ahead, and the grant would then be refused by a
/// conflict the preview had just denied existed. A malformed reply is ours to
/// report, not to round down to good news.
#[tokio::test]
async fn driven_with_no_user_is_an_error_not_an_empty_slot() {
    let server = MockServer::start().await;
    Mock::given(method("POST"))
        .respond_with(ResponseTemplate::new(200)
            .set_body_json(serde_json::json!({ "driven": true })))
        .mount(&server)
        .await;

    let (r, a) = ids();
    let got = BridgeClient::new(server.uri(), String::from("tok")).read_actor_control(r, a).await;
    let e = got.expect_err("driven=true with no user_ref_id must not be reported as undriven");
    assert!(
        e.to_string().contains("driven=true with no user_ref_id"),
        "the contradiction must be named, got {e}"
    );
}

/// …and the same for a user field that is not a uuid.
#[tokio::test]
async fn a_malformed_user_is_an_error_not_an_empty_slot() {
    let server = MockServer::start().await;
    Mock::given(method("POST"))
        .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
            "driven": true, "user_ref_id": "not-a-uuid",
        })))
        .mount(&server)
        .await;

    let (r, a) = ids();
    let e = BridgeClient::new(server.uri(), String::from("tok"))
        .read_actor_control(r, a)
        .await
        .expect_err("a malformed user_ref_id must not be reported as undriven");
    assert!(e.to_string().contains("is not a uuid"), "got {e}");
}

/// A rejected token is ours to surface, not a shrug.
///
/// `401` is asserted separately from the catch-all because it means the caller
/// is mis-configured, and an operator reading "unexpected 401" would go looking
/// at the bridge instead of at their own token.
#[tokio::test]
async fn a_401_is_named() {
    let server = MockServer::start().await;
    Mock::given(method("POST"))
        .respond_with(ResponseTemplate::new(401))
        .mount(&server)
        .await;

    let (r, a) = ids();
    let e = BridgeClient::new(server.uri(), String::from("wrong"))
        .read_actor_control(r, a)
        .await
        .expect_err("401 must be an error");
    assert!(e.to_string().contains("401 unauthorized"), "got {e}");
}

/// Any other status is an error carrying the code, and NOT an empty slot.
///
/// Non-vacuity for the four cases above: a client that returned `Err` for
/// everything would satisfy the three error tests, so the happy path is
/// asserted first and this proves the failure path is not the only one.
#[tokio::test]
async fn an_unexpected_status_is_an_error_carrying_the_code() {
    let server = MockServer::start().await;
    Mock::given(method("POST"))
        .respond_with(ResponseTemplate::new(503).set_body_string("bridge is restarting"))
        .mount(&server)
        .await;

    let (r, a) = ids();
    let e = BridgeClient::new(server.uri(), String::from("tok"))
        .read_actor_control(r, a)
        .await
        .expect_err("503 must be an error");
    assert!(e.to_string().contains("503"), "the status must reach the caller, got {e}");
}
