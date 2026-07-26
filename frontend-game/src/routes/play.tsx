import { useEffect, useState } from 'react';
import { PhaserGame } from '@/components/PhaserGame';
import { HpBar, ManaBar } from '@/components/hud';
import { Modal } from '@/components/modal/Modal';
import { RotatePrompt } from '@/components/mobile/RotatePrompt';
import { VirtualGamepad } from '@/components/mobile/VirtualGamepad';
import { EchoPanel } from '@/components/echo/EchoPanel';
import { LayerToggles } from '@/components/viewer/LayerToggles';
import { TileInspector } from '@/components/viewer/TileInspector';
import { MetadataPanel } from '@/components/viewer/MetadataPanel';
import { useTilemapHealth, useZoneTilemap } from '@/api/tilemap-client';
import { EventBus } from '@/game/EventBus';
import { useViewerStore } from '@/store/viewer-store';
import {
  DEFAULT_SEED,
  DEFAULT_TIER,
  DEFAULT_ZONE_HEIGHT,
  DEFAULT_ZONE_WIDTH,
} from '@/game/config/constants';
import type { ChannelTier } from '@/types/tilemap';
import type { JSX } from 'react';

// V1.2 tilemap-viewer route. Renders one zone fetched from
// tilemap-service /internal/v1/tilemaps/render with all 7 visualizable
// layers (foundation + roads + rivers + crossings + objects + zone
// centers + Player). Spec:
// `docs/specs/2026-05-24-v1-tilemap-viewer-scope-expansion.md` +
// `2026-05-24-v1-tilemap-viewer-render-strategy.md`.

const TIER_OPTIONS: readonly ChannelTier[] = ['town', 'district', 'country', 'continent'] as const;
const GRID_DEFAULTS_BY_TIER: Record<ChannelTier, { w: number; h: number }> = {
  town: { w: 64, h: 64 },
  district: { w: 128, h: 128 },
  country: { w: 192, h: 192 },
  continent: { w: 256, h: 256 },
};

