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

  it('PUT-replace read-modify-write preserves unmanaged keys (llm_model)', async () => {
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
    // unmanaged llm_model preserved verbatim
    expect(payload.llm_model).toEqual({ model_ref: 'keep-me-uuid' });
    // filter preserved + recovery toggled on
    expect(payload.precision_filter.categories).toEqual(['relation']);
    expect(payload.entity_recovery.enabled).toBe(true);
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
