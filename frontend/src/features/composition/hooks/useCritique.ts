// LOOM Composition (M8) — advisory critique controller (react-query mutations).
import { useMutation } from '@tanstack/react-query';
import { compositionApi } from '../api';

export function useCritique(token: string | null) {
  const critique = useMutation({
    mutationFn: (v: { jobId: string; passage: string }) =>
      compositionApi.critique(v.jobId, v.passage, token!),
  });
  const dismiss = useMutation({
    mutationFn: (v: { jobId: string; ruleId: string }) =>
      compositionApi.dismissViolation(v.jobId, v.ruleId, token!),
  });
  return { critique, dismiss };
}
