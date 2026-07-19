import { useViewerStore, type ViewerLayer } from '@/store/viewer-store';
import type { JSX } from 'react';

// 8 checkboxes (L0..L7). Wired to viewer-store; WorldScene subscribes
// to the store and toggles per-layer visibility without re-fetching
// from backend.
//
// L5 zone_boundaries shown disabled — implementation deferred V2
// (needs BigInt JSON reviver for u64 bitmap; see render-strategy spec).

const LAYERS: ReadonlyArray<{
  key: ViewerLayer;
  label: string;
  disabled?: boolean;
  hint?: string;
}> = [
  { key: 'foundation', label: 'L0 Foundation' },
  { key: 'paths', label: 'L1/L2 Roads + Rivers + Crossings' },
  { key: 'objects', label: 'L4 Objects (props)' },
  { key: 'zone_boundaries', label: 'L5 Zone boundaries' },
  { key: 'zone_centers', label: 'L6 Zone centers' },
  { key: 'player', label: 'L7 Player' },
];

export function LayerToggles(): JSX.Element {
  const visibleLayers = useViewerStore((s) => s.visibleLayers);
  const setLayer = useViewerStore((s) => s.setLayer);
  const blendEnabled = useViewerStore((s) => s.blendEnabled);
  const setBlendEnabled = useViewerStore((s) => s.setBlendEnabled);
  const showTreasureBands = useViewerStore((s) => s.showTreasureBands);
  const setShowTreasureBands = useViewerStore((s) => s.setShowTreasureBands);
  return (
    <div className="bg-slate-900/90 border border-slate-700 rounded-md p-3 text-xs text-slate-200 font-mono pointer-events-auto flex flex-col gap-1.5 w-64">
      <div className="font-semibold text-sm mb-1">Layers</div>
      {LAYERS.map((l) => (
        <label
          key={l.key}
          className={`flex items-center gap-2 ${l.disabled ? 'opacity-50' : 'cursor-pointer hover:bg-slate-800/60 rounded px-1'}`}
          title={l.hint}
        >
          <input
            type="checkbox"
            checked={!!visibleLayers[l.key]}
            onChange={(e) => setLayer(l.key, e.target.checked)}
            disabled={l.disabled}
            className="accent-indigo-500"
          />
          <span>{l.label}</span>
          {l.hint && <span className="text-[10px] text-slate-500 ml-auto">{l.hint}</span>}
        </label>
      ))}
      {/* TMP-Q3 chunk A — Stage-1 smooth-blend polish toggle. Off = V0
          hard-pixel rendering. Chunk B will swap the Blur for a true
          cross-tile shader behind the same flag.
          COSMETIC-1 fix from chunk-A /review-impl: separate "Polish"
          subsection from Layers with a top border + extra spacing so
          first-time users don't mistake the blend checkbox for an
          L-something layer toggle. */}
      <div className="mt-3 pt-2 border-t border-slate-700 font-semibold text-sm mb-1">
        Polish
      </div>
      <label
        className="flex items-center gap-2 cursor-pointer hover:bg-slate-800/60 rounded px-1"
        title="Phaser 4 Blur filter on the foundation tilemap. Disable for crisp pixel-art mode."
      >
        <input
          type="checkbox"
          checked={blendEnabled}
          onChange={(e) => setBlendEnabled(e.target.checked)}
          className="accent-indigo-500"
        />
        <span>Smooth blend</span>
      </label>
      {/* TMP-Q4 chunk C — zone-tier treasure-band overlay toggle.
          Default OFF: tints each zone with its max-tier band color
          for at-a-glance economy review. Independent of "Smooth blend"
          and L0..L7 layer toggles. */}
      <label
        className="flex items-center gap-2 cursor-pointer hover:bg-slate-800/60 rounded px-1"
        title="Translucent tint per zone reflecting its highest treasure tier band."
      >
        <input
          type="checkbox"
          checked={showTreasureBands}
          onChange={(e) => setShowTreasureBands(e.target.checked)}
          className="accent-indigo-500"
        />
        <span>Treasure bands</span>
      </label>
    </div>
  );
}
