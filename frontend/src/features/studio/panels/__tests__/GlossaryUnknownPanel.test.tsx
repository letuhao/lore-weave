// 13_glossary_panels.md Phase B — GlossaryUnknownPanel: promotes the "unknown entities" triage
// view (previously an internal view-swap inside GlossaryPanel) to its own dock panel. This test
// stubs UnknownEntitiesPanel + useEntityKinds to isolate the wrapper's OWN wiring: registration,
// book_id/kinds pass-through, and the close callback routing back to the sibling `glossary` panel
// via the REAL host.openPanel (spied, not mocked — mirrors statusItems.test.tsx's pattern).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';

const mockKinds = [
  { kind_id: 'k1', code: 'character', name: 'Character' },
  { kind_id: 'k2', code: 'location', name: 'Location' },
];

vi.mock('@/features/glossary/hooks/useEntityKinds', () => ({
  useEntityKinds: () => ({ kinds: mockKinds, isLoading: false, error: '' }),
}));

vi.mock('@/features/glossary/components/UnknownEntitiesPanel', () => ({
  UnknownEntitiesPanel: ({ bookId, kinds, onClose }: { bookId: string; kinds: Array<{ code: string }>; onClose: () => void }) => (
    <div data-testid="stub-unknown-entities-panel" data-book={bookId} data-kinds={kinds.length}>
      <button onClick={onClose}>close</button>
    </div>
  ),
}));

import { GlossaryUnknownPanel } from '../GlossaryUnknownPanel';

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function dockProps() {
  return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
}

function withHost(bookId: string, ui: ReactNode) {
  return render(<StudioHostProvider bookId={bookId}><HostProbe />{ui}</StudioHostProvider>);
}

beforeEach(() => { hostRef = null; vi.clearAllMocks(); });

describe('GlossaryUnknownPanel', () => {
  it('resolves book_id from the host and passes system kinds through to UnknownEntitiesPanel', () => {
    const props = dockProps();
    withHost('b1', <GlossaryUnknownPanel {...props} />);
    const stub = screen.getByTestId('stub-unknown-entities-panel');
    expect(stub.getAttribute('data-book')).toBe('b1');
    expect(stub.getAttribute('data-kinds')).toBe('2');
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('registers with the host as an openable studio tool tagged with the glossary_ MCP prefix', () => {
    withHost('b1', <GlossaryUnknownPanel {...dockProps()} />);
    expect(hostRef!.getRegisteredTool('glossary-unknown')).not.toBeNull();
    expect(hostRef!.getRegisteredTool('glossary-unknown')!.commandId).toBe('studio.openPanel.glossary-unknown');
    expect(hostRef!.getRegisteredTool('glossary-unknown')!.mcpToolPrefixes).toEqual(['glossary_']);
  });

  it('closing routes back to the sibling glossary panel via host.openPanel', () => {
    withHost('b1', <GlossaryUnknownPanel {...dockProps()} />);
    const spy = vi.spyOn(hostRef!, 'openPanel');
    fireEvent.click(screen.getByText('close'));
    expect(spy).toHaveBeenCalledWith('glossary');
  });
});
