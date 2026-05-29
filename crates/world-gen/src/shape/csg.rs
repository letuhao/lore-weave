//! Boolean polygon-ops (CSG) shape generator — union / difference /
//! intersection of simple sub-ellipses via the `geo-clipper` crate
//! (v3.1b). Produces rings, peanut-shapes (Africa-like), crescents
//! (gulf/coast bay), and wedge-cut continents.
//!
//! Algorithm: build 2–3 sub-ellipses in clean f64 coords (no fbm — clipper
//! needs simple inputs to avoid degenerate output). Apply Boolean op via
//! `Clipper`. Take the largest component if the result is multi-polygon.
//! Discard inner holes (Ring template). Resample to `vertex_count_range`
//! count via arc-length interpolation. Apply per-vertex jitter, rotate,
//! translate.
//!
//! Templates (picked deterministically by `hash(ctx.seed) % 4`):
//! - **Ring** — outer ellipse minus smaller centred ellipse (inner ring
//!   discarded — v3.3 hole support deferred).
//! - **EllipseUnion** — two overlapping ellipses → peanut.
//! - **EllipseDifference** — ellipse minus offset ellipse → crescent.
//! - **WedgeCut** — ellipse minus triangular wedge → gulf/inlet.
//!
//! `safe_boolean` wraps every clipper call: if the result is empty or
//! degenerate, returns the operand A unchanged (visible failure beats
//! silent emptiness in a generated map).
//!
//! Determinism: `Rng::for_stage(ctx.seed as u64, b"boolean")`.

use std::f32::consts::TAU;

use geo_clipper::Clipper;
use geo_types::{Coord, LineString, MultiPolygon, Polygon as GeoPolygon};

use crate::flatworld::Polygon;
use crate::rng::Rng;

use super::{ShapeContext, ShapeGenerator, ShapeKind, ShapeResult};

/// Fixed-point scale factor for geo-clipper. Polygons span roughly
/// `[-1, 1]` units in local coords, so 10_000 gives sub-0.0001 precision.
const CLIPPER_SCALE: f64 = 10_000.0;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
pub enum BooleanTemplate {
    /// Outer ellipse minus inner centred ellipse → annulus. **Reserved for
    /// v3.3** (hole-in-polygon support): currently the inner hole is
    /// discarded which makes Ring's exterior identical to its outer
    /// ellipse — zero visual variety vs an Ellipse plate. Removed from
    /// active rotation in v3.1b; will rejoin when `Polygon` supports
    /// interior rings in v3.3 marching-squares era.
    Ring,
    /// Two overlapping ellipses → peanut.
    EllipseUnion,
    /// Ellipse minus offset ellipse → crescent.
    EllipseDifference,
    /// Ellipse minus triangular wedge → gulf / inlet.
    WedgeCut,
}

impl BooleanTemplate {
    /// Active templates picked by `pick_template`. Ring is reserved (see
    /// doc comment) so it never lands until v3.3 hole support arrives.
    const ACTIVE: [BooleanTemplate; 3] = [
        BooleanTemplate::EllipseUnion,
        BooleanTemplate::EllipseDifference,
        BooleanTemplate::WedgeCut,
    ];

}

pub struct BooleanGenerator;

impl ShapeGenerator for BooleanGenerator {
    fn kind(&self) -> ShapeKind {
        ShapeKind::Boolean
    }

