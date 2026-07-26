// 15_chapter_browser.md B1 — panel-shell tests: registration/self-title (DOCK-3/DOCK-5) + the
// Title/Content mode toggle keeps BOTH sub-views mounted (CSS `hidden`, never a ternary unmount —
// CLAUDE.md "never conditionally unmount stateful components"). The two sub-views themselves
// (ChapterBrowserTitleView / ChapterBrowserContentView) are covered by their own test files —
// mocked here so this file stays a pure shell test.
import { act, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';

vi.mock('../ChapterBrowserTitleView', () => ({
  ChapterBrowserTitleView: ({ bookId }: { bookId: string }) => (
    <div data-testid="mock-title-view">{bookId}</div>
  ),
}));
vi.mock('../ChapterBrowserContentView', () => ({
  ChapterBrowserContentView: ({ bookId }: { bookId: string }) => (
    <div data-testid="mock-content-view">{bookId}</div>
  ),
}));

import { ChapterBrowserPanel } from '../ChapterBrowserPanel';

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function dockProps() {
  return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
}

function withHost(ui: ReactNode) {
  return render(<StudioHostProvider bookId="book-1"><HostProbe />{ui}</StudioHostProvider>);
}

beforeEach(() => { hostRef = null; });

describe('ChapterBrowserPanel', () => {
  it('registers with the host and titles its dock tab (DOCK-3/DOCK-5)', () => {
    const props = dockProps();
    withHost(<ChapterBrowserPanel {...props} />);
    expect(hostRef!.getRegisteredTool('chapter-browser')).not.toBeNull();
    expect(hostRef!.getRegisteredTool('chapter-browser')!.commandId).toBe('studio.openPanel.chapter-browser');
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('defaults to Title mode visible, Content mode hidden (not unmounted)', () => {
    withHost(<ChapterBrowserPanel {...dockProps()} />);
    expect(screen.getByTestId('chapter-browser-title-body')).not.toHaveClass('hidden');
    expect(screen.getByTestId('chapter-browser-content-body')).toHaveClass('hidden');
    // Both children are mounted regardless of which is visible.
    expect(screen.getByTestId('mock-title-view')).toBeInTheDocument();
    expect(screen.getByTestId('mock-content-view')).toBeInTheDocument();
  });

  it('switching to Content mode hides Title (CSS), never unmounts either sub-view', () => {
    withHost(<ChapterBrowserPanel {...dockProps()} />);
    act(() => { screen.getByTestId('chapter-browser-mode-content').click(); });
    expect(screen.getByTestId('chapter-browser-content-body')).not.toHaveClass('hidden');
    expect(screen.getByTestId('chapter-browser-title-body')).toHaveClass('hidden');
    // Still present in the DOM — a real unmount would remove these nodes entirely.
    expect(screen.getByTestId('mock-title-view')).toBeInTheDocument();
    expect(screen.getByTestId('mock-content-view')).toBeInTheDocument();
  });

  it('passes bookId from the studio host to both sub-views', () => {
    withHost(<ChapterBrowserPanel {...dockProps()} />);
    expect(screen.getByTestId('mock-title-view')).toHaveTextContent('book-1');
    expect(screen.getByTestId('mock-content-view')).toHaveTextContent('book-1');
  });
});
