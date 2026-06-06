import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

const resolveWorkMock = vi.fn();
const publishGateMock = vi.fn();
vi.mock('../../api', () => ({
  compositionApi: {
    resolveWork: (...a: unknown[]) => resolveWorkMock(...a),
    publishGate: (...a: unknown[]) => publishGateMock(...a),
  },
}));

import { useChapterPublishGate } from '../usePublishGate';
import type { Work } from '../../types';

const WORK: Work = {
  project_id: 'p1', user_id: 'u1', book_id: 'b1',
  active_template_id: null, status: 'active', settings: {}, version: 1,
};

function Wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const render = () =>
  renderHook(() => useChapterPublishGate('b1', 'c1', 'tok'), { wrapper: Wrapper });

beforeEach(() => {
  resolveWorkMock.mockReset();
  publishGateMock.mockReset();
});

describe('useChapterPublishGate', () => {
  it('no composition Work → ungated (blocked:false), gate endpoint never called', async () => {
    // a book with a knowledge project but no marked composition_work
    resolveWorkMock.mockResolvedValue({ status: 'unmarked_single', work: null, candidates: [], book_project_id: 'p1', book_project_ids: [] });
    const { result } = render();
    await waitFor(() => expect(resolveWorkMock).toHaveBeenCalled());
    expect(result.current.blocked).toBe(false);
    expect(publishGateMock).not.toHaveBeenCalled();
  });

  it("Work + not-all-scenes-done → blocked:true with counts", async () => {
    resolveWorkMock.mockResolvedValue({ status: 'found', work: WORK, candidates: [], book_project_id: null, book_project_ids: [] });
    publishGateMock.mockResolvedValue({ chapter_id: 'c1', scenes_total: 3, scenes_done: 1, can_publish: false });
    const { result } = render();
    await waitFor(() => expect(result.current.blocked).toBe(true));
    expect(result.current.scenesTotal).toBe(3);
    expect(result.current.scenesDone).toBe(1);
    expect(publishGateMock).toHaveBeenCalledWith('p1', 'c1', 'tok');
  });

  it('Work + all-scenes-done → ungated (blocked:false)', async () => {
    resolveWorkMock.mockResolvedValue({ status: 'found', work: WORK, candidates: [], book_project_id: null, book_project_ids: [] });
    publishGateMock.mockResolvedValue({ chapter_id: 'c1', scenes_total: 2, scenes_done: 2, can_publish: true });
    const { result } = render();
    await waitFor(() => expect(publishGateMock).toHaveBeenCalled());
    await waitFor(() => expect(result.current.blocked).toBe(false));
    expect(result.current.scenesTotal).toBe(2);
  });

  it('candidates (multi-marked) → uses the first work for the gate', async () => {
    resolveWorkMock.mockResolvedValue({ status: 'candidates', work: null, candidates: [WORK], book_project_id: null, book_project_ids: [] });
    publishGateMock.mockResolvedValue({ chapter_id: 'c1', scenes_total: 1, scenes_done: 0, can_publish: false });
    const { result } = render();
    await waitFor(() => expect(result.current.blocked).toBe(true));
    expect(publishGateMock).toHaveBeenCalledWith('p1', 'c1', 'tok');
  });
});
