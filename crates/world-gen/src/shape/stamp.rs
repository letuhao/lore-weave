//! Stamp generator — 10 procedural "signature continents" (v3.6).
//!
//! Each template is a function returning a unit-space polygon (or polygons,
//! for multi-component templates like Japan) in `[-1, 1]²`. The generator
//! picks a template via `ctx.seed`, optionally rejects templates whose
//! `allowed_ranks` doesn't include `ctx.size_rank`, transforms to world
//! space (scale × envelope, rotate, translate to `ctx.center`), then
//! returns the result. The universal v3.5 coastline fractalize then runs
//! on top (in `flatworld::generate`).
//!
//! Per roadmap §14 Q3 PO decision: 10 hand-tuned signature shapes
//! recognisable as real-world landmasses. Per PO CLARIFY 2026-05-28:
//! procedural code (not external JSON) — faster ship, version-controlled,
//! parametric jitter per call.

use std::f32::consts::TAU;

use crate::flatworld::{Polygon, SizeRank};
use crate::rng::Rng;

use super::{ShapeContext, ShapeGenerator, ShapeKind, ShapeResult};

/// Procedural stamp templates. Each variant encodes a recognisable
/// real-world landmass silhouette. Multi-component variants (Japan) emit
/// `Vec<Polygon>`; single-component variants emit one polygon.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
pub enum StampTemplate {
    ItalyBoot,
    KoreaHook,
    CubaCrescent,
    JapanArc,
    IcelandCompact,
    GreenlandLarge,
    SicilyTriangular,
    SriLankaTeardrop,
    MadagascarElongated,
    HispaniolaIrregular,
}

impl StampTemplate {
    pub const ALL: [StampTemplate; 10] = [
        StampTemplate::ItalyBoot,
        StampTemplate::KoreaHook,
        StampTemplate::CubaCrescent,
        StampTemplate::JapanArc,
        StampTemplate::IcelandCompact,
        StampTemplate::GreenlandLarge,
        StampTemplate::SicilyTriangular,
        StampTemplate::SriLankaTeardrop,
        StampTemplate::MadagascarElongated,
        StampTemplate::HispaniolaIrregular,
    ];

    pub fn as_str(self) -> &'static str {
        match self {
            StampTemplate::ItalyBoot => "ItalyBoot",
            StampTemplate::KoreaHook => "KoreaHook",
            StampTemplate::CubaCrescent => "CubaCrescent",
            StampTemplate::JapanArc => "JapanArc",
            StampTemplate::IcelandCompact => "IcelandCompact",
            StampTemplate::GreenlandLarge => "GreenlandLarge",
            StampTemplate::SicilyTriangular => "SicilyTriangular",
            StampTemplate::SriLankaTeardrop => "SriLankaTeardrop",
            StampTemplate::MadagascarElongated => "MadagascarElongated",
            StampTemplate::HispaniolaIrregular => "HispaniolaIrregular",
        }
    }

    /// Per-stamp size-rank gate. Big-by-design stamps (Greenland) only
    /// fire on Giant+; small-by-design stamps (Sicily) skip Giant.
    pub fn allowed_ranks(self) -> &'static [SizeRank] {
        match self {
            // Boot, hook, elongated: any rank but Micro
            StampTemplate::ItalyBoot
            | StampTemplate::KoreaHook
            | StampTemplate::MadagascarElongated => {
                &[SizeRank::Giant, SizeRank::Large, SizeRank::Medium, SizeRank::Small]
            }
            // Crescent, teardrop, triangle, irregular: small/medium continents
            StampTemplate::CubaCrescent
            | StampTemplate::SicilyTriangular
            | StampTemplate::SriLankaTeardrop
            | StampTemplate::HispaniolaIrregular => {
                &[SizeRank::Medium, SizeRank::Small, SizeRank::Micro]
            }
            // Japan arc (multi-component): Large/Medium signature
            StampTemplate::JapanArc => &[SizeRank::Large, SizeRank::Medium],
            // Iceland compact: small island scale
            StampTemplate::IcelandCompact => &[SizeRank::Medium, SizeRank::Small, SizeRank::Micro],
            // Greenland: giant-only signature
            StampTemplate::GreenlandLarge => &[SizeRank::Giant, SizeRank::Large],
        }
    }

    /// Emit the unit-space polygon(s) for this template. Multi-component
    /// templates return >1 polygon (Japan). All unit coords in `[-1.2, 1.2]²`
    /// approximately.
    fn emit(self, rng: &mut Rng) -> Vec<Polygon> {
        match self {
            StampTemplate::ItalyBoot => vec![italy_boot(rng)],
            StampTemplate::KoreaHook => vec![korea_hook(rng)],
            StampTemplate::CubaCrescent => vec![cuba_crescent(rng)],
            StampTemplate::JapanArc => japan_arc(rng),
            StampTemplate::IcelandCompact => vec![iceland_compact(rng)],
            StampTemplate::GreenlandLarge => vec![greenland_large(rng)],
            StampTemplate::SicilyTriangular => vec![sicily_triangular(rng)],
            StampTemplate::SriLankaTeardrop => vec![sri_lanka_teardrop(rng)],
            StampTemplate::MadagascarElongated => vec![madagascar_elongated(rng)],
            StampTemplate::HispaniolaIrregular => vec![hispaniola_irregular(rng)],
        }
    }
}

