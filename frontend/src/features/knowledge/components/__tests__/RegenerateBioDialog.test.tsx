import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

vi.mock('@/auth', () => ({
  useAuth: () => ({
    accessToken: 'tok-test',
    user: {
      user_id: 'u1',
      email: 'a@b',
      display_name: null,
      avatar_url: null,
    },
  }),
}));

// vi.mock factory is hoisted above top-level declarations, so
// `toastMocks` must be hoisted too — otherwise it's in the temporal
// dead zone when the factory runs. `vi.hoisted` is the supported
// vitest escape hatch.
const toastMocks = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
}));
vi.mock('sonner', () => ({
  toast: toastMocks,
}));

const listUserModelsMock = vi.fn();
vi.mock('@/features/ai-models/api', () => ({
  aiModelsApi: {
    listUserModels: (...args: unknown[]) => listUserModelsMock(...args),
  },
}));

const regenerateGlobalBioMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    knowledgeApi: {
      regenerateGlobalBio: (...args: unknown[]) =>
        regenerateGlobalBioMock(...args),
    },
  };
});

import { RegenerateBioDialog } from '../RegenerateBioDialog';

function Wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function renderOpen() {
  const onOpenChange = vi.fn();
  const result = render(
    <RegenerateBioDialog open={true} onOpenChange={onOpenChange} />,
    { wrapper: Wrapper },
  );
  return { ...result, onOpenChange };
}

