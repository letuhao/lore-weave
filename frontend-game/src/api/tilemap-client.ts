// HTTP client for tilemap-service. Session D wires the real fetch to
// `localhost:8220/tilemaps/render` (V0 direct hit per spec §19; V1+
// routes through api-gateway-bff).
//
// Session D AC-FG-8: fetch `/livez` and display "tilemap-service: ok"
// via TanStack Query.

import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { queryKeys } from './query-keys';

const TILEMAP_SERVICE_BASE = 'http://localhost:8220';

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
