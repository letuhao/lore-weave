//! Minimum spanning tree over tile coordinates (Prim 1957) — the TMP_003 §3.4
//! `RoadPlacer` backbone. Pure + deterministic: edge weight is Manhattan
//! distance, ties broken by the lower out-of-tree node index.

use crate::types::tile::TileCoord;

/// Manhattan distance between two tiles.
fn manhattan(a: TileCoord, b: TileCoord) -> u32 {
    a.x.abs_diff(b.x) + a.y.abs_diff(b.y)
}

/// The minimum spanning tree of the complete graph over `coords`, edges
/// weighted by Manhattan distance. Returns `n-1` edges as `(usize, usize)`
/// index pairs into `coords` — each `(in_tree_node, newly_added_node)`. Fewer
/// than 2 coords ⇒ no edges.
///
/// Deterministic (TMP-A4): Prim's algorithm grown from index 0; on a weight tie
/// the lower out-of-tree node index wins, and an equal-weight relaxation never
/// overwrites the recorded parent.
pub fn minimum_spanning_tree(coords: &[TileCoord]) -> Vec<(usize, usize)> {
    let n = coords.len();
    if n < 2 {
        return Vec::new();
    }
    let mut in_tree = vec![false; n];
    in_tree[0] = true;
    // best[j] for an out-of-tree j = (weight, the in-tree node it connects to).
    let mut best: Vec<Option<(u32, usize)>> = vec![None; n];
    for (j, slot) in best.iter_mut().enumerate().skip(1) {
        *slot = Some((manhattan(coords[0], coords[j]), 0));
    }

    let mut edges = Vec::with_capacity(n - 1);
    for _ in 1..n {
        // Pick the out-of-tree node with the smallest (weight, node index).
        let mut pick: Option<(u32, usize, usize)> = None; // (weight, node, parent)
        for j in 0..n {
            if in_tree[j] {
                continue;
            }
            if let Some((w, from)) = best[j] {
                if pick.is_none_or(|(pw, pj, _)| (w, j) < (pw, pj)) {
                    pick = Some((w, j, from));
                }
            }
        }
        let (_, node, from) = pick.expect("the complete graph always has a next node");
        in_tree[node] = true;
        edges.push((from, node));
        // Relax every still-out-of-tree node against the freshly added node.
        // Strict `<` — an equal-weight alternative does NOT overwrite the
        // parent, pinning the tree (TMP-A4).
        for j in 0..n {
            if in_tree[j] {
                continue;
            }
            let w = manhattan(coords[node], coords[j]);
            if best[j].is_none_or(|(bw, _)| w < bw) {
                best[j] = Some((w, node));
            }
        }
    }
    edges
}

#[cfg(test)]
mod tests {
    use super::*;

    fn c(x: u32, y: u32) -> TileCoord {
        TileCoord::new(x, y)
    }

    /// Total Manhattan weight of an edge list over `coords`.
    fn tree_weight(coords: &[TileCoord], edges: &[(usize, usize)]) -> u32 {
        edges.iter().map(|&(a, b)| manhattan(coords[a], coords[b])).sum()
    }

    /// Are all `n` nodes connected by `edges`? (union-find reachability).
    fn spans_all(n: usize, edges: &[(usize, usize)]) -> bool {
        let mut parent: Vec<usize> = (0..n).collect();
        fn find(parent: &mut [usize], x: usize) -> usize {
            let mut r = x;
            while parent[r] != r {
                r = parent[r];
            }
            let mut cur = x;
            while parent[cur] != r {
                let next = parent[cur];
                parent[cur] = r;
                cur = next;
            }
            r
        }
        for &(a, b) in edges {
            let (ra, rb) = (find(&mut parent, a), find(&mut parent, b));
            parent[ra] = rb;
        }
        (0..n).all(|i| find(&mut parent, i) == find(&mut parent, 0))
    }

    #[test]
    fn fewer_than_two_nodes_has_no_edges() {
        assert!(minimum_spanning_tree(&[]).is_empty());
        assert!(minimum_spanning_tree(&[c(3, 3)]).is_empty());
    }

    #[test]
    fn two_nodes_yield_one_edge() {
        let coords = [c(0, 0), c(2, 5)];
        let edges = minimum_spanning_tree(&coords);
        assert_eq!(edges, vec![(0, 1)]);
    }

    #[test]
    fn unit_square_picks_the_four_cheap_sides_not_the_diagonals() {
        // A 1×1 square: sides weight 1, diagonals weight 2. An MST of 4 nodes
        // has 3 edges; every edge must be a weight-1 side.
        let coords = [c(0, 0), c(1, 0), c(0, 1), c(1, 1)];
        let edges = minimum_spanning_tree(&coords);
        assert_eq!(edges.len(), 3, "an MST of 4 nodes has 3 edges");
        assert!(spans_all(4, &edges), "the MST must connect every node");
        assert_eq!(tree_weight(&coords, &edges), 3, "three weight-1 sides");
    }

    #[test]
    fn mst_is_n_minus_1_edges_spans_all_and_beats_the_naive_chain() {
        // Property check over several fixed coord sets — the MST has n-1 edges,
        // connects every node, and its weight never exceeds the naive
        // sequential-chain spanning tree (a valid spanning tree, so MST ≤ it).
        let sets: Vec<Vec<TileCoord>> = vec![
            vec![c(0, 0), c(9, 1), c(2, 8), c(7, 7), c(4, 3)],
            vec![c(5, 5), c(5, 6), c(5, 7), c(5, 8), c(5, 9), c(5, 10)],
            vec![c(0, 0), c(20, 0), c(0, 20), c(20, 20), c(10, 10), c(3, 17), c(15, 4)],
            vec![c(12, 0), c(0, 12), c(12, 12)],
        ];
        for coords in &sets {
            let n = coords.len();
            let edges = minimum_spanning_tree(coords);
            assert_eq!(edges.len(), n - 1, "n-1 edges for n={n}");
            assert!(spans_all(n, &edges), "the MST must span every node (n={n})");
            let chain: Vec<(usize, usize)> = (0..n - 1).map(|i| (i, i + 1)).collect();
            assert!(
                tree_weight(coords, &edges) <= tree_weight(coords, &chain),
                "MST weight must not exceed the naive chain (n={n})",
            );
        }
    }

    #[test]
    fn mst_is_deterministic() {
        let coords = [c(0, 0), c(9, 1), c(2, 8), c(7, 7), c(4, 3), c(8, 8)];
        assert_eq!(minimum_spanning_tree(&coords), minimum_spanning_tree(&coords));
    }
}
