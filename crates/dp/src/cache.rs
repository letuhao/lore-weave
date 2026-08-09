//! `DP-K7` — `dp::cache_key!`, and the `KeyId` it converts through.
//!
//! # What the macro is for
//!
//! `DP-R4`: *"Cache keys are built only via the `dp::cache_key!` macro. Feature
//! code does not concatenate strings for cache keys."* The stated violation
//! mode is worth quoting, because it is why a macro rather than a helper
//! function: *"Key format drift (missing `reality_id`, wrong tier prefix, typos
//! in `aggregate_type`) produces silent coherency bugs — the write lands at one
//! key and the read misses elsewhere."* A bug that looks like a stale cache and
//! is actually two different keys.
//!
//! # The shape, and where every token comes from
//!
//! ```text
//! dp:{reality}:r:{tier}:{typ}:{id}[:{subkey}]
//!    ^          ^  ^     ^     ^
//!    |          |  |     |     `- Into<KeyId>, at the call site
//!    |          |  |     `------- <A as DpAggregate>::TYPE_NAME
//!    |          |  `------------- <A::Tier as Tier>::LEVEL.as_key()
//!    |          `---------------- <A::Scope as Scope>::KIND.as_key()
//!    `--------------------------- ctx.reality_id(), which only bind can produce
//! ```
//!
//! **Nothing in that line is a literal at the call site.** Four of the five
//! tokens are read off the aggregate's own types, and the fifth is the session's
//! verified `RealityId`. That is what makes a typo impossible rather than
//! discouraged — the failure mode `DP-R4` describes needs a hand-written string
//! to happen in, and there is nowhere to write one.
//!
//! # The tier argument is CHECKED, not decoration
//!
//! `DP-K7` requires *"`$tier` must match the tier trait of `$aggregate` — else
//! type-check failure"*. It does, and by construction rather than by assertion:
//! the macro passes the tier as a **type parameter** to a function whose bound
//! is `A: DpAggregate<Tier = T>`. Writing `cache_key!(ctx, T1, X, id)` for a
//! `T2` aggregate is then an ordinary type mismatch, reported by rustc at the
//! call site. `tests/ui/cache_key_wrong_tier.rs` pins that.
//!
//! # DEFERRED — the channel-scoped arm (`DP-K7`'s second form)
//!
//! `dp:{reality}:c:{channel}:{tier}:{typ}:{id}` is specified and is NOT built,
//! for the reason §0.6c seals: **nothing produces a `ChannelId`**. Its producer
//! is `DP-Ch9`'s `move_session_to_channel`, which is slice 5, and
//! `SessionContext` carries no channel fields for the same reason. An arm
//! accepting *any* `Display` as a channel would take a forged value and put it
//! in a key, which is worse than not having the arm.
//!
//! Recorded in [`DEFERRED_CACHE_FORMS`], which `tests/spec_oracle.rs` reads.

use crate::aggregate::DpAggregate;
use crate::scope::{RealityScope, Scope};
use crate::session::SessionContext;
use crate::tier::Tier;

/// Cache-key forms `DP-K7` specifies that are NOT built, with their blocker.
///
/// Same discipline as `DEFERRED_IDS` and `DEFERRED_VARIANTS`: a spec'd thing
/// with no producer is recorded rather than shipped, and the oracle fails if a
/// row outlives its reason.
pub const DEFERRED_CACHE_FORMS: &[(&str, &str)] = &[
    ("channel_scoped", "DP-Ch9 move_session_to_channel produces ChannelId (slice 5)"),
];

/// The `{id}` token of a cache key.
///
/// A newtype rather than `impl Display` at the call site, because the set of
/// things that may become a key segment is deliberately small and closed. Two
/// rules it enforces that a bare `to_string()` would not:
///
///   * **A colon in an id would forge a key segment.** `dp:R:r:t2:x:a:b` is
///     indistinguishable from a subkey, so an id containing `:` could collide
///     with a different aggregate's entry. [`KeyId::new`] rejects it.
///   * **An empty id is not an id.** It would produce a trailing colon and a
///     key that reads as a prefix, which is how a targeted read becomes a
///     scan.
#[derive(Clone, Debug, Eq, PartialEq, Hash)]
pub struct KeyId(String);

