//! LLM integration tests — `CreativeSeed` authoring + feature naming.
//!
//! `#[ignore]`d: they need a running gateway + a registered model_ref.
//! Environment setup before running:
//!
//! ```text
//! export LOREWEAVE_INTERNAL_TOKEN=<token>
//! export LOREWEAVE_GATEWAY_URL=http://localhost:8208     # provider-registry host port
//! export LOREWEAVE_TEST_MODEL_REF=<uuid>                  # platform-registered model
//! export LOREWEAVE_TEST_USER_ID=<uuid>                    # any test user
//! cargo test -p world-gen --test author_llm -- --ignored
//! ```
//!
//! **2026-05-30 refactor**: previous version called LM Studio directly via
//! `--llm-url http://localhost:1234/v1` — that was a CLAUDE.md provider
//! gateway invariant violation. Now: all LLM calls flow through
//! `loreweave_llm::GatewayClient`.

use std::sync::Arc;

use loreweave_llm::{GatewayClient, ModelSource};
use tokio::runtime::Builder as RuntimeBuilder;
use uuid::Uuid;
use world_gen::author::request_creative_seed;
use world_gen::naming::name_world;
use world_gen::shape::GatewayTextProvider;
use world_gen::{CreativeSeed, WorldArchetype, generate};

fn build_provider() -> GatewayTextProvider {
    let client = GatewayClient::from_env().expect("LOREWEAVE_INTERNAL_TOKEN must be set");
    let model_ref: Uuid = std::env::var("LOREWEAVE_TEST_MODEL_REF")
        .expect("LOREWEAVE_TEST_MODEL_REF must be set")
        .parse()
        .expect("LOREWEAVE_TEST_MODEL_REF must be a valid UUID");
    let user_id: Uuid = std::env::var("LOREWEAVE_TEST_USER_ID")
        .expect("LOREWEAVE_TEST_USER_ID must be set")
        .parse()
        .expect("LOREWEAVE_TEST_USER_ID must be a valid UUID");
    let model_source = match std::env::var("LOREWEAVE_TEST_MODEL_SOURCE")
        .unwrap_or_else(|_| "platform".to_string())
        .as_str()
    {
        "user" => ModelSource::UserModel,
        _ => ModelSource::PlatformModel,
    };
    let runtime = RuntimeBuilder::new_current_thread()
        .enable_all()
        .build()
        .expect("tokio runtime build");
    GatewayTextProvider::new(
        Arc::new(client),
        model_source,
        model_ref,
        user_id,
        Arc::new(runtime),
    )
}

#[test]
#[ignore = "requires a running gateway + LOREWEAVE_TEST_MODEL_REF env"]
fn llm_authors_a_creative_seed_that_generates_a_valid_map() {
    let provider = build_provider();
    let cs = request_creative_seed(
        "a cold, mountainous wuxia realm of scattered island kingdoms, \
         sparsely settled, with several rival cultures",
        &provider,
    )
    .expect("gateway should return a schema-valid CreativeSeed");

    let map = generate(1, &cs);
    assert!(map.verify_hash(), "authored map fails its own hash check");
    assert!(!map.provinces.is_empty(), "authored map has no provinces");
    assert!(!map.settlements.is_empty(), "authored map has no settlements");
}

#[test]
#[ignore = "requires a running gateway + LOREWEAVE_TEST_MODEL_REF env"]
fn llm_names_a_world() {
    let provider = build_provider();
    let mut map = generate(2, &CreativeSeed::default());
    name_world(&mut map, WorldArchetype::HighFantasy, &provider)
        .expect("gateway should return schema-valid world names");
    assert!(
        map.settlements.iter().any(|s| !s.name.is_empty()),
        "no settlement was named"
    );
    assert!(map.verify_hash(), "naming changed the hashed geometry");
}
