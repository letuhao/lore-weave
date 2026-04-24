import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

// C12b-b — focus: the new RunBenchmarkButton rendered inside the
// picker's BenchmarkBadge area. Existing picker behaviour (select
// render, orphan fallback, benchmark badge copy) is covered
// implicitly — we assert the key contract: button visibility is
// driven entirely by `projectId && value && !status.passed`.

vi.mock('@/auth', () => ({
  useAuth: () => ({
    accessToken: 'tok-test',
    user: {
      user_id: 'u1',
      email: 'a@b',
      display_name: null,
      avatar_url: null,
    },
  }),
}));

const toastMocks = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
}));
vi.mock('sonner', () => ({
  toast: toastMocks,
}));

const listUserModelsMock = vi.fn();
vi.mock('@/features/ai-models/api', () => ({
  aiModelsApi: {
    listUserModels: (...args: unknown[]) => listUserModelsMock(...args),
  },
}));

const getBenchmarkStatusMock = vi.fn();
const runBenchmarkMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    knowledgeApi: {
      getBenchmarkStatus: (...args: unknown[]) => getBenchmarkStatusMock(...args),
      runBenchmark: (...args: unknown[]) => runBenchmarkMock(...args),
    },
  };
});

import { EmbeddingModelPicker } from '../EmbeddingModelPicker';

const PROJECT_ID = '11111111-1111-1111-1111-111111111111';

function Wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function renderPicker(props: Partial<Parameters<typeof EmbeddingModelPicker>[0]>) {
  const onChange = vi.fn();
  const result = render(
    <EmbeddingModelPicker
      value="bge-m3"
      onChange={onChange}
      projectId={PROJECT_ID}
      {...props}
    />,
    { wrapper: Wrapper },
  );
  return { ...result, onChange };
}

