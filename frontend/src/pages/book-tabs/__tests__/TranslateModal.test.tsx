import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { TranslateModal } from '../TranslateModal';

// ── Mocks ──────────────────────────────────────────────────────────────────────
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const toastError = vi.fn();
const toastSuccess = vi.fn();
vi.mock('sonner', () => ({ toast: { error: (...a: unknown[]) => toastError(...a), success: (...a: unknown[]) => toastSuccess(...a) } }));

vi.mock('@/features/books/api', () => ({
  booksApi: {
    listChapters: vi.fn().mockResolvedValue({
      items: [{ chapter_id: 'ch1', title: 'Chapter 1', chapter_index: 0, language_code: 'en' }],
    }),
  },
}));

const createJob = vi.fn().mockResolvedValue({});
const putBookSettings = vi.fn().mockResolvedValue({});
const getBookSettings = vi.fn().mockResolvedValue({
  book_id: 'bk1',
  target_language: 'vi',
  model_source: 'user_model',
  model_ref: 'm1',
  system_prompt: 'Custom system prompt.',
  user_prompt_tpl: 'Custom {chapter_text}',
  is_default: false,
});
vi.mock('@/features/translation/api', () => ({
  translationApi: {
    getBookSettings: (...a: unknown[]) => getBookSettings(...a),
    putBookSettings: (...a: unknown[]) => putBookSettings(...a),
    createJob: (...a: unknown[]) => createJob(...a),
  },
}));

vi.mock('@/features/ai-models/api', () => ({
  aiModelsApi: {
    listUserModels: vi.fn().mockResolvedValue({
      items: [{ user_model_id: 'm1', alias: 'Qwen3', provider_model_name: 'qwen3', provider_kind: 'lm_studio', is_active: true }],
    }),
  },
}));

const baseProps = { open: true, onClose: vi.fn(), bookId: 'bk1', onJobCreated: vi.fn() };

beforeEach(() => {
  toastError.mockClear();
  toastSuccess.mockClear();
  createJob.mockClear();
  putBookSettings.mockClear();
});

describe('TranslateModal — T1 fixes', () => {
  it('Fix-C: submit passes per-job target_language/model_source/model_ref to createJob', async () => {
    render(<TranslateModal {...baseProps} />);
    // Wait for async load (chapters/settings/models) to finish.
    const submit = await screen.findByRole('button', { name: 'Start Translation' });
    expect(submit).not.toBeDisabled(); // settings pre-fill language + model

    fireEvent.click(submit);

    await waitFor(() => expect(createJob).toHaveBeenCalledTimes(1));
    const payload = createJob.mock.calls[0][2];
    expect(payload.chapter_ids).toEqual(['ch1']);
    expect(payload.target_language).toBe('vi');
    expect(payload.model_source).toBe('user_model');
    expect(payload.model_ref).toBe('m1');
  });

  it('Fix-B: a settings-save failure surfaces a toast instead of being swallowed', async () => {
    putBookSettings.mockRejectedValueOnce(new Error('422 boom'));
    render(<TranslateModal {...baseProps} />);

    // Wait for load, then change the language → triggers handleSaveSettings (best-effort persist).
    await screen.findByRole('button', { name: 'Start Translation' });
    const langSelect = screen.getAllByRole('combobox')[0]; // Target Language
    fireEvent.change(langSelect, { target: { value: 'ja' } });

    await waitFor(() => expect(putBookSettings).toHaveBeenCalled());
    await waitFor(() => expect(toastError).toHaveBeenCalled());
  });
});
