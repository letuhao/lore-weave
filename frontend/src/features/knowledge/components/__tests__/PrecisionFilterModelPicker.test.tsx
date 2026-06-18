import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

// D-WX-PRECISION-FILTER-MODEL-ARCH — the precision-filter model picker: fetches the
// user's chat-capability BYOK models and binds the project's
// precision_filter.model_ref (user_model_id UUID). Empty selection ⇒ null = reuse
// the extraction model (BE fallback). NEVER a hardcoded/env model.

vi.mock('@/auth', () => ({
  useAuth: () => ({
    accessToken: 'tok-test',
    user: { user_id: 'u1', email: 'a@b', display_name: null, avatar_url: null },
  }),
}));

const listUserModelsMock = vi.fn();
vi.mock('@/features/ai-models/api', () => ({
  aiModelsApi: {
    listUserModels: (...args: unknown[]) => listUserModelsMock(...args),
  },
}));

import { PrecisionFilterModelPicker } from '../PrecisionFilterModelPicker';

const CHAT_MODEL = {
  user_model_id: 'fm1',
  provider_kind: 'lm_studio',
  provider_model_name: 'qwen2.5-7b-instruct',
  alias: null,
};

describe('PrecisionFilterModelPicker (D-WX-PRECISION-FILTER-MODEL-ARCH)', () => {
  beforeEach(() => listUserModelsMock.mockReset());

  it('fetches chat-CAPABILITY models and binds the chosen user_model_id', async () => {
    listUserModelsMock.mockResolvedValue({ items: [CHAT_MODEL] });
    const onChange = vi.fn();
    render(<PrecisionFilterModelPicker value={null} onChange={onChange} />);
    await waitFor(() => expect(listUserModelsMock).toHaveBeenCalled());
    // BYOK + capability-scoped — never a hardcoded/env model.
    expect(listUserModelsMock).toHaveBeenCalledWith('tok-test', {
      capability: 'chat',
      include_inactive: false,
    });
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'fm1' } });
    expect(onChange).toHaveBeenCalledWith('fm1');
  });

  it('selecting the default option clears the model (→ reuse extraction model)', async () => {
    listUserModelsMock.mockResolvedValue({ items: [CHAT_MODEL] });
    const onChange = vi.fn();
    render(<PrecisionFilterModelPicker value="fm1" onChange={onChange} />);
    await waitFor(() => expect(listUserModelsMock).toHaveBeenCalled());
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '' } });
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('renders an orphan option when the saved model left the registry', async () => {
    listUserModelsMock.mockResolvedValue({ items: [] });
    render(<PrecisionFilterModelPicker value="gone-uuid" onChange={vi.fn()} />);
    await screen.findByText(/projects\.extractionTuning\.filterModelOrphan/);
  });
});
