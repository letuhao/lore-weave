import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { ontologyApi } from '../api/ontology';

// useResolvedSchema — read-only controller for a project's EFFECTIVE schema
// (the system→user→project merge). Backs the Knowledge-GUI Schema inspector.
// Always resolves to something (system defaults even before adopt), so the
// inspector never dead-ends on "no schema adopted".
export function useResolvedSchema(projectId: string | null) {
  const { accessToken } = useAuth();
  const query = useQuery({
    queryKey: ['kg-resolved-schema', projectId],
    queryFn: () => ontologyApi.getResolvedSchema(projectId!, accessToken!),
    enabled: !!accessToken && !!projectId,
  });
  return {
    schema: query.data ?? null,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
  };
}
