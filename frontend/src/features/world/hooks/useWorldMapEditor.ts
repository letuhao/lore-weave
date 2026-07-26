import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { worldsApi } from '../api';
import type { WorldMapDetail, WorldMapMarker, WorldMapRegion } from '../types';

// S7·2 — the world-map EDITOR controller (MVC "controller"): owns world/map selection, the
// interaction mode, and every write mutation (create/upload/add/UPDATE/delete) with optimistic
// drag + rollback and cache invalidation. No JSX. Extends useWorldMaps' query keys
// (['world-maps', worldId] / ['world-map', worldId, mapId]) so an agent write (Lane-B) and a
// human edit converge on the same cache.

export type EditorMode = 'select' | 'pin' | 'region';

export interface WorldMapFocusParams {
  worldId?: string;
  mapId?: string;
}

const mapKey = (worldId?: string, mapId?: string | null) => ['world-map', worldId, mapId] as const;
const listKey = (worldId?: string) => ['world-maps', worldId] as const;

export function useWorldMapEditor(params?: WorldMapFocusParams) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();

  // ── world selection: params → in-panel picker (book→world derivation is done by the caller
  //    passing params.worldId; a bare-id open with no world shows the picker, never a dead pane). ──
  const [pickedWorldId, setPickedWorldId] = useState<string | null>(params?.worldId ?? null);
  const worldId = pickedWorldId ?? params?.worldId ?? undefined;

  const worlds = useQuery({
    queryKey: ['worlds', 'for-map-picker'],
    queryFn: () => worldsApi.listWorlds(accessToken!),
    enabled: !!accessToken && !worldId,
  });

  // ── map selection within the world ──
  const [pickedMapId, setPickedMapId] = useState<string | null>(params?.mapId ?? null);
  const list = useQuery({
    queryKey: listKey(worldId),
    queryFn: () => worldsApi.listWorldMaps(accessToken!, worldId!),
    enabled: !!accessToken && !!worldId,
  });
  const maps = list.data?.items ?? [];
  const selectedMapId = pickedMapId ?? maps[0]?.map_id ?? null;

  const detail = useQuery({
    queryKey: mapKey(worldId, selectedMapId),
    queryFn: () => worldsApi.getWorldMap(accessToken!, worldId!, selectedMapId!),
    enabled: !!accessToken && !!worldId && !!selectedMapId,
  });

  const [mode, setMode] = useState<EditorMode>('select');
  const [selectedMarkerId, setSelectedMarkerId] = useState<string | null>(null);
  const [selectedRegionId, setSelectedRegionId] = useState<string | null>(null);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: listKey(worldId) });
    qc.invalidateQueries({ queryKey: mapKey(worldId, selectedMapId) });
  };

  // ── map-level mutations ──
  const createMap = useMutation({
    mutationFn: (name: string) => worldsApi.createMap(accessToken!, worldId!, { name }),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: listKey(worldId) });
      setPickedMapId(res.map.map_id);
    },
  });

  const uploadImage = useMutation({
    mutationFn: (file: File) => worldsApi.uploadMapImage(accessToken!, worldId!, selectedMapId!, file),
    onSuccess: invalidate,
  });

  const renameMap = useMutation({
    mutationFn: ({ name, version }: { name: string; version: number }) =>
      worldsApi.patchMap(accessToken!, worldId!, selectedMapId!, version, { name }),
    // 412: the thrown error carries the current row on `body.current` — reseed the cache so the
    // canvas shows the winning name, never a blind clobber (§3.5 OCC-conflict state).
    onError: (err: unknown) => {
      const current = (err as { body?: { current?: WorldMapDetail['map'] } })?.body?.current;
      if (current) {
        qc.setQueryData(mapKey(worldId, selectedMapId), (prev: WorldMapDetail | undefined) =>
          prev ? { ...prev, map: current } : prev,
        );
      }
    },
    onSuccess: invalidate,
  });

  const deleteMap = useMutation({
    mutationFn: (mapId: string) => worldsApi.deleteMap(accessToken!, worldId!, mapId),
    onSuccess: () => {
      setPickedMapId(null);
      qc.invalidateQueries({ queryKey: listKey(worldId) });
    },
  });

  // ── marker mutations ──
  const addMarker = useMutation({
    mutationFn: (p: { label: string; x: number; y: number; entity_id?: string; marker_type?: string }) =>
      worldsApi.addMarker(accessToken!, worldId!, selectedMapId!, p),
    onSuccess: invalidate,
  });

  // 🔴 The drag PATCH. Optimistic-with-rollback: move the pin locally, PATCH the ABSOLUTE coord on
  // the stable marker_id, and snap back on error (§3.5 "drag mid-flight, then disconnect"). One
  // atomic PATCH — never delete+recreate — so there is no stranded-delete half-state.
  const moveMarker = useMutation({
    mutationFn: ({ markerId, x, y }: { markerId: string; x: number; y: number }) =>
      worldsApi.patchMarker(accessToken!, worldId!, selectedMapId!, markerId, { x, y }),
    onMutate: async ({ markerId, x, y }) => {
      const key = mapKey(worldId, selectedMapId);
      await qc.cancelQueries({ queryKey: key });
      const prev = qc.getQueryData<WorldMapDetail>(key);
      qc.setQueryData<WorldMapDetail>(key, (d) =>
        d ? { ...d, markers: d.markers.map((m) => (m.marker_id === markerId ? { ...m, x, y } : m)) } : d,
      );
      return { prev, key };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(ctx.key, ctx.prev);
    },
    onSettled: invalidate,
  });

  const patchMarker = useMutation({
    mutationFn: ({ markerId, payload }: { markerId: string; payload: Parameters<typeof worldsApi.patchMarker>[4] }) =>
      worldsApi.patchMarker(accessToken!, worldId!, selectedMapId!, markerId, payload),
    onSuccess: invalidate,
  });

  const deleteMarker = useMutation({
    mutationFn: (markerId: string) => worldsApi.deleteMarker(accessToken!, worldId!, selectedMapId!, markerId),
    onSuccess: () => {
      setSelectedMarkerId(null);
      invalidate();
    },
  });

  // ── region mutations ──
  const addRegion = useMutation({
    mutationFn: (p: { name: string; polygon: number[][]; entity_id?: string }) =>
      worldsApi.addRegion(accessToken!, worldId!, selectedMapId!, p),
    onSuccess: invalidate,
  });

  const reshapeRegion = useMutation({
    mutationFn: ({ regionId, polygon }: { regionId: string; polygon: number[][] }) =>
      worldsApi.patchRegion(accessToken!, worldId!, selectedMapId!, regionId, { polygon }),
    onMutate: async ({ regionId, polygon }) => {
      const key = mapKey(worldId, selectedMapId);
      await qc.cancelQueries({ queryKey: key });
      const prev = qc.getQueryData<WorldMapDetail>(key);
      qc.setQueryData<WorldMapDetail>(key, (d) =>
        d ? { ...d, regions: d.regions.map((r) => (r.region_id === regionId ? { ...r, polygon } : r)) } : d,
      );
      return { prev, key };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(ctx.key, ctx.prev);
    },
    onSettled: invalidate,
  });

  const patchRegion = useMutation({
    mutationFn: ({ regionId, payload }: { regionId: string; payload: Parameters<typeof worldsApi.patchRegion>[4] }) =>
      worldsApi.patchRegion(accessToken!, worldId!, selectedMapId!, regionId, payload),
    onSuccess: invalidate,
  });

  const deleteRegion = useMutation({
    mutationFn: (regionId: string) => worldsApi.deleteRegion(accessToken!, worldId!, selectedMapId!, regionId),
    onSuccess: () => {
      setSelectedRegionId(null);
      invalidate();
    },
  });

  const markers: WorldMapMarker[] = detail.data?.markers ?? [];
  const regions: WorldMapRegion[] = detail.data?.regions ?? [];
  const selectedMarker = useMemo(
    () => markers.find((m) => m.marker_id === selectedMarkerId) ?? null,
    [markers, selectedMarkerId],
  );
  const selectedRegion = useMemo(
    () => regions.find((r) => r.region_id === selectedRegionId) ?? null,
    [regions, selectedRegionId],
  );

  return {
    // world/map resolution
    worldId,
    needsWorldPicker: !worldId,
    worldOptions: worlds.data?.items ?? [],
    pickWorld: setPickedWorldId,
    maps,
    selectedMapId,
    selectMap: setPickedMapId,
    map: detail.data?.map ?? null,
    markers,
    regions,
    // status
    isLoading: list.isLoading || detail.isLoading,
    isError: list.isError || detail.isError,
    error: (list.error ?? detail.error) as Error | null,
    isEmpty: !!worldId && !list.isLoading && maps.length === 0,
    // interaction
    mode,
    setMode,
    selectedMarkerId,
    setSelectedMarkerId,
    selectedRegionId,
    setSelectedRegionId,
    selectedMarker,
    selectedRegion,
    // mutations
    createMap,
    uploadImage,
    renameMap,
    deleteMap,
    addMarker,
    moveMarker,
    patchMarker,
    deleteMarker,
    addRegion,
    reshapeRegion,
    patchRegion,
    deleteRegion,
  };
}
