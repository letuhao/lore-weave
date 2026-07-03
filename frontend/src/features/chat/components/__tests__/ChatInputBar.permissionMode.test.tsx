import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

// RAID C2/B2 → Chat Quality Wave W4 — the Ask/Plan/Write control is now ONE
// compact dropdown (was a 3-button segmented pill): the trigger shows the
// current mode's icon + colored label, the menu lists the 3 modes with hints,
// and Ctrl+. cycles ask → plan → write. Hidden when the host surface doesn't
// wire the props (embedded surfaces) — same contract as before.

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

describe('ChatInputBar — Ask/Plan/Write mode dropdown', () => {
  beforeEach(() => vi.clearAllMocks());

  it('trigger shows the current mode; opening the menu lists all three with hints', () => {
    renderBar({ permissionMode: 'plan' });
    const trigger = screen.getByTestId('permission-mode-toggle');
    expect(trigger.textContent).toContain('input.mode_plan');
    expect(screen.queryByTestId('permission-mode-menu')).toBeNull();
    fireEvent.click(trigger);
    expect(screen.getByTestId('permission-mode-menu')).toBeInTheDocument();
    expect(screen.getByTestId('mode-opt-ask')).toBeInTheDocument();
    expect(screen.getByTestId('mode-opt-plan')).toBeInTheDocument();
    expect(screen.getByTestId('mode-opt-write')).toBeInTheDocument();
    expect(screen.getByText('input.mode_ask_hint')).toBeInTheDocument();
    // Ctrl+. cycling is documented in the menu footer
    expect(screen.getByText('input.mode_cycle_hint')).toBeInTheDocument();
  });

  it('selecting a mode fires the change and closes the menu', () => {
    const { onPermissionModeChange } = renderBar();
    fireEvent.click(screen.getByTestId('permission-mode-toggle'));
    fireEvent.click(screen.getByTestId('mode-opt-ask'));
    expect(onPermissionModeChange).toHaveBeenCalledWith('ask');
    expect(screen.queryByTestId('permission-mode-menu')).toBeNull();
  });

  it('marks the active mode via aria-checked (menuitemradio)', () => {
    renderBar({ permissionMode: 'ask' });
    fireEvent.click(screen.getByTestId('permission-mode-toggle'));
    expect(screen.getByTestId('mode-opt-ask').getAttribute('aria-checked')).toBe('true');
    expect(screen.getByTestId('mode-opt-plan').getAttribute('aria-checked')).toBe('false');
    expect(screen.getByTestId('mode-opt-write').getAttribute('aria-checked')).toBe('false');
  });

  it('Ctrl+. cycles ask → plan → write → ask from the input bar', () => {
    const { onPermissionModeChange } = renderBar({ permissionMode: 'ask' });
    const textarea = screen.getByPlaceholderText('input.placeholder');
    fireEvent.keyDown(textarea, { key: '.', ctrlKey: true });
    expect(onPermissionModeChange).toHaveBeenCalledWith('plan');
  });

  it('Ctrl+. wraps write back to ask', () => {
    const { onPermissionModeChange } = renderBar({ permissionMode: 'write' });
    fireEvent.keyDown(screen.getByPlaceholderText('input.placeholder'), { key: '.', ctrlKey: true });
    expect(onPermissionModeChange).toHaveBeenCalledWith('ask');
  });

  it('is hidden when the surface does not wire the props', () => {
    renderBar({ permissionMode: undefined, onPermissionModeChange: undefined });
    expect(screen.queryByTestId('permission-mode-toggle')).toBeNull();
  });
});
