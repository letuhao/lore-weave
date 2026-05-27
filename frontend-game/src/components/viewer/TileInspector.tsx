import { useViewerStore } from '@/store/viewer-store';
import { TerrainKind, terrainKindTag } from '@/types/tilemap';

// Side panel showing metadata for the last clicked tile.
//
// Opened by EventBus emit('inspector-open', { tile, view }) from
// InputSystem when the user holds Shift while clicking, OR via a
// future "inspector mode" toggle. For V1.2 the Shift-click path is the
// only entry; non-Shift click still triggers Player.walkTo.
// V2 — extra rows expose `terrainCell` (primitive + tag) and per-placement
// (primitive · tag · footprint · orientation) when present.

export function TileInspector(): JSX.Element | null {
  const inspector = useViewerStore((s) => s.inspector);
  const close = useViewerStore((s) => s.closeInspector);
  if (!inspector) return null;

  const terrainTag =
    inspector.terrainKind >= 1 && inspector.terrainKind <= 10
      ? terrainKindTag(inspector.terrainKind as TerrainKind)
      : '(unknown)';

  return (
    <div className="bg-slate-900/95 border border-slate-700 rounded-md p-3 text-xs text-slate-200 font-mono pointer-events-auto w-72">
      <div className="flex items-center justify-between mb-2">
        <span className="font-semibold text-sm">Tile inspector</span>
        <button
          onClick={close}
          className="text-slate-400 hover:text-slate-100 px-2"
          aria-label="close inspector"
        >
          ×
        </button>
      </div>
      <Row k="coord" v={`(${inspector.tile.x}, ${inspector.tile.y})`} />
      <Row
        k="terrain"
        v={`${terrainTag} [u8=${inspector.terrainKind}]`}
      />
      {inspector.terrainCell && (
        <Row
          k="primitive · tag"
          v={`${inspector.terrainCell.primitive} · ${inspector.terrainCell.tag}`}
        />
      )}
      <Row
        k="zone (nearest)"
        v={
          inspector.zone
            ? `${inspector.zone.id} · ${inspector.zone.role} · ${inspector.zone.terrain}`
            : '—'
        }
      />
      <Row
        k="placements"
        v={
          inspector.placementsAtTile.length === 0
            ? '—'
            : inspector.placementsAtTile
                .map(
                  (p) =>
                    `${p.kind}${p.biome_object_type ? `.${p.biome_object_type}` : ''}`,
                )
                .join(', ')
        }
      />
      {inspector.placementsAtTile.length > 0 && (
        <details className="mt-1">
          <summary className="cursor-pointer text-slate-400 text-[10px]">
            V2 placement detail
          </summary>
          <div className="mt-1 flex flex-col gap-1">
            {inspector.placementsAtTile.map((p, i) => (
              <div
                key={`${p.kind}-${i}`}
                className="border-l-2 border-slate-700 pl-2 py-0.5"
              >
                <Row k="kind" v={p.kind} />
                {p.tag && <Row k="tag" v={p.tag} />}
                {p.primitive && <Row k="primitive" v={p.primitive} />}
                {p.footprint && (
                  <Row
                    k="footprint"
                    v={`${p.footprint.width} × ${p.footprint.height}`}
                  />
                )}
                {p.orientation && <Row k="orientation" v={p.orientation} />}
                {p.value !== undefined && p.value !== null && (
                  <Row k="value" v={String(p.value)} />
                )}
              </div>
            ))}
          </div>
        </details>
      )}
      <Row
        k="road hits"
        v={String(inspector.roadHits)}
      />
      <Row
        k="river hit"
        v={inspector.riverHit ? inspector.riverHit.kind : '—'}
      />
      <div className="text-[10px] text-slate-500 mt-2">
        Shift-click a tile to inspect. Plain click walks the Player.
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }): JSX.Element {
  return (
    <div className="flex justify-between gap-2 py-0.5">
      <span className="text-slate-400">{k}</span>
      <span className="text-right break-words max-w-[60%]">{v}</span>
    </div>
  );
}
