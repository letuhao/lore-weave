/**
 * Kenney Roguelike RPG Pack — sprite atlas index map.
 *
 * License: CC0 by Kenney.nl (see public/assets/kenney_LICENSE.txt).
 * Spritesheet: public/assets/kenney_roguelike_sheet.png (968×526; 16×16 tiles + 1px margin)
 *
 * Frame index formula: `index = row * COLS + col`
 * Phaser load: spritesheet('roguelike', '...', { frameWidth: 16, frameHeight: 16, margin: 0, spacing: 1 })
 *
 * NOTE: Tile coordinates below are visual best-guesses from inspecting the spritesheet.
 * If a sprite shows wrong/blank, tune (col, row) here. Renderer falls back to emoji
 * automatically when frame doesn't render correctly.
 *
 * Cols (per spritesheet): 0..57 (~58 columns due to 968/17)
 * Rows (per spritesheet): 0..30 (~31 rows due to 526/17)
 */

export const KENNEY = {
  sheetKey: 'roguelike',
  sheetPath: '/assets/kenney_roguelike_sheet.png',
  frameWidth: 16,
  frameHeight: 16,
  margin: 0,
  spacing: 1,
  cols: 57,
  rows: 31,
} as const;

export interface TileIndex {
  col: number;
  row: number;
}

/** Compute Phaser frame index from (col, row). */
export function frameOf(t: TileIndex): number {
  return t.row * KENNEY.cols + t.col;
}

/**
 * Decoration sprite library — scattered procedurally on tiles by terrain type.
 *
 * Each terrain has a list of candidate decorations + per-tile spawn probability.
 * Scatter is deterministic via PRNG keyed on (cell_id, x, y, seed).
 *
 * NOTE: indices are tunable. If wrong tile shows, edit here. Empty list = no scatter.
 */

// Tree/foliage decorations (best-guess indices for Kenney Roguelike pine trees + bushes)
const PINE_TREE_DARK: TileIndex = { col: 6, row: 5 };
const PINE_TREE_LIGHT: TileIndex = { col: 7, row: 5 };
const TREE_LARGE: TileIndex = { col: 8, row: 5 };
const BUSH_GREEN: TileIndex = { col: 5, row: 6 };
const BUSH_DARK: TileIndex = { col: 6, row: 6 };

// Grass decorations
const FLOWER_RED: TileIndex = { col: 3, row: 8 };
const FLOWER_YELLOW: TileIndex = { col: 3, row: 9 };
const FLOWER_BLUE: TileIndex = { col: 4, row: 8 };
const MUSHROOM_RED: TileIndex = { col: 4, row: 9 };
const GRASS_TUFT: TileIndex = { col: 2, row: 8 };

// Mountain/rock decorations
const ROCK_SMALL: TileIndex = { col: 5, row: 7 };
const ROCK_LARGE: TileIndex = { col: 4, row: 7 };

// Water decorations
const LILY_PAD: TileIndex = { col: 14, row: 1 };
const REED: TileIndex = { col: 13, row: 1 };

// Sand/desert
const CACTUS: TileIndex = { col: 9, row: 7 };
const SAND_SHELL: TileIndex = { col: 10, row: 7 };

// Cell anchor sprites (replace emoji when sprite available)
export const CELL_SPRITES = {
  capital: { col: 26, row: 4 } as TileIndex, // larger building
  fortress: { col: 30, row: 4 } as TileIndex, // fortress/keep
  temple: { col: 36, row: 4 } as TileIndex, // chapel/temple
  tavern: { col: 28, row: 5 } as TileIndex, // small house
  port: { col: 32, row: 4 } as TileIndex, // dockside building
  cell: { col: 28, row: 4 } as TileIndex, // generic small house
  cave: { col: 26, row: 6 } as TileIndex,
} as const;

// Landmark sprites
export const LANDMARK_SPRITES = {
  Landmark: { col: 9, row: 5 } as TileIndex, // stone monument / large tree
  Ruin: { col: 11, row: 6 } as TileIndex, // ruined tower
  MonsterLair: { col: 36, row: 5 } as TileIndex, // dark cave/bones
  Treasure: { col: 28, row: 9 } as TileIndex, // chest
  Mine: { col: 38, row: 4 } as TileIndex, // mine entrance
  Decoration: { col: 8, row: 4 } as TileIndex, // tree decoration
  Portal: { col: 44, row: 4 } as TileIndex,
} as const;

/** Decoration spawn rules — terrain → list of (sprite, weight, probability). */
export interface DecorationRule {
  sprite: TileIndex;
  /** 0..1 — probability of any decoration appearing on this terrain at all */
  base_chance: number;
  /** weight within decoration set when spawn fires */
  weight: number;
}

export const DECORATION_RULES: Record<string, DecorationRule[]> = {
  Grass: [
    { sprite: FLOWER_RED, base_chance: 0.15, weight: 1 },
    { sprite: FLOWER_YELLOW, base_chance: 0.15, weight: 1 },
    { sprite: FLOWER_BLUE, base_chance: 0.15, weight: 1 },
    { sprite: GRASS_TUFT, base_chance: 0.15, weight: 2 },
    { sprite: BUSH_GREEN, base_chance: 0.15, weight: 0.5 },
  ],
  Forest: [
    { sprite: PINE_TREE_DARK, base_chance: 0.5, weight: 3 },
    { sprite: PINE_TREE_LIGHT, base_chance: 0.5, weight: 2 },
    { sprite: TREE_LARGE, base_chance: 0.5, weight: 1 },
    { sprite: BUSH_DARK, base_chance: 0.5, weight: 1 },
    { sprite: MUSHROOM_RED, base_chance: 0.5, weight: 0.5 },
  ],
  Mountain: [
    { sprite: ROCK_SMALL, base_chance: 0.35, weight: 2 },
    { sprite: ROCK_LARGE, base_chance: 0.35, weight: 1 },
  ],
  Water: [
    { sprite: LILY_PAD, base_chance: 0.06, weight: 1 },
    { sprite: REED, base_chance: 0.06, weight: 1 },
  ],
  Sand: [
    { sprite: CACTUS, base_chance: 0.08, weight: 1 },
    { sprite: SAND_SHELL, base_chance: 0.08, weight: 1 },
  ],
  Snow: [{ sprite: ROCK_SMALL, base_chance: 0.1, weight: 1 }],
  Swamp: [
    { sprite: MUSHROOM_RED, base_chance: 0.3, weight: 2 },
    { sprite: REED, base_chance: 0.3, weight: 1 },
  ],
  Road: [],
  Rough: [{ sprite: ROCK_SMALL, base_chance: 0.15, weight: 1 }],
  Subterranean: [],
};
