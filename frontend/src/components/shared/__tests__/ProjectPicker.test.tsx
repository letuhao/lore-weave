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

  it('filters out non-matching names', async () => {
    listProjectsMock.mockResolvedValue(PROJECTS);
    render(<ProjectPicker value={null} onChange={vi.fn()} />);
    await waitFor(() => expect(listProjectsMock).toHaveBeenCalled());
    fireEvent.focus(screen.getByRole('combobox'));
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'eastern' } });
    await waitFor(() => expect(screen.queryByText('Silk Road Codex')).toBeNull());
    expect(screen.getByText('Eastern Sea Lore')).toBeInTheDocument();
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
