import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// External Services section — web_search (and future siblings) register as a
// dedicated provider credential + a user_model carrying the capability flag,
// NOT as a tickable model capability. These tests lock the two-step create
// (with orphan rollback) and the card's toggle/delete wiring.

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok-test' }) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

const createProviderMock = vi.fn();
const createUserModelMock = vi.fn();
const deleteProviderMock = vi.fn();
const deleteUserModelMock = vi.fn();
const patchActivationMock = vi.fn();

vi.mock('../api', async (orig) => {
  const actual = await orig<typeof import('../api')>();
  return {
    ...actual,
    providerApi: {
      ...actual.providerApi,
      createProvider: (...a: unknown[]) => createProviderMock(...a),
      createUserModel: (...a: unknown[]) => createUserModelMock(...a),
      deleteProvider: (...a: unknown[]) => deleteProviderMock(...a),
      deleteUserModel: (...a: unknown[]) => deleteUserModelMock(...a),
      patchActivation: (...a: unknown[]) => patchActivationMock(...a),
    },
  };
});

import { AddServiceModal } from '../AddServiceModal';
import { ExternalServicesCard } from '../ExternalServicesCard';

const SERVICE_PROVIDER = {
  provider_credential_id: 'pc1',
  provider_kind: 'web_search',
  display_name: 'My Search',
  endpoint_base_url: 'http://ws:8090',
  status: 'active',
  has_secret: false,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
} as never;

const SERVICE_MODEL = {
  user_model_id: 'um1',
  provider_credential_id: 'pc1',
  provider_kind: 'web_search',
  provider_model_name: 'searxng-default',
  is_active: true,
  is_favorite: false,
  capability_flags: { web_search: true },
  tags: [],
  created_at: '2026-01-01T00:00:00Z',
} as never;

beforeEach(() => {
  createProviderMock.mockReset();
  createUserModelMock.mockReset();
  deleteProviderMock.mockReset();
  deleteUserModelMock.mockReset();
  patchActivationMock.mockReset();
});

describe('AddServiceModal', () => {
  it('creates a web_search credential + model carrying the capability flag', async () => {
    createProviderMock.mockResolvedValue({ provider_credential_id: 'new-cred' });
    createUserModelMock.mockResolvedValue({});
    const onAdded = vi.fn();
    render(<AddServiceModal onClose={() => {}} onAdded={onAdded} />);

    fireEvent.change(screen.getByPlaceholderText('http://local-web-search-service:8090'), {
      target: { value: 'http://ws:8090' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'services.add_dialog.submit' }));

    await waitFor(() => expect(createUserModelMock).toHaveBeenCalled());
    expect(createProviderMock).toHaveBeenCalledWith(
      'tok-test',
      expect.objectContaining({ provider_kind: 'web_search', endpoint_base_url: 'http://ws:8090' }),
    );
    expect(createUserModelMock).toHaveBeenCalledWith(
      'tok-test',
      expect.objectContaining({ provider_credential_id: 'new-cred', capability_flags: { web_search: true } }),
    );
    expect(onAdded).toHaveBeenCalled();
  });

  it('rolls back the orphan credential when the model create fails', async () => {
    createProviderMock.mockResolvedValue({ provider_credential_id: 'orphan' });
    createUserModelMock.mockRejectedValue(new Error('boom'));
    deleteProviderMock.mockResolvedValue(undefined);
    render(<AddServiceModal onClose={() => {}} onAdded={vi.fn()} />);

    fireEvent.change(screen.getByPlaceholderText('http://local-web-search-service:8090'), {
      target: { value: 'http://ws:8090' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'services.add_dialog.submit' }));

    await waitFor(() => expect(deleteProviderMock).toHaveBeenCalledWith('tok-test', 'orphan'));
  });

  it('disables submit until an endpoint is entered', () => {
    render(<AddServiceModal onClose={() => {}} onAdded={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'services.add_dialog.submit' })).toBeDisabled();
  });
});

describe('ExternalServicesCard', () => {
  it('shows the empty state when no services are registered', () => {
    render(<ExternalServicesCard providers={[]} models={[]} onChanged={() => {}} />);
    expect(screen.getByText('services.empty')).toBeInTheDocument();
  });

  it('renders a registered service and toggles its activation', async () => {
    patchActivationMock.mockResolvedValue({});
    const onChanged = vi.fn();
    render(<ExternalServicesCard providers={[SERVICE_PROVIDER]} models={[SERVICE_MODEL]} onChanged={onChanged} />);

    expect(screen.getByText('My Search')).toBeInTheDocument();
    // is_active true → the control offers "deactivate"
    fireEvent.click(screen.getByRole('button', { name: 'services.deactivate_aria' }));
    await waitFor(() => expect(patchActivationMock).toHaveBeenCalledWith('tok-test', 'um1', false));
    expect(onChanged).toHaveBeenCalled();
  });

  it('deletes the model then the credential when removing a service', async () => {
    deleteUserModelMock.mockResolvedValue(undefined);
    deleteProviderMock.mockResolvedValue(undefined);
    const onChanged = vi.fn();
    render(<ExternalServicesCard providers={[SERVICE_PROVIDER]} models={[SERVICE_MODEL]} onChanged={onChanged} />);

    fireEvent.click(screen.getByRole('button', { name: 'services.delete_aria' }));
    await waitFor(() => expect(deleteProviderMock).toHaveBeenCalledWith('tok-test', 'pc1'));
    expect(deleteUserModelMock).toHaveBeenCalledWith('tok-test', 'um1');
    expect(onChanged).toHaveBeenCalled();
  });
});
