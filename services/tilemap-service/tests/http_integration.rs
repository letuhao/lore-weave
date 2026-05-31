//! End-to-end HTTP integration test for `POST /internal/v1/tilemaps/render`.
//!
//! Boots a server on an ephemeral port via the library `serve()` entry,
//! then drives it with `reqwest`. Covers spec §9 acceptance criteria
//! AC-HTTP-2 through AC-HTTP-8 (AC-HTTP-1 / AC-HTTP-9 land in Chunk 4's
//! boot guard, AC-HTTP-10 is the cumulative count gate).

use std::net::SocketAddr;

use reqwest::StatusCode;
use serde_json::{Value, json};
use tilemap_service::http;
use tilemap_service::types::template::{TilemapTemplate, TilemapTemplateId, ZoneSpec};
use tilemap_service::types::zone::{PassageKind, ZoneId, ZoneRole};
use tilemap_service::types::tile::TerrainKind;
use tilemap_service::world_inherit::{
    MockFileWorldSource, RegionPath, WorldBiome, WorldSource, WorldZoneSnapshot,
};

const TOKEN: &str = "test-internal-token-do-not-use-in-prod";

/// Boot the server on an ephemeral port and return its `http://127.0.0.1:PORT`
/// base URL. The server task is leaked deliberately — the test process exits
/// after the assertions and tokio cleans up.
async fn boot_server() -> String {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0")
        .await
        .expect("bind ephemeral");
    let addr: SocketAddr = listener.local_addr().expect("local_addr");
    let state = http::AppState::new(TOKEN.to_string());
    let router = http::build_router(state);
    tokio::spawn(async move {
        let _ = axum::serve(listener, router).await;
    });
    // Tiny yield so the listener task definitely starts polling before we
    // call connect. Not strictly necessary on tokio but harmless.
    tokio::task::yield_now().await;
    format!("http://{addr}")
}

fn minimal_template() -> TilemapTemplate {
    fn zone(id: &str, role: ZoneRole, conns: &[(&str, PassageKind)]) -> ZoneSpec {
        use tilemap_service::types::template::TemplateConnection;
        ZoneSpec {
            zone_id: ZoneId(id.to_string()),
            zone_role: role,
            size: 100,
            terrain_types: vec![],
            monster_strength: None,
            connections: conns
                .iter()
                .map(|(to, k)| TemplateConnection::new(ZoneId(to.to_string()), *k))
                .collect(),
            treasure_tiers: vec![],
            biome_selection_rules: None,
            inherit_treasure_from: None,
            biome_theme: None,
        }
    }
    TilemapTemplate {
        template_id: TilemapTemplateId("http_integration_minimal".to_string()),
        zones: vec![
            zone("capital", ZoneRole::Wilderness, &[("crossroad", PassageKind::Threshold)]),
            zone("crossroad", ZoneRole::Hub, &[("frontier", PassageKind::Open)]),
            zone("frontier", ZoneRole::Wilderness, &[]),
            zone("inland_sea", ZoneRole::Sea, &[]),
            zone("rival", ZoneRole::Forbidden, &[]),
        ],
        seed_offset: 0,
        world_zone: None,
        decoration_density: None,
        background_biome: None,
    }
}

fn minimal_render_body(template: &TilemapTemplate, seed: u64) -> Value {
    json!({
        "template": template,
        "channel_id": "ch_http_integration",
        "tier": "country",
        "grid_size": { "width": 64, "height": 64 },
        "seed": seed,
    })
}

