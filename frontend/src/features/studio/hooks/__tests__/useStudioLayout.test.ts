import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useStudioLayout } from '../useStudioLayout';

const LAYOUT_KEY = 'lw_studio_layout_b1';

/** A minimal fake DockviewApi with the surface the hook touches. */
function makeApi(over: Record<string, unknown> = {}) {
  return {
    onDidLayoutChange: vi.fn(() => ({ dispose: vi.fn() })),
    fromJSON: vi.fn(),
    addPanel: vi.fn(),
    toJSON: vi.fn(() => ({ grid: {}, panels: { welcome: {} } })),
    ...over,
  };
}

const fireReady = (api: ReturnType<typeof makeApi>) => {
  const { result } = renderHook(() => useStudioLayout('b1'));
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  result.current.onReady({ api } as any);
  return result;
};

describe('useStudioLayout', () => {
  beforeEach(() => localStorage.clear());

  it('seeds the Welcome panel when there is no saved layout', () => {
    const api = makeApi();
    fireReady(api);
    expect(api.fromJSON).not.toHaveBeenCalled();
    expect(api.addPanel).toHaveBeenCalledWith(expect.objectContaining({ id: 'welcome', component: 'welcome' }));
  });

  it('restores a saved layout (does not re-seed Welcome)', () => {
    localStorage.setItem(LAYOUT_KEY, JSON.stringify({ grid: {}, panels: {} }));
    const api = makeApi();
    fireReady(api);
    expect(api.fromJSON).toHaveBeenCalledTimes(1);
    expect(api.addPanel).not.toHaveBeenCalled();
  });

  it('degrades to the Welcome default when the saved layout is corrupt JSON', () => {
    localStorage.setItem(LAYOUT_KEY, '{not json');
    const api = makeApi();
    fireReady(api);
    expect(api.addPanel).toHaveBeenCalledWith(expect.objectContaining({ component: 'welcome' }));
  });

  it('degrades to Welcome when fromJSON throws on a stale layout', () => {
    localStorage.setItem(LAYOUT_KEY, JSON.stringify({ grid: {}, panels: { gone: {} } }));
    const api = makeApi({ fromJSON: vi.fn(() => { throw new Error('unknown component'); }) });
    fireReady(api);
    expect(api.fromJSON).toHaveBeenCalled();
    expect(api.addPanel).toHaveBeenCalledWith(expect.objectContaining({ component: 'welcome' }));
  });

  it('persists the serialized layout on a user change', () => {
    let layoutCb: (() => void) | undefined;
    const api = makeApi({
      onDidLayoutChange: vi.fn((cb: () => void) => { layoutCb = cb; return { dispose: vi.fn() }; }),
    });
    fireReady(api);
    // Listener is registered AFTER restore/seed (so the idempotent seed doesn't auto-write);
    // invoking the captured callback proves a real change writes the serialized layout.
    expect(layoutCb).toBeTypeOf('function');
    layoutCb!();
    expect(localStorage.getItem(LAYOUT_KEY)).toBe(JSON.stringify(api.toJSON()));
  });
});
