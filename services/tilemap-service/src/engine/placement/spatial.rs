//! TMP_002 perf — `UniformBuckets<P>`, a uniform 2D bin grid over points.
//!
//! Both `fractalize::scatter_and_connect` and `penrose::assign_zone_tiles` need
//! to ask "given a query point, which already-inserted points lie within a
//! radius?" — a quadratic-time linear scan in the original implementation. This
//! helper provides the shared storage + iteration; the per-algorithm query
//! semantics (fractalize: any-within-radius, penrose: nearest-with-index-tie-
//! break) stay in the consumer modules.
//!
//! Determinism (TMP-A4): bin storage is `Vec<(usize, P)>` in insertion order;
//! `for_each_in_bucket` and `for_each_in_ring` iterate in fixed row-major then
//! insertion order. Bucket boundaries are deterministic (`floor` + clamp), so
//! the same point always lands in the same bucket across runs.
//!
//! Spec: [`docs/specs/2026-05-20-tilemap-perf-fractalize-penrose.md`] §9.1.

use crate::types::tile::TileCoord;

use super::Vec2;

/// A point that knows how to map itself to bucket coordinates.
///
/// The trait method returns the **unclamped** bucket coords; [`UniformBuckets`]
/// applies the in-range clamp around it so out-of-range points safely land in
/// the boundary bucket (used by the spiral query when the query point sits at
/// the grid edge).
pub(super) trait BucketPoint: Copy {
    /// Return `(bucket_x, bucket_y)` for this point. `floor`ed — a point at
    /// the bucket boundary lands in the higher bucket.
    fn to_bucket_xy(self, origin: (f64, f64), inv_bucket_size: f64) -> (i32, i32);
}

impl BucketPoint for Vec2 {
    fn to_bucket_xy(self, origin: (f64, f64), inv_bucket_size: f64) -> (i32, i32) {
        let bx = ((self.x - origin.0) * inv_bucket_size).floor() as i32;
        let by = ((self.y - origin.1) * inv_bucket_size).floor() as i32;
        (bx, by)
    }
}

impl BucketPoint for TileCoord {
    fn to_bucket_xy(self, origin: (f64, f64), inv_bucket_size: f64) -> (i32, i32) {
        let bx = ((self.x as f64 - origin.0) * inv_bucket_size).floor() as i32;
        let by = ((self.y as f64 - origin.1) * inv_bucket_size).floor() as i32;
        (bx, by)
    }
}

/// 2D uniform bin grid over `[origin .. origin + cols*bucket_size]²`.
///
/// Bins hold `(caller_index, point)` pairs in insertion order. The
/// `caller_index` lets the consumer track which input point the entry came
/// from — penrose uses it for the lowest-index tie-break; fractalize passes
/// `0` since its query is boolean.
pub(super) struct UniformBuckets<P: BucketPoint> {
    origin: (f64, f64),
    bucket_size: f64,
    inv_bucket_size: f64,
    cols: i32,
    rows: i32,
    bins: Vec<Vec<(usize, P)>>,
}

impl<P: BucketPoint> UniformBuckets<P> {
    /// Empty grid sized to cover `[origin .. origin + cols*bucket_size]²`.
    ///
    /// `bucket_size` must be > 0; `cols` and `rows` must be ≥ 1 (callers that
    /// would compute 0 must guard with `.max(1)` themselves so the empty-grid
    /// case is intentional, not arithmetic drift).
    pub fn new(origin: (f64, f64), bucket_size: f64, cols: i32, rows: i32) -> Self {
        debug_assert!(bucket_size > 0.0, "bucket_size must be positive");
        debug_assert!(cols >= 1 && rows >= 1, "grid must be ≥ 1×1");
        let bin_count = (cols as usize) * (rows as usize);
        Self {
            origin,
            bucket_size,
            inv_bucket_size: 1.0 / bucket_size,
            cols,
            rows,
            bins: vec![Vec::new(); bin_count],
        }
    }

    /// Insert `(caller_index, point)` into `point`'s bucket. O(1).
    ///
    /// Out-of-range points are **clamped** to the boundary bucket — defensive
    /// against `f64` rounding at the right/bottom edge (a vertex normalized to
    /// exactly `1.0` would otherwise land in bucket `cols`, out of range).
    pub fn insert(&mut self, caller_index: usize, point: P) {
        let (bx, by) = self.clamped_bucket_xy(point);
        let bin_idx = (by * self.cols + bx) as usize;
        self.bins[bin_idx].push((caller_index, point));
    }

