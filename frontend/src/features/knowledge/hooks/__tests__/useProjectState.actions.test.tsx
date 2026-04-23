// C4 (D-K19a.5-05 + D-K19a.7-01) — action-callback hook tests for
// useProjectState.
//
// The sibling .ts file covers the pure `deriveState` + `scopeOfJob`
// helpers. This .tsx file covers the hook's ACTION CALLBACK surface:
// 8 real BE-firing actions + 6 no-op placeholders. Each real action
// must (a) call the right `knowledgeApi` method with the right args,
// (b) invalidate both jobs + graph-stats queries on success, and
// (c) surface BE errors via `toast.error` without touching the
// query cache.
//
// Why this matters: the K19a.7 ACTION_KEYS map closed compile-time
// typos, but nothing locks the RUNTIME contract — a regression
// swapping `pauseExtraction` for `cancelExtraction` in `onPause`
// would ship undetected. These tests are the behavioural guard.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren, ReactNode } from 'react';

import type { ExtractionJobWire } from '../../api';
import type { Project } from '../../types';

// ── mocks ──────────────────────────────────────────────────────────
//
// vitest hoists vi.mock() factories above top-level consts, so the
// mock vars must be created via vi.hoisted() to beat the hoist.
// Referring to a bare top-level const here would crash with
// "Cannot access 'apiMocks' before initialization" at collection
// time (see memory: feedback_vitest_hoisted_mock_vars.md).

const { useAuthMock, apiMocks, toastErrorMock } = vi.hoisted(() => ({
  useAuthMock: vi.fn(),
  apiMocks: {
    listExtractionJobs: vi.fn(),
    getGraphStats: vi.fn(),
    pauseExtraction: vi.fn(),
    resumeExtraction: vi.fn(),
    cancelExtraction: vi.fn(),
    deleteGraph: vi.fn(),
    startExtraction: vi.fn(),
    rebuildGraph: vi.fn(),
  },
  toastErrorMock: vi.fn(),
}));

vi.mock('@/auth', () => ({ useAuth: () => useAuthMock() }));

vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return { ...actual, knowledgeApi: apiMocks };
});

vi.mock('sonner', () => ({
  toast: { error: (...a: unknown[]) => toastErrorMock(...a) },
}));

// /review-impl L4 — local i18n mock that encodes `opts` into the
// returned string. The global mock in `vitest.setup.ts` returns raw
// key paths with no interpolation — which means a regression that
// drops the `{label, error: msg}` opts passed to t('projects.toast.
// actionFailed', ...) would pass any `stringContaining('actionFailed')`
// assertion (both opt'd and un-opt'd calls produce the same key
// string). Encoding opts as `"<key>|<json>"` makes the drop observable.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts ? `${key}|${JSON.stringify(opts)}` : key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
  Trans: ({ children }: { children: ReactNode }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}));

import { useProjectState } from '../useProjectState';

// ── fixtures ───────────────────────────────────────────────────────

const PROJECT_ID = 'project-001';
const TOKEN = 'tok-test';

function makeProject(overrides: Partial<Project> = {}): Project {
  return {
    project_id: PROJECT_ID,
    user_id: 'u1',
    name: 'Test',
    description: '',
    project_type: 'translation',
    book_id: null,
    instructions: '',
    extraction_enabled: true,
    extraction_status: 'ready',
    embedding_model: 'bge-m3',
    embedding_dimension: 1024,
    extraction_config: {},
    last_extracted_at: null,
    estimated_cost_usd: '0',
    actual_cost_usd: '0',
    is_archived: false,
    version: 1,
    created_at: '2026-04-23T00:00:00Z',
    updated_at: '2026-04-23T00:00:00Z',
    ...overrides,
  };
}

function makeJobWire(
  overrides: Partial<ExtractionJobWire> = {},
): ExtractionJobWire {
  return {
    job_id: 'job-001',
    user_id: 'u1',
    project_id: PROJECT_ID,
    status: 'running',
    scope: 'all' as ExtractionJobWire['scope'],
    scope_range: null,
    llm_model: 'claude-sonnet-4-6',
    embedding_model: 'bge-m3',
    items_processed: 3,
    items_total: 10,
    cost_spent_usd: '0.50',
    max_spend_usd: '5.00',
    started_at: '2026-04-23T12:00:00Z',
    paused_at: null,
    completed_at: null,
    created_at: '2026-04-23T12:00:00Z',
    updated_at: '2026-04-23T12:00:00Z',
    current_cursor: null,
    error_message: null,
    project_name: null,
    ...overrides,
  };
}

