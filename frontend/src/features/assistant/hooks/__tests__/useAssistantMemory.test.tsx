// A2 — the shared memory/journal controller's handler orchestration: each destructive action refetches
// exactly the surfaces it changed ON SUCCESS, and does NOT refetch on a no-op/failure. Erase additionally
// re-provisions (the diary book is gone). This is the wiring both the dock and the desktop strip rely on.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

const journalRefresh = vi.fn();
const memoryRefresh = vi.fn();
const railRefresh = vi.fn();
const reprovision = vi.fn();
const correct = vi.fn();
const forget = vi.fn();
const erase = vi.fn();

vi.mock('../../context/AssistantContext', () => ({
  useAssistant: () => ({ bookId: 'book-1', reprovision, captureRail: { refresh: railRefresh } }),
}));
vi.mock('../useDiaryEntries', () => ({ useDiaryEntries: () => ({ entries: [], loading: false, error: null, refresh: journalRefresh }) }));
vi.mock('../useMemoryEntities', () => ({ useMemoryEntities: () => ({ entities: [], loading: false, error: null, search: '', setSearch: vi.fn(), refresh: memoryRefresh }) }));
vi.mock('../useDiaryCorrection', () => ({ useDiaryCorrection: () => ({ correct, correctingId: null }) }));
vi.mock('../useForgetEntity', () => ({ useForgetEntity: () => ({ forget, forgettingName: null }) }));
vi.mock('../useEraseAllData', () => ({ useEraseAllData: () => ({ erase, erasing: false }) }));

import { useAssistantMemory } from '../useAssistantMemory';

beforeEach(() => {
  [journalRefresh, memoryRefresh, railRefresh, reprovision, correct, forget, erase].forEach((m) => m.mockReset());
});

describe('useAssistantMemory (A2 shared controller)', () => {
  it('handleForget refetches memory + rail ONLY on a successful forget', async () => {
    const { result } = renderHook(() => useAssistantMemory());

    forget.mockResolvedValueOnce({ forgotten: true });
    await act(async () => { await result.current.handleForget('Minh'); });
    expect(memoryRefresh).toHaveBeenCalledTimes(1);
    expect(railRefresh).toHaveBeenCalledTimes(1);

    forget.mockResolvedValueOnce({ forgotten: false }); // no-op → no refetch
    await act(async () => { await result.current.handleForget('Ghost'); });
    expect(memoryRefresh).toHaveBeenCalledTimes(1); // unchanged
  });

  it('handleEraseAll re-provisions + refetches everything on success, nothing on failure', async () => {
    const { result } = renderHook(() => useAssistantMemory());

    erase.mockResolvedValueOnce(true);
    await act(async () => { await result.current.handleEraseAll(); });
    expect(reprovision).toHaveBeenCalledTimes(1); // the diary book is gone → rebind
    expect(memoryRefresh).toHaveBeenCalledTimes(1);
    expect(journalRefresh).toHaveBeenCalledTimes(1);
    expect(railRefresh).toHaveBeenCalledTimes(1);

    erase.mockResolvedValueOnce(false);
    await act(async () => { await result.current.handleEraseAll(); });
    expect(reprovision).toHaveBeenCalledTimes(1); // unchanged — no wipe, no rebind
  });

  it('handleCorrect refetches journal + memory + rail only when the amend lands', async () => {
    const { result } = renderHook(() => useAssistantMemory());

    correct.mockResolvedValueOnce({ amended: true });
    await act(async () => { await result.current.handleCorrect('c1', 'fixed body'); });
    expect(journalRefresh).toHaveBeenCalledTimes(1);
    expect(memoryRefresh).toHaveBeenCalledTimes(1);

    correct.mockResolvedValueOnce({ amended: false });
    await act(async () => { await result.current.handleCorrect('c1', 'noop'); });
    expect(journalRefresh).toHaveBeenCalledTimes(1); // unchanged
  });
});
