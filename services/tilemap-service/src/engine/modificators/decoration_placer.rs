//! TMP-Q1 — `DecorationPlacer` (chunk A skeleton).
//!
//! Fills the walkable OPEN region of each zone with cosmetic
//! `primitive: Decoration` objects to address the "visually empty" map
//! gap diagnosed in the quality-push ADR. Opt-in via
//! [`crate::types::template::TilemapTemplate::decoration_density`].
//!
//! **Chunk A scope (this file):** skeleton only. When
//! `template.decoration_density == None`, this placer early-returns —
//! the V2 golden output is byte-identical to the pre-V3 state.
//!
//! **Chunk C will add (later PR):** per-zone OPEN-region computation,
//! biome-filtered weighted tag selection, per-tag min_spacing
//! enforcement with retry-on-reject fallback, and the V3 composed-path
//! snapshot pin.
//!
//! Spec: [`docs/specs/2026-05-28-decoration-placer-density-pass.md`](../../../../docs/specs/2026-05-28-decoration-placer-density-pass.md)
//! Plan: [`docs/plans/2026-05-28-decoration-placer-build.md`](../../../../docs/plans/2026-05-28-decoration-placer-build.md)

use crate::engine::pipeline::{Modificator, ModificatorContext};

/// Visual-density pass. See module doc.
#[derive(Debug)]
pub struct DecorationPlacer;

impl Modificator for DecorationPlacer {
    fn name(&self) -> &str {
        "decoration_placer"
    }

    fn dependencies(&self) -> Vec<&str> {
        // Decoration placer must run AFTER every modificator that mutates
        // the OPEN region (so the "free for decorations" mask is correct).
        // Naming the last-running upstream placers is enough — the
        // topological sort follows transitive deps. Unregistered names
        // are treated as satisfied (pipeline D7), so chunk-A registers
        // these even though chunk-C's full subtraction needs them all.
        vec![
            "road_placer",
            "river_placer",
            "obstacle_fill_placer",
        ]
    }

    fn process(&self, ctx: &mut ModificatorContext<'_>) -> crate::Result<()> {
        // Chunk A: opt-in skeleton. None = no decorations placed = V2
        // golden byte-identical for every existing template fixture.
        if ctx.template.decoration_density.is_none() {
            return Ok(());
        }

        // Chunk C will replace this with the full algorithm. Until then,
        // a Some(..) value is accepted but no decorations are produced.
        // This is intentional: chunk A is a compile-time + V2-preservation
        // milestone. Templates that opt in won't see visible decorations
        // until chunk C lands — that's expected during the 4-chunk arc.
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn name_is_stable() {
        assert_eq!(DecorationPlacer.name(), "decoration_placer");
    }

    #[test]
    fn dependencies_cover_last_running_upstream_placers() {
        let deps = DecorationPlacer.dependencies();
        assert!(deps.contains(&"road_placer"));
        assert!(deps.contains(&"river_placer"));
        assert!(deps.contains(&"obstacle_fill_placer"));
    }
}
