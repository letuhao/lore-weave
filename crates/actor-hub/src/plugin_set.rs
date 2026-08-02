//! `PluginSet` — hub §3.4: **which plugins are attached to this actor.**
//!
//! ```text
//! 4  ATTACHMENT  PluginSet — a u32 bitmask over plugin ordinals
//! ```
//!
//! ## Why a bitmask and not a list of granted things
//!
//! > **`granted` is not a field.** Quantity `q` is present **exactly when the
//! > plugin that declares `q` is attached** — a village has no hp because combat
//! > is not attached; a stone has no qi because cultivation is not. **One fact,
//! > nothing to keep in step.**
//!
//! A second field recording *which quantities an actor has* would be a second
//! copy of a fact the attachment set already determines, and two copies of one
//! fact drift. The mask is the only record; presence is **derived** from it by
//! [`crate::HubRegistry::is_present`].
//!
//! ## What the hub knows about a plugin
//!
//! Its ordinal. Nothing else. **The hub knows nothing about what any plugin
//! means** — that is the whole decoupling, and it is why this type has no name
//! table, no kind discriminator, and no per-plugin behaviour.

use crate::ordinal::{MAX_PLUGINS, PluginOrdinal};

/// The set of plugins attached to one actor.
///
/// `Copy`, 4 bytes, and stored inline in the actor — hub §5: *"attachment does
/// not mean remote."*
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Default)]
pub struct PluginSet(u32);

impl PluginSet {
    /// Nothing attached. **Not "an actor with no quantities" — an actor with no
    /// quantities *declared*.** The difference is hub §3.4b: an unattached
    /// plugin's quantity is ABSENT, not zero.
    pub const EMPTY: Self = Self(0);

    /// Build from a raw mask. Total: every `u32` is a valid set, because every
    /// bit position is a valid [`PluginOrdinal`] (the widths agree — see
    /// `ordinal::MAX_PLUGINS`).
    pub const fn from_bits(bits: u32) -> Self {
        Self(bits)
    }

    /// The raw mask, for encoding.
    pub const fn bits(self) -> u32 {
        self.0
    }

    /// Attach a plugin. Idempotent: attaching twice is the same set, because a
    /// set is a set. **Attachment is not a counter** — a "how many times
    /// attached" field would need a detach protocol to match it, and hub §3.4
    /// deliberately has one fact and nothing to keep in step.
    #[must_use]
    pub const fn attach(self, p: PluginOrdinal) -> Self {
        Self(self.0 | p.bit())
    }

    /// Detach a plugin.
    ///
    /// **What happens to the quantities it declared is NOT decided here.** Hub
    /// §3.4b makes them ABSENT again by construction — presence is derived from
    /// this mask — but *whether a stored value survives a detach/re-attach* is
    /// `M-2`, and `D-289` ruled it **PREMATURE**: detach *which* plugin, when
    /// plugin #2 does not exist? Its trigger is *"when plugin #2 is declared"*.
    /// This method exists because a set without a removal verb is not a set;
    /// it does not answer the question.
    #[must_use]
    pub const fn detach(self, p: PluginOrdinal) -> Self {
        Self(self.0 & !p.bit())
    }

    /// Is this plugin attached?
    pub const fn contains(self, p: PluginOrdinal) -> bool {
        self.0 & p.bit() != 0
    }

    /// How many plugins are attached.
    pub const fn len(self) -> usize {
        self.0.count_ones() as usize
    }

    pub const fn is_empty(self) -> bool {
        self.0 == 0
    }

