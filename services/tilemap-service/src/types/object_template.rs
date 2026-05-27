//! TMP_005 §2.1 / TMP_006 §3.1 — object footprint descriptor. A
//! [`TilemapObjectTemplate`] declares which tiles an object occupies relative
//! to an anchor and which of those block movement. The placement engine
//! (Phase A `ObjectManager`) projects a footprint onto the grid at a candidate
//! anchor.

use serde::{Deserialize, Serialize};

use crate::types::tile::TileCoord;
use crate::types::tile_mask::TileMask;
use crate::types::tilemap::GridSize;

/// One cell of an object footprint — a signed offset from the object's anchor
/// plus whether it blocks movement. A non-blocking cell (e.g. a tree-canopy
/// overhang) is occupied visually but does not break paths, so it is excluded
/// from the connectivity check (TMP_006 §4 — see [`Self::blocking`]).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct FootprintCell {
    pub dx: i32,
    pub dy: i32,
    /// Whether this cell blocks actor movement. Only blocking cells feed
    /// `would_seal_a_gap`.
    pub blocking: bool,
}

impl FootprintCell {
    /// A blocking cell at the given offset — the common case.
    pub fn blocking(dx: i32, dy: i32) -> Self {
        Self { dx, dy, blocking: true }
    }
}

/// A placeable object's footprint — TMP_005 §2.1 "which tiles the object
/// occupies + which are blocking". The anchor is the `(0, 0)` reference; cell
/// offsets are signed so a footprint can extend in any direction from it.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TilemapObjectTemplate {
    pub name: String,
    pub cells: Vec<FootprintCell>,
}

impl TilemapObjectTemplate {
    /// Project every occupied cell onto the grid at `anchor`. `None` if any cell
    /// lands out of bounds — the object does not fit there at all.
    pub fn footprint_at(&self, anchor: TileCoord, grid: GridSize) -> Option<TileMask> {
        self.project(anchor, grid, false)
    }

    /// Project only the **blocking** cells — the mask the connectivity check
    /// (`would_seal_a_gap`) consumes. `None` on any out-of-bounds cell, matching
    /// [`Self::footprint_at`]: an object that does not fit has no blocking mask
    /// either, so the two projections agree on `None`.
    pub fn blocking_footprint_at(&self, anchor: TileCoord, grid: GridSize) -> Option<TileMask> {
        self.project(anchor, grid, true)
    }

    /// Shared projection. `blocking_only` filters which cells are *set*, but
    /// bounds are checked against **every** cell — so both projections return
    /// `None` together when the object overhangs the grid edge.
    fn project(&self, anchor: TileCoord, grid: GridSize, blocking_only: bool) -> Option<TileMask> {
        let mut mask = TileMask::new(grid.width, grid.height);
        for cell in &self.cells {
            let x = anchor.x as i64 + cell.dx as i64;
            let y = anchor.y as i64 + cell.dy as i64;
            if x < 0 || y < 0 || x >= grid.width as i64 || y >= grid.height as i64 {
                return None;
            }
            if !blocking_only || cell.blocking {
                mask.set(TileCoord::new(x as u32, y as u32));
            }
        }
        Some(mask)
    }

    /// Whether every occupied cell at `anchor` lands in-bounds **and** inside
    /// `area` (TMP_006 §3.4 — the footprint must fit the candidate search area).
    pub fn fits(&self, anchor: TileCoord, area: &TileMask) -> bool {
        self.cells.iter().all(|cell| {
            let x = anchor.x as i64 + cell.dx as i64;
            let y = anchor.y as i64 + cell.dy as i64;
            x >= 0
                && y >= 0
                && x < area.width() as i64
                && y < area.height() as i64
                && area.get(TileCoord::new(x as u32, y as u32))
        })
    }

    /// Occupied-cell count — the largest-first sort key for obstacle fill
    /// (TMP_005 §4.4).
    pub fn area(&self) -> usize {
        self.cells.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// `cell(dx, dy, blocking)` shorthand.
    fn cell(dx: i32, dy: i32, blocking: bool) -> FootprintCell {
        FootprintCell { dx, dy, blocking }
    }

    /// A 2×1 object: one blocking cell at the anchor, one non-blocking to its
    /// right — exercises the blocking/occupied projection split.
    fn mixed_template() -> TilemapObjectTemplate {
        TilemapObjectTemplate {
            name: "mixed".to_string(),
            cells: vec![cell(0, 0, true), cell(1, 0, false)],
        }
    }

    const GRID: GridSize = GridSize { width: 8, height: 8 };

    #[test]
    fn footprint_and_blocking_projections_differ_for_a_mixed_template() {
        // AC-5 — footprint_at projects all occupied cells; blocking_footprint_at
        // only the blocking ones.
        let t = mixed_template();
        let full = t.footprint_at(TileCoord::new(2, 2), GRID).unwrap();
        let blocking = t.blocking_footprint_at(TileCoord::new(2, 2), GRID).unwrap();
        assert_eq!(full.count_ones(), 2, "footprint_at projects both cells");
        assert_eq!(blocking.count_ones(), 1, "blocking_footprint_at projects only the blocking cell");
        assert!(full.get(TileCoord::new(2, 2)) && full.get(TileCoord::new(3, 2)));
        assert!(blocking.get(TileCoord::new(2, 2)) && !blocking.get(TileCoord::new(3, 2)));
        assert_ne!(full, blocking, "the two projections must differ");
    }

    #[test]
    fn projections_return_none_when_any_cell_is_out_of_bounds() {
        // AC-5 — both projections agree on None for an overhanging anchor.
        let t = mixed_template();
        // Anchor at the right edge: the non-blocking cell at dx=1 falls off-grid.
        let anchor = TileCoord::new(7, 0);
        assert!(t.footprint_at(anchor, GRID).is_none());
        assert!(t.blocking_footprint_at(anchor, GRID).is_none());
        // A negative offset also overhangs.
        let neg = TilemapObjectTemplate { name: "neg".into(), cells: vec![cell(-1, 0, true)] };
        assert!(neg.footprint_at(TileCoord::new(0, 3), GRID).is_none());
    }

    #[test]
    fn fits_is_true_only_when_every_occupied_cell_is_in_the_area() {
        // AC-5 — fits ⟺ every occupied cell lands in-bounds inside `area`.
        let t = mixed_template();
        let mut area = TileMask::new(8, 8);
        // Carve a 2-wide strip the 2×1 template can sit on.
        for x in 2..=3 {
            area.set(TileCoord::new(x, 4));
        }
        assert!(t.fits(TileCoord::new(2, 4), &area), "fits the carved strip");
        assert!(!t.fits(TileCoord::new(3, 4), &area), "cell dx=1 falls outside the strip");
        assert!(!t.fits(TileCoord::new(2, 5), &area), "row 5 is not in the area");
        assert!(!t.fits(TileCoord::new(7, 4), &area), "out of bounds is not a fit");
    }

    #[test]
    fn area_is_the_occupied_cell_count() {
        assert_eq!(mixed_template().area(), 2);
        let big = TilemapObjectTemplate {
            name: "3x3".to_string(),
            cells: (0..3).flat_map(|y| (0..3).map(move |x| cell(x, y, true))).collect(),
        };
        assert_eq!(big.area(), 9);
    }
}
