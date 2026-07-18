// 22-C2b — the bulk controller: selection toggles, and apply/trash fan OCC writes across DISTINCT
// nodes with an HONEST partial-failure tally (a 412 is a conflict, other errors are failures),
// then clears the selection and reloads.
import { renderHook, act, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const patchNode = vi.fn();
const archiveNode = vi.fn();
vi.mock('@/features/composition/api', () => ({
  compositionApi: {
    patchNode: (...a: unknown[]) => patchNode(...a),
    archiveNode: (...a: unknown[]) => archiveNode(...a),
  },
}));

import { useSceneBulk } from '../useSceneBulk';

beforeEach(() => { patchNode.mockReset(); archiveNode.mockReset(); });

describe('useSceneBulk (22-C2b)', () => {
  it('toggle adds/removes an id; setMany selects/deselects in bulk; clear empties', () => {
    const { result } = renderHook(() => useSceneBulk('tok', vi.fn()));
    act(() => result.current.toggle('a'));
    act(() => result.current.toggle('b'));
    expect([...result.current.selected].sort()).toEqual(['a', 'b']);
    act(() => result.current.toggle('a')); // toggle off
    expect([...result.current.selected]).toEqual(['b']);
    act(() => result.current.setMany(['c', 'd'], true));
    expect([...result.current.selected].sort()).toEqual(['b', 'c', 'd']);
    act(() => result.current.setMany(['b', 'c'], false));
    expect([...result.current.selected]).toEqual(['d']);
    act(() => result.current.clear());
    expect(result.current.selected.size).toBe(0);
  });

  it('apply patches each target with its OWN OCC version and reports all-ok, then reloads + clears', async () => {
    patchNode.mockResolvedValue({});
    const reload = vi.fn();
    const { result } = renderHook(() => useSceneBulk('tok', reload));
    act(() => result.current.setMany(['n1', 'n2'], true));
    await act(async () => {
      await result.current.apply([{ id: 'n1', version: 3 }, { id: 'n2', version: 7 }], { status: 'done' });
    });
    expect(patchNode).toHaveBeenCalledWith('n1', { status: 'done' }, 'tok', 3);
    expect(patchNode).toHaveBeenCalledWith('n2', { status: 'done' }, 'tok', 7); // each node's OWN version
    expect(result.current.result).toEqual({ ok: 2, conflicts: 0, failed: 0 });
    expect(result.current.selected.size).toBe(0); // cleared after apply
    expect(reload).toHaveBeenCalled();
  });

  it('a 412 counts as a conflict and a non-412 error as a failure — honest partial tally', async () => {
    patchNode.mockImplementation(async (id: string) => {
      if (id === 'conflict') throw Object.assign(new Error('stale'), { status: 412 });
      if (id === 'boom') throw Object.assign(new Error('server'), { status: 500 });
      return {};
    });
    const { result } = renderHook(() => useSceneBulk('tok', vi.fn()));
    await act(async () => {
      await result.current.apply(
        [{ id: 'ok', version: 1 }, { id: 'conflict', version: 1 }, { id: 'boom', version: 1 }],
        { status: 'drafting' },
      );
    });
    expect(result.current.result).toEqual({ ok: 1, conflicts: 1, failed: 1 });
  });

  it('trash archives each target (no version needed) and tallies the outcome', async () => {
    archiveNode.mockResolvedValue(undefined);
    const reload = vi.fn();
    const { result } = renderHook(() => useSceneBulk('tok', reload));
    await act(async () => { await result.current.trash([{ id: 'n1', version: 1 }, { id: 'n2', version: 1 }]); });
    expect(archiveNode).toHaveBeenCalledWith('n1', 'tok');
    expect(archiveNode).toHaveBeenCalledWith('n2', 'tok');
    expect(result.current.result).toEqual({ ok: 2, conflicts: 0, failed: 0 });
    expect(reload).toHaveBeenCalled();
  });

  it('apply with no targets is a no-op (no request, no reload)', async () => {
    const reload = vi.fn();
    const { result } = renderHook(() => useSceneBulk('tok', reload));
    await act(async () => { await result.current.apply([], { status: 'done' }); });
    expect(patchNode).not.toHaveBeenCalled();
    expect(reload).not.toHaveBeenCalled();
  });
});
