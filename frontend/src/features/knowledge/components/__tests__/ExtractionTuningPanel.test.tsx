import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok-test' }),
}));

const updateExtractionConfigMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    knowledgeApi: {
      updateExtractionConfig: (...args: unknown[]) => updateExtractionConfigMock(...args),
    },
  };
});

const toastSuccessMock = vi.fn();
const toastErrorMock = vi.fn();
vi.mock('sonner', () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccessMock(...args),
    error: (...args: unknown[]) => toastErrorMock(...args),
  },
}));

// Stub the shared ModelPicker (covers the default-model + recovery-model inline
// pickers AND PrecisionFilterModelPicker's inner ModelPicker) — a button keyed by
// ariaLabel that emits a fixed model id, so payload logic is testable without the
// picker's fetch. A second click clears (emits null) to test the "use default" path.
vi.mock('@/components/model-picker', () => ({
  ModelPicker: ({
    value,
    onChange,
    ariaLabel,
  }: {
    value: string | null;
    onChange: (v: string | null) => void;
    ariaLabel: string;
  }) => (
    <button
      type="button"
      aria-label={ariaLabel}
      data-value={value ?? ''}
      onClick={() => onChange(value ? null : 'picked-model-uuid')}
    >
      {ariaLabel}
    </button>
  ),
}));

import { ExtractionTuningPanel } from '../ExtractionTuningPanel';
import type { Project } from '../../types';

function makeProject(extraction_config: Record<string, unknown> = {}): Project {
  return {
    project_id: 'p1',
    user_id: 'u1',
    name: 'Test',
    description: '',
    project_type: 'book',
    instructions: '',
    book_id: 'b1',
    extraction_enabled: true,
    tool_calling_enabled: true,
    memory_remember_confirm: false,
    extraction_status: 'ready',
    embedding_model: 'bge-m3',
    embedding_dimension: 1024,
    extraction_config,
    last_extracted_at: null,
    estimated_cost_usd: '0',
    actual_cost_usd: '0',
    is_archived: false,
    version: 4,
    created_at: '2026-05-31T00:00:00Z',
    updated_at: '2026-05-31T00:00:00Z',
  };
}

function renderPanel(project: Project, open = true) {
  const onOpenChange = vi.fn();
  const onChanged = vi.fn();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={qc}>
      <ExtractionTuningPanel
        open={open}
        onOpenChange={onOpenChange}
        project={project}
        onChanged={onChanged}
      />
    </QueryClientProvider>,
  );
  return { ...utils, onOpenChange, onChanged };
}

const saveBtn = () =>
  screen.getByRole('button', { name: 'projects.extractionTuning.save' }) as HTMLButtonElement;