impl KeyId {
    /// Build a key segment, rejecting anything that would change the key's
    /// shape.
    ///
    /// Returns `None` rather than panicking: a bad id is a caller error to
    /// handle, and a panic inside a cache-key expansion would abort a request
    /// path over a data problem.
    pub fn new(raw: impl Into<String>) -> Option<Self> {
        let s = raw.into();
        if s.is_empty() || s.contains(':') {
            return None;
        }
        Some(Self(s))
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl From<uuid::Uuid> for KeyId {
    /// Always valid: a hyphenated UUID contains no colon and is never empty.
    fn from(u: uuid::Uuid) -> Self {
        Self(u.to_string())
    }
}

impl From<u64> for KeyId {
    fn from(n: u64) -> Self {
        Self(n.to_string())
    }
}

impl From<i64> for KeyId {
    fn from(n: i64) -> Self {
        Self(n.to_string())
    }
}

/// Build a reality-scoped cache key. **Call it through [`crate::cache_key!`].**
///
/// Public because the macro expands to a path into it, not because feature code
/// should call it directly — calling it directly is not a *violation* (it still
/// derives every token from types), it is just less readable than the macro.
///
/// The two type parameters are the enforcement. `A: DpAggregate<Tier = T,
/// Scope = RealityScope>` makes a wrong tier and a channel-scoped aggregate
/// both type errors rather than runtime surprises.
pub fn reality_key<A, T>(ctx: &SessionContext, id: impl Into<KeyId>, subkeys: &[&str]) -> String
where
    T: Tier,
    A: DpAggregate<Tier = T, Scope = RealityScope>,
{
    let mut out = format!(
        "dp:{reality}:{scope}:{tier}:{typ}:{id}",
        reality = ctx.reality_id(),
        scope = <A::Scope as Scope>::KIND.as_key(),
        tier = <A::Tier as Tier>::LEVEL.as_key(),
        typ = A::TYPE_NAME,
        id = id.into().as_str(),
    );
    for sk in subkeys {
        out.push(':');
        out.push_str(sk);
    }
    out
}

/// `DP-K7` — the only sanctioned way to build a cache key.
///
/// ```ignore
/// let k = dp::cache_key!(ctx, T2, PlayerInventory, player_id);
/// let k = dp::cache_key!(ctx, T2, PlayerInventory, player_id, "equipped");
/// ```
///
/// The channel-scoped form (`; channel = ...`) is NOT implemented — see
/// [`DEFERRED_CACHE_FORMS`]. Writing it produces a "no rules expected" error,
/// which is the correct outcome: there is no `ChannelId` to pass it.
#[macro_export]
macro_rules! cache_key {
    ($ctx:expr, $tier:ident, $aggregate:ty, $id:expr $(, $subkey:expr)* $(,)?) => {
        $crate::cache::reality_key::<$aggregate, $crate::tier::$tier>(
            $ctx,
            $id,
            &[$($subkey),*],
        )
    };
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::scope::RealityScope;
    use crate::session::{BindRequest, ControlPlane, SessionContext, VerifiedBind};
    use crate::tier::{T1, T2};
    use crate::DpError;

    struct Inventory;
    impl DpAggregate for Inventory {
        type Tier = T2;
        type Scope = RealityScope;
        type Id = uuid::Uuid;
        type Delta = ();
        type Projection = ();
        const TYPE_NAME: &'static str = "cache_key_fixture";
    }

    struct Cp;
    impl ControlPlane for Cp {
        fn verify_bind(&self, req: &BindRequest) -> Result<VerifiedBind, DpError> {
            Ok(VerifiedBind {
                reality: req.reality,
                session: uuid::Uuid::from_u128(7),
                capability_secret: "s".into(),
                expires_at_ms: 10_000,
            })
        }
    }

    fn ctx() -> SessionContext {
        SessionContext::bind(
            &Cp,
            BindRequest {
                reality: uuid::Uuid::from_u128(1),
                node: "n".into(),
                service: crate::ServiceIdentity::new("test-harness").expect("valid"),
            },
            0,
        )
        .expect("bind")
    }

    #[test]
    fn the_key_has_the_dp_k7_shape() {
        let k = cache_key!(&ctx(), T2, Inventory, uuid::Uuid::from_u128(2));
        assert_eq!(
            k,
            "dp:00000000-0000-0000-0000-000000000001:r:t2:cache_key_fixture:\
             00000000-0000-0000-0000-000000000002"
                .replace(' ', "")
        );
    }

    #[test]
    fn every_token_comes_from_a_type_not_the_call_site() {
        // The point of DP-R4: nothing here is spelled by the caller. Changing
        // TYPE_NAME or the tier changes the key without the call site moving.
        let k = cache_key!(&ctx(), T2, Inventory, 42u64);
        assert!(k.contains(":r:"), "scope token from A::Scope::KIND: {k}");
        assert!(k.contains(":t2:"), "tier token from A::Tier::LEVEL: {k}");
        assert!(k.contains(":cache_key_fixture:"), "type token from TYPE_NAME: {k}");
        assert!(k.starts_with("dp:00000000-0000-0000-0000-000000000001:"), "reality: {k}");
        assert!(k.ends_with(":42"), "id: {k}");
    }

    #[test]
    fn subkeys_append_in_order() {
        let k = cache_key!(&ctx(), T2, Inventory, 1u64, "equipped", "left");
        assert!(k.ends_with(":1:equipped:left"), "{k}");
    }

    #[test]
    fn a_colon_in_an_id_is_refused() {
        // Without this, an id could forge a subkey boundary and collide with a
        // different entry — a silent coherency bug, which is the exact failure
        // DP-R4 exists to prevent.
        assert!(KeyId::new("a:b").is_none());
        assert!(KeyId::new("").is_none(), "an empty id makes the key read as a prefix");
        assert_eq!(KeyId::new("ok").unwrap().as_str(), "ok");
    }

    #[test]
    fn uuid_and_integer_ids_are_always_valid() {
        assert!(!KeyId::from(uuid::Uuid::from_u128(3)).as_str().contains(':'));
        assert_eq!(KeyId::from(7u64).as_str(), "7");
        assert_eq!(KeyId::from(-7i64).as_str(), "-7");
    }

    /// The tier argument is load-bearing: `T1` here would not compile.
    /// `tests/ui/cache_key_wrong_tier.rs` is that claim executed by rustc;
    /// this test only records that `T1` exists and is a different type, so the
    /// ui case is not passing because the name is undefined.
    #[test]
    fn the_wrong_tier_is_a_real_type_that_simply_does_not_match() {
        assert_eq!(<T1 as Tier>::LEVEL.as_key(), "t1");
        assert_eq!(<T2 as Tier>::LEVEL.as_key(), "t2");
    }
}
