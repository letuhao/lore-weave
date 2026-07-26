// ACP A4.3 — the CLIENT MIRROR of the server's wrap enforcement (SDK compute_progress /
// resolve_anchor). The server is authoritative — it injects the wrap directive into the
// interviewer's prompt so the model actually closes at the target. This is the read-only display
// so the Practice UI can show "Question 3 of 5" + a countdown that MATCHES what the server does.
// Keep the formula byte-aligned with the backend: question_count = message_count // 2; wrap when
// count >= target OR elapsed >= budget; an interview genre defaults target to 5 (as roleplay's
// charter::freeze does).

import type { Script } from '../types';

export const DEFAULT_INTERVIEW_QUESTION_TARGET = 5;

export interface PracticeProgress {
  questionCount: number;
  target: number | null; // null ⇒ freeform (no count-wrap)
  elapsedMin: number | null;
  budgetMin: number | null;
  wrapping: boolean; // the server is closing the interview now (count/time reached)
}

/**
 * Mirror the server's interview progress for display.
 * @param messageCount total messages in the session (user + assistant).
 * @param startedAt    the session's created_at ISO string (for the elapsed/countdown), or null.
 * @param script       the practice script (its scenario carries question_target / time_budget_min).
 * @param nowMs        injectable clock (tests pass a fixed value).
 */
export function practiceProgress(
  messageCount: number,
  startedAt: string | null,
  script: Script | undefined,
  nowMs: number = Date.now(),
): PracticeProgress {
  const scenario = script?.scenario;
  const target =
    scenario?.question_target ??
    (script?.genre === 'interview' ? DEFAULT_INTERVIEW_QUESTION_TARGET : null);
  const budgetMin = scenario?.time_budget_min ?? null;

  const questionCount = Math.max(0, Math.floor((messageCount ?? 0) / 2));
  const elapsedMin =
    startedAt != null
      ? Math.max(0, Math.floor((nowMs - new Date(startedAt).getTime()) / 60000))
      : null;

  const byCount = target != null && questionCount >= target;
  const byTime = budgetMin != null && elapsedMin != null && elapsedMin >= budgetMin;

  return { questionCount, target, elapsedMin, budgetMin, wrapping: Boolean(byCount || byTime) };
}
