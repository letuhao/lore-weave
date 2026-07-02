import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useRegisteredTools } from '../../host/StudioHostProvider';
import { useUiNavInterceptor } from '@/features/chat/nav/uiNavScope';

// The whole chat feature is embedded AS-IS; stub it here to capture the props the panel passes.
// The stub also probes the nav-interceptor context from where the real Chat tree would read it.
const chatProps = vi.hoisted(() => ({ value: null as Record<string, unknown> | null }));
const seenInterceptor = vi.hoisted(() => ({ value: null as unknown }));
vi.mock('@/features/chat/Chat', () => ({
  Chat: (p: Record<string, unknown>) => {
    chatProps.value = p;
    seenInterceptor.value = useUiNavInterceptor();
    return <div data-testid="chat-stub" />;
  },
}));

import { ComposePanel } from '../ComposePanel';

const dockProps = { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;

describe('ComposePanel', () => {
  it('embeds <Chat> with the host bookId + windowing (turn survives dock float/close)', () => {
    render(<StudioHostProvider bookId="book-42"><ComposePanel {...dockProps} /></StudioHostProvider>);
    expect(screen.getByTestId('chat-stub')).toBeTruthy();
    expect(chatProps.value).toMatchObject({ bookId: 'book-42', windowingEnabled: true });
  });

  // #12 M-E wiring proof — the panel must PROVIDE the studio nav interceptor to the chat
  // tree, and it must claim a same-book ui_open_book (the live-caught studio-killing nav).
  // A dropped provider would leave every other test green while restoring the bug.
  it('provides the studio nav interceptor that claims same-book C-NAV calls', () => {
    render(<StudioHostProvider bookId="book-42"><ComposePanel {...dockProps} /></StudioHostProvider>);
    const intercept = seenInterceptor.value as ((t: string, a: Record<string, unknown>) => unknown) | null;
    expect(typeof intercept).toBe('function');
    const claimed = intercept!('ui_open_book', { book_id: 'book-42' }) as { path: null; result: { opened: boolean } };
    expect(claimed).toMatchObject({ path: null, result: { opened: true } });
    expect(intercept!('ui_open_book', { book_id: 'ANOTHER' })).toBeNull();
  });

  it('registers itself as the "compose" studio tool (for the agent rack)', () => {
    let tools: ReturnType<typeof useRegisteredTools> = [];
    function Probe() { tools = useRegisteredTools(); return null; }
    render(
      <StudioHostProvider bookId="b1"><ComposePanel {...dockProps} /><Probe /></StudioHostProvider>,
    );
    const compose = tools.find((t) => t.panelId === 'compose');
    expect(compose).toBeTruthy();
    expect(compose?.commandId).toBe('studio.openPanel.compose');
    expect(compose?.mcpToolPrefixes).toContain('composition_');
  });
});
