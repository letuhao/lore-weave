import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// #286 / plan 2026-09-19 T14 — "serve one model at a time" in Settings → Providers. It is the
// user's statement about their own hardware, so the UI shows what is stored, sends the field only
// when the user changed it, and never turns it on by itself.

const listProviders = vi.fn();
const patchProvider = vi.fn();
const createProvider = vi.fn();

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('../api', async (orig) => {
  const real = await orig<typeof import('../api')>();
  return {
    ...real,
    providerApi: {
      ...real.providerApi,
      listProviders: (...a: unknown[]) => listProviders(...a),
      listUserModels: vi.fn().mockResolvedValue({ items: [] }),
      patchProvider: (...a: unknown[]) => patchProvider(...a),
      createProvider: (...a: unknown[]) => createProvider(...a),
    },
  };
});
vi.mock('../DefaultModelsCard', () => ({ DefaultModelsCard: () => null }));
vi.mock('../ModelOrderCard', () => ({ ModelOrderCard: () => null }));
vi.mock('../ExternalServicesCard', () => ({ ExternalServicesCard: () => null }));

import { ProvidersTab } from '../ProvidersTab';

const provider = (over: Record<string, unknown> = {}) => ({
  provider_credential_id: 'p1', provider_kind: 'lm_studio', display_name: 'Local GPU',
  endpoint_base_url: 'http://host.docker.internal:1234', status: 'active', has_secret: false,
  api_standard: 'lm_studio', max_concurrency: null, serve_one_model_at_a_time: false,
  created_at: '2026-09-19T00:00:00Z', updated_at: '2026-09-19T00:00:00Z', ...over,
});

async function openEdit() {
  render(<MemoryRouter><ProvidersTab /></MemoryRouter>);
  fireEvent.click(await screen.findByText('providers.edit_key'));
  return screen.getByTestId('provider-edit-one-model') as HTMLInputElement;
}

describe('ProvidersTab — serve one model at a time (#286)', () => {
  beforeEach(() => {
    listProviders.mockReset(); patchProvider.mockReset(); createProvider.mockReset();
    patchProvider.mockResolvedValue(provider());
  });

  it('shows the stored value, and turning it on sends exactly that field', async () => {
    listProviders.mockResolvedValue({ items: [provider()] });
    const box = await openEdit();
    expect(box.checked).toBe(false);
    fireEvent.click(box);
    fireEvent.click(screen.getByText('providers.edit_dialog.submit'));
    await waitFor(() => expect(patchProvider).toHaveBeenCalled());
    expect(patchProvider.mock.calls[0][2]).toEqual({ serve_one_model_at_a_time: true });
  });

  it('an unrelated edit does not send the setting at all', async () => {
    listProviders.mockResolvedValue({ items: [provider({ serve_one_model_at_a_time: true })] });
    const box = await openEdit();
    expect(box.checked, 'the dialog must show what is stored').toBe(true);
    fireEvent.click(screen.getByText('providers.edit_dialog.submit'));
    await waitFor(() => expect(patchProvider).toHaveBeenCalled());
    expect(patchProvider.mock.calls[0][2]).not.toHaveProperty('serve_one_model_at_a_time');
  });

  it('a new provider is created with it OFF unless the user ticks it', async () => {
    listProviders.mockResolvedValue({ items: [] });
    createProvider.mockResolvedValue(provider());
    render(<MemoryRouter><ProvidersTab /></MemoryRouter>);
    fireEvent.click(await screen.findByText('providers.add_provider'));
    expect((screen.getByTestId('provider-add-one-model') as HTMLInputElement).checked).toBe(false);
  });
});
