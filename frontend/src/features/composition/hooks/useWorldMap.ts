// LOOM Composition (T2.5) — World Map controller. The book's places (location
// entities) and their location↔location relations as a hand-rolled SVG graph
// (reuses the shared <GraphCanvas>). Author-arranged positions + an optional
// backdrop image persist SERVER-SIDE on the composition work.settings (shared
// across devices — distinct from T2.2's per-device localStorage). "+ add place"
// and "link places" write to the knowledge graph via the new T2.5 create routes.
import { useMemo, useRef, useState } from 'react';
import { keepPreviousData, useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { knowledgeApi } from '../../knowledge/api';
import type { Entity, EntityDetail } from '../../knowledge/api';
import { booksApi } from '../../books/api';
import { useKnowledgeProjectId } from './useCast';
import { useSetWorkSettings } from './useWork';
import type { Work } from '../types';
import type { GraphEdge, GraphNode } from './useRelationshipMap';
import type { Pos } from '../components/GraphCanvas';

export const PLACE_LINK_PREDICATES = ['contains', 'borders', 'route_to'] as const;
export type PlaceLinkPredicate = (typeof PLACE_LINK_PREDICATES)[number];

// Pure (exported for tests): grid auto-layout for places without a saved position.
export function gridLayout(
  ids: string[],
  opts: { cols?: number; gapX?: number; gapY?: number; pad?: number } = {},
): Record<string, Pos> {
  const { cols = 4, gapX = 200, gapY = 140, pad = 32 } = opts;
  const out: Record<string, Pos> = {};
  ids.forEach((id, i) => {
    out[id] = { x: pad + (i % cols) * gapX, y: pad + Math.floor(i / cols) * gapY };
  });
  return out;
}

// Pure (exported for tests): assemble the place graph — nodes = locations, edges =
// relations whose BOTH endpoints are locations (a place↔character edge is dropped),
// deduped by relation id. Mapped to the shared GraphNode/GraphEdge so RelationEdge
// (T2.2) renders them unchanged.
export function buildPlaceGraph(
  places: Entity[],
  details: Record<string, EntityDetail>,
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const placeIds = new Set(places.map((p) => p.id));
  const nodes: GraphNode[] = places.map((p) => ({ id: p.id, name: p.name, kind: p.kind }));
  const edges = new Map<string, GraphEdge>();
  for (const p of places) {
    const d = details[p.id];
    if (!d) continue;
    for (const r of d.relations) {
      if (!placeIds.has(r.subject_id) || !placeIds.has(r.object_id)) continue;
      if (!edges.has(r.id)) {
        edges.set(r.id, {
          id: r.id, from: r.subject_id, to: r.object_id,
          predicate: r.predicate, pending: r.pending_validation, confidence: r.confidence,
        });
      }
    }
  }
  return { nodes, edges: [...edges.values()] };
}

type WorldMapSettings = { positions?: Record<string, Pos>; backdrop_url?: string };

export function useWorldMap(work: Work, bookId: string, chapterId: string, token: string | null) {
  const qc = useQueryClient();
  const projectQ = useKnowledgeProjectId(bookId, token);
  const knowledgeProjectId = projectQ.data;
  const enabled = !!knowledgeProjectId && !!token;

  const placesQ = useQuery({
    queryKey: ['composition', 'worldmap', 'places', knowledgeProjectId],
    queryFn: () => knowledgeApi.listEntities({ project_id: knowledgeProjectId!, kind: 'location', limit: 200 }, token!),
    enabled,
    select: (d) => d.entities,
    placeholderData: keepPreviousData,
  });
  const places = placesQ.data ?? [];

  // One detail fetch per place to discover its location↔location edges.
  const detailQueries = useQueries({
    queries: places.map((p) => ({
      queryKey: ['composition', 'worldmap', 'detail', p.id],
      queryFn: () => knowledgeApi.getEntityDetail(p.id, token!),
      enabled: !!token,
      staleTime: 60 * 1000,
    })),
  });
  const details: Record<string, EntityDetail> = {};
  detailQueries.forEach((q, i) => { if (q.data && places[i]) details[places[i].id] = q.data; });

  const { nodes, edges } = useMemo(() => buildPlaceGraph(places, details), [places, details]);

  // Positions + backdrop persist on the COMPOSITION work.settings (shared across
  // devices). Drag overrides seed once from settings; new places fall back to grid.
  const wm = (work.settings.world_map as WorldMapSettings | undefined) ?? {};
  const setSettings = useSetWorkSettings(bookId, token);
  const seed = wm.positions ?? {};
  const [local, setLocal] = useState<Record<string, Pos>>(seed);
  const localRef = useRef<Record<string, Pos>>(seed);
  const applyLocal = (next: Record<string, Pos>) => { localRef.current = next; setLocal(next); };
  // The two writers (positions + backdrop) both replace the SINGLE `world_map`
  // blob. Read-modify-writing from the (possibly stale) `work` prop lets one
  // clobber the other's sub-key (upload backdrop, then drag before `work`
  // refetches → the positions PATCH drops backdrop_url). Keep the live merged
  // blob in a ref both writers update, so neither loses the other's sub-key.
  const wmRef = useRef<WorldMapSettings>(wm);
  const persistWorldMap = (patch: Partial<WorldMapSettings>) => {
    wmRef.current = { ...wmRef.current, ...patch };
    setSettings.mutate({ projectId: work.project_id, currentSettings: work.settings, patch: { world_map: wmRef.current } });
  };
  const persistPositions = (positions: Record<string, Pos>) => {
    localRef.current = positions;
    persistWorldMap({ positions });
  };

  const auto = useMemo(() => gridLayout(nodes.map((n) => n.id)), [nodes]);
  const positions = useMemo(() => {
    const acc: Record<string, Pos> = {};
    for (const n of nodes) acc[n.id] = local[n.id] ?? auto[n.id] ?? { x: 32, y: 32 };
    return acc;
  }, [nodes, local, auto]);

  const invalidatePlaces = () => {
    qc.invalidateQueries({ queryKey: ['composition', 'worldmap', 'places'] });
    qc.invalidateQueries({ queryKey: ['composition', 'worldmap', 'detail'] });
  };

  const createPlace = useMutation({
    mutationFn: (name: string) =>
      knowledgeApi.createEntity({ project_id: knowledgeProjectId!, name, kind: 'location' }, token!),
    onSuccess: invalidatePlaces,
  });
  const linkPlaces = useMutation({
    mutationFn: (v: { subjectId: string; objectId: string; predicate: PlaceLinkPredicate }) =>
      knowledgeApi.createRelation({ subject_id: v.subjectId, object_id: v.objectId, predicate: v.predicate }, token!),
    onSuccess: invalidatePlaces,
  });
  // Remove a place = soft-archive the location entity (mirror KG authoring's
  // useArchiveEntity). The node's `id` IS the createEntity id IS the id the
  // DELETE /me/entities/{id} route accepts (id-equivalence proven live). 404 is
  // idempotent success (already gone / cross-user typo), never a hard failure.
  const deletePlace = useMutation({
    mutationFn: async (entityId: string) => {
      try {
        await knowledgeApi.archiveMyEntity(entityId, token!);
      } catch (err) {
        const status = (err as Error & { status?: number }).status;
        if (status === 404) return; // idempotent: already hidden == success
        throw err;
      }
    },
    onSuccess: invalidatePlaces,
  });
  const uploadBackdrop = useMutation({
    mutationFn: async (file: File) => (await booksApi.uploadChapterMedia(token!, bookId, chapterId, file)).url,
    onSuccess: (url) => persistWorldMap({ backdrop_url: url }),
  });

  return {
    knowledgeProjectId,
    projectLoading: projectQ.isLoading,
    placesLoading: placesQ.isLoading,
    nodes, edges, positions,
    backdropUrl: wm.backdrop_url ?? null,
    applyLocal, localRef, persistPositions,
    createPlace, linkPlaces, deletePlace, uploadBackdrop,
  };
}
