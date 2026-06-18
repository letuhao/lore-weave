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
  ProjectSortBy,
  ProjectSortDir,
  ProjectStatusFilter,
  ProjectUpdatePayload,
} from '../types';

// C7 (G6) + C7-followup (KN-7) — the projects browser is the
// knowledge-service HOME and now narrows SERVER-SIDE. The BE list
// endpoint takes `search` / `sort_by` / `sort_dir` / `status` (plus
// cursor pagination), so search / sort / filter run across ALL projects
// rather than only the loaded cursor pages (the client-side
// `narrowProjects` no longer gates which rows the user sees). `items` is
// the flattened union of every loaded page for the ACTIVE narrowing.
const PAGE_LIMIT = 100;

export interface ProjectsQueryParams {
  includeArchived: boolean;
  search?: string;
  sortBy?: ProjectSortBy;
  sortDir?: ProjectSortDir;
  status?: ProjectStatusFilter;
}

// Back-compat: callers that only care about archived visibility (the
// editor AI panel, mobile shells, detail-shell resolvers) pass a bare
// boolean and get the original unfiltered behaviour. The HOME browser
// passes the full params object to drive server-side narrowing.
export function useProjects(arg: boolean | ProjectsQueryParams) {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();

  const params: ProjectsQueryParams =
    typeof arg === 'boolean' ? { includeArchived: arg } : arg;
  const { includeArchived, search, sortBy, sortDir, status } = params;

  // The narrowing is part of the query identity — a changed search /
  // sort / status starts a fresh server-side query (new first page),
  // not a re-narrow of the previously-loaded rows.
  const queryKey = [
    'knowledge-projects',
    { includeArchived, search, sortBy, sortDir, status },
  ] as const;

  const query = useInfiniteQuery({
    queryKey,
    queryFn: ({ pageParam }) =>
      knowledgeApi.listProjects(
        {
          limit: PAGE_LIMIT,
          include_archived: includeArchived,
          cursor: pageParam,
          search: search || undefined,
          sort_by: sortBy,
          sort_dir: sortDir,
          status,
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
