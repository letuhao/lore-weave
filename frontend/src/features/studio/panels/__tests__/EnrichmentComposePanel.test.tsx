// 17_translation_enrichment_sharing_settings_docks.md — EnrichmentComposePanel: resolves
// book_id from the host, self-titles, registers, mounts its OWN EnrichmentProvider scoped to
// that book, and routes the "Use Gaps" cross-panel signal to the REAL sibling `enrichment-gaps`
// dock panel (not the internal EnrichmentView tab-switch ComposePanel falls back to when no
// override is given). Stubs the heavy ComposePanel so this test stays about the WRAPPER's own
// wiring, not ComposePanel's internals (separately covered by ComposePanel.test.tsx).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';
import { useEnrichmentContext } from '@/features/enrichment/context/EnrichmentContext';

vi.mock('@/features/enrichment/components/compose/ComposePanel', () => ({
  ComposePanel: ({ onUseGaps }: { onUseGaps?: () => void }) => {
    const { bookId } = useEnrichmentContext();
    return (
      <div data-testid="stub-compose-panel" data-book={bookId}>
        <button onClick={onUseGaps}>use-gaps</button>
      </div>
    );
  },
}));

import { EnrichmentComposePanel } from '../EnrichmentComposePanel';

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function dockProps() {
  return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
}

function withHost(bookId: string, ui: ReactNode) {
  return render(<StudioHostProvider bookId={bookId}><HostProbe />{ui}</StudioHostProvider>);
}

beforeEach(() => { hostRef = null; });

describe('EnrichmentComposePanel', () => {
  it('resolves book_id from the host, self-titles, and scopes the compose capability to this book', () => {
    const props = dockProps();
    withHost('b1', <EnrichmentComposePanel {...props} />);
    const stub = screen.getByTestId('stub-compose-panel');
    expect(stub.getAttribute('data-book')).toBe('b1');
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('registers with the host as an openable studio tool', () => {
    withHost('b1', <EnrichmentComposePanel {...dockProps()} />);
    const reg = hostRef!.getRegisteredTool('enrichment-compose');
    expect(reg).not.toBeNull();
    expect(reg!.commandId).toBe('studio.openPanel.enrichment-compose');
  });

  it('"Use Gaps" routes to the REAL sibling enrichment-gaps panel via host.openPanel, not an internal tab-switch', () => {
    withHost('b1', <EnrichmentComposePanel {...dockProps()} />);
    const spy = vi.spyOn(hostRef!, 'openPanel');
    fireEvent.click(screen.getByText('use-gaps'));
    expect(spy).toHaveBeenCalledWith('enrichment-gaps');
  });
});
