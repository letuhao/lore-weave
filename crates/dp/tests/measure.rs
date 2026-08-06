//! `S3.1` / `S3.2` / `S3.4` — the numbers, off a real run.
//!
//! The design claim behind slice 1 is that moving tier and scope from *fields*
//! to *types* costs nothing at runtime. That is a claim about generated code, so
//! it is measured rather than asserted.

use core::mem::size_of;

use dp::{
    tier_row, ChannelScope, Coherency, DpAggregate, RealityScope, ScopeKind, TierLevel, TierRow,
    T0, T1, T2, T3,
};

/// The subject of the measurements below. Its `TYPE_NAME` is deliberately NOT
/// `player_inventory` — `aggregate.rs`'s unit tests already bind that one, and
/// `dp-aggregate-gate` found the collision on its first run. Two impls under one
/// name is the `V1-F1` shape even when, as here, both happen to pick `T2`.
struct MeasuredInventory;
impl DpAggregate for MeasuredInventory {
    type Tier = T2;
    type Scope = RealityScope;
    type Id = u64;
    const TYPE_NAME: &'static str = "measured_inventory";
}

/// `S3.2` — evaluated in a **`const` context**, which proves the row *can* be
/// computed entirely by the compiler: a `const` binding cannot be produced by a
/// runtime call, so this is a proof rather than a benchmark.
///
/// **It does not prove "zero instructions at runtime", and the earlier wording
/// that said so was wrong (`V1-F6`).** The refuter disassembled a *non-const*
/// call site and found nine instructions at `-O3` and a real `callq` at `-O0`.
/// The honest claim is the one this line makes: **at a `const` site the cost is
/// zero, and every site in this crate's own API is one.** A caller who writes
/// `let row = tier_row::<A>()` in a hot loop gets a function call like any
/// other, and should hoist it into a `const` — which they can, and which is the
/// point of the design.
const INVENTORY_ROW: TierRow = tier_row::<MeasuredInventory>();

#[test]
fn s3_1_every_marker_type_is_zero_sized() {
    let sizes = [
        ("T0", size_of::<T0>()),
        ("T1", size_of::<T1>()),
        ("T2", size_of::<T2>()),
        ("T3", size_of::<T3>()),
        ("RealityScope", size_of::<RealityScope>()),
        ("ChannelScope", size_of::<ChannelScope>()),
    ];
    for (name, sz) in sizes {
        println!("S3.1  size_of::<{name}>() = {sz}");
        assert_eq!(sz, 0, "{name} must be zero-sized: the tier is a type, not data");
    }
    // The runtime-inspectable forms DO cost something, and that is correct —
    // they exist to be written into a cache key or a metric label.
    println!("S3.1  size_of::<TierLevel>() = {}", size_of::<TierLevel>());
    println!("S3.1  size_of::<ScopeKind>() = {}", size_of::<ScopeKind>());
    assert_eq!(size_of::<TierLevel>(), 1);
    assert_eq!(size_of::<ScopeKind>(), 1);
}

/// The assertions themselves run **at compile time**. A `const` block that
/// fails is a build error, not a test failure — which is a strictly stronger
/// claim than a `#[test]` making the same comparison, and it is why clippy is
/// right to refuse `assert!` on a constant inside a test body: the assertion
/// belongs where the constant does.
const _: () = {
    assert!(INVENTORY_ROW.survives_store_outage());
    assert!(matches!(INVENTORY_ROW.tier(), TierLevel::T2));
    assert!(matches!(INVENTORY_ROW.scope(), ScopeKind::Reality));
    assert!(matches!(
        INVENTORY_ROW.coherency(),
        Coherency::WriteThroughAsyncInvalidate
    ));
};

#[test]
fn s3_2_the_tier_row_is_computed_at_compile_time() {
    // The proof is above and already ran — this only prints the evidence.
    println!("S3.2  const INVENTORY_ROW = {INVENTORY_ROW:?}");
    println!("S3.2  the four asserts above are in a `const _: () = {{ .. }}` block:");
    println!("S3.2    they were evaluated by rustc, not by this test binary");
    assert_eq!(INVENTORY_ROW.type_name(), "measured_inventory");
}

