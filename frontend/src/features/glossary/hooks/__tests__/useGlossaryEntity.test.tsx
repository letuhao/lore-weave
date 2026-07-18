import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import type { GlossaryEntity } from '../../types';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const apiMocks = vi.hoisted(() => ({
  getEntity: vi.fn(),
  patchAttributeValue: vi.fn(),
  patchEntity: vi.fn(),
  addAttributeValue: vi.fn(),
  deleteAttributeValue: vi.fn(),
}));
vi.mock('../../api', () => ({ glossaryApi: apiMocks }));

import { toast } from 'sonner';
import { useGlossaryEntity } from '../useGlossaryEntity';

const BOOK = 'book-1';
const ENTITY_ID = 'entity-1';

function entity(overrides: Partial<GlossaryEntity> = {}): GlossaryEntity {
  return {
    entity_id: ENTITY_ID,
    book_id: BOOK,
    kind_id: 'kind-1',
    kind: { kind_id: 'kind-1', code: 'character', name: 'Character', icon: '🧑', color: '#fff' },
    display_name: 'Jiang Ziya',
    display_name_translation: null,
    status: 'draft',
    tags: [],
    chapter_link_count: 0,
    translation_count: 0,
    evidence_count: 0,
    created_at: '2026-07-04T00:00:00Z',
    updated_at: '2026-07-04T00:00:00Z',
    chapter_links: [],
    attribute_values: [
      {
        attr_value_id: 'av-1',
        entity_id: ENTITY_ID,
        attr_def_id: 'def-1',
        attribute_def: {
          attr_def_id: 'def-1', code: 'title', name: 'Title', field_type: 'text',
          is_required: false, is_system: false, is_active: true, sort_order: 0, genre_tags: [],
        },
        original_language: 'en',
        original_value: 'Immortal',
        translations: [],
        evidences: [],
      },
    ],
    ...overrides,
  };
}

async function mountHook(seed: GlossaryEntity = entity()) {
  apiMocks.getEntity.mockResolvedValue(seed);
  const { result } = renderHook(() => useGlossaryEntity(BOOK, ENTITY_ID));
  await waitFor(() => expect(result.current.loading).toBe(false));
  return result;
}

beforeEach(() => {
  Object.values(apiMocks).forEach((m) => m.mockReset());
  vi.mocked(toast.success).mockReset();
  vi.mocked(toast.error).mockReset();
  apiMocks.patchAttributeValue.mockResolvedValue({});
  apiMocks.patchEntity.mockResolvedValue(entity({ status: 'active' }));
});

