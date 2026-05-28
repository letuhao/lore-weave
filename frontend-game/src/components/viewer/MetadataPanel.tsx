import type { TilemapView } from '@/types/tilemap';

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
    </div>
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