/// LOW-5 helper from /review-impl: every 4xx test should assert the
/// Content-Type is `application/problem+json` AND the body URN matches
/// the expected family. Without this, a future refactor that broke
/// `IntoResponse for ProblemDetails` would only fail one (AC-HTTP-3),
/// leaving a wide regression silent.
async fn assert_problem_json(
    resp: reqwest::Response,
    expected_status: StatusCode,
    expected_urn: &str,
) -> Value {
    let status = resp.status();
    let ct = resp
        .headers()
        .get(reqwest::header::CONTENT_TYPE)
        .and_then(|h| h.to_str().ok())
        .unwrap_or("")
        .to_string();
    let body: Value = resp.json().await.expect("problem+json body must parse");
    assert_eq!(status, expected_status, "expected {expected_status}, got {status} body {body}");
    assert!(
        ct.starts_with("application/problem+json"),
        "Content-Type must be application/problem+json, got {ct:?} body {body}"
    );
    let urn = body["type"].as_str().unwrap_or("");
    assert_eq!(
        urn, expected_urn,
        "URN mismatch: expected {expected_urn}, got {urn:?} body {body}"
    );
    assert_eq!(
        body["status"].as_u64(),
        Some(expected_status.as_u16() as u64),
        "body.status must mirror HTTP status"
    );
    body
}

#[tokio::test]
async fn health_livez_returns_200_without_auth() {
    // /livez and /readyz are public probes (k8s pattern). They must
    // respond 200 with no Authorization header — docker healthcheck +
    // load-balancer probes cannot present a Bearer token.
    let base = boot_server().await;
    let client = reqwest::Client::new();
    let resp = client
        .get(format!("{base}/livez"))
        .send()
        .await
        .expect("send");
    assert_eq!(resp.status(), StatusCode::OK);
    let body: Value = resp.json().await.expect("json");
    assert_eq!(body["status"], "ok");
    assert_eq!(body["endpoint"], "livez");
    assert_eq!(body["service"], "tilemap-service");
    // LOW-5 from /review-impl: `version` is opt-in via
    // TILEMAP_HEALTH_VERBOSE=1. The test process doesn't set the env
    // var, so the field must be ABSENT (Option::None +
    // skip_serializing_if).
    assert!(
        body.get("version").is_none(),
        "version must be absent by default — leak guard; got body={body}"
    );
}

#[tokio::test]
async fn health_readyz_returns_200_without_auth() {
    let base = boot_server().await;
    let client = reqwest::Client::new();
    let resp = client
        .get(format!("{base}/readyz"))
        .send()
        .await
        .expect("send");
    assert_eq!(resp.status(), StatusCode::OK);
    let body: Value = resp.json().await.expect("json");
    assert_eq!(body["endpoint"], "readyz");
}

#[tokio::test]
async fn health_endpoints_ignore_bearer_token() {
    // Defensive: even when a (valid or invalid) Bearer is sent, the
    // probes still return 200. They're outside the auth-gated group.
    let base = boot_server().await;
    let client = reqwest::Client::new();
    let resp_with_wrong = client
        .get(format!("{base}/livez"))
        .bearer_auth("garbage-token")
        .send()
        .await
        .unwrap();
    assert_eq!(resp_with_wrong.status(), StatusCode::OK);
}

#[tokio::test]
async fn cosmetic_7_health_endpoints_reject_non_get() {
    // COSMETIC-7 regression from /review-impl: probes are GET-only. A
    // POST/PUT/DELETE to /livez or /readyz should return 405 Method
    // Not Allowed (axum router default). This catches the case where
    // a future refactor mistakenly maps multiple methods to the probe.
    let base = boot_server().await;
    let client = reqwest::Client::new();
    let resp = client
        .post(format!("{base}/livez"))
        .send()
        .await
        .expect("send");
    assert_eq!(
        resp.status(),
        StatusCode::METHOD_NOT_ALLOWED,
        "POST /livez should be 405; got {}",
        resp.status()
    );
    let resp = client
        .post(format!("{base}/readyz"))
        .send()
        .await
        .expect("send");
    assert_eq!(resp.status(), StatusCode::METHOD_NOT_ALLOWED);
}

#[tokio::test]
async fn ac_http_2_valid_request_returns_200_with_tilemap_view() {
    let base = boot_server().await;
    let client = reqwest::Client::new();
    let resp = client
        .post(format!("{base}/internal/v1/tilemaps/render"))
        .bearer_auth(TOKEN)
        .json(&minimal_render_body(&minimal_template(), 0xA11CE))
        .send()
        .await
        .expect("send");
    assert_eq!(resp.status(), StatusCode::OK, "expected 200, got {}", resp.status());
    let view: Value = resp.json().await.expect("json");
    assert_eq!(view["template_id"], "http_integration_minimal");
    assert!(!view["zones"].as_array().unwrap().is_empty());
}

