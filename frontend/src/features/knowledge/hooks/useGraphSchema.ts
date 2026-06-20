import {
  useQuery,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { ontologyApi, type ListSchemasParams } from '../api/ontology';
import type {
  EdgeTypeCreate,
  FactTypeCreate,
  GraphSchemaPatch,
  SchemaNodeKindCreate,
  VocabValueCreate,
} from '../types/ontology';

// ─────────────────────────────────────────────────────────────────────────────
// useGraphSchema — controller for the tiered schema list + one schema's full
// tree, plus the schema-editor mutations (additive child adds + deprecate-only,
// metadata patch). Pure logic/state; the schema-editor + adopt-picker views
// render off the returned data. Each child mutation invalidates the schema tree
// so the bumped schema_version + new child re-render.
// ─────────────────────────────────────────────────────────────────────────────

export function useGraphSchemaList(params: ListSchemasParams) {
  const { accessToken } = useAuth();
  return useQuery({
    queryKey: ['kg-graph-schemas', params],
    queryFn: () => ontologyApi.listSchemas(params, accessToken!),
    enabled: !!accessToken,
  });
}

export function useGraphSchema(schemaId: string | null) {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ['kg-graph-schema', schemaId],
    queryFn: () => ontologyApi.getSchema(schemaId!, accessToken!),
    enabled: !!accessToken && !!schemaId,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['kg-graph-schema', schemaId] });
    queryClient.invalidateQueries({ queryKey: ['kg-graph-schemas'] });
  };

  const patchMeta = useMutation({
    mutationFn: (patch: GraphSchemaPatch) =>
      ontologyApi.patchSchema(schemaId!, patch, accessToken!),
    onSuccess: invalidate,
  });

  const addEdgeType = useMutation({
    mutationFn: (body: EdgeTypeCreate) =>
      ontologyApi.addEdgeType(schemaId!, body, accessToken!),
    onSuccess: invalidate,
  });

  const deprecateEdgeType = useMutation({
    mutationFn: (code: string) =>
      ontologyApi.deprecateEdgeType(schemaId!, code, accessToken!),
    onSuccess: invalidate,
  });

  const addFactType = useMutation({
    mutationFn: (body: FactTypeCreate) =>
      ontologyApi.addFactType(schemaId!, body, accessToken!),
    onSuccess: invalidate,
  });

  const addVocabValue = useMutation({
    mutationFn: (args: { setCode: string; body: VocabValueCreate }) =>
      ontologyApi.addVocabValue(schemaId!, args.setCode, args.body, accessToken!),
    onSuccess: invalidate,
  });

  const addNodeKind = useMutation({
    mutationFn: (body: SchemaNodeKindCreate) =>
      ontologyApi.addNodeKind(schemaId!, body, accessToken!),
    onSuccess: invalidate,
  });

  return {
    schema: query.data ?? null,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
    patchMeta: patchMeta.mutateAsync,
    addEdgeType: addEdgeType.mutateAsync,
    deprecateEdgeType: deprecateEdgeType.mutateAsync,
    addFactType: addFactType.mutateAsync,
    addVocabValue: addVocabValue.mutateAsync,
    addNodeKind: addNodeKind.mutateAsync,
    isMutating:
      patchMeta.isPending ||
      addEdgeType.isPending ||
      deprecateEdgeType.isPending ||
      addFactType.isPending ||
      addVocabValue.isPending ||
      addNodeKind.isPending,
  };
}
