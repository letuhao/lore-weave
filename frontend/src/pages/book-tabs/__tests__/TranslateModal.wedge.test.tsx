// Spec 29 Phase A — T5/D7/D8: the modal must never wedge on "Loading chapters…". The
// language/model pickers render immediately (they need no big fetch); only the chapter
// checklist is network-bound, and a rejecting OR hanging chapter fetch recovers into an inline
// typed error + Retry. D7: seeding a language must not clobber a choice the user already made.
// D8: with a preselection, submit stays enabled even if the chapter list fails.
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));

const toastError = vi.fn();
vi.mock('sonner', () => ({ toast: { error: (...a: unknown[]) => toastError(...a), success: vi.fn() } }));

const listChapters = vi.fn();
vi.mock('@/features/books/api', () => ({ booksApi: { listChapters: (...a: unknown[]) => listChapters(...a) } }));

const createJob = vi.fn().mockResolvedValue({});
const putBookSettings = vi.fn().mockResolvedValue({});
const getBookSettings = vi.fn();
const getBookCoverage = vi.fn();
vi.mock('@/features/translation/api', () => ({
  translationApi: {
    getBookSettings: (...a: unknown[]) => getBookSettings(...a),
    putBookSettings: (...a: unknown[]) => putBookSettings(...a),
    getBookCoverage: (...a: unknown[]) => getBookCoverage(...a),
    createJob: (...a: unknown[]) => createJob(...a),
  },
}));
vi.mock('@/features/ai-models/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/ai-models/api')>();
  return {
    ...actual,
    aiModelsApi: {
      listUserModels: vi.fn().mockResolvedValue({
        items: [{
          user_model_id: 'm1', provider_credential_id: 'cred-1', provider_kind: 'lm_studio',
          provider_model_name: 'qwen3', alias: 'Qwen3', is_active: true, is_favorite: false,
          capability_flags: {}, tags: [], created_at: '2026-01-01T00:00:00Z',
        }],
      }),
      patchFavorite: vi.fn(),
    },
  };
});
vi.mock('@/lib/syncPrefs', () => ({
  loadPrefFromServer: vi.fn().mockResolvedValue(undefined),
  savePrefToServer: vi.fn().mockResolvedValue(true),
  syncPrefsToServer: vi.fn(),
}));

import { invalidateUserModelsCache } from '@/components/model-picker';
import { TranslateModal } from '../TranslateModal';

const baseProps = { open: true, onClose: vi.fn(), bookId: 'bk1', onJobCreated: vi.fn() };
const httpError = (status: number) => Object.assign(new Error('proxy leak'), { status });

/** A promise you resolve/reject manually — for controlling load ordering. */
function deferred<T>() {
  let resolve!: (v: T) => void, reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

const settingsFixture = {
  book_id: 'bk1', target_language: 'vi', model_source: 'user_model', model_ref: 'm1',
  system_prompt: '', user_prompt_tpl: '', is_default: false,
};

beforeEach(() => {
  toastError.mockClear(); createJob.mockClear(); putBookSettings.mockClear();
  localStorage.clear(); invalidateUserModelsCache();
  listChapters.mockReset();
  listChapters.mockResolvedValue({ items: [{ chapter_id: 'ch1', title: 'Chapter 1', sort_order: 0 }], total: 1 });
  getBookSettings.mockResolvedValue(settingsFixture);
  getBookCoverage.mockResolvedValue({ book_id: 'bk1', coverage: [], known_languages: ['vi'] });
});

describe('TranslateModal — T5 no wedge', () => {
  it('renders the language picker immediately while the chapter list is still loading', async () => {
    // chapters never resolve within the test → the checklist stays loading, but the pickers must show
    listChapters.mockReturnValue(new Promise(() => {}));
    render(<TranslateModal {...baseProps} />);
    // the target-language select is present even though the checklist has not loaded
    await waitFor(() => expect(screen.getAllByRole('combobox').length).toBeGreaterThan(0));
    expect(screen.getByTestId('translate-chapters-loading')).toBeInTheDocument();
  });

  it('recovers a failed chapter fetch into a typed error + Retry (not a permanent spinner)', async () => {
    listChapters.mockRejectedValue(httpError(503));
    render(<TranslateModal {...baseProps} />);
    const box = await screen.findByTestId('translation-error');
    expect(box.getAttribute('data-kind')).toBe('retryable');
    expect(screen.getByTestId('translation-error-retry')).toBeInTheDocument();
    // Retry re-runs the fetch — make the next attempt succeed
    listChapters.mockResolvedValue({ items: [{ chapter_id: 'ch1', title: 'Chapter 1', sort_order: 0 }], total: 1 });
    fireEvent.click(screen.getByTestId('translation-error-retry'));
    expect(await screen.findByText('Chapter 1')).toBeInTheDocument();
  });
});

describe('TranslateModal — D7 seed does not clobber a user choice', () => {
  it('keeps a language the user picked before getBookSettings resolves', async () => {
    const d = deferred<typeof settingsFixture>();
    getBookSettings.mockReturnValue(d.promise);
    render(<TranslateModal {...baseProps} />);
    // the select renders before settings resolve; user picks Japanese
    const langSelect = (await screen.findAllByRole('combobox'))[0];
    fireEvent.change(langSelect, { target: { value: 'ja' } });
    // settings resolve LATE with vi — must NOT overwrite the user's ja
    d.resolve(settingsFixture);
    await waitFor(() => expect(putBookSettings).toHaveBeenCalled());
    expect((langSelect as HTMLSelectElement).value).toBe('ja');
  });
});

describe('TranslateModal — D8 submit survives a failed chapter list', () => {
  it('keeps submit enabled for a preselection when the chapter fetch fails', async () => {
    listChapters.mockRejectedValue(httpError(503));
    render(<TranslateModal {...baseProps} preselectedChapterIds={['ch1', 'ch2']} />);
    // the checklist errored, but the pickers seeded lang+model from settings and the selection
    // was seeded from the preselection → submit is enabled
    await screen.findByTestId('translation-error');
    const submit = await screen.findByRole('button', { name: 'translate.submit_selected' });
    await waitFor(() => expect(submit).not.toBeDisabled());
  });
});