#[tokio::test]
async fn tmp_q4_render_endpoint_emits_tier_index_on_treasure_placements() {
    // TMP-Q4 MED-1 from /review-impl — locks the HTTP wire contract for
    // the new `tier_index` field. The lib-level placer tests prove the
    // struct is populated; this test proves the field SURVIVES axum's
    // JSON response codepath and ends up readable by HTTP clients.
    //
    // A future refactor that dropped `tier_index` from `commit_placement`
    // OR from `TilemapObjectPlacement`'s serde derive OR from the response
    // serializer would slip past the lib tests but fail here.
    //
    // Template strategy: declare a zone with two value-disjoint tiers
    // (low-first author order) so the post-sort `tier_index` mapping is
    // unambiguous (high-`max` ⇒ tier_index=0).
    use tilemap_service::types::template::TemplateConnection;
    use tilemap_service::types::treasure::TreasureTierSpec;
    let mut tmpl = minimal_template();
    let capital_idx = tmpl
        .zones
        .iter()
        .position(|z| z.zone_id.0 == "capital")
        .expect("minimal template has 'capital'");
    tmpl.zones[capital_idx].treasure_tiers = vec![
        TreasureTierSpec { min: 300, max: 800, density: 5 },
        TreasureTierSpec { min: 5000, max: 9000, density: 4 },
    ];
    // The minimal template's `frontier` zone is unreachable from
    // `capital` via the default Open + Threshold connections + the
    // Forbidden `rival`. We don't depend on the connection topology —
    // capital is Wilderness which TreasurePlacer processes.
    let _ = TemplateConnection::new(ZoneId("frontier".to_string()), PassageKind::Open);
    let base = boot_server().await;
    let client = reqwest::Client::new();
    let resp = client
        .post(format!("{base}/internal/v1/tilemaps/render"))
        .bearer_auth(TOKEN)
        .json(&minimal_render_body(&tmpl, 19))
        .send()
        .await
        .expect("send");
    assert_eq!(resp.status(), StatusCode::OK, "expected 200 with tier-bearing template");
    let view: Value = resp.json().await.expect("json");

    let placements = view["object_placements"]
        .as_array()
        .expect("object_placements must be an array");
    let treasures: Vec<&Value> = placements
        .iter()
        .filter(|p| p["kind"] == "treasure")
        .collect();
    assert!(
        !treasures.is_empty(),
        "tier-populated zone must produce at least one treasure placement on the wire"
    );
    for p in &treasures {
        let v = p["value"].as_u64().expect("treasure has value");
        let idx = p["tier_index"]
            .as_u64()
            .expect("MED-1: treasure placement MUST carry tier_index on the HTTP wire");
        let expected = if v >= 5000 { 0 } else { 1 };
        assert_eq!(
            idx, expected,
            "value {v} expects tier_index {expected} (high-max first); got {idx} on the wire",
        );
    }

    // A non-treasure placement (obstacle / connection guard / decoration)
    // MUST NOT serialise `tier_index` — `skip_serializing_if` discipline
    // pins V2 byte-identical for everything else.
    for p in placements.iter().filter(|p| p["kind"] != "treasure" && p["kind"] != "monster_lair") {
        assert!(
            p.get("tier_index").is_none() || p["tier_index"].is_null(),
            "MED-1: non-treasure placement (kind={}) MUST NOT carry tier_index on the wire; got {:?}",
            p["kind"],
            p["tier_index"],
        );
    }
}

