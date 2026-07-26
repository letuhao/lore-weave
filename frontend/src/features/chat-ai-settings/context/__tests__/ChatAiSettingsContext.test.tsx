import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { ChatAiSettingsProvider, useEffectiveModel } from '../ChatAiSettingsContext';
import type { EffectiveSettings } from '../../types';

const h = vi.hoisted(() => ({ getEffective: vi.fn() }));
vi.mock('../../api', () => ({ aiSettingsApi: { getEffective: h.getEffective } }));

function Probe() {
  const chat = useEffectiveModel('chat');
  return <div data-testid="chat-model">{chat ?? 'NONE'}</div>;
}

function makeEffective(chatRef: string | null): EffectiveSettings {
  return {
    context_ref: { book_id: 'b1', session_id: null },
    models: {
      chat: {
        effective_value: chatRef ? { model_source: 'user_model', model_ref: chatRef } : null,
        source_tier: chatRef ? 'account' : 'no_model_configured',
        tier_stack: {}, skipped: [],
      },
    },
    behavior: {}, grounding: {}, voice: {}, context: {},
  };
}

describe('ChatAiSettingsContext', () => {
  beforeEach(() => h.getEffective.mockReset());

  it('useEffectiveModel returns null outside a provider (degrades, no throw)', () => {
    render(<Probe />);
    expect(screen.getByTestId('chat-model').textContent).toBe('NONE');
  });

  it('exposes the resolved chat model to consumers', async () => {
    h.getEffective.mockResolvedValue(makeEffective('acct-model'));
    render(
      <ChatAiSettingsProvider token="t" bookId="b1">
        <Probe />
      </ChatAiSettingsProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('chat-model').textContent).toBe('acct-model'));
    expect(h.getEffective).toHaveBeenCalledWith('t', { bookId: 'b1', sessionId: undefined });
  });

  it('shows NONE when no model resolves (no_model_configured)', async () => {
    h.getEffective.mockResolvedValue(makeEffective(null));
    render(
      <ChatAiSettingsProvider token="t" bookId="b1">
        <Probe />
      </ChatAiSettingsProvider>,
    );
    await waitFor(() => expect(h.getEffective).toHaveBeenCalled());
    expect(screen.getByTestId('chat-model').textContent).toBe('NONE');
  });
});
