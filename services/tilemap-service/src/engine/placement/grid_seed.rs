//! TMP_002 §3.1 — initial grid seed.
//!
//! Produces a sane starting layout for force-directed convergence: zones are
//! placed on an `N × N` grid (`N = ceil(sqrt(zone_count))`) so connected zones
//! start near each other and `Adversarial`-connected zones start apart.
//!
//! **Fully deterministic** — no RNG. Zones are placed in `zone_id`-ascending
//! order; ties between equally-good grid cells break to the lowest linear cell
//! index. Same template ⇒ same seed layout (TMP-A4).

use std::collections::{HashMap, HashSet};

use crate::types::template::TilemapTemplate;
use crate::types::zone::{PassageKind, ZoneId};

use super::{PlacedZone, Vec2};

/// A cell on the seed grid.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct Cell {
    gx: u32,
    gy: u32,
}

impl Cell {
    /// Manhattan distance to another cell.
    fn manhattan(self, other: Cell) -> i64 {
        (self.gx as i64 - other.gx as i64).abs() + (self.gy as i64 - other.gy as i64).abs()
    }
}

/// Build the §3.1 initial grid layout for `template`.
///
/// Connection semantics (TMP_002 §3.1): `Threshold` / `Open` / `Hint` edges
/// pull zones together (proximity); `Adversarial` edges push apart; `Portal`
/// edges are ignored (a teleport imposes no spatial constraint).
pub fn initial_grid_layout(template: &TilemapTemplate) -> Vec<PlacedZone> {
    let zone_count = template.zones.len();
    if zone_count == 0 {
        return Vec::new();
    }

    // Deterministic placement order: zone_id ascending.
    let mut specs: Vec<&_> = template.zones.iter().collect();
    specs.sort_by(|a, b| a.zone_id.0.cmp(&b.zone_id.0));

    let in_template: HashSet<&str> =
        template.zones.iter().map(|z| z.zone_id.0.as_str()).collect();

    // Undirected proximity + adversarial adjacency. A connection is listed on
    // one zone's spec; mirror it so both endpoints see the edge. Edges whose
    // `to_zone` is not in the template are dropped (defensive — bad template).
    let mut proximity: HashMap<&str, HashSet<&str>> = HashMap::new();
    let mut adversarial: HashMap<&str, HashSet<&str>> = HashMap::new();
    for spec in &template.zones {
        let a = spec.zone_id.0.as_str();
        for conn in &spec.connections {
            let b = conn.to_zone.0.as_str();
            if a == b || !in_template.contains(b) {
                continue;
            }
            let (map, _) = match conn.kind {
                PassageKind::Threshold | PassageKind::Open | PassageKind::Hint => {
                    (&mut proximity, ())
                }
                PassageKind::Adversarial => (&mut adversarial, ()),
                PassageKind::Portal => continue,
            };
            map.entry(a).or_default().insert(b);
            map.entry(b).or_default().insert(a);
        }
    }

    // N x N grid sized to hold every zone.
    let n = (zone_count as f64).sqrt().ceil() as u32;
    let n = n.max(1);

    // Greedy assignment. `placed` maps an already-seated zone_id to its cell.
    let mut placed: HashMap<&str, Cell> = HashMap::new();
    let mut taken: HashSet<(u32, u32)> = HashSet::new();

    for spec in &specs {
        let zone = spec.zone_id.0.as_str();
        let prox_neighbors = proximity.get(zone);
        let adv_neighbors = adversarial.get(zone);

        let mut best: Option<(i64, Cell)> = None;
        // Iterate candidate cells in linear-index order — the deterministic
        // tie-break (first-found wins on an equal score).
        for gy in 0..n {
            for gx in 0..n {
                if taken.contains(&(gx, gy)) {
                    continue;
                }
                let cand = Cell { gx, gy };
                let mut score: i64 = 0;
                if let Some(neighbors) = prox_neighbors {
                    for nb in neighbors {
                        if let Some(&nb_cell) = placed.get(nb) {
                            score += cand.manhattan(nb_cell);
                        }
                    }
                }
                if let Some(neighbors) = adv_neighbors {
                    for nb in neighbors {
                        if let Some(&nb_cell) = placed.get(nb) {
                            // Adversarial: reward distance ⇒ subtract it.
                            score -= cand.manhattan(nb_cell);
                        }
                    }
                }
                if best.is_none_or(|(best_score, _)| score < best_score) {
                    best = Some((score, cand));
                }
            }
        }

        // A free cell always exists — the grid has n*n >= zone_count cells.
        let cell = best.expect("n*n grid has a free cell for every zone").1;
        placed.insert(zone, cell);
        taken.insert((cell.gx, cell.gy));
    }

    // Convert cells to normalized [0,1] centers, returned in zone_id order.
    specs
        .iter()
        .map(|spec| {
            let cell = placed[spec.zone_id.0.as_str()];
            PlacedZone {
                id: ZoneId(spec.zone_id.0.clone()),
                role: spec.zone_role,
                size: spec.size,
                pos: Vec2::new(
                    (cell.gx as f64 + 0.5) / n as f64,
                    (cell.gy as f64 + 0.5) / n as f64,
                ),
            }
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::template::{TemplateConnection, TilemapTemplateId, ZoneSpec};
    use crate::types::zone::ZoneRole;

    fn zone(id: &str, conns: &[(&str, PassageKind)]) -> ZoneSpec {
        ZoneSpec {
            zone_id: ZoneId(id.to_string()),
            zone_role: ZoneRole::Wilderness,
            size: 100,
            terrain_types: vec![],
            monster_strength: None,
            connections: conns
                .iter()
                .map(|(to, kind)| TemplateConnection::new(ZoneId(to.to_string()), *kind))
                .collect(),
            treasure_tiers: vec![],
            biome_selection_rules: None,
            inherit_treasure_from: None,
            biome_theme: None,
        }
    }

    fn template(zones: Vec<ZoneSpec>) -> TilemapTemplate {
        TilemapTemplate {
            template_id: TilemapTemplateId("t".to_string()),
            zones,
            seed_offset: 0,
            world_zone: None,
            decoration_density: None,
            background_biome: None,
        }
    }

    #[test]
    fn empty_template_yields_no_zones() {
        assert!(initial_grid_layout(&template(vec![])).is_empty());
    }

    #[test]
    fn single_zone_is_centered() {
        let layout = initial_grid_layout(&template(vec![zone("a", &[])]));
        assert_eq!(layout.len(), 1);
        assert_eq!(layout[0].pos, Vec2::new(0.5, 0.5)); // n=1 → cell (0,0) center
    }

    #[test]
    fn all_positions_are_in_unit_square_and_distinct() {
        let zones = (0..10)
            .map(|i| zone(&format!("z{i:02}"), &[]))
            .collect();
        let layout = initial_grid_layout(&template(zones));
        assert_eq!(layout.len(), 10);
        for z in &layout {
            assert!((0.0..=1.0).contains(&z.pos.x) && (0.0..=1.0).contains(&z.pos.y));
        }
        // Every zone gets its own cell — positions are pairwise distinct.
        for i in 0..layout.len() {
            for j in (i + 1)..layout.len() {
                assert_ne!(layout[i].pos, layout[j].pos, "zones share a cell");
            }
        }
    }

    #[test]
    fn deterministic_same_template_same_layout() {
        let mk = || {
            template(vec![
                zone("a", &[("b", PassageKind::Threshold)]),
                zone("b", &[("c", PassageKind::Open)]),
                zone("c", &[]),
                zone("d", &[]),
            ])
        };
        let l1 = initial_grid_layout(&mk());
        let l2 = initial_grid_layout(&mk());
        for (z1, z2) in l1.iter().zip(&l2) {
            assert_eq!(z1.id, z2.id);
            assert_eq!(z1.pos, z2.pos);
        }
    }

    #[test]
    fn connected_zones_seed_closer_than_unconnected() {
        // a–b connected (Threshold); a–c not. b should seed nearer a than c.
        let layout = initial_grid_layout(&template(vec![
            zone("a", &[("b", PassageKind::Threshold)]),
            zone("b", &[]),
            zone("c", &[]),
            zone("d", &[]),
        ]));
        let by = |id: &str| layout.iter().find(|z| z.id.0 == id).unwrap().pos;
        let (a, b, c) = (by("a"), by("b"), by("c"));
        assert!(
            a.distance(b) <= a.distance(c),
            "connected b ({b:?}) should seed no further from a ({a:?}) than unconnected c ({c:?})",
        );
    }

    #[test]
    fn adversarial_zones_seed_apart() {
        // a and b are Adversarial-connected — they should NOT be adjacent.
        let layout = initial_grid_layout(&template(vec![
            zone("a", &[("b", PassageKind::Adversarial)]),
            zone("b", &[]),
            zone("c", &[]),
            zone("d", &[]),
        ]));
        let by = |id: &str| layout.iter().find(|z| z.id.0 == id).unwrap().pos;
        // On a 2x2 grid the max separation is the diagonal; adversarial a/b
        // should take diagonal corners, not share an edge.
        assert!(
            by("a").distance(by("b")) > 0.5,
            "adversarial zones a/b seeded too close",
        );
    }
}
