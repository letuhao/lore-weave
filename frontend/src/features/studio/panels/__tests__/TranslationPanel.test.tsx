// TranslationPanel — thin wrapper reusing the classic TranslationTab AS-IS (DOCK-2), resolving
// book_id from the studio host instead of a route param (DOCK-7). Stubs TranslationTab (its own
// coverage-matrix/filter/bulk-action logic is covered by TranslationTab's own tests) so this test
// stays about THIS panel's own wiring: registration, self-titling, book_id resolution, and the
// onManageVersions → host.openPanel('translation-versions', ...) DOCK-7 seam.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const onManageVersionsCalls: Array<[string, string]> = [];
vi.mock('@/pages/book-tabs/TranslationTab', () => ({
  TranslationTab: ({
    bookId,
    onManageVersions,
  }: {
    bookId: string;
    onManageVersions?: (chapterId: string, lang: string) => void;
  }) => (
    <div data-testid="stub-translation-tab" data-book={bookId}>
      <button onClick={() => onManageVersions?.('ch1', 'vi')}>manage-versions</button>
    </div>
  ),
}));

import { TranslationPanel } from '../TranslationPanel';

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

beforeEach(() => {
  hostRef = null;
  onManageVersionsCalls.length = 0;
});

describe('TranslationPanel', () => {
  it('resolves book_id from the host and renders the coverage matrix', () => {
    withHost('b1', <TranslationPanel {...dockProps()} />);
    const stub = screen.getByTestId('stub-translation-tab');
    expect(stub.getAttribute('data-book')).toBe('b1');
  });

  it('self-titles the dock tab on mount', () => {
    const props = dockProps();
    withHost('b1', <TranslationPanel {...props} />);
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('registers with the host as an openable studio tool, with no MCP tool prefixes (translation has no MCP tools)', () => {
    withHost('b1', <TranslationPanel {...dockProps()} />);
    const reg = hostRef!.getRegisteredTool('translation');
    expect(reg).not.toBeNull();
    expect(reg!.commandId).toBe('studio.openPanel.translation');
    expect(reg!.mcpToolPrefixes).toBeUndefined();
  });

  it('DOCK-7: routes a matrix-cell "manage versions" action to the translation-versions sibling panel via host.openPanel, never navigate', () => {
    withHost('b1', <TranslationPanel {...dockProps()} />);
    const openPanelSpy = vi.spyOn(hostRef!, 'openPanel');
    fireEvent.click(screen.getByText('manage-versions'));
    expect(openPanelSpy).toHaveBeenCalledWith('translation-versions', { params: { chapterId: 'ch1', lang: 'vi' } });
  });
});
