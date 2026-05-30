import { create } from 'zustand';
import type {
  TerrainCell,
  TilemapObjectPlacement,
  TilemapView,
} from '@/types/tilemap';

// V1.2 Batch 2.3 viewer state — layer toggles + tile inspector.
//
// Layer keys mirror the L0–L7 layers in `docs/specs/2026-05-24-v1-
// tilemap-viewer-render-strategy.md` §3. Defaults: L0–L4 + L6 + L7 ON
// (L6 zone centers default ON because they help orient the viewer);
// L5 zone boundaries OFF (deferred to V2 — not rendered yet anyway).

export type ViewerLayer =
  | 'foundation'
  | 'paths' // L1/L2/L2.5 combined: roads + rivers + crossings (shared RT)
  | 'objects'
  | 'zone_boundaries'
  | 'zone_centers'
  | 'player';

const DEFAULT_VISIBLE: Record<ViewerLayer, boolean> = {
  foundation: true,
  paths: true,
  objects: true,
  // L5 zone boundaries — debug toggle, default OFF (visually busy when on)
  zone_boundaries: false,
  zone_centers: true,
  player: true,
};

export interface InspectorPayload {
  tile: { x: number; y: number };
  terrainKind: number; // 1..10 or 0 for unknown
  /** V2 — resolved from `terrain_vocabulary[terrain_layer[i]]`. Absent on
   *  pre-V2 fixtures (no vocabulary present). */
  terrainCell: TerrainCell | null;
  zone: { id: string; role: string; terrain: string } | null;
  placementsAtTile: TilemapObjectPlacement[];
  roadHits: number;
  riverHit: { kind: 'tile' | 'bridge' | 'ford' } | null;
}

export interface ViewerState {
  visibleLayers: Record<ViewerLayer, boolean>;
  setLayer: (layer: ViewerLayer, visible: boolean) => void;
  resetLayers: () => void;

  /** TMP-Q3 chunk A — Stage-1 smooth-blend post-processing on the
   *  foundation layer. `true` (default) enables a low-strength Phaser
   *  Blur filter; `false` falls back to V0 hard-pixel rendering for
   *  debug / perf comparison. Chunk B replaces the Blur with a custom
   *  cross-tile shader gated by the same flag. */
  blendEnabled: boolean;
  setBlendEnabled: (enabled: boolean) => void;

  /** Last clicked tile (null = inspector closed). */
  inspector: InspectorPayload | null;
  openInspectorFor: (
    tile: { x: number; y: number },
    view: TilemapView,
  ) => void;
  closeInspector: () => void;
}

function lookupAt(
  tile: { x: number; y: number },
  view: TilemapView,
): InspectorPayload {
  const w = view.grid_size.width;
  const idx = tile.y * w + tile.x;
  const terrainKind =
    idx >= 0 && idx < view.terrain_layer.length
      ? (view.terrain_layer[idx] ?? 0)
      : 0;
  const terrainCell =
    view.terrain_vocabulary && terrainKind >= 0 && terrainKind < view.terrain_vocabulary.length
      ? (view.terrain_vocabulary[terrainKind] ?? null)
      : null;

  // Nearest-zone by center_position (Voronoi). Bitmap-precise lookup
  // needs BigInt JSON reviver (DEFERRED V2 with L5).
  let bestZone: ViewerState['inspector'] extends infer T
    ? T extends { zone: infer Z }
      ? Z
      : never
    : never;
  bestZone = null as unknown as typeof bestZone;
  let bestDist = Infinity;
  for (const z of view.zones) {
    const dx = z.center_position.x - tile.x;
    const dy = z.center_position.y - tile.y;
    const d = dx * dx + dy * dy;
    if (d < bestDist) {
      bestDist = d;
      bestZone = { id: z.zone_id, role: z.zone_role, terrain: z.terrain_type };
    }
  }

  const placementsAtTile = view.object_placements.filter(
    (p) => p.anchor.x === tile.x && p.anchor.y === tile.y,
  );

  let roadHits = 0;
  for (const seg of view.road_segments) {
    if (seg.waypoints.some((wp) => wp.x === tile.x && wp.y === tile.y)) {
      roadHits++;
    }
  }

  let riverHit: InspectorPayload['riverHit'] = null;
  for (const seg of view.river_segments) {
    const c = seg.crossings.find(
      (cr) => cr.at.x === tile.x && cr.at.y === tile.y,
    );
    if (c) {
      riverHit = { kind: c.kind };
      break;
    }
    if (seg.tiles.some((t) => t.x === tile.x && t.y === tile.y)) {
      riverHit = { kind: 'tile' };
      // keep looking in case a crossing also matches
    }
  }

  return {
    tile,
    terrainKind,
    terrainCell,
    zone: bestZone,
    placementsAtTile,
    roadHits,
    riverHit,
  };
}

export const useViewerStore = create<ViewerState>((set) => ({
  visibleLayers: { ...DEFAULT_VISIBLE },
  setLayer: (layer, visible) =>
    set((s) => ({
      visibleLayers: { ...s.visibleLayers, [layer]: visible },
    })),
  resetLayers: () => set({ visibleLayers: { ...DEFAULT_VISIBLE } }),

  blendEnabled: true,
  setBlendEnabled: (enabled) => set({ blendEnabled: enabled }),

  inspector: null,
  openInspectorFor: (tile, view) =>
    set({ inspector: lookupAt(tile, view) }),
  closeInspector: () => set({ inspector: null }),
}));

// Exported for unit tests + future TileInspector hot-lookup outside React.
export { lookupAt };
