// REG-P5-04 — the plugins/bundle FE (import + export + list).
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'test-token' }) }));

const api = vi.hoisted(() => ({
  listPlugins: vi.fn(),
  deletePlugin: vi.fn(),
  exportBundle: vi.fn(),
  importBundle: vi.fn(),
}));
vi.mock('@/features/extensions/api', () => ({ extensionsApi: api }));

import { PluginsView } from '../PluginsView';

const plugin = (over = {}) => ({ plugin_id: 'p1', tier: 'user', name: 'io.me/pack', version: '1.0.0', description: 'x', status: 'active', created_at: '', updated_at: '', ...over });

beforeEach(() => {
  Object.values(api).forEach((f) => (f as ReturnType<typeof vi.fn>).mockReset());
  api.listPlugins.mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 });
});

describe('PluginsView', () => {
  it('shows the empty state + an Import button', async () => {
    render(<PluginsView />);
    await waitFor(() => expect(screen.getByTestId('plugins-empty')).toBeTruthy());
    expect(screen.getByTestId('plugin-import-btn')).toBeTruthy();
  });

  it('lists a plugin with Export + Delete', async () => {
    api.listPlugins.mockResolvedValue({ items: [plugin()], total: 1, limit: 50, offset: 0 });
    render(<PluginsView />);
    await waitFor(() => expect(screen.getByTestId('plugin-row')).toBeTruthy());
    expect(screen.getByTestId('plugin-export')).toBeTruthy();
  });

  it('importing a valid bundle file calls the API', async () => {
    api.importBundle.mockResolvedValue({ plugin_id: 'p2', name: 'io.me/x', imported: {} });
    render(<PluginsView />);
    await waitFor(() => expect(screen.getByTestId('plugin-import-file')).toBeTruthy());
    const file = new File([JSON.stringify({ manifest: { name: 'io.me/x', version: '1.0.0' }, skills: [] })], 'b.json', { type: 'application/json' });
    fireEvent.change(screen.getByTestId('plugin-import-file'), { target: { files: [file] } });
    await waitFor(() => expect(api.importBundle).toHaveBeenCalled());
    expect(api.importBundle.mock.calls[0][1]).toMatchObject({ manifest: { name: 'io.me/x' } });
  });

  it('rejects a non-bundle file with an inline error (no API call)', async () => {
    render(<PluginsView />);
    await waitFor(() => expect(screen.getByTestId('plugin-import-file')).toBeTruthy());
    const file = new File([JSON.stringify({ nope: true })], 'x.json', { type: 'application/json' });
    fireEvent.change(screen.getByTestId('plugin-import-file'), { target: { files: [file] } });
    await waitFor(() => expect(screen.getByTestId('plugin-import-error')).toBeTruthy());
    expect(api.importBundle).not.toHaveBeenCalled();
  });
});
