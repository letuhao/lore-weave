import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// W4 (G2) — ProjectPicker: search projects by name, emit the project_id (UUID),
// empty selection stays valid, optional inline "create new", archived fallback.

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok-test', user: { user_id: 'u1' } }),
}));

const listProjectsMock = vi.fn();
const getProjectMock = vi.fn();
vi.mock('@/features/knowledge/api', () => ({
  knowledgeApi: {
    listProjects: (...a: unknown[]) => listProjectsMock(...a),
    getProject: (...a: unknown[]) => getProjectMock(...a),
  },
}));

import { ProjectPicker } from '../ProjectPicker';

const PROJECTS = {
  items: [
    { project_id: 'p-aaaa', name: 'Eastern Sea Lore' },
    { project_id: 'p-bbbb', name: 'Silk Road Codex' },
  ],
  next_cursor: null,
};

describe('ProjectPicker (W4)', () => {
  beforeEach(() => {
    listProjectsMock.mockReset();
    getProjectMock.mockReset();
  });

  it('loads active projects only and never requests archived', async () => {
    listProjectsMock.mockResolvedValue(PROJECTS);
    render(<ProjectPicker value={null} onChange={vi.fn()} />);
    await waitFor(() => expect(listProjectsMock).toHaveBeenCalled());
    expect(listProjectsMock).toHaveBeenCalledWith(
      expect.objectContaining({ include_archived: false }),
      'tok-test',
    );
  });

  it('searches by name and emits the project_id (not the name)', async () => {
    listProjectsMock.mockResolvedValue(PROJECTS);
    const onChange = vi.fn();
    render(<ProjectPicker value={null} onChange={onChange} />);
    await waitFor(() => expect(listProjectsMock).toHaveBeenCalled());
    const input = screen.getByRole('combobox');
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: 'silk' } });
    const option = await screen.findByText('Silk Road Codex');
    fireEvent.click(option);
    expect(onChange).toHaveBeenCalledWith('p-bbbb');
  });

  it('empty selection is valid — nothing emitted until a pick', async () => {
    listProjectsMock.mockResolvedValue(PROJECTS);
    const onChange = vi.fn();
    render(<ProjectPicker value={null} onChange={onChange} />);
    await waitFor(() => expect(listProjectsMock).toHaveBeenCalled());
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole('combobox')).toBeInTheDocument();
  });

  it('shows the selected name and clears back to null', async () => {
    listProjectsMock.mockResolvedValue(PROJECTS);
    const onChange = vi.fn();
    render(<ProjectPicker value="p-aaaa" onChange={onChange} />);
    await waitFor(() => expect(listProjectsMock).toHaveBeenCalled());
    expect(await screen.findByTestId('project-picker-selected')).toHaveTextContent(
      'Eastern Sea Lore',
    );
    fireEvent.click(screen.getByLabelText('Clear selected project'));
    expect(onChange).toHaveBeenCalledWith(null);
  });

  // ── the name filter is the SERVER'S ──────────────────────────────────────
  //
  // This used to mock `listProjects` to return every project whatever was asked
  // for, and assert that typing hid the non-matches — which only passes while
  // the filtering happens in the browser. That is exactly the shape the picker
  // was fixed away from: it asks for `limit: 200`, the route clamps to 100, and
  // a project past the ceiling was unfindable by name with no symptom.
  //
  // So the mock now behaves like the endpoint, and the assertions below pin the
  // REQUEST as well as the render. A test that only checked the render would go
  // on passing if someone re-added a client-side `.filter()`.
  const serverSideList = (params: { search?: string }) => {
    const q = (params.search ?? '').toLowerCase();
    return Promise.resolve({
      items: q
        ? PROJECTS.items.filter((p) => p.name.toLowerCase().includes(q))
        : PROJECTS.items,
      next_cursor: null,
    });
  };

  it('sends the typed name to the server rather than filtering in the browser', async () => {
    listProjectsMock.mockImplementation((params: { search?: string }) => serverSideList(params));
    render(<ProjectPicker value={null} onChange={vi.fn()} />);
    await waitFor(() => expect(listProjectsMock).toHaveBeenCalled());
    fireEvent.focus(screen.getByRole('combobox'));
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'eastern' } });

    // The REQUEST carried it. Without this the test cannot distinguish a
    // server-side search from a client-side one over a full list.
    await waitFor(() =>
      expect(listProjectsMock).toHaveBeenCalledWith(
        expect.objectContaining({ search: 'eastern' }),
        'tok-test',
      ),
    );
    await waitFor(() => expect(screen.queryByText('Silk Road Codex')).toBeNull());
    expect(screen.getByText('Eastern Sea Lore')).toBeInTheDocument();
  });

  it('renders what the server returned even when it does not contain the typed text', async () => {
    // THE DISCRIMINATING CASE. A client-side `includes()` would hide this row;
    // the server is the authority on what matches, and a real one does things
    // the browser cannot — accent folding, trigram similarity, aliases. If this
    // test goes red, filtering has crept back into the component.
    listProjectsMock.mockResolvedValue({
      items: [{ project_id: 'p-dddd', name: 'Silk Road Codex' }],
      next_cursor: null,
    });
    render(<ProjectPicker value={null} onChange={vi.fn()} />);
    await waitFor(() => expect(listProjectsMock).toHaveBeenCalled());
    fireEvent.focus(screen.getByRole('combobox'));
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'eastern' } });
    // Wait PAST the 180ms debounce. Asserting straight away passed by racing it:
    // a re-added client-side filter had not run yet, so the row was still on
    // screen and the test agreed with the bug. Measured — under a deliberate
    // revert to client-side filtering this assertion stayed green until the wait
    // was added.
    await new Promise((r) => setTimeout(r, 320));
    expect(screen.getByText('Silk Road Codex')).toBeInTheDocument();
  });

  it('an empty box asks for no search at all, rather than searching for ""', async () => {
    listProjectsMock.mockImplementation((params: { search?: string }) => serverSideList(params));
    render(<ProjectPicker value={null} onChange={vi.fn()} />);
    await waitFor(() => expect(listProjectsMock).toHaveBeenCalled());
    expect(listProjectsMock.mock.calls[0][0]).not.toHaveProperty('search');
  });

  it('resolves a linked-but-unlisted (archived) project by id for the chip', async () => {
    listProjectsMock.mockResolvedValue(PROJECTS);
    // p-cccc is NOT in the active list → fallback fetch by id.
    getProjectMock.mockResolvedValue({ project_id: 'p-cccc', name: 'Shelved Saga' });
    render(<ProjectPicker value="p-cccc" onChange={vi.fn()} />);
    await waitFor(() => expect(getProjectMock).toHaveBeenCalledWith('p-cccc', 'tok-test'));
    expect(await screen.findByTestId('project-picker-selected')).toHaveTextContent(
      'Shelved Saga',
    );
  });

  it('renders an inline "create new" row only when onCreateNew is given', async () => {
    listProjectsMock.mockResolvedValue(PROJECTS);
    const onCreateNew = vi.fn();
    render(<ProjectPicker value={null} onChange={vi.fn()} onCreateNew={onCreateNew} />);
    await waitFor(() => expect(listProjectsMock).toHaveBeenCalled());
    fireEvent.focus(screen.getByRole('combobox'));
    const create = await screen.findByText('Create new project');
    fireEvent.click(create);
    expect(onCreateNew).toHaveBeenCalledTimes(1);
  });
});
