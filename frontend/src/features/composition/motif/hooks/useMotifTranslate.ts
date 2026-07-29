// The user-paid LIBRARY translate (spec 2026-07-29-motif-i18n §5) — the Tier-W flow
// controller, for motifs AND arc templates. Mirrors useMotifMine: PROPOSE (mint a confirm token + $ estimate via the
// FE→MCP bridge) → the human confirms the cost → poll the job. The FE never executes
// the spend.
//
// Why this exists at all: the platform's own motifs ship translated into every supported
// language for free, and a motif the USER wrote is deliberately never machine-translated
// on our initiative. That policy was implemented only in the half that REFUSES — so
// until this hook, "we don't translate for you" was indistinguishable from "you can't
// translate". No JSX.
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { motifApi, isQuotaError } from '../api';
import type { CostEstimate, MotifTranslateLanguage, MotifTranslateResult } from '../types';

type Args = {
  /** Which library. Both carried the identical identity defect and share one policy,
   *  one tool and one worker job — only the table differs. */
  kind?: 'motif' | 'arc_template';
  ids: string[];
  targetLanguage: MotifTranslateLanguage;
  bookId?: string | null;
  /** Re-translate one that already exists and is still current. Off by default —
   *  charging again for wording that has not moved is what this whole path avoids. */
  force?: boolean;
};

export function useMotifTranslate(token: string | null, onDone?: () => void) {
  const qc = useQueryClient();
  const [estimate, setEstimate] = useState<(CostEstimate & { skipped: number }) | null>(null);
  const [result, setResult] = useState<MotifTranslateResult | null>(null);

  // Step 1 — mint the estimate + confirm token for the chosen model. No spend. The
  // server drops ids the caller may not translate, so `skipped` can be > 0 and the card
  // must say so rather than quietly charging for fewer motifs than the user picked.
  const mint = useMutation({
    mutationFn: (args: Args & { modelRef: string }) =>
      motifApi.translatePropose(
        {
          kind: args.kind,
          ids: args.ids,
          targetLanguage: args.targetLanguage,
          bookId: args.bookId,
          force: args.force,
          modelRef: args.modelRef,
        },
        token!,
      ),
    onSuccess: setEstimate,
  });

  // Step 2 — confirm → poll → the per-motif outcome. Invalidate the motif queries so
  // the drawer/list re-read in the new language (a translation that landed but is not
  // shown reads as a failed purchase).
  const confirm = useMutation({
    mutationFn: () => motifApi.translateConfirm(estimate!.confirm_token, token!),
    onSuccess: (r) => {
      setResult(r);
      setEstimate(null);
      qc.invalidateQueries({ queryKey: ['composition', 'motifs'] });
      qc.invalidateQueries({ queryKey: ['composition', 'motif'] });
      qc.invalidateQueries({ queryKey: ['composition', 'arcTemplates'] });
      qc.invalidateQueries({ queryKey: ['composition', 'arcTemplate'] });
      onDone?.();
    },
  });

  const cancel = () => setEstimate(null);
  const reset = () => {
    setEstimate(null);
    setResult(null);
    mint.reset();
    confirm.reset();
  };

  const error = (mint.error || confirm.error) as unknown;
  return {
    estimate, result,
    mint, confirm, cancel, reset,
    isQuota: isQuotaError(error),
    error,
  };
}