    /// The attached ordinals, **in ascending ordinal order**.
    ///
    /// **Correction, after a review measured it:** an earlier version of this doc
    /// justified the order by saying *"the fold walks contributions from attached
    /// plugins"*. It does not — [`crate::fold`] iterates quantity ordinals and
    /// never calls this method. The order is a property worth having and worth
    /// stating (a bitmask has no insertion order to depend on, so a re-fold
    /// cannot depend on how the actor was assembled), but attributing it to a
    /// caller that does not exist is the citation failure this project has
    /// recorded 22 times.
    ///
    /// **Who does call it: nobody in this crate outside tests, today.** It is
    /// here because a set without an enumeration verb is not a set, and because
    /// the first plugin host will need it.
    pub fn iter(self) -> impl Iterator<Item = PluginOrdinal> {
        (0..MAX_PLUGINS as u8)
            .filter_map(PluginOrdinal::new)
            .filter(move |p| self.contains(*p))
    }
}

impl FromIterator<PluginOrdinal> for PluginSet {
    fn from_iter<T: IntoIterator<Item = PluginOrdinal>>(iter: T) -> Self {
        iter.into_iter().fold(Self::EMPTY, Self::attach)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn p(raw: u8) -> PluginOrdinal {
        PluginOrdinal::new(raw).expect("ordinal in range")
    }

    #[test]
    fn empty_contains_nothing() {
        let s = PluginSet::EMPTY;
        assert!(s.is_empty());
        assert_eq!(s.len(), 0);
        for raw in 0..MAX_PLUGINS as u8 {
            assert!(!s.contains(p(raw)));
        }
        assert_eq!(s.iter().count(), 0);
    }

    #[test]
    fn attach_then_contains() {
        let s = PluginSet::EMPTY.attach(p(0)).attach(p(31));
        assert!(s.contains(p(0)));
        assert!(s.contains(p(31)));
        assert!(!s.contains(p(1)));
        assert_eq!(s.len(), 2);
    }

    #[test]
    fn attach_is_idempotent() {
        let once = PluginSet::EMPTY.attach(p(7));
        let twice = once.attach(p(7));
        assert_eq!(once, twice);
        assert_eq!(twice.len(), 1);
    }

    #[test]
    fn detach_removes_only_its_own_bit() {
        let s = PluginSet::EMPTY.attach(p(3)).attach(p(4)).detach(p(3));
        assert!(!s.contains(p(3)));
        assert!(s.contains(p(4)));
        // Detaching something never attached is a no-op, not an error: the set
        // has no state that could disagree.
        assert_eq!(s, s.detach(p(9)));
    }

    /// The property the type exists for: **iteration order is ordinal order,
    /// never insertion order.** Two sets built in opposite orders iterate the
    /// same, so a re-fold cannot depend on how the actor was assembled.
    #[test]
    fn iteration_order_is_independent_of_attach_order() {
        let forward: PluginSet = [2u8, 9, 17, 31].iter().map(|r| p(*r)).collect();
        let backward: PluginSet = [31u8, 17, 9, 2].iter().map(|r| p(*r)).collect();
        assert_eq!(forward, backward);
        let seen: Vec<u8> = forward.iter().map(PluginOrdinal::get).collect();
        assert_eq!(seen, vec![2, 9, 17, 31]);
    }

    /// Every ordinal is reachable, including the last one — the case a `u32`
    /// shift would get wrong if `MAX_PLUGINS` ever exceeded 32.
    #[test]
    fn every_ordinal_round_trips() {
        for raw in 0..MAX_PLUGINS as u8 {
            let s = PluginSet::EMPTY.attach(p(raw));
            assert_eq!(s.len(), 1, "ordinal {raw} did not set exactly one bit");
            assert_eq!(s.iter().next(), Some(p(raw)));
            assert!(s.detach(p(raw)).is_empty());
        }
        let all: PluginSet = (0..MAX_PLUGINS as u8).map(p).collect();
        assert_eq!(all.len(), MAX_PLUGINS);
        assert_eq!(all.bits(), u32::MAX);
    }

    #[test]
    fn bits_round_trip() {
        let s: PluginSet = [0u8, 5, 30].iter().map(|r| p(*r)).collect();
        assert_eq!(PluginSet::from_bits(s.bits()), s);
    }
}
