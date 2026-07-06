// 17_translation_enrichment_sharing_settings_docks.md — EnrichmentGapsPanel: resolves book_id
// from the host, self-titles, registers, and mounts its OWN EnrichmentProvider scoped to that
// book around the EXISTING GapsPanel (D-ENRICH-GAPS-NO-EXTRACT-CTA lives inside GapsPanel
// itself, covered by GapsPanel.test.tsx). Stubs the heavy GapsPanel so this test stays about
// the WRAPPER's own wiring.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';
import { useEnrichmentContext } from '@/features/enrichment/context/EnrichmentContext';

vi.mock('@/features/enrichment/components/GapsPanel', () => ({
  GapsPanel: () => {
    const { bookId } = useEnrichmentContext();
    return <div data-testid="stub-gaps-panel" data-book={bookId} />;
  },
}));

import { EnrichmentGapsPanel } from '../EnrichmentGapsPanel';

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function dockProps() {
  return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
}

function withHost(bookId: string, ui: ReactNode) {
  return render(<StudioHostProvider bookId={bookId}><HostProbe />{ui}</StudioHostProvider>);
}

beforeEach(() => { hostRef = null; });

describe('EnrichmentGapsPanel', () => {
  it('resolves book_id from the host, self-titles, and scopes the gaps capability to this book', () => {
    const props = dockProps();
    withHost('b1', <EnrichmentGapsPanel {...props} />);
    const stub = screen.getByTestId('stub-gaps-panel');
    expect(stub.getAttribute('data-book')).toBe('b1');
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('registers with the host as an openable studio tool', () => {
    withHost('b1', <EnrichmentGapsPanel {...dockProps()} />);
    const reg = hostRef!.getRegisteredTool('enrichment-gaps');
    expect(reg).not.toBeNull();
    expect(reg!.commandId).toBe('studio.openPanel.enrichment-gaps');
  });
});
