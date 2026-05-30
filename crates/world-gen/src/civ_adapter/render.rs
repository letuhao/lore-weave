//! Civilization render — political-map PNG + SVG export with labels.
//!
//! Both renderers work in world-pixel coordinates by walking
//! `world.plates[].zones[].subzones[]` directly (NOT through
//! `view.centers`) so the sphere projection in `mesh::project_to_sphere`
//! doesn't affect the visual output.

use crate::flatworld::FlatWorld;
use crate::political::Political;
use crate::world_map::{Route, Settlement};

/// Build a HashMap from `(plate_id, zone_id, subzone_id)` to civ-layer
/// cell index. Iteration order matches
/// [`crate::civ_adapter::mesh::build_civ_view`] (plates outer, zones
/// middle, subzones inner) so the mapping is a stable function of
/// `world.plates`.
pub(crate) fn cell_index_map(
    world: &FlatWorld,
) -> std::collections::HashMap<(usize, usize, usize), u32> {
    let mut out = std::collections::HashMap::new();
    let mut idx: u32 = 0;
    for plate in &world.plates {
        for (zi, zone) in plate.zones.iter().enumerate() {
            for si in 0..zone.subzones.len() {
                out.insert((plate.id, zi, si), idx);
                idx += 1;
            }
        }
    }
    out
}

/// **LOW-2 fix (review 2026-05-30)**: pre-build the full `cell_idx →
/// center` table once so a render that emits ~1000 features doesn't
/// walk the plate tree for every callsite. Iteration order matches
/// [`mesh::build_civ_view`] (plates outer, zones middle, subzones inner)
/// so the returned Vec is indexable by civ-layer cell index. The
/// pipeline sphere regression test also consumes this lookup directly —
/// the previous O(N) per-call `cell_index_to_center` helper was deleted
/// alongside the render-internal callsites.
pub(crate) fn cell_center_lookup(world: &FlatWorld) -> Vec<(f32, f32)> {
    let mut out = Vec::new();
    for plate in &world.plates {
        for zone in &plate.zones {
            for sub in &zone.subzones {
                out.push(sub.center);
            }
        }
    }
    out
}

/// Deterministic per-state colour from a stable HSV palette.
///
/// **LOW-4 fix (review 2026-05-30)**: bumped hue multiplier 57 → 137.
/// `gcd(57, 360) = 3` aliased every 120 states (state 0 and state 120
/// got identical hue); `gcd(137, 360) = 1` so all 360 hues are reachable.
/// 137 is also close to the golden-angle approximation (137.5°) which
/// maximises perceptual separation between successive ids.
fn state_color(state_id: u32) -> [u8; 3] {
    let hue = (state_id.wrapping_mul(137) % 360) as f32;
    let sat = 0.55;
    let val = 0.85;
    hsv_to_rgb(hue, sat, val)
}

fn hsv_to_rgb(h: f32, s: f32, v: f32) -> [u8; 3] {
    let c = v * s;
    let hp = h / 60.0;
    let x = c * (1.0 - (hp % 2.0 - 1.0).abs());
    let (r, g, b) = match hp as u32 {
        0 => (c, x, 0.0),
        1 => (x, c, 0.0),
        2 => (0.0, c, x),
        3 => (0.0, x, c),
        4 => (x, 0.0, c),
        _ => (c, 0.0, x),
    };
    let m = v - c;
    [
        ((r + m) * 255.0).round() as u8,
        ((g + m) * 255.0).round() as u8,
        ((b + m) * 255.0).round() as u8,
    ]
}

fn paint_disk(buf: &mut [u8], w: usize, h: usize, cx: i32, cy: i32, r: i32, color: [u8; 3]) {
    let r2 = r * r;
    for dy in -r..=r {
        for dx in -r..=r {
            if dx * dx + dy * dy > r2 {
                continue;
            }
            let x = cx + dx;
            let y = cy + dy;
            if x < 0 || y < 0 || (x as usize) >= w || (y as usize) >= h {
                continue;
            }
            let off = (y as usize * w + x as usize) * 3;
            buf[off] = color[0];
            buf[off + 1] = color[1];
            buf[off + 2] = color[2];
        }
    }
}

fn escape_xml(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&apos;")
}

