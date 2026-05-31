import Phaser from 'phaser';
import { TILE_PX } from '../config/constants';
import type {
  BiomeObjectType,
  TilemapObjectKind,
  TilemapView,
} from '@/types/tilemap';
import { bandColor, pickValueBand, shouldStampBadge } from './treasure-badge';

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

// TMP-Q4 chunk B — value-band badge constants. MED-1: stamp only on
// `kind === 'treasure'` (lairs inherit tier_index but their `value` is
// strength, not gold). LOW-3: BADGE_DEPTH_BASE = 100_000 plants badges
// above all sprite depths (depth = 100 + anchor.y, max ~ grid height).
const BADGE_RADIUS_PX = 4;
const BADGE_DEPTH_BASE = 100_000;
const BADGE_ALPHA = 0.95;
const BADGE_BORDER_COLOR = 0x0f172a; // slate-900
const BADGE_BORDER_ALPHA = 0.7;
const BADGE_LOD_MIN_ZOOM = 0.4;

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
  /** TMP-Q4 chunk B — value-band badges, stamped only on `kind === 'treasure'`.
   *  Separate from sprites so the LOD `cam.zoom < BADGE_LOD_MIN_ZOOM` cull
   *  toggles only badges and not the underlying treasure sprite. */
  badgeArcs: Phaser.GameObjects.Arc[];
}

const EMPTY_BY_TIER = (): Record<SpriteMapping['tier'], Phaser.GameObjects.Image[]> => ({
  xl: [], l: [], m: [], s: [], xs: [], marker: [],
});

export interface ObjectOverlayHandle {
  /** Call this every frame (or on camera move) to update chunk visibility + LOD. */
  update(): void;
  /** Dispose all sprites + containers. Idempotent. */
  destroy(): void;
  /** Toggle ALL object chunks on/off (viewer layer panel). */
  setEnabled(v: boolean): void;
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
        badgeArcs: [],
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

    // TMP-Q4 chunk B — stamp a value-band badge on treasure piles only
    // (MED-1: NOT on MonsterLair guards even though they inherit
    // tier_index, because their `value` is strength not gold). The
    // gate routes through `shouldStampBadge` (treasure-badge.ts) so
    // the V1+V2 dual-kind check + finite-value defense live in one
    // testable predicate (LOW-2 + LOW-5 from chunk-B /review-impl).
    // The badge color comes from `pickValueBand` which defends against
    // malformed registry thresholds (LOW-6 from chunk-A /review-impl).
    if (shouldStampBadge(p)) {
      const band = pickValueBand(
        p.value as number,
        view.registry_ref?.value_band_thresholds ?? null,
      );
      const badge = scene.add
        .circle(
          screenX + displayPx * 0.35,
          screenY - displayPx * 0.85,
          BADGE_RADIUS_PX,
          bandColor(band),
          BADGE_ALPHA,
        )
        .setStrokeStyle(1, BADGE_BORDER_COLOR, BADGE_BORDER_ALPHA);
      badge.setDepth(BADGE_DEPTH_BASE + p.anchor.y);
      entry.container.add(badge);
      entry.badgeArcs.push(badge);
    }
  }

  const cam = scene.cameras.main;

  function update(): void {
    const wv = cam.worldView;
    const lodKeep = tiersForZoom(cam.zoom);
    // TMP-Q4 chunk B — badges culled at extreme zoom-out (small +
    // unreadable). The badge LOD is independent of the tier LOD: at
    // zoom 0.3 you can still see XL town sprites but a 4-px badge
    // becomes unreadable noise.
    const showBadges = cam.zoom >= BADGE_LOD_MIN_ZOOM;
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
      // Badges visibility is independent of tier LOD — they only hide
      // when the chunk is offscreen OR the camera is zoomed below the
      // readability threshold.
      for (const badge of entry.badgeArcs) {
        badge.visible = visible && showBadges;
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

  let enabled = true;
  return {
    update: () => {
      if (!enabled) return;
      update();
    },
    destroy,
    setEnabled: (v) => {
      enabled = v;
      for (const entry of chunks.values()) entry.container.visible = v;
      if (v) update();
    },
  };
}
