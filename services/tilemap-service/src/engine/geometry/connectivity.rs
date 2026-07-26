//! TMP_006 §4 — the "never seal a gap" connectivity invariant. `would_seal_a_gap`
//! is the most correctness-critical primitive in the modificator pipeline: a
//! false negative ships an unreachable region (catastrophic UX failure).
//!
//! Per spec D5, the check operates on the **passable** region (`Walkable ∪
//! Open`), not the Walkable-only `free_paths`, and uses a label-mapping
//! algorithm that is correct for a multi-component `passable` — a single
//! footprint can split one component while eliminating another, leaving the raw
//! component count unchanged though a real split occurred.

use std::collections::HashMap;

use crate::types::tile::TileCoord;
use crate::types::tile_mask::TileMask;

use super::neighbors4;

/// Per-tile 4-connected component labels of a mask. `label_at` returns 0 for a
/// tile not in the mask, else a component id in `1..=count`.
struct ComponentLabels {
    labels: Vec<u32>,
    width: u32,
    count: u32,
}

impl ComponentLabels {
    fn label_at(&self, c: TileCoord) -> u32 {
        self.labels[c.flat_index(self.width)]
    }
}

/// 4-connected component labelling — iterative flood-fill, seeds taken in
/// flat-index order so the labelling is deterministic.
fn label_components(mask: &TileMask) -> ComponentLabels {
    let width = mask.width();
    let height = mask.height();
    let mut labels = vec![0u32; mask.tile_count()];
    let mut count = 0u32;
    for start in mask.iter_set() {
        if labels[start.flat_index(width)] != 0 {
            continue;
        }
        count += 1;
        labels[start.flat_index(width)] = count;
        let mut stack = vec![start];
        while let Some(t) = stack.pop() {
            for n in neighbors4(t, width, height) {
                let ni = n.flat_index(width);
                if mask.get(n) && labels[ni] == 0 {
                    labels[ni] = count;
                    stack.push(n);
                }
            }
        }
    }
    ComponentLabels { labels, width, count }
}

/// Count the 4-connected components of `mask` (TMP_006 §4.2). Empty mask → 0;
/// diagonal-only adjacency does not connect.
pub fn connected_components(mask: &TileMask) -> usize {
    label_components(mask).count as usize
}

