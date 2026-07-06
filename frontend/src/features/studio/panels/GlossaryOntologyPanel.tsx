// 13_glossary_panels.md Phase B — the `glossary-ontology` dock panel: a thin wrapper around the
// existing OntologyShell (Manage/Matrix/Sync tabs over the book-local ontology). Extracted out of
// GlossaryPanel's temporary internal view-swap (DOCK-8 exception) now that ontology gets its own
// dock tab. `onClose` no longer flips a local view flag — it's a real cross-panel jump back to the
// sibling `glossary` panel (the correct dockview semantic: "back to entities" = focus that tab).
import type { IDockviewPanelProps } from 'dockview-react';
import { OntologyShell } from '@/features/glossary/components/tiering/OntologyShell';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';

export function GlossaryOntologyPanel(props: IDockviewPanelProps) {
  useStudioPanel('glossary-ontology', props.api, { mcpToolPrefixes: ['glossary_'] });
  const host = useStudioHost();

  return (
    <div data-testid="studio-glossary-ontology-panel" className="h-full min-h-0 overflow-auto">
      <OntologyShell bookId={host.bookId} onClose={() => host.openPanel('glossary')} />
    </div>
  );
}
