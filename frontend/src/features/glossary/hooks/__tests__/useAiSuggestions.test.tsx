import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';
import type { GlossaryEntitySummary } from '../../types';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const apiMocks = vi.hoisted(() => ({
  listAiSuggestions: vi.fn(),
  patchEntity: vi.fn(),
}));
vi.mock('../../api', () => ({ glossaryApi: apiMocks }));

import { useAiSuggestions } from '../useAiSuggestions';

const BOOK = 'book-1';

function ent(id: string, name: string, tags: string[] = ['ai-suggested']): GlossaryEntitySummary {
  return {
    entity_id: id,
    book_id: BOOK,
    kind_id: 'k1',
    kind: { code: 'character', name: 'Character' } as GlossaryEntitySummary['kind'],
    display_name: name,
    display_name_translation: null,
    status: 'draft',
    tags,
    chapter_link_count: 3,
    translation_count: 0,
    evidence_count: 1,
    created_at: '2026-06-06T00:00:00Z',
    updated_at: '2026-06-06T00:00:00Z',
  };
}

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { Wrapper, invalidateSpy };
}

async function mountHook(items: GlossaryEntitySummary[]) {
  apiMocks.listAiSuggestions.mockResolvedValue({ items, total: items.length, limit: 200, offset: 0 });
  const { Wrapper, invalidateSpy } = makeWrapper();
  const { result } = renderHook(() => useAiSuggestions(BOOK), { wrapper: Wrapper });
  await waitFor(() => expect(result.current.isLoading).toBe(false));
  return { result, invalidateSpy };
}

beforeEach(() => {
  Object.values(apiMocks).forEach((m) => m.mockReset());
  apiMocks.patchEntity.mockResolvedValue({});
});

describe('useAiSuggestions', () => {
  it('loads the ai-suggested draft queue for the book', async () => {
    const { result } = await mountHook([ent('e1', '哪吒')]);
    expect(apiMocks.listAiSuggestions).toHaveBeenCalledWith(BOOK, 'tok');
    expect(result.current.items).toHaveLength(1);
    expect(result.current.total).toBe(1);
  });

  it('promote sets status=active and invalidates inbox + entity list', async () => {
    const { result, invalidateSpy } = await mountHook([ent('e1', '哪吒')]);
    await act(async () => { await result.current.promote(result.current.items[0]); });
    expect(apiMocks.patchEntity).toHaveBeenCalledWith(BOOK, 'e1', { status: 'active' }, 'tok');
    const keys = invalidateSpy.mock.calls.map((c) => c[0]?.queryKey);
    expect(keys).toContainEqual(['glossary-ai-suggestions', BOOK]);
    expect(keys).toContainEqual(['glossary-entities', BOOK]);
  });

  it('reject sets status=inactive and adds the ai-rejected tombstone (keeps ai-suggested)', async () => {
    const { result } = await mountHook([ent('e1', '李靖', ['ai-suggested'])]);
    await act(async () => { await result.current.reject(result.current.items[0]); });
    expect(apiMocks.patchEntity).toHaveBeenCalledWith(
      BOOK, 'e1',
      { status: 'inactive', tags: ['ai-suggested', 'ai-rejected'] },
      'tok',
    );
  });

  it('reject is idempotent when ai-rejected is already present', async () => {
    const { result } = await mountHook([ent('e1', '李靖', ['ai-suggested', 'ai-rejected'])]);
    await act(async () => { await result.current.reject(result.current.items[0]); });
    expect(apiMocks.patchEntity).toHaveBeenCalledWith(
      BOOK, 'e1',
      { status: 'inactive', tags: ['ai-suggested', 'ai-rejected'] },
      'tok',
    );
  });
});
