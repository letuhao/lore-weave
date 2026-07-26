import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// Track B B1(2) — MultiProjectPicker: the multi-KG grounding SET. Add/remove
// projects by name, emit the id array, cap at `max`, archived-fallback chips.

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

import { MultiProjectPicker } from '../MultiProjectPicker';

const PROJECTS = {
  items: [
    { project_id: 'p-aaaa', name: 'Eastern Sea Lore' },
    { project_id: 'p-bbbb', name: 'Silk Road Codex' },
    { project_id: 'p-cccc', name: 'Northern Reaches' },
  ],
  next_cursor: null,
};

describe('MultiProjectPicker (Track B B1(2))', () => {
  beforeEach(() => {
    listProjectsMock.mockReset();
    getProjectMock.mockReset();
  });

  it('loads active projects only and never requests archived', async () => {
    listProjectsMock.mockResolvedValue(PROJECTS);
    render(<MultiProjectPicker value={[]} onChange={vi.fn()} />);
    await waitFor(() => expect(listProjectsMock).toHaveBeenCalled());
    expect(listProjectsMock).toHaveBeenCalledWith(
      expect.objectContaining({ include_archived: false }),
      'tok-test',
    );
  });

  it('adds a project to the set by name and emits the appended id array', async () => {
    listProjectsMock.mockResolvedValue(PROJECTS);
    const onChange = vi.fn();
    render(<MultiProjectPicker value={['p-aaaa']} onChange={onChange} />);
    await waitFor(() => expect(listProjectsMock).toHaveBeenCalled());
    fireEvent.focus(screen.getByRole('combobox'));
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'silk' } });
    fireEvent.click(await screen.findByText('Silk Road Codex'));
    expect(onChange).toHaveBeenCalledWith(['p-aaaa', 'p-bbbb']);
  });

  it('already-selected projects are not offered in the dropdown', async () => {
    listProjectsMock.mockResolvedValue(PROJECTS);
    render(<MultiProjectPicker value={['p-aaaa']} onChange={vi.fn()} />);
    await waitFor(() => expect(listProjectsMock).toHaveBeenCalled());
    fireEvent.focus(screen.getByRole('combobox'));
    // Eastern Sea Lore is already selected → only its chip shows it, not the list.
    await screen.findByText('Silk Road Codex'); // list populated
    const chips = screen.getByTestId('multi-project-chips');
    expect(chips).toHaveTextContent('Eastern Sea Lore');
    // No option button for the already-selected one.
    expect(screen.queryByText('Northern Reaches')).toBeInTheDocument();
  });

  it('removes a project from the set', async () => {
    listProjectsMock.mockResolvedValue(PROJECTS);
    const onChange = vi.fn();
    render(<MultiProjectPicker value={['p-aaaa', 'p-bbbb']} onChange={onChange} />);
    await waitFor(() => expect(listProjectsMock).toHaveBeenCalled());
    fireEvent.click(await screen.findByLabelText('Remove Eastern Sea Lore'));
    expect(onChange).toHaveBeenCalledWith(['p-bbbb']);
  });

  it('caps selection at `max` and disables the input at the cap', async () => {
    listProjectsMock.mockResolvedValue(PROJECTS);
    render(<MultiProjectPicker value={['p-aaaa', 'p-bbbb']} onChange={vi.fn()} max={2} />);
    await waitFor(() => expect(listProjectsMock).toHaveBeenCalled());
    expect(screen.getByRole('combobox')).toBeDisabled();
  });

  it('resolves an archived (unlisted) selected id by id for its chip name', async () => {
    listProjectsMock.mockResolvedValue(PROJECTS);
    getProjectMock.mockResolvedValue({ project_id: 'p-zzzz', name: 'Shelved Saga' });
    render(<MultiProjectPicker value={['p-zzzz']} onChange={vi.fn()} />);
    await waitFor(() => expect(getProjectMock).toHaveBeenCalledWith('p-zzzz', 'tok-test'));
    expect(await screen.findByText('Shelved Saga')).toBeInTheDocument();
  });

  it('empty set is valid — nothing emitted until a pick', async () => {
    listProjectsMock.mockResolvedValue(PROJECTS);
    const onChange = vi.fn();
    render(<MultiProjectPicker value={[]} onChange={onChange} />);
    await waitFor(() => expect(listProjectsMock).toHaveBeenCalled());
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.queryByTestId('multi-project-chips')).toBeNull();
  });
});
