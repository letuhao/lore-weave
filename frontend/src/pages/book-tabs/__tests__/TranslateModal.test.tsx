import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// ── Mocks ──────────────────────────────────────────────────────────────────────
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
// DOCK-7 fallback path (openModelSettings navigates when no studio host is present) — the test
// harness renders outside a <Router>, so useNavigate must be stubbed the same way
// TranslationTab.badge.test.tsx already does for its own DOCK-7 fallback.
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));

const toastError = vi.fn();
const toastSuccess = vi.fn();
vi.mock('sonner', () => ({ toast: { error: (...a: unknown[]) => toastError(...a), success: (...a: unknown[]) => toastSuccess(...a) } }));

const listChapters = vi.fn();
vi.mock('@/features/books/api', () => ({
  booksApi: { listChapters: (...a: unknown[]) => listChapters(...a) },
}));

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

// W5 — the model selects are the shared ModelPicker, which also imports
// getUserModelMeta from this module → keep the actual exports around.
vi.mock('@/features/ai-models/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/ai-models/api')>();
  return {
    ...actual,
    aiModelsApi: {
      listUserModels: vi.fn().mockResolvedValue({
        items: [
          {
            user_model_id: 'm1',
            provider_credential_id: 'cred-1',
            provider_kind: 'lm_studio',
            provider_model_name: 'qwen3',
            alias: 'Qwen3',
            is_active: true,
            is_favorite: false,
            capability_flags: {},
            tags: [],
            created_at: '2026-01-01T00:00:00Z',
          },
        ],
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

const cell = (over: Record<string, unknown>) => ({
  has_active: false,
  active_version_num: null,
  latest_version_num: null,
  latest_status: null,
  version_count: 0,
  ...over,
});

beforeEach(() => {
  toastError.mockClear();
  toastSuccess.mockClear();
  createJob.mockClear();
  putBookSettings.mockClear();
  localStorage.clear();
  invalidateUserModelsCache(); // the shared model fetch keeps a short-TTL module cache
  listChapters.mockReset();
  listChapters.mockResolvedValue({
    items: [{ chapter_id: 'ch1', title: 'Chapter 1', sort_order: 0 }],
    total: 1,
  });
  getBookSettings.mockResolvedValue({
    book_id: 'bk1',
    target_language: 'vi',
    model_source: 'user_model',
    model_ref: 'm1',
    system_prompt: 'Custom system prompt.',
    user_prompt_tpl: 'Custom {chapter_text}',
    is_default: false,
  });
  getBookCoverage.mockResolvedValue({ book_id: 'bk1', coverage: [], known_languages: ['vi'] });
});

describe('TranslateModal — T1 fixes', () => {
  it('Fix-C: submit passes per-job target_language/model_source/model_ref to createJob', async () => {
    render(<TranslateModal {...baseProps} />);
    // Wait for async load (chapters/coverage/settings/models) to finish.
    const submit = await screen.findByRole('button', { name: 'translate.submit_selected' });
    expect(submit).not.toBeDisabled(); // settings pre-fill language + model; ch1 defaults selected (untranslated)

    fireEvent.click(submit);

    await waitFor(() => expect(createJob).toHaveBeenCalledTimes(1));
    const payload = createJob.mock.calls[0][2];
    expect(payload.chapter_ids).toEqual(['ch1']);
    expect(payload.target_language).toBe('vi');
    expect(payload.model_source).toBe('user_model');
    expect(payload.model_ref).toBe('m1');
    expect(payload.force_retranslate).toBe(false);
  });

  it('Fix-B: a settings-save failure surfaces a toast instead of being swallowed', async () => {
    putBookSettings.mockRejectedValueOnce(new Error('422 boom'));
    render(<TranslateModal {...baseProps} />);

    // Wait for load, then change the language → triggers handleSaveSettings (best-effort persist).
    await screen.findByRole('button', { name: 'translate.submit_selected' });
    const langSelect = screen.getAllByRole('combobox')[0]; // Target Language
    fireEvent.change(langSelect, { target: { value: 'ja' } });

    await waitFor(() => expect(putBookSettings).toHaveBeenCalled());
    await waitFor(() => expect(toastError).toHaveBeenCalled());
  });
});

describe('TranslateModal — smart selection', () => {
  it('default-targets only the chapters that need translation (untranslated ∪ stale ∪ failed)', async () => {
    listChapters.mockResolvedValue({
      items: [
        { chapter_id: 'ch1', title: 'Done', sort_order: 0 },
        { chapter_id: 'ch2', title: 'New', sort_order: 1 },
        { chapter_id: 'ch3', title: 'Stale', sort_order: 2 },
      ],
      total: 3,
    });
    getBookCoverage.mockResolvedValue({
      book_id: 'bk1',
      known_languages: ['vi'],
      coverage: [
        { chapter_id: 'ch1', languages: { vi: cell({ has_active: true, is_glossary_stale: false }) } }, // translated
        { chapter_id: 'ch3', languages: { vi: cell({ has_active: true, is_glossary_stale: true }) } }, // stale
        // ch2 absent → untranslated
      ],
    });

    render(<TranslateModal {...baseProps} />);
    // The summary's primary "translate what needs it" button targets ch2 + ch3.
    const primary = await screen.findByRole('button', { name: 'translate.translate_needed' });
    fireEvent.click(primary);

    await waitFor(() => expect(createJob).toHaveBeenCalledTimes(1));
    const payload = createJob.mock.calls[0][2];
    expect([...payload.chapter_ids].sort()).toEqual(['ch2', 'ch3']);
    expect(payload.force_retranslate).toBe(false); // gate skips the fresh ch1
  });

  it('paginates a large book (100/pg) — next page reveals the next slice', async () => {
    listChapters.mockResolvedValue({
      items: Array.from({ length: 150 }, (_, i) => ({ chapter_id: `c${i + 1}`, title: `Ch${i + 1}`, sort_order: i + 1 })),
      total: 150,
    });

    render(<TranslateModal {...baseProps} />);
    // Page 1 = chapters 1..100; chapter 101 lives on page 2.
    expect(await screen.findByText('Ch1')).toBeInTheDocument();
    expect(screen.queryByText('Ch101')).toBeNull();

    fireEvent.click(screen.getByLabelText('translate.next'));

    expect(await screen.findByText('Ch101')).toBeInTheDocument();
    expect(screen.queryByText('Ch1')).toBeNull();
  });
});
