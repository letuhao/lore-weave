//! The ruleset vocabulary — identity, ordering, and the two ways a mismatch is
//! refused.
//!
//! Split out of `types.rs` on 2026-07-29 when `Q0b B2a` pushed that file past
//! its ceiling. The cut is along a real seam rather than a line count: these
//! four items are the only ones in the kernel that answer *"which rules is this
//! island running, and may it change?"*, and every one of them is consumed by
//! `island::epoch` together.
//!
//! **Re-exported from `types` so no consumer's import path changed** — the
//! allowlist row that governed the old file warned that a split here "changes
//! every consumer's import paths across four crates", and it would have, which
//! is why it does not.

/// Which ruleset epoch this island is running (`RLS-A13`: **ordering, not
/// identity**).
///
/// The digest below is the identity — two epochs bound to the same bytes have
/// the same digest, and the same rules resolved twice are the same ruleset. The
/// epoch says *which one came later*, which is the only question a switch has
/// to answer and the one a hash cannot.
///
/// **`RLS-I1`: monotonic per island.** A duplicated or re-ordered switch — two
/// nodes racing, a redelivered message, a replay that re-offers an old item —
/// must not move an island backwards onto rules its committed outcomes were not
/// produced under. That is a refusal, not a clamp: see
/// [`Island::activate_epoch`](crate::Island::activate_epoch).
///
/// A separate type from [`Gen`] on purpose, though both are `u32` counters: an
/// island generation is bumped by lifecycle churn many times per epoch, and
/// giving them one type would let a cascade bump silently satisfy a ruleset
/// monotonicity check.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct RulesetEpoch(pub u32);

/// Why an island refused a ruleset epoch switch (`RLS-D8` / `RLS-I1`).
///
/// An enum rather than `bool`/`Option` because the three answers need
/// different operator responses: `NotMonotonic` is usually a *duplicate
/// delivery* and benign, `MidStep` is a kernel bug, and `Poisoned` means the
/// island must be rebuilt. Collapsing them would make the first two look alike.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EpochSwitchRefused {
    /// `RLS-I1` — the offered epoch is not strictly greater than the current
    /// one. Equality is refused too: at-least-once delivery makes duplicates
    /// normal, and a silent `Ok` on the second delivery would hide a genuine
    /// double-activation with different bytes behind the common case.
    NotMonotonic { current: RulesetEpoch, offered: RulesetEpoch },
    /// `RLS-D8` — attempted from inside `step`. Not reachable from a host (the
    /// borrow checker sees to that); reachable only by an edit to `island.rs`,
    /// which is precisely the edit this arm exists to catch.
    MidStep,
    /// `SC-A8` poison-not-resume. Swapping rules is work, and a poisoned island
    /// does not get quietly repaired into a running one.
    Poisoned,
}

impl core::fmt::Display for EpochSwitchRefused {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            Self::NotMonotonic { current, offered } => write!(
                f,
                "ruleset epoch {} is not greater than the island's current {}: a \
                 duplicated or re-ordered switch must not move an island backwards \
                 onto rules its committed outcomes were not produced under (RLS-I1)",
                offered.0, current.0
            ),
            Self::MidStep => write!(
                f,
                "a ruleset switch was attempted from INSIDE step(): RLS-D8 applies the \
                 new Arc between two steps, never within one, or a single item would \
                 be validated under one ruleset and applied under another"
            ),
            Self::Poisoned => write!(
                f,
                "the island is poisoned and must be rebuilt by the host (SC-A8 \
                 poison-not-resume); swapping its rules is work, not repair"
            ),
        }
    }
}

/// Content digest of the resolved `RealityRuleset` this island runs under
/// (RLS-A13). Pinned at construction; the host stamps it into every emitted
/// event's envelope at the S3 boundary.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RulesetDigest(pub [u8; 32]);

