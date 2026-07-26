import { useContext } from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { StudioPopoutHost } from '../StudioPopoutHost';
import { PopoutRelayContext } from '../popoutRelayContext';
import { openPopoutChannel, type PopoutMessage } from '@/features/composition/workspace/popoutChannel';

// Mock the heavy chat surface — this test exercises the popout SHELL (param parsing,
// props threaded to <Chat>, the relay context, dock-back), not the chat internals.
// A small real component (not a bare stub) so it can read PopoutRelayContext via
// useContext, mirroring how a real ProposeEditCard inside <Chat> would.
const chatProps = vi.fn();
vi.mock('@/features/chat/Chat', () => ({
  Chat: (props: Record<string, unknown>) => {
    chatProps(props);
    return <ChatRelayProbe />;
  },
}));

const relayResult = vi.fn();
function ChatRelayProbe() {
  const relay = useContext(PopoutRelayContext);
  return (
    <div data-testid="chat-mock">
      <button data-testid="emit-relay" onClick={() => void relay?.post('drafted', 'qwen').then(relayResult)}>relay</button>
    </div>
  );
}

function renderAt(query: string) {
  return render(
    <MemoryRouter initialEntries={[`/studio/popout${query}`]}>
      <StudioPopoutHost />
    </MemoryRouter>,
  );
}

describe('StudioPopoutHost (#16 2.8)', () => {
  beforeEach(() => { chatProps.mockClear(); relayResult.mockClear(); });

  it('renders <Chat> with editorContext/studioContext derived from URL params', () => {
    renderAt('?book=b1&chapter=c1');
    expect(screen.getByTestId('chat-mock')).toBeInTheDocument();
    expect(chatProps).toHaveBeenCalledTimes(1);
    expect(chatProps.mock.calls[0][0]).toMatchObject({
      bookId: 'b1',
      editorContext: { book_id: 'b1', chapter_id: 'c1' },
      studioContext: { book_id: 'b1', active_chapter_id: 'c1' },
      windowingEnabled: true,
      className: 'h-full',
    });
  });

  it('rejects when required params are missing (no book)', () => {
    renderAt('?chapter=c1');
    expect(screen.queryByTestId('chat-mock')).toBeNull();
    expect(screen.getByText('popout.invalid')).toBeInTheDocument();
  });

  it('rejects when required params are missing (no chapter)', () => {
    renderAt('?book=b1');
    expect(screen.queryByTestId('chat-mock')).toBeNull();
    expect(screen.getByText('popout.invalid')).toBeInTheDocument();
  });

  it('relays prose posted via PopoutRelayContext to the opener over the per-(book,chapter) channel', async () => {
    // FILE-UNIQUE book id — BroadcastChannel is shared across vitest worker threads, so a
    // generic 'b1'/'c1' can cross-talk with sibling popout-channel tests (see PopoutHost.test's
    // own PHOST_ convention).
    const opener = openPopoutChannel('SPH_relay', 'c1');
    const got: PopoutMessage[] = [];
    opener.subscribe((m) => got.push(m));
    renderAt('?book=SPH_relay&chapter=c1');
    fireEvent.click(screen.getByTestId('emit-relay'));
    await waitFor(() => expect(got).toContainEqual(
      expect.objectContaining({ kind: 'insert-prose', text: 'drafted', model: 'qwen' }),
    ));
    opener.close();
  });

  // #16 2.8 /review-impl HIGH fix — post() now waits for the opener's ack instead of assuming
  // a bare BroadcastChannel post succeeded (the opener may have navigated to a different
  // chapter and dropped the message silently).
  it('post() resolves true once the opener acks the matching reqId', async () => {
    const opener = openPopoutChannel('SPH_ack_ok', 'c1');
    opener.subscribe((m) => {
      if (m.kind === 'insert-prose' && m.reqId) opener.post({ kind: 'insert-ack', reqId: m.reqId, ok: true });
    });
    renderAt('?book=SPH_ack_ok&chapter=c1');
    fireEvent.click(screen.getByTestId('emit-relay'));
    await waitFor(() => expect(relayResult).toHaveBeenCalledWith(true));
    opener.close();
  });

  it('post() resolves false when no ack arrives before the timeout (silent-drop guard)', async () => {
    vi.useFakeTimers();
    try {
      // No subscriber acks this channel — simulates the opener having navigated away.
      renderAt('?book=SPH_ack_timeout&chapter=c1');
      fireEvent.click(screen.getByTestId('emit-relay'));
      await vi.advanceTimersByTimeAsync(4000);
      expect(relayResult).toHaveBeenCalledWith(false);
    } finally {
      vi.useRealTimers();
    }
  });

  it('dock-back posts dock-back for the compose panel + closes the window', async () => {
    const close = vi.spyOn(window, 'close').mockImplementation(() => {});
    const opener = openPopoutChannel('SPH_dock', 'c1');
    const got: PopoutMessage[] = [];
    opener.subscribe((m) => got.push(m));
    renderAt('?book=SPH_dock&chapter=c1');
    fireEvent.click(screen.getByTestId('studio-popout-dock-back'));
    await waitFor(() => expect(got).toContainEqual({ kind: 'dock-back', panel: 'compose' }));
    expect(close).toHaveBeenCalledTimes(1);
    opener.close();
    close.mockRestore();
  });
});
