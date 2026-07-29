//! The structural registries — entity and encounter generations.
//!
//! A CHILD module of `island` (it reads the parent's private `entities` /
//! `encounters` maps directly). The seam: everything here is `sim-core`'s OWN
//! bookkeeping about who exists, as distinct from the step loop that consumes
//! it and the domain state it knows nothing about.
//!
//! Split out on 2026-07-29 when `Q0b B2b` pushed `island/mod.rs` past its
//! recorded ceiling. Nothing changed in the move.

use super::Island;
use crate::domain::Domain;
use crate::types::{EntityId, Gen};

impl<D: Domain> Island<D> {
    // ─── structural registry (S1a surface; the invalidation CASCADE is S1b) ───

    /// Spawning over an id this island ALREADY tracks bumps its generation
    /// (same rule as `arrive` — review-impl S2 finding 2): re-inserting at
    /// Gen(0) would RESURRECT old-epoch refs pinned to Gen(0).
    pub fn spawn_entity(&mut self, id: EntityId) -> Gen {
        let g = match self.entities.get(&id) {
            Some(prev) => Gen(prev.0.saturating_add(1)),
            None => Gen(0),
        };
        self.entities.insert(id, g);
        g
    }

    /// Bump an entity's generation — every in-flight input holding the old
    /// gen becomes stale and will discard at ITS step (never retroactively).
    pub fn bump_entity_gen(&mut self, id: EntityId) -> Option<Gen> {
        let g = self.entities.get_mut(&id)?;
        // Saturating: a wrap at u32::MAX would RESURRECT stale generations;
        // pinning at MAX makes everything stale-forever — the safe direction.
        *g = Gen(g.0.saturating_add(1));
        Some(*g)
    }

    pub fn despawn_entity(&mut self, id: EntityId) {
        self.entities.remove(&id);
    }

    pub fn entity_gen(&self, id: EntityId) -> Option<Gen> {
        self.entities.get(&id).copied()
    }

    /// Same anti-resurrection rule as `spawn_entity`.
    pub fn start_encounter(&mut self, id: EntityId) -> Gen {
        let g = match self.encounters.get(&id) {
            Some(prev) => Gen(prev.0.saturating_add(1)),
            None => Gen(0),
        };
        self.encounters.insert(id, g);
        g
    }

    pub fn end_encounter(&mut self, id: EntityId) {
        self.encounters.remove(&id);
    }
}
