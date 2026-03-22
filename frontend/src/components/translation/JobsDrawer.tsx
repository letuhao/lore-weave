import type { TranslationJob } from '@/features/translation/api';
import { translationApi } from '@/features/translation/api';
import { Button } from '@/components/ui/button';

type Props = {
  token: string;
  bookId: string;
  jobs: TranslationJob[];
  onClose: () => void;
  onJobsChange: (jobs: TranslationJob[]) => void;
};

const STATUS_COLOR: Record<string, string> = {
  completed: 'text-green-600',
  partial:   'text-amber-600',
  failed:    'text-red-600',
  running:   'text-amber-600',
  pending:   'text-muted-foreground',
  cancelled: 'text-muted-foreground',
};

const STATUS_ICON: Record<string, string> = {
  completed: '✓',
  partial:   '⚠',
  failed:    '✗',
  running:   '◌',
  pending:   '◌',
  cancelled: '—',
};

export function JobsDrawer({ token, jobs, onClose, onJobsChange }: Props) {
  async function handleCancel(jobId: string) {
    await translationApi.cancelJob(token, jobId);
    onJobsChange(jobs.map((j) => j.job_id === jobId ? { ...j, status: 'cancelled' } : j));
  }

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/20" onClick={onClose} />
      <div className="fixed right-0 top-0 z-50 flex h-full w-full max-w-sm flex-col border-l bg-background shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b px-4 py-3">
          <h2 className="font-semibold">Recent jobs</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">✕</button>
        </div>
        <div className="flex-1 space-y-2 overflow-y-auto p-4">
          {jobs.length === 0 && (
            <p className="text-sm text-muted-foreground">No translation jobs yet.</p>
          )}
          {jobs.map((job) => (
            <div key={job.job_id} className="rounded border p-3 text-sm space-y-1">
              <div className="flex items-center justify-between">
                <span className={STATUS_COLOR[job.status] ?? 'text-muted-foreground'}>
                  {STATUS_ICON[job.status] ?? job.status} {job.status}
                </span>
                <span className="text-xs text-muted-foreground">
                  {new Date(job.created_at).toLocaleDateString()}
                </span>
              </div>
              <p className="text-xs text-muted-foreground">
                {job.completed_chapters}/{job.total_chapters} chapters → {job.target_language}
              </p>
              {(job.status === 'pending' || job.status === 'running') && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => void handleCancel(job.job_id)}
                >
                  Cancel
                </Button>
              )}
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
