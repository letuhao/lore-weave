import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const listUserModels = vi.fn();
vi.mock('@/features/ai-models/api', () => ({
  aiModelsApi: { listUserModels: (...a: unknown[]) => listUserModels(...a) },
}));
const getKinds = vi.fn();
vi.mock('@/features/glossary/api', () => ({
  glossaryApi: { getKinds: (...a: unknown[]) => getKinds(...a) },
}));

import { GenerateWikiDialog } from '../GenerateWikiDialog';

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(ui, { wrapper: Wrapper });
}

beforeEach(() => {
  vi.clearAllMocks();
  listUserModels.mockResolvedValue({
    items: [
      { user_model_id: 'm1', provider_kind: 'lm_studio', provider_model_name: 'gemma', alias: 'Gemma', is_active: true, is_favorite: false, tags: [], created_at: '' },
    ],
  });
  getKinds.mockResolvedValue([{ kind_id: 'k1', code: 'character', name: 'Character', icon: '🧍', color: '#abc' }]);
});

describe('GenerateWikiDialog', () => {
  it('renders nothing when closed', () => {
    const { container } = wrap(
      <GenerateWikiDialog open={false} onClose={() => {}} onTrigger={vi.fn()} busy={false} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('defaults to the deterministic-stub action (no model selected)', async () => {
    wrap(<GenerateWikiDialog open onClose={() => {}} onTrigger={vi.fn()} busy={false} />);
    await waitFor(() => expect(screen.getByTestId('wiki-gen-model')).toBeTruthy());
    // confirm label = stub, no spend cap field
    expect(screen.getByTestId('wiki-gen-confirm').textContent).toContain('gen.confirmStub');
    expect(screen.queryByTestId('wiki-gen-maxspend')).toBeNull();
  });

  it('switching to a model reveals the spend cap and the AI action, and triggers with model_ref', async () => {
    const onTrigger = vi.fn().mockResolvedValue({ job_id: 'j1', status: 'pending' });
    const onClose = vi.fn();
    wrap(<GenerateWikiDialog open onClose={onClose} onTrigger={onTrigger} busy={false} />);
    await waitFor(() => expect(screen.getByRole('option', { name: /Gemma/ })).toBeTruthy());

    fireEvent.change(screen.getByTestId('wiki-gen-model'), { target: { value: 'm1' } });
    expect(screen.getByTestId('wiki-gen-confirm').textContent).toContain('gen.confirmLlm');
    expect(screen.getByTestId('wiki-gen-maxspend')).toBeTruthy();

    fireEvent.change(screen.getByTestId('wiki-gen-maxspend'), { target: { value: '2.50' } });
    fireEvent.click(screen.getByTestId('wiki-gen-confirm'));
    await waitFor(() =>
      expect(onTrigger).toHaveBeenCalledWith({ model_ref: 'm1', max_spend_usd: 2.5 }),
    );
    await waitFor(() => expect(onClose).toHaveBeenCalled()); // closes on success
  });

  it('resets to the deterministic default when reopened (/review-impl F1)', async () => {
    const { rerender } = wrap(
      <GenerateWikiDialog open onClose={() => {}} onTrigger={vi.fn()} busy={false} />,
    );
    await waitFor(() => expect(screen.getByRole('option', { name: /Gemma/ })).toBeTruthy());
    fireEvent.change(screen.getByTestId('wiki-gen-model'), { target: { value: 'm1' } });
    expect((screen.getByTestId('wiki-gen-model') as HTMLSelectElement).value).toBe('m1');
    // close then reopen — the dialog stays mounted, so without the reset the
    // model selection would persist
    rerender(<GenerateWikiDialog open={false} onClose={() => {}} onTrigger={vi.fn()} busy={false} />);
    rerender(<GenerateWikiDialog open onClose={() => {}} onTrigger={vi.fn()} busy={false} />);
    await waitFor(() =>
      expect((screen.getByTestId('wiki-gen-model') as HTMLSelectElement).value).toBe(''),
    );
    expect(screen.queryByTestId('wiki-gen-maxspend')).toBeNull(); // back to deterministic
  });

  it('regen mode requires a model and triggers with entity_ids (not kind_codes)', async () => {
    const onTrigger = vi.fn().mockResolvedValue({ job_id: 'j1', status: 'pending' });
    wrap(
      <GenerateWikiDialog
        open
        onClose={() => {}}
        onTrigger={onTrigger}
        busy={false}
        entityIds={['e-42']}
        regenName="Dracula"
      />,
    );
    await waitFor(() => expect(screen.getByRole('option', { name: /Gemma/ })).toBeTruthy());
    // no model picked yet → confirm disabled (deterministic regen would be a no-op)
    expect((screen.getByTestId('wiki-gen-confirm') as HTMLButtonElement).disabled).toBe(true);
    // the deterministic option is disabled in regen mode
    const deterministic = screen.getByRole('option', { name: 'gen.model.pickRequired' }) as HTMLOptionElement;
    expect(deterministic.disabled).toBe(true);

    fireEvent.change(screen.getByTestId('wiki-gen-model'), { target: { value: 'm1' } });
    fireEvent.click(screen.getByTestId('wiki-gen-confirm'));
    await waitFor(() =>
      expect(onTrigger).toHaveBeenCalledWith({ model_ref: 'm1', entity_ids: ['e-42'] }),
    );
  });

  it('blocks confirm on an invalid spend cap', async () => {
    const onTrigger = vi.fn();
    wrap(<GenerateWikiDialog open onClose={() => {}} onTrigger={onTrigger} busy={false} />);
    // wait for the model OPTION (not just the select) so the value actually sticks
    await waitFor(() => expect(screen.getByRole('option', { name: /Gemma/ })).toBeTruthy());
    fireEvent.change(screen.getByTestId('wiki-gen-model'), { target: { value: 'm1' } });
    fireEvent.change(screen.getByTestId('wiki-gen-maxspend'), { target: { value: 'abc' } });
    expect((screen.getByTestId('wiki-gen-confirm') as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByTestId('wiki-gen-confirm'));
    expect(onTrigger).not.toHaveBeenCalled();
  });
});