/// `S3.4` — the counts, **measured rather than typed.**
///
/// This test used to print `"compile-fail UI cases = 3 (two_tiers, fifth_tier,
/// runtime_tier)"` while four files sat in `tests/ui/` (`V1-F11`). The number was
/// a sentence, so it went stale the moment a case was added — and the reader it
/// misinforms is the one auditing whether the suite covers what it claims.
///
/// Every figure below is now counted off the tree at run time. This repo has a
/// gate for exactly this defect on its design docs (`actor-hub-figures-gate`);
/// the rule is the same in a test.
///
/// The closed-set assertions that used to live here are gone rather than moved:
/// `assert_eq!([T0,T1,T2,T3].len(), 4)` is `NV-1` — the array has four elements
/// because the test wrote four. `spec_oracle::the_tier_set_in_source_matches_the_taxonomy_doc`
/// makes that claim against two sources that can both move.
#[test]
fn s3_4_counts() {
    let dir = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"));

    let ui_cases: Vec<String> = std::fs::read_dir(dir.join("tests/ui"))
        .expect("tests/ui")
        .filter_map(Result::ok)
        .map(|e| e.file_name().to_string_lossy().into_owned())
        .filter(|n| n.ends_with(".rs"))
        .collect();
    let stderr_files = std::fs::read_dir(dir.join("tests/ui"))
        .expect("tests/ui")
        .filter_map(Result::ok)
        .filter(|e| e.file_name().to_string_lossy().ends_with(".stderr"))
        .count();

    let oracle = std::fs::read_to_string(dir.join("tests/spec_oracle.rs")).expect("spec_oracle.rs");
    let oracle_tests = oracle.matches("#[test]").count();

    let tiers = [TierLevel::T0, TierLevel::T1, TierLevel::T2, TierLevel::T3];
    let scopes = [ScopeKind::Reality, ScopeKind::Channel];

    println!("S3.4  tiers declared          = {}", tiers.len());
    println!("S3.4  scopes declared         = {}", scopes.len());
    println!("S3.4  tier x scope cells      = {}", tiers.len() * scopes.len());
    println!("S3.4  compile-fail UI cases   = {} ({})", ui_cases.len(), {
        let mut v = ui_cases.clone();
        v.sort();
        v.join(", ")
    });
    println!("S3.4  pinned .stderr files    = {stderr_files}");
    println!("S3.4  spec-oracle tests       = {oracle_tests}");

    // `V2-F5` — **the assertion that used to live here was `NV-1`, and the
    // comment above it claimed otherwise.** It read
    // `assert_eq!(tiers.len() * scopes.len(), 8)` and called that "a PRODUCT of
    // two independently-declared sets". They are two array literals typed three
    // lines up. Adding a fifth `TierLevel` variant left this test **printing
    // `tiers declared = 4` and `cells = 8`, and passing** — which is
    // `assert_eq!([T0..T3].len(), 4)`, the assertion `V1-F2` deleted from this
    // very file, wearing a different costume.
    //
    // The subject that can actually vary is the SOURCE. `TierLevel`'s variants
    // and `declare_tier!`'s invocations are two independent things in one file:
    // add a variant without a tier, or a tier without a variant, and they
    // disagree. The arrays above are then checked against the parse rather than
    // against themselves.
    let tier_src = std::fs::read_to_string(dir.join("src/tier.rs")).expect("tier.rs");
    let enum_body = {
        let s = tier_src.find("pub enum TierLevel {").expect("the TierLevel enum");
        let e = tier_src[s..].find('}').expect("its closing brace") + s;
        &tier_src[s..e]
    };
    let variants: Vec<&str> = enum_body
        .lines()
        .skip(1)
        .map(|l| l.trim().trim_end_matches(','))
        .filter(|l| !l.is_empty() && !l.starts_with("//"))
        .collect();
    let invocations = tier_src.matches("declare_tier!(").count();

    println!("S3.4  TierLevel variants      = {} {:?}", variants.len(), variants);
    println!("S3.4  declare_tier! calls     = {invocations}");

    assert_eq!(
        variants.len(),
        invocations,
        "tier.rs declares {} TierLevel variant(s) {variants:?} and makes {invocations} \
         declare_tier! call(s) — one was added without the other",
        variants.len()
    );
    assert_eq!(
        tiers.len(),
        variants.len(),
        "this test enumerates {} tier(s) while tier.rs declares {} — the array above is stale",
        tiers.len(),
        variants.len()
    );
    // `DP-Ch4`: "all 4 tiers x 2 scopes = 8 combinations, all valid." Now a
    // product of two numbers that came from the file rather than from here.
    println!("S3.4  cells (parsed)          = {}", variants.len() * scopes.len());

    // Every UI case must carry a pinned expectation, or trybuild would accept a
    // failure whose REASON has drifted. Counted, not assumed.
    assert_eq!(
        ui_cases.len(),
        stderr_files,
        "every tests/ui/*.rs needs its .stderr: found {ui_cases:?} against {stderr_files} pins"
    );
    assert!(!ui_cases.is_empty() && oracle_tests > 0, "S3.4 counted nothing");
}
