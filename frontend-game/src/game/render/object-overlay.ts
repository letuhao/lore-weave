import Phaser from 'phaser';
import { TILE_PX } from '../config/constants';
import type {
  BiomeObjectType,
  TilemapObjectKind,
  TilemapView,
} from '@/types/tilemap';

// L4 object overlay — Strategy B (Container chunked culling) + D (LOD)
// from `docs/specs/2026-05-24-v1-tilemap-viewer-render-strategy.md`.
//
// Each `TilemapView.object_placements[]` entry → one sprite placed at
// `anchor` tile center, foot-anchored (`setOrigin(0.5, 1.0)`) so the
// sprite grows upward from the tile. Sprites are grouped into chunks
// of `CHUNK_TILES × CHUNK_TILES` tiles; per-frame the camera's
// `worldView` is intersected against chunk bounds and offscreen chunks
// have `.visible = false`. At Continent scale this caps draw calls to
// ~visible chunks × props-per-chunk instead of all 5k+ placements.

const CHUNK_TILES = 16; // 16×16 tiles per chunk

// LOD: which tiers stay visible at a given camera zoom. Mirror spec §2 D.
//   key = upper-bound zoom (exclusive); value = tiers to KEEP visible.
const LOD_BANDS: ReadonlyArray<{ maxZoom: number; keepTiers: ReadonlySet<string> }> = [
  { maxZoom: 0.1, keepTiers: new Set(['xl', 'l', 'marker']) },
  { maxZoom: 0.25, keepTiers: new Set(['xl', 'l', 'm', 'marker']) },
  { maxZoom: 0.5, keepTiers: new Set(['xl', 'l', 'm', 's', 'marker']) },
  // > 0.5 → keep everything (Number.POSITIVE_INFINITY sentinel below)
];

function tiersForZoom(zoom: number): ReadonlySet<string> | null {
  for (const band of LOD_BANDS) {
    if (zoom < band.maxZoom) return band.keepTiers;
  }
  return null; // null = show all tiers
}

interface SpriteMapping {
  textureKey: string;
  tier: 'xl' | 'l' | 'm' | 's' | 'xs' | 'marker';
  /** Display width = display height (square). */
  displayPx: number;
}

const TIER_DISPLAY_PX: Record<SpriteMapping['tier'], number> = {
  xl: 384,
  l: 256,
  m: 192,
  s: 160,
  xs: 128,
  marker: 128,
};

/**
 * Map (kind, biome_object_type) tuple to a sprite texture key + tier.
 * Mirrors the per-(kind, subtype) table in the scope-expansion spec.
 */
export function spriteForPlacement(
  kind: TilemapObjectKind,
  biomeObjectType: BiomeObjectType | undefined | null,
): SpriteMapping {
  const t = (tier: SpriteMapping['tier'], key: string): SpriteMapping => ({
    textureKey: key,
    tier,
    displayPx: TIER_DISPLAY_PX[tier],
  });

  switch (kind) {
    case 'town':
      return t('xl', 'prop-xl-town');
    case 'landmark':
      return t('xl', 'prop-xl-landmark_statue');
    case 'mine':
      return t('l', 'prop-l-mine_gold');
    case 'monolith':
      return t('l', 'prop-l-monolith');
    case 'treasure':
      return t('s', 'prop-s-treasure_pile');
    case 'monster_lair':
      return t('marker', 'marker-monster_lair');
    case 'ferry':
      return t('marker', 'marker-ferry');
    case 'decoration':
      return t('xs', 'prop-xs-decoration_boundary_stones');
    case 'obstacle':
      switch (biomeObjectType) {
        case 'mountain':
          return t('m', 'prop-m-mountain_rocks');
        case 'tree':
          return t('s', 'prop-s-tree');
        case 'plant':
          return t('s', 'prop-s-bush');
        case 'structure':
          return t('m', 'prop-m-siege_tower_fragment');
        case 'rock':
          return t('xs', 'prop-xs-decoration_boundary_stones');
        case 'lake':
          return t('marker', 'marker-lake');
        case 'crater':
          return t('marker', 'marker-crater');
        case 'animal':
          return t('marker', 'marker-animal');
        case 'other':
        default:
          return t('marker', 'marker-other');
      }
    default:
      return t('marker', 'marker-other');
  }
}

