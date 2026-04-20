import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok-test' }),
}));

const updateEmbeddingModelMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    knowledgeApi: {
      updateEmbeddingModel: (...args: unknown[]) => updateEmbeddingModelMock(...args),
    },
  };
});

// Stub the picker to a simple select so tests can drive value changes
// without loading benchmark-status.
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
      <option value="text-embedding-3-small">text-embedding-3-small</option>
    </select>
  ),
}));

const toastErrorMock = vi.fn();
const toastInfoMock = vi.fn();
vi.mock('sonner', () => ({
  toast: {
    error: (...args: unknown[]) => toastErrorMock(...args),
    info: (...args: unknown[]) => toastInfoMock(...args),
  },
}));

import { ChangeModelDialog } from '../ChangeModelDialog';
import type { Project } from '../../types';

const sampleProject: Project = {
  project_id: 'p1',
  user_id: 'u1',
  name: 'Test',
  description: '',
  project_type: 'book',
  instructions: '',
  book_id: 'b1',
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
  created_at: '2026-04-19T00:00:00Z',
  updated_at: '2026-04-19T00:00:00Z',
};

function renderDialog(onOpenChange = vi.fn(), onChanged = vi.fn(), project = sampleProject, open = true) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={qc}>
      <ChangeModelDialog
        open={open}
        onOpenChange={onOpenChange}
        project={project}
        onChanged={onChanged}
      />
    </QueryClientProvider>,
  );
  return { ...utils, onOpenChange, onChanged };
}

describe('ChangeModelDialog', () => {
  beforeEach(() => {
    updateEmbeddingModelMock.mockReset();
    toastErrorMock.mockReset();
    toastInfoMock.mockReset();
  });

  it('renders title + warning when open', () => {
    renderDialog();
    expect(screen.getByText('projects.changeModelDialog.title')).toBeDefined();
    expect(screen.getByText('projects.changeModelDialog.warningTitle')).toBeDefined();
  });

  it('does not render when closed', () => {
    renderDialog(vi.fn(), vi.fn(), sampleProject, false);
    expect(screen.queryByText('projects.changeModelDialog.title')).toBeNull();
  });

  it('Confirm disabled when selected model equals current', () => {
    renderDialog();
    const confirm = screen.getByRole('button', {
      name: 'projects.changeModelDialog.confirm',
    }) as HTMLButtonElement;
    // Initial selection mirrors project.embedding_model (bge-m3).
    expect(confirm.disabled).toBe(true);
    expect(screen.getByText('projects.changeModelDialog.sameModel')).toBeDefined();
  });

  it('Confirm enabled after picking a different model', () => {
    renderDialog();
    fireEvent.change(screen.getByTestId('embedding-picker'), {
      target: { value: 'text-embedding-3-small' },
    });
    const confirm = screen.getByRole('button', {
      name: 'projects.changeModelDialog.confirm',
    }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(false);
  });

  it('calls updateEmbeddingModel with confirm=true on Confirm', async () => {
    updateEmbeddingModelMock.mockResolvedValue({
      project_id: 'p1',
      previous_model: 'bge-m3',
      new_model: 'text-embedding-3-small',
      nodes_deleted: 42,
      extraction_status: 'disabled',
    });
    const { onChanged, onOpenChange } = renderDialog();
    fireEvent.change(screen.getByTestId('embedding-picker'), {
      target: { value: 'text-embedding-3-small' },
    });
    await act(async () => {
      fireEvent.click(
        screen.getByRole('button', { name: 'projects.changeModelDialog.confirm' }),
      );
    });
    await waitFor(() => {
      expect(updateEmbeddingModelMock).toHaveBeenCalledWith(
        'p1',
        'text-embedding-3-small',
        'tok-test',
        { confirm: true },
      );
    });
    expect(onChanged).toHaveBeenCalledTimes(1);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('toasts on update failure and keeps dialog open', async () => {
    updateEmbeddingModelMock.mockRejectedValue(
      Object.assign(new Error('Conflict'), {
        status: 409,
        body: { detail: { message: 'cannot change while job active' } },
      }),
    );
    const { onChanged, onOpenChange } = renderDialog();
    fireEvent.change(screen.getByTestId('embedding-picker'), {
      target: { value: 'text-embedding-3-small' },
    });
    await act(async () => {
      fireEvent.click(
        screen.getByRole('button', { name: 'projects.changeModelDialog.confirm' }),
      );
    });
    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalled();
    });
    expect(onChanged).not.toHaveBeenCalled();
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });

  it('Cancel closes the dialog', () => {
    const { onOpenChange } = renderDialog();
    fireEvent.click(
      screen.getByRole('button', { name: 'projects.changeModelDialog.cancel' }),
    );
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  // review-impl F2 — BE same-model guard runs BEFORE the confirm gate.
  // If another device switched the model to our `selected` value between
  // open and Confirm, BE returns `{message, current_model}` even with
  // confirm=true. FE must NOT treat that as a real change.
  it('handles no-op response (message + current_model) without firing onChanged', async () => {
    updateEmbeddingModelMock.mockResolvedValue({
      message: 'model unchanged',
      current_model: 'text-embedding-3-small',
    });
    const { onChanged, onOpenChange } = renderDialog();
    fireEvent.change(screen.getByTestId('embedding-picker'), {
      target: { value: 'text-embedding-3-small' },
    });
    await act(async () => {
      fireEvent.click(
        screen.getByRole('button', { name: 'projects.changeModelDialog.confirm' }),
      );
    });
    await waitFor(() => {
      expect(updateEmbeddingModelMock).toHaveBeenCalled();
    });
    expect(toastInfoMock).toHaveBeenCalled();
    expect(onChanged).not.toHaveBeenCalled();
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });
});
