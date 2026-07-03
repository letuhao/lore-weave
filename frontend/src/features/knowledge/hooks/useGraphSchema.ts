import {
  useQuery,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { ontologyApi, type ListSchemasParams } from '../api/ontology';
import type {
  BlankSchemaCreate,
  CloneSchemaRequest,
  EdgeTypeCreate,
  EdgeTypePatch,
  FactTypeCreate,
  FactTypePatch,
  GraphSchemaPatch,
  NodeKindPatch,
  SchemaNodeKindCreate,
  VocabSetCreate,
  VocabSetPatch,
  VocabValueCreate,
  VocabValuePatch,
} from '../types/ontology';

// ─────────────────────────────────────────────────────────────────────────────
// useGraphSchema — controller for the tiered schema list + one schema's full
// tree, plus the FULL-CRUD schema-editor mutations (A1): add (revive-on-recreate
// server-side) + attribute-only PATCH (code immutable) + tier-aware DELETE, on
// every component (edge/node-kind/fact/vocab-set/vocab-value). Pure logic/state;
// the redesigned SchemaWorkbench renders off the returned data. Each mutation
// invalidates the schema tree so the bumped version + change re-render.
// ─────────────────────────────────────────────────────────────────────────────

export function useGraphSchemaList(params: ListSchemasParams) {
  const { accessToken } = useAuth();
  return useQuery({
    queryKey: ['kg-graph-schemas', params],
    queryFn: () => ontologyApi.listSchemas(params, accessToken!),
    enabled: !!accessToken,
  });
}

export function useGraphSchema(schemaId: string | null, projectId?: string | null) {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();

  const query = useQuery({
    // projectId is part of the key: a PROJECT-scoped schema is only visible to a
    // reader passing its project_id (BE tenancy gate) — without it the tree 404s.
    queryKey: ['kg-graph-schema', schemaId, projectId ?? null],
    queryFn: () => ontologyApi.getSchema(schemaId!, accessToken!, projectId ?? undefined),
    enabled: !!accessToken && !!schemaId,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['kg-graph-schema', schemaId] });
    queryClient.invalidateQueries({ queryKey: ['kg-graph-schemas'] });
  };

  // Small custom hook: build a mutation whose fn closes over the resolved
  // schemaId. Named `use*` so rules-of-hooks recognizes the useMutation inside;
  // called unconditionally + in stable order below (16 fixed calls per render).
  const useMut = <TArgs>(fn: (id: string, args: TArgs) => Promise<unknown>) =>
    useMutation({ mutationFn: (args: TArgs) => fn(schemaId!, args), onSuccess: invalidate });

  const patchMeta = useMut<GraphSchemaPatch>((id, p) => ontologyApi.patchSchema(id, p, accessToken!));

  const addEdgeType = useMut<EdgeTypeCreate>((id, b) => ontologyApi.addEdgeType(id, b, accessToken!));
  const patchEdgeType = useMut<{ code: string; patch: EdgeTypePatch }>((id, a) =>
    ontologyApi.patchEdgeType(id, a.code, a.patch, accessToken!),
  );
  const deleteEdgeType = useMut<string>((id, code) => ontologyApi.deleteEdgeType(id, code, accessToken!));

  const addFactType = useMut<FactTypeCreate>((id, b) => ontologyApi.addFactType(id, b, accessToken!));
  const patchFactType = useMut<{ code: string; patch: FactTypePatch }>((id, a) =>
    ontologyApi.patchFactType(id, a.code, a.patch, accessToken!),
  );
  const deleteFactType = useMut<string>((id, code) => ontologyApi.deleteFactType(id, code, accessToken!));

  const addNodeKind = useMut<SchemaNodeKindCreate>((id, b) => ontologyApi.addNodeKind(id, b, accessToken!));
  const patchNodeKind = useMut<{ code: string; patch: NodeKindPatch }>((id, a) =>
    ontologyApi.patchNodeKind(id, a.code, a.patch, accessToken!),
  );
  const deleteNodeKind = useMut<string>((id, code) => ontologyApi.deleteNodeKind(id, code, accessToken!));

  const addVocabSet = useMut<VocabSetCreate>((id, b) => ontologyApi.addVocabSet(id, b, accessToken!));
  const patchVocabSet = useMut<{ setCode: string; patch: VocabSetPatch }>((id, a) =>
    ontologyApi.patchVocabSet(id, a.setCode, a.patch, accessToken!),
  );
  const deleteVocabSet = useMut<string>((id, setCode) => ontologyApi.deleteVocabSet(id, setCode, accessToken!));

  const addVocabValue = useMut<{ setCode: string; body: VocabValueCreate }>((id, a) =>
    ontologyApi.addVocabValue(id, a.setCode, a.body, accessToken!),
  );
  const patchVocabValue = useMut<{ setCode: string; code: string; patch: VocabValuePatch }>((id, a) =>
    ontologyApi.patchVocabValue(id, a.setCode, a.code, a.patch, accessToken!),
  );
  const deleteVocabValue = useMut<{ setCode: string; code: string }>((id, a) =>
    ontologyApi.deleteVocabValue(id, a.setCode, a.code, accessToken!),
  );

  const all = [
    patchMeta, addEdgeType, patchEdgeType, deleteEdgeType,
    addFactType, patchFactType, deleteFactType,
    addNodeKind, patchNodeKind, deleteNodeKind,
    addVocabSet, patchVocabSet, deleteVocabSet,
    addVocabValue, patchVocabValue, deleteVocabValue,
  ];

  return {
    schema: query.data ?? null,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
    patchMeta: patchMeta.mutateAsync,
    addEdgeType: addEdgeType.mutateAsync,
    patchEdgeType: patchEdgeType.mutateAsync,
    deleteEdgeType: deleteEdgeType.mutateAsync,
    addFactType: addFactType.mutateAsync,
    patchFactType: patchFactType.mutateAsync,
    deleteFactType: deleteFactType.mutateAsync,
    addNodeKind: addNodeKind.mutateAsync,
    patchNodeKind: patchNodeKind.mutateAsync,
    deleteNodeKind: deleteNodeKind.mutateAsync,
    addVocabSet: addVocabSet.mutateAsync,
    patchVocabSet: patchVocabSet.mutateAsync,
    deleteVocabSet: deleteVocabSet.mutateAsync,
    addVocabValue: addVocabValue.mutateAsync,
    patchVocabValue: patchVocabValue.mutateAsync,
    deleteVocabValue: deleteVocabValue.mutateAsync,
    isMutating: all.some((m) => m.isPending),
  };
}

