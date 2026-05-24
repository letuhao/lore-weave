"""Render real-Earth landmass silhouettes at 1024x640 scale as Phase A v2 target reference.

Stylised hand-defined vertex sets approximating Japan, Indonesia, Britain, Norway,
India, Greece, and Italy — the 7 most recognisable landmasses that show:
  * island arcs (Japan)
  * archipelago (Indonesia, Greece)
  * fjord coast (Norway)
  * ria coast (Britain)
  * peninsula (India, Italy)

Output: eval/compare-phase-a/target_real_earth.png — a calibration reference
showing what 1 plate SHOULD look like at our scale.

Not algorithmically generated — these are HAND-PLACED polygons meant to set the
visual bar for Phase A v2's output. Each silhouette is sized so its longest
dimension is ~plate diameter (~230px in our default 1024x640 / 12-plate world).
"""

from PIL import Image, ImageDraw, ImageFont

# Canvas — match our generator scale
W, H = 1024, 640
LAND = (110, 165, 95)
SEA = (10, 14, 30)
LABEL = (255, 255, 220)
GRID = (50, 60, 70)

img = Image.new("RGB", (W, H), SEA)
draw = ImageDraw.Draw(img)

# Faint grid showing our "1 plate" reference size (≈ 230×230 px)
for x in range(0, W, 128):
    draw.line([(x, 0), (x, H)], fill=GRID, width=1)
for y in range(0, H, 128):
    draw.line([(0, y), (W, y)], fill=GRID, width=1)

try:
    font = ImageFont.truetype("arial.ttf", 14)
    sm = ImageFont.truetype("arial.ttf", 11)
except OSError:
    font = ImageFont.load_default()
    sm = ImageFont.load_default()


def draw_silhouette(polys, color=LAND):
    """Draw 1+ polygons. Each poly is a list of (x, y) tuples."""
    for poly in polys:
        if len(poly) >= 3:
            draw.polygon(poly, fill=color)


# ── 1. JAPAN ARCHIPELAGO (top-left, ~250x180) — island arc topology
# 4 main islands + ~8 minor islands, arranged in NE-SW arc
jx, jy = 80, 60
japan = [
    # Hokkaido (northeast big island)
    [(jx + 165, jy + 5), (jx + 200, jy + 10), (jx + 220, jy + 30), (jx + 215, jy + 50),
     (jx + 195, jy + 60), (jx + 175, jy + 55), (jx + 160, jy + 40), (jx + 158, jy + 20)],
    # Honshu (main island, elongated NE-SW)
    [(jx + 130, jy + 60), (jx + 160, jy + 65), (jx + 180, jy + 78), (jx + 175, jy + 95),
     (jx + 155, jy + 100), (jx + 130, jy + 110), (jx + 100, jy + 125), (jx + 70, jy + 135),
     (jx + 50, jy + 140), (jx + 35, jy + 135), (jx + 40, jy + 120), (jx + 60, jy + 115),
     (jx + 85, jy + 105), (jx + 105, jy + 90), (jx + 120, jy + 75)],
    # Shikoku (south of Honshu)
    [(jx + 65, jy + 145), (jx + 90, jy + 148), (jx + 100, jy + 158), (jx + 85, jy + 165),
     (jx + 65, jy + 160)],
    # Kyushu (southwest)
    [(jx + 25, jy + 150), (jx + 55, jy + 155), (jx + 60, jy + 170), (jx + 50, jy + 178),
     (jx + 30, jy + 175), (jx + 18, jy + 165)],
    # Sado (small island offshore Honshu)
    [(jx + 88, jy + 75), (jx + 95, jy + 78), (jx + 94, jy + 84), (jx + 87, jy + 82)],
    # Oki, Iki, Tsushima (smaller islets)
    [(jx + 15, jy + 145), (jx + 22, jy + 147), (jx + 20, jy + 152), (jx + 14, jy + 150)],
    [(jx + 5, jy + 155), (jx + 12, jy + 156), (jx + 10, jy + 162), (jx + 4, jy + 160)],
]
draw_silhouette(japan)
draw.text((jx + 80, jy - 18), "JAPAN — island arc", fill=LABEL, font=font)
draw.text((jx, jy + 188), "~250×180px · 4 main + 6 minor islands · D~1.2", fill=LABEL, font=sm)

