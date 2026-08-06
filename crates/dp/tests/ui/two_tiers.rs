//! `S2.2(a)` — an aggregate may not declare TWO tiers.
//!
//! `DP-Ch4` states the rule as *"an aggregate type implements **exactly one** of
//! these"* and delegates enforcement to `#[derive(Aggregate)]`. A macro check is
//! bypassed by writing the impl by hand — which is what this file does. It must
//! not compile.

use dp::{ChannelScope, DpAggregate, RealityScope, T2, T3};

struct Ambivalent;

impl DpAggregate for Ambivalent {
    type Tier = T2;
    // A second binding for an associated type is not "rejected" — there is
    // nowhere for it to live. This is the whole claim of slice 1.
    type Tier = T3;
    type Scope = RealityScope;
    type Id = u64;
    const TYPE_NAME: &'static str = "ambivalent";
}

struct AlsoAmbivalent;

impl DpAggregate for AlsoAmbivalent {
    type Tier = T2;
    type Scope = RealityScope;
    type Scope = ChannelScope;
    type Id = u64;
    const TYPE_NAME: &'static str = "also_ambivalent";
}

fn main() {}
