import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { knowledgeApi } from '../api';
import type {
  Project,
  ProjectCreatePayload,
  ProjectUpdatePayload,
} from '../types';

// Track 1 keeps pagination simple: single page of up to 100 projects.
// The backend supports cursor pagination, but no-one has that many
// projects in practice. When next_cursor is non-null the list footer
// tells the user, and proper pagination lands with K8+ / Track 2.
const PAGE_LIMIT = 100;

export function useProjects(includeArchived: boolean) {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();

  const queryKey = ['knowledge-projects', { includeArchived }] as const;

  const query = useQuery({
    queryKey,
    queryFn: () =>
      knowledgeApi.listProjects(
        { limit: PAGE_LIMIT, include_archived: includeArchived },
        accessToken!,
      ),
    enabled: !!accessToken,
  });

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
    items: (query.data?.items ?? []) as Project[],
    hasMore: !!query.data?.next_cursor,
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