describe('EmbeddingModelPicker — RunBenchmarkButton (C12b-b)', () => {
  beforeEach(() => {
    listUserModelsMock.mockReset();
    getBenchmarkStatusMock.mockReset();
    runBenchmarkMock.mockReset();
    toastMocks.success.mockReset();
    toastMocks.error.mockReset();
    toastMocks.info.mockReset();
    listUserModelsMock.mockResolvedValue({
      items: [
        {
          user_model_id: 'm1',
          provider_kind: 'openai',
          provider_model_name: 'bge-m3',
          alias: null,
        },
      ],
    });
  });

  const STATUS_NO_RUN = {
    has_run: false,
    passed: null,
    run_id: null,
    embedding_model: null,
    recall_at_3: null,
    mrr: null,
    created_at: null,
  };
  const STATUS_FAILED = {
    has_run: true,
    passed: false,
    run_id: 'r1',
    embedding_model: 'bge-m3',
    recall_at_3: 0.1,
    mrr: 0.05,
    created_at: '2026-04-24T00:00:00Z',
  };
  const STATUS_PASSED = {
    has_run: true,
    passed: true,
    run_id: 'r2',
    embedding_model: 'bge-m3',
    recall_at_3: 0.82,
    mrr: 0.71,
    created_at: '2026-04-24T00:00:00Z',
  };

  it('does NOT render button when projectId is undefined', async () => {
    getBenchmarkStatusMock.mockResolvedValue(STATUS_NO_RUN);
    renderPicker({ projectId: undefined });
    // Wait for models query to settle so we don't assert too early.
    await waitFor(() => expect(listUserModelsMock).toHaveBeenCalled());
    expect(
      screen.queryByRole('button', { name: /projects\.form\.benchmark\.run/ }),
    ).toBeNull();
    // Badge also hidden (no projectId → no benchmark query).
    expect(getBenchmarkStatusMock).not.toHaveBeenCalled();
  });

  it('does NOT render button when value (model) is null', async () => {
    getBenchmarkStatusMock.mockResolvedValue(STATUS_NO_RUN);
    renderPicker({ value: null });
    await waitFor(() => expect(listUserModelsMock).toHaveBeenCalled());
    expect(
      screen.queryByRole('button', { name: /projects\.form\.benchmark\.run/ }),
    ).toBeNull();
    expect(getBenchmarkStatusMock).not.toHaveBeenCalled();
  });

  it('renders button when benchmark has_run=false', async () => {
    getBenchmarkStatusMock.mockResolvedValue(STATUS_NO_RUN);
    renderPicker({});
    const btn = await screen.findByRole('button', {
      name: /projects\.form\.benchmark\.run/,
    });
    expect(btn).toBeEnabled();
  });

  it('renders button when benchmark passed=false (failed state)', async () => {
    getBenchmarkStatusMock.mockResolvedValue(STATUS_FAILED);
    renderPicker({});
    const btn = await screen.findByRole('button', {
      name: /projects\.form\.benchmark\.run/,
    });
    expect(btn).toBeEnabled();
  });

  it('HIDES button when benchmark passed=true', async () => {
    getBenchmarkStatusMock.mockResolvedValue(STATUS_PASSED);
    renderPicker({});
    // Wait until the benchmark badge query settles so we know status
    // hydrated. Badge renders passed copy key.
    await screen.findByText(/projects\.form\.benchmarkPassed/);
    expect(
      screen.queryByRole('button', { name: /projects\.form\.benchmark\.run/ }),
    ).toBeNull();
  });

  it('fires runBenchmark with runs=3 on click + shows success toast', async () => {
    getBenchmarkStatusMock.mockResolvedValue(STATUS_NO_RUN);
    runBenchmarkMock.mockResolvedValue({
      run_id: 'r-success',
      embedding_model: 'bge-m3',
      passed: true,
      recall_at_3: 0.85,
      mrr: 0.72,
      avg_score_positive: 0.68,
      negative_control_max_score: 0.28,
      stddev_recall: 0.02,
      stddev_mrr: 0.03,
      runs: 3,
    });
    renderPicker({});
    const btn = await screen.findByRole('button', {
      name: /projects\.form\.benchmark\.run/,
    });
    fireEvent.click(btn);
    await waitFor(() => {
      expect(runBenchmarkMock).toHaveBeenCalledWith(
        PROJECT_ID,
        3,
        'tok-test',
      );
    });
    await waitFor(() => {
      expect(toastMocks.success).toHaveBeenCalledTimes(1);
    });
    // Toast arg is the i18n key (mock returns key; interpolation
    // applies only when the KEY contains {{...}} placeholders, so the
    // success copy just echoes the key).
    expect(toastMocks.success.mock.calls[0][0]).toContain(
      'projects.form.benchmark.success',
    );
  });

  it('shows "Running benchmark…" label while pending + disables button', async () => {
    getBenchmarkStatusMock.mockResolvedValue(STATUS_NO_RUN);
    // Resolve later so we can observe the pending state.
    let resolveRun: (v: unknown) => void = () => {};
    runBenchmarkMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveRun = resolve;
        }),
    );
    renderPicker({});
    const btn = await screen.findByRole('button', {
      name: /projects\.form\.benchmark\.run/,
    });
    fireEvent.click(btn);
    // Label swaps to the "running" key and disabled flips true.
    await waitFor(() => {
      expect(
        screen.getByRole('button', {
          name: /projects\.form\.benchmark\.running/,
        }),
      ).toBeDisabled();
    });
    // Unblock so the test's beforeEach cleanup doesn't strand a
    // pending promise that logs unhandled-rejection noise.
    resolveRun({
      run_id: 'r-late',
      embedding_model: 'bge-m3',
      passed: true,
      recall_at_3: 0.85,
      mrr: 0.72,
      avg_score_positive: 0.68,
      negative_control_max_score: 0.28,
      stddev_recall: 0.02,
      stddev_mrr: 0.03,
      runs: 3,
    });
  });

  it('shows code-specific error toast on 409 not_benchmark_project', async () => {
    getBenchmarkStatusMock.mockResolvedValue(STATUS_NO_RUN);
    runBenchmarkMock.mockRejectedValue(
      Object.assign(new Error('nope'), {
        status: 409,
        body: { detail: { error_code: 'not_benchmark_project' } },
      }),
    );
    renderPicker({});
    const btn = await screen.findByRole('button', {
      name: /projects\.form\.benchmark\.run/,
    });
    fireEvent.click(btn);
    await waitFor(() => {
      expect(toastMocks.error).toHaveBeenCalledTimes(1);
    });
    expect(toastMocks.error.mock.calls[0][0]).toContain(
      'errorNotBenchmarkProject',
    );
  });

  it('shows 502 error toast for embedding_provider_flake', async () => {
    getBenchmarkStatusMock.mockResolvedValue(STATUS_FAILED);
    runBenchmarkMock.mockRejectedValue(
      Object.assign(new Error('flake'), {
        status: 502,
        body: { detail: { error_code: 'embedding_provider_flake' } },
      }),
    );
    renderPicker({});
    const btn = await screen.findByRole('button', {
      name: /projects\.form\.benchmark\.run/,
    });
    fireEvent.click(btn);
    await waitFor(() => {
      expect(toastMocks.error).toHaveBeenCalledTimes(1);
    });
    expect(toastMocks.error.mock.calls[0][0]).toContain('errorProviderFlake');
  });

  it('shows generic error toast when error_code is missing (network/malformed)', async () => {
    getBenchmarkStatusMock.mockResolvedValue(STATUS_NO_RUN);
    runBenchmarkMock.mockRejectedValue(new Error('ECONNREFUSED'));
    renderPicker({});
    const btn = await screen.findByRole('button', {
      name: /projects\.form\.benchmark\.run/,
    });
    fireEvent.click(btn);
    await waitFor(() => {
      expect(toastMocks.error).toHaveBeenCalledTimes(1);
    });
    expect(toastMocks.error.mock.calls[0][0]).toContain('errorGeneric');
  });
});
