import { describe, it, expect, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useAiTask } from '../useAiTask';

describe('useAiTask (propose→review→confirm controller)', () => {
  it('run stores the result and clears busy', async () => {
    const run = vi.fn().mockResolvedValue({ ok: 1 });
    const { result } = renderHook(() => useAiTask<{ q: string }, { ok: number }>({ run }));

    let returned: unknown;
    await act(async () => { returned = await result.current.run({ q: 'x' }); });
    expect(returned).toEqual({ ok: 1 });
    expect(result.current.result).toEqual({ ok: 1 });
    expect(result.current.busy).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('run reads the backend error and does NOT throw', async () => {
    const err = Object.assign(new Error('x'), { body: { detail: { message: 'empty response' } } });
    const run = vi.fn().mockRejectedValue(err);
    const onError = vi.fn();
    const { result } = renderHook(() => useAiTask({ run, onError }));

    let returned: unknown = 'unset';
    await act(async () => { returned = await result.current.run({}); });
    expect(returned).toBeNull();
    expect(result.current.error).toBe('empty response');
    expect(onError).toHaveBeenCalledWith('empty response');
  });

  it('confirm commits the current result; reset clears it', async () => {
    const run = vi.fn().mockResolvedValue('R');
    const confirm = vi.fn().mockResolvedValue(undefined);
    const { result } = renderHook(() => useAiTask<unknown, string>({ run, confirm }));

    await act(async () => { await result.current.run({}); });
    await act(async () => { await result.current.confirm(); });
    expect(confirm).toHaveBeenCalledWith('R');

    act(() => result.current.reset());
    expect(result.current.result).toBeNull();
  });

  it('confirm re-throws on failure so the dialog stays open', async () => {
    const run = vi.fn().mockResolvedValue('R');
    const confirm = vi.fn().mockRejectedValue(Object.assign(new Error('nope'), { body: { message: 'quota' } }));
    const { result } = renderHook(() => useAiTask<unknown, string>({ run, confirm }));

    await act(async () => { await result.current.run({}); });
    await act(async () => {
      await expect(result.current.confirm()).rejects.toThrow();
    });
    await waitFor(() => expect(result.current.error).toBe('quota'));
  });
});
