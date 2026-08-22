//! The two ordinal spaces the hub addresses, and what is and is not mechanised
//! about each.
//!
//! > **A declared quantity is addressed by an ORDINAL, assigned once and NEVER
//! > reused. A name is the author's; an ordinal is the mechanism's.**
//! > — engine substrate §4
//!
//! ## The QUANTITY space — assigned and checked elsewhere
//!
//! [`ruleset_core::QuantityTable`] assigns it inside the hashed ruleset bytes,
//! and `ruleset-core`'s `never_reuse` walks every prior epoch's table to catch a
//! renumber. This module adds only the **typed address**.
//!
//! ## The PLUGIN space — introduced here, and its never-reuse check does NOT exist
//!
//! Stated plainly rather than implied by the section above it. The law is the
//! same — a plugin ordinal is assigned once and never reused, because a
//! renumbering silently redefines every stored attachment — but **no mechanism
//! enforces it in this crate, and none should yet.**
//!
//! `D-289` ruled `M-8` **PREMATURE**: the shape is known (`never_reuse.rs` is
//! the template) but **an ordinal space with one member cannot be renumbered**,
//! so a check built today would have no failing input — which is `NV-1` vacuity,
//! not coverage. **Trigger: when plugin #2 is declared.** Naming the absent
//! check is the obligation `NV-6` imposes; *"an axiom does not become true by
//! being written down."*
//!
//! ## Why a newtype rather than a bare integer — and the failure it does NOT fix
//!
//! Both spaces are small unsigned integers, and both index arrays. A bare `u16`
//! passed to a function expecting the *other* space compiles and reads the wrong
//! slot forever. **A newtype makes that SPACE confusion a type error, and that is
//! the whole of what it buys.**
//!
//! It does **nothing** about **table** confusion, which is a different failure:
//! `QTY-A14` — *"an L2 ordinal is meaningless without `(reality_id,
//! ruleset_digest)`; any datum that leaves the island carrying an ordinal MUST
//! carry the digest that gives it meaning."* Reality A's ordinal 3 is `qi` and
//! reality B's is `mana`; [`QuantityOrdinal::new(3)`](QuantityOrdinal::new)
//! succeeds against both, and the derived `PartialEq`/`Ord`/`Hash` compare the
//! two **equal**. Nothing here refuses that, because nothing here carries a
//! digest. **The carrier `QTY-A14` demands is UNWRITTEN**, and it belongs to
//! whatever first moves a quantity across a reality boundary — the same seam
//! `S-9` registers for identity. Conflating the two failures is how a reader
//! greps `QTY-A14`, finds it *"addressed"*, and never builds the carrier.
//!
//! ## The bound is checked at CONSTRUCTION, not at use
//!
//! [`QuantityOrdinal::new`] and [`PluginOrdinal::new`] refuse out-of-range
//! input, so every value of these types is a valid index into an array of the
//! corresponding width. Callers that already hold one never need a second check,
//! and there is no path that produces an unchecked one.

use ruleset_core::MAX_DECLARED_QUANTITIES;

/// How many plugins may be attached to one actor — hub §3.4.
///
/// **Tied to [`MAX_DECLARED_QUANTITIES`] on purpose**, so the two ceilings move
/// together instead of drifting apart (`D-255`). The `const` assertion directly
/// below is what makes that a mechanism rather than a comment.
///
/// Raising it later is an engine release that **moves no existing digest** —
/// only `0..n` is ever encoded — while lowering it is impossible, so 32 is the
/// reversible direction. The 33rd plugin **does** touch actor core, and that is
/// a **version bump**: visible and costed, not a silent failure (hub §6).
pub const MAX_PLUGINS: usize = MAX_DECLARED_QUANTITIES;

// The width agreement, as a compile-time check rather than a promise.
//
// `PluginSet` is a `u32` bitmask, so it can hold exactly 32 ordinals. If someone
// raises `MAX_DECLARED_QUANTITIES`, `MAX_PLUGINS` follows it and this assertion
// reds at compile time — the bitmask would silently drop plugins 32.. otherwise.
//
// **This assertion can fail**, and it was measured doing so: at 16 and at 64 it
// emits `error[E0080]` naming this line. Its subject varies with a constant a
// future author has a real reason to change (`quantity.rs` calls raising it
// cheap). Contrast a `size_of` assertion on a BOXED payload, which is 16 bytes
// for every possible content — see `docs/standards/non-vacuity.md`.
//
// One thing the narration must be honest about: at 64 the FIRST error a builder
// sees is `ruleset.rs`'s own `size_of::<Ruleset>()` budget, because the wider
// table makes the ruleset bigger. This assertion fires on the next build, once
// that budget is repinned. It is a second gate on the same change, not the first.
//
// Written as an anonymous `const _` rather than a named one: a named constant is
// still evaluated, but rustc then warns it is never used, and the `const _ = NAME;`
// line added to silence that reads like the mechanism when it is only a
// dead-code suppressor.
const _: () = assert!(
    MAX_PLUGINS == u32::BITS as usize,
    "PluginSet is a u32 bitmask and can hold exactly 32 plugin ordinals. \
     MAX_PLUGINS is tied to MAX_DECLARED_QUANTITIES so the two ceilings move \
     together; raising that constant past 32 requires widening PluginSet in \
     the same change, or plugins above ordinal 31 are silently unattachable."
);