describe('RegenerateBioDialog', () => {
  beforeEach(() => {
    regenerateGlobalBioMock.mockReset();
    listUserModelsMock.mockReset();
    toastMocks.success.mockReset();
    toastMocks.error.mockReset();
    toastMocks.info.mockReset();
    listUserModelsMock.mockResolvedValue({
      items: [
        {
          user_model_id: 'm1',
          provider_kind: 'openai',
          provider_model_name: 'gpt-4o-mini',
          alias: 'Mini',
        },
      ],
    });
  });

  async function pickModelAndConfirm() {
    await screen.findByRole('option', { name: /gpt-4o-mini/i });
    fireEvent.change(await screen.findByTestId('regenerate-bio-model'), {
      target: { value: 'gpt-4o-mini' },
    });
    fireEvent.click(screen.getByTestId('regenerate-bio-confirm'));
  }

  it('disables submit until a model is selected', async () => {
    const { onOpenChange } = renderOpen();
    const confirm = await screen.findByTestId('regenerate-bio-confirm');
    expect(confirm).toBeDisabled();

    await waitFor(() => {
      expect(listUserModelsMock).toHaveBeenCalledTimes(1);
    });
    const select = await screen.findByTestId('regenerate-bio-model');
    // Wait for the chat-model option to render after the query resolves
    // — the select renders immediately but is empty until modelsQuery
    // settles. Without this wait, fireEvent.change() below races the
    // options and the state never flips.
    await screen.findByRole('option', { name: /gpt-4o-mini/i });
    fireEvent.change(select, { target: { value: 'gpt-4o-mini' } });
    expect(confirm).not.toBeDisabled();
    expect(onOpenChange).not.toHaveBeenCalled();
  });

  it('calls regen API with selected model on confirm and closes on success', async () => {
    regenerateGlobalBioMock.mockResolvedValue({
      status: 'regenerated',
      summary: {
        summary_id: 's1',
        user_id: 'u1',
        scope_type: 'global',
        scope_id: null,
        content: 'new',
        token_count: 3,
        version: 2,
        created_at: '2026-04-22T00:00:00Z',
        updated_at: '2026-04-22T00:00:00Z',
      },
      skipped_reason: null,
    });
    const { onOpenChange } = renderOpen();
    const select = await screen.findByTestId('regenerate-bio-model');
    // Wait for the chat-model option to render after the query resolves
    // — the select renders immediately but is empty until modelsQuery
    // settles. Without this wait, fireEvent.change() below races the
    // options and the state never flips.
    await screen.findByRole('option', { name: /gpt-4o-mini/i });
    fireEvent.change(select, { target: { value: 'gpt-4o-mini' } });
    fireEvent.click(screen.getByTestId('regenerate-bio-confirm'));

    await waitFor(() => {
      expect(regenerateGlobalBioMock).toHaveBeenCalledWith(
        { model_source: 'user_model', model_ref: 'gpt-4o-mini' },
        'tok-test',
      );
    });
    await waitFor(() => {
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });

  it('renders inline edit-lock banner on 409 user_edit_lock without closing', async () => {
    regenerateGlobalBioMock.mockRejectedValue(
      Object.assign(new Error('locked'), {
        status: 409,
        body: {
          detail: {
            error_code: 'user_edit_lock',
            message: 'Protected by manual edit on 2026-04-21',
          },
        },
      }),
    );
    const { onOpenChange } = renderOpen();
    const select = await screen.findByTestId('regenerate-bio-model');
    // Wait for the chat-model option to render after the query resolves
    // — the select renders immediately but is empty until modelsQuery
    // settles. Without this wait, fireEvent.change() below races the
    // options and the state never flips.
    await screen.findByRole('option', { name: /gpt-4o-mini/i });
    fireEvent.change(select, { target: { value: 'gpt-4o-mini' } });
    fireEvent.click(screen.getByTestId('regenerate-bio-confirm'));

    const banner = await screen.findByTestId('regenerate-bio-edit-lock');
    expect(banner.textContent).toContain('2026-04-21');
    // Dialog stays open so the user can read the banner.
    expect(onOpenChange).not.toHaveBeenCalled();
  });

  it('shows "no models" hint when listUserModels returns empty', async () => {
    listUserModelsMock.mockResolvedValue({ items: [] });
    renderOpen();
    // Wait for the query to resolve; the hint uses a translation
    // key that the global test mock resolves to the key itself.
    await screen.findByText('global.regenerate.noModels');
  });

  it('toasts error + closes on 409 regen_concurrent_edit', async () => {
    regenerateGlobalBioMock.mockRejectedValue(
      Object.assign(new Error('race'), {
        status: 409,
        body: { detail: { error_code: 'regen_concurrent_edit' } },
      }),
    );
    const { onOpenChange } = renderOpen();
    await pickModelAndConfirm();
    await waitFor(() => {
      expect(toastMocks.error).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });

  it('toasts error on 422 regen_guardrail_failed and stays open', async () => {
    regenerateGlobalBioMock.mockRejectedValue(
      Object.assign(new Error('guardrail'), {
        status: 422,
        body: {
          detail: {
            error_code: 'regen_guardrail_failed',
            message: 'token_overflow',
          },
        },
      }),
    );
    const { onOpenChange } = renderOpen();
    await pickModelAndConfirm();
    await waitFor(() => {
      expect(toastMocks.error).toHaveBeenCalledTimes(1);
    });
    // Guardrail failure stays open — unlike 409 concurrent which
    // auto-closes, guardrail gives the user a chance to pick a
    // different model and retry.
    expect(onOpenChange).not.toHaveBeenCalled();
  });

  it('toasts provider error on 502', async () => {
    regenerateGlobalBioMock.mockRejectedValue(
      Object.assign(new Error('provider'), {
        status: 502,
        body: {
          detail: {
            error_code: 'provider_error',
            message: 'upstream 500',
          },
        },
      }),
    );
    renderOpen();
    await pickModelAndConfirm();
    await waitFor(() => {
      expect(toastMocks.error).toHaveBeenCalledTimes(1);
    });
  });

  it('info-toasts on 200 no_op_similarity and closes', async () => {
    regenerateGlobalBioMock.mockResolvedValue({
      status: 'no_op_similarity',
      summary: null,
      skipped_reason: 'identical',
    });
    const { onOpenChange } = renderOpen();
    await pickModelAndConfirm();
    await waitFor(() => {
      expect(toastMocks.info).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });
});
