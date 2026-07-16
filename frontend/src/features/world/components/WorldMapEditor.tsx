import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { MapPin } from 'lucide-react';
import type { WorldMapMarker, WorldMapRegion } from '../types';
import { useWorldMapEditor, type EditorMode } from '../hooks/useWorldMapEditor';

// S7·2 — the world-map editor VIEW (MVC "view"): tool rail + map rail + canvas + marker popover.
// Render-only; all logic (selection, writes, optimistic drag) lives in useWorldMapEditor. Reuses
// WorldMapsSection's overlay math: regions in a 0..100 viewBox (preserveAspectRatio none), pins
// absolutely positioned by normalized coords. Adds drag, click-to-drop, region drawing, and the
// relabel/rebind/unbind/delete popover.

type Ctl = ReturnType<typeof useWorldMapEditor>;

/** Normalized [0,1] canvas coords from a pointer event, clamped so a drag off-canvas stays valid. */
function coordsFromEvent(el: HTMLElement, clientX: number, clientY: number): { x: number; y: number } {
  const rect = el.getBoundingClientRect();
  const x = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
  const y = Math.min(1, Math.max(0, (clientY - rect.top) / rect.height));
  return { x, y };
}

export function WorldMapEditor({ ctl }: { ctl: Ctl }) {
  const { t } = useTranslation('world');

  if (ctl.needsWorldPicker) {
    return <WorldPicker ctl={ctl} t={t} />;
  }
  if (ctl.isError) {
    return (
      <div data-testid="world-map-error" className="p-4 text-sm text-rose-600">
        {t('mapEditor.error', { defaultValue: 'Could not load this map.' })}
      </div>
    );
  }
  if (ctl.isEmpty) {
    return (
      <div data-testid="world-map-empty" className="flex flex-col items-center gap-3 p-8 text-center text-sm">
        <p className="text-muted-foreground">
          {t('mapEditor.empty', { defaultValue: 'No maps yet — draw the world your story lives in.' })}
        </p>
        <CreateMapButton ctl={ctl} t={t} />
      </div>
    );
  }

  return (
    <div data-testid="world-map-editor" className="flex h-full min-h-0 flex-col">
      <ToolRail ctl={ctl} t={t} />
      <div className="flex min-h-0 flex-1">
        <MapRail ctl={ctl} t={t} />
        <div className="relative min-w-0 flex-1 p-2">
          <Canvas ctl={ctl} />
        </div>
      </div>
      <Footer ctl={ctl} />
      {ctl.selectedMarker && <MarkerPopover ctl={ctl} marker={ctl.selectedMarker} t={t} />}
    </div>
  );
}

function ToolRail({ ctl, t }: { ctl: Ctl; t: (k: string, o?: Record<string, unknown>) => string }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const modes: EditorMode[] = ['select', 'pin', 'region'];
  return (
    <div className="flex flex-wrap items-center gap-2 border-b p-2" data-testid="world-map-toolrail">
      <div className="inline-flex overflow-hidden rounded-md border">
        {modes.map((m) => (
          <button
            key={m}
            type="button"
            data-testid={`world-map-mode-${m}`}
            aria-pressed={ctl.mode === m}
            onClick={() => ctl.setMode(m)}
            className={`px-3 py-1 text-xs ${ctl.mode === m ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'}`}
          >
            {t(`mapEditor.mode.${m}`, { defaultValue: m })}
          </button>
        ))}
      </div>
      <button
        type="button"
        data-testid="world-map-upload"
        disabled={!ctl.selectedMapId}
        onClick={() => fileRef.current?.click()}
        className="rounded-md border px-2 py-1 text-xs disabled:opacity-50"
      >
        {t('mapEditor.uploadImage', { defaultValue: 'Upload base image' })}
      </button>
      <input
        ref={fileRef}
        type="file"
        accept="image/png,image/jpeg,image/gif,image/webp"
        className="hidden"
        data-testid="world-map-file-input"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) ctl.uploadImage.mutate(f);
          e.target.value = '';
        }}
      />
    </div>
  );
}

function MapRail({ ctl, t }: { ctl: Ctl; t: (k: string, o?: Record<string, unknown>) => string }) {
  return (
    <aside className="w-40 shrink-0 overflow-auto border-r p-2 text-xs" data-testid="world-map-rail">
      <ul className="flex flex-col gap-1">
        {ctl.maps.map((m) => (
          <li key={m.map_id}>
            <button
              type="button"
              data-testid={`world-map-tab-${m.map_id}`}
              onClick={() => ctl.selectMap(m.map_id)}
              className={`w-full rounded px-2 py-1 text-left ${m.map_id === ctl.selectedMapId ? 'bg-muted font-semibold' : 'hover:bg-muted/50'}`}
            >
              {m.name}
            </button>
          </li>
        ))}
      </ul>
      <div className="mt-2">
        <CreateMapButton ctl={ctl} t={t} />
      </div>
    </aside>
  );
}

