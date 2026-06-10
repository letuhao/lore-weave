import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { usePlanner } from '../usePlanner';

const { mockApi } = vi.hoisted(() => ({
  mockApi: {
    listTemplates: vi.fn(),
    decomposePreview: vi.fn(),
    commitDecompose: vi.fn(),
  },
}));
vi.mock('../../api', () => ({ compositionApi: mockApi }));

const PREVIEW = {
  arc_title: 'Arc One',
  chapters: [
    {
      chapter: { chapter_id: 'ch1', title: 'Ch 1', sort_order: 1, beat_role: 'setup', intent: 'open' },
      scenes: [
        { title: 'S1', synopsis: 'syn', tension: 40, present_entity_ids: ['e1'], present_entity_names_unresolved: ['Ghost'], suggested_k: 3 },
      ],
      warning: null,
    },
  ],
  unmapped_beats: [],
};

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  mockApi.listTemplates = vi.fn().mockResolvedValue([{ id: 't1', name: 'Three-Act' }]);
  mockApi.decomposePreview = vi.fn().mockResolvedValue(PREVIEW);
  mockApi.commitDecompose = vi.fn().mockResolvedValue({});
});

describe('usePlanner', () => {
  it('preview → editable draft; an edit is carried into the commit payload (not the default)', async () => {
    const { result } = renderHook(() => usePlanner('p1', 'tok'), { wrapper });
    act(() => { result.current.setTemplateId('t1'); result.current.setPremise('a premise'); });
    act(() => { result.current.runPreview({ modelRef: 'm1' }); });
    await waitFor(() => expect(result.current.draft).not.toBeNull());
    expect(result.current.draft![0].scenes[0].title).toBe('S1');
    expect(result.current.totalScenes).toBe(1);

    // non-default regression-lock: change tension + synopsis, then commit.
    act(() => { result.current.editScene(0, 0, { tension: 90, synopsis: 'EDITED' }); });
    expect(result.current.draft![0].scenes[0].tension).toBe(90);
    act(() => { result.current.commit(); });
    await waitFor(() => expect(mockApi.commitDecompose).toHaveBeenCalled());

    const payload = mockApi.commitDecompose.mock.calls[0][1];
    expect(payload.replace).toBe(false);
    expect(payload.idempotency_key).toBeTruthy();
    expect(payload.chapters[0].scenes[0].tension).toBe(90);
    expect(payload.chapters[0].scenes[0].synopsis).toBe('EDITED');
    // present_entity_ids flow through; the display-only unresolved names do NOT.
    expect(payload.chapters[0].scenes[0].present_entity_ids).toEqual(['e1']);
    expect(payload.chapters[0].scenes[0]).not.toHaveProperty('present_entity_names_unresolved');
  });

  it('add/remove scene mutates the draft', async () => {
    const { result } = renderHook(() => usePlanner('p1', 'tok'), { wrapper });
    act(() => { result.current.setTemplateId('t1'); result.current.setPremise('p'); });
    act(() => { result.current.runPreview({ modelRef: 'm1' }); });
    await waitFor(() => expect(result.current.draft).not.toBeNull());
    act(() => { result.current.addScene(0); });
    expect(result.current.totalScenes).toBe(2);
    act(() => { result.current.removeScene(0, 0); });
    expect(result.current.totalScenes).toBe(1);
  });

  it('409 CHAPTER_ALREADY_PLANNED → needsReplace; confirmReplace resends with replace=true', async () => {
    const { result } = renderHook(() => usePlanner('p1', 'tok'), { wrapper });
    act(() => { result.current.setTemplateId('t1'); result.current.setPremise('p'); });
    act(() => { result.current.runPreview({ modelRef: 'm1' }); });
    await waitFor(() => expect(result.current.draft).not.toBeNull());

    mockApi.commitDecompose = vi.fn().mockRejectedValueOnce(
      Object.assign(new Error('conflict'), { status: 409, body: { detail: { code: 'CHAPTER_ALREADY_PLANNED', chapter_ids: ['ch1'] } } }),
    );
    act(() => { result.current.commit(); });
    await waitFor(() => expect(result.current.needsReplace).toEqual(['ch1']));

    mockApi.commitDecompose = vi.fn().mockResolvedValue({});
    act(() => { result.current.confirmReplace(); });
    await waitFor(() => expect(mockApi.commitDecompose).toHaveBeenCalled());
    expect(mockApi.commitDecompose.mock.calls[0][1].replace).toBe(true);
    // a successful commit clears the draft.
    await waitFor(() => expect(result.current.draft).toBeNull());
  });
});
