// 13_glossary_panels.md Phase B — GlossaryMergeCandidatesPanel: a thin dock-panel wrapper around
// the existing MergeCandidatePanel. Stubs MergeCandidatePanel so this test stays about the
// wrapper's OWN wiring (registration/self-title/bookId passthrough/close-navigates-to-glossary),
// not the merge-review internals (separately tested via useMergeCandidates).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';

vi.mock('@/features/glossary/components/MergeCandidatePanel', () => ({
  MergeCandidatePanel: ({ bookId, onClose }: { bookId: string; onClose: () => void }) => (
    <div data-testid="stub-merge-candidates" data-book={bookId}>
      <button onClick={onClose}>close</button>
    </div>
  ),
}));

import { GlossaryMergeCandidatesPanel } from '../GlossaryMergeCandidatesPanel';

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

describe('GlossaryMergeCandidatesPanel', () => {
  it('resolves book_id from the host and passes it through to MergeCandidatePanel', () => {
    withHost('b1', <GlossaryMergeCandidatesPanel {...dockProps()} />);
    expect(screen.getByTestId('stub-merge-candidates').getAttribute('data-book')).toBe('b1');
  });

  it('registers with the host as an openable studio tool', () => {
    withHost('b1', <GlossaryMergeCandidatesPanel {...dockProps()} />);
    expect(hostRef!.getRegisteredTool('glossary-merge-candidates')).not.toBeNull();
    expect(hostRef!.getRegisteredTool('glossary-merge-candidates')!.commandId).toBe(
      'studio.openPanel.glossary-merge-candidates',
    );
  });

  it('self-titles the dock tab on mount', () => {
    const props = dockProps();
    withHost('b1', <GlossaryMergeCandidatesPanel {...props} />);
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('onClose navigates back to the sibling glossary panel via the host', () => {
    withHost('b1', <GlossaryMergeCandidatesPanel {...dockProps()} />);
    const addPanel = vi.fn();
    hostRef!._dockApiRef.current = { getPanel: () => null, addPanel } as never;

    fireEvent.click(screen.getByText('close'));

    expect(addPanel).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'glossary', component: 'glossary' }),
    );
  });
});
