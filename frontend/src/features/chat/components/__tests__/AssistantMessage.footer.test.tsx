import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

// Chat Quality Wave W2 — the per-message token footer (Windsurf pattern):
// "↑in ↓out" renders as an ALWAYS-visible muted line on persisted assistant
// messages (no hover gating on the metrics — only the action buttons fade in).

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok-1' }) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
const { submitMessageFeedback } = vi.hoisted(() => ({ submitMessageFeedback: vi.fn() }));
vi.mock('../../api', () => ({ chatApi: { submitMessageFeedback } }));

import { AssistantMessage } from '../AssistantMessage';

describe('AssistantMessage token footer', () => {
  it('renders ↑input ↓output when token counts are present', () => {
    render(<AssistantMessage content="Hi" messageId="m1" inputTokens={1234} outputTokens={567} />);
    const footer = screen.getByTestId('message-token-footer');
    expect(footer.textContent).toContain('↑1,234');
    expect(footer.textContent).toContain('↓567');
    // Always visible: the metrics line itself carries no hover-opacity gating.
    expect(footer.className).not.toContain('opacity-0');
    expect(footer.parentElement!.className).not.toContain('opacity-0');
  });

  it('renders no footer when neither tokens nor timing are present', () => {
    render(<AssistantMessage content="Hi" messageId="m1" />);
    expect(screen.queryByTestId('message-token-footer')).toBeNull();
  });

  it('renders output-only when input is null (partial data)', () => {
    render(<AssistantMessage content="Hi" messageId="m1" inputTokens={null} outputTokens={42} />);
    const footer = screen.getByTestId('message-token-footer');
    expect(footer.textContent).not.toContain('↑');
    expect(footer.textContent).toContain('↓42');
  });

  it('is suppressed while streaming', () => {
    render(<AssistantMessage content="Hi" isStreaming inputTokens={10} outputTokens={20} />);
    expect(screen.queryByTestId('message-token-footer')).toBeNull();
  });
});

describe('AssistantMessage — N2 first-class Insert (dogfood F4)', () => {
  it('renders a per-message Insert button that calls the injected onInsert with the reply content', () => {
    const onInsert = vi.fn();
    render(<AssistantMessage content="The forge glowed." messageId="m1" onInsert={onInsert} />);
    fireEvent.click(screen.getByRole('button', { name: /insert/i }));
    expect(onInsert).toHaveBeenCalledWith('The forge glowed.');
  });

  it('shows no Insert button while streaming or on an empty reply', () => {
    const onInsert = vi.fn();
    const { rerender } = render(<AssistantMessage content="partial" isStreaming onInsert={onInsert} />);
    expect(screen.queryByRole('button', { name: /insert/i })).toBeNull();
    rerender(<AssistantMessage content="   " onInsert={onInsert} />);
    expect(screen.queryByRole('button', { name: /insert/i })).toBeNull();
  });
});
