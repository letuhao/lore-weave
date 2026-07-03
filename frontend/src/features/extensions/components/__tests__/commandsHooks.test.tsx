// REG-P4-02/04 — the command + hook builder UIs.
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'test-token' }) }));

const api = vi.hoisted(() => ({
  listCommands: vi.fn(),
  createCommand: vi.fn(),
  patchCommand: vi.fn(),
  deleteCommand: vi.fn(),
  listHooks: vi.fn(),
  createHook: vi.fn(),
  patchHook: vi.fn(),
  deleteHook: vi.fn(),
}));
vi.mock('@/features/extensions/api', () => ({ extensionsApi: api }));

import { CommandsHooksView } from '../CommandsHooksView';

beforeEach(() => {
  Object.values(api).forEach((f) => (f as ReturnType<typeof vi.fn>).mockReset());
  api.listCommands.mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 });
  api.listHooks.mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 });
});

describe('CommandsHooksView', () => {
  it('renders both builder sections', async () => {
    render(<CommandsHooksView />);
    await waitFor(() => expect(screen.getByTestId('commands-section')).toBeTruthy());
    expect(screen.getByTestId('hooks-section')).toBeTruthy();
  });

  it('creates a slash command with name + template', async () => {
    api.createCommand.mockResolvedValue({});
    render(<CommandsHooksView />);
    await waitFor(() => expect(screen.getByTestId('cmd-name')).toBeTruthy());
    fireEvent.change(screen.getByTestId('cmd-name'), { target: { value: 'plan-scene' } });
    fireEvent.change(screen.getByTestId('cmd-template'), { target: { value: 'Plan {{topic}}' } });
    fireEvent.click(screen.getByTestId('cmd-create'));
    await waitFor(() => expect(api.createCommand).toHaveBeenCalled());
    expect(api.createCommand.mock.calls[0][1]).toMatchObject({ name: 'plan-scene', template_md: 'Plan {{topic}}' });
  });

  it('a deny hook form sends the tool_pattern match + deny action', async () => {
    api.createHook.mockResolvedValue({});
    render(<CommandsHooksView />);
    await waitFor(() => expect(screen.getByTestId('hook-event')).toBeTruthy());
    // default event=pre_tool_call, action=deny → the tool-match input shows
    fireEvent.change(screen.getByTestId('hook-match'), { target: { value: 'glossary_delete_*' } });
    fireEvent.click(screen.getByTestId('hook-create'));
    await waitFor(() => expect(api.createHook).toHaveBeenCalled());
    expect(api.createHook.mock.calls[0][1]).toMatchObject({
      on_event: 'pre_tool_call',
      action: { kind: 'deny' },
      match: { tool_pattern: 'glossary_delete_*' },
    });
  });

  it('an inject_text hook requires + sends the text', async () => {
    api.createHook.mockResolvedValue({});
    render(<CommandsHooksView />);
    await waitFor(() => expect(screen.getByTestId('hook-action')).toBeTruthy());
    fireEvent.change(screen.getByTestId('hook-event'), { target: { value: 'pre_turn' } });
    fireEvent.change(screen.getByTestId('hook-action'), { target: { value: 'inject_text' } });
    fireEvent.change(screen.getByTestId('hook-text'), { target: { value: 'Keep a wry tone.' } });
    fireEvent.click(screen.getByTestId('hook-create'));
    await waitFor(() => expect(api.createHook).toHaveBeenCalled());
    expect(api.createHook.mock.calls[0][1]).toMatchObject({
      on_event: 'pre_turn',
      action: { kind: 'inject_text', text: 'Keep a wry tone.' },
    });
  });
});