#[tokio::test]
async fn tmp_q4_render_endpoint_emits_registry_ref_without_value_band_thresholds_for_default() {
    // TMP-Q4 MED-1 from /review-impl (companion test) — the default `lw`
    // registry does NOT declare `value_band_thresholds`, so the wire-shape
    // contract is: the field is OMITTED entirely (not present as `null`).
    // A regression where `RegistryRef` serialized `value_band_thresholds:
    // null` instead of skipping it would shift the V2 byte-identical
    // baseline and break frontend strict-key consumers.
    let base = boot_server().await;
    let client = reqwest::Client::new();
    let resp = client
        .post(format!("{base}/internal/v1/tilemaps/render"))
        .bearer_auth(TOKEN)
        .json(&minimal_render_body(&minimal_template(), 23))
        .send()
        .await
        .expect("send");
    assert_eq!(resp.status(), StatusCode::OK);
    // Pull the raw body so we can inspect serialization (not just parse).
    let view: Value = resp.json().await.expect("json");
    let registry_ref = view["registry_ref"]
        .as_object()
        .expect("default registry must emit registry_ref");
    assert_eq!(registry_ref["id"], "lw", "default is the lw registry");
    assert!(
        !registry_ref.contains_key("value_band_thresholds"),
        "MED-1: default registry omits value_band_thresholds (None ⇒ skipped); \
         got {registry_ref:?}",
    );
}

#[tokio::test]
async fn ac_http_3_missing_authorization_returns_401_problem_json() {
    let base = boot_server().await;
    let client = reqwest::Client::new();
    let resp = client
        .post(format!("{base}/internal/v1/tilemaps/render"))
        // intentionally NO .bearer_auth
        .json(&minimal_render_body(&minimal_template(), 1))
        .send()
        .await
        .expect("send");
    assert_problem_json(
        resp,
        StatusCode::UNAUTHORIZED,
        "urn:tilemap-service:error:unauthorized",
    )
    .await;
}

#[tokio::test]
async fn ac_http_4_wrong_token_returns_401() {
    let base = boot_server().await;
    let client = reqwest::Client::new();
    let resp = client
        .post(format!("{base}/internal/v1/tilemaps/render"))
        .bearer_auth("wrong-token")
        .json(&minimal_render_body(&minimal_template(), 1))
        .send()
        .await
        .expect("send");
    assert_problem_json(
        resp,
        StatusCode::UNAUTHORIZED,
        "urn:tilemap-service:error:unauthorized",
    )
    .await;
}

#[tokio::test]
async fn ac_http_5_malformed_body_returns_400_problem_json() {
    // MED-2 fix from /review-impl: the JsonProblem extractor now routes
    // axum's JsonRejection through ProblemDetails — malformed bodies
    // (missing required field) get a real problem+json response, not
    // axum's default text/plain.
    let base = boot_server().await;
    let client = reqwest::Client::new();
    let bad = json!({
        "template": minimal_template(),
        "channel_id": "ch",
        "tier": "country",
        "grid_size": { "width": 64, "height": 64 }
        // intentionally NO "seed"
    });
    let resp = client
        .post(format!("{base}/internal/v1/tilemaps/render"))
        .bearer_auth(TOKEN)
        .json(&bad)
        .send()
        .await
        .expect("send");
    // Axum reports missing field as UNPROCESSABLE_ENTITY (422) via its
    // JsonRejection — our wrapper maps that to bad-request URN.
    let status = resp.status();
    assert!(
        status == StatusCode::BAD_REQUEST || status == StatusCode::UNPROCESSABLE_ENTITY,
        "malformed body should be 4xx, got {status}"
    );
    let ct = resp
        .headers()
        .get(reqwest::header::CONTENT_TYPE)
        .and_then(|h| h.to_str().ok())
        .unwrap_or("")
        .to_string();
    assert!(
        ct.starts_with("application/problem+json"),
        "MED-2: malformed body Content-Type must be problem+json, got {ct:?}"
    );
    let body: Value = resp.json().await.unwrap();
    let urn = body["type"].as_str().unwrap_or("");
    assert_eq!(urn, "urn:tilemap-service:error:bad-request");
}

