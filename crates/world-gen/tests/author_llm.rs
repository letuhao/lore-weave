//! LLM integration tests — `CreativeSeed` authoring + feature naming.
//!
//! `#[ignore]`d: they need a running OpenAI-compatible endpoint (LM Studio at
//! `localhost:1234` with `ibm/granite-4-h-tiny` loaded). Run on demand:
//! `cargo test -p world-gen --test author_llm -- --ignored`.

use world_gen::author::request_creative_seed;
use world_gen::naming::name_world;
use world_gen::{CreativeSeed, WorldArchetype, generate};

#[test]
#[ignore = "requires a running LM Studio at http://localhost:1234"]
fn llm_authors_a_creative_seed_that_generates_a_valid_map() {
    let cs = request_creative_seed(
        "a cold, mountainous wuxia realm of scattered island kingdoms, \
         sparsely settled, with several rival cultures",
        "http://localhost:1234/v1",
        "ibm/granite-4-h-tiny",
    )
    .expect("LLM should return a schema-valid CreativeSeed");

    // The authored CreativeSeed must drive a valid, self-consistent map.
    let map = generate(1, &cs);
    assert!(map.verify_hash(), "authored map fails its own hash check");
    assert!(!map.provinces.is_empty(), "authored map has no provinces");
    assert!(!map.settlements.is_empty(), "authored map has no settlements");
}

#[test]
#[ignore = "requires a running LM Studio at http://localhost:1234"]
fn llm_names_a_world() {
    let mut map = generate(2, &CreativeSeed::default());
    name_world(
        &mut map,
        WorldArchetype::HighFantasy,
        "http://localhost:1234/v1",
        "ibm/granite-4-h-tiny",
    )
    .expect("LLM should return schema-valid world names");

    // The settlements should come back named, and naming must not disturb the
    // hashed geometry (names are excluded from `content_hash`).
    assert!(
        map.settlements.iter().any(|s| !s.name.is_empty()),
        "no settlement was named"
    );
    assert!(map.verify_hash(), "naming changed the hashed geometry");
}
