//! Phase 4 — LLM authoring integration test.
//!
//! `#[ignore]`d: it needs a running OpenAI-compatible endpoint (LM Studio at
//! `localhost:1234` with `ibm/granite-4-h-tiny` loaded). Run on demand:
//! `cargo test -p world-gen --test author_llm -- --ignored`.

use world_gen::author::request_creative_seed;
use world_gen::generate;

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
