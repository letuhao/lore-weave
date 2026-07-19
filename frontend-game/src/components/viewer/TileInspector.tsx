import type { JSX, ReactNode } from 'react';
import { useViewerStore } from '@/store/viewer-store';
import { TerrainKind, terrainKindTag } from '@/types/tilemap';
import {
  bandColor,
  bandLabel,
  pickValueBand,
  shouldStampBadge,
} from '@/game/render/treasure-badge';

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
            {inspector.placementsAtTile.map((p, i) => {
              // TMP-Q4 chunk B — treasure section only renders when the
              // badge gate fires (LOW-2 + LOW-5 from chunk-B /review-impl:
              // single source of truth for "is this a treasure pile?",
              // covers V1 `kind` AND V2 `primitive` paths). Guards
              // (`monster_lair`) inherit `tier_index` but never badge.
              const stampsBadge = shouldStampBadge(p);
              const isGuardWithTier =
                p.kind === 'monster_lair' && p.tier_index != null;
              return (
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
                  {/* Generic value row for non-treasure placements
                      (lair strength, etc.). COSMETIC-1 simplification:
                      `!= null` catches both null and undefined. */}
                  {!stampsBadge && p.value != null && (
                    <Row k="value" v={String(p.value)} />
                  )}
                  {/* TMP-Q4 treasure section */}
                  {stampsBadge && p.value != null && (
                    <>
                      <Row k="treasure value" v={`${p.value} gold`} />
                      {p.tier_index != null && (
                        <Row
                          k="treasure tier"
                          v={`tier ${p.tier_index} (in zone)`}
                        />
                      )}
                      <BandRow
                        value={p.value}
                        thresholds={inspector.valueBandThresholds}
                      />
                    </>
                  )}
                  {/* TMP-Q4 guard tier row (no band — value is strength, not gold) */}
                  {isGuardWithTier && (
                    <Row
                      k="guard tier"
                      v={`tier ${p.tier_index} (in zone, inherited)`}
                    />
                  )}
                </div>
              );
            })}
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

function Row({ k, v }: { k: string; v: ReactNode }): JSX.Element {
  return (
    <div className="flex justify-between gap-2 py-0.5">
      <span className="text-slate-400">{k}</span>
      <span className="text-right break-words max-w-[60%]">{v}</span>
    </div>
  );
}

// TMP-Q4 chunk B — band swatch + label row. Color sourced from the
// shared `bandColor` helper so it stays consistent with the canvas
// badge (object-overlay.ts also calls `bandColor(pickValueBand(...))`).
function BandRow({
  value,
  thresholds,
}: {
  value: number;
  thresholds: readonly [number, number, number, number] | null;
}): JSX.Element {
  const band = pickValueBand(value, thresholds);
  const hex = bandColor(band).toString(16).padStart(6, '0');
  return (
    <Row
      k="band"
      v={
        <span className="inline-flex items-center gap-1">
          <span
            className="inline-block w-2 h-2 rounded-full"
            style={{ backgroundColor: `#${hex}` }}
            // LOW-4 from chunk-B /review-impl — the testid stays for
            // chunk C's visual regression goldens to anchor against.
            // No vitest assertion today (would require @testing-library
            // /react render + Zustand setup; chunk C's screenshot diff
            // pins the rendered DOM more economically).
            data-testid="band-swatch"
          />
          <span>{bandLabel(band)}</span>
        </span>
      }
    />
  );
}