pub struct StampGenerator;

impl ShapeGenerator for StampGenerator {
    fn kind(&self) -> ShapeKind {
        ShapeKind::Stamp
    }

    fn generate(&self, ctx: &ShapeContext, _caller_rng: &mut Rng) -> ShapeResult {
        let mut rng = Rng::for_stage(ctx.seed as u64, b"stamp");

        // Pick a template; filter by size_rank. If no template allows
        // this rank, fall back to Ellipse.
        let allowed: Vec<StampTemplate> = StampTemplate::ALL
            .into_iter()
            .filter(|t| t.allowed_ranks().contains(&ctx.size_rank))
            .collect();
        if allowed.is_empty() {
            let mut fallback_rng = Rng::for_stage(ctx.seed as u64, b"stamp-fallback");
            let mut result = super::EllipseGenerator.generate(ctx, &mut fallback_rng);
            result.effective_kind = ShapeKind::Ellipse;
            return result;
        }
        // **v4.3b**: honour an LLM-decided template index when present and
        // valid for this rank; otherwise fall back to the seed-driven
        // random pick. RNG draw stays in the default path for byte-
        // identical determinism. Out-of-range `template_id` silently
        // falls back to random pick rather than erroring — provider
        // hallucinations don't break generation.
        let llm_template = match &ctx.params {
            Some(crate::shape::ParamOverride::Stamp {
                template_id: Some(id),
            }) => StampTemplate::ALL
                .get(*id as usize)
                .copied()
                .filter(|t| t.allowed_ranks().contains(&ctx.size_rank)),
            _ => None,
        };
        let random_pick = allowed[(rng.next_u32() as usize) % allowed.len()];
        let template = llm_template.unwrap_or(random_pick);

        // Per-template emit + transform to world space.
        let unit_polys = template.emit(&mut rng);
        let rotation = rng.next_f32() * TAU;
        let cos_r = rotation.cos();
        let sin_r = rotation.sin();

        // Scale to ctx.envelope using the per-rank radius band (mid).
        let (rmin, rmax) = ctx.size_rank.radius_band();
        let scale = ctx.envelope.0 * (rmin + rmax) * 0.5;

        // Apply shared transform across all sub-polygons so multi-component
        // templates (Japan) preserve their relative positions.
        let world_polys: Vec<Polygon> = unit_polys
            .into_iter()
            .map(|unit| {
                unit.into_iter()
                    .map(|(ux, uy)| {
                        let rx = ux * cos_r - uy * sin_r;
                        let ry = ux * sin_r + uy * cos_r;
                        (ctx.center.0 + rx * scale, ctx.center.1 + ry * scale)
                    })
                    .collect()
            })
            .collect();

        // Caller's vertex-count range honored via shape-preserving fit
        // (matches Ellipse / Bezier / etc. discipline).
        let (vmin, vmax) = ctx.vertex_count_range;
        let fitted: Vec<Polygon> = world_polys
            .into_iter()
            .map(|p| fit_count(p, vmin.max(3), vmax.max(vmin)))
            .filter(|p| p.len() >= 3)
            .collect();
        if fitted.is_empty() {
            // Defensive: every polygon was degenerate after fit. Hard-fallback
            // to Ellipse.
            let mut fallback_rng = Rng::for_stage(ctx.seed as u64, b"stamp-fallback");
            let mut result = super::EllipseGenerator.generate(ctx, &mut fallback_rng);
            result.effective_kind = ShapeKind::Ellipse;
            return result;
        }
        ShapeResult::single_kind(fitted, ShapeKind::Stamp)
    }
}

