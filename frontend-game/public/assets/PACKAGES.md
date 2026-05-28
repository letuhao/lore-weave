# Asset package manifest

This file maps each asset pack's filename convention to the in-game use
case so future devs (and AI agents) can find "the grass tile" without
opening every PNG.

## Acknowledgements

LoreWeave gratefully uses CC0 art from **Kenney** (https://kenney.nl) —
even though CC0 doesn't require attribution, we credit because the
ecosystem benefits when free-asset providers get visibility.

## kenney-isometric-landscape (V0 demo, Session D)

Pack location: `public/assets/tiles/kenney-isometric-landscape/`
License: CC0 (see `tiles/LICENSES.md`)
Source: https://kenney.nl/assets/isometric-tiles-landscape
Tile sprite size: 128×128 PNG (iso diamond inside is 128×64 visible)

**Filename → use case (PO-confirmed 2026-05-24):**

Pack contains 128 PNG files (`landscapeTiles_000.png` … `_127.png`) at
128×128 sprite canvas. Each tile is a 3D iso cube — diamond top (128×64
visible footprint) with sides extending downward, giving a stacked look
when placed on the iso grid (correct for our hybrid 2D iso aesthetic).

| Phaser key | File path | Use case | Spec biome (Session E+) |
|---|---|---|---|
| `tile-grass` | `kenney-isometric-landscape/PNG/landscapeTiles_067.png` | Default Town tier ground (solid green cube) | Town |
| `tile-dirt` | `kenney-isometric-landscape/PNG/landscapeTiles_083.png` | Path/road base (solid brown cube) | Path |
| `tile-stone-decor` | `kenney-isometric-landscape/PNG/landscapeTiles_127.png` | Stone cave-entrance decoration on grass | (V1+) |
| `tile-water-canal` | `kenney-isometric-landscape/PNG/landscapeTiles_017.png` | Grass with diagonal water canal | (V1+) |
| `tile-water-corner` | `kenney-isometric-landscape/PNG/landscapeTiles_009.png` | Grass cliff with partial water | (V1+) |

For V0 demo (Session D), only `tile-grass` is loaded. Others are stubbed
in this manifest for Session E+ biome variety.

**Anchor / origin note:** all cubes in this pack are rendered with the
ground-diamond at the TOP of the PNG and the cube sides extending DOWN.
Place via `setOrigin(0.5, 0)` so the top diamond aligns with the iso grid
cell at `worldToScreen(x, y)`. (Empirically determined; revisit if
visual smoke shows misalignment.)

## Future packs

Pending: Player character + NPC sprites. Kenney "Toon Characters 1"
candidate; PO to confirm in Session E+ when first NPC ships.