export function PlayRoute(): JSX.Element {
  const health = useTilemapHealth();
  const [seed, setSeed] = useState<number>(DEFAULT_SEED);
  const [tier, setTier] = useState<ChannelTier>(DEFAULT_TIER);
  const [gridWidth, setGridWidth] = useState<number>(DEFAULT_ZONE_WIDTH);
  const [gridHeight, setGridHeight] = useState<number>(DEFAULT_ZONE_HEIGHT);

  // TMP-Q4 chunk C — let the e2e select a fixture via `?template=<key>`
  // so the visual regression goldens can exercise the badges + zone
  // overlay against a treasure-bearing template without changing
  // minimal.json (which the existing AC-DECO-8 / AC-BIOME-8 smoke
  // tests depend on). Default remains minimal.json so /play loads
  // unchanged in normal usage.
  const templateUrl =
    typeof window !== 'undefined'
      ? (() => {
          const params = new URLSearchParams(window.location.search);
          const key = params.get('template');
          if (key === 'treasure-demo') return '/templates/treasure-demo.json';
          return undefined;
        })()
      : undefined;
  const tilemap = useZoneTilemap({ seed, tier, gridWidth, gridHeight, templateUrl });
  const openInspectorFor = useViewerStore((s) => s.openInspectorFor);

  // Bridge Phaser EventBus → viewer-store: Shift-click on a tile
  // emits `inspect-tile`; here we resolve with the current TilemapView
  // and open the inspector. Skipped when no view loaded yet.
  useEffect(() => {
    const handler = (tile: { x: number; y: number }): void => {
      if (tilemap.data) {
        openInspectorFor(tile, tilemap.data);
      }
    };
    EventBus.on('inspect-tile', handler);
    return () => {
      EventBus.off('inspect-tile', handler);
    };
  }, [tilemap.data, openInspectorFor]);

  const onRender = (): void => {
    void tilemap.refetch();
  };

  const onTierChange = (next: ChannelTier): void => {
    setTier(next);
    const d = GRID_DEFAULTS_BY_TIER[next];
    setGridWidth(d.w);
    setGridHeight(d.h);
  };

  return (
    <div className="relative w-screen h-screen overflow-hidden">
      <PhaserGame tilemap={tilemap.data} />

      {/* HUD overlay top-left */}
      <div className="absolute top-4 left-4 flex flex-col gap-2 pointer-events-auto">
        <HpBar />
        <ManaBar />
        <div className="text-xs text-slate-300 font-mono mt-2">
          tilemap-service: {health.isLoading ? '…' : health.data?.status ?? 'down'}
        </div>
      </div>

      {/* Tilemap viewer render-controls — top-right */}
      <div className="absolute top-4 right-4 bg-slate-900/90 border border-slate-700 rounded-md p-3 text-xs text-slate-200 font-mono pointer-events-auto flex flex-col gap-2 z-10 w-64">
        <div className="font-semibold text-sm">Tilemap viewer</div>
        <label className="flex justify-between items-center gap-2">
          <span>seed</span>
          <input
            type="number"
            value={seed}
            onChange={(e) => setSeed(Number(e.target.value) || 0)}
            className="bg-slate-800 border border-slate-600 rounded px-2 py-1 w-24 text-right"
          />
        </label>
        <label className="flex justify-between items-center gap-2">
          <span>tier</span>
          <select
            value={tier}
            onChange={(e) => onTierChange(e.target.value as ChannelTier)}
            className="bg-slate-800 border border-slate-600 rounded px-2 py-1 w-24"
          >
            {TIER_OPTIONS.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label className="flex justify-between items-center gap-2">
          <span>width</span>
          <input
            type="number"
            min={4}
            max={256}
            value={gridWidth}
            onChange={(e) => setGridWidth(Math.max(4, Math.min(256, Number(e.target.value) || 0)))}
            className="bg-slate-800 border border-slate-600 rounded px-2 py-1 w-24 text-right"
          />
        </label>
        <label className="flex justify-between items-center gap-2">
          <span>height</span>
          <input
            type="number"
            min={4}
            max={256}
            value={gridHeight}
            onChange={(e) => setGridHeight(Math.max(4, Math.min(256, Number(e.target.value) || 0)))}
            className="bg-slate-800 border border-slate-600 rounded px-2 py-1 w-24 text-right"
          />
        </label>
        <button
          onClick={onRender}
          disabled={tilemap.isFetching}
          className="bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-700 rounded px-3 py-1.5 text-sm font-semibold mt-1"
        >
          {tilemap.isFetching ? 'rendering…' : 'render zone'}
        </button>
        {tilemap.error && (
          <div className="text-rose-400 text-[10px] break-words mt-1">
            {String(tilemap.error)}
          </div>
        )}
        {tilemap.data && (
          <div className="text-emerald-400 text-[10px] mt-1">
            ok · {tilemap.data.terrain_layer.length} tiles · {tilemap.data.zones.length} zones
          </div>
        )}
      </div>

      {/* Layer toggles — left side under HUD */}
      <div className="absolute top-44 left-4 pointer-events-auto z-10">
        <LayerToggles />
      </div>

      {/* Metadata panel — bottom-left */}
      <div className="absolute bottom-4 left-4 pointer-events-auto z-10">
        <MetadataPanel view={tilemap.data} />
      </div>

      {/* Tile inspector — right side under render-controls */}
      <div className="absolute top-[420px] right-4 pointer-events-auto z-10">
        <TileInspector />
      </div>

      {/* Session E WS echo demo panel */}
      <EchoPanel />

      {/* Mobile + modal overlays */}
      <VirtualGamepad />
      <Modal>
        <h2 className="text-lg font-semibold mb-2 text-slate-100">Modal placeholder</h2>
        <p className="text-slate-300 text-sm">Future encounter scenes will live here.</p>
      </Modal>
      <RotatePrompt />
    </div>
  );
}
