// WS-1.10 controller — "End my day": trigger the distiller, poll for the day's entry, keep it.
// CLAUDE.md MVC: all the flow logic lives here; EndOfDayReview only renders + calls back.
import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { chatApi } from '@/features/chat/api';
import { assistantApi } from '../api';
import type { DiaryEntry } from '../types';

export type EndOfDayStatus = 'idle' | 'distilling' | 'ready' | 'error';

const POLL_INTERVAL_MS = 3000;
const POLL_MAX_TRIES = 40; // ~2 min — a local-model map-reduce can be slow

export function useEndOfDay(bookId: string | null) {
  const { accessToken } = useAuth();
  const [status, setStatus] = useState<EndOfDayStatus>('idle');
  const [entry, setEntry] = useState<DiaryEntry | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [keeping, setKeeping] = useState(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const trigger = useCallback(async () => {
    if (!accessToken || !bookId) return;
    setStatus('distilling');
    setError(null);
    setEntry(null);
    try {
      // The distiller LLM is the user's chosen chat model — read it off the assistant session
      // (Q8 server-side model resolution is a follow-up; for now the session carries it).
      const sess = await chatApi.listSessions(accessToken, 'active', bookId);
      const assistant = sess.items.find((s) => s.session_kind === 'assistant') ?? sess.items[0];
      if (!assistant) {
        throw new Error('Say a few things first — the assistant needs a model to write your entry.');
      }
      const res = await assistantApi.endDay(accessToken, {
        book_id: bookId,
        model_source: assistant.model_source,
        model_ref: assistant.model_ref,
      });
      const targetDate = res.entry_date;
      if (!targetDate) {
        // The server always echoes the day it enqueued. Its absence means we can't identify THIS
        // day's entry — and we must NEVER fall back to "the newest existing entry", which could
        // surface YESTERDAY's diary as if freshly distilled (audit MED #3).
        throw new Error('The assistant could not start your entry — please try again.');
      }

      // Freshness baseline: capture the day's EXISTING entry timestamp (if any) BEFORE the re-distill
      // overwrites it, so a same-day re-run waits for the NEW draft rather than instantly showing the
      // stale pre-existing one (audit MED #3). Best-effort — a failed read just means "no baseline".
      let baselineUpdatedAt: string | null = null;
      try {
        const pre = await assistantApi.listDiaryEntries(accessToken, bookId);
        const existing = pre.entries.find(
          (e) => e.entry_date === targetDate && e.journal_kind === 'primary',
        );
        baselineUpdatedAt = existing?.draft_updated_at ?? null;
      } catch {
        /* no baseline — first-write case is handled below */
      }

      // Poll for the distilled entry (the map-reduce runs async on worker-ai).
      for (let i = 0; i < POLL_MAX_TRIES; i++) {
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
        if (!mounted.current) return;
        const list = await assistantApi.listDiaryEntries(accessToken, bookId);
        const found = list.entries.find(
          (e) =>
            e.entry_date === targetDate &&
            e.journal_kind === 'primary' &&
            e.body.trim() &&
            // FRESH: no prior entry for the day, OR this one was written AFTER the baseline
            // (draft_updated_at is server RFC3339 → lexicographic compare == chronological).
            (baselineUpdatedAt === null ||
              (!!e.draft_updated_at && e.draft_updated_at > baselineUpdatedAt)),
        );
        if (found) {
          if (mounted.current) {
            setEntry(found);
            setStatus('ready');
          }
          return;
        }
      }
      if (mounted.current) {
        setError('Your entry is taking longer than usual — check back shortly.');
        setStatus('error');
      }
    } catch (e) {
      if (mounted.current) {
        setError(e instanceof Error ? e.message : 'Failed to end the day.');
        setStatus('error');
      }
    }
  }, [accessToken, bookId]);

  const keep = useCallback(async () => {
    if (!accessToken || !bookId || !entry) return;
    setKeeping(true);
    try {
      await assistantApi.keepDiaryEntry(accessToken, bookId, entry.chapter_id);
      if (mounted.current) setEntry({ ...entry, kept: true });
      toast.success('Kept — that builds your memory.');
    } catch {
      toast.error('Could not keep the entry.');
    } finally {
      if (mounted.current) setKeeping(false);
    }
  }, [accessToken, bookId, entry]);

  return { status, entry, error, keeping, trigger, keep };
}
