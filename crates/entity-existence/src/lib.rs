//! `entity-existence` — **is this row reachable?**
//!
//! The lattice, its precedence order, and nothing else. Extracted from
//! `dp-kernel::entity_status` (cycle 20 / L4.E) so a **pure** crate can hold it;
//! see this crate's `Cargo.toml` for why that extraction happened rather than a
//! copy.
//!
//! ## What this answers, and what it deliberately does not
//!
//! > **It answers *"is this row reachable?"* — PLATFORM existence. Fiction
//! > existence, alive or dead, is a STATUS and is not here. Two beings can both
//! > be `Active` while one is a corpse.**
//! > — actor-hub contract §3.3
//!
//! That distinction is the reason this enum can be adopted by the actor hub
//! without the hub acquiring an opinion about death, unconsciousness, or any
//! other fiction state. Those belong to a status plugin that does not exist yet.
//!
//! ## Parity with Go
//!
//! `contracts/entity_status/gone_state.go` is the Go mirror; the wire form is
//! canonical `snake_case` and the precedence ranks match. Both properties are
//! asserted in `dp-kernel`'s tests, which exercise this type through the
//! re-export — so the parity suite did not move away from the platform side
//! that owns the contract.

use serde::{Deserialize, Serialize};

/// Lifecycle state of a game entity. Wire format = canonical snake_case.
/// Mirrors `GoneState` in `contracts/entity_status/gone_state.go`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum GoneState {
    /// Entity is live and reachable.
    Active,
    /// Entity moved between realities or was disconnected from its parent.
    Severed,
    /// Entity's home reality was archived.
    Archived,
    /// Entity (or its reality) was hard-deleted. Terminal.
    Dropped,
    /// Entity's PII was crypto-shredded (GDPR Art. 17). Terminal.
    UserErased,
}

impl GoneState {
    /// Canonical snake_case string form.
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Active => "active",
            Self::Severed => "severed",
            Self::Archived => "archived",
            Self::Dropped => "dropped",
            Self::UserErased => "user_erased",
        }
    }

    /// True iff the entity is reachable for normal hot-path reads.
    pub fn is_live(&self) -> bool {
        matches!(self, Self::Active)
    }

    /// True iff the state never transitions back to `Active`.
    pub fn is_terminal(&self) -> bool {
        matches!(self, Self::Dropped | Self::UserErased)
    }
}

/// Precedence rank — higher wins. Mirrors `precedence.go::precedenceRank`.
fn precedence_rank(s: GoneState) -> u8 {
    match s {
        GoneState::Dropped => 5,
        GoneState::UserErased => 4,
        GoneState::Severed => 3,
        GoneState::Archived => 2,
        GoneState::Active => 1,
    }
}

/// Returns whichever of `(a, b)` has stronger precedence.
pub fn higher(a: GoneState, b: GoneState) -> GoneState {
    if precedence_rank(a) >= precedence_rank(b) { a } else { b }
}

/// Reduce N candidates to the strongest. Empty = `Active`.
pub fn reduce(states: &[GoneState]) -> GoneState {
    let mut winner = GoneState::Active;
    for s in states {
        winner = higher(winner, *s);
    }
    winner
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Every variant, so a sixth added without a rank is caught here rather
    /// than by whichever caller happens to compare it first.
    const ALL: [GoneState; 5] = [
        GoneState::Active,
        GoneState::Severed,
        GoneState::Archived,
        GoneState::Dropped,
        GoneState::UserErased,
    ];

    #[test]
    fn precedence_is_a_strict_total_order() {
        let mut ranks: Vec<u8> = ALL.iter().map(|s| precedence_rank(*s)).collect();
        ranks.sort_unstable();
        ranks.dedup();
        assert_eq!(ranks.len(), ALL.len(), "two states share a precedence rank");
    }

    /// `higher` must not depend on argument order — the resolver folds layer
    /// answers in whatever order the cascade produced them.
    #[test]
    fn higher_is_commutative() {
        for a in ALL {
            for b in ALL {
                assert_eq!(higher(a, b), higher(b, a), "higher({a:?}, {b:?}) is order-dependent");
            }
        }
    }

    #[test]
    fn dropped_beats_every_other_state() {
        for s in ALL {
            assert_eq!(higher(GoneState::Dropped, s), GoneState::Dropped);
        }
    }

    #[test]
    fn reduce_empty_is_active() {
        assert_eq!(reduce(&[]), GoneState::Active);
    }

    #[test]
    fn reduce_picks_the_strongest_regardless_of_input_order() {
        let forward = [GoneState::Active, GoneState::Archived, GoneState::Severed];
        let backward = [GoneState::Severed, GoneState::Archived, GoneState::Active];
        assert_eq!(reduce(&forward), GoneState::Severed);
        assert_eq!(reduce(&backward), GoneState::Severed);
    }

    #[test]
    fn live_and_terminal_partition_as_documented() {
        assert!(GoneState::Active.is_live());
        for s in ALL {
            if s != GoneState::Active {
                assert!(!s.is_live(), "{s:?} must not be live");
            }
        }
        assert!(GoneState::Dropped.is_terminal());
        assert!(GoneState::UserErased.is_terminal());
        assert!(!GoneState::Severed.is_terminal());
        assert!(!GoneState::Archived.is_terminal());
        assert!(!GoneState::Active.is_terminal());
    }
}
