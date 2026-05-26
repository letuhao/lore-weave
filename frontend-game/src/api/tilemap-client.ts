// HTTP client for tilemap-service.
//
// V0 ships `useTilemapHealth` (livez probe).
// V1 rescope adds `useZoneTilemap` posting to
// `POST /internal/v1/tilemaps/render` with a baked-in template fixture
// from `/public/templates/minimal.json`. Spec:
// `docs/specs/2026-05-24-v1-tilemap-viewer-rescope.md` §4–§5.
//
// SECURITY: bearer token from `SERVICES.devToken` is the same dev-only
// internal token as V0 EchoPanel. Bundles into client JS. Tracked
// in DEFERRED #033 — V1.5 / V2 replaces with auth-service JWT.

import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { queryKeys } from './query-keys';
import { SERVICES } from '@/config/services';
import type { ChannelTier, RenderRequest, TileMask, TilemapView } from '@/types/tilemap';

const TILEMAP_SERVICE_BASE = SERVICES.tilemap;

/**
 * BigInt-aware `TilemapView` parser. The backend `zones[].assigned_tiles`
 * field is a `TileMask` whose `bits` array contains u64 values that may
 * exceed 2^53 — JS `JSON.parse` silently truncates to IEEE 754 floats
 * and loses low-order bits, which would scramble per-tile bitmap reads.
 *
 * Strategy: regex-tag every `"bits": [n0, n1, ...]` array in the raw
 * response text so JSON.parse reads each u64 as a STRING; then post-
 * convert each string to BigInt while building the `TileMask` shape.
 *
 * Limit of the regex: it relies on the response NOT containing the
 * literal `"bits":` key anywhere outside a TileMask array. The backend
 * uses this key only in `TileMask`, so the assumption holds.
 *
 * Exported for unit testing.
 */
export function parseTilemapView(text: string): TilemapView {
  // Wrap every numeric element of any `"bits": [...]` array in quotes.
  const tagged = text.replace(/"bits"\s*:\s*\[([^\]]*)\]/g, (_match, body: string) => {
    const items = body
      .split(/\s*,\s*/)
      .map((tok) => tok.trim())
      .filter((tok) => tok.length > 0)
      .map((tok) => `"${tok}"`)
      .join(',');
    return `"bits":[${items}]`;
  });
  const parsed = JSON.parse(tagged) as TilemapView & {
    zones: Array<{
      assigned_tiles?: { width: number; height: number; bits: string[] };
    } & Record<string, unknown>>;
  };
  for (const zone of parsed.zones ?? []) {
    const at = zone.assigned_tiles;
    if (at && Array.isArray(at.bits)) {
      const bits: bigint[] = at.bits.map((s) => BigInt(s));
      const mask: TileMask = { width: at.width, height: at.height, bits };
      (zone as unknown as { assigned_tiles: TileMask }).assigned_tiles = mask;
    }
  }
  return parsed as unknown as TilemapView;
}

export interface TilemapHealth {
  status: 'ok' | 'down';
  endpoint: string;
  service: string;
}

export function useTilemapHealth(): UseQueryResult<TilemapHealth> {
  return useQuery({
    queryKey: queryKeys.health.tilemap(),
    queryFn: async (): Promise<TilemapHealth> => {
      const res = await fetch(`${TILEMAP_SERVICE_BASE}/livez`);
      if (!res.ok) {
        return { status: 'down', endpoint: 'livez', service: 'tilemap-service' };
      }
      return (await res.json()) as TilemapHealth;
    },
    refetchInterval: 10_000,
  });
}

export interface UseZoneTilemapParams {
  seed: number;
  gridWidth: number;
  gridHeight: number;
  tier: ChannelTier;
  /** Static fixture path under /public — default minimal 5-zone fixture. */
  templateUrl?: string;
  /** Channel id for the render call. Default `ch_v1_viewer`. */
  channelId?: string;
}

const DEFAULT_TEMPLATE_URL = '/templates/minimal.json';
const DEFAULT_CHANNEL_ID = 'ch_v1_viewer';

/**
 * Fetches a fresh `TilemapView` for the given parameters.
 *
 * Two-step: first GETs the bundled `TilemapTemplate` JSON from
 * `/public/templates/`, then POSTs the full RenderRequest to
 * `tilemap-service /internal/v1/tilemaps/render`. TanStack cache key
 * is `[tilemap, zone, tier, w, h, seed]` so changing the seed input
 * in the UI triggers a fresh render (and the prior view stays in
 * cache for "back" navigation).
 */
export function useZoneTilemap(params: UseZoneTilemapParams): UseQueryResult<TilemapView> {
  const templateUrl = params.templateUrl ?? DEFAULT_TEMPLATE_URL;
  const channelId = params.channelId ?? DEFAULT_CHANNEL_ID;
  return useQuery({
    queryKey: queryKeys.tilemap.zone({
      seed: params.seed,
      gridWidth: params.gridWidth,
      gridHeight: params.gridHeight,
      tier: params.tier,
    }),
    queryFn: async (): Promise<TilemapView> => {
      const templateRes = await fetch(templateUrl);
      if (!templateRes.ok) {
        throw new Error(`failed to load template fixture: ${templateRes.status}`);
      }
      const template = (await templateRes.json()) as unknown;

      const body: RenderRequest = {
        template,
        channel_id: channelId,
        tier: params.tier,
        grid_size: { width: params.gridWidth, height: params.gridHeight },
        seed: params.seed,
      };

      const renderRes = await fetch(`${TILEMAP_SERVICE_BASE}/internal/v1/tilemaps/render`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${SERVICES.devToken}`,
        },
        body: JSON.stringify(body),
      });
      if (!renderRes.ok) {
        const detail = await renderRes.text();
        throw new Error(`tilemap render failed: ${renderRes.status} ${detail}`);
      }
      const text = await renderRes.text();
      return parseTilemapView(text);
    },
    refetchOnWindowFocus: false,
    staleTime: Infinity,
  });
}
