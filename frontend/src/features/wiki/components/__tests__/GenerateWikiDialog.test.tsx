import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

vi.mock('react-i18next', () => ({
  // interpolating stub so estimate assertions can read the {{count}}/{{total}} args
  useTranslation: () => ({
    t: (k: string, o?: Record<string, unknown>) => (o ? `${k}:${JSON.stringify(o)}` : k),
  }),
}));
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

// W5 — the model pickers are now the shared ModelPicker, which also imports
// getUserModelMeta from this module: spread the actual module and only
// override the API surface.
const listUserModels = vi.fn();
vi.mock('@/features/ai-models/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/ai-models/api')>();
  return {
    ...actual,
    aiModelsApi: { listUserModels: (...a: unknown[]) => listUserModels(...a), patchFavorite: vi.fn() },
  };
});
// ModelPicker persists recents via syncPrefs — stub the server round-trip.
vi.mock('@/lib/syncPrefs', () => ({
  loadPrefFromServer: vi.fn().mockResolvedValue(undefined),
  savePrefToServer: vi.fn().mockResolvedValue(true),
  syncPrefsToServer: vi.fn(),
}));
const getKinds = vi.fn();
vi.mock('@/features/glossary/api', () => ({
  glossaryApi: { getKinds: (...a: unknown[]) => getKinds(...a) },
}));
const getGenConfig = vi.fn();
vi.mock('../../api', () => ({
  wikiApi: { getGenConfig: (...a: unknown[]) => getGenConfig(...a) },
}));
const getBook = vi.fn();
vi.mock('@/features/books/api', () => ({
  booksApi: { getBook: (...a: unknown[]) => getBook(...a) },
}));
const listProjects = vi.fn();
vi.mock('@/features/knowledge/api', () => ({
  knowledgeApi: { listProjects: (...a: unknown[]) => listProjects(...a) },
}));
const getGuardrail = vi.fn();
vi.mock('@/features/usage/api', () => ({
  usageApi: { getGuardrail: (...a: unknown[]) => getGuardrail(...a) },
}));

import { GenerateWikiDialog } from '../GenerateWikiDialog';
import { invalidateUserModelsCache } from '@/components/model-picker';

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(ui, { wrapper: Wrapper });
}

// W5 — the pickers are the shared ModelPicker (combobox trigger + listbox).
// The trigger only renders once the models fetch resolves (loading skeleton
// before that), so `findByRole` doubles as the readiness wait.
function pickerTrigger(testId: string) {
  return within(screen.getByTestId(testId)).findByRole('combobox');
}
async function pickModel(testId: string, name: string | RegExp = /Gemma/) {
  fireEvent.click(await pickerTrigger(testId));
  fireEvent.click(await screen.findByRole('option', { name }));
}

// W3 — switch the batch dialog into AI mode (the model picker only renders here).
async function toAiMode() {
  fireEvent.click(screen.getByTestId('wiki-gen-mode-llm'));
  await pickerTrigger('wiki-gen-model');
}

beforeEach(() => {
  vi.clearAllMocks();
  // W5 — flush the shared fetch's module-level cache + recents cache.
  invalidateUserModelsCache();
  localStorage.clear();
  listUserModels.mockResolvedValue({
    items: [
      { user_model_id: 'm1', provider_kind: 'lm_studio', provider_model_name: 'gemma', alias: 'Gemma', is_active: true, is_favorite: false, tags: [], created_at: '' },
    ],
  });
  getKinds.mockResolvedValue([{ kind_id: 'k1', code: 'character', name: 'Character', icon: '🧍', color: '#abc' }]);
  getGenConfig.mockResolvedValue({ cost_per_article_usd: '0.05' });
  // W6a — advisory-context reads (lazy-gated; default to a sensible loaded state).
  getBook.mockResolvedValue({ book_id: 'b1', original_language: 'en' });
  listProjects.mockResolvedValue({ items: [{ project_id: 'p1' }] });
  getGuardrail.mockResolvedValue({
    daily_limit_usd: 1, monthly_limit_usd: 10, daily_spent_usd: 0, monthly_spent_usd: 3,
    reserved_usd: 0, daily_available_usd: 1, monthly_available_usd: 7,
  });
});

