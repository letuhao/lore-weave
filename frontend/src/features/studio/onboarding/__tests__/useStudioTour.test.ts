import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useStudioTour } from '../useStudioTour';

// The real `core` tour's first step targets [data-testid="studio-activity-manuscript"] with no
// panelId (chrome-only); its 3rd step (index 2) opens 'compose' and targets
// [data-testid="studio-compose-panel"]. Tests drive real DOM nodes rather than mocking
// querySelector, matching the hook's actual anchor-detection mechanism.

function addAnchor(testid: string) {
  const el = document.createElement('div');
  el.setAttribute('data-testid', testid);
  document.body.appendChild(el);
  return el;
}

describe('useStudioTour', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    document.body.innerHTML = '';
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('becomes active once the first step\'s anchor is present (chrome-only step, no panel open)', async () => {
    addAnchor('studio-activity-manuscript');
    const onOpenPanel = vi.fn();
    const { result } = renderHook(() => useStudioTour(onOpenPanel));

    act(() => { result.current.start('core'); });
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(result.current.active).toBe(true);
    expect(result.current.stepIndex).toBe(0);
    expect(onOpenPanel).not.toHaveBeenCalled(); // step 0 has no panelId
  });

  it('opens the step\'s panel before waiting for its anchor', async () => {
    addAnchor('studio-activity-manuscript');
    addAnchor('studio-command-palette');
    // The compose panel's anchor doesn't exist yet — onOpenPanel must fire regardless.
    const onOpenPanel = vi.fn();
    const { result } = renderHook(() => useStudioTour(onOpenPanel));

    act(() => { result.current.start('core'); });
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    act(() => { result.current.next(); }); // → step 1 (palette, chrome-only)
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    act(() => { result.current.next(); }); // → step 2 (compose panel)
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(onOpenPanel).toHaveBeenCalledWith('compose');
  });

  it('idempotent re-open: every step re-calls onOpenPanel, self-healing a manually-closed panel', async () => {
    addAnchor('studio-activity-manuscript');
    addAnchor('studio-command-palette');
    addAnchor('studio-compose-panel');
    addAnchor('studio-editor-panel');
    const onOpenPanel = vi.fn();
    const { result } = renderHook(() => useStudioTour(onOpenPanel));

    act(() => { result.current.start('core'); });
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    act(() => { result.current.next(); });
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    act(() => { result.current.next(); }); // compose
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    act(() => { result.current.next(); }); // editor
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(onOpenPanel.mock.calls.filter((c) => c[0] === 'compose').length).toBe(1);
    expect(onOpenPanel.mock.calls.filter((c) => c[0] === 'editor').length).toBe(1);
  });

  it('skips a step whose anchor never appears, after the timeout — never hangs', async () => {
    addAnchor('studio-activity-manuscript');
    // Deliberately do NOT add 'studio-command-palette' (step 1's anchor) — simulates a
    // stale/typo'd selector. 'studio-compose-panel' (step 2) DOES exist.
    addAnchor('studio-compose-panel');
    const onOpenPanel = vi.fn();
    const { result } = renderHook(() => useStudioTour(onOpenPanel));

    act(() => { result.current.start('core'); });
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(result.current.stepIndex).toBe(0);

    act(() => { result.current.next(); }); // → step 1, whose anchor never appears
    // Advance past the 4s anchor-wait timeout — the hook must auto-skip to step 2, not hang.
    await act(async () => { await vi.advanceTimersByTimeAsync(4500); });

    expect(result.current.active).toBe(true);
    expect(result.current.stepIndex).toBe(2); // skipped step 1, landed on compose
    expect(onOpenPanel).toHaveBeenCalledWith('compose');
  });

  it('stop() invalidates an in-flight wait — a superseded step never marks ready', async () => {
    // No anchors at all — every step would wait the full timeout.
    const onOpenPanel = vi.fn();
    const { result } = renderHook(() => useStudioTour(onOpenPanel));

    act(() => { result.current.start('core'); });
    act(() => { result.current.stop(); });
    await act(async () => { await vi.advanceTimersByTimeAsync(4500); });

    expect(result.current.active).toBe(false);
  });

  it('next() on the last step stops the tour instead of overrunning', async () => {
    for (const id of ['studio-activity-manuscript', 'studio-command-palette', 'studio-compose-panel', 'studio-editor-panel']) {
      addAnchor(id);
    }
    const { result } = renderHook(() => useStudioTour(vi.fn()));
    act(() => { result.current.start('core'); });
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    for (let i = 0; i < 3; i++) {
      act(() => { result.current.next(); });
      await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    }
    expect(result.current.stepIndex).toBe(3); // last (editor)
    act(() => { result.current.next(); }); // past the end
    expect(result.current.active).toBe(false);
  });
});
