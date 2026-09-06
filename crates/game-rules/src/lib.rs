//! `game-rules` — the LAWS (26 §4, `IMP-A5`).
//!
//! ## What is here, and what deliberately is not
//!
//! The COMB_001 §4 damage chain, HSR initiative, and DF07 stat resolution. Not
//! the `Domain` impl, not payloads, not events, not state — those are the
//! *engine's* concern and stay in `commit-service/src/domain/`. A law here is a
//! function of `(state, &Rules)` with one correct answer.
//!
//! ## IMP-D2 — this crate must not be able to do I/O
//!
//! > *"`game-rules` must not depend on `ruleset-loader`. Laws take a resolved
//! > `Rules` by reference (RLS-A12) and know nothing about where it came from.
//! > **A law that can read a file is a law that can be slow, fallible, and
//! > untestable.**"*
//!
//! `IMP-Q2` asked whether this should be a crate or a module of commit-service.
//! **Crate**, and the doc's own reasoning is why: *"leaning crate, because the
//! gate is the point."* A module makes IMP-D2 a promise that a future `use`
//! statement quietly breaks; a crate makes it a **link error**.
//!
//! The dependency graph already supported it on the day of the split —
//! `sim-core` has zero dependencies, `ruleset-core` is `sim-core + blake3` with
//! no `fs`/`net`/`io` anywhere in its source. Nothing had to be weakened to get
//! here.
//!
//! **`scripts/crate-purity-gate.py` is what keeps it true**, and its strongest
//! rule is not the dependency allowlist but the capability scan: no `std::fs`,
//! `std::net`, `std::process`, `std::env`, `SystemTime` or `Instant` in this
//! crate's source. A law that reads a file has to name a path to do it.
//!
//! ## Determinism, restated because it is the reason for all of the above
//!
//! Every law here is integer-only — not because DF7-A4 bans float (revised
//! 2026-08-02: it does not; it requires one byte representation per value),
//! but because these numbers are integers on a fixed scale and fixed-point is
//! the representation that fits them. A law reads no ambient randomness (rolls
//! are derived per-coordinate — see [`combat`]) and touches no clock. Same inputs,
//! byte-identical outputs, on any machine — which is what makes replaying a
//! committed encounter a recovery model instead of a hope.

pub mod combat;
pub mod stats;