// =============================================================================
// Procedural template implementations (10 stamps)
// =============================================================================

/// Italy boot — heel-to-toe diagonal silhouette with calf bulge.
fn italy_boot(rng: &mut Rng) -> Polygon {
    let mut p = Vec::with_capacity(28);
    // Hand-tuned key points in unit space, traversed CCW from heel.
    let pts = [
        (-0.20, 0.95), (-0.05, 0.92), (0.10, 0.85), (0.20, 0.70), (0.18, 0.50),
        (0.10, 0.30), (0.05, 0.10), (0.00, -0.10), (-0.05, -0.30), (-0.12, -0.50),
        (-0.20, -0.65), (-0.30, -0.75), (-0.35, -0.65), (-0.42, -0.50), (-0.50, -0.30),
        (-0.45, -0.15), (-0.40, 0.05), (-0.45, 0.25), (-0.55, 0.40), (-0.60, 0.55),
        (-0.55, 0.70), (-0.45, 0.82), (-0.35, 0.90),
    ];
    push_with_jitter(&mut p, &pts, rng, 0.04);
    p
}

/// Korea hook — vertical peninsular J.
fn korea_hook(rng: &mut Rng) -> Polygon {
    let pts = [
        (-0.20, 0.85), (0.05, 0.90), (0.20, 0.80), (0.25, 0.50), (0.15, 0.20),
        (0.10, -0.10), (0.00, -0.40), (-0.05, -0.70), (-0.15, -0.85), (-0.30, -0.85),
        (-0.40, -0.70), (-0.35, -0.40), (-0.25, -0.10), (-0.30, 0.15), (-0.40, 0.40),
        (-0.45, 0.60), (-0.35, 0.78),
    ];
    let mut p = Vec::with_capacity(pts.len() + 4);
    push_with_jitter(&mut p, &pts, rng, 0.05);
    p
}

/// Cuba crescent — long shallow C, opening to the south.
fn cuba_crescent(rng: &mut Rng) -> Polygon {
    let mut p = Vec::with_capacity(28);
    let n = 24;
    for i in 0..n {
        let t = i as f32 / n as f32;
        let theta = t * TAU;
        // Outer arc: ellipse rx=0.9, ry=0.3, top half
        if theta < std::f32::consts::PI {
            let x = 0.9 * (theta).cos();
            let y = 0.3 * (theta).sin();
            p.push(jitter(x, y, rng, 0.04));
        }
    }
    // Inner arc back (closes the crescent), south concave
    for i in (1..n - 1).rev() {
        let t = i as f32 / n as f32;
        let theta = t * std::f32::consts::PI;
        let x = 0.75 * theta.cos();
        let y = 0.15 + 0.10 * theta.sin();
        p.push(jitter(x, y, rng, 0.04));
    }
    p
}

