//! `TileMask` — a grid-sized bitset over tile coordinates.
//!
//! Phase 1 replaces the Phase-0a `Vec<TileCoord>` placeholders on
//! [`crate::types::ZoneRuntime`] with this type: a zone's `assigned_tiles` and
//! `free_paths` are large, set-membership-heavy, and must iterate
//! **deterministically**. A `HashSet<TileCoord>` would iterate in a
//! seed-independent but hash-random order — fatal for the TMP-A4 determinism
//! axiom. `TileMask::iter_set` walks bits in flat-index ascending order, so any
//! consumer (terrain paint, serialization) sees a reproducible sequence.

use serde::{Deserialize, Serialize};

use crate::types::tile::TileCoord;

const BITS_PER_WORD: usize = 64;

/// A bitset with one bit per `(x, y)` tile of a `width × height` grid. Bit
/// `flat_index = y * width + x`. Out-of-bounds coordinates are silently ignored
/// by `set`/`clear` and read `false` from `get`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TileMask {
    width: u32,
    height: u32,
    /// `tile_count` bits packed little-endian within each `u64`; word
    /// `i / 64`, bit `i % 64`. Length = `ceil(tile_count / 64)`.
    bits: Vec<u64>,
}

impl TileMask {
    /// An all-zero mask sized to a `width × height` grid.
    pub fn new(width: u32, height: u32) -> Self {
        let tile_count = (width as usize) * (height as usize);
        Self {
            width,
            height,
            bits: vec![0; tile_count.div_ceil(BITS_PER_WORD)],
        }
    }

    pub fn width(&self) -> u32 {
        self.width
    }

    pub fn height(&self) -> u32 {
        self.height
    }

    /// Total addressable tiles (`width * height`).
    pub fn tile_count(&self) -> usize {
        (self.width as usize) * (self.height as usize)
    }

    /// Flat bit index for an in-bounds coord; `None` if out of bounds.
    fn index(&self, coord: TileCoord) -> Option<usize> {
        if coord.x >= self.width || coord.y >= self.height {
            return None;
        }
        Some(coord.flat_index(self.width))
    }

    /// Set the bit for `coord`. Out-of-bounds coords are ignored.
    pub fn set(&mut self, coord: TileCoord) {
        if let Some(i) = self.index(coord) {
            self.bits[i / BITS_PER_WORD] |= 1u64 << (i % BITS_PER_WORD);
        }
    }

    /// Clear the bit for `coord`. Out-of-bounds coords are ignored.
    pub fn clear(&mut self, coord: TileCoord) {
        if let Some(i) = self.index(coord) {
            self.bits[i / BITS_PER_WORD] &= !(1u64 << (i % BITS_PER_WORD));
        }
    }

    /// Whether `coord`'s bit is set. Out-of-bounds reads `false`.
    pub fn get(&self, coord: TileCoord) -> bool {
        match self.index(coord) {
            Some(i) => (self.bits[i / BITS_PER_WORD] >> (i % BITS_PER_WORD)) & 1 == 1,
            None => false,
        }
    }

    /// Number of set bits.
    pub fn count_ones(&self) -> usize {
        self.bits.iter().map(|w| w.count_ones() as usize).sum()
    }

    /// Whether no bit is set.
    pub fn is_empty(&self) -> bool {
        self.bits.iter().all(|w| *w == 0)
    }

