// LOOM Composition (T3.6) — controller for the author's reference shelf.
// Owns: the Work's reference library (list), the per-scene semantic retrieval
// (search, auto query unless `query` is given), add/delete mutations, and pin/
// exclude reuse (the T3.4 grounding-pin PUT with item_type='reference'). View-free.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { compositionApi } from '../api';
import type { PinAction, ReferenceHit, ReferenceList, ReferenceSearch } from '../types';

export function useReferences(
  projectId: string | undefined,
  sceneId: string | undefined,
  token: string | null,
  query = '',
) {
  const qc = useQueryClient();
  // Audit fix — mutations were silent on failure (onSuccess only). Surface errors so a
  // failed add/edit/delete/re-embed isn't an invisible no-op.
  const fail = (msg: string) => () => toast.error(msg);
  const listKey = ['composition', 'references', projectId];
  const searchKey = ['composition', 'references', 'search', projectId, sceneId, query];

  const list = useQuery({
    queryKey: listKey,
    queryFn: () => compositionApi.listReferences(projectId!, token!),
    enabled: !!projectId && !!token,
  });

  const search = useQuery({
    queryKey: searchKey,
    queryFn: () => compositionApi.searchReferences(projectId!, sceneId!, token!, query || undefined),
    // only retrieve once a scene is selected AND the Work has an embed model
    // (else the BE returns a neutral empty — no point spending the round-trip).
    enabled: !!projectId && !!sceneId && !!token && list.data?.embed_model_set === true,
  });

  const add = useMutation({
    mutationFn: (body: { content: string; title?: string; author?: string; source_url?: string;
                         model_ref?: string; model_source?: string }) =>
      compositionApi.addReference(projectId!, body, token!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: listKey });
      qc.invalidateQueries({ queryKey: ['composition', 'references', 'search', projectId] });
    },
    onError: fail('Could not add the reference — try again.'),
  });

  const remove = useMutation({
    mutationFn: (referenceId: string) => compositionApi.deleteReference(referenceId, token!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: listKey });
      qc.invalidateQueries({ queryKey: ['composition', 'references', 'search', projectId] });
    },
    onError: fail('Could not delete the reference — try again.'),
  });

  // S-03 — edit a reference. Metadata is cheap (no re-embed); content re-embeds. Both
  // refresh the library + per-scene retrieval (an edited passage changes both).
  const updateMetadata = useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: { title?: string; author?: string; source_url?: string } }) =>
      compositionApi.updateReferenceMetadata(projectId!, id, patch, token!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: listKey });
      qc.invalidateQueries({ queryKey: ['composition', 'references', 'search', projectId] });
    },
    onError: fail('Could not save the details — try again.'),
  });

  const updateContent = useMutation({
    mutationFn: ({ id, content }: { id: string; content: string }) =>
      compositionApi.updateReferenceContent(projectId!, id, content, token!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: listKey });
      qc.invalidateQueries({ queryKey: ['composition', 'references', 'search', projectId] });
    },
    onError: fail('Could not save the content (re-embed failed) — try again.'),
  });

  const pin = useMutation({
    mutationFn: ({ hit, action }: { hit: ReferenceHit; action: PinAction }) =>
      compositionApi.setGroundingPin(
        projectId!, sceneId!, { item_type: 'reference', item_id: hit.id, action }, token!),
    onMutate: ({ hit, action }) => {
      qc.setQueriesData<ReferenceSearch>({ queryKey: ['composition', 'references', 'search', projectId, sceneId] },
        (old) => old
          ? { ...old, hits: old.hits.map((h) => h.id === hit.id
              ? { ...h, pinned: action === 'pin', excluded: action === 'exclude' } : h) }
          : old);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['composition', 'references', 'search', projectId, sceneId] });
    },
  });

  const setPin = (hit: ReferenceHit, action: PinAction) => {
    if (!projectId || !sceneId || !token) return;
    pin.mutate({ hit, action });
  };

  const data: ReferenceList | undefined = list.data;
  return {
    references: data?.references ?? [],
    embedModelSet: data?.embed_model_set ?? false,
    isLoading: list.isLoading,
    hits: search.data?.hits ?? [],
    searchUnavailable: search.data?.unavailable ?? false,
    isSearching: search.isFetching,
    add,
    remove,
    updateMetadata,
    updateContent,
    setPin,
  };
}
