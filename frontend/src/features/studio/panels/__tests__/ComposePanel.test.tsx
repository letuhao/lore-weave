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

// APPLY-DIFF wiring proof — stub the manuscript-unit meta hook so the test can drive whether a
// chapter is "open" without mounting the full Tier-4 hoist provider.
const unitMeta = vi.hoisted(() => ({ value: null as { projectId?: string; activeChapterId: string | null } | null }));
vi.mock('../../manuscript/unit/ManuscriptUnitProvider', () => ({
  useManuscriptUnitMeta: () => unitMeta.value,
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

  // APPLY-DIFF fix (writing-studio-fragmented register #2) — EditorPanel already registers the
  // propose_edit write-back target whenever a chapter is open; chat-service only advertises
  // propose_edit when `editorContext` is present. Without this the agent could never initiate a
  // human-gated prose diff on the studio surface (chat-service test coverage alone can't catch
  // this — the gap was entirely in what the STUDIO surface passes to <Chat>).
  it('passes editorContext to <Chat> once a chapter is open, mirroring the legacy editor', () => {
    unitMeta.value = { activeChapterId: 'chapter-9' };
    render(<StudioHostProvider bookId="book-42"><ComposePanel {...dockProps} /></StudioHostProvider>);
    expect(chatProps.value).toMatchObject({
      editorContext: { book_id: 'book-42', chapter_id: 'chapter-9' },
    });
  });

  it('omits editorContext when no chapter is open yet (no false propose_edit advertisement)', () => {
    unitMeta.value = { activeChapterId: null };
    render(<StudioHostProvider bookId="book-42"><ComposePanel {...dockProps} /></StudioHostProvider>);
    expect(chatProps.value?.editorContext).toBeUndefined();
  });
});
