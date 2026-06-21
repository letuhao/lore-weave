import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import type { TranslationCandidatesResponse } from '../../types';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const api = vi.hoisted(() => ({
  listTranslationCandidates: vi.fn(),
  applyTranslations: vi.fn(),
}));
vi.mock('../../api', () => ({ glossaryApi: api }));

import { useBatchTranslate } from '../useBatchTranslate';

const CANDIDATES: TranslationCandidatesResponse = {
  book_id: 'b1',
  target_language: 'en',
  total: 1,
  limit: 100,
  offset: 0,
  items: [
    {
      entity_id: 'e1',
      display_name: '焰魔',
      kind_code: 'character',
      status: 'active',
      attributes: [
        { attr_value_id: 'av-name', code: 'name', field_type: 'text', original_language: 'zh', original_value: '焰魔' },
        { attr_value_id: 'av-desc', code: 'description', field_type: 'textarea', original_language: 'zh', original_value: '魔', existing_value: 'Demon' },
      ],
    },
  ],
};

describe('useBatchTranslate', () => {
  beforeEach(() => {
    api.listTranslationCandidates.mockReset().mockResolvedValue(CANDIDATES);
    api.applyTranslations.mockReset().mockResolvedValue({ translated: 1, skipped_verified: 0, skipped_empty: 0, failed: [] });
  });

  it('loads candidates on language select and pre-fills existing translations', async () => {
    const { result } = renderHook(() => useBatchTranslate('b1'));
    act(() => result.current.selectLanguage('en'));
    await waitFor(() => expect(result.current.candidates).toHaveLength(1));
    expect(api.listTranslationCandidates).toHaveBeenCalledWith('b1', 'en', { limit: 100 }, 'tok');
    // existing 'Demon' pre-filled for the description attr value
    expect(result.current.drafts['e1:av-desc']).toBe('Demon');
    expect(result.current.drafts['e1:av-name']).toBeUndefined();
  });

  it('submit posts only non-empty drafts and surfaces the report', async () => {
    const { result } = renderHook(() => useBatchTranslate('b1'));
    act(() => result.current.selectLanguage('en'));
    await waitFor(() => expect(result.current.candidates).toHaveLength(1));

    act(() => result.current.setDraft('e1', 'av-name', '  Flame Demon  '));
    await act(async () => { await result.current.submit(); });

    expect(api.applyTranslations).toHaveBeenCalledWith(
      'b1',
      {
        target_language: 'en',
        items: [
          { entity_id: 'e1', attr_value_id: 'av-name', value: 'Flame Demon' }, // trimmed
          { entity_id: 'e1', attr_value_id: 'av-desc', value: 'Demon' }, // the pre-filled existing value
        ],
      },
      'tok',
    );
    expect(result.current.result?.translated).toBe(1);
  });

  it('surfaces a load error without throwing', async () => {
    api.listTranslationCandidates.mockRejectedValueOnce(new Error('boom'));
    const { result } = renderHook(() => useBatchTranslate('b1'));
    act(() => result.current.selectLanguage('en'));
    await waitFor(() => expect(result.current.error).toBe('boom'));
    expect(result.current.candidates).toHaveLength(0);
  });
});
