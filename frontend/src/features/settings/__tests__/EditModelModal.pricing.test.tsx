import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// D-PRICING-REFRESH — until this fix, a user who registered a paid model
// (e.g. gpt-4o) with a stale/wrong pre-filled rate had NO way to correct it:
// patchUserModel had no pricing field, and no UI showed the numeric rate at
// all. These tests prove: the price is shown, editable, saved via patch
// (merged with any pre-existing dims the UI doesn't expose), rejects a
// negative value client-side, and the "Check OpenRouter" suggestion flow
// fills the fields on Apply without auto-saving anything.

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok-test', user: { user_id: 'u1' } }),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

const patchUserModelMock = vi.fn().mockResolvedValue({});
const putUserModelTagsMock = vi.fn().mockResolvedValue({});
const suggestPricingMock = vi.fn();
vi.mock('../api', async (orig) => {
  const actual = await orig<typeof import('../api')>();
  return {
    ...actual,
    providerApi: {
      ...actual.providerApi,
      patchUserModel: (...a: unknown[]) => patchUserModelMock(...a),
      putUserModelTags: (...a: unknown[]) => putUserModelTagsMock(...a),
      suggestPricing: (...a: unknown[]) => suggestPricingMock(...a),
    },
  };
});

import { EditModelModal } from '../EditModelModal';
import { toast } from 'sonner';

const PAID_MODEL = {
  user_model_id: 'm1',
  provider_credential_id: 'pc1',
  provider_kind: 'openai',
  provider_model_name: 'gpt-4o',
  context_length: 128000,
  alias: 'My GPT-4o',
  is_active: true,
  is_favorite: false,
  capability_flags: { chat: true },
  pricing: { input_per_mtok: 2.5, output_per_mtok: 10 },
  tags: [],
  notes: '',
} as never;

const LOCAL_MODEL = {
  ...PAID_MODEL,
  user_model_id: 'm2',
  provider_kind: 'lm_studio',
  pricing: { input_per_mtok: 0, output_per_mtok: 0 },
} as never;

describe('EditModelModal pricing (D-PRICING-REFRESH)', () => {
  beforeEach(() => {
    patchUserModelMock.mockClear();
    putUserModelTagsMock.mockClear();
    suggestPricingMock.mockReset();
  });

  it('renders the existing pricing as editable numeric fields', () => {
    render(<EditModelModal model={PAID_MODEL} onClose={() => {}} onUpdated={() => {}} />);
    expect(screen.getByDisplayValue('2.5')).toBeInTheDocument();
    expect(screen.getByDisplayValue('10')).toBeInTheDocument();
  });

  it('shows a free/local message instead of price inputs for a local BYOK kind', () => {
    render(<EditModelModal model={LOCAL_MODEL} onClose={() => {}} onUpdated={() => {}} />);
    expect(screen.getByText('model_modal.edit.pricing_free_local')).toBeInTheDocument();
    expect(screen.queryByDisplayValue('0')).toBeNull();
  });

  it('saves an edited price via patchUserModel, preserving pricing dims the UI does not expose', async () => {
    const modelWithExtraDim = {
      ...PAID_MODEL,
      pricing: { input_per_mtok: 2.5, output_per_mtok: 10, per_image: 0.04 },
    } as never;
    render(<EditModelModal model={modelWithExtraDim} onClose={() => {}} onUpdated={() => {}} />);
    fireEvent.change(screen.getByDisplayValue('2.5'), { target: { value: '3' } });
    fireEvent.click(screen.getByRole('button', { name: 'model_modal.edit.submit' }));

    await waitFor(() => expect(patchUserModelMock).toHaveBeenCalled());
    const payload = patchUserModelMock.mock.calls[0][2];
    expect(payload.pricing).toEqual({ input_per_mtok: 3, output_per_mtok: 10, per_image: 0.04 });
  });

  it('rejects a negative price client-side without calling patchUserModel', async () => {
    render(<EditModelModal model={PAID_MODEL} onClose={() => {}} onUpdated={() => {}} />);
    fireEvent.change(screen.getByDisplayValue('2.5'), { target: { value: '-1' } });
    fireEvent.click(screen.getByRole('button', { name: 'model_modal.edit.submit' }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('model_modal.edit.pricing_negative_error'));
    expect(patchUserModelMock).not.toHaveBeenCalled();
  });

  it('omits pricing from the patch payload for a local kind', async () => {
    render(<EditModelModal model={LOCAL_MODEL} onClose={() => {}} onUpdated={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: 'model_modal.edit.submit' }));

    await waitFor(() => expect(patchUserModelMock).toHaveBeenCalled());
    const payload = patchUserModelMock.mock.calls[0][2];
    expect(payload.pricing).toBeUndefined();
  });

  it('shows a found OpenRouter suggestion and applies it to the fields on click', async () => {
    suggestPricingMock.mockResolvedValue({
      found: true,
      source_model_id: 'openai/gpt-4o',
      pricing: { input_per_mtok: 2.5, output_per_mtok: 10 },
    });
    render(<EditModelModal model={{ ...PAID_MODEL, pricing: { input_per_mtok: 1, output_per_mtok: 4 } } as never} onClose={() => {}} onUpdated={() => {}} />);

    fireEvent.click(screen.getByRole('button', { name: /pricing_check/ }));
    await waitFor(() => expect(suggestPricingMock).toHaveBeenCalledWith('tok-test', 'm1'));
    await waitFor(() => expect(screen.getByText(/pricing_suggestion_found/)).toBeInTheDocument());

    // Suggestion is shown, NOT auto-applied — the stale values are still in the fields.
    expect(screen.getByDisplayValue('1')).toBeInTheDocument();
    expect(screen.getByDisplayValue('4')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'model_modal.edit.pricing_apply' }));
    expect(screen.getByDisplayValue('2.5')).toBeInTheDocument();
    expect(screen.getByDisplayValue('10')).toBeInTheDocument();
    // Applying only fills the form — it must NOT call patchUserModel itself.
    expect(patchUserModelMock).not.toHaveBeenCalled();
  });

  it('shows a not-found toast when OpenRouter has no matching model', async () => {
    suggestPricingMock.mockResolvedValue({ found: false });
    render(<EditModelModal model={PAID_MODEL} onClose={() => {}} onUpdated={() => {}} />);

    fireEvent.click(screen.getByRole('button', { name: /pricing_check/ }));
    await waitFor(() => expect(toast.info).toHaveBeenCalledWith('model_modal.edit.pricing_not_found'));
    expect(screen.queryByText(/pricing_suggestion_found/)).toBeNull();
  });
});
