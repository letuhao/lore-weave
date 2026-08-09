//! `S2.2(c)` — a tier may not be chosen at RUNTIME. **The biteable half.**
//!
//! `DP-A9`: *"Tier is **not** chosen at runtime, not configurable per player,
//! not switchable without a design-change."*
//!
//! The shape a real feature reaches for: *"store the tier next to the data."*
//! `TierLevel` — the runtime enum — exists deliberately, for cache keys and
//! telemetry labels. It is **not** a `Tier`, so it cannot satisfy the associated
//! type, and that separation is the entire reason both exist.
//!
//! This is the half `S3.3` can bite: adding `impl Tier for TierLevel` makes it
//! compile, which proves the guard is the missing impl and nothing else.

use dp::{DpAggregate, RealityScope, TierLevel};

struct FieldTiered;

impl DpAggregate for FieldTiered {
    type Tier = TierLevel;
    type Scope = RealityScope;
    type Id = u64;
    type Delta = ();
    type Projection = ();
    const TYPE_NAME: &'static str = "field_tiered";
}

fn main() {}
