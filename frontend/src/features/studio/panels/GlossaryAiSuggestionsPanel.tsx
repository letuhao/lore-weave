// 13_glossary_panels.md Phase B — the `glossary-ai-suggestions` dock panel: a thin wrapper
// around the existing AiSuggestionsPanel (the AI-pipeline v2 draft-entity inbox). Extracted out
// of GlossaryPanel's temporary internal view-swap (DOCK-8 exception) now that ai_suggestions gets
// its own dock tab. `onClose` no longer flips a local view flag — it's a real cross-panel jump
// back to the sibling `glossary` panel (the correct dockview semantic: "back to entities" = focus
// that tab), mirroring GlossaryOntologyPanel.
import type { IDockviewPanelProps } from 'dockview-react';
import { AiSuggestionsPanel } from '@/features/glossary/components/AiSuggestionsPanel';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';

export function GlossaryAiSuggestionsPanel(props: IDockviewPanelProps) {
  useStudioPanel('glossary-ai-suggestions', props.api, { mcpToolPrefixes: ['glossary_'] });
  const host = useStudioHost();

  return (
    <div data-testid="studio-glossary-ai-suggestions-panel" className="h-full min-h-0 overflow-auto">
      <AiSuggestionsPanel bookId={host.bookId} onClose={() => host.openPanel('glossary')} />
    </div>
  );
}
