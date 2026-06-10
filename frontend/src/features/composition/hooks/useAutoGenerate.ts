// LOOM Composition (V1 slice 3) — controlled-auto generation + correction capture.
//
// `useAutoGenerate` runs the diverge→converge POST (non-streaming) and exposes
// the result (winner + K candidates) for the gate cards. `useCorrection` posts
// the genuine-author-choice actions (edit/pick_different/regenerate/reject) —
// NEVER 'accept' (accepting the winner as-is is not a correction, H2).
import { useMutation } from '@tanstack/react-query';
import { compositionApi, type AutoGenerateParams } from '../api';
import type { CorrectionBody } from '../types';

export function useAutoGenerate(token: string | null) {
  return useMutation({
    mutationFn: (v: { projectId: string } & AutoGenerateParams) =>
      compositionApi.generateAuto(v.projectId, v, token!),
  });
}

export function useCorrection(token: string | null) {
  return useMutation({
    mutationFn: (v: { jobId: string; body: CorrectionBody }) =>
      compositionApi.submitCorrection(v.jobId, v.body, token!),
  });
}
