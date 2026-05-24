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
import type { ChannelTier, RenderRequest, TilemapView } from '@/types/tilemap';

const TILEMAP_SERVICE_BASE = SERVICES.tilemap;

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
      return (await renderRes.json()) as TilemapView;
    },
    refetchOnWindowFocus: false,
    staleTime: Infinity,
  });
}
