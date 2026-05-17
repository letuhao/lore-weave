//! Deterministic integer-cost pathfinding — shared by stages 5, 7, 8.
//!
//! All heaps are keyed `(cost, cell)` so cost ties resolve to the lower cell
//! id; costs are integers so the `BinaryHeap` key is `Ord` (no f32-in-heap
//! nondeterminism).

use std::cmp::Reverse;
use std::collections::BinaryHeap;
use std::collections::VecDeque;

/// Sentinel for "unreachable / unassigned".
pub const NONE: u32 = u32::MAX;

/// Connected components of land cells over `neighbors`. Ascending start-cell
/// sweep, DFS over the (sorted) neighbour lists → deterministic. Each inner
/// `Vec` is one component's cell ids.
pub fn land_components(is_land: &[bool], neighbors: &[Vec<u32>]) -> Vec<Vec<u32>> {
    let n = is_land.len();
    let mut seen = vec![false; n];
    let mut comps: Vec<Vec<u32>> = Vec::new();
    for start in 0..n {
        if seen[start] || !is_land[start] {
            continue;
        }
        let mut comp = Vec::new();
        let mut stack = vec![start];
        seen[start] = true;
        while let Some(c) = stack.pop() {
            comp.push(c as u32);
            for &nb in &neighbors[c] {
                let nb = nb as usize;
                if !seen[nb] && is_land[nb] {
                    seen[nb] = true;
                    stack.push(nb);
                }
            }
        }
        comps.push(comp);
    }
    comps
}

/// Multi-source Dijkstra. `cost_of(cell)` is the cost to ENTER `cell`
/// (`None` = impassable). Returns, per cell, the **index into `seeds`** of the
/// nearest seed (`NONE` if unreachable). Deterministic.
pub fn multi_source_assign(
    seeds: &[u32],
    cost_of: impl Fn(usize) -> Option<u32>,
    neighbors: &[Vec<u32>],
) -> Vec<u32> {
    let n = neighbors.len();
    let mut best = vec![u32::MAX; n];
    let mut owner = vec![NONE; n];
    let mut heap: BinaryHeap<Reverse<(u32, u32)>> = BinaryHeap::new();
    for (si, &s) in seeds.iter().enumerate() {
        let s = s as usize;
        if cost_of(s).is_some() && best[s] != 0 {
            best[s] = 0;
            owner[s] = si as u32;
            heap.push(Reverse((0, s as u32)));
        }
    }
    while let Some(Reverse((c, cell))) = heap.pop() {
        let cell = cell as usize;
        if c > best[cell] {
            continue;
        }
        for &nb in &neighbors[cell] {
            let nb = nb as usize;
            if let Some(step) = cost_of(nb) {
                let nc = c + step;
                if nc < best[nb] {
                    best[nb] = nc;
                    owner[nb] = owner[cell];
                    heap.push(Reverse((nc, nb as u32)));
                }
            }
        }
    }
    owner
}

/// Single-source Dijkstra from `src`. Returns `(dist, prev)` — `dist[c]` is the
/// path cost (`u32::MAX` if unreachable), `prev[c]` the predecessor cell
/// (`NONE` for `src` and unreachable cells). `src` is assumed passable.
pub fn single_source_dist(
    src: u32,
    cost_of: impl Fn(usize) -> Option<u32>,
    neighbors: &[Vec<u32>],
) -> (Vec<u32>, Vec<u32>) {
    let n = neighbors.len();
    let mut dist = vec![u32::MAX; n];
    let mut prev = vec![NONE; n];
    let src = src as usize;
    dist[src] = 0;
    let mut heap: BinaryHeap<Reverse<(u32, u32)>> = BinaryHeap::new();
    heap.push(Reverse((0, src as u32)));
    while let Some(Reverse((c, cell))) = heap.pop() {
        let cell = cell as usize;
        if c > dist[cell] {
            continue;
        }
        for &nb in &neighbors[cell] {
            let nb = nb as usize;
            if let Some(step) = cost_of(nb) {
                let nc = c + step;
                if nc < dist[nb] {
                    dist[nb] = nc;
                    prev[nb] = cell as u32;
                    heap.push(Reverse((nc, nb as u32)));
                }
            }
        }
    }
    (dist, prev)
}

/// Reconstruct the cell path from a Dijkstra root to `dst` using its `prev`
/// array (inclusive of both ends). A single-cell result means `dst` is the
/// root or unreachable — the caller checks `dist` for reachability.
pub fn reconstruct_path(dst: u32, prev: &[u32]) -> Vec<u32> {
    let mut path = vec![dst];
    let mut cur = dst;
    while prev[cur as usize] != NONE {
        cur = prev[cur as usize];
        path.push(cur);
    }
    path.reverse();
    path
}

/// BFS over the cells for which `passable(cell)` holds; returns the
/// fewest-hop cell path from `src` to `dst` inclusive (`[src, …, dst]`), or
/// `None` if `dst` is unreachable. `src` is the BFS root; `dst` must itself
/// satisfy `passable` to be reached. Used for SeaLane water connectivity.
pub fn bfs_path(
    src: u32,
    dst: u32,
    passable: impl Fn(usize) -> bool,
    neighbors: &[Vec<u32>],
) -> Option<Vec<u32>> {
    if src == dst {
        return Some(vec![src]);
    }
    let mut prev = vec![NONE; neighbors.len()];
    let mut seen = vec![false; neighbors.len()];
    let mut queue = VecDeque::new();
    seen[src as usize] = true;
    queue.push_back(src as usize);
    while let Some(c) = queue.pop_front() {
        for &nb in &neighbors[c] {
            let nbu = nb as usize;
            if seen[nbu] || !passable(nbu) {
                continue;
            }
            seen[nbu] = true;
            prev[nbu] = c as u32;
            if nbu == dst as usize {
                // Reconstruct src → dst via the BFS predecessor chain.
                let mut path = vec![dst];
                let mut cur = dst;
                while cur != src {
                    cur = prev[cur as usize];
                    path.push(cur);
                }
                path.reverse();
                return Some(path);
            }
            queue.push_back(nbu);
        }
    }
    None
}