// Pre-seed the query cache so the hook starts with non-null
// `latestJob` — lets actions that depend on `latestLlmModel` /
// `latestEmbeddingModel` / `latestScope` resolve their replayPayload
// without waiting on the initial `useQuery` fetch to resolve.
function makeWrapper(prefilledJobs?: ExtractionJobWire[]) {
  const qc = new QueryClient({
    // staleTime:Infinity prevents the pre-seeded data being instantly
    // stale → no auto-refetch loop during the test.
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  if (prefilledJobs) {
    qc.setQueryData(['knowledge-project-jobs', PROJECT_ID], prefilledJobs);
  }
  const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, Wrapper, invalidateSpy };
}

// ── setup ──────────────────────────────────────────────────────────

describe('useProjectState — actions', () => {
  beforeEach(() => {
    useAuthMock.mockReset().mockReturnValue({ accessToken: TOKEN });
    toastErrorMock.mockReset();
    // /review-impl L1 — loop over apiMocks rather than naming each
    // method explicitly. A future `knowledgeApi.newMethod` added to
    // the hook + the mock object will be reset automatically, no
    // per-method maintenance needed. Default every mock to resolve
    // with undefined so tests don't hang on an unmocked reject.
    for (const fn of Object.values(apiMocks)) {
      (fn as ReturnType<typeof vi.fn>).mockReset().mockResolvedValue(undefined);
    }
    // Two of the mocks feed useQuery and need specific default shapes
    // (useQuery returns the resolved value as `data`). Override after
    // the loop rather than inside it.
    apiMocks.listExtractionJobs.mockResolvedValue([]);
    apiMocks.getGraphStats.mockResolvedValue(null);
  });

  // ── Block 1: happy-path BE action fires ──────────────────────────

  it('onPause fires pauseExtraction with (project_id, token) and invalidates both queries', async () => {
    const { Wrapper, invalidateSpy } = makeWrapper([makeJobWire()]);
    const { result } = renderHook(() => useProjectState(makeProject()), {
      wrapper: Wrapper,
    });
    await act(async () => {
      result.current.actions.onPause();
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(apiMocks.pauseExtraction).toHaveBeenCalledTimes(1);
    });
    expect(apiMocks.pauseExtraction).toHaveBeenCalledWith(PROJECT_ID, TOKEN);
    const invalidated = invalidateSpy.mock.calls.map(
      (c) => (c[0] as { queryKey?: unknown[] })?.queryKey,
    );
    expect(invalidated).toContainEqual([
      'knowledge-project-jobs',
      PROJECT_ID,
    ]);
    expect(invalidated).toContainEqual([
      'knowledge-project-graph-stats',
      PROJECT_ID,
    ]);
  });

  it('onResume fires resumeExtraction', async () => {
    const { Wrapper } = makeWrapper([makeJobWire({ status: 'paused' })]);
    const { result } = renderHook(() => useProjectState(makeProject()), {
      wrapper: Wrapper,
    });
    await act(async () => {
      result.current.actions.onResume();
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(apiMocks.resumeExtraction).toHaveBeenCalledWith(PROJECT_ID, TOKEN);
    });
  });

  it('onCancel fires cancelExtraction', async () => {
    const { Wrapper } = makeWrapper([makeJobWire()]);
    const { result } = renderHook(() => useProjectState(makeProject()), {
      wrapper: Wrapper,
    });
    await act(async () => {
      result.current.actions.onCancel();
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(apiMocks.cancelExtraction).toHaveBeenCalledWith(PROJECT_ID, TOKEN);
    });
  });

  it('onDeleteGraph fires deleteGraph', async () => {
    const { Wrapper } = makeWrapper([makeJobWire({ status: 'complete' })]);
    const { result } = renderHook(() => useProjectState(makeProject()), {
      wrapper: Wrapper,
    });
    await act(async () => {
      result.current.actions.onDeleteGraph();
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(apiMocks.deleteGraph).toHaveBeenCalledWith(PROJECT_ID, TOKEN);
    });
  });

  it('onRebuild fires rebuildGraph with latest job models', async () => {
    const { Wrapper } = makeWrapper([
      makeJobWire({
        status: 'complete',
        llm_model: 'gpt-4o-mini',
        embedding_model: 'bge-m3-v2',
      }),
    ]);
    const { result } = renderHook(() => useProjectState(makeProject()), {
      wrapper: Wrapper,
    });
    await act(async () => {
      result.current.actions.onRebuild();
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(apiMocks.rebuildGraph).toHaveBeenCalledWith(
        PROJECT_ID,
        { llm_model: 'gpt-4o-mini', embedding_model: 'bge-m3-v2' },
        TOKEN,
      );
    });
  });

  // ── Block 2: replay-payload logic ────────────────────────────────

  it('onRetry replays the latest job scope + both models', async () => {
    const { Wrapper } = makeWrapper([
      makeJobWire({
        status: 'failed',
        scope: 'chat' as ExtractionJobWire['scope'],
        llm_model: 'claude-sonnet-4-6',
        embedding_model: 'bge-m3',
      }),
    ]);
    const { result } = renderHook(() => useProjectState(makeProject()), {
      wrapper: Wrapper,
    });
    await act(async () => {
      result.current.actions.onRetry();
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(apiMocks.startExtraction).toHaveBeenCalledTimes(1);
    });
    expect(apiMocks.startExtraction).toHaveBeenCalledWith(
      PROJECT_ID,
      {
        scope: 'chat',
        llm_model: 'claude-sonnet-4-6',
        embedding_model: 'bge-m3',
      },
      TOKEN,
    );
  });

  it('onRetry no-ops with noPriorJob toast when no prior job', async () => {
    const { Wrapper } = makeWrapper([]); // empty jobs list
    const { result } = renderHook(() => useProjectState(makeProject()), {
      wrapper: Wrapper,
    });
    await act(async () => {
      result.current.actions.onRetry();
      await Promise.resolve();
    });
    // noPriorJob is called without opts — the string is the raw key.
    expect(toastErrorMock).toHaveBeenCalledWith('projects.toast.noPriorJob');
    expect(apiMocks.startExtraction).not.toHaveBeenCalled();
  });

  it('onExtractNew forces scope="chapters" even when prior job was chat', async () => {
    const { Wrapper } = makeWrapper([
      makeJobWire({
        status: 'complete',
        scope: 'chat' as ExtractionJobWire['scope'],
      }),
    ]);
    const { result } = renderHook(() => useProjectState(makeProject()), {
      wrapper: Wrapper,
    });
    await act(async () => {
      result.current.actions.onExtractNew();
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(apiMocks.startExtraction).toHaveBeenCalledTimes(1);
    });
    const payload = apiMocks.startExtraction.mock.calls[0][1];
    expect(payload.scope).toBe('chapters');
  });

  it('onExtractNew no-ops with noPriorJob toast when no prior job', async () => {
    const { Wrapper } = makeWrapper([]);
    const { result } = renderHook(() => useProjectState(makeProject()), {
      wrapper: Wrapper,
    });
    await act(async () => {
      result.current.actions.onExtractNew();
      await Promise.resolve();
    });
    expect(toastErrorMock).toHaveBeenCalledWith('projects.toast.noPriorJob');
    expect(apiMocks.startExtraction).not.toHaveBeenCalled();
  });

  // /review-impl L3 — replayPayload null-guard branch coverage. The
  // guard is `!latestJobId || !latestLlmModel || !latestEmbeddingModel
  // || !latestScope`. The "empty jobs" test above only exercises the
  // first branch. Each of the 3 other branches gets an explicit test
  // — a regression dropping any one of the 4 checks (e.g. a well-meaning
  // refactor that forgot scope) would silently let a malformed payload
  // reach the BE.
  it('onRetry no-ops via replayPayload guard when llm_model is missing on latest job', async () => {
    const { Wrapper } = makeWrapper([
      makeJobWire({ status: 'failed', llm_model: null as unknown as string }),
    ]);
    const { result } = renderHook(() => useProjectState(makeProject()), {
      wrapper: Wrapper,
    });
    await act(async () => {
      result.current.actions.onRetry();
      await Promise.resolve();
    });
    expect(toastErrorMock).toHaveBeenCalledWith('projects.toast.noPriorJob');
    expect(apiMocks.startExtraction).not.toHaveBeenCalled();
  });

  it('onRetry no-ops via replayPayload guard when embedding_model is missing', async () => {
    const { Wrapper } = makeWrapper([
      makeJobWire({
        status: 'failed',
        embedding_model: null as unknown as string,
      }),
    ]);
    const { result } = renderHook(() => useProjectState(makeProject()), {
      wrapper: Wrapper,
    });
    await act(async () => {
      result.current.actions.onRetry();
      await Promise.resolve();
    });
    expect(toastErrorMock).toHaveBeenCalledWith('projects.toast.noPriorJob');
    expect(apiMocks.startExtraction).not.toHaveBeenCalled();
  });

  it('onRetry no-ops via replayPayload guard when scope is missing', async () => {
    const { Wrapper } = makeWrapper([
      makeJobWire({
        status: 'failed',
        scope: null as unknown as ExtractionJobWire['scope'],
      }),
    ]);
    const { result } = renderHook(() => useProjectState(makeProject()), {
      wrapper: Wrapper,
    });
    await act(async () => {
      result.current.actions.onRetry();
      await Promise.resolve();
    });
    expect(toastErrorMock).toHaveBeenCalledWith('projects.toast.noPriorJob');
    expect(apiMocks.startExtraction).not.toHaveBeenCalled();
  });

  // ── Block 3: rebuild / model-change guards ───────────────────────

  it('onConfirmModelChange fires rebuildGraph with latest models', async () => {
    const { Wrapper } = makeWrapper([
      makeJobWire({
        status: 'complete',
        llm_model: 'gpt-4o',
        embedding_model: 'text-embedding-3-large',
      }),
    ]);
    const { result } = renderHook(() => useProjectState(makeProject()), {
      wrapper: Wrapper,
    });
    await act(async () => {
      result.current.actions.onConfirmModelChange();
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(apiMocks.rebuildGraph).toHaveBeenCalledWith(
        PROJECT_ID,
        { llm_model: 'gpt-4o', embedding_model: 'text-embedding-3-large' },
        TOKEN,
      );
    });
  });

  // /review-impl L2 — symmetric rebuild-guard coverage. The guard is
  // `!latestLlmModel || !latestEmbeddingModel` — 2 fields × 2 actions
  // = 4 cells. Before this cycle only 2 of 4 were tested (onRebuild
  // with llm_model null + onConfirmModelChange with embedding_model
  // null). A regression dropping the OTHER half of the `||` check in
  // either action would have passed the 2 existing tests. These 4
  // tests close the matrix.
  it('onRebuild no-ops with noPriorRebuild toast when llm_model is missing', async () => {
    const { Wrapper } = makeWrapper([
      makeJobWire({ status: 'complete', llm_model: null as unknown as string }),
    ]);
    const { result } = renderHook(() => useProjectState(makeProject()), {
      wrapper: Wrapper,
    });
    await act(async () => {
      result.current.actions.onRebuild();
      await Promise.resolve();
    });
    expect(toastErrorMock).toHaveBeenCalledWith('projects.toast.noPriorRebuild');
    expect(apiMocks.rebuildGraph).not.toHaveBeenCalled();
  });

  it('onRebuild no-ops with noPriorRebuild toast when embedding_model is missing', async () => {
    const { Wrapper } = makeWrapper([
      makeJobWire({
        status: 'complete',
        embedding_model: null as unknown as string,
      }),
    ]);
    const { result } = renderHook(() => useProjectState(makeProject()), {
      wrapper: Wrapper,
    });
    await act(async () => {
      result.current.actions.onRebuild();
      await Promise.resolve();
    });
    expect(toastErrorMock).toHaveBeenCalledWith('projects.toast.noPriorRebuild');
    expect(apiMocks.rebuildGraph).not.toHaveBeenCalled();
  });

  it('onConfirmModelChange no-ops with noPriorRebuild toast when llm_model is missing', async () => {
    const { Wrapper } = makeWrapper([
      makeJobWire({ status: 'complete', llm_model: null as unknown as string }),
    ]);
    const { result } = renderHook(() => useProjectState(makeProject()), {
      wrapper: Wrapper,
    });
    await act(async () => {
      result.current.actions.onConfirmModelChange();
      await Promise.resolve();
    });
    expect(toastErrorMock).toHaveBeenCalledWith('projects.toast.noPriorRebuild');
    expect(apiMocks.rebuildGraph).not.toHaveBeenCalled();
  });

  it('onConfirmModelChange no-ops with noPriorRebuild toast when embedding_model is missing', async () => {
    const { Wrapper } = makeWrapper([
      makeJobWire({
        status: 'complete',
        embedding_model: null as unknown as string,
      }),
    ]);
    const { result } = renderHook(() => useProjectState(makeProject()), {
      wrapper: Wrapper,
    });
    await act(async () => {
      result.current.actions.onConfirmModelChange();
      await Promise.resolve();
    });
    expect(toastErrorMock).toHaveBeenCalledWith('projects.toast.noPriorRebuild');
    expect(apiMocks.rebuildGraph).not.toHaveBeenCalled();
  });

  // ── Block 4: error + no-token guards ─────────────────────────────

  it('onPause BE error surfaces actionFailed toast + leaves query cache untouched', async () => {
    apiMocks.pauseExtraction.mockRejectedValue(new Error('upstream 502'));
    const { Wrapper, invalidateSpy } = makeWrapper([makeJobWire()]);
    const { result } = renderHook(() => useProjectState(makeProject()), {
      wrapper: Wrapper,
    });
    const invalidateCallsBefore = invalidateSpy.mock.calls.length;
    await act(async () => {
      result.current.actions.onPause();
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalled();
    });
    // /review-impl L4 — assert the toast carried BOTH the outer
    // template key AND the `{label, error}` opts through. The local
    // i18n mock encodes opts as `"<key>|<json>"` so a regression
    // dropping the opts dict would fail this match. Label resolves
    // to the action key (projects.state.actions.pause) because the
    // mock returns raw keys when called without opts.
    const toastCall = toastErrorMock.mock.calls[0][0] as string;
    expect(toastCall).toContain('projects.toast.actionFailed');
    expect(toastCall).toContain('"label":"projects.state.actions.pause"');
    expect(toastCall).toContain('"error":"upstream 502"');
    // /review-impl C6 — explicit negative slice rather than equality
    // on `calls.length`. Asserts no NEW invalidateQueries happened
    // after our baseline. Critical: query cache must NOT be
    // invalidated on failure (else the FE re-polls on bad state).
    const postFailureInvalidates = invalidateSpy.mock.calls.slice(
      invalidateCallsBefore,
    );
    expect(postFailureInvalidates).toHaveLength(0);
  });

  it('accessToken=null short-circuits every real action (no API calls)', async () => {
    // /review-impl C5 — this single batched test exercises all 8
    // actions together. Chosen tradeoff: if ONE action leaks (fails
    // to short-circuit), the test fails by showing its specific mock
    // was called — still actionable, but the test doesn't tell you
    // whether the OTHER 7 actions were correct. Split into 8 tests
    // for isolation if a regression ever actually lands; current
    // density is appropriate for a guard that should either pass all
    // or fail one obvious case.
    useAuthMock.mockReturnValue({ accessToken: null });
    const { Wrapper } = makeWrapper([makeJobWire({ status: 'complete' })]);
    const { result } = renderHook(() => useProjectState(makeProject()), {
      wrapper: Wrapper,
    });
    await act(async () => {
      result.current.actions.onPause();
      result.current.actions.onResume();
      result.current.actions.onCancel();
      result.current.actions.onDeleteGraph();
      result.current.actions.onRetry();
      result.current.actions.onExtractNew();
      result.current.actions.onRebuild();
      result.current.actions.onConfirmModelChange();
      await Promise.resolve();
    });
    expect(apiMocks.pauseExtraction).not.toHaveBeenCalled();
    expect(apiMocks.resumeExtraction).not.toHaveBeenCalled();
    expect(apiMocks.cancelExtraction).not.toHaveBeenCalled();
    expect(apiMocks.deleteGraph).not.toHaveBeenCalled();
    expect(apiMocks.startExtraction).not.toHaveBeenCalled();
    expect(apiMocks.rebuildGraph).not.toHaveBeenCalled();
  });

  // ── no-op placeholders ───────────────────────────────────────────

  it('parent-owned no-op placeholders are callable without throwing or calling any API', async () => {
    // K19a.5 + K19a.6 own these — ProjectRow merges dialog-backed
    // overrides on top. The hook's job is to provide a complete
    // 14-action surface so a caller that forgets to merge doesn't
    // crash; the button just looks dead. This test locks "dead but
    // not crashy".
    const { Wrapper } = makeWrapper([makeJobWire()]);
    const { result } = renderHook(() => useProjectState(makeProject()), {
      wrapper: Wrapper,
    });
    expect(() => {
      result.current.actions.onBuildGraph();
      result.current.actions.onViewError();
      result.current.actions.onStart();
      result.current.actions.onChangeModel();
      result.current.actions.onDisable();
      result.current.actions.onIgnoreStale();
    }).not.toThrow();
    // No real API was touched by any of the 6 placeholders.
    expect(apiMocks.pauseExtraction).not.toHaveBeenCalled();
    expect(apiMocks.resumeExtraction).not.toHaveBeenCalled();
    expect(apiMocks.cancelExtraction).not.toHaveBeenCalled();
    expect(apiMocks.deleteGraph).not.toHaveBeenCalled();
    expect(apiMocks.startExtraction).not.toHaveBeenCalled();
    expect(apiMocks.rebuildGraph).not.toHaveBeenCalled();
  });
});