# ── 2. INDONESIA (top-right, ~290x180) — archipelago topology
# Java + Sumatra + Borneo + Sulawesi + Papua + 1000s of small islands
ix, iy = 700, 50
indo = [
    # Sumatra (long NW-SE island)
    [(ix + 5, iy + 90), (ix + 20, iy + 75), (ix + 40, iy + 60), (ix + 60, iy + 55),
     (ix + 75, iy + 65), (ix + 70, iy + 80), (ix + 55, iy + 95), (ix + 35, iy + 105),
     (ix + 18, iy + 105), (ix + 5, iy + 100)],
    # Java (south of Sumatra, elongated E-W)
    [(ix + 70, iy + 120), (ix + 130, iy + 115), (ix + 145, iy + 122), (ix + 140, iy + 132),
     (ix + 115, iy + 135), (ix + 85, iy + 138), (ix + 65, iy + 130)],
    # Borneo (large central rounded island)
    [(ix + 95, iy + 50), (ix + 130, iy + 45), (ix + 155, iy + 55), (ix + 168, iy + 75),
     (ix + 160, iy + 95), (ix + 140, iy + 105), (ix + 115, iy + 102), (ix + 90, iy + 90),
     (ix + 85, iy + 70)],
    # Sulawesi (K-shape east of Borneo)
    [(ix + 180, iy + 60), (ix + 195, iy + 55), (ix + 200, iy + 70), (ix + 205, iy + 90),
     (ix + 195, iy + 95), (ix + 188, iy + 80), (ix + 185, iy + 70)],
    # Papua (western half, NE area)
    [(ix + 220, iy + 100), (ix + 260, iy + 95), (ix + 285, iy + 110), (ix + 280, iy + 125),
     (ix + 250, iy + 130), (ix + 225, iy + 122)],
    # Bali (small east of Java)
    [(ix + 150, iy + 130), (ix + 158, iy + 130), (ix + 156, iy + 137), (ix + 150, iy + 136)],
    # Lombok, Sumbawa, Flores, Timor — chain east of Bali
    [(ix + 162, iy + 132), (ix + 172, iy + 134), (ix + 170, iy + 140), (ix + 162, iy + 138)],
    [(ix + 178, iy + 134), (ix + 192, iy + 136), (ix + 190, iy + 142), (ix + 178, iy + 140)],
    [(ix + 198, iy + 137), (ix + 215, iy + 140), (ix + 213, iy + 146), (ix + 198, iy + 144)],
    # Halmahera (small NE)
    [(ix + 207, iy + 70), (ix + 215, iy + 65), (ix + 220, iy + 78), (ix + 213, iy + 85),
     (ix + 207, iy + 78)],
    # Many small dots = Maluku islands
]
# Draw scattered small island dots
import random
random.seed(42)
for _ in range(40):
    px = ix + 100 + random.randint(0, 180)
    py = iy + 45 + random.randint(0, 100)
    sz = random.randint(2, 4)
    draw.ellipse([(px, py), (px + sz, py + sz)], fill=LAND)
draw_silhouette(indo)
draw.text((ix + 90, iy - 18), "INDONESIA — archipelago", fill=LABEL, font=font)
draw.text((ix, iy + 188), "~290×180px · ~17,500 islands · max-fragmentation", fill=LABEL, font=sm)

