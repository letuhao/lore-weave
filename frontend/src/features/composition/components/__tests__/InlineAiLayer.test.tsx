import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { InlineAiLayer } from '../InlineAiLayer';

// Control useInlineGhost; InlineGhost (the overlay) renders for real.
const { ghost } = vi.hoisted(() => ({ ghost: vi.fn() }));
vi.mock('../../hooks/useInlineGhost', () => ({ useInlineGhost: () => ghost() }));

const continueDraft = vi.fn();
const accept = vi.fn();
const edit = vi.fn();
const discard = vi.fn();
const regenerate = vi.fn();

const base = {
  anchor: null as null | { pos: number; coords: { top: number; left: number } },
  ghost: '', streaming: false, error: null as string | null, canContinue: true,
  continueDraft, accept, edit, discard, regenerate, reposition: vi.fn(),
};

function render0(props: Partial<Parameters<typeof InlineAiLayer>[0]> = {}) {
  return render(
    <InlineAiLayer
      editor={{} as never}
      projectId="p1" sceneId="scene-9" modelRef="m1" token="t"
      {...props}
    />,
  );
}

describe('InlineAiLayer (T3.3)', () => {
  beforeEach(() => {
    continueDraft.mockReset(); accept.mockReset(); edit.mockReset(); discard.mockReset(); regenerate.mockReset();
    localStorage.clear();
    ghost.mockReturnValue({ ...base });
  });

  it('C17 (WG-5): "Continue from cursor" is first-class — present in Classic mode (defaults Classic), not buried behind the AI toggle', () => {
    render0();
    expect(screen.getByTestId('inline-mode-classic').getAttribute('aria-pressed')).toBe('true');
    // The continue-from-cursor action is visible without switching to AI mode.
    expect(screen.getByTestId('inline-continue')).toBeInTheDocument();
  });

  it('clicking "Continue from cursor" streams a caret-anchored continuation', () => {
    render0();
    const cont = screen.getByTestId('inline-continue');
    fireEvent.click(cont);
    expect(continueDraft).toHaveBeenCalled();
  });


  // T2 — the reason a disabled control is disabled must be VISIBLE. It used to live only in
  // `title`, which a disabled button never surfaces: a 2026-09-06 human-sim run hand-pasted an
  // entire 5-arc novel having concluded the feature did not exist, when `modelRef` was simply null.
  describe('T2 — disabled reasons are visible and specific', () => {
    const reasonOf = () => screen.getByTestId('inline-continue-disabled-reason').getAttribute('data-reason');

    it('names the MISSING MODEL specifically (not a generic "cannot run")', () => {
      ghost.mockReturnValue({ ...base, canContinue: false });
      render0({ modelRef: null });
      expect(reasonOf()).toBe('need-model');
      expect(screen.getByTestId('inline-continue-disabled-reason').textContent).toMatch(/model/i);
    });

    it('names the MISSING SCENE specifically — a different problem with a different fix', () => {
      ghost.mockReturnValue({ ...base, canContinue: false });
      render0({ sceneId: null });
      expect(reasonOf()).toBe('need-scene');
    });

    it('distinguishes STREAMING from an unmet precondition', () => {
      ghost.mockReturnValue({ ...base, streaming: true });
      render0();
      expect(reasonOf()).toBe('streaming');
    });

    it('distinguishes an UNRESOLVED SUGGESTION from an unmet precondition', () => {
      ghost.mockReturnValue({ ...base, anchor: { pos: 1, coords: { top: 0, left: 0 } } });
      render0();
      expect(reasonOf()).toBe('pending-ghost');
    });

    // NV-7: a reason that is always on screen conveys nothing. It must be ABSENT when usable.
    it('shows NO reason when Continue is actually usable', () => {
      ghost.mockReturnValue({ ...base });
      render0();
      expect(screen.queryByTestId('inline-continue-disabled-reason')).toBeNull();
      expect(screen.getByTestId('inline-continue')).not.toBeDisabled();
    });

    // The model gate must NOT be silently self-healed (settings-and-config SET: no silent fallback).
    it('does not auto-pick a model — it reports the gap instead', () => {
      ghost.mockReturnValue({ ...base, canContinue: false });
      render0({ modelRef: null });
      expect(screen.getByTestId('inline-continue')).toBeDisabled();
      expect(continueDraft).not.toHaveBeenCalled();
    });
  });

  it('disables Continue when it cannot run (no scene/model)', () => {
    ghost.mockReturnValue({ ...base, canContinue: false });
    render0({ sceneId: null });
    expect(screen.getByTestId('inline-continue')).toBeDisabled();
  });

  it('disables Continue while a ghost is pending (resolve it first)', () => {
    ghost.mockReturnValue({ ...base, anchor: { pos: 3, coords: { top: 10, left: 10 } }, ghost: 'draft' });
    render0();
    expect(screen.getByTestId('inline-continue')).toBeDisabled();
  });

  it('renders the inline ghost + accept-bar when anchored, wired to the actions', () => {
    ghost.mockReturnValue({ ...base, anchor: { pos: 12, coords: { top: 100, left: 40 } }, ghost: 'the fog held its breath' });
    render0();
    expect(screen.getByTestId('inline-ghost-text').textContent).toContain('the fog held its breath');
    fireEvent.click(screen.getByTestId('inline-accept'));
    expect(accept).toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('inline-edit'));
    expect(edit).toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('inline-discard'));
    expect(discard).toHaveBeenCalled();
  });

  it('keeps the in-flight ghost visible after toggling between AI and Classic (anchor-based — never lose a stream)', () => {
    ghost.mockReturnValue({ ...base, anchor: { pos: 5, coords: { top: 50, left: 20 } }, ghost: 'streaming…', streaming: true });
    render0();
    fireEvent.click(screen.getByTestId('inline-mode-ai'));
    expect(screen.getByTestId('inline-ghost')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('inline-mode-classic')); // toggle back mid-stream
    expect(screen.getByTestId('inline-ghost')).toBeInTheDocument(); // NOT lost — anchor-based, mode-independent
  });

  it('persists the mode to localStorage', () => {
    render0();
    fireEvent.click(screen.getByTestId('inline-mode-ai'));
    expect(localStorage.getItem('loreweave.editor.aiMode')).toBe('ai');
  });
});
