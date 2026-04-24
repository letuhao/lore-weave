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

// K19b.6 (D-K19a.5-03): the dialog now reads user-wide costs to show
// "$X left this month" near max_spend. Default mock returns null costs
// so existing tests see no hint; the dedicated test below overrides.
const useUserCostsMock = vi.fn().mockReturnValue({
  costs: null,
  isLoading: false,
  error: null,
});
vi.mock('../../hooks/useUserCosts', () => ({
  useUserCosts: () => useUserCostsMock(),
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
    project_name: null,
  };
}

describe('BuildGraphDialog', () => {
  beforeEach(() => {
    listUserModelsMock.mockReset();
    estimateMock.mockReset();
    startMock.mockReset();
    benchmarkMock.mockReset();
    toastErrorMock.mockReset();
    // Default useUserCosts → null costs so existing tests see no hint.
    useUserCostsMock.mockReset();
    useUserCostsMock.mockReturnValue({
      costs: null,
      isLoading: false,
      error: null,
    });
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
    // C12c-b — glossary_sync also depends on a linked book; must be
    // hidden when book_id=null, same as chapters. BE 422s on start
    // with this combo (C12c-a MED#1), so the UI must not offer it.
    expect(
      screen.queryByRole('radio', { name: 'projects.buildDialog.scope.glossary_sync' }),
    ).toBeNull();
  });

  // ── C12c-b — glossary_sync scope option ───────────────────────

  it('renders glossary_sync radio when project has a linked book', () => {
    renderDialog();
    // sampleProject has book_id set → glossary_sync should appear.
    expect(
      screen.getByRole('radio', { name: 'projects.buildDialog.scope.glossary_sync' }),
    ).toBeDefined();
  });

  it('start payload carries scope=glossary_sync when the radio is selected', async () => {
    estimateMock.mockResolvedValue(sampleEstimate());
    startMock.mockResolvedValue(sampleJob());
    renderDialog();

    await waitFor(() => {
      expect(screen.getByRole('option', { name: /GPT-5/ })).toBeDefined();
    });

    // Switch to glossary_sync, pick LLM + embedding.
    fireEvent.click(
      screen.getByRole('radio', { name: 'projects.buildDialog.scope.glossary_sync' }),
    );
    fireEvent.change(
      screen.getByRole('combobox', { name: 'projects.buildDialog.llmModel.label' }),
      { target: { value: 'gpt-5' } },
    );
    fireEvent.change(screen.getByTestId('embedding-picker'), {
      target: { value: 'bge-m3' },
    });
    await new Promise((r) => setTimeout(r, 350));

    await act(async () => {
      fireEvent.click(
        screen.getByRole('button', { name: 'projects.buildDialog.confirm' }),
      );
    });

    await waitFor(() => {
      expect(startMock).toHaveBeenCalledTimes(1);
    });
    const payload = startMock.mock.calls[0][1];
    expect(payload.scope).toBe('glossary_sync');
    // scope_range MUST be omitted — glossary_sync has no chapter_range.
    expect(payload.scope_range).toBeUndefined();
  });

  // ── C12a (D-K19a.5-04) — chapter-range picker ─────────────────

  it('renders chapter-range picker only when scope=chapters', () => {
    renderDialog();
    // Default scope is 'chapters' for book-linked project.
    expect(
      screen.getByTestId('build-graph-chapter-range'),
    ).toBeInTheDocument();
    // Switch to 'chat' — picker hides.
    fireEvent.click(
      screen.getByRole('radio', { name: 'projects.buildDialog.scope.chat' }),
    );
    expect(
      screen.queryByTestId('build-graph-chapter-range'),
    ).not.toBeInTheDocument();
  });

  it('start payload carries scope_range.chapter_range when both inputs are set', async () => {
    estimateMock.mockResolvedValue(sampleEstimate());
    startMock.mockResolvedValue(sampleJob());
    renderDialog();
    await waitFor(() => {
      expect(screen.getByRole('option', { name: /GPT-5/ })).toBeDefined();
    });
    fireEvent.change(
      screen.getByRole('combobox', { name: 'projects.buildDialog.llmModel.label' }),
      { target: { value: 'gpt-5' } },
    );
    fireEvent.change(screen.getByTestId('embedding-picker'), {
      target: { value: 'bge-m3' },
    });
    fireEvent.change(screen.getByTestId('build-graph-chapter-range-from'), {
      target: { value: '10' },
    });
    fireEvent.change(screen.getByTestId('build-graph-chapter-range-to'), {
      target: { value: '20' },
    });
    await new Promise((r) => setTimeout(r, 350));
    await act(async () => {
      fireEvent.click(
        screen.getByRole('button', { name: 'projects.buildDialog.confirm' }),
      );
    });
    await waitFor(() => {
      expect(startMock).toHaveBeenCalledTimes(1);
    });
    const call = startMock.mock.calls[0];
    expect(call[1]).toMatchObject({
      scope: 'chapters',
      scope_range: { chapter_range: [10, 20] },
    });
  });

  it('Confirm disabled + invalid hint shown on reversed chapter range', async () => {
    estimateMock.mockResolvedValue(sampleEstimate());
    renderDialog();
    await waitFor(() => {
      expect(screen.getByRole('option', { name: /GPT-5/ })).toBeDefined();
    });
    fireEvent.change(
      screen.getByRole('combobox', { name: 'projects.buildDialog.llmModel.label' }),
      { target: { value: 'gpt-5' } },
    );
    fireEvent.change(screen.getByTestId('build-graph-chapter-range-from'), {
      target: { value: '50' },
    });
    fireEvent.change(screen.getByTestId('build-graph-chapter-range-to'), {
      target: { value: '10' },
    });
    expect(
      screen.getByTestId('build-graph-chapter-range-invalid'),
    ).toBeInTheDocument();
    const confirm = screen.getByRole('button', {
      name: 'projects.buildDialog.confirm',
    }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
  });

  it('start payload omits scope_range when chapter range inputs are empty', async () => {
    estimateMock.mockResolvedValue(sampleEstimate());
    startMock.mockResolvedValue(sampleJob());
    renderDialog();
    await waitFor(() => {
      expect(screen.getByRole('option', { name: /GPT-5/ })).toBeDefined();
    });
    fireEvent.change(
      screen.getByRole('combobox', { name: 'projects.buildDialog.llmModel.label' }),
      { target: { value: 'gpt-5' } },
    );
    fireEvent.change(screen.getByTestId('embedding-picker'), {
      target: { value: 'bge-m3' },
    });
    // Leave chapter range inputs empty — default state.
    await new Promise((r) => setTimeout(r, 350));
    await act(async () => {
      fireEvent.click(
        screen.getByRole('button', { name: 'projects.buildDialog.confirm' }),
      );
    });
    await waitFor(() => expect(startMock).toHaveBeenCalledTimes(1));
    const payload = startMock.mock.calls[0][1];
    expect(payload.scope).toBe('chapters');
    expect(payload.scope_range).toBeUndefined();
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

  // K19b.5: initialValues pre-fill for the retry flow.
  it('pre-fills form state from initialValues when the dialog opens', async () => {
    // beforeEach has already stubbed listUserModelsMock with a gpt-5
    // model; use that so the <select>'s DOM value matches (a select
    // with a value absent from its options silently falls back to empty,
    // which would make this test unreliable).
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <BuildGraphDialog
          open={true}
          onOpenChange={vi.fn()}
          project={sampleProject}
          onStarted={vi.fn()}
          initialValues={{
            scope: 'all',
            llmModel: 'gpt-5',
            embeddingModel: 'bge-m3',
            maxSpend: '7.50',
          }}
        />
      </QueryClientProvider>,
    );

    // Scope is a radio group. Assert the 'all' radio is checked.
    const scopeAll = screen.getByRole('radio', {
      name: 'projects.buildDialog.scope.all',
    }) as HTMLInputElement;
    expect(scopeAll.checked).toBe(true);

    // LLM model is a real <select>; wait for the listUserModels mock
    // to resolve so gpt-5 option exists before asserting the value.
    const llmSelect = screen.getByRole('combobox', {
      name: 'projects.buildDialog.llmModel.label',
    }) as HTMLSelectElement;
    await waitFor(() => {
      expect(llmSelect.value).toBe('gpt-5');
    });

    // Embedding picker stub renders a <select> with testid (see top-of-file mock).
    const embedding = screen.getByTestId('embedding-picker') as HTMLSelectElement;
    expect(embedding.value).toBe('bge-m3');

    // max_spend is a plain <input type="text"> with a 0.00 placeholder.
    // The wrapping <label> concatenates title + hint into the a11y name,
    // so `getByRole('textbox', { name: ... })` is fragile; match the
    // placeholder instead.
    const maxSpend = screen.getByPlaceholderText('0.00') as HTMLInputElement;
    expect(maxSpend.value).toBe('7.50');
  });

  // C12c-b /review-impl LOW#2 — retry pre-fill for glossary_sync
  it('pre-fills scope=glossary_sync from initialValues on book-linked project', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <BuildGraphDialog
          open={true}
          onOpenChange={vi.fn()}
          project={sampleProject}
          onStarted={vi.fn()}
          initialValues={{ scope: 'glossary_sync' }}
        />
      </QueryClientProvider>,
    );
    const radio = screen.getByRole('radio', {
      name: 'projects.buildDialog.scope.glossary_sync',
    }) as HTMLInputElement;
    expect(radio.checked).toBe(true);
  });

  // C12c-b /review-impl LOW#1 — if the prior job's scope is now
  // unavailable (book_id unlinked between job creation and retry),
  // fall back to defaultScope so no radio is orphaned in state-but-
  // not-rendered. Mirrors the availableScopes filter.
  it('falls back to defaultScope when initialValues.scope is no longer available', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <BuildGraphDialog
          open={true}
          onOpenChange={vi.fn()}
          project={{ ...sampleProject, book_id: null }}
          onStarted={vi.fn()}
          initialValues={{ scope: 'glossary_sync' }}
        />
      </QueryClientProvider>,
    );
    // glossary_sync radio must NOT be rendered (filter excludes it).
    expect(
      screen.queryByRole('radio', { name: 'projects.buildDialog.scope.glossary_sync' }),
    ).toBeNull();
    // defaultScope ('all' for no-book project) should be checked
    // instead — scope state snapped back rather than left orphaned.
    const allRadio = screen.getByRole('radio', {
      name: 'projects.buildDialog.scope.all',
    }) as HTMLInputElement;
    expect(allRadio.checked).toBe(true);
  });

  // C12c-b /review-impl LOW#1 — symmetric test for chapters
  // (pre-existing pattern C12c-b's fallback also covers).
  it('falls back to defaultScope when initialValues.scope=chapters on unlinked project', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <BuildGraphDialog
          open={true}
          onOpenChange={vi.fn()}
          project={{ ...sampleProject, book_id: null }}
          onStarted={vi.fn()}
          initialValues={{ scope: 'chapters' }}
        />
      </QueryClientProvider>,
    );
    expect(
      screen.queryByRole('radio', { name: 'projects.buildDialog.scope.chapters' }),
    ).toBeNull();
    const allRadio = screen.getByRole('radio', {
      name: 'projects.buildDialog.scope.all',
    }) as HTMLInputElement;
    expect(allRadio.checked).toBe(true);
  });

  // D-K19a.5-03 (cleared in K19b.6): monthly-remaining hint near max_spend.
  it('shows "$X left this month" hint when user-wide budget is set', () => {
    useUserCostsMock.mockReturnValue({
      costs: {
        all_time_usd: '40',
        current_month_usd: '5',
        monthly_budget_usd: '20',
        monthly_remaining_usd: '15.00',
      },
      isLoading: false,
      error: null,
    });
    renderDialog();
    // vitest.setup.ts i18n mock returns the raw key verbatim when the
    // key itself doesn't contain `{{placeholder}}` substrings (dotted
    // paths don't). Assert the hint renders — its i18n template is
    // covered by projectState.test.ts's DIALOG_KEYS iterator.
    expect(screen.getByTestId('build-dialog-monthly-remaining')).toBeInTheDocument();
  });

  it('hides the monthly-remaining hint when no user-wide cap is set', () => {
    // Default mock already returns costs=null, hint should not render.
    renderDialog();
    expect(screen.queryByTestId('build-dialog-monthly-remaining')).toBeNull();
  });
});