    fn generate(&self, ctx: &ShapeContext, _caller_rng: &mut Rng) -> ShapeResult {
        let mut rng = Rng::for_stage(ctx.seed as u64, b"boolean");
        // **v4.3b**: honour an LLM-decided template selection from
        // `ctx.params` when present; otherwise fall back to the seed-driven
        // pick. Default (None) path is byte-identical to v4.3a.
        let template = match &ctx.params {
            Some(crate::shape::ParamOverride::Boolean { template: Some(t) }) => *t,
            _ => pick_template(ctx.seed),
        };

        // Build sub-polygons in local f64 unit coords (roughly [-1, 1]).
        // `fallback_used` is true when the clipper op returned empty or
        // degenerate and `safe_boolean` had to return operand A unchanged
        // — the resulting polygon is effectively a clean ellipse, so we
        // downgrade `effective_kind` to Ellipse for honest telemetry.
        //
        // v3.3: pieces is `Vec<GeoPolygon>` (sorted desc by area). For
        // current templates this is always len == 1 (all unions/diffs
        // produce connected geometry). v3.5+ templates may emit multiple
        // disjoint pieces — the dispatcher path handles both.
        let mut fallback_used = false;
        let pieces_f64 = match template {
            BooleanTemplate::Ring => {
                // Reserved for v3.3+ hole support — `pick_template` never
                // returns Ring today. The arm exists so future hole-aware
                // callers can request it via `DispatchMode::Fixed`.
                let outer = unit_ellipse_f64(1.0, 0.8, 0.0, 0.0, 48);
                let inner = unit_ellipse_f64(0.4, 0.32, 0.0, 0.0, 32);
                safe_difference(&outer, &inner, &mut fallback_used)
            }
            BooleanTemplate::EllipseUnion => {
                let a = unit_ellipse_f64(0.7, 0.55, -0.35, 0.0, 36);
                let b = unit_ellipse_f64(0.7, 0.55, 0.35, 0.0, 36);
                safe_union(&a, &b, &mut fallback_used)
            }
            BooleanTemplate::EllipseDifference => {
                let a = unit_ellipse_f64(1.0, 0.7, 0.0, 0.0, 48);
                // **v3.4 fix**: smaller inner ellipse placed FURTHER from
                // origin so the subtracted region does not contain (0, 0).
                // Previously rx=0.6/ry=0.5 at (0.5, 0.2) still covered the
                // origin (normalized dist ≈ 0.92 < 1), so `contains` failed
                // on the difference result. Now rx=0.45/ry=0.40 at (0.6, 0.25)
                // → origin at normalized dist (-0.6/0.45)² + (-0.25/0.4)² ≈
                // 1.78 + 0.39 ≈ 2.17 (outside the inner ellipse).
                let b = unit_ellipse_f64(0.45, 0.40, 0.6, 0.25, 32);
                safe_difference(&a, &b, &mut fallback_used)
            }
            BooleanTemplate::WedgeCut => {
                let a = unit_ellipse_f64(1.0, 0.8, 0.0, 0.0, 48);
                // **v3.4 fix**: wedge vertex at (0.5, 0) instead of origin —
                // the wedge bites IN from the right side of the ellipse, not
                // THROUGH the centre. Previously the (0, 0) vertex placed
                // the centre of the plate on the boundary of the resulting
                // Pac-Man polygon, which `plate.contains(plate.center)`
                // reports as outside. Caught when v3.4 dispatcher weights
                // pushed WedgeCut into plate 8 at default seed.
                let wedge = wedge_f64(0.5, 0.0, 0.7, 0.45);
                safe_difference(&a, &wedge, &mut fallback_used)
            }
        };

        // Convert each piece to f32 + filter by 1% min-area-of-bbox.
        // For multi-piece output the bbox covers ALL pieces so satellites
        // are measured against the same yardstick as the primary.
        let f32_pieces: Vec<Polygon> = pieces_f64
            .iter()
            .map(|gp| {
                let mut p: Polygon = gp
                    .exterior()
                    .coords()
                    .map(|c| (c.x as f32, c.y as f32))
                    .collect();
                if p.len() >= 2 && p.first() == p.last() {
                    p.pop();
                }
                p
            })
            .filter(|p| p.len() >= 3)
            .collect();
        let pieces_filtered = filter_pieces_by_area(f32_pieces);
        let pieces = if pieces_filtered.is_empty() {
            // Defensive: every piece was degenerate. Hard-fallback to a
            // clean ellipse so the dispatcher never sees an empty plate.
            vec![(0..32)
                .map(|k| {
                    let t = TAU * (k as f32) / 32.0;
                    (t.cos() * 0.9, t.sin() * 0.7)
                })
                .collect()]
        } else {
            pieces_filtered
        };

        // Shared rotation + target vertex count across all pieces (visual
        // consistency for multi-piece Boolean continents).
        let (vmin, vmax) = ctx.vertex_count_range;
        let max_v = vmax.max(vmin);
        let target_nv_primary = (vmin + (rng.next_f32() * (max_v - vmin + 1) as f32) as usize)
            .clamp(12, max_v.max(12));
        let theta_rot = rng.next_f32() * TAU;

        // First pass: resample + jitter each piece in local coords (where the
        // SHARED transform later applies the same scale to all of them).
        let mut jittered_pieces: Vec<Polygon> = Vec::with_capacity(pieces.len());
        for (idx, piece) in pieces.into_iter().enumerate() {
            let nv = if idx == 0 { target_nv_primary } else { vmin.max(12) };
            let resampled = resample_arclength(&piece, nv);
            let jitters: Vec<f32> = (0..resampled.len()).map(|_| rng.next_f32()).collect();
            let j: Polygon = resampled
                .iter()
                .enumerate()
                .map(|(i, &(x, y))| {
                    let r = (x * x + y * y).sqrt();
                    let theta = y.atan2(x);
                    let r2 = r * (1.0 + (jitters[i] - 0.5) * ctx.edge_jitter * 0.6);
                    (r2 * theta.cos(), r2 * theta.sin())
                })
                .collect();
            jittered_pieces.push(j);
        }

        // Pre-compute combined bbox + max distance-from-bbox-centre across
        // all pieces, so all pieces share one scale. Single-piece case
        // matches v3.2 `fit_to_envelope` exactly (max_dist is computed the
        // same way), preserving hash pins.
        let (mut all_minx, mut all_miny) = (f32::INFINITY, f32::INFINITY);
        let (mut all_maxx, mut all_maxy) = (f32::NEG_INFINITY, f32::NEG_INFINITY);
        for p in &jittered_pieces {
            for &(x, y) in p {
                all_minx = all_minx.min(x);
                all_miny = all_miny.min(y);
                all_maxx = all_maxx.max(x);
                all_maxy = all_maxy.max(y);
            }
        }
        let combined_bbox = (all_minx, all_miny, all_maxx, all_maxy);
        let lcx = (all_minx + all_maxx) * 0.5;
        let lcy = (all_miny + all_maxy) * 0.5;
        let combined_max_dist = jittered_pieces
            .iter()
            .flat_map(|p| p.iter())
            .map(|&(x, y)| ((x - lcx).powi(2) + (y - lcy).powi(2)).sqrt())
            .fold(0.0_f32, f32::max)
            .max(1e-6);

        let polygons: Vec<Polygon> = jittered_pieces
            .into_iter()
            .map(|j| {
                fit_piece_to_envelope_shared(&j, ctx, theta_rot, combined_bbox, combined_max_dist)
            })
            .collect();

        // Effective kind: Ellipse if the clipper op fell back (operand A
        // unchanged → result is geometrically a clean ellipse, not a
        // Boolean composite). Otherwise Boolean.
        let effective_kind = if fallback_used {
            ShapeKind::Ellipse
        } else {
            ShapeKind::Boolean
        };

        // **v3.4 defensive check**: if the Boolean polygon does not contain
        // ctx.center (rare interaction of per-vertex jitter × concave
        // wedge/difference cut × rotation), fall back to a clean Ellipse so
        // downstream `plate.contains(plate.center)` succeeds. Honest
        // `effective_kind = Ellipse` reporting consistent with v3.1c.
        if !polygons.is_empty() && !point_in_polygon(&polygons[0], ctx.center) {
            let mut fallback_rng = Rng::for_stage(ctx.seed as u64, b"boolean-fallback");
            let ell = super::EllipseGenerator;
            let mut fallback = ell.generate(ctx, &mut fallback_rng);
            fallback.effective_kind = ShapeKind::Ellipse;
            return fallback;
        }

        ShapeResult {
            polygons,
            effective_kind,
        }
    }
}

