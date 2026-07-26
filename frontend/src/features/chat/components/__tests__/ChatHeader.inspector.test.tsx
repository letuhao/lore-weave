import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { ChatSession } from '../../types';

// Verify-by-EFFECT for the header's Context Inspector affordance: the button
// renders ONLY when the host supplies onOpenInspector (offered on the full chat
// page, withheld on embedded editor/studio surfaces) and clicking it fires the
// callback. i18n + the heavy child chips are stubbed so this stays a bare unit.

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));
vi.mock('@/features/knowledge/components/MemoryIndicator', () => ({
  MemoryIndicator: () => null,
}));
vi.mock('../ContextMeter', () => ({ ContextMeter: () => null }));

import { ChatHeader } from '../ChatHeader';

const session = {
  session_id: 's1',
  title: 'A Session',
  model_ref: 'm1',
  model_source: 'user_model',
  status: 'active',
  message_count: 3,
} as unknown as ChatSession;

describe('ChatHeader — Context Inspector button', () => {
  it('renders the button and fires onOpenInspector on click when the callback is provided', () => {
    const onOpenInspector = vi.fn();
    render(<ChatHeader session={session} onOpenInspector={onOpenInspector} />);
    const btn = screen.getByTestId('chat-context-inspector-button');
    expect(btn).toBeInTheDocument();
    fireEvent.click(btn);
    expect(onOpenInspector).toHaveBeenCalledTimes(1);
  });

  it('omits the button on embedded surfaces (no onOpenInspector)', () => {
    render(<ChatHeader session={session} />);
    expect(screen.queryByTestId('chat-context-inspector-button')).toBeNull();
  });
});
