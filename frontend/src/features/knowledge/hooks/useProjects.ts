import {
  useInfiniteQuery,
  useQueryClient,
  useMutation,
} from '@tanstack/react-query';
import { useMemo } from 'react';
import { useAuth } from '@/auth';
import { knowledgeApi } from '../api';
import type {
  Project,
  ProjectCreatePayload,
  ProjectListResponse,
  ProjectUpdatePayload,
} from '../types';

// C7 (G6) — the projects browser is the knowledge-service HOME. The BE
// list endpoint already supports cursor pagination (`?cursor=` →
// `next_cursor`), so the FE no longer caps at one 100-row page: it
// accumulates pages via useInfiniteQuery and exposes `fetchNextPage` to
// the browser's "Load more". `items` is the flattened union of every
// loaded page. Search / sort / filter-by-state run client-side over
// these loaded rows (the BE list endpoint has no search/sort/status
// params — see api.ts ProjectListParams — and adding them is out of
// scope for C7: "wire the cursor, don't build a new endpoint").
const PAGE_LIMIT = 100;

export function useProjects(includeArchived: boolean) {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();

  const queryKey = ['knowledge-projects', { includeArchived }] as const;

  const query = useInfiniteQuery({
    queryKey,
    queryFn: ({ pageParam }) =>
      knowledgeApi.listProjects(
        {
          limit: PAGE_LIMIT,
          include_archived: includeArchived,
          cursor: pageParam,
        },
        accessToken!,
      ),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage: ProjectListResponse) =>
      lastPage.next_cursor ?? undefined,
    enabled: !!accessToken,
  });

  // Flatten every loaded page into a single list. `pages` is undefined
  // until the first fetch resolves; the `?? []` keeps `items` an array
  // for the whole loading window.
  const items = useMemo<Project[]>(
    () => (query.data?.pages ?? []).flatMap((p) => p.items) as Project[],
    [query.data],
  );

  // Invalidate the whole family (both archived/non-archived variants).
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ['knowledge-projects'] });

  const createMutation = useMutation({
    mutationFn: (payload: ProjectCreatePayload) =>
      knowledgeApi.createProject(payload, accessToken!),
    onSuccess: invalidate,
  });

  const updateMutation = useMutation({
    // D-K8-03: caller must supply `expectedVersion` captured at open
    // time. The hook passes it through to the knowledgeApi layer,
    // which sets If-Match. On 412 the caller catches via
    // isVersionConflict() and refreshes its baseline.
    mutationFn: (args: {
      projectId: string;
      payload: ProjectUpdatePayload;
      expectedVersion: number;
    }) =>
      knowledgeApi.updateProject(
        args.projectId,
        args.payload,
        accessToken!,
        args.expectedVersion,
      ),
    onSuccess: invalidate,
  });

  const archiveMutation = useMutation({
    mutationFn: (projectId: string) =>
      knowledgeApi.archiveProject(projectId, accessToken!),
    onSuccess: invalidate,
  });

  const deleteMutation = useMutation({
    mutationFn: (projectId: string) =>
      knowledgeApi.deleteProject(projectId, accessToken!),
    onSuccess: invalidate,
  });

  return {
    items,
    // C7: real cursor pagination. `hasMore` reflects whether another
    // page exists on the BE; `loadMore` advances to it (accumulating).
    hasMore: !!query.hasNextPage,
    loadMore: query.fetchNextPage,
    isFetchingMore: query.isFetchingNextPage,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
    createProject: createMutation.mutateAsync,
    updateProject: updateMutation.mutateAsync,
    archiveProject: archiveMutation.mutateAsync,
    deleteProject: deleteMutation.mutateAsync,
    isMutating:
      createMutation.isPending ||
      updateMutation.isPending ||
      archiveMutation.isPending ||
      deleteMutation.isPending,
  };
}