fn point_in_polygon(poly: &Polygon, point: (f32, f32)) -> bool {
    let n = poly.len();
    if n < 3 {
        return false;
    }
    let mut inside = false;
    for i in 0..n {
        let (xi, yi) = poly[i];
        let (xj, yj) = poly[(i + 1) % n];
        let cond = ((yi > point.1) != (yj > point.1))
            && (point.0 < (xj - xi) * (point.1 - yi) / (yj - yi + f32::EPSILON) + xi);
        if cond {
            inside = !inside;
        }
    }
    inside
}

fn pick_template(seed: u32) -> BooleanTemplate {
    let mixed = seed
        .wrapping_mul(0x1656_67B1)
        .wrapping_add(0x9E37_79B9)
        .rotate_left(7);
    BooleanTemplate::ACTIVE[(mixed as usize) % BooleanTemplate::ACTIVE.len()]
}

fn unit_ellipse_f64(rx: f64, ry: f64, cx: f64, cy: f64, nv: usize) -> GeoPolygon<f64> {
    let coords: Vec<Coord<f64>> = (0..nv)
        .map(|k| {
            let theta = (k as f64) * std::f64::consts::TAU / (nv as f64);
            Coord {
                x: cx + rx * theta.cos(),
                y: cy + ry * theta.sin(),
            }
        })
        .collect();
    GeoPolygon::new(LineString::new(coords), Vec::new())
}