function CreateMapButton({ ctl, t }: { ctl: Ctl; t: (k: string, o?: Record<string, unknown>) => string }) {
  return (
    <button
      type="button"
      data-testid="world-map-new"
      onClick={() => {
        const name = window.prompt(t('mapEditor.newMapPrompt', { defaultValue: 'Name the new map' }));
        if (name && name.trim()) ctl.createMap.mutate(name.trim());
      }}
      className="rounded-md border border-dashed px-2 py-1 text-xs text-muted-foreground hover:text-foreground"
    >
      {t('mapEditor.newMap', { defaultValue: '+ New map' })}
    </button>
  );
}

function Canvas({ ctl }: { ctl: Ctl }) {
  const canvasRef = useRef<HTMLDivElement>(null);
  const [dragId, setDragId] = useState<string | null>(null);
  const [draft, setDraft] = useState<number[][]>([]); // region-mode vertices in progress

  const onCanvasClick = (e: React.MouseEvent) => {
    if (!canvasRef.current || !ctl.selectedMapId) return;
    const { x, y } = coordsFromEvent(canvasRef.current, e.clientX, e.clientY);
    if (ctl.mode === 'pin') {
      ctl.addMarker.mutate(
        { label: 'New marker', x, y },
        { onSuccess: (res) => ctl.setSelectedMarkerId(res.marker.marker_id) },
      );
    } else if (ctl.mode === 'region') {
      setDraft((d) => [...d, [x, y]]);
    }
  };

  const onPinPointerDown = (markerId: string) => (e: React.PointerEvent) => {
    if (ctl.mode !== 'select') return;
    e.stopPropagation();
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    setDragId(markerId);
    ctl.setSelectedMarkerId(markerId);
  };
  const onPinPointerMove = (markerId: string) => (e: React.PointerEvent) => {
    if (dragId !== markerId || !canvasRef.current) return;
    const { x, y } = coordsFromEvent(canvasRef.current, e.clientX, e.clientY);
    // Optimistic move happens in the mutation onMutate; here we only fire on release to avoid a
    // PATCH per frame — but we do update the visual via the mutation cache on drop.
    (e.currentTarget as HTMLElement).dataset.dragX = String(x);
    (e.currentTarget as HTMLElement).dataset.dragY = String(y);
  };
  const onPinPointerUp = (markerId: string) => (e: React.PointerEvent) => {
    if (dragId !== markerId || !canvasRef.current) return;
    const { x, y } = coordsFromEvent(canvasRef.current, e.clientX, e.clientY);
    setDragId(null);
    ctl.moveMarker.mutate({ markerId, x, y });
  };

  const finishRegion = () => {
    if (draft.length >= 3) {
      ctl.addRegion.mutate({ name: 'New region', polygon: draft });
    }
    setDraft([]);
  };

  const map = ctl.map;
  return (
    <div className="flex h-full flex-col gap-2">
      {ctl.mode === 'region' && draft.length > 0 && (
        <div className="flex items-center gap-2 text-xs">
          <span data-testid="world-map-region-draft">{draft.length} pts</span>
          <button
            type="button"
            data-testid="world-map-region-finish"
            disabled={draft.length < 3}
            onClick={finishRegion}
            className="rounded border px-2 py-0.5 disabled:opacity-50"
          >
            Finish region
          </button>
          <button type="button" onClick={() => setDraft([])} className="rounded border px-2 py-0.5">
            Cancel
          </button>
        </div>
      )}
      <div
        ref={canvasRef}
        onClick={onCanvasClick}
        className="relative w-full flex-1 overflow-hidden rounded-md border bg-muted/30"
        data-testid="world-map-canvas"
        data-map-id={map?.map_id}
        style={{ cursor: ctl.mode === 'select' ? 'default' : 'crosshair' }}
      >
        {map?.image_url ? (
          <img src={map.image_url} alt={map.name} className="pointer-events-none block h-full w-full object-contain" />
        ) : (
          <div className="flex h-full min-h-[240px] w-full items-center justify-center text-xs text-muted-foreground">
            <span data-testid="world-map-no-image">No base image — upload one, or place pins on the field.</span>
          </div>
        )}

        <RegionOverlay regions={ctl.regions} draft={draft} />

        {ctl.markers.map((m) => (
          <button
            key={m.marker_id}
            type="button"
            data-testid={`world-map-marker-${m.marker_id}`}
            data-entity-bound={m.entity_id ? 'true' : undefined}
            onPointerDown={onPinPointerDown(m.marker_id)}
            onPointerMove={onPinPointerMove(m.marker_id)}
            onPointerUp={onPinPointerUp(m.marker_id)}
            onClick={(e) => {
              e.stopPropagation();
              ctl.setSelectedMarkerId(m.marker_id);
            }}
            className="absolute -translate-x-1/2 -translate-y-full"
            style={{ left: `${m.x * 100}%`, top: `${m.y * 100}%`, touchAction: 'none' }}
            title={m.label}
          >
            <MapPin className={`h-4 w-4 drop-shadow ${m.entity_id ? 'text-violet-500' : 'text-primary'}`} />
            <span className="absolute left-1/2 top-4 -translate-x-1/2 whitespace-nowrap rounded bg-background/80 px-1 text-[10px] leading-tight">
              {m.label}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

function RegionOverlay({ regions, draft }: { regions: WorldMapRegion[]; draft: number[][] }) {
  return (
    <svg
      className="pointer-events-none absolute inset-0 h-full w-full"
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      data-testid="world-map-regions"
    >
      {regions.map((r) => (
        <polygon
          key={r.region_id}
          points={r.polygon.map(([x, y]) => `${x * 100},${y * 100}`).join(' ')}
          className="fill-primary/15 stroke-primary/60"
          strokeWidth={0.4}
        >
          <title>{r.name}</title>
        </polygon>
      ))}
      {draft.length > 0 && (
        <polyline
          points={draft.map(([x, y]) => `${x * 100},${y * 100}`).join(' ')}
          className="fill-none stroke-amber-500"
          strokeWidth={0.5}
          strokeDasharray="1 1"
        />
      )}
    </svg>
  );
}

function Footer({ ctl }: { ctl: Ctl }) {
  return (
    <div className="border-t px-3 py-1 text-[11px] text-muted-foreground" data-testid="world-map-footer">
      {ctl.markers.length} pins · {ctl.regions.length} regions · owner-scoped
    </div>
  );
}

function MarkerPopover({
  ctl,
  marker,
  t,
}: {
  ctl: Ctl;
  marker: WorldMapMarker;
  t: (k: string, o?: Record<string, unknown>) => string;
}) {
  const [label, setLabel] = useState(marker.label);
  const [entityId, setEntityId] = useState(marker.entity_id ?? '');
  const [source, setSource] = useState<'glossary' | 'kg'>('glossary');
  return (
    <div
      data-testid="world-map-marker-popover"
      className="absolute right-4 top-16 z-10 w-64 space-y-2 rounded-md border bg-background p-3 text-xs shadow-lg"
    >
      <div className="flex items-center justify-between">
        <span className="font-semibold">{t('mapEditor.marker', { defaultValue: 'Marker' })}</span>
        <button type="button" onClick={() => ctl.setSelectedMarkerId(null)} aria-label="close">
          ×
        </button>
      </div>
      <label className="block">
        {t('mapEditor.label', { defaultValue: 'Label' })}
        <input
          data-testid="world-map-marker-label"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          className="mt-0.5 w-full rounded border px-1 py-0.5"
        />
      </label>
      {/* 🔒 SEALED PO#2 — bind a glossary `location` OR a KG entity; the source is LABELLED so the
          user knows which layer this pin ties into. Soft untyped entity_id (no FK). */}
      <div className="space-y-1">
        <div className="flex items-center gap-1">
          <span>{t('mapEditor.bind', { defaultValue: 'Bind entity' })}</span>
          <select
            data-testid="world-map-marker-source"
            value={source}
            onChange={(e) => setSource(e.target.value as 'glossary' | 'kg')}
            className="rounded border px-1"
          >
            <option value="glossary">glossary</option>
            <option value="kg">KG</option>
          </select>
        </div>
        <input
          data-testid="world-map-marker-entity"
          value={entityId}
          placeholder={t('mapEditor.entityPlaceholder', { defaultValue: 'location entity id' })}
          onChange={(e) => setEntityId(e.target.value)}
          className="w-full rounded border px-1 py-0.5"
        />
      </div>
      <div className="flex flex-wrap gap-2 pt-1">
        <button
          type="button"
          data-testid="world-map-marker-save"
          onClick={() =>
            ctl.patchMarker.mutate({
              markerId: marker.marker_id,
              payload: { label, entity_id: entityId.trim() || null },
            })
          }
          className="rounded bg-primary px-2 py-0.5 text-primary-foreground"
        >
          {t('mapEditor.save', { defaultValue: 'Save' })}
        </button>
        <button
          type="button"
          data-testid="world-map-marker-unbind"
          onClick={() => ctl.patchMarker.mutate({ markerId: marker.marker_id, payload: { entity_id: null } })}
          className="rounded border px-2 py-0.5"
        >
          {t('mapEditor.unbind', { defaultValue: 'Unbind' })}
        </button>
        <button
          type="button"
          data-testid="world-map-marker-delete"
          onClick={() => ctl.deleteMarker.mutate(marker.marker_id)}
          className="rounded border border-rose-300 px-2 py-0.5 text-rose-600"
        >
          {t('mapEditor.delete', { defaultValue: 'Delete' })}
        </button>
      </div>
    </div>
  );
}

function WorldPicker({ ctl, t }: { ctl: Ctl; t: (k: string, o?: Record<string, unknown>) => string }) {
  return (
    <div data-testid="world-map-world-picker" className="flex flex-col gap-2 p-4 text-sm">
      <p className="text-muted-foreground">{t('mapEditor.pickWorld', { defaultValue: 'Pick a world to map.' })}</p>
      <ul className="flex flex-col gap-1">
        {ctl.worldOptions.map((w) => (
          <li key={w.world_id}>
            <button
              type="button"
              data-testid={`world-map-world-${w.world_id}`}
              onClick={() => ctl.pickWorld(w.world_id)}
              className="w-full rounded border px-2 py-1 text-left hover:bg-muted/50"
            >
              {w.name}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
