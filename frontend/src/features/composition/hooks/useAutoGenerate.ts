// LOOM Composition (V1 slice 3) — controlled-auto generation + correction capture.
//
// `useAutoGenerate` runs the diverge→converge POST (non-streaming) and exposes
// the result (winner + K candidates) for the gate cards. `useCorrection` posts
// the genuine-author-choice actions (edit/pick_different/regenerate/reject) —
// NEVER 'accept' (accepting the winner as-is is not a correction, H2).
import { useMutation } from '@tanstack/react-query';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { compositionApi, type AutoGenerateParams } from '../api';
import type { CorrectionBody } from '../types';

export function useAutoGenerate(token: string | null) {
  return useMutation({
    mutationFn: (v: { projectId: string } & AutoGenerateParams) =>
      compositionApi.generateAuto(v.projectId, v, token!),
  });
}

export function useCorrection(token: string | null) {
  const { t } = useTranslation('composition');
  return useMutation({
    mutationFn: (v: { jobId: string; body: CorrectionBody }) =>
      compositionApi.submitCorrection(v.jobId, v.body, token!),
    // Felt signal for the correction flywheel (S1 blackbox D-S1-FLYWHEEL-INVISIBLE): a genuine
    // dissatisfaction capture (reject/regenerate/edit/pick_different — never 'accept', H2) is
    // otherwise a silent backend. One subtle, non-blocking ack so the author knows their edits teach
    // the co-writer. DRY here in the shared mutation → every capture site (inline ghost, scene-compose,
    // chapter-assemble regenerate) gets it for free, and only real corrections fire it.
    onSuccess: () => {
      toast.success(
        t('correction.capturedToast', { defaultValue: 'Noted — your co-writer will learn from this' }),
      );
    },
  });
}
