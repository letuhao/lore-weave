import { useMemo } from 'react';
import type { TilemapView } from '@/types/tilemap';
import { computeZoneBreakdown } from './zone-breakdown';
import type { JSX } from 'react';

// Compact metadata readout for the current TilemapView. Bottom-left,
// shown only when data has settled. Pure presentation — no store
// interaction.

export function MetadataPanel({ view }: { view: TilemapView | undefined }): JSX.Element | null {
  if (!view) return null;
  const objects = view.object_placements.length;
  // TMP-Q1 chunk D: count decorations separately from total placements
  // so the operator can see the visual-density pass output at a glance.
  //
  // Filter rationale: V2+ chunk-C placer always sets BOTH primitive and
  // kind to Decoration, so either check alone catches today's data. The
  // OR is forward-compat for two cases:
  // (1) pre-V2 fixtures (no primitive field) — kind match is the
  //     fallback path
  // (2) future per-book registries that declare new kinds with
  //     primitive: Decoration semantics — primitive is the SoT
  // Confirmed at LOW-4 from chunk-D /review-impl.
  const decorations = view.object_placements.filter(
    (p) => p.primitive === 'decoration' || p.kind === 'decoration',
  ).length;
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
      <TreasureBreakdown view={view} />
    </div>
  );
}

// TMP-Q4 chunk C — collapsible per-zone treasure breakdown table.
// Reuses the same `computeZoneBreakdown` pure helper the canvas overlay
// consumes (MED-1 single-source-of-truth: the panel value-count, the
// panel band swatch, AND the canvas overlay color all agree per zone).
//
// Sorts: total_value desc, zone_id asc tiebreaker. Empty zones (LOW-1)
// are omitted upstream.
function TreasureBreakdown({ view }: { view: TilemapView }): JSX.Element | null {
  // MED-2 from chunk-C /review-impl: memoize on the `view` reference so
  // React parent re-renders (HUD updates, viewer-store flips, etc.)
  // don't re-walk all placements × all zones. The view reference only
  // changes on tilemap refetch, so the memo is stable.
  const rows = useMemo(() => computeZoneBreakdown(view), [view]);
  if (rows.length === 0) {
    // Surface the empty state so the operator knows the panel rendered
    // (it tried) AND that the rendered fixture had no treasures — not
    // a regression where the section silently failed to render.
    return (
      <details className="mt-1">
        <summary className="cursor-pointer text-slate-400 text-[10px]">
          treasure breakdown
        </summary>
        <div className="mt-1 text-[10px] text-slate-500">
          no treasure placed in this view
        </div>
      </details>
    );
  }
  const totalAll = rows.reduce((sum, r) => sum + r.total_value, 0);
  return (
    <details className="mt-1">
      <summary className="cursor-pointer text-slate-400 text-[10px]">
        treasure breakdown ({rows.length} zones · Σ {totalAll} gold)
      </summary>
      <div className="mt-1 max-h-32 overflow-y-auto flex flex-col gap-0.5">
        {rows.map((row) => {
          const hex = row.color.toString(16).padStart(6, '0');
          return (
            <div
              key={row.zone_id}
              className="flex items-center gap-1 text-[10px]"
            >
              <span
                className="inline-block w-2 h-2 rounded-full shrink-0"
                style={{ backgroundColor: `#${hex}` }}
                aria-label={`band ${row.band_name}`}
                data-testid="breakdown-band-swatch"
              />
              <span className="text-slate-400 shrink-0">{row.zone_id}</span>
              <span className="text-slate-500 shrink-0 text-[9px]">
                ({row.zone_role})
              </span>
              <span className="ml-auto text-right text-[10px]">
                {row.pile_count} · Σ {row.total_value}
              </span>
            </div>
          );
        })}
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
