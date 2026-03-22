import { useCallback, useRef, useState } from 'react';
import { translationApi, type TranslationJob } from '../../features/translation/api';
import { useJobEvents, type JobEvent } from '../../hooks/useJobEvents';
import { Button } from '../ui/button';
import { Alert, AlertDescription } from '../ui/alert';

type Phase = 'idle' | 'submitting' | 'listening' | 'done' | 'partial' | 'error';

type Props = {
  token: string;
  bookId: string;
  chapterIds: string[];
  onJobCreated?: (job: TranslationJob) => void;
  disabled?: boolean;
};

export function TranslateButton({ token, bookId, chapterIds, onJobCreated, disabled }: Props) {
  const [phase, setPhase] = useState<Phase>('idle');
  const [job,   setJob]   = useState<TranslationJob | null>(null);
  const [error, setError] = useState('');
  const jobIdRef = useRef<string | null>(null);

  const handleEvent = useCallback((e: JobEvent) => {
    if (!jobIdRef.current || e.job_id !== jobIdRef.current) return;

    if (e.event === 'job.status_changed') {
      const p = e.payload as {
        status: TranslationJob['status'];
        completed_chapters: number;
        failed_chapters: number;
      };
      setJob((prev) => prev ? { ...prev, ...p } : prev);

      if      (p.status === 'completed') setPhase('done');
      else if (p.status === 'partial')   setPhase('partial');
      else if (p.status === 'failed' || p.status === 'cancelled') {
        setError(p.status);
        setPhase('error');
      }
    }

    if (e.event === 'job.chapter_done') {
      const p = e.payload as { completed_chapters?: number; failed_chapters?: number };
      setJob((prev) => prev ? { ...prev, ...p } : prev);
    }
  }, []);

  // Poll once on reconnect to fill any state gap that occurred while disconnected
  const handleReconnect = useCallback(async () => {
    if (!jobIdRef.current) return;
    try {
      const latest = await translationApi.getJob(token, jobIdRef.current);
      setJob(latest);
      if      (latest.status === 'completed') setPhase('done');
      else if (latest.status === 'partial')   setPhase('partial');
      else if (latest.status === 'failed' || latest.status === 'cancelled') {
        setError(latest.status);
        setPhase('error');
      }
    } catch {
      // best-effort — WS will continue delivering future events
    }
  }, [token]);

  useJobEvents({
    onEvent:      handleEvent,
    onReconnect:  handleReconnect,
    enabled:      phase === 'listening',
  });

  async function handleClick() {
    if (chapterIds.length === 0) return;
    setPhase('submitting');
    setError('');
    try {
      const created    = await translationApi.createJob(token, bookId, { chapter_ids: chapterIds });
      jobIdRef.current = created.job_id;
      setJob(created);
      onJobCreated?.(created);
      setPhase('listening');
    } catch (err: unknown) {
      setError((err as { message?: string })?.message || 'Failed to start translation');
      setPhase('error');
    }
  }

  if (phase === 'idle') {
    return (
      <Button onClick={handleClick} disabled={disabled || chapterIds.length === 0}>
        Translate
      </Button>
    );
  }

  if (phase === 'submitting') {
    return <Button disabled>Translating…</Button>;
  }

  if (phase === 'listening' && job) {
    const pct = job.total_chapters > 0
      ? Math.round(((job.completed_chapters + job.failed_chapters) / job.total_chapters) * 100)
      : 0;
    return (
      <div className="space-y-2" aria-live="polite">
        <p className="text-sm">
          Translating… {job.completed_chapters}/{job.total_chapters} chapters
        </p>
        <div className="h-2 w-full overflow-hidden rounded bg-muted">
          <div className="h-full bg-primary transition-all" style={{ width: `${pct}%` }} />
        </div>
      </div>
    );
  }

  if (phase === 'done' && job) {
    return (
      <p className="text-sm text-green-600">
        ✓ {job.completed_chapters} chapters translated
      </p>
    );
  }

  if (phase === 'partial' && job) {
    return (
      <p className="text-sm text-amber-600">
        ⚠ {job.completed_chapters}/{job.total_chapters} chapters translated ({job.failed_chapters} failed)
      </p>
    );
  }

  // error
  return (
    <div className="space-y-2">
      <Alert variant="destructive">
        <AlertDescription>{error}</AlertDescription>
      </Alert>
      <Button variant="outline" onClick={() => { setPhase('idle'); jobIdRef.current = null; }}>
        Retry
      </Button>
    </div>
  );
}
