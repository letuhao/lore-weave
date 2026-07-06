// 13_glossary_panels.md Phase B — GlossaryOntologyPanel: a thin wrapper around OntologyShell.
// Stubs OntologyShell so this test stays about the wrapper's OWN wiring (registration, bookId
// passthrough, the cross-panel close jump) not OntologyShell's internals (separately tested).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';

vi.mock('@/features/glossary/components/tiering/OntologyShell', () => ({
  OntologyShell: ({ bookId, onClose }: { bookId: string; onClose: () => void }) => (
    <div data-testid="stub-ontology-shell" data-book={bookId}>
      <button onClick={onClose}>close</button>
    </div>
  ),
}));

import { GlossaryOntologyPanel } from '../GlossaryOntologyPanel';

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

describe('GlossaryOntologyPanel', () => {
  it('registers with the host as an openable studio tool', () => {
    withHost('b1', <GlossaryOntologyPanel {...dockProps()} />);
    expect(hostRef!.getRegisteredTool('glossary-ontology')).not.toBeNull();
    expect(hostRef!.getRegisteredTool('glossary-ontology')!.commandId).toBe('studio.openPanel.glossary-ontology');
  });

  it('passes bookId through from the host to OntologyShell', () => {
    withHost('b1', <GlossaryOntologyPanel {...dockProps()} />);
    expect(screen.getByTestId('stub-ontology-shell').getAttribute('data-book')).toBe('b1');
  });

  it('self-titles the dock tab', () => {
    const props = dockProps();
    withHost('b1', <GlossaryOntologyPanel {...props} />);
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('closing jumps to the sibling glossary panel via the host, not a local view-switch', () => {
    withHost('b1', <GlossaryOntologyPanel {...dockProps()} />);
    const spy = vi.spyOn(hostRef!, 'openPanel');
    fireEvent.click(screen.getByText('close'));
    expect(spy).toHaveBeenCalledWith('glossary');
  });
});