/// Triangular wedge centred at `(cx, cy)` opening to the right; `length`
/// = half-extent along x, `half_height` = half-extent along y.
fn wedge_f64(cx: f64, cy: f64, length: f64, half_height: f64) -> GeoPolygon<f64> {
    let coords = vec![
        Coord { x: cx, y: cy },
        Coord {
            x: cx + length,
            y: cy + half_height,
        },
        Coord {
            x: cx + length,
            y: cy - half_height,
        },
    ];
    GeoPolygon::new(LineString::new(coords), Vec::new())
}

fn safe_union(
    a: &GeoPolygon<f64>,
    b: &GeoPolygon<f64>,
    fallback_used: &mut bool,
) -> Vec<GeoPolygon<f64>> {
    let result: MultiPolygon<f64> = a.union(b, CLIPPER_SCALE);
    sort_or_fallback(result, a, fallback_used)
}

fn safe_difference(
    a: &GeoPolygon<f64>,
    b: &GeoPolygon<f64>,
    fallback_used: &mut bool,
) -> Vec<GeoPolygon<f64>> {
    let result: MultiPolygon<f64> = a.difference(b, CLIPPER_SCALE);
    sort_or_fallback(result, a, fallback_used)
}

/// **v3.3**: return all pieces from the clipper output, sorted by descending
/// area so `[0]` is the primary. v3.5+ multi-component Boolean templates
/// (e.g. `EllipseBinary` = two disjoint ellipses union) will exercise the
/// multi-piece path. Current v3.3 templates (EllipseUnion / EllipseDifference
/// / WedgeCut) all produce connected geometry so `result.len() == 1` in
/// practice — but the API path is now multi-aware.
///
/// Falls back to operand `a` when the clipper op returns empty or degenerate.
fn sort_or_fallback(
    result: MultiPolygon<f64>,
    fallback: &GeoPolygon<f64>,
    fallback_used: &mut bool,
) -> Vec<GeoPolygon<f64>> {
    if result.0.is_empty() {
        *fallback_used = true;
        return vec![fallback.clone()];
    }
    let mut sorted: Vec<(f64, GeoPolygon<f64>)> = result
        .0
        .into_iter()
        .map(|p| (signed_area_f64(&p).abs(), p))
        .collect();
    sorted.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap_or(std::cmp::Ordering::Equal));
    if sorted.is_empty() {
        *fallback_used = true;
        return vec![fallback.clone()];
    }
    sorted.into_iter().map(|(_, p)| p).collect()
}

fn signed_area_f64(poly: &GeoPolygon<f64>) -> f64 {
    let coords: Vec<Coord<f64>> = poly.exterior().coords().copied().collect();
    let n = coords.len();
    if n < 3 {
        return 0.0;
    }
    let mut acc = 0.0;
    for i in 0..n {
        let j = (i + 1) % n;
        acc += coords[i].x * coords[j].y - coords[j].x * coords[i].y;
    }
    acc * 0.5
}

