import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

// RAID C2/B2 — the Ask/Plan/Write segmented toggle in the input bar: clicking a
// segment fires onPermissionModeChange with the mode (the hook persists + sends
// it on the next message POST). Hidden when the host surface doesn't wire the
// props.

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
  const onPermissionModeChange = vi.fn();
  render(
    <ChatInputBar
      onSend={vi.fn()}
      onStop={vi.fn()}
      isStreaming={false}
      contextItems={[]}
      onAttachContext={vi.fn()}
      onDetachContext={vi.fn()}
      onClearContext={vi.fn()}
      permissionMode="write"
      onPermissionModeChange={onPermissionModeChange}
      {...overrides}
    />,
  );
  return { onPermissionModeChange };
}

describe('ChatInputBar — Ask/Plan/Write permission toggle', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders all three segments and fires each mode change', () => {
    const { onPermissionModeChange } = renderBar();
    expect(screen.getByTestId('permission-mode-toggle')).toBeInTheDocument();
    fireEvent.click(screen.getByText('input.mode_ask'));
    expect(onPermissionModeChange).toHaveBeenCalledWith('ask');
    fireEvent.click(screen.getByText('input.mode_plan'));
    expect(onPermissionModeChange).toHaveBeenCalledWith('plan');
    fireEvent.click(screen.getByText('input.mode_write'));
    expect(onPermissionModeChange).toHaveBeenCalledWith('write');
  });

  it('marks the active segment via aria-pressed', () => {
    renderBar({ permissionMode: 'ask' });
    expect(screen.getByText('input.mode_ask').closest('button')!.getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByText('input.mode_plan').closest('button')!.getAttribute('aria-pressed')).toBe('false');
    expect(screen.getByText('input.mode_write').closest('button')!.getAttribute('aria-pressed')).toBe('false');
  });

  it('marks Plan active via aria-pressed (RAID B2)', () => {
    renderBar({ permissionMode: 'plan' });
    expect(screen.getByText('input.mode_plan').closest('button')!.getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByText('input.mode_ask').closest('button')!.getAttribute('aria-pressed')).toBe('false');
    expect(screen.getByText('input.mode_write').closest('button')!.getAttribute('aria-pressed')).toBe('false');
  });

  it('is hidden when the surface does not wire the props', () => {
    renderBar({ permissionMode: undefined, onPermissionModeChange: undefined });
    expect(screen.queryByTestId('permission-mode-toggle')).toBeNull();
  });
});
