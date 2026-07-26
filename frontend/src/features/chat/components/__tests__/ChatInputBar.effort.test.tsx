import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

// AI-task standard — the effort dropdown is now the shared EffortSelect (unified
// 5-level vocab off|low|medium|high|auto). off → onSend(..., thinking:false, 'off'),
// medium/high/low → thinking:true + that reasoning_effort, auto → thinking:undefined
// + 'auto'. Hidden when the model can't think (never forces thinking).

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

describe('ChatInputBar — effort dropdown (EffortSelect)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('defaults to Off (session default off) and sends thinking:false + reasoning_effort "off"', () => {
    const { onSend } = renderBar();
    expect(screen.getByTestId('effort-select').textContent).toContain('input.effort_off');
    typeAndSend();
    expect(onSend).toHaveBeenCalledWith('hello', false, 'off');
  });

  it('initializes to Medium when the session default is medium and sends thinking:true + "medium"', () => {
    const { onSend } = renderBar({ effortDefault: 'medium' });
    expect(screen.getByTestId('effort-select').textContent).toContain('input.effort_medium');
    typeAndSend();
    expect(onSend).toHaveBeenCalledWith('hello', true, 'medium');
  });

  it('initializes to High from the session default and sends reasoning "high"', () => {
    const { onSend } = renderBar({ effortDefault: 'high' });
    expect(screen.getByTestId('effort-select').textContent).toContain('input.effort_high');
    typeAndSend();
    expect(onSend).toHaveBeenCalledWith('hello', true, 'high');
  });

  it('Auto sends thinking:undefined + reasoning_effort "auto" (adaptive/passthrough)', () => {
    const { onSend } = renderBar({ effortDefault: 'auto' });
    typeAndSend();
    expect(onSend).toHaveBeenCalledWith('hello', undefined, 'auto');
  });

  it('opens the menu and lists all 5 levels', () => {
    renderBar();
    fireEvent.click(screen.getByTestId('effort-select'));
    expect(screen.getByTestId('effort-select-menu')).toBeInTheDocument();
    for (const l of ['off', 'low', 'medium', 'high', 'auto']) {
      expect(screen.getByTestId(`effort-select-opt-${l}`)).toBeInTheDocument();
    }
  });

  it('picking Medium → thinking:true + "medium"; persists via onEffortChange("medium")', () => {
    const { onSend, onEffortChange } = renderBar();
    fireEvent.click(screen.getByTestId('effort-select'));
    fireEvent.click(screen.getByTestId('effort-select-opt-medium'));
    expect(onEffortChange).toHaveBeenCalledWith('medium');
    typeAndSend();
    expect(onSend).toHaveBeenCalledWith('hello', true, 'medium');
  });

  it('picking High → thinking:true + "high"; persists via onEffortChange("high")', () => {
    const { onSend, onEffortChange } = renderBar();
    fireEvent.click(screen.getByTestId('effort-select'));
    fireEvent.click(screen.getByTestId('effort-select-opt-high'));
    expect(onEffortChange).toHaveBeenCalledWith('high');
    typeAndSend();
    expect(onSend).toHaveBeenCalledWith('hello', true, 'high');
  });

  it('back to Off → thinking:false + "off"; persists via onEffortChange("off")', () => {
    const { onSend, onEffortChange } = renderBar();
    fireEvent.click(screen.getByTestId('effort-select'));
    fireEvent.click(screen.getByTestId('effort-select-opt-high'));
    fireEvent.click(screen.getByTestId('effort-select'));
    fireEvent.click(screen.getByTestId('effort-select-opt-off'));
    expect(onEffortChange).toHaveBeenLastCalledWith('off');
    typeAndSend();
    expect(onSend).toHaveBeenCalledWith('hello', false, 'off');
  });

  it('keyboard force-shortcuts override the dropdown for one send (never max high)', () => {
    const { onSend } = renderBar();
    fireEvent.click(screen.getByTestId('effort-select'));
    fireEvent.click(screen.getByTestId('effort-select-opt-high'));
    const textarea = screen.getByPlaceholderText('input.placeholder');
    // Ctrl+Enter = force off
    fireEvent.change(textarea, { target: { value: 'quick' } });
    fireEvent.keyDown(textarea, { key: 'Enter', ctrlKey: true });
    expect(onSend).toHaveBeenLastCalledWith('quick', false, 'off');
    // Ctrl+Shift+Enter = force think (medium, not high)
    fireEvent.change(textarea, { target: { value: 'ponder' } });
    fireEvent.keyDown(textarea, { key: 'Enter', ctrlKey: true, shiftKey: true });
    expect(onSend).toHaveBeenLastCalledWith('ponder', true, 'medium');
  });

  it('is hidden when the model does not support thinking; sends thinking + effort undefined', () => {
    const { onSend } = renderBar({ supportsThinking: false });
    expect(screen.queryByTestId('effort-select')).toBeNull();
    typeAndSend();
    expect(onSend).toHaveBeenCalledWith('hello', undefined, undefined);
  });
});

describe('effort ↔ session generation_params mapping', () => {
  it.each([
    [{ reasoning_effort: 'high' }, 'high'],
    [{ reasoning_effort: 'off' }, 'off'],
    [{ reasoning_effort: 'low' }, 'low'],
    [{ reasoning_effort: 'medium' }, 'medium'],
    [{ reasoning_effort: 'auto' }, 'auto'],
    // no granular knob → legacy thinking boolean decides
    [{ thinking: true }, 'medium'],
    [{ thinking: false }, 'off'],
    [{}, 'off'],
    [null, 'off'],
    // granular knob shadows a disagreeing legacy boolean
    [{ reasoning_effort: 'off', thinking: true }, 'off'],
  ] as const)('effortLevelFromGenerationParams(%j) → %s', (gp, level) => {
    expect(effortLevelFromGenerationParams(gp)).toBe(level);
  });

  it.each(['off', 'low', 'medium', 'high', 'auto'] as const)(
    'reasoningEffortForLevel(%s) round-trips through the session (identity)',
    (level) => {
      expect(reasoningEffortForLevel(level)).toBe(level);
      expect(effortLevelFromGenerationParams({ reasoning_effort: level })).toBe(level);
    },
  );
});
