// A2 (desktop parity) — the shared controller for the assistant's "memory + journal" capabilities (D17):
// browse/recall what's remembered, read + CORRECT past journal days, FORGET a person, ERASE everything.
// These were built as mobile-only sheets; the desktop home strip omitted them (audit gap #1 — 5 caps
// unreachable on desktop, incl. the forget/erase data-rights controls the first-run promises). This hook
// owns the 5 capability hooks + the destructive handlers (each refetches every surface the mutation
// touches), so the wiring lives in ONE place and BOTH the mobile dock and the desktop strip consume it.
import { useAssistant } from '../context/AssistantContext';
import { useDiaryEntries } from './useDiaryEntries';
import { useMemoryEntities } from './useMemoryEntities';
import { useDiaryCorrection } from './useDiaryCorrection';
import { useForgetEntity } from './useForgetEntity';
import { useEraseAllData } from './useEraseAllData';

export function useAssistantMemory() {
  const { bookId, reprovision, captureRail: rail } = useAssistant();
  const journal = useDiaryEntries(bookId);
  const memory = useMemoryEntities(bookId);
  const correction = useDiaryCorrection(bookId);
  const forgetEntity = useForgetEntity(bookId);
  const eraseAll = useEraseAllData();

  // D17 — correcting a day re-distills its facts; forgetting a person deletes them. Both change what
  // "memory" holds, so refetch the journal + the What-I-know list + the capture rail after either succeeds.
  const handleCorrect = async (chapterId: string, body: string, title?: string) => {
    const res = await correction.correct(chapterId, body, title);
    if (res?.amended) {
      void journal.refresh();
      void memory.refresh();
      void rail.refresh();
    }
    return res;
  };
  const handleForget = async (name: string) => {
    const res = await forgetEntity.forget(name);
    if (res?.forgotten) {
      void memory.refresh();
      void rail.refresh();
    }
    return res;
  };
  // Erase wipes memory + journal + the diary book server-side, so the in-session bookId is now dead —
  // re-provision an empty diary (idempotent) so the surfaces bind to a live book, then refresh them.
  // The consumer additionally refreshes its own fact inbox (a separate hook it owns).
  const handleEraseAll = async () => {
    const ok = await eraseAll.erase();
    if (ok) {
      reprovision();
      void memory.refresh();
      void journal.refresh();
      void rail.refresh();
    }
    return ok;
  };

  return { journal, memory, correction, forgetEntity, eraseAll, handleCorrect, handleForget, handleEraseAll };
}