#[tokio::test]
async fn med_2_invalid_json_syntax_returns_problem_json() {
    // MED-2 regression: a body that isn't valid JSON at all flows
    // through JsonProblem → ProblemDetails::bad_request.
    let base = boot_server().await;
    let client = reqwest::Client::new();
    let resp = client
        .post(format!("{base}/internal/v1/tilemaps/render"))
        .bearer_auth(TOKEN)
        .header(reqwest::header::CONTENT_TYPE, "application/json")
        .body("{ not valid json at all }")
        .send()
        .await
        .expect("send");
    // Axum's Json extractor returns 400 for syntax errors.
    assert_problem_json(
        resp,
        StatusCode::BAD_REQUEST,
        "urn:tilemap-service:error:bad-request",
    )
    .await;
}

#[tokio::test]
async fn med_1_oversized_grid_returns_413_problem_json() {
    // MED-1 regression from /review-impl: a request that would allocate
    // billions of tiles must be rejected with 413 BEFORE the engine sees
    // it. Cap is MAX_GRID_TILES = 65_536.
    let base = boot_server().await;
    let body = json!({
        "template": minimal_template(),
        "channel_id": "ch_oversize",
        "tier": "country",
        "grid_size": { "width": 1000, "height": 1000 },  // 1M tiles
        "seed": 1
    });
    let client = reqwest::Client::new();
    let resp = client
        .post(format!("{base}/internal/v1/tilemaps/render"))
        .bearer_auth(TOKEN)
        .json(&body)
        .send()
        .await
        .expect("send");
    let body_val = assert_problem_json(
        resp,
        StatusCode::PAYLOAD_TOO_LARGE,
        "urn:tilemap-service:error:request-too-large",
    )
    .await;
    assert!(
        body_val["detail"].as_str().unwrap_or("").contains("tiles"),
        "detail should explain which limit was exceeded; got {body_val}"
    );
}

#[tokio::test]
async fn med_1_oversized_zone_count_returns_413_problem_json() {
    // MED-1 second leg: zone count beyond MAX_ZONES is rejected the same way.
    use tilemap_service::types::template::{TemplateConnection, TilemapTemplate, TilemapTemplateId, ZoneSpec};
    use tilemap_service::types::zone::{PassageKind, ZoneId, ZoneRole};
    let zones: Vec<ZoneSpec> = (0..300)
        .map(|i| ZoneSpec {
            zone_id: ZoneId(format!("z{i}")),
            zone_role: ZoneRole::Wilderness,
            size: 100,
            terrain_types: vec![],
            monster_strength: None,
            connections: vec![TemplateConnection::new(
                ZoneId(format!("z{}", (i + 1) % 300)),
                PassageKind::Threshold,
            )],
            treasure_tiers: vec![],
            biome_selection_rules: None,
            inherit_treasure_from: None,
            biome_theme: None,
        })
        .collect();
    let template = TilemapTemplate {
        template_id: TilemapTemplateId("oversized_zones".to_string()),
        zones,
        seed_offset: 0,
        world_zone: None,
        decoration_density: None,
        background_biome: None,
    };
    let base = boot_server().await;
    let client = reqwest::Client::new();
    let resp = client
        .post(format!("{base}/internal/v1/tilemaps/render"))
        .bearer_auth(TOKEN)
        .json(&minimal_render_body(&template, 1))
        .send()
        .await
        .expect("send");
    let body = assert_problem_json(
        resp,
        StatusCode::PAYLOAD_TOO_LARGE,
        "urn:tilemap-service:error:request-too-large",
    )
    .await;
    assert!(body["detail"].as_str().unwrap_or("").contains("zones"));
}

