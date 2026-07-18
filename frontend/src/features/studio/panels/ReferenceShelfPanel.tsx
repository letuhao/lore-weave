// H-1a (2026-07-18 UX-hardening spec) — the reference-shelf studio panel. Wraps the legacy
// composition ReferencesPanel (which carries the S-03 add/edit/delete/search + the edit
// affordance) so a Studio user can finally reach the reference corpus without the deprecated
// ChapterEditorPage. Absorbs & supersedes S-10 O2.
//
// LIBRARY-FIRST mount (spec edge-fix): the studio dock has no reliable ambient scene, so we pass
// sceneId='' — the panel's own `{sceneId && embedModelSet && …}` gate then hides per-scene
// retrieval/pins and shows the library CRUD (the S-03 core, fully operable). Per-scene
// retrieval-in-studio is a tracked follow-up (needs the studio's active-scene plumbing).
import type { IDockviewPanelProps } from 'dockview-react';

import { useAuth } from '@/auth';
import { useUserModels } from '@/components/model-picker';
import { ReferencesPanel } from '@/features/composition/components/ReferencesPanel';
import { useWorkResolution } from '@/features/composition/hooks/useWork';
import { useActiveWorkId } from '@/features/composition/hooks/useActiveWork';
import { resolveActiveWork } from '@/features/composition/workSelect';
import { useTranslation } from 'react-i18next';

import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';
import { BookNotReadyDoor } from './BookNotReadyDoor';

export function ReferenceShelfPanel(props: IDockviewPanelProps) {
  useStudioPanel('reference-shelf', props.api);
  const { t } = useTranslation('studio');
  const host = useStudioHost();
  const { accessToken } = useAuth();
  const resolution = useWorkResolution(host.bookId, accessToken);
  const { data: activeWorkId } = useActiveWorkId(host.bookId, accessToken);
  const work = resolveActiveWork(resolution.data, activeWorkId);
  const models = useUserModels({ capability: 'embedding' }).models;

  if (!work?.project_id) {
    // F10 / Part A — the shared onboarding door (guided copy + the idempotent create-Work CTA).
    return (
      <BookNotReadyDoor
        need="work"
        bookId={host.bookId}
        token={accessToken}
        testId="reference-shelf-nowork"
        message={t('panels.reference-shelf.noWork', { defaultValue: "Writing isn't set up for this book yet — set it up to curate its reference shelf here." })}
      />
    );
  }
  return (
    <div className="h-full min-h-0 overflow-y-auto">
      <ReferencesPanel projectId={work.project_id} sceneId="" token={accessToken} models={models ?? []} />
    </div>
  );
}
