import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

// Chat Quality Wave W4 — the effort dropdown (replaces the Think/Fast pill).
// Fast → onSend(..., thinking:false, no effort), Standard → thinking:true,
// Deep → thinking:true + reasoning_effort:"deep". Hidden when the model does
// not support thinking (never forces thinking — market anti-pattern).

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

import {
  ChatInputBar,
  effortLevelFromGenerationParams,
  reasoningEffortForLevel,
} from '../ChatInputBar';

function renderBar(overrides: Record<string, unknown> = {}) {
  const onSend = vi.fn();
  const onEffortChange = vi.fn();
  render(
    <ChatInputBar
      onSend={onSend}
      onStop={vi.fn()}
      isStreaming={false}
      contextItems={[]}
      onAttachContext={vi.fn()}
      onDetachContext={vi.fn()}
      onClearContext={vi.fn()}
      supportsThinking
      onEffortChange={onEffortChange}
      {...overrides}
    />,
  );
  return { onSend, onEffortChange };
}

function typeAndSend(text = 'hello') {
  const textarea = screen.getByPlaceholderText('input.placeholder');
  fireEvent.change(textarea, { target: { value: text } });
  fireEvent.keyDown(textarea, { key: 'Enter' });
}

describe('ChatInputBar — effort dropdown', () => {
  beforeEach(() => vi.clearAllMocks());

  it('defaults to Fast (session default off) and sends thinking:false, no effort field', () => {
    const { onSend } = renderBar();
    expect(screen.getByTestId('effort-dropdown').textContent).toContain('input.effort_fast');
    typeAndSend();
    expect(onSend).toHaveBeenCalledWith('hello', false, undefined);
  });

  it('initializes to Standard when the session default is standard', () => {
    renderBar({ effortDefault: 'standard' });
    expect(screen.getByTestId('effort-dropdown').textContent).toContain('input.effort_standard');
  });

  it('initializes to Deep from the session default and sends reasoning "deep" (reload keeps Deep)', () => {
    const { onSend } = renderBar({ effortDefault: 'deep' });
    expect(screen.getByTestId('effort-dropdown').textContent).toContain('input.effort_deep');
    typeAndSend();
    expect(onSend).toHaveBeenCalledWith('hello', true, 'deep');
  });

  it('opens the menu and lists Fast / Standard / Deep with hints', () => {
    renderBar();
    fireEvent.click(screen.getByTestId('effort-dropdown'));
    expect(screen.getByTestId('effort-menu')).toBeInTheDocument();
    expect(screen.getByTestId('effort-opt-fast')).toBeInTheDocument();
    expect(screen.getByTestId('effort-opt-standard')).toBeInTheDocument();
    expect(screen.getByTestId('effort-opt-deep')).toBeInTheDocument();
    expect(screen.getByText('input.effort_deep_hint')).toBeInTheDocument();
  });

  it('Standard → thinking:true, no effort field; persists via onEffortChange("standard")', () => {
    const { onSend, onEffortChange } = renderBar();
    fireEvent.click(screen.getByTestId('effort-dropdown'));
    fireEvent.click(screen.getByTestId('effort-opt-standard'));
    expect(onEffortChange).toHaveBeenCalledWith('standard');
    typeAndSend();
    expect(onSend).toHaveBeenCalledWith('hello', true, undefined);
  });

  it('Deep → thinking:true + reasoning_effort:"deep"; persists via onEffortChange("deep")', () => {
    const { onSend, onEffortChange } = renderBar();
    fireEvent.click(screen.getByTestId('effort-dropdown'));
    fireEvent.click(screen.getByTestId('effort-opt-deep'));
    expect(onEffortChange).toHaveBeenCalledWith('deep');
    typeAndSend();
    expect(onSend).toHaveBeenCalledWith('hello', true, 'deep');
  });

  it('back to Fast → thinking:false; persists via onEffortChange("fast")', () => {
    const { onSend, onEffortChange } = renderBar();
    fireEvent.click(screen.getByTestId('effort-dropdown'));
    fireEvent.click(screen.getByTestId('effort-opt-deep'));
    fireEvent.click(screen.getByTestId('effort-dropdown'));
    fireEvent.click(screen.getByTestId('effort-opt-fast'));
    expect(onEffortChange).toHaveBeenLastCalledWith('fast');
    typeAndSend();
    expect(onSend).toHaveBeenCalledWith('hello', false, undefined);
  });

  it('keyboard force-shortcuts override the dropdown for one send (never deep)', () => {
    const { onSend } = renderBar();
    fireEvent.click(screen.getByTestId('effort-dropdown'));
    fireEvent.click(screen.getByTestId('effort-opt-deep'));
    const textarea = screen.getByPlaceholderText('input.placeholder');
    // Ctrl+Enter = force fast
    fireEvent.change(textarea, { target: { value: 'quick' } });
    fireEvent.keyDown(textarea, { key: 'Enter', ctrlKey: true });
    expect(onSend).toHaveBeenLastCalledWith('quick', false, undefined);
    // Ctrl+Shift+Enter = force think (standard, not deep)
    fireEvent.change(textarea, { target: { value: 'ponder' } });
    fireEvent.keyDown(textarea, { key: 'Enter', ctrlKey: true, shiftKey: true });
    expect(onSend).toHaveBeenLastCalledWith('ponder', true, undefined);
  });

  it('is hidden when the model does not support thinking; sends thinking undefined', () => {
    const { onSend } = renderBar({ supportsThinking: false });
    expect(screen.queryByTestId('effort-dropdown')).toBeNull();
    typeAndSend();
    expect(onSend).toHaveBeenCalledWith('hello', undefined, undefined);
  });
});

describe('effort ↔ session generation_params mapping', () => {
  it.each([
    [{ reasoning_effort: 'high' }, 'deep'],
    [{ reasoning_effort: 'off' }, 'fast'],
    [{ reasoning_effort: 'low' }, 'standard'],
    [{ reasoning_effort: 'medium' }, 'standard'],
    [{ reasoning_effort: 'auto' }, 'standard'],
    // no granular knob → legacy thinking boolean decides
    [{ thinking: true }, 'standard'],
    [{ thinking: false }, 'fast'],
    [{}, 'fast'],
    [null, 'fast'],
    // granular knob shadows a disagreeing legacy boolean
    [{ reasoning_effort: 'off', thinking: true }, 'fast'],
  ] as const)('effortLevelFromGenerationParams(%j) → %s', (gp, level) => {
    expect(effortLevelFromGenerationParams(gp)).toBe(level);
  });

  it.each([
    ['fast', 'off'],
    ['standard', 'medium'],
    ['deep', 'high'],
  ] as const)('reasoningEffortForLevel(%s) → %s (round-trips through the session)', (level, re) => {
    expect(reasoningEffortForLevel(level)).toBe(re);
    // the persisted value derives BACK to the same dropdown level on reload
    expect(effortLevelFromGenerationParams({ reasoning_effort: re })).toBe(level);
  });
});
