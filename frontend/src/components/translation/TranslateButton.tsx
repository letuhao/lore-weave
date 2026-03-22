import { useEffect, useRef, useState } from 'react';
import { translationApi, type TranslationJob } from '../../features/translation/api';
import { Button } from '../ui/button';
import { Alert, AlertDescription } from '../ui/alert';

type Phase = 'idle' | 'submitting' | 'polling' | 'done' | 'partial' | 'error';

type Props = {
  token: string;
  bookId: string;
  chapterIds: string[];
  onJobCreated?: (job: TranslationJob) => void;
  disabled?: boolean;
};

export function TranslateButton({ token, bookId, chapterIds, onJobCreated, disabled }: Props) {
  const [phase, setPhase] = useState<Phase>('idle');
  const [job, setJob] = useState<TranslationJob | null>(null);
  const [error, setError] = useState<string>('');
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const networkErrorsRef = useRef(0);

  function stopPolling() {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }

  useEffect(() => () => stopPolling(), []);

  async function handleClick() {
    if (chapterIds.length === 0) return;
    setPhase('submitting');
    setError('');
    try {
      const created = await translationApi.createJob(token, bookId, { chapter_ids: chapterIds });
      setJob(created);
      onJobCreated?.(created);
      setPhase('polling');
      networkErrorsRef.current = 0;

      intervalRef.current = setInterval(async () => {
        try {
          const updated = await translationApi.getJob(token, created.job_id);
          setJob(updated);
          networkErrorsRef.current = 0;
          if (updated.status === 'completed') {
            stopPolling();
            setPhase('done');
          } else if (updated.status === 'partial') {
            stopPolling();
            setPhase('partial');
          } else if (updated.status === 'failed' || updated.status === 'cancelled') {
            stopPolling();
            setError(updated.error_message || updated.status);
            setPhase('error');
          }
        } catch {
          networkErrorsRef.current += 1;
          if (networkErrorsRef.current >= 3) {
            stopPolling();
            setError('Lost connection while polling job status');
            setPhase('error');
          }
        }
      }, 5000);
    } catch (err: unknown) {
      const msg = (err as { message?: string })?.message || 'Failed to start translation';
      setError(msg);
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

  if (phase === 'polling' && job) {
    const pct = job.total_chapters > 0
      ? Math.round((job.completed_chapters / job.total_chapters) * 100)
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
      <Button variant="outline" onClick={() => setPhase('idle')}>
        Retry
      </Button>
    </div>
  );
}