/// TMP_006 §4 / spec D5 — would placing an object whose **blocking** footprint
/// is `blocking` disconnect the passable region `passable` (`Walkable ∪ Open`)?
///
/// Returns `true` iff removing `blocking` from `passable` would **split** a
/// component (some component's surviving tiles fall into ≥2 components of the
/// remainder) **or eliminate** the region entirely. Correct for a
/// multi-component `passable`: the raw component-count delta is *not* used —
/// one footprint can split one component while eliminating another, leaving the
/// count unchanged.
///
/// `blocking` and `passable` must share grid dimensions.
pub fn would_seal_a_gap(blocking: &TileMask, passable: &TileMask) -> bool {
    let mut blocked_after = passable.clone();
    blocked_after.subtract(blocking);

    // Elimination — the object eats the whole passable region.
    if blocked_after.is_empty() {
        return !passable.is_empty();
    }

    // Split — a component of `passable` whose surviving tiles land in more than
    // one component of `blocked_after`.
    let before = label_components(passable);
    let after = label_components(&blocked_after);
    let mut first_after: HashMap<u32, u32> = HashMap::new();
    for tile in blocked_after.iter_set() {
        let before_label = before.label_at(tile);
        let after_label = after.label_at(tile);
        match first_after.get(&before_label) {
            Some(&seen) if seen != after_label => return true,
            Some(_) => {}
            None => {
                first_after.insert(before_label, after_label);
            }
        }
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;
    use rand::{Rng, SeedableRng};
    use rand_chacha::ChaCha8Rng;

    /// Build a `TileMask` from ASCII rows — `'#'` sets a tile, anything else
    /// clears it. All rows must be equal length.
    fn grid(rows: &[&str]) -> TileMask {
        let height = rows.len() as u32;
        let width = rows[0].len() as u32;
        let mut m = TileMask::new(width, height);
        for (y, row) in rows.iter().enumerate() {
            assert_eq!(row.len() as u32, width, "ragged grid fixture");
            for (x, ch) in row.chars().enumerate() {
                if ch == '#' {
                    m.set(TileCoord::new(x as u32, y as u32));
                }
            }
        }
        m
    }

    // ── AC-3 — connected_components ──────────────────────────────────────

    #[test]
    fn connected_components_counts_4_connected_regions() {
        assert_eq!(connected_components(&TileMask::new(5, 5)), 0, "empty mask");
        assert_eq!(connected_components(&grid(&["###", "###"])), 1, "one blob");
        assert_eq!(connected_components(&grid(&["#.#", "#.#"])), 2, "two columns");
    }

    #[test]
    fn connected_components_does_not_connect_diagonally() {
        // Two tiles touching only at a corner are two separate components.
        assert_eq!(connected_components(&grid(&["#.", ".#"])), 2);
    }

    // ── AC-2(a) — would_seal_a_gap hand fixtures ─────────────────────────

    #[test]
    fn corridor_split_seals() {
        // Removing the middle of a 1×3 line splits it 1 → 2.
        let passable = grid(&["###"]);
        let blocking = grid(&[".#."]);
        assert!(would_seal_a_gap(&blocking, &passable));
    }

    #[test]
    fn covering_the_whole_passable_region_seals_by_elimination() {
        let passable = grid(&["###"]);
        let blocking = grid(&["###"]);
        assert!(would_seal_a_gap(&blocking, &passable));
    }

    #[test]
    fn interior_tile_does_not_seal() {
        // Removing the centre of a 3×3 block leaves a connected ring.
        let passable = grid(&["###", "###", "###"]);
        let blocking = grid(&["...", ".#.", "..."]);
        assert!(!would_seal_a_gap(&blocking, &passable));
    }

    #[test]
    fn removing_a_dead_end_stub_does_not_seal() {
        // (2,1) is a stub hanging off the row-0 line; removing it strands nothing.
        let passable = grid(&["###", "..#"]);
        let blocking = grid(&["...", "..#"]);
        assert!(!would_seal_a_gap(&blocking, &passable));
    }

    #[test]
    fn eliminating_an_isolated_pocket_does_not_seal() {
        // `passable` is a 1×3 line + a separate 1-tile pocket; removing the
        // pocket drops a whole component but strands no surviving tile.
        let passable = grid(&["###.#"]);
        let blocking = grid(&["....#"]);
        assert!(!would_seal_a_gap(&blocking, &passable));
    }

    #[test]
    fn three_way_split_seals() {
        // Removing the centre of a T splits it into 3 components.
        let passable = grid(&["#.#", "###", ".#."]);
        let blocking = grid(&["...", ".#.", "..."]);
        assert!(would_seal_a_gap(&blocking, &passable));
    }

    #[test]
    fn multi_component_passable_empty_blocking_does_not_seal() {
        // Two disjoint blobs, blocking nothing — the count is 2 before and
        // after; a count-≥2-after oracle would wrongly say `true`.
        let passable = grid(&["#.#"]);
        let blocking = TileMask::new(3, 1);
        assert!(!would_seal_a_gap(&blocking, &passable));
    }

    #[test]
    fn split_one_component_while_eliminating_another_seals() {
        // `passable` = a 1×3 line (A) + a 1-tile pocket (B). `blocking` splits A
        // at its midpoint AND covers B. Components: 2 before, 2 after — the
        // count is UNCHANGED, yet A was split. The label-mapping catches it; a
        // count-delta check would not. (Spec D5 / r4 BLOCK fixture.)
        let passable = grid(&["###.#"]);
        let blocking = grid(&[".#..#"]);
        assert!(would_seal_a_gap(&blocking, &passable));
    }

    // ── AC-2(b) — differential property test ─────────────────────────────

    /// Independent oracle: `would_seal_a_gap` via all-pairs reachability —
    /// structurally unrelated to the production label-mapping algorithm.
    fn oracle_seals(blocking: &TileMask, passable: &TileMask) -> bool {
        let mut after = passable.clone();
        after.subtract(blocking);
        if after.is_empty() {
            return !passable.is_empty();
        }
        let survivors: Vec<TileCoord> = after.iter_set().collect();
        for (i, &u) in survivors.iter().enumerate() {
            for &v in &survivors[i + 1..] {
                if reachable(passable, u, v) && !reachable(&after, u, v) {
                    return true;
                }
            }
        }
        false
    }

    /// Independent BFS reachability between two set tiles of `mask`.
    fn reachable(mask: &TileMask, from: TileCoord, to: TileCoord) -> bool {
        if !mask.get(from) || !mask.get(to) {
            return false;
        }
        let mut visited = TileMask::new(mask.width(), mask.height());
        let mut stack = vec![from];
        visited.set(from);
        while let Some(t) = stack.pop() {
            if t == to {
                return true;
            }
            for n in neighbors4(t, mask.width(), mask.height()) {
                if mask.get(n) && !visited.get(n) {
                    visited.set(n);
                    stack.push(n);
                }
            }
        }
        false
    }

    fn random_mask(rng: &mut ChaCha8Rng, w: u32, h: u32, density: f64) -> TileMask {
        let mut m = TileMask::new(w, h);
        for y in 0..h {
            for x in 0..w {
                if rng.random_bool(density) {
                    m.set(TileCoord::new(x, y));
                }
            }
        }
        m
    }

    #[test]
    fn would_seal_a_gap_matches_the_independent_reachability_oracle() {
        // 600 random (passable, blocking) pairs on an 8×8 grid — random masks
        // are overwhelmingly multi-component, so this exercises exactly the
        // case a count-delta implementation gets wrong. Fixed RNG seed → the
        // test is reproducible without being single-input.
        let mut rng = ChaCha8Rng::seed_from_u64(0x5EA1_6A99);
        let mut seal_true = 0usize;
        for _ in 0..600 {
            let passable = random_mask(&mut rng, 8, 8, 0.55);
            // Vary blocking density so both verdicts occur in quantity.
            let bd = *[0.1, 0.25, 0.55].get(rng.random_range(0..3)).unwrap();
            let blocking = random_mask(&mut rng, 8, 8, bd);
            let got = would_seal_a_gap(&blocking, &passable);
            let want = oracle_seals(&blocking, &passable);
            assert_eq!(got, want, "verdict mismatch\npassable={passable:?}\nblocking={blocking:?}");
            if want {
                seal_true += 1;
            }
        }
        // Sanity: the corpus actually exercises both verdicts.
        assert!(seal_true > 30, "too few seal=true cases ({seal_true}) — corpus not varied");
        assert!(seal_true < 570, "too few seal=false cases — corpus not varied");
    }

    #[test]
    fn would_seal_a_gap_is_deterministic() {
        let passable = grid(&["###", "#.#", "###"]);
        let blocking = grid(&["...", "#..", "..."]);
        assert_eq!(
            would_seal_a_gap(&blocking, &passable),
            would_seal_a_gap(&blocking, &passable),
        );
    }
}
