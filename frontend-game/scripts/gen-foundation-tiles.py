"""Generate flat seamless foundation tiles for the V1 tilemap viewer.

10 terrains × 1 tile each, 256×256 PNG. Algorithm:
  1. FFT-low-passed white noise → guaranteed tileable organic texture
  2. Per-terrain base RGB palette
  3. Two noise layers (low-freq tonal sweep, mid-freq grain) modulate luminance
  4. Per-terrain "specials": water ripple, snow sparkle, mountain crack,
     swamp puddle hint, road compaction streaks, forest dapple, sand wind ripple

Outputs to frontend-game/public/assets/tiles/homm3-placeholder/<tag>.png,
overwriting AI-generated placeholders.

Run:
  python frontend-game/scripts/gen-foundation-tiles.py

Output is deterministic per seed; default SEED_BASE=2026 produces a fixed
set. Re-run with a different SEED_BASE to refresh the look.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

import numpy as np
from PIL import Image

SIZE: Final = 256
OUT_DIR: Final = Path(__file__).resolve().parents[1] / "public" / "assets" / "tiles" / "homm3-placeholder"
SEED_BASE: Final = 2026

# Per-terrain palette: base RGB + (low_freq_amp, mid_freq_amp) for noise
# modulation. Amplitudes are fractions of base; 0.15 = ±15% luminance.
TERRAINS: Final = {
    "grass":        ((0x5C, 0x8A, 0x3E), (0.18, 0.10)),
    "forest":       ((0x3D, 0x5C, 0x2E), (0.20, 0.12)),
    "mountain":     ((0x7A, 0x72, 0x68), (0.15, 0.18)),
    "water":        ((0x2E, 0x5C, 0x8A), (0.12, 0.05)),
    "sand":         ((0xC9, 0xA9, 0x61), (0.14, 0.08)),
    "snow":         ((0xDD, 0xE8, 0xEC), (0.06, 0.04)),
    "swamp":        ((0x4D, 0x5C, 0x3D), (0.22, 0.12)),
    "road":         ((0x8A, 0x6E, 0x4B), (0.14, 0.10)),
    "rough":        ((0x8C, 0x75, 0x48), (0.20, 0.14)),
    "subterranean": ((0x2A, 0x26, 0x30), (0.10, 0.16)),
}


def tileable_noise(size: int, freq_sigma: float, seed: int) -> np.ndarray:
    """Generate a seamless 2D noise field, normalized to [0, 1].

    Strategy: FFT a white-noise field, multiply spectrum by a Gaussian
    band-pass centered at DC, then IFFT. The discrete FFT treats the
    input as periodic so the IFFT output tiles seamlessly. `freq_sigma`
    controls the cutoff — smaller = lower freq = broader patches.
    """
    rng = np.random.default_rng(seed)
    spec = rng.standard_normal((size, size))
    f = np.fft.fft2(spec)
    yy, xx = np.indices((size, size))
    # Build a tileable radial frequency map (distance from any corner,
    # wrapping at the edges).
    yc = np.minimum(yy, size - yy)
    xc = np.minimum(xx, size - xx)
    radial = np.sqrt(xc**2 + yc**2)
    mask = np.exp(-(radial / freq_sigma) ** 2)
    out = np.real(np.fft.ifft2(f * mask))
    lo, hi = out.min(), out.max()
    return (out - lo) / (hi - lo + 1e-9)


def voronoi_cracks(size: int, n_points: int, seed: int) -> np.ndarray:
    """Cheap Voronoi distance field for mountain-style crack lines.

    Returns a [0, 1] field where 1 is the cell edge (between two
    nearest points) and 0 is the cell interior. Tileable via toroidal
    distance metric.
    """
    rng = np.random.default_rng(seed)
    pts = rng.random((n_points, 2)) * size
    yy, xx = np.indices((size, size))
    # Toroidal distance to each point
    dxs = np.abs(xx[:, :, None] - pts[None, None, :, 0])
    dys = np.abs(yy[:, :, None] - pts[None, None, :, 1])
    dxs = np.minimum(dxs, size - dxs)
    dys = np.minimum(dys, size - dys)
    d = np.sqrt(dxs**2 + dys**2)
    sorted_d = np.sort(d, axis=2)
    edge = sorted_d[:, :, 1] - sorted_d[:, :, 0]
    # invert + threshold so edges (small diff between nearest two) are bright
    edge_norm = 1.0 - edge / (edge.max() + 1e-9)
    return edge_norm**2


def base_tile(base_rgb, low_amp: float, mid_amp: float, seed: int) -> np.ndarray:
    """Common foundation: base color modulated by two noise layers."""
    low = tileable_noise(SIZE, freq_sigma=12, seed=seed) - 0.5  # [-0.5, 0.5]
    mid = tileable_noise(SIZE, freq_sigma=48, seed=seed + 1) - 0.5
    lum = 1.0 + low * 2 * low_amp + mid * 2 * mid_amp  # ±low_amp ±mid_amp
    lum = np.clip(lum, 0.55, 1.45)
    base = np.array(base_rgb, dtype=np.float32) / 255.0
    rgb = base[None, None, :] * lum[:, :, None]
    return np.clip(rgb, 0, 1)


def add_water_ripple(rgb: np.ndarray, seed: int) -> np.ndarray:
    """Gentle sinusoidal ripple highlights for water."""
    yy, xx = np.indices((SIZE, SIZE))
    angle = np.deg2rad(20 + (seed % 60))
    proj = np.cos(angle) * xx + np.sin(angle) * yy
    ripple = 0.08 * np.sin(proj * 2 * np.pi / 40)  # 40 px wavelength
    extra = tileable_noise(SIZE, freq_sigma=32, seed=seed + 7) - 0.5
    ripple += extra * 0.06
    rgb = rgb * (1.0 + ripple[:, :, None])
    return np.clip(rgb, 0, 1)


def add_snow_sparkle(rgb: np.ndarray, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed + 11)
    sparkle = rng.random((SIZE, SIZE)) > 0.998
    rgb = rgb.copy()
    rgb[sparkle] = np.minimum(rgb[sparkle] + 0.15, 1.0)
    return rgb


def add_mountain_cracks(rgb: np.ndarray, seed: int) -> np.ndarray:
    cracks = voronoi_cracks(SIZE, n_points=18, seed=seed + 13)
    # Darken near edges
    darken = 1.0 - cracks * 0.45
    return np.clip(rgb * darken[:, :, None], 0, 1)


def add_swamp_puddles(rgb: np.ndarray, seed: int) -> np.ndarray:
    puddles = tileable_noise(SIZE, freq_sigma=8, seed=seed + 17)
    puddle_mask = (puddles > 0.62).astype(np.float32) * 0.4
    # Slight green-blue tint where puddles
    rgb = rgb.copy()
    rgb[..., 0] *= (1 - puddle_mask)
    rgb[..., 1] *= (1 - puddle_mask * 0.5)
    rgb[..., 2] *= (1 + puddle_mask * 0.2)
    return np.clip(rgb, 0, 1)


def add_road_compaction(rgb: np.ndarray, seed: int) -> np.ndarray:
    """Faint linear streaks suggesting compacted travel direction."""
    yy = np.indices((SIZE, SIZE))[0]
    streak = 0.06 * np.sin(yy * 2 * np.pi / 24 + (seed % 8))
    rgb = rgb * (1.0 + streak[:, :, None])
    return np.clip(rgb, 0, 1)


def add_subterranean_vein(rgb: np.ndarray, seed: int) -> np.ndarray:
    """Faint mineral vein streaks via thresholded noise gradient."""
    n = tileable_noise(SIZE, freq_sigma=14, seed=seed + 19)
    # Edges of noise patches = veins
    gy = np.abs(np.gradient(n, axis=0))
    gx = np.abs(np.gradient(n, axis=1))
    veins = np.clip((gy + gx) * 12, 0, 1)
    glow = veins * 0.35
    rgb = rgb.copy()
    rgb[..., 0] += glow * 0.15  # faint warm hint
    rgb[..., 1] += glow * 0.10
    rgb[..., 2] += glow * 0.05
    return np.clip(rgb, 0, 1)


def add_forest_dapple(rgb: np.ndarray, seed: int) -> np.ndarray:
    dapple = tileable_noise(SIZE, freq_sigma=20, seed=seed + 23) - 0.5
    return np.clip(rgb * (1.0 + dapple[:, :, None] * 0.18), 0, 1)


def add_sand_wind(rgb: np.ndarray, seed: int) -> np.ndarray:
    """Soft directional ripple suggesting wind."""
    yy, xx = np.indices((SIZE, SIZE))
    angle = np.deg2rad(35 + (seed % 30))
    proj = np.cos(angle) * xx + np.sin(angle) * yy
    ripple = 0.05 * np.sin(proj * 2 * np.pi / 28)
    n = tileable_noise(SIZE, freq_sigma=22, seed=seed + 29) - 0.5
    return np.clip(rgb * (1.0 + ripple[:, :, None] + n[:, :, None] * 0.08), 0, 1)


def add_rough_tufts(rgb: np.ndarray, seed: int) -> np.ndarray:
    """Small darker patches suggesting tussock grass clumps."""
    tufts = tileable_noise(SIZE, freq_sigma=64, seed=seed + 31)
    tuft_mask = (tufts > 0.66).astype(np.float32)
    # Darken + shift toward green
    rgb = rgb.copy()
    rgb[..., 0] *= (1 - tuft_mask * 0.18)
    rgb[..., 1] *= (1 - tuft_mask * 0.08)
    rgb[..., 2] *= (1 - tuft_mask * 0.22)
    return np.clip(rgb, 0, 1)


SPECIALS = {
    "water": add_water_ripple,
    "snow": add_snow_sparkle,
    "mountain": add_mountain_cracks,
    "swamp": add_swamp_puddles,
    "road": add_road_compaction,
    "subterranean": add_subterranean_vein,
    "forest": add_forest_dapple,
    "sand": add_sand_wind,
    "rough": add_rough_tufts,
}


def gen_one(tag: str, idx: int) -> Path:
    base_rgb, (low_amp, mid_amp) = TERRAINS[tag]
    seed = SEED_BASE + idx * 1000
    rgb = base_tile(base_rgb, low_amp, mid_amp, seed)
    special = SPECIALS.get(tag)
    if special is not None:
        rgb = special(rgb, seed)
    img8 = (rgb * 255).astype(np.uint8)
    img = Image.fromarray(img8, mode="RGB")
    out = OUT_DIR / f"{tag}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG", optimize=True)
    return out


def main() -> None:
    print(f"out dir: {OUT_DIR}")
    total = 0
    for i, tag in enumerate(TERRAINS):
        out = gen_one(tag, i)
        sz = os.path.getsize(out)
        total += sz
        print(f"  {tag}: {sz//1024} KB")
    print(f"\n10 terrains, {total//1024} KB total")


if __name__ == "__main__":
    main()
