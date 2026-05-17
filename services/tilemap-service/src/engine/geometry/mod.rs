//! Geometry primitives for the modificator pipeline — the "never seal a gap"
//! connectivity invariant (TMP_006 §4) and grid path search (TMP_007 §5).
//! Pure functions over [`TileMask`](crate::types::tile_mask::TileMask); they
//! hold no engine state, so they are trivially deterministic.

pub mod connectivity;
pub mod pathfind;

pub use connectivity::{connected_components, would_seal_a_gap};
pub use pathfind::{Path, search_path};

use crate::types::tile::TileCoord;

/// The 4-connected neighbours of `c` inside a `width × height` grid, yielded in
/// **flat-index ascending order** — up, left, right, down. Both the
/// connectivity flood-fill and the Dijkstra relaxation rely on this fixed order
/// for determinism (TMP-A4).
pub(crate) fn neighbors4(
    c: TileCoord,
    width: u32,
    height: u32,
) -> impl Iterator<Item = TileCoord> {
    let mut out = Vec::with_capacity(4);
    if c.y > 0 {
        out.push(TileCoord::new(c.x, c.y - 1)); // up    — flat (y-1)*w + x
    }
    if c.x > 0 {
        out.push(TileCoord::new(c.x - 1, c.y)); // left  — flat y*w + x-1
    }
    if c.x + 1 < width {
        out.push(TileCoord::new(c.x + 1, c.y)); // right — flat y*w + x+1
    }
    if c.y + 1 < height {
        out.push(TileCoord::new(c.x, c.y + 1)); // down  — flat (y+1)*w + x
    }
    out.into_iter()
}
