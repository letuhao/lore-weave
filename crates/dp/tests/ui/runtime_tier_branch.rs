//! `S2.2(c)` — a tier may not be chosen at RUNTIME. **The unbiteable half, and
//! it is labelled unbiteable on purpose.**
//!
//! The other shape a feature reaches for: *"under load, degrade this aggregate
//! to T1."* An associated type is resolved by the compiler; `if` produces a
//! value, not a type, so this is a **parse** error.
//!
//! # This case has NO bite, and saying so is the honest form
//!
//! `S3.3` requires that removing a guard makes the violation legal. There is no
//! guard to remove here — *"a type position cannot hold an expression"* is a
//! rule of the language, not a mechanism `crates/dp` installed. Any bite
//! designed for it would be theatre.
//!
//! It is kept because it documents a real thing an author will try, and it is
//! **separated from [`runtime_tier_field.rs`]** because the first version of
//! this suite had both in one file — and the parse error masked the field case
//! entirely, so the half that COULD be bitten never was. The bite harness found
//! that, which is the second time in this run a harness caught a defect in the
//! test rather than in the subject (`BDR-6`).
//!
//! [`runtime_tier_field.rs`]: ./runtime_tier_field.rs

use dp::{DpAggregate, RealityScope, T1, T2};

fn under_load() -> bool {
    std::env::var("DP_DEGRADE").is_ok()
}

struct LoadAdaptive;

impl DpAggregate for LoadAdaptive {
    type Tier = if under_load() { T1 } else { T2 };
    type Scope = RealityScope;
    type Id = u64;
    const TYPE_NAME: &'static str = "load_adaptive";
}

fn main() {}