/// **Civ Ship 8** — political-map RGB buffer.
///
/// Per-pixel hit-test: find covering plate → its sub-zone via
/// `Plate::zone_at_polygon` + `Zone::subzone_at_polygon` → look up
/// `political.province_of[cell] → political.provinces[…].state` →
/// colour by [`state_color`]. Void pixels render as deep-ocean blue;
/// settlement cells get a white 3-px disk overlay.
///
/// Buffer layout: `width * height * 3` RGB bytes, top-left origin.
pub fn render_civ_political_png(
    world: &FlatWorld,
    political: &Political,
    settlements: &[Settlement],
) -> Vec<u8> {
    const VOID: [u8; 3] = [12, 22, 48];
    let w = world.width as usize;
    let h = world.height as usize;
    let mut buf = vec![0u8; w * h * 3];
    let idx_of = cell_index_map(world);

    for py in 0..h {
        for px in 0..w {
            let fx = px as f32 + 0.5;
            let fy = py as f32 + 0.5;
            let pixel_color = match world.plates.iter().find(|p| p.contains(fx, fy)) {
                None => VOID,
                Some(plate) => {
                    let zi_opt = plate.zone_at_polygon(fx, fy);
                    let mut color = VOID;
                    if let Some(zi) = zi_opt {
                        let zone = &plate.zones[zi];
                        if let Some(si) = zone.subzone_at_polygon(fx, fy) {
                            if let Some(&cell_idx) = idx_of.get(&(plate.id, zi, si)) {
                                let prov = political.province_of[cell_idx as usize];
                                if prov != u32::MAX {
                                    let state = political.provinces[prov as usize].state;
                                    color = state_color(state);
                                }
                            }
                        }
                    }
                    color
                }
            };
            let off = (py * w + px) * 3;
            buf[off] = pixel_color[0];
            buf[off + 1] = pixel_color[1];
            buf[off + 2] = pixel_color[2];
        }
    }

    let centers = cell_center_lookup(world);
    for s in settlements {
        let cell = s.cell as usize;
        if let Some(&(cx, cy)) = centers.get(cell) {
            paint_disk(&mut buf, w, h, cx as i32, cy as i32, 3, [255, 255, 255]);
        }
    }

    buf
}

