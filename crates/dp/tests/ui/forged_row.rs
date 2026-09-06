//! `S2.2(d)` — a `TierRow` may not be written by hand.
//!
//! `DP-R2` requires every feature design doc to carry a tier table, and that
//! table has always been prose a human checked. [`dp::tier_row`] replaces the
//! checkable part of it by *deriving* the row from the aggregate's types, so a
//! table and the code cannot disagree.
//!
//! That only holds if derivation is the **only** way to get a row. It was not:
//! every field was `pub` until `V1-F5`, and the cold-start refuter built this
//! exact value on 2026-08-07 — a `T3` row promising no coherency, a 24-hour TTL
//! (the `const` block in `dp::tier` asserts ≤ 1 h across every tier) and
//! `survives_store_outage: true`, which inverts `REC-102c` for the one tier that
//! must refuse rather than buffer. It compiled, because a struct literal is not
//! a derivation.
//!
//! **A table that can be written by hand is the hand-written table it was meant
//! to replace.** The fields are private now, so this is a compile error, and
//! `S3.3` bites it by restoring `pub` and watching it become legal again.

use core::time::Duration;
use dp::{Coherency, ScopeKind, TierLevel, TierRow};

fn main() {
    // Every value here contradicts the tier it claims to be.
    let forged = TierRow {
        type_name: "player_wallet",
        tier: TierLevel::T3,
        scope: ScopeKind::Reality,
        coherency: Coherency::None,
        cache_ttl: Some(Duration::from_secs(24 * 60 * 60)),
        write_ack_p99: Duration::from_millis(1),
        survives_store_outage: true,
    };
    println!("{forged:?}");
}