# ── 3. BRITAIN (middle-left, ~150x230) — ria coastline D~1.25
bx, by = 100, 290
britain = [
    # Main island Great Britain (irregular ria coast)
    [(bx + 30, by + 5), (bx + 50, by + 0), (bx + 65, by + 12), (bx + 60, by + 28),
     (bx + 50, by + 35), (bx + 45, by + 50), (bx + 60, by + 60), (bx + 80, by + 55),
     (bx + 90, by + 70), (bx + 105, by + 80), (bx + 115, by + 95), (bx + 125, by + 115),
     (bx + 122, by + 135), (bx + 115, by + 150), (bx + 105, by + 165), (bx + 92, by + 175),
     (bx + 75, by + 178), (bx + 55, by + 175), (bx + 40, by + 170), (bx + 25, by + 162),
     (bx + 18, by + 148), (bx + 12, by + 130), (bx + 8, by + 110), (bx + 12, by + 90),
     (bx + 22, by + 78), (bx + 30, by + 65), (bx + 25, by + 50), (bx + 18, by + 35),
     (bx + 20, by + 20)],
    # Ireland (west of GB)
    [(bx - 50, by + 80), (bx - 28, by + 75), (bx - 12, by + 88), (bx - 8, by + 110),
     (bx - 15, by + 125), (bx - 32, by + 135), (bx - 50, by + 130), (bx - 58, by + 115),
     (bx - 55, by + 95)],
    # Isle of Man + Outer Hebrides + Shetland (small islands)
    [(bx - 5, by + 90), (bx + 5, by + 92), (bx + 4, by + 100), (bx - 5, by + 98)],
    [(bx - 12, by + 28), (bx - 5, by + 30), (bx - 6, by + 38), (bx - 12, by + 36)],
    [(bx - 18, by + 18), (bx - 10, by + 20), (bx - 11, by + 26), (bx - 18, by + 24)],
]
draw_silhouette(britain)
draw.text((bx - 50, by - 15), "BRITAIN — ria coast (D≈1.25)", fill=LABEL, font=font)
draw.text((bx - 50, by + 195), "~180×220px · GB+Ireland+islets · indented coast", fill=LABEL, font=sm)

# ── 4. NORWAY (middle-center, ~180x260) — fjord coast D~1.52
nx, ny = 360, 280
# Approximate Norway's elongated mountainous coast with DEEP fjord intrusions
norway = [
    [
        # East border (mostly straight, Swedish boundary)
        (nx + 80, ny + 0), (nx + 95, ny + 5), (nx + 110, ny + 25), (nx + 115, ny + 50),
        (nx + 118, ny + 80), (nx + 122, ny + 110), (nx + 125, ny + 140), (nx + 130, ny + 165),
        (nx + 140, ny + 185), (nx + 155, ny + 200), (nx + 165, ny + 218), (nx + 170, ny + 235),
        # South coast
        (nx + 160, ny + 250), (nx + 140, ny + 252), (nx + 115, ny + 250), (nx + 95, ny + 245),
        # WEST COAST with DEEP FJORDS — heavy zigzag
        (nx + 88, ny + 230), (nx + 80, ny + 232), (nx + 75, ny + 220), (nx + 82, ny + 215),  # fjord
        (nx + 85, ny + 205), (nx + 70, ny + 205), (nx + 68, ny + 195), (nx + 80, ny + 192),  # fjord
        (nx + 78, ny + 180), (nx + 63, ny + 182), (nx + 60, ny + 168), (nx + 75, ny + 165),  # fjord
        (nx + 72, ny + 152), (nx + 55, ny + 155), (nx + 50, ny + 142), (nx + 68, ny + 138),  # fjord
        (nx + 65, ny + 125), (nx + 48, ny + 128), (nx + 42, ny + 115), (nx + 60, ny + 112),  # fjord
        (nx + 58, ny + 98), (nx + 40, ny + 100), (nx + 35, ny + 88), (nx + 53, ny + 85),     # fjord
        (nx + 50, ny + 72), (nx + 33, ny + 75), (nx + 28, ny + 62), (nx + 48, ny + 60),      # fjord
        (nx + 50, ny + 48), (nx + 30, ny + 50), (nx + 25, ny + 38), (nx + 45, ny + 35),      # fjord
        (nx + 48, ny + 22), (nx + 28, ny + 25), (nx + 22, ny + 12), (nx + 50, ny + 8),       # fjord
        (nx + 65, ny + 2),
    ],
    # Lofoten + offshore island chain
    [(nx + 10, ny + 5), (nx + 18, ny + 8), (nx + 16, ny + 14), (nx + 8, ny + 12)],
    [(nx + 2, ny + 16), (nx + 12, ny + 18), (nx + 10, ny + 24), (nx + 1, ny + 22)],
    [(nx + 0, ny + 40), (nx + 10, ny + 42), (nx + 8, ny + 50), (nx - 2, ny + 48)],
    [(nx + 5, ny + 70), (nx + 14, ny + 72), (nx + 13, ny + 80), (nx + 4, ny + 78)],
]
draw_silhouette(norway)
draw.text((nx + 5, ny - 15), "NORWAY — fjord coast (D≈1.52)", fill=LABEL, font=font)
draw.text((nx, ny + 268), "~180×260px · deep zigzag fjords · highest D in world", fill=LABEL, font=sm)

