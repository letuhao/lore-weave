//! Map projections — translate a unit-sphere point to a `(u, v) ∈ [0, 1]²`
//! image canvas coordinate (and back). Two variants ship in Phase 1 stage B:
//!
//! - [`Projection::Equirectangular`] — plate-carrée; the canonical flat
//!   world map. `u = (lon + π) / 2π`, `v = (π/2 − lat) / π`. 2:1 aspect.
//! - [`Projection::Orthographic`] — a unit-disc globe view. Hemisphere
//!   visible from `camera`; the far side projects to `None`.
//!
//! Used by [`crate::render`] and [`crate::relief`] to compose images, and by
//! the CLI's `--projection` flag. **Rendering is *not* part of `WorldMap`
//! or `content_hash`** — projections are a presentation concern.

use std::f32::consts::{FRAC_PI_2, PI, TAU};

use serde::{Deserialize, Serialize};

/// How a unit-sphere point is mapped to a 2D image canvas.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize, Default)]
pub enum Projection {
    /// Equirectangular (plate-carrée). The default. `u = (lon + π) / 2π`,
    /// `v = (π/2 − lat) / π`. Renders to a 2:1 aspect rectangle.
    #[default]
    Equirectangular,
    /// Orthographic — "globe view." The sphere is projected onto the
    /// tangent plane at the *anti-camera* direction; only the hemisphere
    /// facing `camera` is visible (the far side projects to `None`).
    /// `camera` is a unit vector pointing from the world centre toward the
    /// viewer's eye; e.g. `[1, 0, 0]` looks at lat=0, lon=0.
    Orthographic { camera: [f32; 3] },
}

impl Projection {
    /// Project a unit-sphere point to an image-canvas coordinate `(u, v) ∈
    /// [0, 1]²`. **Equirectangular** always succeeds. **Orthographic**
    /// returns `None` for points on the far hemisphere (`p · camera < 0`).
    pub fn project(&self, p: [f32; 3]) -> Option<(f32, f32)> {
        match *self {
            Projection::Equirectangular => {
                let lat = p[2].clamp(-1.0, 1.0).asin();
                let lon = p[1].atan2(p[0]);
                let u = (lon + PI) / TAU;
                let v = (FRAC_PI_2 - lat) / PI;
                Some((u, v))
            }
            Projection::Orthographic { camera } => {
                let cam = normalize(camera);
                let dot = p[0] * cam[0] + p[1] * cam[1] + p[2] * cam[2];
                if dot < 0.0 {
                    return None;
                }
                let (ex, ey) = tangent_basis(cam);
                let x = p[0] * ex[0] + p[1] * ex[1] + p[2] * ex[2];
                let y = p[0] * ey[0] + p[1] * ey[1] + p[2] * ey[2];
                // x, y in [-1, 1]; map to canvas [0, 1]² with y-down so the
                // canvas row 0 is the top (north up).
                let u = (x + 1.0) * 0.5;
                let v = (1.0 - y) * 0.5;
                Some((u, v))
            }
        }
    }

    /// Inverse of [`project`]. Map an image-canvas coordinate back to a
    /// unit-sphere point. **Equirectangular** always succeeds. **Orthographic**
    /// returns `None` for canvas points outside the unit disc.
    pub fn back_project(&self, uv: (f32, f32)) -> Option<[f32; 3]> {
        match *self {
            Projection::Equirectangular => {
                let (u, v) = uv;
                let lon = u * TAU - PI;
                let lat = FRAC_PI_2 - v * PI;
                Some([lat.cos() * lon.cos(), lat.cos() * lon.sin(), lat.sin()])
            }
            Projection::Orthographic { camera } => {
                let cam = normalize(camera);
                let (u, v) = uv;
                // canvas → tangent-plane (x, y) ∈ [-1, 1].
                let x = u * 2.0 - 1.0;
                let y = 1.0 - v * 2.0;
                let r2 = x * x + y * y;
                if r2 > 1.0 {
                    return None;
                }
                let z = (1.0 - r2).max(0.0).sqrt();
                let (ex, ey) = tangent_basis(cam);
                let p = [
                    ex[0] * x + ey[0] * y + cam[0] * z,
                    ex[1] * x + ey[1] * y + cam[1] * z,
                    ex[2] * x + ey[2] * y + cam[2] * z,
                ];
                Some(normalize(p))
            }
        }
    }

    /// Whether a unit-sphere point is visible — i.e. [`project`] returns
    /// `Some`. Convenience for renderers that want to skip hidden cells
    /// without producing the `(u, v)`.
    pub fn is_visible(&self, p: [f32; 3]) -> bool {
        match *self {
            Projection::Equirectangular => true,
            Projection::Orthographic { camera } => {
                let cam = normalize(camera);
                (p[0] * cam[0] + p[1] * cam[1] + p[2] * cam[2]) >= 0.0
            }
        }
    }

