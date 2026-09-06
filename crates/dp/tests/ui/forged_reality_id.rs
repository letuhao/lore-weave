//! `DP-A12` / `DP-K1` — a feature crate may not MINT a `RealityId`.
//!
//! `04a_core_types_and_session.md`: *"Newtype with module-private constructor —
//! cannot be forged by feature code. Produced only by SDK during session bind
//! (`DP-K10`) after verification against the control plane."*
//!
//! That is a claim about what rustc rejects, so rustc is what checks it. Same
//! shape as `forged_row.rs`, which exists because a refuter hand-built a
//! `TierRow` and printed it (`V1-F5`) — the lesson being that *"the constructor
//! is private"* is worth exactly as much as a test that tries to call it.
//!
//! Both escapes are attempted, because they fail for DIFFERENT reasons and a
//! file that tried only one would pass while the other stayed open:
//!
//!   1. the tuple-struct constructor `RealityId(uuid)` — the FIELD is private
//!      (`E0603`);
//!   2. the named constructor `RealityId::new_verified(uuid)` — the FUNCTION is
//!      `pub(crate)` (`E0624`).
//!
//! If either compiles, a feature crate can address a reality it was never
//! granted and `DP-A12`'s session gating becomes a convention.
//!
//! The legitimate door is `dp::session::SessionContext::bind`, which mints one
//! only from a `ControlPlane` answer — that path is exercised in
//! `session.rs`'s tests, so this file covers the refusal and that one covers
//! the grant.

fn main() {
    let raw = uuid::Uuid::from_u128(1);

    // (1) Straight through the tuple-struct constructor.
    let _forged = dp::RealityId(raw);

    // (2) Through the verified-mint path, which is `pub(crate)`.
    let _minted = dp::RealityId::new_verified(raw);
}