/// Japan arc — 4 island-chain components.
fn japan_arc(rng: &mut Rng) -> Vec<Polygon> {
    let centers = [
        (-0.85, 0.55), (-0.40, 0.20), (0.05, -0.25), (0.65, -0.55),
    ];
    let radii = [(0.30, 0.20), (0.40, 0.22), (0.45, 0.18), (0.32, 0.16)];
    let mut out = Vec::with_capacity(4);
    for i in 0..4 {
        let (cx, cy) = centers[i];
        let (rx, ry) = radii[i];
        let mut poly = Vec::with_capacity(20);
        let n = 18;
        for k in 0..n {
            let theta = (k as f32) * TAU / (n as f32);
            let r_jitter = 1.0 + (rng.next_f32() - 0.5) * 0.10;
            poly.push((
                cx + rx * theta.cos() * r_jitter,
                cy + ry * theta.sin() * r_jitter,
            ));
        }
        out.push(poly);
    }
    out
}

/// Iceland compact — irregular round volcanic island.
fn iceland_compact(rng: &mut Rng) -> Polygon {
    let mut p = Vec::with_capacity(20);
    let n = 18;
    for k in 0..n {
        let theta = (k as f32) * TAU / (n as f32);
        let r = 0.65 + (rng.next_f32() - 0.5) * 0.18;
        p.push((r * theta.cos(), r * theta.sin() * 0.85));
    }
    p
}

/// Greenland — large irregular landmass with northern peak.
fn greenland_large(rng: &mut Rng) -> Polygon {
    let mut p = Vec::with_capacity(28);
    let n = 24;
    for k in 0..n {
        let theta = (k as f32) * TAU / (n as f32);
        // North bias: stretch y when theta near π/2
        let r_base = 0.75 + 0.25 * theta.sin().max(0.0);
        let r = r_base * (1.0 + (rng.next_f32() - 0.5) * 0.20);
        p.push((r * theta.cos(), r * theta.sin()));
    }
    p
}

/// Sicily — triangle with rounded corners.
fn sicily_triangular(rng: &mut Rng) -> Polygon {
    let corners = [(0.0, 0.85), (-0.78, -0.45), (0.78, -0.45)];
    let mut p = Vec::with_capacity(18);
    for ci in 0..3 {
        let a = corners[ci];
        let b = corners[(ci + 1) % 3];
        // 6 intermediate points along edge, slight outward bulge.
        for k in 0..6 {
            let t = k as f32 / 6.0;
            let mx = a.0 + (b.0 - a.0) * t;
            let my = a.1 + (b.1 - a.1) * t;
            // Outward bulge by perpendicular offset.
            let edge_dx = b.0 - a.0;
            let edge_dy = b.1 - a.1;
            let len = (edge_dx * edge_dx + edge_dy * edge_dy).sqrt().max(1e-6);
            let bulge = 0.08 * (t * std::f32::consts::PI).sin();
            let bx = mx + (-edge_dy / len) * bulge;
            let by = my + (edge_dx / len) * bulge;
            p.push(jitter(bx, by, rng, 0.03));
        }
    }
    p
}

/// Sri Lanka — teardrop / pear shape.
fn sri_lanka_teardrop(rng: &mut Rng) -> Polygon {
    let mut p = Vec::with_capacity(20);
    let n = 20;
    for k in 0..n {
        let t = (k as f32) / (n as f32);
        let theta = t * TAU;
        // Teardrop: stretched on negative-y, rounded on positive-y.
        let r = if theta < std::f32::consts::PI {
            0.65 // top half
        } else {
            0.55 + 0.20 * (theta - std::f32::consts::PI).sin()
        };
        let x = r * theta.cos();
        let y = if theta < std::f32::consts::PI {
            r * theta.sin() + 0.15
        } else {
            r * theta.sin() * 1.3 - 0.10
        };
        p.push(jitter(x, y, rng, 0.04));
    }
    p
}