    /// The recommended canvas aspect ratio (width / height). Equirectangular
    /// is 2:1 by convention; Orthographic is 1:1 (a disc inscribed in a
    /// square).
    pub fn aspect(&self) -> f32 {
        match self {
            Projection::Equirectangular => 2.0,
            Projection::Orthographic { .. } => 1.0,
        }
    }

    /// Derive a render `(width, height)` from the world's `cell_count` so that
    /// **each cell gets roughly `detail` pixels across** — a floor on per-cell
    /// resolution. This is the cure for "the whole planet squeezed into a fixed
    /// square": the image grows with the cell count and respects the
    /// projection's aspect (2:1 for Equirectangular, 1:1 for Orthographic)
    /// instead of being a fixed square. Like cells in a body — each cell has a
    /// minimum size, so a bigger world produces a bigger image.
    ///
    /// `detail` is pixels-per-cell (linear); ~2.5 is a good default. Dimensions
    /// are clamped to `[64, 16384]` so tiny worlds aren't degenerate and huge
    /// ones stay within image limits.
    pub fn auto_dimensions(&self, cell_count: usize, detail: f32) -> (u32, u32) {
        let aspect = self.aspect();
        // Cells visible in the render: Orthographic shows ~half the sphere.
        let visible = match self {
            Projection::Orthographic { .. } => cell_count as f32 * 0.5,
            Projection::Equirectangular => cell_count as f32,
        };
        // Cells uniform in solid angle ⇒ to keep them ~square in pixels the
        // image is `aspect:1`; cells along the height axis ≈ sqrt(visible /
        // aspect). Height pixels = that × detail.
        let height_cells = (visible / aspect).max(1.0).sqrt();
        let height = (height_cells * detail).round().clamp(64.0, 16384.0);
        let width = (height * aspect).round().clamp(64.0, 16384.0);
        (width as u32, height as u32)
    }
}

/// Shortcut for [`Projection::Equirectangular`] — `(u, v)` in `[0, 1]²` for
/// any unit-sphere point. Used by render code paths that haven't yet been
/// parametrized over [`Projection`]; equirectangular always succeeds, so
/// `.expect` is appropriate.
pub fn equirectangular(p: [f32; 3]) -> (f32, f32) {
    Projection::Equirectangular
        .project(p)
        .expect("equirectangular projects every unit-sphere point")
}

// --- helpers ---------------------------------------------------------------

fn normalize(v: [f32; 3]) -> [f32; 3] {
    let len = (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]).sqrt();
    if len > 0.0 {
        [v[0] / len, v[1] / len, v[2] / len]
    } else {
        [0.0, 0.0, 1.0]
    }
}

/// Orthonormal tangent basis `(ex, ey)` at unit-sphere point `c`. Picks the
/// helper axis least-aligned with `c` so the cross product is well
/// conditioned even at the poles.
fn tangent_basis(c: [f32; 3]) -> ([f32; 3], [f32; 3]) {
    let helper = if c[0].abs() <= c[1].abs() && c[0].abs() <= c[2].abs() {
        [1.0, 0.0, 0.0]
    } else if c[1].abs() <= c[2].abs() {
        [0.0, 1.0, 0.0]
    } else {
        [0.0, 0.0, 1.0]
    };
    let ex = normalize(cross(c, helper));
    let ey = cross(c, ex);
    (ex, ey)
}

fn cross(a: [f32; 3], b: [f32; 3]) -> [f32; 3] {
    [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]
}

#[cfg(test)]
mod tests {
    use super::*;

    fn unit(x: f32, y: f32, z: f32) -> [f32; 3] {
        normalize([x, y, z])
    }

    #[test]
    fn equirectangular_projects_north_pole_to_top_centre() {
        let p = unit(0.0, 0.0, 1.0);
        let (u, v) = Projection::Equirectangular.project(p).unwrap();
        assert!((u - 0.5).abs() < 1e-4, "u for north pole = {u}");
        assert!(v.abs() < 1e-4, "v for north pole = {v}");
    }

    #[test]
    fn equirectangular_projects_south_pole_to_bottom_centre() {
        let p = unit(0.0, 0.0, -1.0);
        let (u, v) = Projection::Equirectangular.project(p).unwrap();
        assert!((u - 0.5).abs() < 1e-4);
        assert!((v - 1.0).abs() < 1e-4);
    }

