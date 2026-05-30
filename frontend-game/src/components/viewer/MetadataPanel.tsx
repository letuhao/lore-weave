import { useMemo } from 'react';
import type { TilemapView } from '@/types/tilemap';
import {
  computeDecorationFamilyBreakdown,
  isDecorationPlacement,
} from './decoration-family-breakdown';
import { computeRoleBreakdown } from './role-breakdown';

// Compact metadata readout for the current TilemapView. Bottom-left,
// shown only when data has settled. Pure presentation — no store
// interaction.

export function MetadataPanel({ view }: { view: TilemapView | undefined }): JSX.Element | null {
  if (!view) return null;
  const objects = view.object_placements.length;
  // TMP-Q1 chunk D: count decorations separately from total placements
  // so the operator can see the visual-density pass output at a glance.
  //
  // MED-1 fix from chunk-C /review-impl — extracted to the shared
  // `isDecorationPlacement` predicate so the family breakdown and this
  // counter can never silently disagree on the population they count
  // (see [[extract-cross-surface-predicate]]).
  const decorations = view.object_placements.filter(isDecorationPlacement).length;
  // TMP-Q2 chunk C: distinct TerrainKind count across terrain_layer.
  // Used as the visible signal that BiomeThemePainter expanded the
  // single-fill-per-zone V2 baseline into multi-kind Perlin patches.
  //
  // **Metric scope (MED-1 from chunk-C /review-impl):** this counts
  // distinct kinds across ALL placers (TerrainPainter single-fill +
  // BiomeThemePainter mix + RoadPlacer + Sea-zone Water), not just
  // biome-painted tiles. The spec AC-BIOME-8 promise of
  // "biome-painted tile count" requires backend metadata to compute
  // exactly; this distinct-kind count is a practical proxy that
  // visibly grows when biome is enabled (V2 baseline ≈ 3-5, biome
  // enabled ≈ 6-8). The browser smoke pairs this with a direct
  // /render HTTP call asserting specific mix kinds present, so a
  // stale backend that silently drops biome_theme is caught.
  //
  // Excludes u8=0 (void / unpainted) since it isn't a TerrainKind.
  const distinctTerrains = new Set(
    view.terrain_layer.filter((v) => v !== 0),
  ).size;
  const roads = view.road_segments.length;
  const rivers = view.river_segments.length;
  const crossings = view.river_segments.reduce((a, r) => a + r.crossings.length, 0);

  return (
    <div className="bg-slate-900/90 border border-slate-700 rounded-md p-3 text-[11px] text-slate-200 font-mono pointer-events-auto w-72 flex flex-col gap-1">
      <div className="font-semibold text-sm mb-1">TilemapView</div>
      <Row k="template" v={view.template_id} />
      <Row k="seed" v={String(view.seed)} />
      <Row k="tier" v={view.tier} />
      <Row k="grid" v={`${view.grid_size.width} × ${view.grid_size.height}`} />
      <Row k="tiles" v={String(view.terrain_layer.length)} />
      <Row k="zones" v={String(view.zones.length)} />
      <Row k="placements" v={String(objects)} />
      <Row k="decorations" v={String(decorations)} />
      <Row k="distinct terrains" v={String(distinctTerrains)} />
      <Row k="roads / rivers" v={`${roads} / ${rivers}`} />
      <Row k="crossings" v={String(crossings)} />
      <Row k="source" v={view.generation_source.kind} />
      <Row k="prompt_v" v={String(view.prompt_template_version)} />
      {view.registry_ref && (
        <Row
          k="registry"
          v={`${view.registry_ref.id} @ ${view.registry_ref.version}`}
        />
      )}
      {view.terrain_vocabulary && (
        <Row
          k="vocab entries"
          v={String(view.terrain_vocabulary.length)}
        />
      )}
      <details className="mt-1">
        <summary className="cursor-pointer text-slate-400 text-[10px]">zones</summary>
        <div className="mt-1 max-h-32 overflow-y-auto">
          {view.zones.map((z) => (
            <div key={z.zone_id} className="flex justify-between gap-2 text-[10px]">
              <span className="text-slate-400">{z.zone_id}</span>
              <span>
                {z.zone_role} · ({z.center_position.x},{z.center_position.y}) · {z.terrain_type}
              </span>
            </div>
          ))}
        </div>
      </details>
      <RoleBreakdown view={view} />
      <DecorationFamilyBreakdown view={view} />
    </div>
  );
}

