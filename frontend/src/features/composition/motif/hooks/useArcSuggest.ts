// S-10 O6b — the "Suggest an arc for this premise" controller. Ranks the caller-visible arc templates
// that fit a Work's premise/genre via POST /arc-templates/suggest (read-only, VIEW on the Work's book).
// A mutation (not a query) because the premise is a user-typed input the caller submits. No JSX.
import { useMutation } from '@tanstack/react-query';
import { arcApi, type ArcSuggestResult } from '../arcApi';

export function useArcSuggest(projectId: string | null, token: string | null) {
  const mut = useMutation<ArcSuggestResult, Error, { premise?: string; genre?: string }>({
    mutationFn: ({ premise, genre }) =>
      arcApi.suggest(
        { project_id: projectId!, premise: premise || undefined, genre: genre || undefined, limit: 8, detail: 'summary' },
        token!,
      ),
  });
  return {
    run: (premise?: string, genre?: string) => mut.mutate({ premise, genre }),
    candidates: mut.data?.candidates ?? [],
    ran: mut.isSuccess,
    isPending: mut.isPending,
    isError: mut.isError,
    reset: mut.reset,
  };
}
