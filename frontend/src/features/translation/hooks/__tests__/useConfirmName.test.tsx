import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

// M6a — useConfirmName resolves a corrected name to its glossary entity and
// confirms (confidence='verified') via the glossary API.

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const { listEntities, getEntity, patchTranslation, createTranslation } = vi.hoisted(() => ({
  listEntities: vi.fn(), getEntity: vi.fn(),
  patchTranslation: vi.fn(), createTranslation: vi.fn(),
}));
vi.mock('@/features/glossary/api', () => ({
  glossaryApi: { listEntities, getEntity, patchTranslation, createTranslation },
}));

import { useConfirmName } from '../useConfirmName';

const nameEntity = (translations: any[]) => ({
  entity_id: 'e1',
  attribute_values: [
    { attr_value_id: 'av1', attribute_def: { code: 'name' }, translations },
  ],
});

async function run(sourceName: string, target: string) {
  const { result } = renderHook(() => useConfirmName('b1', 'vi'));
  let r: string | undefined;
  await act(async () => { r = await result.current.confirm(sourceName, target); });
  return r;
}

describe('useConfirmName', () => {
  beforeEach(() => {
    listEntities.mockReset(); getEntity.mockReset();
    patchTranslation.mockReset(); createTranslation.mockReset();
    patchTranslation.mockResolvedValue({}); createTranslation.mockResolvedValue({});
  });

  it('patches an existing target translation with confidence=verified', async () => {
    listEntities.mockResolvedValue({ items: [{ entity_id: 'e1', display_name: '提拉米' }] });
    getEntity.mockResolvedValue(nameEntity([{ translation_id: 't1', language_code: 'vi', value: 'old' }]));
    expect(await run('提拉米', 'Tirami')).toBe('confirmed');
    expect(patchTranslation).toHaveBeenCalledWith(
      'b1', 'e1', 'av1', 't1', { value: 'Tirami', confidence: 'verified' }, 'tok');
    expect(createTranslation).not.toHaveBeenCalled();
  });

  it('creates a translation when none exists for the target language', async () => {
    listEntities.mockResolvedValue({ items: [{ entity_id: 'e1', display_name: '提拉米' }] });
    getEntity.mockResolvedValue(nameEntity([{ translation_id: 't1', language_code: 'en', value: 'X' }]));
    expect(await run('提拉米', 'Tirami')).toBe('confirmed');
    expect(createTranslation).toHaveBeenCalledWith(
      'b1', 'e1', 'av1', { language_code: 'vi', value: 'Tirami', confidence: 'verified' }, 'tok');
    expect(patchTranslation).not.toHaveBeenCalled();
  });

  it('confirms only the exact display-name match, ignoring fuzzy hits', async () => {
    listEntities.mockResolvedValue({ items: [
      { entity_id: 'eX', display_name: '提拉米苏' },
      { entity_id: 'e1', display_name: '提拉米' },
    ] });
    getEntity.mockResolvedValue(nameEntity([]));
    await run('提拉米', 'Tirami');
    expect(getEntity).toHaveBeenCalledWith('b1', 'e1', 'tok');  // the exact match
  });

  it('returns not_found when no entity matches', async () => {
    listEntities.mockResolvedValue({ items: [] });
    expect(await run('提拉米', 'Tirami')).toBe('not_found');
    expect(getEntity).not.toHaveBeenCalled();
  });

  it('returns not_found (no wrong-entity write) when only fuzzy hits exist', async () => {
    listEntities.mockResolvedValue({ items: [
      { entity_id: 'eX', display_name: '提拉米苏' },  // fuzzy, NOT exact
    ] });
    expect(await run('提拉米', 'Tirami')).toBe('not_found');
    expect(getEntity).not.toHaveBeenCalled();
    expect(patchTranslation).not.toHaveBeenCalled();
    expect(createTranslation).not.toHaveBeenCalled();
  });

  it('returns no_name_attr when the entity has no name attribute', async () => {
    listEntities.mockResolvedValue({ items: [{ entity_id: 'e1', display_name: '提拉米' }] });
    getEntity.mockResolvedValue({ entity_id: 'e1', attribute_values: [
      { attr_value_id: 'av9', attribute_def: { code: 'aliases' }, translations: [] },
    ] });
    expect(await run('提拉米', 'Tirami')).toBe('no_name_attr');
  });

  it('returns error on an API failure AND logs the exception (S8: no silent swallow)', async () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    listEntities.mockRejectedValue(new Error('boom'));
    expect(await run('提拉米', 'Tirami')).toBe('error');
    // S8: the catch used to discard the exception; it must now surface it to the console.
    expect(spy).toHaveBeenCalledWith('useConfirmName: confirm failed', expect.any(Error));
    spy.mockRestore();
  });

  it('returns error on blank input without calling the API', async () => {
    expect(await run('  ', 'Tirami')).toBe('error');
    expect(listEntities).not.toHaveBeenCalled();
  });
});