impl RulesetDigest {
    /// An island running a domain that has **no content ruleset to hash** — the
    /// kernel's own harness domains (`crates/sim`'s `TestDomain`, benches,
    /// stress bins). Their rules are Rust structs invented by the test, not a
    /// resolved artifact, so there is nothing for a digest to address.
    ///
    /// **This exists so the zero is DECLARED rather than emergent.** The bare
    /// `RulesetDigest([0u8; 32])` literal used to appear in 15 places — four of
    /// them production paths — and read identically in all of them: in a bin it
    /// meant *"we have not wired the loader yet"*, and nothing distinguished
    /// that from *"this domain genuinely has no ruleset."* Same move as
    /// `MAX_HIT` in the damage chain: a declared value has a name and a reason;
    /// an emergent one is a number nobody can explain.
    ///
    /// `scripts/zero-digest-gate.py` bans the anonymous literal repo-wide, and
    /// bans this constant outside `crates/sim` and test files — so reaching for
    /// it in a service binary is a gate finding, not a shortcut.
    pub const UNPINNED: Self = Self([0u8; 32]);

    /// Lowercase hex, 64 chars — the ONE spelling this value has outside Rust.
    ///
    /// The DB column (`events.ruleset_digest CHAR(64)`), the wire schema
    /// (`game-wire/common.schema.json#/$defs/Digest`, `^[0-9a-f]{64}$`) and both
    /// language envelopes all use it, so a second spelling anywhere means two
    /// producers write the same rules under different keys and nothing matches.
    /// Hand-rolled rather than a hex crate: 8 lines, and `sim-core` takes no
    /// runtime dependencies.
    /// The inverse of [`RulesetDigest::to_hex`]. `None` unless the input is
    /// exactly 64 LOWERCASE hex characters.
    ///
    /// It lives here because it had shipped THREE TIMES by the time anyone
    /// looked: `binding::parse_digest`, `epoch::parse_hex`, and a third copy
    /// added the same afternoon. Two of the three accepted upper-case and one
    /// did not, which is the drift a duplicated parser always produces — and
    /// the one spelling this value has outside Rust is lowercase (the DB
    /// `CHAR(64)`, the wire schema's `^[0-9a-f]{64}$`). Rejecting upper-case is
    /// therefore the correct strictness, not an oversight.
    pub fn from_hex(hex: &str) -> Option<Self> {
        if hex.len() != 64 {
            return None;
        }
        let mut out = [0u8; 32];
        for (i, b) in out.iter_mut().enumerate() {
            let pair = hex.get(i * 2..i * 2 + 2)?;
            if !pair.bytes().all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c)) {
                return None;
            }
            *b = u8::from_str_radix(pair, 16).ok()?;
        }
        Some(Self(out))
    }

    pub fn to_hex(&self) -> String {
        const HEX: &[u8; 16] = b"0123456789abcdef";
        let mut out = String::with_capacity(64);
        for b in self.0 {
            out.push(HEX[(b >> 4) as usize] as char);
            out.push(HEX[(b & 0x0f) as usize] as char);
        }
        out
    }
}

/// A checkpoint's ruleset pin does not describe the rules it is being restored
/// under (RLS-A13).
///
/// Carries BOTH digests rather than a bare "mismatch": the operator's first
/// question is *which* ruleset the island was checkpointed under, and an error
/// that cannot answer it turns a five-minute lookup into an archaeology
/// session. Once F2's immutable ruleset store exists, `checkpoint` is the
/// digest to resolve the correct rules BY.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RulesetMismatch {
    /// What the checkpoint was written under.
    pub checkpoint: RulesetDigest,
    /// What the rules handed to `restore` actually hash to.
    pub supplied: RulesetDigest,
}

impl core::fmt::Display for RulesetMismatch {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        write!(
            f,
            "ruleset mismatch: checkpoint pinned {} but the supplied rules hash to {} - \
             refusing to resume under rules the log does not describe",
            self.checkpoint.to_hex(),
            self.supplied.to_hex()
        )
    }
}