describe('GenerateWikiDialog', () => {
  it('renders nothing when closed', () => {
    const { container } = wrap(
      <GenerateWikiDialog open={false} onClose={() => {}} onTrigger={vi.fn()} busy={false} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('defaults to the deterministic-stub mode (toggle on stub, no model picker)', async () => {
    wrap(<GenerateWikiDialog open onClose={() => {}} onTrigger={vi.fn()} busy={false} />);
    await waitFor(() => expect(screen.getByTestId('wiki-gen-mode-stub')).toBeTruthy());
    // stub segment selected, no model picker, no spend cap, stub confirm label
    expect(screen.getByTestId('wiki-gen-mode-stub').getAttribute('aria-checked')).toBe('true');
    expect(screen.queryByTestId('wiki-gen-model')).toBeNull();
    expect(screen.queryByTestId('wiki-gen-maxspend')).toBeNull();
    expect(screen.getByTestId('wiki-gen-confirm').textContent).toContain('gen.confirmStub');
  });

  it('stub mode triggers a deterministic run (no model_ref)', async () => {
    const onTrigger = vi.fn().mockResolvedValue({ job_id: 'j1', status: 'pending' });
    const onClose = vi.fn();
    wrap(<GenerateWikiDialog open onClose={onClose} onTrigger={onTrigger} busy={false} />);
    await waitFor(() => expect(screen.getByTestId('wiki-gen-mode-stub')).toBeTruthy());
    fireEvent.click(screen.getByTestId('wiki-gen-confirm'));
    await waitFor(() => expect(onTrigger).toHaveBeenCalledWith({}));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it('stub mode passes selected kind_codes (deterministic generation by kind)', async () => {
    const onTrigger = vi.fn().mockResolvedValue({ job_id: 'j1', status: 'pending' });
    wrap(<GenerateWikiDialog open onClose={() => {}} onTrigger={onTrigger} busy={false} />);
    // kind chips load from getKinds and render in batch mode (both modes)
    const chip = await screen.findByRole('button', { name: /Character/ });
    fireEvent.click(chip);
    fireEvent.click(screen.getByTestId('wiki-gen-confirm'));
    // stub mode → no model_ref, but the kind filter still scopes the run
    await waitFor(() => expect(onTrigger).toHaveBeenCalledWith({ kind_codes: ['character'] }));
  });

  it('AI mode with no model picked keeps confirm disabled', async () => {
    const onTrigger = vi.fn();
    wrap(<GenerateWikiDialog open onClose={() => {}} onTrigger={onTrigger} busy={false} />);
    await waitFor(() => expect(screen.getByTestId('wiki-gen-mode-llm')).toBeTruthy());
    await toAiMode();
    // picker present but nothing selected → confirm disabled, AI confirm label
    expect(await pickerTrigger('wiki-gen-model')).toHaveTextContent('gen.model.pickRequired');
    expect((screen.getByTestId('wiki-gen-confirm') as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByTestId('wiki-gen-confirm').textContent).toContain('gen.confirmLlm');
    fireEvent.click(screen.getByTestId('wiki-gen-confirm'));
    expect(onTrigger).not.toHaveBeenCalled();
  });

  it('AI mode + model reveals the spend cap and triggers with model_ref', async () => {
    const onTrigger = vi.fn().mockResolvedValue({ job_id: 'j1', status: 'pending' });
    const onClose = vi.fn();
    wrap(<GenerateWikiDialog open onClose={onClose} onTrigger={onTrigger} busy={false} />);
    await waitFor(() => expect(screen.getByTestId('wiki-gen-mode-llm')).toBeTruthy());
    await toAiMode();

    await pickModel('wiki-gen-model');
    expect(screen.getByTestId('wiki-gen-confirm').textContent).toContain('gen.confirmLlm');
    expect(screen.getByTestId('wiki-gen-maxspend')).toBeTruthy();

    fireEvent.change(screen.getByTestId('wiki-gen-maxspend'), { target: { value: '2.50' } });
    fireEvent.click(screen.getByTestId('wiki-gen-confirm'));
    await waitFor(() =>
      expect(onTrigger).toHaveBeenCalledWith({ model_ref: 'm1', max_spend_usd: 2.5 }),
    );
    await waitFor(() => expect(onClose).toHaveBeenCalled()); // closes on success
  });

  it('switching AI → stub clears the picked model + spend (no token-spend leak)', async () => {
    const onTrigger = vi.fn().mockResolvedValue({ job_id: 'j1', status: 'pending' });
    wrap(<GenerateWikiDialog open onClose={() => {}} onTrigger={onTrigger} busy={false} />);
    await waitFor(() => expect(screen.getByTestId('wiki-gen-mode-llm')).toBeTruthy());
    await toAiMode();
    await pickModel('wiki-gen-model');
    fireEvent.change(screen.getByTestId('wiki-gen-maxspend'), { target: { value: '5.00' } });
    // back to stub — picker + spend gone, and a confirm runs deterministic
    fireEvent.click(screen.getByTestId('wiki-gen-mode-stub'));
    expect(screen.queryByTestId('wiki-gen-model')).toBeNull();
    expect(screen.queryByTestId('wiki-gen-maxspend')).toBeNull();
    fireEvent.click(screen.getByTestId('wiki-gen-confirm'));
    await waitFor(() => expect(onTrigger).toHaveBeenCalledWith({}));
  });

  it('resets to the stub default when reopened (/review-impl F1)', async () => {
    const { rerender } = wrap(
      <GenerateWikiDialog open onClose={() => {}} onTrigger={vi.fn()} busy={false} />,
    );
    await waitFor(() => expect(screen.getByTestId('wiki-gen-mode-llm')).toBeTruthy());
    await toAiMode();
    await pickModel('wiki-gen-model');
    expect(await pickerTrigger('wiki-gen-model')).toHaveTextContent('Gemma');
    // close then reopen — the dialog stays mounted, so without the reset the
    // AI selection would persist
    rerender(<GenerateWikiDialog open={false} onClose={() => {}} onTrigger={vi.fn()} busy={false} />);
    rerender(<GenerateWikiDialog open onClose={() => {}} onTrigger={vi.fn()} busy={false} />);
    await waitFor(() =>
      expect(screen.getByTestId('wiki-gen-mode-stub').getAttribute('aria-checked')).toBe('true'),
    );
    expect(screen.queryByTestId('wiki-gen-model')).toBeNull(); // back to deterministic
  });

  it('regen mode has no toggle, requires a model, triggers with entity_ids', async () => {
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
    await pickerTrigger('wiki-gen-model');
    // regen is always AI — no mode toggle, picker shown directly
    expect(screen.queryByTestId('wiki-gen-mode-stub')).toBeNull();
    // no model picked yet → confirm disabled (deterministic regen would be a no-op)
    expect((screen.getByTestId('wiki-gen-confirm') as HTMLButtonElement).disabled).toBe(true);
    // no selection yet — the trigger shows the pick-required placeholder
    expect(await pickerTrigger('wiki-gen-model')).toHaveTextContent('gen.model.pickRequired');

    await pickModel('wiki-gen-model');
    fireEvent.click(screen.getByTestId('wiki-gen-confirm'));
    await waitFor(() =>
      expect(onTrigger).toHaveBeenCalledWith({ model_ref: 'm1', entity_ids: ['e-42'] }),
    );
  });

  it('shows a precise N × rate estimate in regen mode (D-WIKI-P2B-COST-ESTIMATE)', async () => {
    wrap(
      <GenerateWikiDialog
        open
        onClose={() => {}}
        onTrigger={vi.fn()}
        busy={false}
        bookId="b1"
        entityIds={['e1', 'e2', 'e3']}
        regenName="Dracula"
      />,
    );
    await pickerTrigger('wiki-gen-model');
    await pickModel('wiki-gen-model');
    // 3 entities × $0.05 ≈ $0.15
    await waitFor(() => {
      const txt = screen.getByTestId('wiki-gen-estimate').textContent || '';
      expect(txt).toContain('gen.estimate.forN');
      expect(txt).toContain('"count":3');
      expect(txt).toContain('"total":"$0.15"');
    });
    expect(getGenConfig).toHaveBeenCalledWith('b1', 'tok');
  });

  it('shows a per-article rate estimate in batch AI mode (count unknown pre-flight)', async () => {
    wrap(<GenerateWikiDialog open onClose={() => {}} onTrigger={vi.fn()} busy={false} bookId="b1" />);
    await waitFor(() => expect(screen.getByTestId('wiki-gen-mode-llm')).toBeTruthy());
    await toAiMode();
    await waitFor(() => {
      const txt = screen.getByTestId('wiki-gen-estimate').textContent || '';
      expect(txt).toContain('gen.estimate.perArticle');
      expect(txt).toContain('"perArticle":"$0.05"');
    });
  });

  it('shows no estimate in the deterministic (stub) mode', async () => {
    wrap(<GenerateWikiDialog open onClose={() => {}} onTrigger={vi.fn()} busy={false} bookId="b1" />);
    await waitFor(() => expect(screen.getByTestId('wiki-gen-mode-stub')).toBeTruthy());
    expect(screen.queryByTestId('wiki-gen-estimate')).toBeNull();
    expect(getGenConfig).not.toHaveBeenCalled();
  });

  it('forwards an optional revise model only when chosen (W5)', async () => {
    const onTrigger = vi.fn().mockResolvedValue({ job_id: 'j1', status: 'pending' });
    wrap(<GenerateWikiDialog open onClose={() => {}} onTrigger={onTrigger} busy={false} />);
    await waitFor(() => expect(screen.getByTestId('wiki-gen-mode-llm')).toBeTruthy());
    await toAiMode();
    await pickModel('wiki-gen-model');
    // the revise picker defaults to "same as generation" (None) → no override sent
    expect(await pickerTrigger('wiki-gen-revise-model')).toHaveTextContent('gen.reviseModel.same');
    await pickModel('wiki-gen-revise-model');
    fireEvent.click(screen.getByTestId('wiki-gen-confirm'));
    await waitFor(() =>
      expect(onTrigger).toHaveBeenCalledWith({ model_ref: 'm1', revise_model_ref: 'm1' }),
    );
  });

  it('regen mode forwards a revise model alongside entity_ids (W5)', async () => {
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
    // regen shows both pickers directly (always AI, no toggle)
    await pickerTrigger('wiki-gen-model');
    await pickModel('wiki-gen-model');
    await pickModel('wiki-gen-revise-model');
    fireEvent.click(screen.getByTestId('wiki-gen-confirm'));
    await waitFor(() =>
      expect(onTrigger).toHaveBeenCalledWith({ model_ref: 'm1', entity_ids: ['e-42'], revise_model_ref: 'm1' }),
    );
  });

  it('omits the revise model when left at "same as generation"', async () => {
    const onTrigger = vi.fn().mockResolvedValue({ job_id: 'j1', status: 'pending' });
    wrap(<GenerateWikiDialog open onClose={() => {}} onTrigger={onTrigger} busy={false} />);
    await waitFor(() => expect(screen.getByTestId('wiki-gen-mode-llm')).toBeTruthy());
    await toAiMode();
    await pickModel('wiki-gen-model');
    fireEvent.click(screen.getByTestId('wiki-gen-confirm'));
    await waitFor(() => expect(onTrigger).toHaveBeenCalledWith({ model_ref: 'm1' }));
  });

  it('hides the revise picker in stub mode', async () => {
    wrap(<GenerateWikiDialog open onClose={() => {}} onTrigger={vi.fn()} busy={false} />);
    await waitFor(() => expect(screen.getByTestId('wiki-gen-mode-stub')).toBeTruthy());
    expect(screen.queryByTestId('wiki-gen-revise-model')).toBeNull();
  });

  it('blocks confirm on an invalid spend cap', async () => {
    const onTrigger = vi.fn();
    wrap(<GenerateWikiDialog open onClose={() => {}} onTrigger={onTrigger} busy={false} />);
    await waitFor(() => expect(screen.getByTestId('wiki-gen-mode-llm')).toBeTruthy());
    await toAiMode();
    await pickModel('wiki-gen-model');
    fireEvent.change(screen.getByTestId('wiki-gen-maxspend'), { target: { value: 'abc' } });
    expect((screen.getByTestId('wiki-gen-confirm') as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByTestId('wiki-gen-confirm'));
    expect(onTrigger).not.toHaveBeenCalled();
  });

  // ── W6a: advisory context lines (language / grounding / budget) ──────────────

  it('shows the book language line (advisory) when a book is loaded', async () => {
    wrap(<GenerateWikiDialog open onClose={() => {}} onTrigger={vi.fn()} busy={false} bookId="b1" />);
    await waitFor(() =>
      expect(screen.getByTestId('wiki-gen-language').textContent).toContain('gen.context.language'),
    );
    expect(screen.getByTestId('wiki-gen-language').textContent).toContain('"lang":"en"');
  });

  it('shows the grounding-status + budget lines in AI mode', async () => {
    wrap(<GenerateWikiDialog open onClose={() => {}} onTrigger={vi.fn()} busy={false} bookId="b1" />);
    // stub default ⇒ AI-only lines hidden
    expect(screen.queryByTestId('wiki-gen-indexed')).toBeNull();
    expect(screen.queryByTestId('wiki-gen-budget')).toBeNull();
    await toAiMode();
    await waitFor(() => expect(screen.getByTestId('wiki-gen-indexed').textContent).toContain('gen.context.indexed'));
    await waitFor(() => {
      const txt = screen.getByTestId('wiki-gen-budget').textContent || '';
      expect(txt).toContain('gen.context.budget');
      expect(txt).toContain('"used":"$3.00"');
      expect(txt).toContain('"limit":"$10.00"');
    });
  });

  it('flags a not-indexed book in AI mode', async () => {
    listProjects.mockResolvedValue({ items: [] }); // no knowledge project → not indexed
    wrap(<GenerateWikiDialog open onClose={() => {}} onTrigger={vi.fn()} busy={false} bookId="b1" />);
    await toAiMode();
    await waitFor(() =>
      expect(screen.getByTestId('wiki-gen-indexed').textContent).toContain('gen.context.notIndexed'),
    );
  });
});
