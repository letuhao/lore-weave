import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

// WS-4.5 — voice affordance gate. A voice turn in an assistant session does not
// fire canon capture yet (the WS-4.1 gap), so the spoken diary would be silently
// dropped. `voiceEnabled={false}` must hide ALL voice controls (push-to-talk mic +
// voice-assist toggle); the default (true) keeps them for ordinary chat sessions.

vi.mock('../../voicePrefs', () => ({
  loadVoicePrefs: () => ({ voiceAssistEnabled: false, voiceAssistAppend: false }),
}));
vi.mock('../../hooks/useVoiceAssistMic', () => ({
  useVoiceAssistMic: () => ({ micState: 'idle', toggleMic: vi.fn() }),
}));
vi.mock('../../hooks/useMentionPicker', () => ({
  useMentionPicker: () => ({
    open: false, filtered: [], selectedIndex: 0,
    attachCandidate: vi.fn(), setSelectedIndex: vi.fn(),
    handleKeyDown: () => false, syncFromInput: vi.fn(),
  }),
}));
vi.mock('../../context/ContextBar', () => ({ ContextBar: () => null }));
vi.mock('../PromptTemplates', () => ({ PromptTemplatePicker: () => null }));
vi.mock('../MentionPopover', () => ({ MentionPopover: () => null }));

import { ChatInputBar } from '../ChatInputBar';

function renderBar(overrides: Record<string, unknown> = {}) {
  render(
    <ChatInputBar
      onSend={vi.fn()}
      onStop={vi.fn()}
      isStreaming={false}
      contextItems={[]}
      onAttachContext={vi.fn()}
      onDetachContext={vi.fn()}
      onClearContext={vi.fn()}
      onToggleVoiceAssist={vi.fn()}
      {...overrides}
    />,
  );
}

describe('ChatInputBar — voice affordance gate (WS-4.5)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders voice controls by default (ordinary chat session)', () => {
    renderBar();
    expect(screen.queryByLabelText('input.toggle_voice_assist')).not.toBeNull();
    expect(screen.queryByLabelText('input.mic_input')).not.toBeNull();
  });

  it('hides ALL voice controls when voiceEnabled is false (assistant session)', () => {
    renderBar({ voiceEnabled: false });
    expect(screen.queryByLabelText('input.toggle_voice_assist')).toBeNull();
    expect(screen.queryByLabelText('input.mic_input')).toBeNull();
  });
});
