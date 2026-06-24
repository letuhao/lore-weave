// LOOM Composition (T3.4) — controller for per-scene grounding pin/exclude.
// setAction(item, action) optimistically flips the item's pinned/excluded state in
// every cached grounding query for this scene (any guide), PUTs the change, then
// invalidates so the preview re-packs (the BE honors the set on the next pack).
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { compositionApi } from '../api';
import type { Grounding, GroundingItem, PinAction } from '../types';

export function useGroundingPins(
  projectId: string | undefined, nodeId: string | undefined, token: string | null,
) {
  const qc = useQueryClient();
  const key = ['composition', 'grounding', projectId, nodeId];

  const mutation = useMutation({
    mutationFn: ({ item, action }: { item: GroundingItem; action: PinAction }) =>
      compositionApi.setGroundingPin(
        projectId!, nodeId!, { item_type: item.type, item_id: item.id, action }, token!),
    onMutate: ({ item, action }) => {
      const patch = (it: GroundingItem): GroundingItem =>
        it.type === item.type && it.id === item.id
          ? { ...it, pinned: action === 'pin', excluded: action === 'exclude' }
          : it;
      qc.setQueriesData<Grounding>({ queryKey: key }, (old) =>
        old?.grounding_items
          ? { ...old, grounding_items: old.grounding_items.map(patch) }
          : old);
    },
    // Re-pack so blocks/token_count reflect the new steering (not just the badges).
    onSettled: () => { qc.invalidateQueries({ queryKey: key }); },
  });

  const setAction = (item: GroundingItem, action: PinAction) => {
    if (!projectId || !nodeId || !token) return;
    mutation.mutate({ item, action });
  };

  return { setAction, isPending: mutation.isPending };
}