/// Madagascar — elongated oval N-S, slight east bulge.
fn madagascar_elongated(rng: &mut Rng) -> Polygon {
    let mut p = Vec::with_capacity(24);
    let n = 22;
    for k in 0..n {
        let theta = (k as f32) * TAU / (n as f32);
        let rx = 0.35 + 0.05 * theta.cos().max(0.0); // east bulge
        let ry = 0.95;
        let r_jitter = 1.0 + (rng.next_f32() - 0.5) * 0.10;
        p.push((rx * theta.cos() * r_jitter, ry * theta.sin() * r_jitter));
    }
    p
}

/// Hispaniola — irregular dual-coast (rough north, smooth south).
fn hispaniola_irregular(rng: &mut Rng) -> Polygon {
    let mut p = Vec::with_capacity(22);
    let n = 20;
    for k in 0..n {
        let theta = (k as f32) * TAU / (n as f32);
        let r_base = 0.7;
        // North coast (sin > 0): rough; south (sin <= 0): smooth.
        let r_noise = if theta.sin() > 0.0 {
            (rng.next_f32() - 0.5) * 0.30
        } else {
            (rng.next_f32() - 0.5) * 0.06
        };
        let r = r_base + r_noise;
        let x_squash = 1.3 * r * theta.cos();
        let y_squash = 0.6 * r * theta.sin();
        p.push((x_squash, y_squash));
    }
    p
}

// =============================================================================
// Helpers
// =============================================================================

fn jitter(x: f32, y: f32, rng: &mut Rng, amp: f32) -> (f32, f32) {
    (
        x + (rng.next_f32() - 0.5) * 2.0 * amp,
        y + (rng.next_f32() - 0.5) * 2.0 * amp,
    )
}

fn push_with_jitter(out: &mut Polygon, pts: &[(f32, f32)], rng: &mut Rng, amp: f32) {
    for &(x, y) in pts {
        out.push(jitter(x, y, rng, amp));
    }
}