    #[test]
    fn equirectangular_is_a_round_trip() {
        // Sample a sphere lattice; project + back_project should land at the
        // same point within a small float tolerance.
        for lat_step in -8..=8 {
            for lon_step in -16..=16 {
                let lat = lat_step as f32 * 0.1;
                let lon = lon_step as f32 * 0.18;
                let p = unit(lat.cos() * lon.cos(), lat.cos() * lon.sin(), lat.sin());
                let uv = Projection::Equirectangular.project(p).unwrap();
                let back = Projection::Equirectangular.back_project(uv).unwrap();
                for k in 0..3 {
                    assert!(
                        (p[k] - back[k]).abs() < 1e-3,
                        "equirectangular round-trip drift at lat {lat} lon {lon}: {p:?} → {back:?}"
                    );
                }
            }
        }
    }

    #[test]
    fn orthographic_hides_the_far_hemisphere() {
        let cam = unit(1.0, 0.0, 0.0);
        let proj = Projection::Orthographic { camera: cam };
        // A point exactly on the anti-camera side projects to None.
        assert_eq!(proj.project(unit(-1.0, 0.0, 0.0)), None);
        // A point on the camera side projects to canvas centre.
        let (u, v) = proj.project(unit(1.0, 0.0, 0.0)).unwrap();
        assert!((u - 0.5).abs() < 1e-4);
        assert!((v - 0.5).abs() < 1e-4);
    }

    #[test]
    fn orthographic_back_projects_outside_disc_to_none() {
        let proj = Projection::Orthographic {
            camera: unit(1.0, 0.0, 0.0),
        };
        // Canvas corner (0,0): x=-1, y=1, r²=2 — outside the disc.
        assert_eq!(proj.back_project((0.0, 0.0)), None);
        // Canvas centre (0.5, 0.5): r=0, on the camera direction.
        let p = proj.back_project((0.5, 0.5)).unwrap();
        // Should be ~(1, 0, 0) — the camera direction.
        assert!((p[0] - 1.0).abs() < 1e-3);
        assert!(p[1].abs() < 1e-3);
        assert!(p[2].abs() < 1e-3);
    }

    #[test]
    fn orthographic_is_a_round_trip_on_visible_hemisphere() {
        let proj = Projection::Orthographic {
            camera: unit(1.0, 0.0, 0.0),
        };
        for theta_step in -6..=6 {
            for phi_step in -6..=6 {
                let theta = theta_step as f32 * 0.15;
                let phi = phi_step as f32 * 0.18;
                let p = unit(theta.cos() * phi.cos(), theta.cos() * phi.sin(), theta.sin());
                if let Some(uv) = proj.project(p) {
                    let back = proj.back_project(uv).unwrap();
                    for k in 0..3 {
                        assert!(
                            (p[k] - back[k]).abs() < 1e-3,
                            "orthographic round-trip drift at θ {theta} φ {phi}: {p:?} → {back:?}"
                        );
                    }
                }
            }
        }
    }

    #[test]
    fn orthographic_disc_covers_half_the_sphere() {
        let proj = Projection::Orthographic {
            camera: unit(1.0, 0.0, 0.0),
        };
        let mut visible = 0;
        let mut hidden = 0;
        for theta_step in -10..=10 {
            for phi_step in -20..=20 {
                let theta = theta_step as f32 * 0.15;
                let phi = phi_step as f32 * 0.15;
                let p = unit(theta.cos() * phi.cos(), theta.cos() * phi.sin(), theta.sin());
                if proj.is_visible(p) {
                    visible += 1;
                } else {
                    hidden += 1;
                }
            }
        }
        // Roughly half visible (within 5%; the sampling is not exactly
        // uniform on the sphere).
        let total = visible + hidden;
        let ratio = visible as f32 / total as f32;
        assert!(
            (0.45..=0.55).contains(&ratio),
            "orthographic visibility ratio out of band: {ratio} ({visible}/{total})"
        );
    }

    #[test]
    fn orthographic_camera_at_pole_does_not_panic() {
        let proj = Projection::Orthographic {
            camera: [0.0, 0.0, 1.0],
        };
        // Tangent basis at the pole is non-degenerate (helper axis swap).
        let p = unit(0.0, 0.0, 1.0); // looking right at the camera direction
        let (u, v) = proj.project(p).unwrap();
        assert!((u - 0.5).abs() < 1e-4 && (v - 0.5).abs() < 1e-4);
    }

    #[test]
    fn aspect_ratio_matches_canvas() {
        assert!((Projection::Equirectangular.aspect() - 2.0).abs() < 1e-6);
        assert!(
            (Projection::Orthographic {
                camera: [1.0, 0.0, 0.0]
            }
            .aspect()
                - 1.0)
                .abs()
                < 1e-6
        );
    }

    #[test]
    fn default_is_equirectangular() {
        assert_eq!(Projection::default(), Projection::Equirectangular);
    }
}
