import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { Project } from '../../types';

// K21-C (D3/D4): ProjectFormModal must round-trip the two new
// memory-tool toggles — tool_calling_enabled + memory_remember_confirm.

const toastMocks = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
}));
vi.mock('sonner', () => ({ toast: toastMocks }));

// The embedding-model picker fetches models on mount — stub it so the
// test stays focused on the toggles.
vi.mock('../EmbeddingModelPicker', () => ({
  EmbeddingModelPicker: () => <div data-testid="embedding-picker-stub" />,
}));
vi.mock('../RerankModelPicker', () => ({
  RerankModelPicker: () => <div data-testid="rerank-picker-stub" />,
}));
// C4: BookPicker fetches the user's books on mount via useAuth/booksApi — stub it
// so this toggles test stays focused (same pattern as the model pickers above).
vi.mock('@/components/shared/BookPicker', () => ({
  BookPicker: () => <div data-testid="book-picker-stub" />,
}));

import { ProjectFormModal } from '../ProjectFormModal';

function projectFixture(overrides: Partial<Project> = {}): Project {
  return {
    project_id: 'p-1',
    user_id: 'u-1',
    name: 'Test Project',
    description: '',
    project_type: 'book',
    book_id: null,
    instructions: '',
    extraction_enabled: true,
    tool_calling_enabled: true,
    memory_remember_confirm: false,
    canon_capture_enabled: false,
    extraction_status: 'ready',
    embedding_model: null,
    embedding_dimension: null,
    extraction_config: {},
    last_extracted_at: null,
    estimated_cost_usd: '0.00',
    actual_cost_usd: '0.00',
    is_archived: false,
    version: 2,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

function renderEdit(project: Project) {
  const onCreate = vi.fn();
  const onUpdate = vi.fn().mockResolvedValue(project);
  render(
    <ProjectFormModal
      open
      onOpenChange={vi.fn()}
      mode="edit"
      project={project}
      onCreate={onCreate}
      onUpdate={onUpdate}
    />,
  );
  return { onCreate, onUpdate };
}

describe('ProjectFormModal — memory-tool toggles', () => {
  beforeEach(() => {
    toastMocks.success.mockReset();
    toastMocks.error.mockReset();
  });

  it('reflects the project values on the toggles when opened in edit mode', () => {
    renderEdit(projectFixture({ tool_calling_enabled: false, memory_remember_confirm: true }));
    expect(screen.getByTestId('project-tool-calling-toggle')).not.toBeChecked();
    expect(screen.getByTestId('project-memory-confirm-toggle')).toBeChecked();
  });

  it('defaults — tool calling on, confirm off — surface for a default project', () => {
    renderEdit(projectFixture());
    expect(screen.getByTestId('project-tool-calling-toggle')).toBeChecked();
    expect(screen.getByTestId('project-memory-confirm-toggle')).not.toBeChecked();
  });

  it('sends both toggle values in the update patch', async () => {
    const { onUpdate } = renderEdit(projectFixture());
    // Flip both toggles: tool calling off→ wait, then on again so the
    // confirm toggle is interactable; here flip confirm on first.
    fireEvent.click(screen.getByTestId('project-memory-confirm-toggle'));
    fireEvent.click(screen.getByText('projects.form.save'));

    await waitFor(() => expect(onUpdate).toHaveBeenCalledTimes(1));
    const [projectId, patch, expectedVersion] = onUpdate.mock.calls[0];
    expect(projectId).toBe('p-1');
    expect(expectedVersion).toBe(2);
    expect(patch).toMatchObject({
      tool_calling_enabled: true,
      memory_remember_confirm: true,
    });
  });

  it('round-trips a flipped tool_calling_enabled value', async () => {
    const { onUpdate } = renderEdit(projectFixture({ tool_calling_enabled: true }));
    fireEvent.click(screen.getByTestId('project-tool-calling-toggle')); // → false
    fireEvent.click(screen.getByText('projects.form.save'));

    await waitFor(() => expect(onUpdate).toHaveBeenCalledTimes(1));
    expect(onUpdate.mock.calls[0][1]).toMatchObject({
      tool_calling_enabled: false,
    });
  });

  it('disables the confirm toggle while tool calling is off', () => {
    renderEdit(projectFixture({ tool_calling_enabled: false }));
    expect(screen.getByTestId('project-memory-confirm-toggle')).toBeDisabled();
  });
});

// WS-4C Half A — canon auto-capture. This toggle IS the user's consent to spend: each
// capture is an extra LLM call on their own model. So it must default OFF, round-trip
// honestly, and be unreachable where it could not work.
// The form only enables Save for an empty or genuinely UUID-shaped book_id
// (`bookIdValid`), so the fixture must carry a real one.
const BOOK_UUID = '019d872f-f3a3-7076-88b8-6c902054860f';

describe('ProjectFormModal — canon auto-capture toggle', () => {
  beforeEach(() => {
    toastMocks.success.mockReset();
    toastMocks.error.mockReset();
  });

  it('is OFF for a default project — capture is opt-in, never opt-out', () => {
    renderEdit(projectFixture({ book_id: BOOK_UUID }));
    expect(screen.getByTestId('project-canon-capture-toggle')).not.toBeChecked();
  });

  it('reflects an opted-in project', () => {
    renderEdit(projectFixture({ book_id: BOOK_UUID, canon_capture_enabled: true }));
    expect(screen.getByTestId('project-canon-capture-toggle')).toBeChecked();
  });

  it('is disabled without a linked book — there is no glossary inbox to capture into', () => {
    renderEdit(projectFixture({ book_id: null }));
    expect(screen.getByTestId('project-canon-capture-toggle')).toBeDisabled();
  });

  it('sends the opt-in through in the update patch', async () => {
    const { onUpdate } = renderEdit(projectFixture({ book_id: BOOK_UUID }));
    fireEvent.click(screen.getByTestId('project-canon-capture-toggle')); // → true
    fireEvent.click(screen.getByText('projects.form.save'));

    await waitFor(() => expect(onUpdate).toHaveBeenCalledTimes(1));
    expect(onUpdate.mock.calls[0][1]).toMatchObject({ canon_capture_enabled: true });
  });

  it('sends the opt-OUT through too — un-checking must actually turn spend off', async () => {
    const { onUpdate } = renderEdit(projectFixture({ book_id: BOOK_UUID, canon_capture_enabled: true }));
    fireEvent.click(screen.getByTestId('project-canon-capture-toggle')); // → false
    fireEvent.click(screen.getByText('projects.form.save'));

    await waitFor(() => expect(onUpdate).toHaveBeenCalledTimes(1));
    expect(onUpdate.mock.calls[0][1]).toMatchObject({ canon_capture_enabled: false });
  });
});
