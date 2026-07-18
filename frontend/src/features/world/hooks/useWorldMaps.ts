import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { worldsApi } from '../api';

// W10 maps controller — owns the map list + the selected map's detail (image +
// markers + regions). View-only: renders what the world_map_* agent tools wrote.
// The selected map defaults to the first once the list loads.
export function useWorldMaps(worldId: string | undefined) {
  const { accessToken } = useAuth();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const list = useQuery({
    queryKey: ['world-maps', worldId],
    queryFn: () => worldsApi.listWorldMaps(accessToken!, worldId!),
    enabled: !!accessToken && !!worldId,
  });

  const maps = list.data?.items ?? [];
  // Resolve the effective selection: explicit pick, else the first map.
  const effectiveId = selectedId ?? maps[0]?.map_id ?? null;

  const detail = useQuery({
    queryKey: ['world-map', worldId, effectiveId],
    queryFn: () => worldsApi.getWorldMap(accessToken!, worldId!, effectiveId!),
    enabled: !!accessToken && !!worldId && !!effectiveId,
  });

  return {
    maps,
    selectedId: effectiveId,
    select: setSelectedId,
    detail: detail.data ?? null,
    isLoading: list.isLoading,
    isDetailLoading: detail.isLoading,
    isError: list.isError || detail.isError,
    error: (list.error ?? detail.error) as Error | null,
  };
}