// M1 — all node-kind + edge-type usage counts for a project (inline "· used by N"
// badges + the delete-confirm gate), one query, react-query cached.
export function useSchemaUsageSummary(projectId: string | null) {
  const { accessToken } = useAuth();
  return useQuery({
    queryKey: ['kg-schema-usage', projectId],
    queryFn: () => ontologyApi.schemaUsageSummary(projectId!, accessToken!),
    enabled: !!accessToken && !!projectId,
  });
}

// ── create-from-scratch + clone (A2) — project/caller-scoped, not tied to one
//    schema id. `createBlank` replaces the project's active schema (server-side
//    one-active); `clone` mints a NEW user-scoped editable template. ──────────
export function useSchemaAuthoring(projectId: string | null) {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['kg-graph-schemas'] });
    queryClient.invalidateQueries({ queryKey: ['kg-resolved-schema', projectId] });
  };

  const createBlank = useMutation({
    mutationFn: (body: BlankSchemaCreate) =>
      ontologyApi.createBlankSchema(projectId!, body, accessToken!),
    onSuccess: invalidate,
  });

  const clone = useMutation({
    mutationFn: (body: CloneSchemaRequest) => ontologyApi.cloneSchema(body, accessToken!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['kg-graph-schemas'] }),
  });

  return {
    createBlank: createBlank.mutateAsync,
    clone: clone.mutateAsync,
    isCreating: createBlank.isPending,
    isCloning: clone.isPending,
  };
}