interface ChunkEntry {
  container: Phaser.GameObjects.Container;
  /** Bounds rect (world coords) used for camera culling. */
  bx: number;
  by: number;
  bw: number;
  bh: number;
  /** Sprites grouped by tier — for LOD toggle without re-checking each sprite. */
  byTier: Record<SpriteMapping['tier'], Phaser.GameObjects.Image[]>;
}

const EMPTY_BY_TIER = (): Record<SpriteMapping['tier'], Phaser.GameObjects.Image[]> => ({
  xl: [], l: [], m: [], s: [], xs: [], marker: [],
});

export interface ObjectOverlayHandle {
  /** Call this every frame (or on camera move) to update chunk visibility + LOD. */
  update(): void;
  /** Dispose all sprites + containers. Idempotent. */
  destroy(): void;
}

export function buildObjectOverlay(
  scene: Phaser.Scene,
  view: TilemapView,
): ObjectOverlayHandle {
  const chunks = new Map<string, ChunkEntry>();
  const chunkSize = CHUNK_TILES * TILE_PX;

  for (const p of view.object_placements ?? []) {
    if (!p || !p.anchor) continue;
    const { textureKey, tier, displayPx } = spriteForPlacement(p.kind, p.biome_object_type);
    const cx = Math.floor(p.anchor.x / CHUNK_TILES);
    const cy = Math.floor(p.anchor.y / CHUNK_TILES);
    const key = `${cx},${cy}`;
    let entry = chunks.get(key);
    if (!entry) {
      entry = {
        container: scene.add.container(0, 0),
        bx: cx * chunkSize,
        by: cy * chunkSize,
        bw: chunkSize,
        bh: chunkSize,
        byTier: EMPTY_BY_TIER(),
      };
      // Render objects above the foundation; depth 100 leaves room for
      // overlays (200) and Player (1000) above.
      entry.container.setDepth(100);
      chunks.set(key, entry);
    }
    const screenX = p.anchor.x * TILE_PX + TILE_PX / 2;
    const screenY = p.anchor.y * TILE_PX + TILE_PX;
    const sprite = scene.add
      .image(screenX, screenY, textureKey)
      .setOrigin(0.5, 1.0)
      .setDisplaySize(displayPx, displayPx);
    // Depth-sort within chunk by anchor y so closer-to-camera props
    // render on top — cheap because chunks are small.
    sprite.setDepth(100 + p.anchor.y);
    entry.container.add(sprite);
    entry.byTier[tier].push(sprite);
  }

  const cam = scene.cameras.main;

  function update(): void {
    const wv = cam.worldView;
    const lodKeep = tiersForZoom(cam.zoom);
    for (const entry of chunks.values()) {
      const visible = Phaser.Geom.Rectangle.Overlaps(
        wv,
        new Phaser.Geom.Rectangle(entry.bx, entry.by, entry.bw, entry.bh),
      );
      entry.container.visible = visible;
      if (visible && lodKeep) {
        // Toggle per-tier visibility within visible chunks.
        for (const tier of ['xl', 'l', 'm', 's', 'xs', 'marker'] as const) {
          const shouldShow = lodKeep.has(tier);
          for (const sprite of entry.byTier[tier]) {
            sprite.visible = shouldShow;
          }
        }
      } else if (visible) {
        // lodKeep null = show all tiers
        for (const tier of ['xl', 'l', 'm', 's', 'xs', 'marker'] as const) {
          for (const sprite of entry.byTier[tier]) {
            sprite.visible = true;
          }
        }
      }
    }
  }

  function destroy(): void {
    for (const entry of chunks.values()) {
      entry.container.destroy(true);
    }
    chunks.clear();
  }

  // First-frame update so initial render is culled correctly.
  update();

  return { update, destroy };
}