#[tokio::test]
async fn ac_http_6_placement_failure_returns_422_with_tilemap_urn() {
    // PLAN risks anticipated this: empty-zones templates DON'T trigger
    // Error::EmptyZone — the engine accepts them and produces an empty
    // TilemapView. To exercise the 422 path, force a placement failure
    // via a degenerate config: 5 zones onto a 1x1 grid. Penrose cannot
    // assign every zone ≥1 tile → some zone gets 0 → Error::EmptyZone.
    let base = boot_server().await;
    let body = json!({
        "template": minimal_template(),
        "channel_id": "ch_force_failure",
        "tier": "country",
        "grid_size": { "width": 1, "height": 1 },
        "seed": 1
    });
    let client = reqwest::Client::new();
    let resp = client
        .post(format!("{base}/internal/v1/tilemaps/render"))
        .bearer_auth(TOKEN)
        .json(&body)
        .send()
        .await
        .expect("send");
    // The exact URN depends on engine check order (Placement vs
    // EmptyZone) — accept any tilemap-service URN at the 422 level
    // and assert Content-Type via the helper.
    let status = resp.status();
    let ct = resp
        .headers()
        .get(reqwest::header::CONTENT_TYPE)
        .and_then(|h| h.to_str().ok())
        .unwrap_or("")
        .to_string();
    let body_val: Value = resp.json().await.expect("json");
    let urn = body_val["type"].as_str().unwrap_or("");
    assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
    assert!(
        ct.starts_with("application/problem+json"),
        "Content-Type must be problem+json on placement failure"
    );
    assert!(
        urn == "urn:tilemap-service:error:placement"
            || urn == "urn:tilemap-service:error:empty-zone"
            || urn == "urn:tilemap-service:error:modificator",
        "expected a placement-family URN, got {urn:?}"
    );
}

#[tokio::test]
async fn ac_http_7_same_request_twice_returns_byte_identical_response() {
    let base = boot_server().await;
    let client = reqwest::Client::new();
    let body = minimal_render_body(&minimal_template(), 0xDE7E);
    let url = format!("{base}/internal/v1/tilemaps/render");
    let a = client.post(&url).bearer_auth(TOKEN).json(&body).send().await.unwrap();
    let b = client.post(&url).bearer_auth(TOKEN).json(&body).send().await.unwrap();
    assert_eq!(a.status(), StatusCode::OK);
    assert_eq!(b.status(), StatusCode::OK);
    let ja: Value = a.json().await.unwrap();
    let jb: Value = b.json().await.unwrap();
    assert_eq!(ja, jb, "determinism violated across HTTP boundary");
}

#[tokio::test]
async fn ac_http_8_world_zone_some_changes_output_through_http() {
    // World-inheritance integration through the HTTP layer (composition
    // test). Twin requests, same seed; one sends world_zone:None, the
    // other world_zone:Some(IceSnapshot). Outputs MUST differ.
    let base = boot_server().await;
    let client = reqwest::Client::new();
    let url = format!("{base}/internal/v1/tilemaps/render");

    // Pull a real Ice snapshot from the diverse-biomes fixture.
    let fixture = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures/world-mock/diverse-biomes.json");
    let src = MockFileWorldSource::new(&fixture);
    let snap: WorldZoneSnapshot = src
        .load_zone(&RegionPath::new(vec![0, 0]))
        .expect("zone [0, 0] should be Ice");
    assert_eq!(snap.climate.biome_name, WorldBiome::Ice);

    // Twin templates — identical except for world_zone.
    let mut template_none = minimal_template();
    template_none.template_id =
        TilemapTemplateId("http_world_inherit_delta".to_string());
    // Sand terrain on the wilderness zones to maximize the delta — Ice
    // allow-set excludes sand_*, so the filtered library shifts.
    for z in &mut template_none.zones {
        if z.zone_role == ZoneRole::Wilderness {
            z.terrain_types = vec![TerrainKind::Sand];
        }
    }
    let mut template_ice = template_none.clone();
    template_ice.world_zone = Some(snap);

    let body_none = minimal_render_body(&template_none, 0xCAFE);
    let body_ice = minimal_render_body(&template_ice, 0xCAFE);

    let r_none = client.post(&url).bearer_auth(TOKEN).json(&body_none).send().await.unwrap();
    let r_ice = client.post(&url).bearer_auth(TOKEN).json(&body_ice).send().await.unwrap();
    assert_eq!(r_none.status(), StatusCode::OK);
    assert_eq!(r_ice.status(), StatusCode::OK);
    let j_none: Value = r_none.json().await.unwrap();
    let j_ice: Value = r_ice.json().await.unwrap();
    assert_ne!(
        j_none, j_ice,
        "world_zone Some(Ice) must change output over HTTP — bridge wiring may be a no-op"
    );
}
