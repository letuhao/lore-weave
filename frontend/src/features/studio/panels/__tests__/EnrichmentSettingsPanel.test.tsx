// 17_translation_enrichment_sharing_settings_docks.md — EnrichmentSettingsPanel: resolves
// book_id from the host, self-titles, registers, and mounts its OWN EnrichmentProvider scoped
// to that book around the EXISTING SettingsPanel (the per-book de-bias PROFILE authoring
// surface). Stubs the heavy SettingsPanel so this test stays about the WRAPPER's own wiring,
// not SettingsPanel's internals (separately covered by ProfileForm.test.tsx).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';
import { useEnrichmentContext } from '@/features/enrichment/context/EnrichmentContext';

vi.mock('@/features/enrichment/components/SettingsPanel', () => ({
  SettingsPanel: () => {
    const { bookId } = useEnrichmentContext();
    return <div data-testid="stub-enrichment-settings-panel" data-book={bookId} />;
  },
}));

import { EnrichmentSettingsPanel } from '../EnrichmentSettingsPanel';

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function dockProps() {
  return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
}

function withHost(bookId: string, ui: ReactNode) {
  return render(<StudioHostProvider bookId={bookId}><HostProbe />{ui}</StudioHostProvider>);
}

beforeEach(() => { hostRef = null; });

describe('EnrichmentSettingsPanel', () => {
  it('resolves book_id from the host, self-titles, and scopes the profile capability to this book', () => {
    const props = dockProps();
    withHost('b1', <EnrichmentSettingsPanel {...props} />);
    const stub = screen.getByTestId('stub-enrichment-settings-panel');
    expect(stub.getAttribute('data-book')).toBe('b1');
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('registers with the host as an openable studio tool', () => {
    withHost('b1', <EnrichmentSettingsPanel {...dockProps()} />);
    const reg = hostRef!.getRegisteredTool('enrichment-settings');
    expect(reg).not.toBeNull();
    expect(reg!.commandId).toBe('studio.openPanel.enrichment-settings');
  });
});
