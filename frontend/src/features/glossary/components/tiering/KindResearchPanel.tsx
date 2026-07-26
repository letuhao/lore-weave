import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Search } from 'lucide-react';
import { useKindResearch } from '../../hooks/useResearchJobs';
import { isTerminalResearchStatus } from '../../researchApi';
import { ResearchJobCard } from './ResearchJobCard';
import { ResearchLaunchModal } from './ResearchLaunchModal';

/** D-BATCH-RESEARCH-JOB M3 — the per-kind research surface: a launch button, the active
 *  job's status card, and the create modal. Owns the controller hook; ManageWorkspace
 *  renders it for the selected kind. Self-contained (CLAUDE.md: hooks own their state). */
export function KindResearchPanel({ bookId, kindId, kindName }: { bookId: string; kindId: string; kindName: string }) {
  const { t } = useTranslation('glossaryTiering');
  const { job, create, pause, resume, cancel, estimate } = useKindResearch(bookId, kindId);
  const [showModal, setShowModal] = useState(false);

  // The BE allows one live job per (book, kind); only offer launch when none is active.
  const canLaunch = !job || isTerminalResearchStatus(job.status);

  return (
    <div className="space-y-2 rounded-lg border bg-card p-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {t('research.heading')}
        </span>
        {canLaunch && (
          <button
            type="button"
            onClick={() => setShowModal(true)}
            className="flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-primary hover:bg-primary/10"
            data-testid="research-launch"
          >
            <Search className="h-3 w-3" /> {t('research.launch')}
          </button>
        )}
      </div>

      {job ? (
        <ResearchJobCard
          job={job}
          onPause={() => void pause(job.job_id)}
          onResume={() => void resume(job.job_id)}
          onCancel={() => void cancel(job.job_id)}
        />
      ) : (
        <p className="text-xs text-muted-foreground">{t('research.none')}</p>
      )}

      {showModal && (
        <ResearchLaunchModal
          kindName={kindName}
          fetchEstimate={() => estimate(0)}
          onCreate={(req) => create(req)}
          onClose={() => setShowModal(false)}
        />
      )}
    </div>
  );
}
