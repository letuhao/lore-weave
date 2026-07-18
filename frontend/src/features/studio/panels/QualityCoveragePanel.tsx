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
import { BookPromiseCoverageSection } from '@/features/composition/components/BookPromiseCoverageSection';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';
import { QualityWorkGate } from './QualityNoWorkState';
import { useQualityWork } from './useQualityWork';

export function QualityCoveragePanel(props: IDockviewPanelProps) {
  useStudioPanel('quality-coverage', props.api);
  const { t } = useTranslation('studio');
  const host = useStudioHost();
  const { accessToken } = useAuth();
  // `unavailable` (composition-service is DOWN) must NOT render as "no co-writer session yet" —
  // unconsulted is not empty. See useQualityWork / RUN-STATE DR-27.
  const work = useQualityWork(host.bookId, accessToken);
  const [modelRef, setModelRef] = useState('');

  if (work.kind !== 'ready') return <QualityWorkGate state={work} testIdPrefix="quality-coverage" bookId={host.bookId} token={accessToken} />;

  return (
    <div data-testid="studio-quality-coverage-panel" className="flex h-full min-h-0 flex-col gap-2 overflow-auto p-3 text-sm">
      <ModelPicker
        capability="chat"
        value={modelRef || null}
        onChange={(id) => setModelRef(id ?? '')}
        placeholder={t('quality.pickModel', { defaultValue: 'Pick a model to analyze with…' })}
        compact
      />
      <BookPromiseCoverageSection projectId={work.projectId} token={accessToken} modelRef={modelRef} />
    </div>
  );
}