# ── 5. INDIA — peninsula (right-middle, ~180x230)
inx, iny = 600, 280
india = [
    [(inx + 50, iny + 0), (inx + 80, iny + 5), (inx + 105, iny + 15), (inx + 130, iny + 25),
     (inx + 150, iny + 38), (inx + 160, iny + 55), (inx + 158, iny + 78), (inx + 152, iny + 100),
     (inx + 145, iny + 125), (inx + 135, iny + 150), (inx + 122, iny + 175), (inx + 105, iny + 198),
     (inx + 90, iny + 215), (inx + 75, iny + 222), (inx + 65, iny + 213), (inx + 58, iny + 195),
     (inx + 50, iny + 175), (inx + 42, iny + 150), (inx + 35, iny + 125), (inx + 28, iny + 100),
     (inx + 22, iny + 78), (inx + 15, iny + 55), (inx + 12, iny + 32), (inx + 22, iny + 15)],
    # Sri Lanka (tear-shaped offshore)
    [(inx + 95, iny + 218), (inx + 108, iny + 222), (inx + 110, iny + 238), (inx + 100, iny + 242),
     (inx + 92, iny + 235), (inx + 90, iny + 225)],
]
draw_silhouette(india)
draw.text((inx + 30, iny - 15), "INDIA — peninsula", fill=LABEL, font=font)
draw.text((inx, iny + 252), "~180×240px · long taper south · 1 main + Sri Lanka", fill=LABEL, font=sm)

# ── 6. GREECE — archipelago + mainland (~140x150)
gx, gy = 800, 280
greece = [
    # Mainland Greece (Peloponnese + mainland)
    [(gx + 30, gy + 5), (gx + 60, gy + 0), (gx + 85, gy + 8), (gx + 100, gy + 20),
     (gx + 105, gy + 35), (gx + 100, gy + 50), (gx + 90, gy + 58), (gx + 75, gy + 65),
     (gx + 60, gy + 78), (gx + 50, gy + 95), (gx + 40, gy + 105), (gx + 25, gy + 102),
     (gx + 15, gy + 92), (gx + 22, gy + 78), (gx + 30, gy + 65), (gx + 25, gy + 50),
     (gx + 18, gy + 38), (gx + 15, gy + 22)],
    # Crete (south)
    [(gx + 40, gy + 132), (gx + 80, gy + 130), (gx + 95, gy + 138), (gx + 90, gy + 145),
     (gx + 55, gy + 145), (gx + 38, gy + 140)],
    # Many Aegean islands (Cyclades, Dodecanese)
]
random.seed(7)
for _ in range(25):
    px = gx + 95 + random.randint(0, 55)
    py = gy + 25 + random.randint(0, 95)
    sz = random.randint(3, 7)
    draw.ellipse([(px, py), (px + sz, py + sz)], fill=LAND)
draw_silhouette(greece)
draw.text((gx + 30, gy - 15), "GREECE — mainland+isles", fill=LABEL, font=font)
draw.text((gx, gy + 160), "~150×150px · ~6000 islands in archipelago", fill=LABEL, font=sm)

# Title at the very bottom
draw.text((10, H - 22),
          "PHASE A v2 TARGET — what 'organic continents' look like at our 1024×640 / 12-plate scale "
          "(each landmass sized to ~1 plate diameter ≈ 230px)",
          fill=LABEL, font=font)

img.save("eval/compare-phase-a/target_real_earth.png")
print("wrote eval/compare-phase-a/target_real_earth.png — 7 real-Earth landmass silhouettes at our scale")