/// The address of a declared quantity — an index into the actor's array and
/// into [`ruleset_core::QuantityTable`], which is the same space.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct QuantityOrdinal(u16);

impl QuantityOrdinal {
    /// Refuses anything at or past the declared width.
    pub const fn new(raw: u16) -> Option<Self> {
        if (raw as usize) < MAX_DECLARED_QUANTITIES {
            Some(Self(raw))
        } else {
            None
        }
    }

    /// The raw ordinal, for encoding and for indexing the quantity table.
    pub const fn get(self) -> u16 {
        self.0
    }

    /// As an array index. Total by construction — see the module doc.
    pub const fn index(self) -> usize {
        self.0 as usize
    }
}

/// The address of a plugin — hub §3.4, a bit position in [`PluginSet`].
///
/// [`PluginSet`]: crate::PluginSet
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct PluginOrdinal(u8);

impl PluginOrdinal {
    /// Refuses anything at or past [`MAX_PLUGINS`].
    pub const fn new(raw: u8) -> Option<Self> {
        if (raw as usize) < MAX_PLUGINS {
            Some(Self(raw))
        } else {
            None
        }
    }

    pub const fn get(self) -> u8 {
        self.0
    }

    pub const fn index(self) -> usize {
        self.0 as usize
    }

    /// The single-bit mask this ordinal owns inside a [`crate::PluginSet`].
    pub(crate) const fn bit(self) -> u32 {
        1u32 << self.0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn quantity_ordinal_refuses_past_the_declared_width() {
        assert!(QuantityOrdinal::new(0).is_some());
        assert!(QuantityOrdinal::new(MAX_DECLARED_QUANTITIES as u16 - 1).is_some());
        assert!(QuantityOrdinal::new(MAX_DECLARED_QUANTITIES as u16).is_none());
        assert!(QuantityOrdinal::new(u16::MAX).is_none());
    }

    /// `get` is the ENCODING path — it is what a persisted or wire-bound datum
    /// carries — so a wrong ordinal here is the never-reuse hazard the module
    /// doc invokes, arriving silently. Round-tripping every constructible value
    /// is what makes it observable. (Added after a review measured that
    /// replacing the body with `0` reddened nothing.)
    #[test]
    fn quantity_ordinal_round_trips_through_get_and_index() {
        for raw in 0..MAX_DECLARED_QUANTITIES as u16 {
            let q = QuantityOrdinal::new(raw).unwrap();
            assert_eq!(q.get(), raw, "get() must return the ordinal it was built from");
            assert_eq!(q.index(), raw as usize);
            assert_eq!(QuantityOrdinal::new(q.get()), Some(q));
        }
    }

    /// The same for the plugin space, and for the same reason.
    #[test]
    fn plugin_ordinal_round_trips_through_get_and_index() {
        for raw in 0..MAX_PLUGINS as u8 {
            let p = PluginOrdinal::new(raw).unwrap();
            assert_eq!(p.get(), raw);
            assert_eq!(p.index(), raw as usize);
            assert_eq!(PluginOrdinal::new(p.get()), Some(p));
        }
    }

    #[test]
    fn plugin_ordinal_refuses_past_max_plugins() {
        assert!(PluginOrdinal::new(0).is_some());
        assert!(PluginOrdinal::new(MAX_PLUGINS as u8 - 1).is_some());
        assert!(PluginOrdinal::new(MAX_PLUGINS as u8).is_none());
        assert!(PluginOrdinal::new(u8::MAX).is_none());
    }

    /// Every constructible ordinal indexes an array of the declared width. This
    /// is the property the type exists to buy, so it is asserted rather than
    /// assumed.
    #[test]
    fn every_constructible_ordinal_is_a_valid_index() {
        let slots = [0i32; MAX_DECLARED_QUANTITIES];
        for raw in 0..=u16::MAX {
            if let Some(q) = QuantityOrdinal::new(raw) {
                assert_eq!(slots[q.index()], 0);
            }
        }
        let bits = [false; MAX_PLUGINS];
        for raw in 0..=u8::MAX {
            if let Some(p) = PluginOrdinal::new(raw) {
                assert!(!bits[p.index()]);
            }
        }
    }

    /// The bit an ordinal owns is unique, and ordinal 31 is the last that fits.
    #[test]
    fn plugin_bits_are_distinct_and_fit_the_mask() {
        let mut seen = 0u32;
        for raw in 0..MAX_PLUGINS as u8 {
            let bit = PluginOrdinal::new(raw).unwrap().bit();
            assert_eq!(seen & bit, 0, "ordinal {raw} reused a bit");
            seen |= bit;
        }
        assert_eq!(seen, u32::MAX, "the ordinals do not cover the whole mask");
    }
}
