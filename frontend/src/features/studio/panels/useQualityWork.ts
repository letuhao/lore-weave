// THE Work gate. One implementation, for every consumer that needs "which project, and if none —
// why not?" (the quality panels, the scene browser/inspector, the quality hub).
//
// WHY IT EXISTS. `WorkResolution.status` has SIX values, and consumers kept collapsing them:
//
//     const projectId = resolution.data?.status === 'found' ? resolution.data.work?.project_id : null;
//     if (!projectId) return <QualityNoWorkState … />;   // "This book has no co-writer session yet"
//
// That one line folds together three *different* facts and answers all of them with the same
// reassuring sentence:
//
//   • `unavailable` — composition-service is DOWN. A fact about US, not the book. The data may well
//     exist; we could not look. Saying "start composing a chapter first" is a wrong answer dressed as
//     a helpful nudge — and it invites the user to create a DUPLICATE Work.
//   • `candidates` / `unmarked_*` — the book HAS Works, we just need to pick one. Every other consumer
//     (CompositionPanel, OutlineTree, usePublishGate, useSceneBrowser) resolves this by taking the
//     first candidate. Calling it "no session yet" is simply false.
//   • `none` — the genuine answer: nothing has ever run here.
//
// UNCONSULTED IS NOT EMPTY, and AMBIGUOUS IS NOT ABSENT. Same class as the canon panel's HIGH
// (RUN-STATE DR-27). `useSceneBrowser` had already worked this out and its comment says so; three
// independent re-derivations of one gate is exactly what SDK-First exists to stop.
import { useMemo } from 'react';
import { useWorkResolution } from '@/features/composition/hooks/useWork';
import { useActiveWorkId } from '@/features/composition/hooks/useActiveWork';
import { resolveActiveWork } from '@/features/composition/workSelect';

export type QualityWorkState =
  | { kind: 'loading' }
  /** composition-service could not be reached — the data is UNKNOWN, not absent. Never a CTA. */
  | { kind: 'unavailable' }
  /** This book genuinely has no composition Work. Nothing has run; that is a real answer. */
  | { kind: 'no-work' }
  | { kind: 'ready'; projectId: string };

export function useQualityWork(bookId: string, token: string | null): QualityWorkState {
  const resolution = useWorkResolution(bookId, token);
  const { data, isLoading, isError } = resolution;
  const { data: activeWorkId } = useActiveWorkId(bookId, token);

  return useMemo<QualityWorkState>(() => {
    if (isLoading) return { kind: 'loading' };
    // An errored resolution is not an absence of work — we never got to ask.
    if (isError || data?.status === 'unavailable') return { kind: 'unavailable' };

    // `candidates` means Works EXIST. Resolve the ACTIVE Work (EC-3d: per-book pref, else
    // canonical) — one name, one concept — so the quality panels follow a "Switch to".
    const projectId = resolveActiveWork(data, activeWorkId)?.project_id ?? null;

    return projectId ? { kind: 'ready', projectId } : { kind: 'no-work' };
  }, [data, isLoading, isError, activeWorkId]);
}
