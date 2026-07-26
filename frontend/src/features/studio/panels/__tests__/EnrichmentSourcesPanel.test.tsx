// 17_translation_enrichment_sharing_settings_docks.md — EnrichmentSourcesPanel: resolves
// book_id from the host, self-titles, registers, and mounts its OWN EnrichmentProvider scoped
// to that book around the EXISTING SourcesPanel (license-tagged corpus material for retrieval/
// recook). Stubs the heavy SourcesPanel so this test stays about the WRAPPER's own wiring, not
// SourcesPanel's internals (separately covered by SourcesPanel.test.tsx).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';
import { useEnrichmentContext } from '@/features/enrichment/context/EnrichmentContext';

vi.mock('@/features/enrichment/components/SourcesPanel', () => ({
  SourcesPanel: () => {
    const { bookId } = useEnrichmentContext();
    return <div data-testid="stub-sources-panel" data-book={bookId} />;
  },
}));

import { EnrichmentSourcesPanel } from '../EnrichmentSourcesPanel';

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function dockProps() {
  return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
}

function withHost(bookId: string, ui: ReactNode) {
  return render(<StudioHostProvider bookId={bookId}><HostProbe />{ui}</StudioHostProvider>);
}

beforeEach(() => { hostRef = null; });

describe('EnrichmentSourcesPanel', () => {
  it('resolves book_id from the host, self-titles, and scopes the sources capability to this book', () => {
    const props = dockProps();
    withHost('b1', <EnrichmentSourcesPanel {...props} />);
    const stub = screen.getByTestId('stub-sources-panel');
    expect(stub.getAttribute('data-book')).toBe('b1');
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('registers with the host as an openable studio tool', () => {
    withHost('b1', <EnrichmentSourcesPanel {...dockProps()} />);
    const reg = hostRef!.getRegisteredTool('enrichment-sources');
    expect(reg).not.toBeNull();
    expect(reg!.commandId).toBe('studio.openPanel.enrichment-sources');
  });
});
