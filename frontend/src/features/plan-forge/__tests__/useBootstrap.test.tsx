import { describe, expect, it, vi, beforeEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';

const bootstrapPropose = vi.fn();
const bootstrapApprove = vi.fn();
const bootstrapReject = vi.fn();
const bootstrapApply = vi.fn();
vi.mock('../api', () => ({
  planForgeApi: {
    bootstrapPropose: (...a: unknown[]) => bootstrapPropose(...a),
    bootstrapApprove: (...a: unknown[]) => bootstrapApprove(...a),
    bootstrapReject: (...a: unknown[]) => bootstrapReject(...a),
    bootstrapApply: (...a: unknown[]) => bootstrapApply(...a),
  },
}));

import { useBootstrap } from '../hooks/useBootstrap';

const proposal = (over: Record<string, unknown> = {}) => ({
  id: 'p1', run_id: 'r1', book_id: 'b1', owner_user_id: 'u1', status: 'pending',
  diff: { new_chapters: [], new_glossary_entities: [] }, applied_results: {},
  error_detail: null, created_at: '', updated_at: '', ...over,
});

beforeEach(() => {
  bootstrapPropose.mockReset(); bootstrapApprove.mockReset();
  bootstrapReject.mockReset(); bootstrapApply.mockReset();
});

describe('useBootstrap', () => {
  it('propose() calls the API with the given run id and stores the result', async () => {
    bootstrapPropose.mockResolvedValue(proposal());
    const { result } = renderHook(() => useBootstrap('b1', 'tok'));
    await act(async () => { await result.current.propose('r1'); });
    expect(bootstrapPropose).toHaveBeenCalledWith('b1', 'r1', 'tok');
    expect(result.current.proposal?.id).toBe('p1');
    expect(result.current.busy).toBe(false);
  });

  it('approve/reject/apply act on the CURRENT proposal id, never re-propose', async () => {
    bootstrapPropose.mockResolvedValue(proposal({ status: 'pending' }));
    bootstrapApprove.mockResolvedValue(proposal({ status: 'approved' }));
    bootstrapApply.mockResolvedValue(proposal({ status: 'applied' }));

    const { result } = renderHook(() => useBootstrap('b1', 'tok'));
    await act(async () => { await result.current.propose('r1'); });
    await act(async () => { await result.current.approve(); });
    expect(bootstrapApprove).toHaveBeenCalledWith('b1', 'p1', 'tok');
    expect(result.current.proposal?.status).toBe('approved');

    await act(async () => { await result.current.apply(); });
    expect(bootstrapApply).toHaveBeenCalledWith('b1', 'p1', 'tok');
    expect(result.current.proposal?.status).toBe('applied');
    expect(bootstrapPropose).toHaveBeenCalledTimes(1); // never re-proposed
  });

  it('approve/reject/apply are no-ops without a proposal yet', async () => {
    const { result } = renderHook(() => useBootstrap('b1', 'tok'));
    await act(async () => { await result.current.approve(); });
    await act(async () => { await result.current.reject(); });
    await act(async () => { await result.current.apply(); });
    expect(bootstrapApprove).not.toHaveBeenCalled();
    expect(bootstrapReject).not.toHaveBeenCalled();
    expect(bootstrapApply).not.toHaveBeenCalled();
  });

  it('surfaces the raw body.detail on a FastAPI-shaped error (the shared apiJson type only reads .message)', async () => {
    bootstrapPropose.mockRejectedValue(
      Object.assign(new Error('Unprocessable Entity'), { body: { detail: 'This book has no Glossary ontology yet.' } }),
    );
    const { result } = renderHook(() => useBootstrap('b1', 'tok'));
    await act(async () => { await result.current.propose('r1'); });
    expect(result.current.error).toBe('This book has no Glossary ontology yet.');
  });

  it('falls back to the Error message when no body.detail is present', async () => {
    bootstrapPropose.mockRejectedValue(new Error('network down'));
    const { result } = renderHook(() => useBootstrap('b1', 'tok'));
    await act(async () => { await result.current.propose('r1'); });
    expect(result.current.error).toBe('network down');
  });

  it('reset() clears the proposal and error back to idle', async () => {
    bootstrapPropose.mockResolvedValue(proposal());
    const { result } = renderHook(() => useBootstrap('b1', 'tok'));
    await act(async () => { await result.current.propose('r1'); });
    act(() => { result.current.reset(); });
    expect(result.current.proposal).toBeNull();
    expect(result.current.error).toBeNull();
  });
});
