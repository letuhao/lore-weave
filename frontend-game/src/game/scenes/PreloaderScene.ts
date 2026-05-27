import Phaser from 'phaser';
import { EventBus } from '../EventBus';

// Loads critical assets for V1 tilemap viewer.
//
// Batch 2.0: foundation uses one stitched `terrain-tileset.png` strip
// (10 × 64 px frames) consumed by Phaser 4 `TilemapGPULayer`.
//
// Batch 2.1: prop bundle loaded here too. Total bundle weight ~500 KB
// (WebP @ q=85) — small enough to ship all at boot rather than lazy
// per-tier. Bundle composition mirrors
// `frontend-game/scripts/gen-prop-bundle.py` + manifest at
// `/assets/sprites/MANIFEST.json` (loaded later if metadata needed).

const TILE_BASE = '/assets/tiles/homm3-placeholder';
const SPRITE_BASE = '/assets/sprites';
const TERRAIN_TILESET_KEY = 'terrain-tileset';

interface SpriteEntry {
  /** Texture key used by code at `terrain-<tag>` / `prop-<name>` / etc. */
  key: string;
  /** Relative URL under `public/`. */
  url: string;
}

const TIER_XL: ReadonlyArray<SpriteEntry> = [
  { key: 'prop-xl-town', url: `${SPRITE_BASE}/xl/town.webp` },
  { key: 'prop-xl-landmark_statue', url: `${SPRITE_BASE}/xl/landmark_statue.webp` },
];

const TIER_L: ReadonlyArray<SpriteEntry> = [
  { key: 'prop-l-mine_gold', url: `${SPRITE_BASE}/l/mine_gold.webp` },
  { key: 'prop-l-mine_ore', url: `${SPRITE_BASE}/l/mine_ore.webp` },
  { key: 'prop-l-mine_gem', url: `${SPRITE_BASE}/l/mine_gem.webp` },
  { key: 'prop-l-shrine', url: `${SPRITE_BASE}/l/shrine.webp` },
  { key: 'prop-l-monolith', url: `${SPRITE_BASE}/l/monolith.webp` },
  { key: 'prop-l-tower_ruin', url: `${SPRITE_BASE}/l/tower_ruin.webp` },
  { key: 'prop-l-monument_obelisk', url: `${SPRITE_BASE}/l/monument_obelisk.webp` },
];

const TIER_M: ReadonlyArray<SpriteEntry> = [
  { key: 'prop-m-mountain_rocks', url: `${SPRITE_BASE}/m/mountain_rocks.webp` },
  { key: 'prop-m-siege_tower_fragment', url: `${SPRITE_BASE}/m/siege_tower_fragment.webp` },
  { key: 'prop-m-palisade_fence', url: `${SPRITE_BASE}/m/palisade_fence.webp` },
];

const TIER_S: ReadonlyArray<SpriteEntry> = [
  { key: 'prop-s-tree', url: `${SPRITE_BASE}/s/tree.webp` },
  { key: 'prop-s-bush', url: `${SPRITE_BASE}/s/bush.webp` },
  { key: 'prop-s-treasure_pile', url: `${SPRITE_BASE}/s/treasure_pile.webp` },
];

const TIER_XS: ReadonlyArray<SpriteEntry> = [
  { key: 'prop-xs-decoration_boundary_stones', url: `${SPRITE_BASE}/xs/decoration_boundary_stones.webp` },
  { key: 'prop-xs-decoration_lantern_post', url: `${SPRITE_BASE}/xs/decoration_lantern_post.webp` },
  { key: 'prop-xs-mushroom_cluster', url: `${SPRITE_BASE}/xs/mushroom_cluster.webp` },
];

const MARKERS: ReadonlyArray<SpriteEntry> = [
  { key: 'marker-monster_lair', url: `${SPRITE_BASE}/marker/monster_lair.webp` },
  { key: 'marker-ferry', url: `${SPRITE_BASE}/marker/ferry.webp` },
  { key: 'marker-lake', url: `${SPRITE_BASE}/marker/lake.webp` },
  { key: 'marker-crater', url: `${SPRITE_BASE}/marker/crater.webp` },
  { key: 'marker-animal', url: `${SPRITE_BASE}/marker/animal.webp` },
  { key: 'marker-other', url: `${SPRITE_BASE}/marker/other.webp` },
];

const PLAYER: SpriteEntry = { key: 'player-sprite', url: `${SPRITE_BASE}/player.webp` };

const ALL_PROPS: ReadonlyArray<SpriteEntry> = [
  ...TIER_XL,
  ...TIER_L,
  ...TIER_M,
  ...TIER_S,
  ...TIER_XS,
  ...MARKERS,
  PLAYER,
];

export class PreloaderScene extends Phaser.Scene {
  constructor() {
    super({ key: 'PreloaderScene' });
  }

  preload(): void {
    // Yellow-circle stub kept as a fallback texture for any code that
    // hasn't migrated to `player-sprite` yet. Cheap to keep — 32×32.
    const playerGfx = this.add.graphics();
    playerGfx.fillStyle(0xfbbf24, 1);
    playerGfx.fillCircle(16, 16, 14);
    playerGfx.lineStyle(2, 0x78350f, 1);
    playerGfx.strokeCircle(16, 16, 14);
    playerGfx.generateTexture('player-stub', 32, 32);
    playerGfx.destroy();

    // Progress bar UI.
    const cam = this.cameras.main;
    const cx = cam.midPoint.x;
    const cy = cam.midPoint.y;
    const barBg = this.add.rectangle(cx, cy, 320, 16, 0x334155);
    const bar = this.add.rectangle(cx - 160, cy, 0, 16, 0x4f46e5).setOrigin(0, 0.5);
    this.load.on('progress', (value: number) => {
      bar.width = 320 * value;
    });
    this.load.on('complete', () => {
      bar.destroy();
      barBg.destroy();
    });

    // Foundation tileset — strip of 10 × 64×64 terrain frames.
    this.load.spritesheet(TERRAIN_TILESET_KEY, `${TILE_BASE}/terrain-tileset.png`, {
      frameWidth: 64,
      frameHeight: 64,
    });

    // Prop bundle — all tiers loaded at boot (~500 KB total).
    for (const s of ALL_PROPS) {
      this.load.image(s.key, s.url);
    }
  }

  create(): void {
    EventBus.emit('scene-ready', { key: 'PreloaderScene' });
    this.scene.start('MainMenuScene');
  }
}

export {
  TERRAIN_TILESET_KEY,
  TIER_XL,
  TIER_L,
  TIER_M,
  TIER_S,
  TIER_XS,
  MARKERS,
  PLAYER,
};
