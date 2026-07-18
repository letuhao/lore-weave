// S-10 O1 — the style-voice studio dock panel. Wraps the legacy composition StyleVoicePanel (density/
// pace + per-character voice, effective-value + source-tier), which was a live capability reachable
// ONLY from the deprecated ChapterEditorPage and belonged to no session charter. Mounting it as a dock
// panel (the ReferenceShelfPanel wrapper pattern) makes style/voice steering reachable in the Studio.
//
// Book-level (project) scope: the studio dock has no reliable ambient chapter/scene, so we mount the
// project-scoped style + voice (the legacy panel's own scope picker still narrows to a chapter/scene
// when the user has one). No draft — the legacy component IS the design.
import type { IDockviewPanelProps } from 'dockview-react';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/auth';
import { StyleVoicePanel } from '@/features/composition/components/StyleVoicePanel';
import { useWorkResolution } from '@/features/composition/hooks/useWork';
import { useActiveWorkId } from '@/features/composition/hooks/useActiveWork';
import { resolveActiveWork } from '@/features/composition/workSelect';

import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';
import { WorkSetupCta } from './WorkSetupCta';

export function StyleVoiceStudioPanel(props: IDockviewPanelProps) {
  useStudioPanel('style-voice', props.api);
  const { t } = useTranslation('studio');
  const host = useStudioHost();
  const { accessToken } = useAuth();
  const resolution = useWorkResolution(host.bookId, accessToken);
  const { data: activeWorkId } = useActiveWorkId(host.bookId, accessToken);
  const work = resolveActiveWork(resolution.data, activeWorkId);

  if (!work?.project_id) {
    // F10 — mount the existing idempotent create-Work CTA and de-jargon the copy (see ReferenceShelf).
    return (
      <div
        data-testid="style-voice-nowork"
        className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center text-sm text-muted-foreground"
      >
        <p className="max-w-xs">
          {t('panels.style-voice.noWork', {
            defaultValue: "Writing isn't set up for this book yet — set it up to steer its style & voice here.",
          })}
        </p>
        <WorkSetupCta bookId={host.bookId} token={accessToken} />
      </div>
    );
  }
  return (
    <div className="h-full min-h-0 overflow-y-auto">
      <StyleVoicePanel projectId={work.project_id} token={accessToken} />
    </div>
  );
}
