// 13_glossary_panels.md Phase B — GlossaryAiSuggestionsPanel: a thin wrapper around
// AiSuggestionsPanel. Stubs AiSuggestionsPanel so this test stays about the wrapper's OWN wiring
// (registration, bookId passthrough, the cross-panel close jump) not AiSuggestionsPanel's
// internals (separately tested). Mirrors GlossaryOntologyPanel.test.tsx.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';

vi.mock('@/features/glossary/components/AiSuggestionsPanel', () => ({
  AiSuggestionsPanel: ({ bookId, onClose }: { bookId: string; onClose: () => void }) => (
    <div data-testid="stub-ai-suggestions-panel" data-book={bookId}>
      <button onClick={onClose}>close</button>
    </div>
  ),
}));

import { GlossaryAiSuggestionsPanel } from '../GlossaryAiSuggestionsPanel';

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function dockProps() {
  return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
}

function withHost(bookId: string, ui: ReactNode) {
  return render(
    <StudioHostProvider bookId={bookId}><HostProbe />{ui}</StudioHostProvider>,
  );
}

beforeEach(() => { hostRef = null; vi.clearAllMocks(); });

describe('GlossaryAiSuggestionsPanel', () => {
  it('registers with the host as an openable studio tool', () => {
    withHost('b1', <GlossaryAiSuggestionsPanel {...dockProps()} />);
    expect(hostRef!.getRegisteredTool('glossary-ai-suggestions')).not.toBeNull();
    expect(hostRef!.getRegisteredTool('glossary-ai-suggestions')!.commandId).toBe('studio.openPanel.glossary-ai-suggestions');
  });

  it('passes bookId through from the host to AiSuggestionsPanel', () => {
    withHost('b1', <GlossaryAiSuggestionsPanel {...dockProps()} />);
    expect(screen.getByTestId('stub-ai-suggestions-panel').getAttribute('data-book')).toBe('b1');
  });

  it('self-titles the dock tab', () => {
    const props = dockProps();
    withHost('b1', <GlossaryAiSuggestionsPanel {...props} />);
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('closing jumps to the sibling glossary panel via the host, not a local view-switch', () => {
    withHost('b1', <GlossaryAiSuggestionsPanel {...dockProps()} />);
    const spy = vi.spyOn(hostRef!, 'openPanel');
    fireEvent.click(screen.getByText('close'));
    expect(spy).toHaveBeenCalledWith('glossary');
  });
});
