// REG-P5-01 — the subagent-persona authoring GUI. EFFECT assertions (not "file exists"):
// create sends the parsed scope + surfaces a backend error verbatim; toggle/delete call
// the api; a System row is read-only.
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'test-token' }) }));

const api = vi.hoisted(() => ({
  listSubagents: vi.fn(),
  createSubagent: vi.fn(),
  patchSubagent: vi.fn(),
  deleteSubagent: vi.fn(),
}));
vi.mock('@/features/extensions/api', () => ({ extensionsApi: api }));

import { SubagentsView } from '../SubagentsView';

const row = (o: Partial<Record<string, unknown>> = {}) => ({
  subagent_id: 's1', tier: 'user', name: 'lore-scout', description: '', system_prompt: 'scout',
  tool_scope: ['glossary_*', 'kg_*'], model_ref: '', enabled: true,
  created_at: '', updated_at: '', ...o,
});

beforeEach(() => {
  Object.values(api).forEach((f) => (f as ReturnType<typeof vi.fn>).mockReset());
  api.listSubagents.mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 });
});

describe('SubagentsView', () => {
  it('creates a persona, parsing the comma scope into globs', async () => {
    api.createSubagent.mockResolvedValue({});
    render(<SubagentsView />);
    await waitFor(() => expect(screen.getByTestId('sa-name')).toBeTruthy());
    fireEvent.change(screen.getByTestId('sa-name'), { target: { value: 'lore-scout' } });
    fireEvent.change(screen.getByTestId('sa-scope'), { target: { value: 'glossary_*, kg_*' } });
    fireEvent.change(screen.getByTestId('sa-prompt'), { target: { value: 'You scout the lore.' } });
    fireEvent.click(screen.getByTestId('sa-create'));
    await waitFor(() => expect(api.createSubagent).toHaveBeenCalled());
    expect(api.createSubagent.mock.calls[0][1]).toMatchObject({
      name: 'lore-scout',
      system_prompt: 'You scout the lore.',
      tool_scope: ['glossary_*', 'kg_*'],
    });
  });

  it('omits model_ref when blank, sends it (trimmed) when filled', async () => {
    api.createSubagent.mockResolvedValue({});
    render(<SubagentsView />);
    await waitFor(() => expect(screen.getByTestId('sa-name')).toBeTruthy());
    fireEvent.change(screen.getByTestId('sa-name'), { target: { value: 'a' } });
    fireEvent.change(screen.getByTestId('sa-prompt'), { target: { value: 'p' } });
    fireEvent.click(screen.getByTestId('sa-create'));
    await waitFor(() => expect(api.createSubagent).toHaveBeenCalled());
    // blank model → undefined (not '') so the backend default applies
    expect(api.createSubagent.mock.calls[0][1].model_ref).toBeUndefined();

    api.createSubagent.mockClear();
    fireEvent.change(screen.getByTestId('sa-name'), { target: { value: 'b' } });
    fireEvent.change(screen.getByTestId('sa-prompt'), { target: { value: 'p' } });
    fireEvent.change(screen.getByTestId('sa-model'), { target: { value: '  m-uuid  ' } });
    fireEvent.click(screen.getByTestId('sa-create'));
    await waitFor(() => expect(api.createSubagent).toHaveBeenCalled());
    expect(api.createSubagent.mock.calls[0][1].model_ref).toBe('m-uuid');
  });

  it('scope parsing drops blanks / trailing commas / stray whitespace', async () => {
    api.createSubagent.mockResolvedValue({});
    render(<SubagentsView />);
    await waitFor(() => expect(screen.getByTestId('sa-name')).toBeTruthy());
    fireEvent.change(screen.getByTestId('sa-name'), { target: { value: 'a' } });
    fireEvent.change(screen.getByTestId('sa-prompt'), { target: { value: 'p' } });
    fireEvent.change(screen.getByTestId('sa-scope'), { target: { value: ' glossary_* , , kg_*,  ' } });
    fireEvent.click(screen.getByTestId('sa-create'));
    await waitFor(() => expect(api.createSubagent).toHaveBeenCalled());
    expect(api.createSubagent.mock.calls[0][1].tool_scope).toEqual(['glossary_*', 'kg_*']);
  });

  it('create button is disabled without a name + system prompt', async () => {
    render(<SubagentsView />);
    await waitFor(() => expect(screen.getByTestId('sa-create')).toBeTruthy());
    expect((screen.getByTestId('sa-create') as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByTestId('sa-name'), { target: { value: 'x' } });
    expect((screen.getByTestId('sa-create') as HTMLButtonElement).disabled).toBe(true); // still need a prompt
    fireEvent.change(screen.getByTestId('sa-prompt'), { target: { value: 'p' } });
    expect((screen.getByTestId('sa-create') as HTMLButtonElement).disabled).toBe(false);
  });

  it('surfaces a backend error verbatim (no silent no-op)', async () => {
    api.createSubagent.mockRejectedValue(new Error("you already have a subagent named 'lore-scout'"));
    render(<SubagentsView />);
    await waitFor(() => expect(screen.getByTestId('sa-name')).toBeTruthy());
    fireEvent.change(screen.getByTestId('sa-name'), { target: { value: 'lore-scout' } });
    fireEvent.change(screen.getByTestId('sa-prompt'), { target: { value: 'p' } });
    fireEvent.click(screen.getByTestId('sa-create'));
    await waitFor(() => expect(screen.getByTestId('sa-error')).toBeTruthy());
    expect(screen.getByTestId('sa-error').textContent).toContain('already have a subagent');
  });

  it('renders scope chips + toggle patches enabled; delete removes', async () => {
    api.listSubagents.mockResolvedValue({ items: [row()], total: 1, limit: 50, offset: 0 });
    api.patchSubagent.mockResolvedValue({});
    api.deleteSubagent.mockResolvedValue(undefined);
    render(<SubagentsView />);
    await waitFor(() => expect(screen.getByTestId('sa-row')).toBeTruthy());
    expect(screen.getAllByTestId('sa-scope-chip').map((c) => c.textContent)).toEqual(['glossary_*', 'kg_*']);
    fireEvent.click(screen.getByTestId('sa-toggle'));
    await waitFor(() => expect(api.patchSubagent).toHaveBeenCalledWith('test-token', 's1', { enabled: false }));
    fireEvent.click(screen.getByTestId('sa-delete'));
    await waitFor(() => expect(api.deleteSubagent).toHaveBeenCalledWith('test-token', 's1'));
  });

  it('a System-tier persona is read-only (no delete button)', async () => {
    api.listSubagents.mockResolvedValue({ items: [row({ tier: 'system', name: 'system-scout' })], total: 1, limit: 50, offset: 0 });
    render(<SubagentsView />);
    await waitFor(() => expect(screen.getByTestId('sa-row')).toBeTruthy());
    expect(screen.queryByTestId('sa-delete')).toBeNull();
  });

  it('an empty scope renders the reasoning-only badge', async () => {
    api.listSubagents.mockResolvedValue({ items: [row({ tool_scope: [] })], total: 1, limit: 50, offset: 0 });
    render(<SubagentsView />);
    await waitFor(() => expect(screen.getByTestId('sa-row')).toBeTruthy());
    expect(screen.getByTestId('sa-row').textContent).toContain('reasoning-only');
  });
});
