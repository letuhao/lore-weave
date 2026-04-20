import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Mock the auth + API modules before the component imports them.
vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok-test' }),
}));

const listUserModelsMock = vi.fn();
vi.mock('../../../ai-models/api', () => ({
  aiModelsApi: {
    listUserModels: (...args: unknown[]) => listUserModelsMock(...args),
  },
}));

const estimateMock = vi.fn();
const startMock = vi.fn();
const benchmarkMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    knowledgeApi: {
      estimateExtraction: (...args: unknown[]) => estimateMock(...args),
      startExtraction: (...args: unknown[]) => startMock(...args),
      getBenchmarkStatus: (...args: unknown[]) => benchmarkMock(...args),
    },
  };
});

// Stub the embedding picker: replace with a <select> exposing value via
// onChange so tests can drive it synchronously without loading the
// benchmark-status side effect.
vi.mock('../EmbeddingModelPicker', () => ({
  EmbeddingModelPicker: ({
    value,
    onChange,
  }: {
    value: string | null;
    onChange: (v: string | null) => void;
  }) => (
    <select
      data-testid="embedding-picker"
      value={value ?? ''}
      onChange={(e) => onChange(e.target.value === '' ? null : e.target.value)}
    >
      <option value="">none</option>
      <option value="bge-m3">bge-m3</option>
    </select>
  ),
}));

const toastErrorMock = vi.fn();
vi.mock('sonner', () => ({
  toast: { error: (...args: unknown[]) => toastErrorMock(...args) },
}));

// Import AFTER the mocks so the component picks them up.
import { BuildGraphDialog, readBackendError } from '../BuildGraphDialog';
import type { Project } from '../../types';

const sampleProject: Project = {
  project_id: 'p1',
  user_id: 'u1',
  name: 'Test',
  description: '',
  project_type: 'book',
  instructions: '',
  book_id: 'b1',
  extraction_enabled: false,
  extraction_status: 'disabled',
  embedding_model: null,
  embedding_dimension: null,
  extraction_config: {},
  last_extracted_at: null,
  estimated_cost_usd: '0',
  actual_cost_usd: '0',
  is_archived: false,
  version: 1,
  created_at: '2026-04-19T00:00:00Z',
  updated_at: '2026-04-19T00:00:00Z',
};

function renderDialog(onOpenChange = vi.fn(), onStarted = vi.fn(), open = true) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={qc}>
      <BuildGraphDialog
        open={open}
        onOpenChange={onOpenChange}
        project={sampleProject}
        onStarted={onStarted}
      />
    </QueryClientProvider>,
  );
  return { ...utils, onOpenChange, onStarted, qc };
}

function sampleEstimate() {
  return {
    items_total: 10,
    items: { chapters: 5, chat_turns: 3, glossary_entities: 2 },
    estimated_tokens: 12000,
    estimated_cost_usd_low: '0.10',
    estimated_cost_usd_high: '0.30',
    estimated_duration_seconds: 60,
  };
}

function sampleJob() {
  return {
    job_id: 'j1',
    user_id: 'u1',
    project_id: 'p1',
    scope: 'chapters' as const,
    scope_range: null,
    status: 'pending' as const,
    llm_model: 'gpt-5',
    embedding_model: 'bge-m3',
    max_spend_usd: null,
    items_processed: 0,
    items_total: 10,
    cost_spent_usd: '0',
    current_cursor: null,
    started_at: '2026-04-19T12:00:00Z',
    paused_at: null,
    completed_at: null,
    created_at: '2026-04-19T12:00:00Z',
    updated_at: '2026-04-19T12:00:00Z',
    error_message: null,
  };
}