/// Resample a closed polygon to `target_nv` vertices via uniform arc-length
/// walk. Adjacent original vertices are linearly interpolated.
fn resample_arclength(poly: &Polygon, target_nv: usize) -> Polygon {
    let n = poly.len();
    if n < 3 || target_nv < 3 {
        return poly.clone();
    }
    // Cumulative arc length around the closed ring.
    let mut cum = Vec::with_capacity(n + 1);
    cum.push(0.0_f32);
    for i in 0..n {
        let (x1, y1) = poly[i];
        let (x2, y2) = poly[(i + 1) % n];
        let dx = x2 - x1;
        let dy = y2 - y1;
        let len = (dx * dx + dy * dy).sqrt();
        cum.push(cum[i] + len);
    }
    let total = *cum.last().unwrap();
    if total < 1e-6 {
        return poly.clone();
    }
    let step = total / (target_nv as f32);
    let mut out = Vec::with_capacity(target_nv);
    let mut seg = 0;
    for k in 0..target_nv {
        let s = step * (k as f32);
        while seg + 1 < cum.len() && cum[seg + 1] < s {
            seg += 1;
        }
        let seg_start = cum[seg];
        let seg_len = (cum[seg + 1] - seg_start).max(1e-6);
        let frac = ((s - seg_start) / seg_len).clamp(0.0, 1.0);
        let (x1, y1) = poly[seg];
        let (x2, y2) = poly[(seg + 1) % n];
        out.push((x1 + (x2 - x1) * frac, y1 + (y2 - y1) * frac));
    }
    out
}

/// **v3.3**: drop pieces whose area is < 1% of the combined-bbox area. The
/// primary (largest) is always kept regardless. Mirrors the
/// `raster::finalize_multi_component` semantics for parity across generators.
fn filter_pieces_by_area(pieces: Vec<Polygon>) -> Vec<Polygon> {
    if pieces.is_empty() {
        return pieces;
    }
    let (mut all_minx, mut all_miny) = (f32::INFINITY, f32::INFINITY);
    let (mut all_maxx, mut all_maxy) = (f32::NEG_INFINITY, f32::NEG_INFINITY);
    for p in &pieces {
        for &(x, y) in p {
            all_minx = all_minx.min(x);
            all_miny = all_miny.min(y);
            all_maxx = all_maxx.max(x);
            all_maxy = all_maxy.max(y);
        }
    }
    let bbox_area = (all_maxx - all_minx).abs() * (all_maxy - all_miny).abs();
    let threshold = bbox_area * 0.01;
    let mut sorted: Vec<(f32, Polygon)> = pieces
        .into_iter()
        .map(|p| (signed_area_f32(&p).abs(), p))
        .collect();
    sorted.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap_or(std::cmp::Ordering::Equal));
    let mut iter = sorted.into_iter();
    let primary = match iter.next() {
        Some((_, p)) => p,
        None => return Vec::new(),
    };
    let mut out = vec![primary];
    for (a, p) in iter {
        if a >= threshold {
            out.push(p);
        }
    }
    out
}

fn signed_area_f32(poly: &Polygon) -> f32 {
    let n = poly.len();
    if n < 3 {
        return 0.0;
    }
    let mut a = 0.0f32;
    for i in 0..n {
        let (x1, y1) = poly[i];
        let (x2, y2) = poly[(i + 1) % n];
        a += x1 * y2 - x2 * y1;
    }
    a * 0.5
}

