import { useTranslation } from 'react-i18next';
import { MapPin } from 'lucide-react';
import { useWorldMaps } from '../hooks/useWorldMaps';

// W10 maps canvas — renders a world's map(s): the base image with region polygons +
// marker pins overlaid, all positioned from NORMALIZED (0..1) coordinates so the
// overlay tracks the image at any size. View-only; the world_map_* agent tools
// (Tier-W) are the only write path. Logic lives in useWorldMaps; this renders.
export function WorldMapsSection({ worldId }: { worldId: string | undefined }) {
  const { t } = useTranslation('world');
  const { maps, selectedId, select, detail, isLoading } = useWorldMaps(worldId);

  if (isLoading) return null;
  if (maps.length === 0) {
    return (
      <section className="space-y-2" data-testid="world-maps-section">
        <h2 className="font-medium">{t('maps.heading', { defaultValue: 'Maps' })}</h2>
        <p className="text-xs text-muted-foreground" data-testid="world-maps-empty">
          {t('maps.empty', {
            defaultValue: 'No maps yet. Ask the assistant to “make a map of this world” to create one.',
          })}
        </p>
      </section>
    );
  }

  const map = detail?.map;
  const markers = detail?.markers ?? [];
  const regions = detail?.regions ?? [];

  return (
    <section className="space-y-2" data-testid="world-maps-section">
      <h2 className="font-medium">{t('maps.heading', { defaultValue: 'Maps' })}</h2>
      {maps.length > 1 && (
        <div className="flex flex-wrap gap-1" data-testid="world-maps-picker">
          {maps.map((m) => (
            <button
              key={m.map_id}
              onClick={() => select(m.map_id)}
              data-testid={`world-map-tab-${m.map_id}`}
              className={`rounded-md px-2 py-1 text-xs ${
                m.map_id === selectedId ? 'bg-muted font-semibold' : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {m.name}
            </button>
          ))}
        </div>
      )}

      <div
        className="relative w-full overflow-hidden rounded-md border bg-muted/30"
        data-testid="world-map-canvas"
        data-map-id={map?.map_id}
      >
        {map?.image_url ? (
          <img src={map.image_url} alt={map.name} className="block w-full" />
        ) : (
          // No base image uploaded yet — still show the pins/regions on a neutral field so
          // the map is usable (and never a blank box that reads as "broken").
          <div className="aspect-[16/9] w-full" />
        )}

        {/* Region polygons — normalized (0..1) points scaled into a 0..100 viewBox that
            stretches with the image (preserveAspectRatio none). */}
        {regions.length > 0 && (
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
          </svg>
        )}

        {/* Marker pins — absolutely positioned by normalized coords. */}
        {markers.map((m) => (
          <div
            key={m.marker_id}
            className="absolute -translate-x-1/2 -translate-y-full"
            style={{ left: `${m.x * 100}%`, top: `${m.y * 100}%` }}
            data-testid={`world-map-marker-${m.marker_id}`}
            title={m.label}
          >
            <MapPin className="h-4 w-4 text-primary drop-shadow" />
            <span className="absolute left-1/2 top-4 -translate-x-1/2 whitespace-nowrap rounded bg-background/80 px-1 text-[10px] leading-tight">
              {m.label}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
