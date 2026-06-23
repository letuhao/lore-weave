// Controller for "End & Evaluate": calls the scorecard pipeline and holds the
// result. Pure logic + state (React-MVC). The 400 "no transcript" and 409
// "no model" backend guards surface as friendly toasts.

import { useCallback, useState } from 'react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { interviewApi } from '../api';
import type { Scorecard } from '../types';

export interface Evaluation {
  scorecard: Scorecard | null;
  evaluating: boolean;
  evaluate: (sessionId: string) => Promise<void>;
  reset: () => void;
}

export function useEvaluation(): Evaluation {
  const { accessToken } = useAuth();
  const [scorecard, setScorecard] = useState<Scorecard | null>(null);
  const [evaluating, setEvaluating] = useState(false);

  const evaluate = useCallback(
    async (sessionId: string) => {
      if (!accessToken || evaluating) return;
      setEvaluating(true);
      try {
        const res = await interviewApi.evaluate(accessToken, sessionId);
        setScorecard(res.scorecard);
      } catch (err) {
        // apiJson throws an Error with a numeric `.status` (see src/api.ts).
        const status = (err as { status?: number }).status;
        if (status === 400) {
          toast.info('Answer at least one question before ending the interview.');
        } else if (status === 409) {
          toast.error('This session has no model configured, so it cannot be scored.');
        } else {
          toast.error('Could not produce a scorecard. Try again.');
        }
      } finally {
        setEvaluating(false);
      }
    },
    [accessToken, evaluating],
  );

  const reset = useCallback(() => setScorecard(null), []);

  return { scorecard, evaluating, evaluate, reset };
}