    /// Iterate set coordinates in **flat-index ascending order** — the
    /// deterministic iteration the TMP-A4 axiom depends on.
    pub fn iter_set(&self) -> impl Iterator<Item = TileCoord> + '_ {
        let width = self.width;
        self.bits.iter().enumerate().flat_map(move |(wi, &word)| {
            (0..BITS_PER_WORD).filter_map(move |bi| {
                if (word >> bi) & 1 == 1 {
                    let flat = (wi * BITS_PER_WORD + bi) as u32;
                    Some(TileCoord::new(flat % width, flat / width))
                } else {
                    None
                }
            })
        })
    }

    /// Assert two masks share dimensions — a mismatch is a programming error.
    fn assert_same_dims(&self, other: &TileMask) {
        assert_eq!(
            (self.width, self.height),
            (other.width, other.height),
            "TileMask dimension mismatch",
        );
    }

    /// In-place set union (`self |= other`).
    pub fn union_with(&mut self, other: &TileMask) {
        self.assert_same_dims(other);
        for (a, b) in self.bits.iter_mut().zip(&other.bits) {
            *a |= *b;
        }
    }

    /// In-place set intersection (`self &= other`).
    pub fn intersect_with(&mut self, other: &TileMask) {
        self.assert_same_dims(other);
        for (a, b) in self.bits.iter_mut().zip(&other.bits) {
            *a &= *b;
        }
    }

    /// In-place set difference (`self &= !other`).
    pub fn subtract(&mut self, other: &TileMask) {
        self.assert_same_dims(other);
        for (a, b) in self.bits.iter_mut().zip(&other.bits) {
            *a &= !*b;
        }
    }

    /// Whether `self` and `other` share at least one set bit.
    pub fn intersects(&self, other: &TileMask) -> bool {
        self.assert_same_dims(other);
        self.bits.iter().zip(&other.bits).any(|(a, b)| a & b != 0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn c(x: u32, y: u32) -> TileCoord {
        TileCoord::new(x, y)
    }

    #[test]
    fn set_get_clear_round_trip() {
        let mut m = TileMask::new(10, 8);
        assert!(!m.get(c(3, 4)));
        m.set(c(3, 4));
        assert!(m.get(c(3, 4)));
        assert_eq!(m.count_ones(), 1);
        m.clear(c(3, 4));
        assert!(!m.get(c(3, 4)));
        assert!(m.is_empty());
    }

    #[test]
    fn out_of_bounds_is_ignored() {
        let mut m = TileMask::new(4, 4);
        m.set(c(4, 0)); // x == width
        m.set(c(0, 99)); // y >> height
        assert!(m.is_empty());
        assert!(!m.get(c(4, 0)));
    }

    #[test]
    fn iter_set_is_flat_index_ascending() {
        let mut m = TileMask::new(5, 5);
        // set in scrambled order
        for &(x, y) in &[(4, 4), (0, 0), (2, 3), (1, 0)] {
            m.set(c(x, y));
        }
        let got: Vec<_> = m.iter_set().collect();
        // expected sorted by y*5+x: (0,0)=0, (1,0)=1, (2,3)=17, (4,4)=24
        assert_eq!(got, vec![c(0, 0), c(1, 0), c(2, 3), c(4, 4)]);
    }

    #[test]
    fn iter_set_never_yields_out_of_grid_coords() {
        // 10x10 = 100 tiles spans 2 words (128 bits); the 28 trailing bits
        // are unaddressable — iter_set must not surface them.
        let mut m = TileMask::new(10, 10);
        m.set(c(9, 9)); // flat 99 — the last valid tile
        let got: Vec<_> = m.iter_set().collect();
        assert_eq!(got, vec![c(9, 9)]);
    }

    #[test]
    fn union_intersect_subtract() {
        let mut a = TileMask::new(8, 8);
        let mut b = TileMask::new(8, 8);
        a.set(c(1, 1));
        a.set(c(2, 2));
        b.set(c(2, 2));
        b.set(c(3, 3));

        let mut u = a.clone();
        u.union_with(&b);
        assert_eq!(u.count_ones(), 3);

        let mut i = a.clone();
        i.intersect_with(&b);
        assert_eq!(i.iter_set().collect::<Vec<_>>(), vec![c(2, 2)]);

        let mut d = a.clone();
        d.subtract(&b);
        assert_eq!(d.iter_set().collect::<Vec<_>>(), vec![c(1, 1)]);

        assert!(a.intersects(&b));
        let mut disjoint = TileMask::new(8, 8);
        disjoint.set(c(7, 7));
        assert!(!a.intersects(&disjoint));
    }

    #[test]
    #[should_panic(expected = "dimension mismatch")]
    fn union_panics_on_dimension_mismatch() {
        let mut a = TileMask::new(8, 8);
        let b = TileMask::new(4, 4);
        a.union_with(&b);
    }

    #[test]
    fn serde_round_trip() {
        let mut m = TileMask::new(16, 16);
        m.set(c(0, 0));
        m.set(c(15, 15));
        m.set(c(7, 9));
        let json = serde_json::to_string(&m).unwrap();
        let back: TileMask = serde_json::from_str(&json).unwrap();
        assert_eq!(m, back);
    }

    #[test]
    fn zero_sized_grid_is_inert() {
        let mut m = TileMask::new(0, 0);
        assert_eq!(m.tile_count(), 0);
        assert!(m.is_empty());
        m.set(c(0, 0));
        assert!(m.is_empty());
    }
}