/// **Civ Ship 8** — SVG export of the civ bundle.
///
/// Layers (back to front):
/// 1. World background rectangle (light ocean blue).
/// 2. Plate polygons filled with their state hue.
/// 3. Route polylines along each route's `path` cell-centre traversal.
/// 4. Settlement circles + text labels.
/// 5. Province name labels at the capital cell centre.
#[allow(clippy::too_many_arguments)]
pub fn render_civ_svg(
    world: &FlatWorld,
    political: &Political,
    settlements: &[Settlement],
    routes_v: &[Route],
) -> String {
    let w = world.width;
    let h = world.height;
    let mut svg = String::new();
    svg.push_str(&format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n\
         <svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 {w} {h}\" \
         width=\"{w}\" height=\"{h}\">\n",
    ));
    svg.push_str(&format!(
        "  <rect x=\"0\" y=\"0\" width=\"{w}\" height=\"{h}\" fill=\"#0c1630\"/>\n",
    ));

    let idx_of = cell_index_map(world);
    let centers = cell_center_lookup(world);
    for plate in &world.plates {
        let tint = plate
            .zones
            .iter()
            .enumerate()
            .find_map(|(zi, zone)| {
                zone.subzones.iter().enumerate().find_map(|(si, _)| {
                    idx_of.get(&(plate.id, zi, si)).copied()
                })
            })
            .map(|cell| {
                let prov = political.province_of[cell as usize];
                if prov == u32::MAX {
                    [128, 128, 160]
                } else {
                    state_color(political.provinces[prov as usize].state)
                }
            })
            .unwrap_or([128, 128, 160]);
        let fill = format!("#{:02x}{:02x}{:02x}", tint[0], tint[1], tint[2]);
        for poly in &plate.components {
            let points = poly
                .iter()
                .map(|&(x, y)| format!("{:.1},{:.1}", x, y))
                .collect::<Vec<_>>()
                .join(" ");
            svg.push_str(&format!(
                "  <polygon points=\"{points}\" fill=\"{fill}\" \
                 fill-opacity=\"0.5\" stroke=\"#222\" stroke-width=\"1\"/>\n",
            ));
        }
    }

    for r in routes_v {
        if r.path.len() < 2 {
            continue;
        }
        let pts: Vec<(f32, f32)> = r
            .path
            .iter()
            .filter_map(|&c| centers.get(c as usize).copied())
            .collect();
        if pts.len() < 2 {
            continue;
        }
        let coords = pts
            .iter()
            .map(|&(x, y)| format!("{:.1},{:.1}", x, y))
            .collect::<Vec<_>>()
            .join(" ");
        let stroke = match r.kind {
            crate::world_map::RouteKind::Road => "#3a2a18",
            crate::world_map::RouteKind::SeaLane => "#1c4a7a",
            crate::world_map::RouteKind::Trail => "#5a4a2a",
            crate::world_map::RouteKind::RiverNavigation => "#2a8aa0",
            crate::world_map::RouteKind::MountainPass => "#7a6a5a",
        };
        svg.push_str(&format!(
            "  <polyline points=\"{coords}\" fill=\"none\" stroke=\"{stroke}\" \
             stroke-width=\"1.5\" stroke-opacity=\"0.85\"/>\n",
        ));
    }

    for s in settlements {
        if let Some(&(x, y)) = centers.get(s.cell as usize) {
            svg.push_str(&format!(
                "  <circle cx=\"{:.1}\" cy=\"{:.1}\" r=\"3\" fill=\"#fff\" stroke=\"#222\"/>\n",
                x, y
            ));
            let escaped = escape_xml(&s.name);
            svg.push_str(&format!(
                "  <text x=\"{:.1}\" y=\"{:.1}\" font-size=\"10\" fill=\"#fff\" \
                 stroke=\"#000\" stroke-width=\"0.4\" \
                 font-family=\"sans-serif\">{escaped}</text>\n",
                x + 4.0,
                y - 4.0
            ));
        }
    }

    for prov in &political.provinces {
        if let Some(&(x, y)) = centers.get(prov.capital_cell as usize) {
            let escaped = escape_xml(&prov.name);
            svg.push_str(&format!(
                "  <text x=\"{:.1}\" y=\"{:.1}\" font-size=\"8\" fill=\"#eee\" \
                 fill-opacity=\"0.85\" font-style=\"italic\" \
                 font-family=\"serif\">{escaped}</text>\n",
                x + 5.0,
                y + 10.0
            ));
        }
    }

    svg.push_str("</svg>\n");
    svg
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::creative_seed::SettlementDensity;
    use crate::flat_climate::WorldClimateParams;
    use crate::flatworld::{generate, FlatParams};

    use super::super::naming::apply_synthetic_names;
    use super::super::pipeline::build_culture;

    #[test]
    fn political_png_has_correct_byte_length() {
        let world = generate(&FlatParams::default());
        let (_, _, political, _, settlements, _, _) = build_culture(
            &world,
            &WorldClimateParams::default(),
            64,
            42,
            SettlementDensity::Medium,
            5,
        );
        let buf = render_civ_political_png(&world, &political, &settlements);
        assert_eq!(
            buf.len(),
            (world.width as usize) * (world.height as usize) * 3,
            "PNG buffer should be width*height*3 bytes"
        );
    }

    #[test]
    fn political_png_paints_void_pixels_with_ocean_blue() {
        let world = generate(&FlatParams::default());
        let (_, _, political, _, settlements, _, _) = build_culture(
            &world,
            &WorldClimateParams::default(),
            64,
            42,
            SettlementDensity::Medium,
            5,
        );
        let buf = render_civ_political_png(&world, &political, &settlements);
        let w = world.width as usize;
        let h = world.height as usize;
        let mut void_found = false;
        for py in 0..h.min(50) {
            for px in 0..w.min(50) {
                let fx = px as f32 + 0.5;
                let fy = py as f32 + 0.5;
                if world.plates.iter().any(|p| p.contains(fx, fy)) {
                    continue;
                }
                let off = (py * w + px) * 3;
                assert_eq!(
                    (buf[off], buf[off + 1], buf[off + 2]),
                    (12, 22, 48),
                    "void pixel at ({px},{py}) should be ocean blue (12,22,48)"
                );
                void_found = true;
            }
        }
        assert!(
            void_found,
            "test world must have ≥1 void pixel in the top-left 50×50 window"
        );
    }

    #[test]
    fn civ_svg_export_well_formed_and_contains_features() {
        let world = generate(&FlatParams::default());
        let (_, mut features, mut political, _, mut settlements, routes_v, mut culture_v) =
            build_culture(
                &world,
                &WorldClimateParams::default(),
                64,
                42,
                SettlementDensity::Medium,
                5,
            );
        apply_synthetic_names(
            &mut features,
            &mut political,
            &mut settlements,
            &mut culture_v,
            42,
        );
        let svg = render_civ_svg(&world, &political, &settlements, &routes_v);
        assert!(svg.starts_with("<?xml"), "SVG must start with XML decl");
        assert!(svg.contains("<svg "), "must contain <svg> root");
        assert!(svg.contains("<polygon "), "must emit plate polygons");
        assert!(svg.contains("<circle "), "must emit settlement circles");
        assert!(svg.contains("<text "), "must emit text labels");
        assert!(svg.ends_with("</svg>\n"), "must close <svg>");
    }
}