describe('BuildGraphDialog', () => {
  beforeEach(() => {
    listUserModelsMock.mockReset();
    estimateMock.mockReset();
    startMock.mockReset();
    benchmarkMock.mockReset();
    toastErrorMock.mockReset();
    listUserModelsMock.mockResolvedValue({
      items: [
        {
          user_model_id: 'm1',
          provider_credential_id: 'c1',
          provider_kind: 'openai',
          provider_model_name: 'gpt-5',
          alias: 'GPT-5',
          is_active: true,
          is_favorite: true,
          tags: [],
          created_at: '2026-04-19T00:00:00Z',
        },
      ],
    });
    // Default: benchmark passed — keeps happy-path tests unchanged.
    benchmarkMock.mockResolvedValue({
      has_run: true,
      passed: true,
      recall_at_3: 0.95,
    });
  });

  it('renders when open with title + scope + llm fields', () => {
    renderDialog();
    expect(screen.getByText('projects.buildDialog.title')).toBeDefined();
    expect(screen.getByText('projects.buildDialog.scope.label')).toBeDefined();
    expect(screen.getByText('projects.buildDialog.llmModel.label')).toBeDefined();
  });

  it('does not render dialog body when open=false', () => {
    renderDialog(vi.fn(), vi.fn(), false);
    expect(screen.queryByText('projects.buildDialog.title')).toBeNull();
  });

  it('confirm button disabled until llm + embedding are picked', async () => {
    renderDialog();
    const confirm = screen.getByRole('button', {
      name: 'projects.buildDialog.confirm',
    }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
  });

  it('auto-fetches estimate after debounce when llm is picked', async () => {
    estimateMock.mockResolvedValue(sampleEstimate());
    renderDialog();
    await waitFor(() => {
      expect(screen.getByRole('option', { name: /GPT-5/ })).toBeDefined();
    });
    fireEvent.change(screen.getByRole('combobox', { name: 'projects.buildDialog.llmModel.label' }), {
      target: { value: 'gpt-5' },
    });
    await new Promise((r) => setTimeout(r, 350));
    await waitFor(() => {
      expect(estimateMock).toHaveBeenCalledWith(
        'p1',
        { scope: 'chapters', llm_model: 'gpt-5' },
        'tok-test',
      );
    });
  });

  it('calls startExtraction with full payload on confirm', async () => {
    estimateMock.mockResolvedValue(sampleEstimate());
    startMock.mockResolvedValue(sampleJob());
    const { onStarted, onOpenChange } = renderDialog();
    await waitFor(() => {
      expect(screen.getByRole('option', { name: /GPT-5/ })).toBeDefined();
    });
    fireEvent.change(screen.getByRole('combobox', { name: 'projects.buildDialog.llmModel.label' }), {
      target: { value: 'gpt-5' },
    });
    fireEvent.change(screen.getByTestId('embedding-picker'), {
      target: { value: 'bge-m3' },
    });
    await new Promise((r) => setTimeout(r, 350));
    fireEvent.change(screen.getByPlaceholderText('0.00'), { target: { value: '1.50' } });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'projects.buildDialog.confirm' }));
    });

    await waitFor(() => {
      expect(startMock).toHaveBeenCalledWith(
        'p1',
        {
          scope: 'chapters',
          llm_model: 'gpt-5',
          embedding_model: 'bge-m3',
          max_spend_usd: '1.50',
        },
        'tok-test',
      );
    });
    expect(onStarted).toHaveBeenCalledTimes(1);
    expect(onStarted).toHaveBeenCalledWith();
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('toasts on start failure and keeps dialog open', async () => {
    estimateMock.mockResolvedValue(sampleEstimate());
    startMock.mockRejectedValue(new Error('boom'));
    const { onStarted, onOpenChange } = renderDialog();
    await waitFor(() => {
      expect(screen.getByRole('option', { name: /GPT-5/ })).toBeDefined();
    });
    fireEvent.change(screen.getByRole('combobox', { name: 'projects.buildDialog.llmModel.label' }), {
      target: { value: 'gpt-5' },
    });
    fireEvent.change(screen.getByTestId('embedding-picker'), {
      target: { value: 'bge-m3' },
    });
    await new Promise((r) => setTimeout(r, 350));
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'projects.buildDialog.confirm' }));
    });
    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalled();
    });
    expect(onStarted).not.toHaveBeenCalled();
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });

  it('flags an invalid max_spend and disables confirm', async () => {
    renderDialog();
    await waitFor(() => {
      expect(screen.getByRole('option', { name: /GPT-5/ })).toBeDefined();
    });
    fireEvent.change(screen.getByRole('combobox', { name: 'projects.buildDialog.llmModel.label' }), {
      target: { value: 'gpt-5' },
    });
    fireEvent.change(screen.getByTestId('embedding-picker'), {
      target: { value: 'bge-m3' },
    });
    fireEvent.change(screen.getByPlaceholderText('0.00'), { target: { value: 'abc' } });
    const confirm = screen.getByRole('button', {
      name: 'projects.buildDialog.confirm',
    }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    expect(screen.getByText('projects.buildDialog.maxSpend.invalid')).toBeDefined();
  });

  it('Cancel button calls onOpenChange(false)', async () => {
    const { onOpenChange } = renderDialog();
    fireEvent.click(screen.getByRole('button', { name: 'projects.buildDialog.cancel' }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('renders estimate failure inline without blocking confirm', async () => {
    estimateMock.mockRejectedValue(new Error('429 rate limit'));
    renderDialog();
    await waitFor(() => {
      expect(screen.getByRole('option', { name: /GPT-5/ })).toBeDefined();
    });
    fireEvent.change(screen.getByRole('combobox', { name: 'projects.buildDialog.llmModel.label' }), {
      target: { value: 'gpt-5' },
    });
    await new Promise((r) => setTimeout(r, 350));
    await waitFor(() => {
      expect(screen.getByText(/projects\.buildDialog\.estimate\.failed/)).toBeDefined();
    });
  });

  // review-impl F1 — BE 409 carries `{detail: {error_code, message}}`.
  // apiJson throws with `body` attached. Dialog must extract the
  // detail.message via `readBackendError` rather than echoing the
  // top-level Error.message ("Conflict"). The i18n mock returns keys
  // verbatim, so we unit-test the extractor directly here — and
  // assert that the toast still fires for the start-path regression
  // coverage.
  it('toasts a start failure that carries a BE detail.message body', async () => {
    estimateMock.mockResolvedValue(sampleEstimate());
    const apiErr = Object.assign(new Error('Conflict'), {
      status: 409,
      body: {
        detail: {
          error_code: 'benchmark_failed',
          message: 'the most recent benchmark did not pass',
        },
      },
    });
    startMock.mockRejectedValue(apiErr);
    renderDialog();
    await waitFor(() => {
      expect(screen.getByRole('option', { name: /GPT-5/ })).toBeDefined();
    });
    fireEvent.change(screen.getByRole('combobox', { name: 'projects.buildDialog.llmModel.label' }), {
      target: { value: 'gpt-5' },
    });
    fireEvent.change(screen.getByTestId('embedding-picker'), {
      target: { value: 'bge-m3' },
    });
    await new Promise((r) => setTimeout(r, 350));
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'projects.buildDialog.confirm' }));
    });
    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalled();
    });
  });

  // review-impl F2 — chapters scope is a book-only code path on BE.
  // Hide the radio option for projects that aren't linked to a book.
  it('hides the chapters radio when project has no book_id', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <BuildGraphDialog
          open
          onOpenChange={vi.fn()}
          project={{ ...sampleProject, book_id: null }}
          onStarted={vi.fn()}
        />
      </QueryClientProvider>,
    );
    // Only `chat` and `all` radios should exist.
    expect(screen.queryByRole('radio', { name: 'projects.buildDialog.scope.chapters' })).toBeNull();
    expect(screen.getByRole('radio', { name: 'projects.buildDialog.scope.chat' })).toBeDefined();
    expect(screen.getByRole('radio', { name: 'projects.buildDialog.scope.all' })).toBeDefined();
    expect(screen.getByText('projects.buildDialog.scope.noBookHint')).toBeDefined();
  });

  // review-impl F1 — pure-function coverage for the backend-error
  // extractor. The component integration test proves toast fires; this
  // proves the string ends up correct regardless of i18n stubbing.
  describe('readBackendError (F1 extractor)', () => {
    it('returns detail.message when BE returns {detail: {message}}', () => {
      const err = Object.assign(new Error('Conflict'), {
        status: 409,
        body: { detail: { error_code: 'benchmark_failed', message: 'explained' } },
      });
      expect(readBackendError(err)).toBe('explained');
    });

    it('returns detail itself when BE returns {detail: "string"}', () => {
      const err = Object.assign(new Error('Conflict'), {
        status: 409,
        body: { detail: 'project not found' },
      });
      expect(readBackendError(err)).toBe('project not found');
    });

    it('falls back to err.message when body has no detail', () => {
      const err = Object.assign(new Error('network down'), {
        status: 502,
        body: null,
      });
      expect(readBackendError(err)).toBe('network down');
    });

    it('stringifies non-Error values', () => {
      expect(readBackendError('raw string')).toBe('raw string');
    });
  });

  // review-impl F6 — Confirm must stay disabled while benchmark is
  // known to have failed or never run. Prevents the round-trip to a
  // guaranteed 409 and surfaces the picker-badge rationale.
  it('gates Confirm on a passing benchmark status', async () => {
    benchmarkMock.mockResolvedValue({ has_run: false, passed: false });
    estimateMock.mockResolvedValue(sampleEstimate());
    renderDialog();
    await waitFor(() => {
      expect(screen.getByRole('option', { name: /GPT-5/ })).toBeDefined();
    });
    fireEvent.change(screen.getByRole('combobox', { name: 'projects.buildDialog.llmModel.label' }), {
      target: { value: 'gpt-5' },
    });
    fireEvent.change(screen.getByTestId('embedding-picker'), {
      target: { value: 'bge-m3' },
    });
    await waitFor(() => {
      expect(benchmarkMock).toHaveBeenCalled();
    });
    const confirm = screen.getByRole('button', {
      name: 'projects.buildDialog.confirm',
    }) as HTMLButtonElement;
    await waitFor(() => {
      expect(confirm.disabled).toBe(true);
    });
  });
});