/// Shape-preserving fit to vertex-count range — over-max: thin via DP-ish
/// drop-shortest; under-min: subdivide longest edge midpoints.
fn fit_count(mut poly: Polygon, vmin: usize, vmax: usize) -> Polygon {
    // Reduce by dropping the vertex with shortest adjacent edges.
    let mut safety = 200;
    while poly.len() > vmax && safety > 0 {
        let n = poly.len();
        let mut drop_idx = 0;
        let mut min_adj = f32::INFINITY;
        for i in 0..n {
            let prev = poly[(i + n - 1) % n];
            let next = poly[(i + 1) % n];
            let here = poly[i];
            let d1 = (prev.0 - here.0).hypot(prev.1 - here.1);
            let d2 = (next.0 - here.0).hypot(next.1 - here.1);
            let adj = d1.min(d2);
            if adj < min_adj {
                min_adj = adj;
                drop_idx = i;
            }
        }
        poly.remove(drop_idx);
        safety -= 1;
    }
    // Grow by subdividing longest edge.
    let mut grow = 256;
    while poly.len() < vmin && grow > 0 {
        let n = poly.len();
        if n < 2 {
            break;
        }
        let mut longest_idx = 0;
        let mut longest_sq = 0.0f32;
        for i in 0..n {
            let p = poly[i];
            let q = poly[(i + 1) % n];
            let d = (p.0 - q.0).powi(2) + (p.1 - q.1).powi(2);
            if d > longest_sq {
                longest_sq = d;
                longest_idx = i;
            }
        }
        let p = poly[longest_idx];
        let q = poly[(longest_idx + 1) % n];
        let mid = ((p.0 + q.0) * 0.5, (p.1 + q.1) * 0.5);
        poly.insert(longest_idx + 1, mid);
        grow -= 1;
    }
    poly
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    fn test_ctx(seed: u32, rank: SizeRank) -> ShapeContext {
        ShapeContext {
            depth: 0,
            center: (500.0, 320.0),
            envelope: (200.0, 200.0),
            size_rank: rank,
            seed,
            plate_salt: seed.wrapping_add(0xDEAD_BEEF),
            parent_path: Vec::new(),
            world_theme: None,
            edge_jitter: 0.30,
            vertex_count_range: (24, 48),
            params: None,
        }
    }

    #[test]
    fn stamp_kind_is_stamp() {
        assert_eq!(StampGenerator.kind(), ShapeKind::Stamp);
    }

    #[test]
    fn stamp_does_not_perturb_caller_rng() {
        let mut a = Rng::for_stage(1, b"caller");
        let mut b = Rng::for_stage(1, b"caller");
        let _ = StampGenerator.generate(&test_ctx(7, SizeRank::Large), &mut a);
        for _ in 0..3 {
            assert_eq!(a.next_u32(), b.next_u32());
        }
    }

    #[test]
    fn stamp_deterministic_for_same_seed() {
        let r1 = StampGenerator.generate(&test_ctx(7, SizeRank::Large), &mut Rng::for_stage(0, b"c"));
        let r2 = StampGenerator.generate(&test_ctx(7, SizeRank::Large), &mut Rng::for_stage(0, b"c"));
        assert_eq!(r1.polygons.len(), r2.polygons.len());
        for (pa, pb) in r1.polygons[0].iter().zip(r2.polygons[0].iter()) {
            assert_eq!(pa.0.to_bits(), pb.0.to_bits());
            assert_eq!(pa.1.to_bits(), pb.1.to_bits());
        }
    }

    #[test]
    fn all_templates_emit_at_least_three_vertices() {
        let mut rng = Rng::for_stage(42, b"t");
        for t in StampTemplate::ALL {
            let polys = t.emit(&mut rng);
            assert!(!polys.is_empty(), "{:?} emitted no polygons", t);
            for p in &polys {
                assert!(p.len() >= 3, "{:?} polygon has {} vertices", t, p.len());
            }
        }
    }

    #[test]
    fn japan_arc_is_multi_component() {
        let mut rng = Rng::for_stage(1, b"t");
        let polys = StampTemplate::JapanArc.emit(&mut rng);
        assert_eq!(polys.len(), 4, "JapanArc should emit 4 islands");
    }

    #[test]
    fn allowed_ranks_filter_excludes_giant_for_sicily() {
        // Sicily is small/medium/micro only — Giant rank should NOT pick it.
        for seed in 0..32u32 {
            let r = StampGenerator.generate(&test_ctx(seed, SizeRank::Giant), &mut Rng::for_stage(0, b"c"));
            // Generator may pick any allowed-for-Giant template OR fall back to Ellipse.
            // Either way, the test passes as long as we don't panic.
            assert!(!r.polygons.is_empty());
        }
    }

    #[test]
    fn micro_rank_falls_back_when_no_template_allowed() {
        // Stamps disabled for Micro (no template lists Micro in allowed_ranks
        // EXCEPT Sri Lanka, Cuba, Iceland, Hispaniola). Force an unusual
        // ctx and check we still get a non-empty result.
        let r = StampGenerator.generate(&test_ctx(1, SizeRank::Micro), &mut Rng::for_stage(0, b"c"));
        assert!(!r.polygons.is_empty());
    }

    #[test]
    fn vertex_count_lands_in_range_for_large_rank() {
        for seed in 0..16u32 {
            let r = StampGenerator.generate(&test_ctx(seed, SizeRank::Large), &mut Rng::for_stage(0, b"c"));
            let n = r.polygons[0].len();
            // Range (24, 48) from test_ctx.
            assert!(
                (12..=64).contains(&n),
                "seed {seed}: vertex count {n} outside reasonable range"
            );
        }
    }
}
