// D-KG-NO-CREATE-CTA: the shared "no KG project for this book" empty state — every
// book-scoped kg-* panel's dead-end ("...create a project to manage its graph schema"
// with no button behind it) now has a real create action. Reuses ProjectFormModal AS-IS
// (DOCK-2) with initialBookId locking the picker to this book.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const toastSuccess = vi.fn();
vi.mock('sonner', () => ({
  toast: { success: (...a: unknown[]) => toastSuccess(...a) },
}));

const createProjectApi = vi.fn();
vi.mock('@/features/knowledge/api', () => ({
  knowledgeApi: {
    createProject: (...a: unknown[]) => createProjectApi(...a),
  },
  isVersionConflict: () => false,
}));

import { KgNoProjectState } from '../KgNoProjectState';

function renderWithProviders(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  createProjectApi.mockReset();
  toastSuccess.mockReset();
});

describe('KgNoProjectState', () => {
  it('renders the no-project copy under the caller-supplied testId', () => {
    renderWithProviders(<KgNoProjectState bookId="11111111-1111-1111-1111-111111111111" testId="kg-overview-no-project" />);
    const el = screen.getByTestId('kg-overview-no-project');
    expect(el).toHaveTextContent('page.noProject');
    expect(el).toHaveTextContent('page.noProjectHelp');
  });

  it('opens the create-project form on button click', () => {
    renderWithProviders(<KgNoProjectState bookId="11111111-1111-1111-1111-111111111111" testId="kg-overview-no-project" />);
    fireEvent.click(screen.getByTestId('kg-no-project-create-btn'));
    // The book-picker field is locked (not the free-text BookPicker) — proves
    // initialBookId reached ProjectFormModal instead of leaving book selection open.
    expect(screen.getByTestId('project-form-book-locked')).toBeInTheDocument();
  });

  it('submitting the form creates a project scoped to this book (locked, not the free BookPicker)', async () => {
    createProjectApi.mockResolvedValue({ project_id: 'new-proj', book_id: '11111111-1111-1111-1111-111111111111' });
    renderWithProviders(<KgNoProjectState bookId="11111111-1111-1111-1111-111111111111" testId="kg-overview-no-project" />);
    fireEvent.click(screen.getByTestId('kg-no-project-create-btn'));

    const nameInput = screen.getByPlaceholderText('projects.form.namePlaceholder');
    fireEvent.change(nameInput, { target: { value: 'My Book KG' } });

    const dialog = screen.getByRole('dialog');
    fireEvent.click(within(dialog).getByText('projects.form.create'));

    await waitFor(() => expect(createProjectApi).toHaveBeenCalled());
    const [payload] = createProjectApi.mock.calls[0]!;
    expect(payload).toMatchObject({ name: 'My Book KG', project_type: 'book', book_id: '11111111-1111-1111-1111-111111111111' });
  });
});
