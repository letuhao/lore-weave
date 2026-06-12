import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

// M7c-2 — useEditTranslation saves a human edit as a new version via the M7c-1
// endpoint (format-aware payload: json doc.content vs text string).

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: any) => (o?.error ? `${k}:${o.error}` : k) }),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const { saveEditedVersion } = vi.hoisted(() => ({ saveEditedVersion: vi.fn() }));
vi.mock('../../api', () => ({ versionsApi: { saveEditedVersion } }));

import { useEditTranslation } from '../useEditTranslation';
import { toast } from 'sonner';

const jsonVersion: any = {
  id: 'v-llm', target_language: 'vi', translated_body_format: 'json',
  translated_body_json: [{ type: 'paragraph', content: [{ type: 'text', text: 'LLM' }] }],
};
const textVersion: any = {
  id: 'v-llm-t', target_language: 'vi', translated_body_format: 'text',
  translated_body: 'LLM text',
};

describe('useEditTranslation', () => {
  beforeEach(() => {
    saveEditedVersion.mockReset();
    saveEditedVersion.mockResolvedValue({ id: 'v-human', version_num: 2 });
  });

  it('saves a json edit as doc.content + format=json, linked to the source', async () => {
    const onSaved = vi.fn();
    const { result } = renderHook(() => useEditTranslation('ch1', jsonVersion, onSaved));
    act(() => result.current.startEdit());
    expect(result.current.editing).toBe(true);
    const editedDoc = { type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'Human' }] }] };
    act(() => result.current.onEditorUpdate(editedDoc));
    await act(async () => { await result.current.save(); });

    expect(saveEditedVersion).toHaveBeenCalledWith('tok', 'ch1', {
      target_language: 'vi',
      edited_from_version_id: 'v-llm',
      translated_body_json: editedDoc.content,
      translated_body_format: 'json',
    });
    expect(onSaved).toHaveBeenCalledWith({ id: 'v-human', version_num: 2 });
    expect(result.current.editing).toBe(false);  // closes on success
  });

  it('saves a text edit as translated_body + format=text', async () => {
    const onSaved = vi.fn();
    const { result } = renderHook(() => useEditTranslation('ch1', textVersion, onSaved));
    act(() => result.current.startEdit());
    expect(result.current.draftText).toBe('LLM text');  // seeded from the source
    act(() => result.current.setDraftText('Human text'));
    await act(async () => { await result.current.save(); });

    expect(saveEditedVersion).toHaveBeenCalledWith('tok', 'ch1', {
      target_language: 'vi',
      edited_from_version_id: 'v-llm-t',
      translated_body: 'Human text',
      translated_body_format: 'text',
    });
  });

  it('keeps editing open + toasts on save failure', async () => {
    saveEditedVersion.mockRejectedValue(new Error('boom'));
    const onSaved = vi.fn();
    const { result } = renderHook(() => useEditTranslation('ch1', textVersion, onSaved));
    act(() => result.current.startEdit());
    act(() => result.current.setDraftText('Human text'));  // a real change → reaches save
    await act(async () => { await result.current.save(); });
    expect(onSaved).not.toHaveBeenCalled();
    expect(result.current.editing).toBe(true);  // stays open to retry
    expect(toast.error).toHaveBeenCalled();
  });

  it('skips an unchanged text edit (no junk version / no-op gold)', async () => {
    const onSaved = vi.fn();
    const { result } = renderHook(() => useEditTranslation('ch1', textVersion, onSaved));
    act(() => result.current.startEdit());           // draftText seeded = 'LLM text'
    await act(async () => { await result.current.save(); });  // no change
    expect(saveEditedVersion).not.toHaveBeenCalled();
    expect(result.current.editing).toBe(false);       // just closes
    expect(onSaved).not.toHaveBeenCalled();
  });

  it('cancel exits edit mode without saving', async () => {
    const { result } = renderHook(() => useEditTranslation('ch1', jsonVersion, vi.fn()));
    act(() => result.current.startEdit());
    act(() => result.current.cancel());
    expect(result.current.editing).toBe(false);
    expect(saveEditedVersion).not.toHaveBeenCalled();
  });
});
