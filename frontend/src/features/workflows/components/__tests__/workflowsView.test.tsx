// S-12 — WorkflowsView: list + per-user enable/disable + delete (own). System rows are
// read-only (no delete) but still toggleable per-user (SD-1). Effect tests through the
// real useWorkflowManage → api boundary.
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'test-token' }) }));

const api = vi.hoisted(() => ({
  list: vi.fn(),
  setEnabled: vi.fn(),
  remove: vi.fn(),
}));
vi.mock('@/features/workflows/api', () => ({ workflowsApi: api }));

import { WorkflowsView } from '../WorkflowsView';

const wf = (over: Record<string, unknown> = {}) => ({
  workflow_id: 'w1', slug: 'setup-world', title: 'Set up my world', description: 'a recipe',
  tier: 'user', status: 'published', enabled: true, ...over,
});

beforeEach(() => {
  Object.values(api).forEach((f) => (f as ReturnType<typeof vi.fn>).mockReset());
  api.list.mockResolvedValue({ workflows: [] });
});

describe('WorkflowsView (S-12)', () => {
  it('shows the empty state', async () => {
    render(<WorkflowsView />);
    await waitFor(() => expect(screen.getByTestId('workflows-empty')).toBeTruthy());
  });

  it('toggle → setEnabled(id, !enabled)', async () => {
    api.list.mockResolvedValue({ workflows: [wf({ enabled: true })] });
    api.setEnabled.mockResolvedValue(undefined);
    render(<WorkflowsView />);
    await waitFor(() => expect(screen.getByTestId('workflow-row')).toBeTruthy());
    fireEvent.click(screen.getByTestId('workflow-toggle'));
    await waitFor(() => expect(api.setEnabled).toHaveBeenCalledWith('test-token', 'w1', false));
  });

  it('delete → remove(id) for an OWN workflow', async () => {
    api.list.mockResolvedValue({ workflows: [wf()] });
    api.remove.mockResolvedValue(undefined);
    render(<WorkflowsView />);
    await waitFor(() => expect(screen.getByTestId('workflow-row')).toBeTruthy());
    fireEvent.click(screen.getByTestId('workflow-delete'));
    await waitFor(() => expect(api.remove).toHaveBeenCalledWith('test-token', 'w1'));
  });

  it('a System workflow is read-only (no delete) but still toggleable', async () => {
    api.list.mockResolvedValue({ workflows: [wf({ workflow_id: 'sys1', tier: 'system' })] });
    render(<WorkflowsView />);
    await waitFor(() => expect(screen.getByTestId('workflow-row')).toBeTruthy());
    expect(screen.queryByTestId('workflow-delete')).toBeNull();     // no delete for System
    expect(screen.getByTestId('workflow-toggle')).toBeTruthy();     // but per-user toggle stays
  });
});
