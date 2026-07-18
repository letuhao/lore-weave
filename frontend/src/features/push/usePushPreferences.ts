// DF5 controller — the per-topic push preferences (the draft's "per-category" settings). Reuses the
// M5 push-preferences BE (GET/PUT, effective value + source). Optimistic toggle. CLAUDE.md MVC.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { pushApi } from './api';

export function usePushPreferences() {
  const { accessToken } = useAuth();
  const qc = useQueryClient();

  const query = useQuery({
    queryKey: ['push-prefs'],
    queryFn: () => pushApi.getPreferences(accessToken),
    enabled: !!accessToken,
    staleTime: 30_000,
  });

  const mutation = useMutation({
    mutationFn: ({ topic, enabled }: { topic: string; enabled: boolean }) =>
      pushApi.setPreference(accessToken, topic, enabled),
    onMutate: async ({ topic, enabled }) => {
      await qc.cancelQueries({ queryKey: ['push-prefs'] });
      const prev = qc.getQueryData(['push-prefs']);
      qc.setQueryData(['push-prefs'], (old: { topics?: Record<string, boolean>; source?: Record<string, string> } | undefined) =>
        old ? { ...old, topics: { ...old.topics, [topic]: enabled }, source: { ...old.source, [topic]: 'user' } } : old,
      );
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(['push-prefs'], ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['push-prefs'] }),
  });

  return {
    topics: query.data?.topics ?? {},
    isLoading: query.isLoading,
    setTopic: (topic: string, enabled: boolean) => mutation.mutate({ topic, enabled }),
  };
}
