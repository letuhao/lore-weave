"""Generate the V1.2 prop / overlay sprite bundle for the tilemap viewer.

Output:
    frontend-game/public/assets/sprites/<tier>/<name>.webp
    frontend-game/public/assets/sprites/marker/<name>.webp
    frontend-game/public/assets/sprites/player.webp
    frontend-game/public/assets/sprites/MANIFEST.json

Tier sizes follow the approved tier table in
`docs/specs/2026-05-24-v1-tilemap-viewer-scope-expansion.md` §1
(minimum 128 px per PO request). Sources are either:
  - HoMM3-bundle PNGs (Flux1-dev outputs, downsampled + WebP encoded)
  - Programmatic PIL drawings (markers + Player + lake/crater)

All outputs are WebP quality 85 (~50-70% smaller than PNG, supported
by all modern browsers; Phaser 4 loads identically to PNG).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw

# ── Paths ────────────────────────────────────────────────────────────
SRC_BUNDLE = Path(
    "G:/Works/local-image-generator-service/outputs/homm3-bundle/pass-full-001"
)
OUT_BASE = Path(__file__).resolve().parents[1] / "public" / "assets" / "sprites"

# ── Tier sizes (display px, then source res = 2× for crisp zoom) ─────
TIER_DISPLAY = {
    "xl": 384,
    "l": 256,
    "m": 192,
    "s": 160,
    "xs": 128,
    "marker": 128,
}
TIER_SOURCE = {tier: disp * 2 for tier, disp in TIER_DISPLAY.items()}
TIER_SOURCE["marker"] = 128  # markers programmatic; no oversample needed
PLAYER_SOURCE = 384

WEBP_QUALITY = 85

# ── Mappings: (sprite_name, tier, hOMM3 source relative path) ────────
#   relative to SRC_BUNDLE; biome defaults to grassland_temperate
HOMM3_MAP: list[tuple[str, str, str]] = [
    # Tier-XL
    ("town", "xl",
     "homm3/structures/grassland_temperate/structures/castle_quarter_wide__1536_1024__s101.png"),
    ("landmark_statue", "xl",
     "homm3/structures/grassland_temperate/structures/hero_monument_statue_tall__1024_1536__s101.png"),
    # Tier-L
    ("mine_gold", "l",
     "homm3/structures/grassland_temperate/structures/mine_gold_entrance__1024_1024__s101.png"),
    ("mine_ore", "l",
     "homm3/structures/grassland_temperate/structures/mine_ore_entrance__1024_1024__s101.png"),
    ("mine_gem", "l",
     "homm3/structures/grassland_temperate/structures/mine_gem_cavern_mouth__1024_1024__s101.png"),
    ("shrine", "l",
     "homm3/structures/grassland_temperate/structures/shrine_magic_arcane__1024_1024__s101.png"),
    ("monolith", "l",
     "homm3/structures/grassland_temperate/structures/portal_gate_stone__1024_1024__s101.png"),
    ("tower_ruin", "l",
     "homm3/structures/grassland_temperate/structures/wizard_tower_ruin__1024_1024__s101.png"),
    ("monument_obelisk", "l",
     "homm3/structures/grassland_temperate/structures/monument_obelisk__1024_1024__s101.png"),
    # Tier-M
    ("mountain_rocks", "m",
     "homm3/structures/grassland_temperate/structures/rock_pillar_obstacle__1024_1024__s101.png"),
    ("siege_tower_fragment", "m",
     "homm3/structures/grassland_temperate/structures/siege_tower_fragment_tall__1024_1536__s101.png"),
    ("palisade_fence", "m",
     "homm3/structures/grassland_temperate/structures/palisade_fence_segment__1024_1024__s101.png"),
    # Tier-S
    ("tree", "s",
     "trees/grassland_temperate/silver_birch_grove_tree__s101.png"),
    ("bush", "s",
     "homm3/bush/grassland_temperate/bush/thorn_scrub_shrub_cluster__1024_1024__s101.png"),
    ("treasure_pile", "s",
     "homm3/structures/grassland_temperate/structures/treasure_pile_prop__1024_1024__s101.png"),
    # Tier-XS
    ("decoration_boundary_stones", "xs",
     "homm3/misc/grassland_temperate/misc/boundary_stones_ring__1024_1024__s101.png"),
    ("decoration_lantern_post", "xs",
     "homm3/misc/grassland_temperate/misc/lantern_post_double__1024_1024__s101.png"),
    ("mushroom_cluster", "xs",
     "homm3/mushroom/grassland_temperate/mushroom/toadstool_ring_cluster_fantasy__1024_1024__s101.png"),
]


def fit_to_square(img: Image.Image, target: int) -> Image.Image:
    """Letterbox a non-square HoMM3 prop onto a transparent square canvas,
    preserving aspect. Some sources are 1024×1536 (tall) — we want the
    final canvas to be `target × target` with the prop centered on the
    bottom edge so foot-anchor placement (`setOrigin(0.5, 1.0)` on the
    sprite) lines up to the tile center.
    """
    img = img.convert("RGBA")
    iw, ih = img.size
    scale = min(target / iw, target / ih)
    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
    scaled = img.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGBA", (target, target), (0, 0, 0, 0))
    # Bottom-center on transparent canvas (foot anchored)
    offset = ((target - nw) // 2, target - nh)
    canvas.paste(scaled, offset, scaled)
    return canvas


def save_webp(img: Image.Image, out_path: Path) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "WEBP", quality=WEBP_QUALITY, method=6)
    return os.path.getsize(out_path)


# ── Programmatic markers (PIL drawing, 128×128 RGBA) ─────────────────
@dataclass
class Marker:
    name: str
    draw: Callable[[ImageDraw.ImageDraw], None]


def draw_skull(d: ImageDraw.ImageDraw) -> None:
    # Red skull silhouette — Monster lair
    d.ellipse((24, 24, 104, 100), fill=(220, 60, 60, 255), outline=(120, 20, 20, 255), width=3)
    d.ellipse((40, 50, 56, 70), fill=(20, 0, 0, 255))  # left eye
    d.ellipse((72, 50, 88, 70), fill=(20, 0, 0, 255))  # right eye
    d.polygon([(60, 78), (64, 90), (68, 78)], fill=(20, 0, 0, 255))  # nose
    d.rectangle((44, 96, 84, 112), fill=(220, 60, 60, 255), outline=(120, 20, 20, 255), width=2)
    for x in range(48, 84, 6):
        d.line((x, 98, x, 110), fill=(120, 20, 20, 255), width=2)


def draw_ferry(d: ImageDraw.ImageDraw) -> None:
    # Cyan boat icon
    # Hull: trapezoid
    d.polygon([(24, 76), (40, 100), (88, 100), (104, 76)],
              fill=(80, 180, 200, 255), outline=(30, 90, 110, 255))
    # Mast
    d.line((64, 76, 64, 30), fill=(80, 50, 30, 255), width=4)
    # Sail
    d.polygon([(64, 30), (96, 64), (64, 70)],
              fill=(240, 240, 230, 255), outline=(60, 50, 40, 255))
    # Water hint
    d.line((16, 108, 112, 108), fill=(60, 140, 180, 200), width=3)


def draw_lake(d: ImageDraw.ImageDraw) -> None:
    # Blue irregular pond
    d.ellipse((10, 30, 118, 100), fill=(46, 92, 138, 255), outline=(30, 70, 110, 255), width=3)
    d.ellipse((30, 44, 70, 70), fill=(80, 130, 180, 200))
    d.ellipse((78, 56, 102, 78), fill=(80, 130, 180, 180))


def draw_crater(d: ImageDraw.ImageDraw) -> None:
    # Dark ring (impact crater seen from above)
    d.ellipse((14, 14, 114, 114), fill=(80, 70, 65, 255), outline=(40, 35, 30, 255), width=2)
    d.ellipse((28, 28, 100, 100), fill=(50, 42, 38, 255))
    d.ellipse((42, 42, 86, 86), fill=(30, 25, 22, 255))


def draw_animal(d: ImageDraw.ImageDraw) -> None:
    # V2 reserve — red dot inside circle
    d.ellipse((16, 16, 112, 112), fill=(140, 40, 40, 255), outline=(70, 20, 20, 255), width=3)
    d.text((52, 52), "?", fill=(240, 200, 200, 255))


def draw_other(d: ImageDraw.ImageDraw) -> None:
    # Catch-all magenta question
    d.ellipse((16, 16, 112, 112), fill=(180, 40, 180, 255), outline=(90, 20, 90, 255), width=3)
    d.text((54, 50), "?", fill=(255, 255, 255, 255))


MARKERS: list[Marker] = [
    Marker("monster_lair", draw_skull),
    Marker("ferry", draw_ferry),
    Marker("lake", draw_lake),
    Marker("crater", draw_crater),
    Marker("animal", draw_animal),
    Marker("other", draw_other),
]


def gen_marker(m: Marker) -> Path:
    canvas = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    m.draw(d)
    out = OUT_BASE / "marker" / f"{m.name}.webp"
    save_webp(canvas, out)
    return out


# ── Player sprite (programmatic warrior silhouette, 384×384) ─────────
def gen_player() -> Path:
    canvas = Image.new("RGBA", (PLAYER_SOURCE, PLAYER_SOURCE), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    cx = PLAYER_SOURCE // 2
    # Cloak: dark teal trapezoid
    d.polygon(
        [(cx - 110, PLAYER_SOURCE - 30), (cx - 60, 180), (cx + 60, 180), (cx + 110, PLAYER_SOURCE - 30)],
        fill=(36, 92, 100, 255), outline=(20, 50, 56, 255),
    )
    # Body torso
    d.polygon(
        [(cx - 60, 180), (cx - 70, 280), (cx + 70, 280), (cx + 60, 180)],
        fill=(50, 130, 140, 255),
    )
    # Head — circle
    d.ellipse((cx - 50, 70, cx + 50, 170), fill=(220, 180, 140, 255), outline=(120, 90, 60, 255), width=3)
    # Hood ridge
    d.arc((cx - 60, 60, cx + 60, 160), 200, 340, fill=(20, 50, 56, 255), width=8)
    # Eyes
    d.ellipse((cx - 24, 100, cx - 12, 116), fill=(30, 30, 30, 255))
    d.ellipse((cx + 12, 100, cx + 24, 116), fill=(30, 30, 30, 255))
    # Sword (right hand, simple line)
    d.line((cx + 80, 220, cx + 130, 100), fill=(200, 200, 220, 255), width=10)
    d.line((cx + 60, 240, cx + 100, 200), fill=(120, 80, 30, 255), width=12)  # hilt
    # Shield (left hand)
    d.ellipse((cx - 130, 200, cx - 60, 280), fill=(160, 50, 50, 255), outline=(80, 20, 20, 255), width=4)
    out = OUT_BASE / "player.webp"
    save_webp(canvas, out)
    return out


def main() -> None:
    print(f"src bundle: {SRC_BUNDLE}")
    print(f"out base:   {OUT_BASE}")
    print()
    manifest: dict = {"tier_display_px": TIER_DISPLAY, "tier_source_px": TIER_SOURCE,
                      "webp_quality": WEBP_QUALITY, "sprites": []}
    total = 0
    missing = 0

    # HoMM3-sourced tier sprites
    for name, tier, rel_src in HOMM3_MAP:
        src_path = SRC_BUNDLE / rel_src
        if not src_path.exists():
            print(f"  MISS  {tier:6} {name:36} <- {rel_src} (file not found)")
            missing += 1
            continue
        target = TIER_SOURCE[tier]
        img = Image.open(src_path)
        squared = fit_to_square(img, target)
        out = OUT_BASE / tier / f"{name}.webp"
        sz = save_webp(squared, out)
        total += sz
        manifest["sprites"].append({
            "name": name, "tier": tier, "source": "homm3", "src_path": rel_src,
            "out_path": str(out.relative_to(OUT_BASE.parent.parent.parent)).replace("\\", "/"),
            "size_kb": sz // 1024,
        })
        print(f"  ✓     {tier:6} {name:36} {sz//1024:4d} KB")

    # Programmatic markers
    print()
    for m in MARKERS:
        out = gen_marker(m)
        sz = os.path.getsize(out)
        total += sz
        manifest["sprites"].append({
            "name": m.name, "tier": "marker", "source": "programmatic",
            "out_path": str(out.relative_to(OUT_BASE.parent.parent.parent)).replace("\\", "/"),
            "size_kb": sz // 1024,
        })
        print(f"  ✓     marker {m.name:36} {sz//1024:4d} KB")

    # Player
    print()
    out = gen_player()
    sz = os.path.getsize(out)
    total += sz
    manifest["sprites"].append({
        "name": "player", "tier": "player", "source": "programmatic",
        "out_path": str(out.relative_to(OUT_BASE.parent.parent.parent)).replace("\\", "/"),
        "size_kb": sz // 1024,
    })
    print(f"  ✓     player                                       {sz//1024:4d} KB")

    # Write manifest
    manifest_path = OUT_BASE / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    print()
    print(f"Bundle total: {total//1024} KB ({len(manifest['sprites'])} sprites)")
    if missing:
        print(f"WARN  {missing} HoMM3 sources missing — fix paths or skip those mappings")


if __name__ == "__main__":
    main()