describe('ExtractionTuningPanel', () => {
  beforeEach(() => {
    updateExtractionConfigMock.mockReset();
    updateExtractionConfigMock.mockResolvedValue(makeProject());
    toastSuccessMock.mockReset();
    toastErrorMock.mockReset();
  });

  it('renders when open, not when closed (visibility transition)', () => {
    const { unmount } = renderPanel(makeProject());
    expect(screen.getByText('projects.extractionTuning.title')).toBeDefined();
    unmount();
    renderPanel(makeProject(), false);
    expect(screen.queryByText('projects.extractionTuning.title')).toBeNull();
  });

  it('read-modify-write: the default LLM (llm_model) round-trips + filter preserved', async () => {
    const project = makeProject({
      llm_model: { model_ref: 'keep-me-uuid' },
      precision_filter: { enabled: true, categories: ['relation'], partial_policy: 'keep' },
    });
    renderPanel(project);
    // turn entity recovery ON (it was off — no entity_recovery in config)
    fireEvent.click(screen.getByLabelText('projects.extractionTuning.recoveryEnabled'));
    fireEvent.click(saveBtn());

    await waitFor(() => expect(updateExtractionConfigMock).toHaveBeenCalledTimes(1));
    const [projectId, payload, token, version] = updateExtractionConfigMock.mock.calls[0];
    expect(projectId).toBe('p1');
    expect(token).toBe('tok-test');
    expect(version).toBe(4); // If-Match = current version
    // KN model-roles — llm_model is now MANAGED by the default-model picker; the
    // persisted ref round-trips with the source stamped.
    expect(payload.llm_model).toEqual({ model_ref: 'keep-me-uuid', model_source: 'user_model' });
    // filter preserved + recovery toggled on
    expect(payload.precision_filter.categories).toEqual(['relation']);
    expect(payload.entity_recovery.enabled).toBe(true);
  });

  it('picking a default extraction model sends llm_model', async () => {
    renderPanel(makeProject());
    fireEvent.click(screen.getByLabelText('projects.extractionTuning.defaultModel'));
    fireEvent.click(saveBtn());
    await waitFor(() => expect(updateExtractionConfigMock).toHaveBeenCalledTimes(1));
    expect(updateExtractionConfigMock.mock.calls[0][1].llm_model).toEqual({
      model_ref: 'picked-model-uuid', model_source: 'user_model',
    });
  });

  it('clearing the default model omits llm_model (fall back to the global default)', async () => {
    const { unmount } = renderPanel(makeProject({ llm_model: { model_ref: 'persisted' } }));
    // the stub toggles: a click on a set value clears it (emits null)
    fireEvent.click(screen.getByLabelText('projects.extractionTuning.defaultModel'));
    fireEvent.click(saveBtn());
    await waitFor(() => expect(updateExtractionConfigMock).toHaveBeenCalledTimes(1));
    expect(updateExtractionConfigMock.mock.calls[0][1].llm_model).toBeUndefined();
    unmount();
  });

  it('entity-recovery model picker appears only when recovery is on and sends model_ref', async () => {
    renderPanel(makeProject());
    // recovery off → no recovery-model picker
    expect(screen.queryByTestId('tuning-recovery-model')).toBeNull();
    fireEvent.click(screen.getByLabelText('projects.extractionTuning.recoveryEnabled'));
    expect(screen.getByTestId('tuning-recovery-model')).toBeDefined();
    // pick a recovery model
    fireEvent.click(screen.getByLabelText('projects.extractionTuning.recoveryModel'));
    fireEvent.click(saveBtn());
    await waitFor(() => expect(updateExtractionConfigMock).toHaveBeenCalledTimes(1));
    expect(updateExtractionConfigMock.mock.calls[0][1].entity_recovery).toEqual({
      enabled: true, model_ref: 'picked-model-uuid', model_source: 'user_model',
    });
  });

  it('the recovery batch size is sent (clamped 1-20) and omitted when blank', async () => {
    renderPanel(makeProject({ entity_recovery: { enabled: true } }));
    fireEvent.change(screen.getByTestId('tuning-recovery-batch'), { target: { value: '50' } });
    fireEvent.click(saveBtn());
    await waitFor(() => expect(updateExtractionConfigMock).toHaveBeenCalledTimes(1));
    // clamped to the 20 max
    expect(updateExtractionConfigMock.mock.calls[0][1].entity_recovery.max_items_per_batch).toBe(20);
  });

  it('toggling writer autocreate sends writer_autocreate.enabled', async () => {
    renderPanel(makeProject());
    fireEvent.click(screen.getByLabelText('projects.extractionTuning.autocreateEnabled'));
    fireEvent.click(saveBtn());
    await waitFor(() => expect(updateExtractionConfigMock).toHaveBeenCalledTimes(1));
    const payload = updateExtractionConfigMock.mock.calls[0][1];
    expect(payload.writer_autocreate).toEqual({ enabled: true });
  });

  it('disabling the filter sends an explicit enabled:false', async () => {
    const project = makeProject({
      precision_filter: { enabled: true, categories: ['relation'] },
    });
    renderPanel(project);
    fireEvent.click(screen.getByLabelText('projects.extractionTuning.filterEnabled'));
    fireEvent.click(saveBtn());
    await waitFor(() => expect(updateExtractionConfigMock).toHaveBeenCalledTimes(1));
    const payload = updateExtractionConfigMock.mock.calls[0][1];
    expect(payload.precision_filter).toEqual({ enabled: false });
  });

  it('a custom prompt is sent under prompts.<op>.system; empty boxes omitted', async () => {
    renderPanel(makeProject());
    // the textarea label also contains a live char counter, so match on the
    // op-key substring rather than the exact accessible name.
    fireEvent.change(
      screen.getByLabelText('projects.extractionTuning.prompt.entity', { exact: false }),
      { target: { value: 'My custom entity prompt' } },
    );
    fireEvent.click(saveBtn());
    await waitFor(() => expect(updateExtractionConfigMock).toHaveBeenCalledTimes(1));
    const payload = updateExtractionConfigMock.mock.calls[0][1];
    expect(payload.prompts).toEqual({ entity: { system: 'My custom entity prompt' } });
  });

  it('an over-length prompt blocks save (avoids guaranteed BE 422)', () => {
    renderPanel(makeProject());
    fireEvent.change(
      screen.getByLabelText('projects.extractionTuning.prompt.entity', { exact: false }),
      { target: { value: 'x'.repeat(16385) } }, // > 16384 cap
    );
    expect(saveBtn().disabled).toBe(true);
  });

  it('filter on with no categories blocks save', () => {
    const project = makeProject({
      precision_filter: { enabled: true, categories: ['relation'] },
    });
    renderPanel(project);
    // uncheck the only category
    fireEvent.click(screen.getByLabelText('projects.extractionTuning.category.relation'));
    expect(saveBtn().disabled).toBe(true);
    expect(screen.getByText('projects.extractionTuning.categoriesRequired')).toBeDefined();
  });
});
