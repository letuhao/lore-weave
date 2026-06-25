import { render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PopoutBridge } from '../PopoutBridge';
import { openPopoutChannel } from '../../../workspace/popoutChannel';

function fakeWindow() {
  return { closed: false, close: vi.fn() } as unknown as Window & { closed: boolean; close: ReturnType<typeof vi.fn> };
}

describe('PopoutBridge (T5.4 M4)', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

  it('opens the popout route ONCE with book/chapter/scene/panel params', () => {
    const win = fakeWindow();
    const open = vi.spyOn(window, 'open').mockReturnValue(win);
    render(<PopoutBridge id="cast" bookId="b1" chapterId="c1" sceneId="s1" onClosed={vi.fn()} />);
    expect(open).toHaveBeenCalledTimes(1);
    const url = String(open.mock.calls[0][0]);
    expect(url).toContain('/composition/popout?');
    expect(url).toContain('book=b1');
    expect(url).toContain('chapter=c1');
    expect(url).toContain('scene=s1');
    expect(url).toContain('panel=cast');
  });

  it('re-docks (onClosed) when the popout window is closed', () => {
    const win = fakeWindow();
    vi.spyOn(window, 'open').mockReturnValue(win);
    const onClosed = vi.fn();
    render(<PopoutBridge id="cast" bookId="b1" chapterId="c1" onClosed={onClosed} />);
    expect(onClosed).not.toHaveBeenCalled();
    win.closed = true;            // user closed the OS window
    vi.advanceTimersByTime(600);  // next poll tick
    expect(onClosed).toHaveBeenCalledTimes(1);
  });

  it('reverts to dock immediately if the popup is BLOCKED (window.open → null)', () => {
    vi.spyOn(window, 'open').mockReturnValue(null);
    const onClosed = vi.fn();
    render(<PopoutBridge id="cast" bookId="b1" chapterId="c1" onClosed={onClosed} />);
    expect(onClosed).toHaveBeenCalledTimes(1);
  });

  it('closes the popout when the opener unmounts (no orphan window in Slice A)', () => {
    const win = fakeWindow();
    vi.spyOn(window, 'open').mockReturnValue(win);
    const { unmount } = render(<PopoutBridge id="cast" bookId="b1" chapterId="c1" onClosed={vi.fn()} />);
    unmount();
    expect(win.close).toHaveBeenCalledTimes(1);
  });

  it('omits the scene param when no scene is set', () => {
    const win = fakeWindow();
    const open = vi.spyOn(window, 'open').mockReturnValue(win);
    render(<PopoutBridge id="grounding" bookId="b1" chapterId="c1" onClosed={vi.fn()} />);
    expect(String(open.mock.calls[0][0])).not.toContain('scene=');
  });

  it('re-docks INSTANTLY on a dock-back channel message (no 500ms poll wait) (/review-impl MED)', async () => {
    vi.useRealTimers();   // BroadcastChannel delivers on a real microtask, not fake timers
    const win = fakeWindow();
    vi.spyOn(window, 'open').mockReturnValue(win);
    const onClosed = vi.fn();
    // FILE+TEST-UNIQUE channel id — BroadcastChannel is shared across vitest worker
    // threads (and a posted message can deliver late into a sibling test on the same
    // channel name), so a generic 'b1' cross-talks. Posting tests get distinct ids.
    render(<PopoutBridge id="cast" bookId="PBRIDGE_dock" chapterId="c1" onClosed={onClosed} />);
    // a popout posts dock-back for THIS panel (the popout's "Dock" button)
    const popout = openPopoutChannel('PBRIDGE_dock', 'c1');
    popout.post({ kind: 'dock-back', panel: 'cast' });
    await new Promise((r) => setTimeout(r, 0));
    expect(onClosed).toHaveBeenCalledTimes(1);   // re-docked without waiting for the poll
    popout.close();
  });

  it('ignores a dock-back for a DIFFERENT panel', async () => {
    vi.useRealTimers();
    const win = fakeWindow();
    vi.spyOn(window, 'open').mockReturnValue(win);
    const onClosed = vi.fn();
    render(<PopoutBridge id="cast" bookId="PBRIDGE_other" chapterId="c1" onClosed={onClosed} />);
    const popout = openPopoutChannel('PBRIDGE_other', 'c1');
    popout.post({ kind: 'dock-back', panel: 'grounding' });   // not this bridge's panel
    await new Promise((r) => setTimeout(r, 0));
    expect(onClosed).not.toHaveBeenCalled();
    popout.close();
  });
});