    /// `point`'s bucket coords, clamped into `[0, cols-1] × [0, rows-1]`.
    pub fn bucket_xy(&self, point: P) -> (i32, i32) {
        self.clamped_bucket_xy(point)
    }

    fn clamped_bucket_xy(&self, point: P) -> (i32, i32) {
        let (bx, by) = point.to_bucket_xy(self.origin, self.inv_bucket_size);
        (bx.clamp(0, self.cols - 1), by.clamp(0, self.rows - 1))
    }

    pub fn bucket_size(&self) -> f64 {
        self.bucket_size
    }

    /// `max(cols, rows)` — the worst-case spiral ring count.
    pub fn max_dim(&self) -> i32 {
        self.cols.max(self.rows)
    }

    /// Iterate the bin at `(bx, by)` (in insertion order); no-op if out of
    /// range. The callback receives `(caller_index, point)` for each entry.
    pub fn for_each_in_bucket<F: FnMut(usize, P)>(&self, bx: i32, by: i32, mut f: F) {
        if bx < 0 || by < 0 || bx >= self.cols || by >= self.rows {
            return;
        }
        let bin_idx = (by * self.cols + bx) as usize;
        for &(i, p) in &self.bins[bin_idx] {
            f(i, p);
        }
    }

    /// Iterate every bin at Chebyshev distance `ring` from `(cx, cy)`.
    /// Ring 0 = the single centre bucket; ring `r > 0` = the perimeter shell.
    /// Out-of-range bins are clipped; negative rings are a no-op.
    ///
    /// Iteration order within a ring is bucket-row-major (top row then bottom
    /// row, then left column then right column, corners-first), then
    /// insertion order within each bin. **Consumers must not depend on the
    /// cross-bucket order** — the current consumers (fractalize: bool short-
    /// circuit; penrose: tie-break by caller_index, not by visit order) are
    /// order-independent.
    pub fn for_each_in_ring<F: FnMut(usize, P)>(&self, cx: i32, cy: i32, ring: i32, mut f: F) {
        if ring < 0 {
            return;
        }
        if ring == 0 {
            self.for_each_in_bucket(cx, cy, f);
            return;
        }
        // Top + bottom rows of the shell (full width).
        for x in (cx - ring)..=(cx + ring) {
            self.for_each_in_bucket(x, cy - ring, &mut f);
            self.for_each_in_bucket(x, cy + ring, &mut f);
        }
        // Left + right columns (excluding the corners already visited above).
        for y in (cy - ring + 1)..=(cy + ring - 1) {
            self.for_each_in_bucket(cx - ring, y, &mut f);
            self.for_each_in_bucket(cx + ring, y, &mut f);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn vb_vec2(cols: i32, rows: i32) -> UniformBuckets<Vec2> {
        UniformBuckets::new((0.0, 0.0), 0.1, cols, rows)
    }

    fn vb_tile() -> UniformBuckets<TileCoord> {
        // 256-wide grid, bucket_size 7 ⇒ 37 cols
        UniformBuckets::new((0.0, 0.0), 7.0, 37, 37)
    }

    fn count_in_ring(vb: &UniformBuckets<Vec2>, cx: i32, cy: i32, ring: i32) -> usize {
        let mut n = 0;
        vb.for_each_in_ring(cx, cy, ring, |_, _| n += 1);
        n
    }

    #[test]
    fn new_empty_grid_has_no_pairs() {
        let vb = vb_vec2(5, 5);
        let mut visited = 0;
        for ring in 0..10 {
            vb.for_each_in_ring(2, 2, ring, |_, _| visited += 1);
        }
        assert_eq!(visited, 0);
    }

    #[test]
    fn insert_then_for_each_in_bucket_round_trips() {
        let mut vb = vb_vec2(10, 10);
        let p = Vec2::new(0.35, 0.42);
        vb.insert(7, p);
        let (bx, by) = vb.bucket_xy(p);
        let mut got: Vec<(usize, Vec2)> = Vec::new();
        vb.for_each_in_bucket(bx, by, |i, q| got.push((i, q)));
        assert_eq!(got, vec![(7, p)]);
    }

    #[test]
    fn for_each_in_ring_zero_visits_centre_only() {
        let mut vb = vb_vec2(5, 5);
        vb.insert(0, Vec2::new(0.25, 0.25)); // bucket (2,2)
        vb.insert(1, Vec2::new(0.35, 0.25)); // bucket (3,2)
        vb.insert(2, Vec2::new(0.15, 0.25)); // bucket (1,2)
        let mut seen: Vec<usize> = Vec::new();
        vb.for_each_in_ring(2, 2, 0, |i, _| seen.push(i));
        assert_eq!(seen, vec![0]);
    }

    #[test]
    fn for_each_in_ring_one_visits_eight_neighbours() {
        let mut vb = vb_vec2(5, 5);
        // Place one vertex in each of the 9 buckets (2,2)±1,±1.
        for (dx, dy) in [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 0), (0, 1), (1, -1), (1, 0), (1, 1)] {
            let cx = 2 + dx;
            let cy = 2 + dy;
            // Vec2 at bucket centre (cx + 0.5) * 0.1
            let p = Vec2::new((cx as f64 + 0.5) * 0.1, (cy as f64 + 0.5) * 0.1);
            vb.insert(((cx + 1) + 3 * (cy + 1)) as usize, p);
        }
        assert_eq!(count_in_ring(&vb, 2, 2, 0), 1);
        assert_eq!(count_in_ring(&vb, 2, 2, 1), 8);
    }

    #[test]
    fn for_each_in_ring_clips_to_grid_edges() {
        let mut vb = vb_vec2(5, 5);
        // Corner bucket (0,0). Ring 1 should see only the 3 in-range cells:
        // (1,0), (0,1), (1,1) — not the 5 negative-x or negative-y cells.
        for (cx, cy) in [(0, 0), (1, 0), (0, 1), (1, 1)] {
            let p = Vec2::new((cx as f64 + 0.5) * 0.1, (cy as f64 + 0.5) * 0.1);
            vb.insert((cx + 5 * cy) as usize, p);
        }
        assert_eq!(count_in_ring(&vb, 0, 0, 0), 1);
        assert_eq!(count_in_ring(&vb, 0, 0, 1), 3);
    }

    #[test]
    fn for_each_in_ring_skips_negative_ring_safely() {
        let mut vb = vb_vec2(5, 5);
        vb.insert(0, Vec2::new(0.25, 0.25));
        assert_eq!(count_in_ring(&vb, 2, 2, -1), 0);
    }

    #[test]
    fn bucket_xy_of_vec2_at_origin() {
        let vb = vb_vec2(10, 10);
        assert_eq!(vb.bucket_xy(Vec2::new(0.0, 0.0)), (0, 0));
        assert_eq!(vb.bucket_xy(Vec2::new(0.09, 0.09)), (0, 0));
        assert_eq!(vb.bucket_xy(Vec2::new(0.1, 0.1)), (1, 1));
        assert_eq!(vb.bucket_xy(Vec2::new(0.95, 0.95)), (9, 9));
    }

    #[test]
    fn bucket_xy_of_tilecoord_at_origin() {
        let vb = vb_tile(); // bucket_size=7, 37×37 grid
        assert_eq!(vb.bucket_xy(TileCoord::new(0, 0)), (0, 0));
        assert_eq!(vb.bucket_xy(TileCoord::new(6, 6)), (0, 0));
        assert_eq!(vb.bucket_xy(TileCoord::new(7, 7)), (1, 1));
        assert_eq!(vb.bucket_xy(TileCoord::new(255, 255)), (36, 36));
    }

    #[test]
    fn out_of_range_bucket_xy_is_clamped() {
        let vb = vb_vec2(5, 5);
        // Below origin clamps to 0.
        assert_eq!(vb.bucket_xy(Vec2::new(-0.5, -0.5)), (0, 0));
        // Past the far edge clamps to (cols-1, rows-1).
        assert_eq!(vb.bucket_xy(Vec2::new(1.0, 1.0)), (4, 4));
        assert_eq!(vb.bucket_xy(Vec2::new(5.0, 5.0)), (4, 4));
    }

    #[test]
    fn insert_at_far_right_edge_lands_in_boundary_bucket() {
        // A Vec2 normalized to exactly 1.0 would compute bucket = cols (out of
        // range) without the insert-time clamp. With the clamp it lands in
        // the rightmost bucket.
        let mut vb = vb_vec2(5, 5);
        vb.insert(99, Vec2::new(1.0, 1.0));
        let mut seen: Vec<usize> = Vec::new();
        vb.for_each_in_bucket(4, 4, |i, _| seen.push(i));
        assert_eq!(seen, vec![99]);
    }

    #[test]
    fn for_each_in_bucket_iterates_in_insertion_order() {
        let mut vb = vb_vec2(5, 5);
        for i in 0..4 {
            vb.insert(i, Vec2::new(0.21 + i as f64 * 0.001, 0.21));
        }
        let mut seen: Vec<usize> = Vec::new();
        vb.for_each_in_bucket(2, 2, |i, _| seen.push(i));
        assert_eq!(seen, vec![0, 1, 2, 3]);
    }
}
