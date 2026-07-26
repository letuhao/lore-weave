import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { useGlossaryQuickCreate } from '../useGlossaryQuickCreate';

// S-10 O7 — the `[[`-create action: create the KG entity, then insert its canonical name. The two
// editor consumers share this hook, so the create+insert behaviour is proven once here.

const createEntity = vi.hoisted(() => vi.fn());
vi.mock('@/features/knowledge/api', () => ({
  knowledgeApi: { createEntity: (...a: unknown[]) => createEntity(...a) },
}));

beforeEach(() => createEntity.mockReset());

describe('useGlossaryQuickCreate', () => {
  it('creates the entity with the closed-set kind and inserts its canonical name', async () => {
    createEntity.mockResolvedValue({ name: 'Kaelith' });
    const insert = vi.fn();
    const { result } = renderHook(() => useGlossaryQuickCreate('proj-1', 'tok', insert));
    expect(result.current).toBeTypeOf('function');
    await result.current!('  Kael  ', 'character');
    // name is trimmed; project + kind threaded; token passed through
    expect(createEntity).toHaveBeenCalledWith({ project_id: 'proj-1', name: 'Kael', kind: 'character' }, 'tok');
    // inserts the CANONICAL name the backend returned, not the raw typed text
    expect(insert).toHaveBeenCalledWith('Kaelith');
  });

  it('is undefined (affordance hidden) until the project resolves', () => {
    const { result } = renderHook(() => useGlossaryQuickCreate(null, 'tok', vi.fn()));
    expect(result.current).toBeUndefined();
  });

  it('is undefined without a token', () => {
    const { result } = renderHook(() => useGlossaryQuickCreate('proj-1', null, vi.fn()));
    expect(result.current).toBeUndefined();
  });

  it('no-ops on a blank name (never creates an unnamed entity)', async () => {
    const insert = vi.fn();
    const { result } = renderHook(() => useGlossaryQuickCreate('proj-1', 'tok', insert));
    await result.current!('   ', 'item');
    expect(createEntity).not.toHaveBeenCalled();
    expect(insert).not.toHaveBeenCalled();
  });
});