// TMP-Q5 chunk B — collapsible per-role breakdown.
//
// Reuses the `computeRoleBreakdown` pure helper that the canvas
// overlay also consumes for color lookup (MED-1 single-source-of-truth:
// canvas tint, panel swatch, and inspector swatch all agree per role).
//
// Memoized on `view` reference per chunk-C MED-2 precedent so React
// parent re-renders (HUD updates, viewer-store flips, etc.) don't
// re-walk all zones × all placements.
function RoleBreakdown({ view }: { view: TilemapView }): JSX.Element {
  const rows = useMemo(() => computeRoleBreakdown(view), [view]);
  if (rows.length === 0) {
    return (
      <details className="mt-1">
        <summary className="cursor-pointer text-slate-400 text-[10px]">
          role breakdown
        </summary>
        <div className="mt-1 text-[10px] text-slate-500">
          no zones in this view
        </div>
      </details>
    );
  }
  return (
    <details className="mt-1">
      <summary className="cursor-pointer text-slate-400 text-[10px]">
        role breakdown ({rows.length} roles · {view.zones.length} zones)
      </summary>
      <div className="mt-1 max-h-32 overflow-y-auto flex flex-col gap-0.5">
        {rows.map((row) => {
          const hex = row.color.toString(16).padStart(6, '0');
          return (
            <div
              key={row.role}
              className="flex items-center gap-1 text-[10px]"
            >
              <span
                className="inline-block w-2 h-2 rounded-full shrink-0"
                style={{ backgroundColor: `#${hex}` }}
                aria-label={`role ${row.label}`}
                // LOW from chunk-B /review-impl — testid stays for
                // chunk C's visual regression goldens + future DOM
                // tests. No vitest assertion today (TileInspector
                // pattern — chunk-C TMP-Q4 LOW-4 precedent).
                data-testid="role-band-swatch"
              />
              <span className="text-slate-400 shrink-0">{row.label}</span>
              <span className="ml-auto text-right text-[10px]">
                {row.count}
              </span>
            </div>
          );
        })}
      </div>
    </details>
  );
}

// TMP-Q6 chunk C — collapsible per-family decoration breakdown.
//
// Reuses the `computeDecorationFamilyBreakdown` pure helper for the
// row aggregation. Same `useMemo(view)` memoization discipline as
// `RoleBreakdown` so React parent re-renders don't re-walk
// `view.object_placements` on every HUD tick.
//
// Layout intentionally minimal — chunk D polish adds per-family
// color swatches / icons. Today: family · count (percent%).
function DecorationFamilyBreakdown({
  view,
}: {
  view: TilemapView;
}): JSX.Element {
  const rows = useMemo(
    () => computeDecorationFamilyBreakdown(view, view.registry_ref ?? null),
    [view],
  );
  if (rows.length === 0) {
    return (
      <details className="mt-1">
        <summary className="cursor-pointer text-slate-400 text-[10px]">
          decoration families
        </summary>
        <div
          className="mt-1 text-[10px] text-slate-500"
          data-testid="decoration-family-empty-state"
        >
          no decorations placed yet
        </div>
      </details>
    );
  }
  const totalDecorations = rows.reduce((sum, r) => sum + r.count, 0);
  return (
    <details className="mt-1">
      <summary className="cursor-pointer text-slate-400 text-[10px]">
        decoration families ({rows.length} families · {totalDecorations}{' '}
        decorations)
      </summary>
      <div
        className="mt-1 max-h-32 overflow-y-auto flex flex-col gap-0.5"
        data-testid="decoration-family-breakdown"
      >
        {rows.map((row) => (
          <div
            key={row.family}
            className="flex items-center gap-1 text-[10px]"
            data-testid="decoration-family-row"
          >
            <span className="text-slate-400 shrink-0">{row.family}</span>
            <span className="ml-auto text-right text-[10px]">
              {row.count} ({row.percent.toFixed(1)}%)
            </span>
          </div>
        ))}
      </div>
    </details>
  );
}

function Row({ k, v }: { k: string; v: string }): JSX.Element {
  return (
    <div className="flex justify-between gap-2">
      <span className="text-slate-400">{k}</span>
      <span className="text-right break-words max-w-[60%]">{v}</span>
    </div>
  );
}