/// Whether `cell`'s centre is ≥ `min_sep` (its *square* is given) from every
/// already-placed cell — the Poisson-disk spacing test for seed/hearth
/// placement (stages 5, 8).
pub fn spaced_ok(cell: u32, placed: &[u32], centers: &[(f32, f32)], min_sep2: f32) -> bool {
    let (cx, cy) = centers[cell as usize];
    placed.iter().all(|&p| {
        let (px, py) = centers[p as usize];
        let dx = cx - px;
        let dy = cy - py;
        dx * dx + dy * dy >= min_sep2
    })
}

/// Largest-remainder apportionment of `total` units across buckets of the
/// given `sizes` — one base unit each, the remainder by size fraction, then
/// **capped so no bucket exceeds its size** (overflow redistributed to buckets
/// with spare capacity). Sums to exactly `total`. Caller guarantees
/// `sizes.len() <= total <= sum(sizes)` and every `size >= 1`.
pub fn apportion(total: usize, sizes: &[usize]) -> Vec<usize> {
    let nc = sizes.len();
    if nc == 0 {
        return Vec::new();
    }
    let whole: usize = sizes.iter().sum();
    // Caller contract — a breach would make the redistribute loop under-fill
    // silently; fail loudly at the real call site in debug builds instead.
    debug_assert!(
        sizes.iter().all(|&s| s >= 1),
        "apportion: every bucket size must be >= 1"
    );
    debug_assert!(
        total >= nc && total <= whole,
        "apportion: total {total} outside [{nc}, {whole}]"
    );
    let mut q = vec![1usize; nc];
    let rem = total - nc;
    if rem > 0 && whole > 0 {
        let mut floors = vec![0usize; nc];
        let mut fracs: Vec<(f64, usize)> = Vec::with_capacity(nc);
        for (i, &sz) in sizes.iter().enumerate() {
            let exact = rem as f64 * (sz as f64 / whole as f64);
            floors[i] = exact.floor() as usize;
            fracs.push((exact - exact.floor(), i));
        }
        let mut leftover = rem - floors.iter().sum::<usize>();
        for (qi, &f) in q.iter_mut().zip(&floors) {
            *qi += f;
        }
        // largest fractional remainder; ties → lower bucket index.
        fracs.sort_by(|a, b| b.0.total_cmp(&a.0).then(a.1.cmp(&b.1)));
        for &(_, i) in &fracs {
            if leftover == 0 {
                break;
            }
            q[i] += 1;
            leftover -= 1;
        }
    }
    // Cap each bucket at its size; redistribute overflow to buckets that still
    // have spare capacity (since total <= sum(sizes), this always fits).
    let mut overflow = 0usize;
    for (qi, &sz) in q.iter_mut().zip(sizes) {
        if *qi > sz {
            overflow += *qi - sz;
            *qi = sz;
        }
    }
    while overflow > 0 {
        // bucket with the most spare capacity; ties → lower index.
        let mut best_spare = 0usize;
        let mut pick = usize::MAX;
        for (i, (&qi, &sz)) in q.iter().zip(sizes).enumerate() {
            if sz - qi > best_spare {
                best_spare = sz - qi;
                pick = i;
            }
        }
        if pick == usize::MAX {
            break; // no spare anywhere — total exceeded sum(sizes)
        }
        q[pick] += 1;
        overflow -= 1;
    }
    q
}

/// Union-find with min-root attach — the root is always a set's lowest index,
/// so `find` is order-independent and deterministic.
pub struct UnionFind {
    parent: Vec<usize>,
}

impl UnionFind {
    pub fn new(n: usize) -> Self {
        UnionFind {
            parent: (0..n).collect(),
        }
    }

    pub fn find(&mut self, x: usize) -> usize {
        let mut r = x;
        while self.parent[r] != r {
            r = self.parent[r];
        }
        let mut c = x;
        while self.parent[c] != c {
            let next = self.parent[c];
            self.parent[c] = r;
            c = next;
        }
        r
    }

    pub fn union(&mut self, a: usize, b: usize) {
        let ra = self.find(a);
        let rb = self.find(b);
        if ra != rb {
            let (lo, hi) = if ra < rb { (ra, rb) } else { (rb, ra) };
            self.parent[hi] = lo;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn apportion_sums_to_total_with_min_one() {
        let sizes = [900usize, 80, 44];
        for total in [3usize, 4, 13, 50, 80] {
            let t = total.max(sizes.len());
            let q = apportion(t, &sizes);
            assert_eq!(q.iter().sum::<usize>(), t);
            assert!(q.iter().all(|&x| x >= 1));
        }
    }

    #[test]
    fn union_find_root_is_set_minimum() {
        let mut uf = UnionFind::new(6);
        uf.union(5, 2);
        uf.union(4, 5);
        assert_eq!(uf.find(5), 2);
        assert_eq!(uf.find(4), 2);
        assert_eq!(uf.find(2), 2);
        assert_ne!(uf.find(0), uf.find(2));
    }
}