describe('useGlossaryEntity', () => {
  it('loads the entity on mount', async () => {
    const result = await mountHook();
    expect(apiMocks.getEntity).toHaveBeenCalledWith(BOOK, ENTITY_ID, 'tok');
    expect(result.current.entity?.entity_id).toBe(ENTITY_ID);
  });

  it('getValue falls back to original_value with no pending change', async () => {
    const result = await mountHook();
    const attr = result.current.entity!.attribute_values[0];
    expect(result.current.getValue(attr)).toBe('Immortal');
  });

  it('setValue marks the field dirty and getValue reflects the override', async () => {
    const result = await mountHook();
    const attr = result.current.entity!.attribute_values[0];
    act(() => result.current.setValue(attr.attr_value_id, 'Deity'));
    expect(result.current.isDirty).toBe(true);
    expect(result.current.getValue(attr)).toBe('Deity');
  });

  it('discard clears pending changes without calling the API', async () => {
    const result = await mountHook();
    const attr = result.current.entity!.attribute_values[0];
    act(() => result.current.setValue(attr.attr_value_id, 'Deity'));
    act(() => result.current.discard());
    expect(result.current.isDirty).toBe(false);
    expect(apiMocks.patchAttributeValue).not.toHaveBeenCalled();
  });

  it('save is a no-op when nothing is dirty', async () => {
    const result = await mountHook();
    await act(async () => { await result.current.save(); });
    expect(apiMocks.patchAttributeValue).not.toHaveBeenCalled();
  });

  it('save persists every pending change, clears dirty, and reloads', async () => {
    const result = await mountHook();
    const attr = result.current.entity!.attribute_values[0];
    act(() => result.current.setValue(attr.attr_value_id, 'Deity'));
    await act(async () => { await result.current.save(); });
    expect(apiMocks.patchAttributeValue).toHaveBeenCalledWith(
      BOOK, ENTITY_ID, attr.attr_value_id, { original_value: 'Deity' }, 'tok',
    );
    expect(result.current.isDirty).toBe(false);
    // reload() re-fetched — getEntity called once for mount + once for post-save reload
    expect(apiMocks.getEntity).toHaveBeenCalledTimes(2);
  });

  it('save propagates a write failure to the caller instead of swallowing it (unlike reload)', async () => {
    const result = await mountHook();
    const attr = result.current.entity!.attribute_values[0];
    act(() => result.current.setValue(attr.attr_value_id, 'Deity'));
    apiMocks.patchAttributeValue.mockRejectedValue(new Error('conflict'));
    await expect(act(async () => { await result.current.save(); })).rejects.toThrow('conflict');
    expect(result.current.saving).toBe(false);
    // a failed write must NOT be treated as clean — the caller can retry
    expect(result.current.isDirty).toBe(true);
  });

  it('setStatus patches the entity and reloads', async () => {
    const result = await mountHook();
    await act(async () => { await result.current.setStatus('active'); });
    expect(apiMocks.patchEntity).toHaveBeenCalledWith(BOOK, ENTITY_ID, { status: 'active' }, 'tok');
    expect(apiMocks.getEntity).toHaveBeenCalledTimes(2);
  });

  it('setScopeLabel patches the entity and reloads', async () => {
    const result = await mountHook();
    await act(async () => { await result.current.setScopeLabel('World A'); });
    expect(apiMocks.patchEntity).toHaveBeenCalledWith(BOOK, ENTITY_ID, { scope_label: 'World A' }, 'tok');
    expect(apiMocks.getEntity).toHaveBeenCalledTimes(2);
  });

  it('setScopeLabel propagates a collision failure to the caller', async () => {
    const result = await mountHook();
    apiMocks.patchEntity.mockRejectedValue(new Error('an entity with this name, kind, and scope already exists in this book'));
    await expect(act(async () => { await result.current.setScopeLabel('World A'); })).rejects.toThrow('already exists');
  });

  it('reload swallows its own fetch error and toasts instead of throwing', async () => {
    const result = await mountHook();
    apiMocks.getEntity.mockRejectedValueOnce(new Error('network down'));
    await act(async () => { await result.current.reload(); });
    expect(toast.error).toHaveBeenCalledWith('network down');
    expect(result.current.loading).toBe(false);
  });

  it('applyTranslationChange adds a translation and increments translation_count', async () => {
    const result = await mountHook();
    const attr = result.current.entity!.attribute_values[0];
    act(() => result.current.applyTranslationChange(attr.attr_value_id, {
      translation_id: 'tr-1', attr_value_id: attr.attr_value_id, language_code: 'vi',
      value: 'Bất Tử', confidence: 'draft', translator: null, updated_at: '2026-07-04T00:00:00Z',
    }));
    expect(result.current.entity?.translation_count).toBe(1);
    expect(result.current.entity?.attribute_values[0].translations).toHaveLength(1);
  });

  it('applyTranslationChange removes a translation and decrements translation_count', async () => {
    const result = await mountHook(entity({
      translation_count: 1,
      attribute_values: [{
        ...entity().attribute_values[0],
        translations: [{ translation_id: 'tr-1', attr_value_id: 'av-1', language_code: 'vi', value: 'Bất Tử', confidence: 'draft', translator: null, updated_at: '2026-07-04T00:00:00Z' }],
      }],
    }));
    act(() => result.current.applyTranslationChange('av-1', null, 'tr-1'));
    expect(result.current.entity?.translation_count).toBe(0);
    expect(result.current.entity?.attribute_values[0].translations).toHaveLength(0);
  });

  it('bumpEvidenceCount adjusts the local count without an API call', async () => {
    const result = await mountHook();
    act(() => result.current.bumpEvidenceCount(1));
    expect(result.current.entity?.evidence_count).toBe(1);
  });

  // ── S-06 add/remove: must PRESERVE the user's other unsaved edits (BUG-A: a plain reload()
  //    cleared ALL pending, silently losing edits on unrelated attrs). ──
  const av2 = () => ({
    ...entity().attribute_values[0],
    attr_value_id: 'av-2', attr_def_id: 'def-2', original_value: 'Staff',
    attribute_def: { ...entity().attribute_values[0].attribute_def, attr_def_id: 'def-2', code: 'weapon', name: 'Weapon' },
  });

  it('removeAttributeValue drops the row + its pending edit but PRESERVES other unsaved edits (no clear-all reload)', async () => {
    const result = await mountHook(entity({ attribute_values: [entity().attribute_values[0], av2()] }));
    apiMocks.deleteAttributeValue.mockResolvedValue(undefined);
    act(() => result.current.setValue('av-1', 'Deity'));   // unsaved edit on av-1
    await act(async () => { await result.current.removeAttributeValue('av-2'); });
    // av-2 gone locally; av-1's unsaved edit survives; no full refetch
    expect(result.current.entity?.attribute_values.map((a) => a.attr_value_id)).toEqual(['av-1']);
    expect(result.current.getValue(result.current.entity!.attribute_values[0])).toBe('Deity');
    expect(result.current.isDirty).toBe(true);
    expect(apiMocks.getEntity).toHaveBeenCalledTimes(1);   // mount only — no reload
  });

  it('addAttributeValue refetches for the new row but PRESERVES other unsaved edits', async () => {
    const result = await mountHook(entity({ attribute_values: [entity().attribute_values[0], av2()] }));
    apiMocks.addAttributeValue.mockResolvedValue({});
    const av3 = { ...entity().attribute_values[0], attr_value_id: 'av-3', attr_def_id: 'def-3', original_value: '',
      attribute_def: { ...entity().attribute_values[0].attribute_def, attr_def_id: 'def-3', code: 'origin', name: 'Origin' } };
    apiMocks.getEntity.mockResolvedValueOnce(entity({ attribute_values: [entity().attribute_values[0], av2(), av3] }));
    act(() => result.current.setValue('av-1', 'Deity'));   // unsaved edit on av-1
    await act(async () => { await result.current.addAttributeValue('def-3', 'Kunlun'); });
    expect(apiMocks.addAttributeValue).toHaveBeenCalledWith(BOOK, ENTITY_ID, { attribute_def_id: 'def-3', value: 'Kunlun' }, 'tok');
    expect(result.current.entity?.attribute_values.map((a) => a.attr_value_id)).toContain('av-3');
    // av-1's unsaved edit survives the refetch
    const av1 = result.current.entity!.attribute_values.find((a) => a.attr_value_id === 'av-1')!;
    expect(result.current.getValue(av1)).toBe('Deity');
  });
});
