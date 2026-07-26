// 13_glossary_panels.md Phase B — GlossaryUnknownPanel: promotes the "unknown entities" review
// surface (previously an internal view-swap inside GlossaryPanel, see D-DOCK-8) to its own real
// dock panel. Thin wrapper: sources system kinds via useEntityKinds (same as GlossaryPanel did),
// resolves book_id from the StudioHost, and routes "back" to the sibling `glossary` panel instead
// of an internal view-state toggle.
import type { IDockviewPanelProps } from 'dockview-react';
import { UnknownEntitiesPanel } from '@/features/glossary/components/UnknownEntitiesPanel';
import { useEntityKinds } from '@/features/glossary/hooks/useEntityKinds';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';

export function GlossaryUnknownPanel(props: IDockviewPanelProps) {
  useStudioPanel('glossary-unknown', props.api, { mcpToolPrefixes: ['glossary_'] });
  const host = useStudioHost();
  const { kinds } = useEntityKinds();

  return (
    <UnknownEntitiesPanel
      bookId={host.bookId}
      kinds={kinds}
      onClose={() => host.openPanel('glossary')}
    />
  );
}
