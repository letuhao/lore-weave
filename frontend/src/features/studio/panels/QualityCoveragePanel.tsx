// Studio Quality tab — `quality-coverage`: book-wide promise-vs-outline audit
// (on-demand LLM pass, not persisted). DOCK-2 — thin wrapper over
// BookPromiseCoverageSection + useWorkResolution, reused AS-IS. Needs a model
// (the underlying hook only enables its Run button when modelRef is set) —
// reuses the shared app-wide ModelPicker (@/components/model-picker), never a
// bespoke <select> (the old workspace's own local-state pattern this book
// deliberately doesn't repeat here).
import { useState } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { ModelPicker } from '@/components/model-picker';
import { Skeleton } from '@/components/shared';
import { BookPromiseCoverageSection } from '@/features/composition/components/BookPromiseCoverageSection';
import { useWorkResolution } from '@/features/composition/hooks/useWork';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';
import { QualityNoWorkState } from './QualityNoWorkState';

export function QualityCoveragePanel(props: IDockviewPanelProps) {
  useStudioPanel('quality-coverage', props.api);
  const { t } = useTranslation('studio');
  const host = useStudioHost();
  const { accessToken } = useAuth();
  const resolution = useWorkResolution(host.bookId, accessToken);
  const [modelRef, setModelRef] = useState('');

  if (resolution.isLoading) {
    return (
      <div data-testid="quality-coverage-loading" className="space-y-3 p-4">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  const projectId = resolution.data?.status === 'found' ? resolution.data.work?.project_id : null;
  if (!projectId) {
    return <QualityNoWorkState testId="quality-coverage-no-work" />;
  }

  return (
    <div data-testid="studio-quality-coverage-panel" className="flex h-full min-h-0 flex-col gap-2 overflow-auto p-3 text-sm">
      <ModelPicker
        capability="chat"
        value={modelRef || null}
        onChange={(id) => setModelRef(id ?? '')}
        placeholder={t('quality.pickModel', { defaultValue: 'Pick a model to analyze with…' })}
        compact
      />
      <BookPromiseCoverageSection projectId={projectId} token={accessToken} modelRef={modelRef} />
    </div>
  );
}
