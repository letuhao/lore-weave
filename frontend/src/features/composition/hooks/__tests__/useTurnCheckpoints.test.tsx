import { renderHook, act, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const listRevisions = vi.fn();
const restoreRevision = vi.fn();
vi.mock('@/features/books/api', () => ({
  booksApi: {
    listRevisions: (...a: unknown[]) => listRevisions(...a),
    restoreRevision: (...a: unknown[]) => restoreRevision(...a),
  },
}));

import { useTurnCheckpoints } from '../useTurnCheckpoints';

const BOOK = 'b1';
const CH = 'c1';

describe('useTurnCheckpoints (RAID C6)', () => {
  beforeEach(() => {
    listRevisions.mockReset();
    restoreRevision.mockReset();
  });

  it('captures the pre-edit revision as the restore point', async () => {
    listRevisions.mockResolvedValue({ items: [{ revision_id: 'rev-A', created_at: 'x' }] });
    const { result } = renderHook(() => useTurnCheckpoints(BOOK));
    await act(async () => { await result.current.capture(CH, 'Once upon a time', 'insert'); });
    expect(result.current.checkpoints).toHaveLength(1);
    expect(result.current.checkpoints[0]).toMatchObject({ chapterId: CH, preRevisionId: 'rev-A', kind: 'insert', count: 1 });
  });

  it('folds consecutive edits that share the same pre-revision (autosave batching)', async () => {
    listRevisions.mockResolvedValue({ items: [{ revision_id: 'rev-A', created_at: 'x' }] });
    const { result } = renderHook(() => useTurnCheckpoints(BOOK));
    await act(async () => {
      await result.current.capture(CH, 'first', 'insert');
      await result.current.capture(CH, 'second', 'insert');
    });
    expect(result.current.checkpoints).toHaveLength(1);
    expect(result.current.checkpoints[0].count).toBe(2);
    // LOW-4: fold KEEPS the first edit's snippet (Restore reverts to before it),
    // it does not overwrite with the newest edit's text.
    expect(result.current.checkpoints[0].snippet).toBe('first');
  });

  it('pins a synchronously-provided pre-revision without an API read (MED-2)', async () => {
    const { result } = renderHook(() => useTurnCheckpoints(BOOK));
    await act(async () => { await result.current.capture(CH, 'sync', 'insert', 'rev-SYNC'); });
    expect(result.current.checkpoints[0]).toMatchObject({ preRevisionId: 'rev-SYNC', kind: 'insert', count: 1 });
    expect(listRevisions).not.toHaveBeenCalled(); // no round-trip → no TOCTOU race
  });

  it('pins an explicitly-null provided pre-revision (Restore disabled, no API read)', async () => {
    const { result } = renderHook(() => useTurnCheckpoints(BOOK));
    await act(async () => { await result.current.capture(CH, 'sync', 'polish', null); });
    expect(result.current.checkpoints[0].preRevisionId).toBeNull();
    expect(listRevisions).not.toHaveBeenCalled();
  });

  it('falls back to the async listRevisions read when no pre-revision is provided', async () => {
    listRevisions.mockResolvedValue({ items: [{ revision_id: 'rev-ASYNC' }] });
    const { result } = renderHook(() => useTurnCheckpoints(BOOK));
    await act(async () => { await result.current.capture(CH, 'async', 'insert'); });
    expect(listRevisions).toHaveBeenCalledTimes(1);
    expect(result.current.checkpoints[0].preRevisionId).toBe('rev-ASYNC');
  });

  it('starts a new checkpoint when the pre-revision advanced (a save happened)', async () => {
    listRevisions
      .mockResolvedValueOnce({ items: [{ revision_id: 'rev-A' }] })
      .mockResolvedValueOnce({ items: [{ revision_id: 'rev-B' }] });
    const { result } = renderHook(() => useTurnCheckpoints(BOOK));
    await act(async () => { await result.current.capture(CH, 'a', 'insert'); });
    await act(async () => { await result.current.capture(CH, 'b', 'insert'); });
    expect(result.current.checkpoints).toHaveLength(2);
    expect(result.current.checkpoints[0].preRevisionId).toBe('rev-B'); // newest first
  });

  it('null pre-revision when the chapter has no revisions yet (Restore disabled)', async () => {
    listRevisions.mockResolvedValue({ items: [] });
    const { result } = renderHook(() => useTurnCheckpoints(BOOK));
    await act(async () => { await result.current.capture(CH, 'x', 'polish'); });
    expect(result.current.checkpoints[0].preRevisionId).toBeNull();
  });

  it('restore calls the API and drops the checkpoint + any newer ones for the chapter', async () => {
    listRevisions
      .mockResolvedValueOnce({ items: [{ revision_id: 'rev-A' }] })
      .mockResolvedValueOnce({ items: [{ revision_id: 'rev-B' }] });
    restoreRevision.mockResolvedValue({});
    const { result } = renderHook(() => useTurnCheckpoints(BOOK));
    await act(async () => { await result.current.capture(CH, 'older', 'insert'); });
    await act(async () => { await result.current.capture(CH, 'newer', 'insert'); });
    const older = result.current.checkpoints[1]; // rev-A, captured first
    await act(async () => { await result.current.restore(older); });
    expect(restoreRevision).toHaveBeenCalledWith('tok', BOOK, CH, 'rev-A');
    await waitFor(() => expect(result.current.checkpoints).toHaveLength(0)); // older + the newer one dropped
  });
});
