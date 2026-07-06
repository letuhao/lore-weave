// 15_wiki_panels.md B1 — WikiPanel: resolves book_id from the host, self-titles, registers,
// and renders the shared WikiWorkspace (DOCK-2 — stubbed here; separately tested).
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));
vi.mock('@/features/wiki/components/WikiWorkspace', () => ({
  WikiWorkspace: ({ bookId }: { bookId: string }) => <div data-testid="stub-wiki-workspace" data-book={bookId} />,
}));

import { WikiPanel } from '../WikiPanel';

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function dockProps() {
  return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
}

function withHost(bookId: string, ui: ReactNode) {
  return render(<StudioHostProvider bookId={bookId}><HostProbe />{ui}</StudioHostProvider>);
}

describe('WikiPanel', () => {
  it('resolves bookId from the host and renders WikiWorkspace', () => {
    withHost('b1', <WikiPanel {...dockProps()} />);
    expect(screen.getByTestId('stub-wiki-workspace').getAttribute('data-book')).toBe('b1');
  });

  it('registers with the host (palette + agent openable)', () => {
    hostRef = null;
    withHost('b1', <WikiPanel {...dockProps()} />);
    expect(hostRef!.getRegisteredTool('wiki')).not.toBeNull();
    expect(hostRef!.getRegisteredTool('wiki')!.commandId).toBe('studio.openPanel.wiki');
  });
});
