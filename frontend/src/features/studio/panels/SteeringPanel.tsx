// RAID C1 · Steering dock panel — author the per-book steering rules (the story-bible-as-steering
// / Cursor-rules analog). book-service owns the SSOT (book_steering); chat-service renders enabled
// entries as a <steering> system part on book-scoped turns. This panel is the authoring surface.
//
// Resolves book_id like the other book-scoped panels (EditorPanel): from the StudioHost book
// context (StudioFrame is keyed by bookId, so host.bookId is the live book), with a deep-link
// params fallback. Renders a hint when there's no book context.
import type { IDockviewPanelProps } from 'dockview-react';
import { useTranslation } from 'react-i18next';
import { useStudioHost } from '../host/StudioHostProvider';
import { SteeringManager } from '@/features/steering/components/SteeringManager';
import { useStudioPanel } from './useStudioPanel';

export function SteeringPanel(props: IDockviewPanelProps) {
  useStudioPanel('steering', props.api, { mcpToolPrefixes: ['book_'] });
  const { t } = useTranslation('studio');
  const host = useStudioHost();
  const params = props.params as { book_id?: string; bookId?: string } | undefined;
  const bookId = host.bookId || params?.book_id || params?.bookId || '';

  if (!bookId) {
    return (
      <div data-testid="studio-steering-panel" className="flex h-full items-center justify-center p-6 text-center text-xs text-muted-foreground">
        {t('steering.noBook')}
      </div>
    );
  }

  return (
    <div data-testid="studio-steering-panel" className="h-full min-h-0">
      <SteeringManager bookId={bookId} />
    </div>
  );
}
