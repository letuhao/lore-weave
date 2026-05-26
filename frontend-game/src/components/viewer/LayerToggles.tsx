import { useViewerStore, type ViewerLayer } from '@/store/viewer-store';

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
    </div>
  );
}
