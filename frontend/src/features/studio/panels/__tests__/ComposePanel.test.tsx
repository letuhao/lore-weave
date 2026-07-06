import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useRegisteredTools } from '../../host/StudioHostProvider';
import { useUiNavInterceptor } from '@/features/chat/nav/uiNavScope';

// #16 2.8 — the pop-out window-lifecycle bridge is heavy (BroadcastChannel + window.open +
// close-poll); stub it here to prove ComposePanel mounts it with the right (id/route/book/
// chapter) props once the pop-out button is clicked, without exercising the real window
// lifecycle (that's PopoutBridge's OWN test suite's job).
const popoutBridgeProps = vi.hoisted(() => ({ value: null as Record<string, unknown> | null }));
vi.mock('@/features/composition/components/workspace/PopoutBridge', () => ({
  PopoutBridge: (p: Record<string, unknown>) => { popoutBridgeProps.value = p; return <div data-testid="popout-bridge-stub" />; },
}));

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

  // #16 2.8 — pop out into a real OS/browser window (multi-monitor use), gated on a chapter
  // being open (mirrors editorContext's own gate — the popout is chapter-scoped).
  describe('pop-out button (#16 2.8)', () => {
    it('is disabled while no chapter is open', () => {
      unitMeta.value = { activeChapterId: null };
      render(<StudioHostProvider bookId="book-42"><ComposePanel {...dockProps} /></StudioHostProvider>);
      expect(screen.getByTestId('studio-compose-popout')).toBeDisabled();
    });

    it('mounts the shared PopoutBridge (route=/studio/popout) once clicked with a chapter open', () => {
      unitMeta.value = { activeChapterId: 'chapter-9' };
      render(<StudioHostProvider bookId="book-42"><ComposePanel {...dockProps} /></StudioHostProvider>);
      const btn = screen.getByTestId('studio-compose-popout');
      expect(btn).not.toBeDisabled();
      expect(screen.queryByTestId('popout-bridge-stub')).toBeNull();
      fireEvent.click(btn);
      expect(screen.getByTestId('popout-bridge-stub')).toBeInTheDocument();
      expect(popoutBridgeProps.value).toMatchObject({
        id: 'compose', bookId: 'book-42', chapterId: 'chapter-9', route: '/studio/popout',
      });
      // Re-clicking while already popped out must not spawn a second bridge instance.
      expect(btn).toBeDisabled();
    });

    it('re-enables the button and unmounts the bridge when the popout re-docks (onClosed)', () => {
      unitMeta.value = { activeChapterId: 'chapter-9' };
      render(<StudioHostProvider bookId="book-42"><ComposePanel {...dockProps} /></StudioHostProvider>);
      fireEvent.click(screen.getByTestId('studio-compose-popout'));
      expect(screen.getByTestId('popout-bridge-stub')).toBeInTheDocument();
      act(() => { (popoutBridgeProps.value!.onClosed as () => void)(); });
      expect(screen.queryByTestId('popout-bridge-stub')).toBeNull();
      expect(screen.getByTestId('studio-compose-popout')).not.toBeDisabled();
    });
  });
});
