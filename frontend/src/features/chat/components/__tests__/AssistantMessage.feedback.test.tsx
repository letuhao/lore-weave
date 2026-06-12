import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// Q3b — chat-turn feedback (thumbs + regenerate-as-negative) on AssistantMessage.

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok-1' }) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// vi.mock is hoisted above imports — the shared mock fn must be hoisted too
// (else TDZ at collection). The hook imports chatApi from '../api'; mocking the
// same module path here patches it everywhere.
const { submitMessageFeedback } = vi.hoisted(() => ({ submitMessageFeedback: vi.fn() }));
vi.mock('../../api', () => ({ chatApi: { submitMessageFeedback } }));

import { AssistantMessage } from '../AssistantMessage';

describe('AssistantMessage feedback', () => {
  beforeEach(() => {
    submitMessageFeedback.mockReset();
    submitMessageFeedback.mockResolvedValue({
      id: 'f1',
      message_id: 'm1',
      rating: 1,
      created_at: '',
    });
  });

  it('posts rating +1 on thumb up', async () => {
    render(<AssistantMessage content="Hi" messageId="m1" />);
    fireEvent.click(screen.getByTitle('message.feedback_up'));
    await waitFor(() =>
      expect(submitMessageFeedback).toHaveBeenCalledWith(
        'tok-1',
        'm1',
        expect.objectContaining({ rating: 1 }),
      ),
    );
  });

  it('posts rating -1 on thumb down', async () => {
    render(<AssistantMessage content="Hi" messageId="m1" />);
    fireEvent.click(screen.getByTitle('message.feedback_down'));
    await waitFor(() =>
      expect(submitMessageFeedback).toHaveBeenCalledWith(
        'tok-1',
        'm1',
        expect.objectContaining({ rating: -1 }),
      ),
    );
  });

  it('regenerate posts an implicit negative then runs onRegenerate', async () => {
    const onRegenerate = vi.fn();
    render(<AssistantMessage content="Hi" messageId="m1" onRegenerate={onRegenerate} />);
    fireEvent.click(screen.getByTitle('message.regenerate'));
    expect(onRegenerate).toHaveBeenCalledTimes(1);
    await waitFor(() =>
      expect(submitMessageFeedback).toHaveBeenCalledWith(
        'tok-1',
        'm1',
        expect.objectContaining({ rating: -1, reason: 'regenerated' }),
      ),
    );
  });

  it('marks the chosen thumb pressed (aria-pressed)', async () => {
    render(<AssistantMessage content="Hi" messageId="m1" />);
    const up = screen.getByTitle('message.feedback_up');
    fireEvent.click(up);
    await waitFor(() => expect(up).toHaveAttribute('aria-pressed', 'true'));
  });

  it('hides thumbs when there is no messageId', () => {
    render(<AssistantMessage content="Hi" />);
    expect(screen.queryByTitle('message.feedback_up')).toBeNull();
    expect(screen.queryByTitle('message.feedback_down')).toBeNull();
  });
});