/// Scale + rotate + translate `piece` using a SHARED transform derived from
/// the `combined_bbox` centre + `combined_max_dist` across all sibling
/// pieces — preserves relative positions between primary and satellites,
/// and (for the single-piece case) matches the v3.2 `fit_to_envelope`
/// behaviour byte-for-byte so single-piece Boolean plates don't shift.
fn fit_piece_to_envelope_shared(
    piece: &Polygon,
    ctx: &ShapeContext,
    theta_rot: f32,
    combined_bbox: (f32, f32, f32, f32),
    combined_max_dist: f32,
) -> Polygon {
    let (minx, miny, maxx, maxy) = combined_bbox;
    let lcx = (minx + maxx) * 0.5;
    let lcy = (miny + maxy) * 0.5;
    let target_radius = ctx.envelope.0.min(ctx.envelope.1);
    let scale = target_radius / combined_max_dist.max(1e-6);
    let cos_t = theta_rot.cos();
    let sin_t = theta_rot.sin();
    piece
        .iter()
        .map(|&(x, y)| {
            let sx = (x - lcx) * scale;
            let sy = (y - lcy) * scale;
            let rx = sx * cos_t - sy * sin_t;
            let ry = sx * sin_t + sy * cos_t;
            (ctx.center.0 + rx, ctx.center.1 + ry)
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::flatworld::SizeRank;

    fn ctx(seed: u32) -> ShapeContext {
        ShapeContext {
            depth: 0,
            center: (500.0, 300.0),
            envelope: (200.0, 200.0),
            size_rank: SizeRank::Large,
            seed,
            plate_salt: seed,
            parent_path: Vec::new(),
            world_theme: None,
            edge_jitter: 0.10,
            vertex_count_range: (32, 48),
            params: None,
        }
    }

    fn ctx_production(seed: u32) -> ShapeContext {
        ShapeContext {
            depth: 0,
            center: (512.0, 320.0),
            envelope: (291.5, 291.5),
            size_rank: SizeRank::Large,
            seed,
            plate_salt: seed,
            parent_path: Vec::new(),
            world_theme: None,
            edge_jitter: 0.35,
            vertex_count_range: (24, 48),
            params: None,
        }
    }

    #[test]
    fn boolean_kind_is_boolean() {
        assert_eq!(BooleanGenerator.kind(), ShapeKind::Boolean);
    }

    #[test]
    fn boolean_does_not_perturb_caller_rng() {
        let mut rng_a = Rng::for_stage(1, b"caller");
        let mut rng_b = Rng::for_stage(1, b"caller");
        let _ = BooleanGenerator.generate(&ctx(1), &mut rng_a);
        for _ in 0..5 {
            assert_eq!(rng_a.next_u32(), rng_b.next_u32());
        }
    }

    #[test]
    fn boolean_deterministic_same_seed() {
        let mut rng_a = Rng::for_stage(1, b"a");
        let mut rng_b = Rng::for_stage(2, b"b");
        let a = BooleanGenerator.generate(&ctx(99), &mut rng_a).polygons;
        let b = BooleanGenerator.generate(&ctx(99), &mut rng_b).polygons;
        for (p, q) in a[0].iter().zip(b[0].iter()) {
            assert_eq!(p.0.to_bits(), q.0.to_bits());
            assert_eq!(p.1.to_bits(), q.1.to_bits());
        }
    }

    #[test]
    fn boolean_active_templates_all_reachable() {
        // ACTIVE = EllipseUnion + EllipseDifference + WedgeCut (Ring is
        // reserved for v3.3). Each of the 3 must be reachable.
        let mut seen = std::collections::HashSet::new();
        for s in 0u32..500 {
            seen.insert(pick_template(s));
        }
        assert_eq!(seen.len(), 3, "all 3 ACTIVE templates must be reachable");
        assert!(
            !seen.contains(&BooleanTemplate::Ring),
            "Ring must not appear in pick_template until v3.3"
        );
    }

    #[test]
    fn boolean_each_active_template_produces_valid_polygon() {
        // Iterate ACTIVE (not ALL — Ring is reserved for v3.3 and never
        // returned by pick_template, so a seed search would overflow).
        for target in BooleanTemplate::ACTIVE {
            let mut seed = 0u32;
            while pick_template(seed) != target {
                seed = seed
                    .checked_add(1)
                    .expect("Every ACTIVE template must be reachable within u32 seeds");
            }
            let c = ctx(seed);
            let mut rng = Rng::for_stage(seed as u64, b"caller");
            let polys = BooleanGenerator.generate(&c, &mut rng).polygons;
            assert_eq!(polys.len(), 1, "{target:?}: expected single component");
            assert!(
                polys[0].len() >= 12,
                "{target:?}: polygon too small ({} vertices)",
                polys[0].len()
            );
        }
    }

    #[test]
    fn ring_template_outer_area_larger_than_inner_minus() {
        // Sanity check: Ring template's outer ellipse area = π * 1.0 * 0.8 ≈
        // 2.51, inner = π * 0.4 * 0.32 ≈ 0.40. Ring area ≈ 2.11.
        let outer = unit_ellipse_f64(1.0, 0.8, 0.0, 0.0, 64);
        let inner = unit_ellipse_f64(0.4, 0.32, 0.0, 0.0, 48);
        let mut fallback = false;
        let ring_pieces = safe_difference(&outer, &inner, &mut fallback);
        assert!(!fallback, "outer-minus-inner should produce non-empty result");
        assert_eq!(ring_pieces.len(), 1, "Ring outer-minus-inner is a single connected ring");
        let ring_area = signed_area_f64(&ring_pieces[0]).abs();
        let outer_area = signed_area_f64(&outer).abs();
        // Ring exterior is the outer ellipse (interior holes dropped),
        // so the *exterior* area equals the outer area. The actual "ring
        // area" with the hole subtracted would be ~84% of outer, but we
        // discard holes, so this asserts the contract: exterior is the
        // outer ellipse.
        assert!(
            (ring_area - outer_area).abs() < outer_area * 0.01,
            "Ring exterior should match outer ellipse (holes discarded)"
        );
    }

    #[test]
    fn ellipse_union_area_within_envelope() {
        let a = unit_ellipse_f64(0.7, 0.55, -0.35, 0.0, 36);
        let b = unit_ellipse_f64(0.7, 0.55, 0.35, 0.0, 36);
        let mut fallback = false;
        let union_pieces = safe_union(&a, &b, &mut fallback);
        assert!(!fallback, "union of two overlapping ellipses should not fall back");
        assert_eq!(union_pieces.len(), 1, "Overlapping ellipses union → single connected piece");
        let area = signed_area_f64(&union_pieces[0]).abs();
        // Each ellipse area ≈ π·0.7·0.55 = 1.21; two overlapping ≈ 1.8-2.1.
        assert!(
            (1.5..=2.6).contains(&area),
            "union area {area} outside reasonable bounds"
        );
    }

    #[test]
    fn resample_preserves_closed_shape() {
        // Resample a 4-vertex square down to 8 vertices — should still be
        // roughly square.
        let square = vec![(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)];
        let resampled = resample_arclength(&square, 8);
        assert_eq!(resampled.len(), 8);
        // All vertices should be inside [0, 1]² bbox.
        for &(x, y) in &resampled {
            assert!((0.0..=1.0).contains(&x));
            assert!((0.0..=1.0).contains(&y));
        }
    }

    #[test]
    fn boolean_within_envelope() {
        for seed in 0..20u32 {
            let c = ctx(seed);
            let mut rng = Rng::for_stage(seed as u64, b"caller");
            let polys = BooleanGenerator.generate(&c, &mut rng).polygons;
            for &(x, y) in &polys[0] {
                let dx = (x - c.center.0).abs();
                let dy = (y - c.center.1).abs();
                assert!(
                    dx <= c.envelope.0 * 1.05 && dy <= c.envelope.1 * 1.05,
                    "seed {seed}: vertex ({x}, {y}) outside envelope"
                );
            }
        }
    }

    #[test]
    fn boolean_within_envelope_under_production_conditions() {
        for seed in 0..30u32 {
            let c = ctx_production(seed);
            let mut rng = Rng::for_stage(seed as u64, b"caller");
            let polys = BooleanGenerator.generate(&c, &mut rng).polygons;
            for &(x, y) in &polys[0] {
                let dx = (x - c.center.0).abs();
                let dy = (y - c.center.1).abs();
                assert!(
                    dx <= c.envelope.0 * 1.05 && dy <= c.envelope.1 * 1.05,
                    "seed {seed}: production-condition vertex ({x}, {y}) outside envelope"
                );
            }
        }
    }

    #[test]
    fn boolean_effective_kind_is_boolean_on_happy_path() {
        // Healthy clipper operations should report Boolean, not the
        // Ellipse downgrade. (Fallback to Ellipse on geo-clipper failure
        // is tested implicitly — degenerate inputs are hard to construct
        // without mocking the FFI, so the happy-path assertion suffices.)
        for seed in 0..20u32 {
            let c = ctx(seed);
            let mut rng = Rng::for_stage(seed as u64, b"caller");
            let result = BooleanGenerator.generate(&c, &mut rng);
            assert_eq!(
                result.effective_kind,
                ShapeKind::Boolean,
                "seed {seed}: happy-path Boolean should not downgrade"
            );
        }
    }
}
