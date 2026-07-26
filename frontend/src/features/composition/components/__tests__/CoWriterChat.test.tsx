import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CoWriterActions } from '../CoWriterActions';
import { CoWriterChat } from '../CoWriterChat';

// CoWriterChat just wraps <Chat> (heavy providers); the bridge logic lives in
// CoWriterActions, which we test by mocking the chat stream/session hooks.
const { stream, session, chatProps } = vi.hoisted(() => ({ stream: vi.fn(), session: vi.fn(), chatProps: vi.fn() }));
vi.mock('../../../chat/providers', () => ({
  useChatStream: () => stream(),
  useChatSession: () => session(),
}));
// Capture the props CoWriterChat hands to <Chat> (the M2 worker-engagement wiring).
vi.mock('../../../chat/Chat', () => ({
  Chat: (props: Record<string, unknown>) => { chatProps(props); return null; },
}));

const onInsert = vi.fn();
const onUseAsGuide = vi.fn();
const send = vi.fn();

function msg(role: 'user' | 'assistant', content: string) {
  return { message_id: `${role}-${content}`, role, content };
}

beforeEach(() => {
  onInsert.mockReset(); onUseAsGuide.mockReset(); send.mockReset();
  stream.mockReturnValue({ messages: [msg('user', 'hi'), msg('assistant', 'reply text')], isStreaming: false, send });
  session.mockReturnValue({ activeSession: { session_id: 's1' } });
});

const render0 = () => render(<CoWriterActions onInsert={onInsert} onUseAsGuide={onUseAsGuide} />);

describe('CoWriterActions (T3.1)', () => {
  it('Insert as draft sends the latest reply to onAccept', () => {
    render0();
    fireEvent.click(screen.getByTestId('cowriter-insert'));
    expect(onInsert).toHaveBeenCalledWith('reply text');
  });

  it('Use as guide pushes the latest reply into the compose guide', () => {
    render0();
    fireEvent.click(screen.getByTestId('cowriter-use-guide'));
    expect(onUseAsGuide).toHaveBeenCalledWith('reply text');
  });

  it('acts on the LAST assistant reply (not an earlier one)', () => {
    stream.mockReturnValue({
      messages: [msg('assistant', 'old'), msg('user', 'more'), msg('assistant', 'newest')],
      isStreaming: false, send,
    });
    render0();
    fireEvent.click(screen.getByTestId('cowriter-insert'));
    expect(onInsert).toHaveBeenCalledWith('newest');
  });

  it('hides the action bar while streaming', () => {
    stream.mockReturnValue({ messages: [msg('assistant', 'partial')], isStreaming: true, send });
    render0();
    expect(screen.queryByTestId('cowriter-actions')).not.toBeInTheDocument();
  });

  it('shows starter chips in an empty active thread; clicking sends the prompt', () => {
    stream.mockReturnValue({ messages: [], isStreaming: false, send });
    render0();
    const chips = screen.getAllByTestId('cowriter-starter');
    expect(chips.length).toBeGreaterThanOrEqual(3);
    fireEvent.click(chips[0]);
    expect(send).toHaveBeenCalledTimes(1);
    expect(send.mock.calls[0][0]).toBeTruthy(); // a non-empty starter prompt
  });

  it('renders nothing when there is no session and no messages', () => {
    stream.mockReturnValue({ messages: [], isStreaming: false, send });
    session.mockReturnValue({ activeSession: null });
    const { container } = render0();
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByTestId('cowriter-starters')).not.toBeInTheDocument();
  });
});

describe('CoWriterChat — M2 worker-engagement wiring (D-T5.4-CHAT-HOIST)', () => {
  beforeEach(() => chatProps.mockReset());

  it('forwards windowingEnabled + forceShared to <Chat> so a windowed/popped chat survives', () => {
    render(<CoWriterChat bookId="b1" onAccept={onInsert} onUseAsGuide={onUseAsGuide} windowingEnabled forceShared />);
    expect(chatProps).toHaveBeenCalledWith(expect.objectContaining({
      bookId: 'b1', composeMode: true, windowingEnabled: true, forceShared: true,
    }));
  });

  it('defaults the engagement flags off (in-process, byte-identical to pre-M2)', () => {
    render(<CoWriterChat bookId="b1" onAccept={onInsert} onUseAsGuide={onUseAsGuide} />);
    const props = chatProps.mock.calls[0][0];
    expect(props.windowingEnabled).toBeUndefined();
    expect(props.forceShared).toBeUndefined();
  });
});
