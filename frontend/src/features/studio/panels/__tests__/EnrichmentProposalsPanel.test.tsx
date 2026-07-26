// 17_translation_enrichment_sharing_settings_docks.md — EnrichmentProposalsPanel: resolves
// book_id from the host, self-titles, registers, and mounts its OWN EnrichmentProvider scoped
// to that book around the EXISTING ProposalsPanel (the review workspace / e2e target). Stubs
// the heavy ProposalsPanel so this test stays about the WRAPPER's own wiring, not
// ProposalsPanel's internals (separately covered by ProposalsPanel.test.tsx).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';
import { useEnrichmentContext } from '@/features/enrichment/context/EnrichmentContext';

vi.mock('@/features/enrichment/components/ProposalsPanel', () => ({
  ProposalsPanel: () => {
    const { bookId } = useEnrichmentContext();
    return <div data-testid="stub-proposals-panel" data-book={bookId} />;
  },
}));

import { EnrichmentProposalsPanel } from '../EnrichmentProposalsPanel';

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function dockProps() {
  return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
}

function withHost(bookId: string, ui: ReactNode) {
  return render(<StudioHostProvider bookId={bookId}><HostProbe />{ui}</StudioHostProvider>);
}

beforeEach(() => { hostRef = null; });

describe('EnrichmentProposalsPanel', () => {
  it('resolves book_id from the host, self-titles, and scopes the proposals capability to this book', () => {
    const props = dockProps();
    withHost('b1', <EnrichmentProposalsPanel {...props} />);
    const stub = screen.getByTestId('stub-proposals-panel');
    expect(stub.getAttribute('data-book')).toBe('b1');
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('registers with the host as an openable studio tool', () => {
    withHost('b1', <EnrichmentProposalsPanel {...dockProps()} />);
    const reg = hostRef!.getRegisteredTool('enrichment-proposals');
    expect(reg).not.toBeNull();
    expect(reg!.commandId).toBe('studio.openPanel.enrichment-proposals');
  });

  it('a different book scopes the SAME capability independently (no cross-book leak)', () => {
    withHost('b2', <EnrichmentProposalsPanel {...dockProps()} />);
    expect(screen.getByTestId('stub-proposals-panel').getAttribute('data-book')).toBe('b2');
  });
});
