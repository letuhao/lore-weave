import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useWorldLore } from '../hooks/useWorldLore';
import { worldsApi } from '../api';

// C21 — the core acceptance: authored lore anchors to the world's BIBLE CHAPTER.
// useWorldLore must (1) create the entity in the bible BOOK, then (2) chapter-
// link it to the bible CHAPTER carrying the exact bible_chapter_id — in that
// order. A mis-anchor (wrong chapter id, or skipping the link) is the headline
// bug the adversary hunts for, so we assert the call args precisely.

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok', user: { user_id: 'u1' } }),
}));

const BIBLE_BOOK = 'bible-book-1';
const BIBLE_CHAPTER = 'bible-chapter-0';

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(worldsApi, 'listKinds').mockResolvedValue([
    { kind_id: 'k1', code: 'character', name: 'Character' },
  ]);
});

describe('useWorldLore — anchors authored lore to the bible chapter', () => {
  it('creates the entity in the bible book, then chapter-links it to the bible chapter id', async () => {
    const createSpy = vi
      .spyOn(worldsApi, 'createBibleEntity')
      .mockResolvedValue({ entity_id: 'ent-99' });
    const linkSpy = vi
      .spyOn(worldsApi, 'linkEntityToBibleChapter')
      .mockResolvedValue({
        link_id: 'lnk-1',
        entity_id: 'ent-99',
        chapter_id: BIBLE_CHAPTER,
        relevance: 'major',
      });

    const { result } = renderHook(() => useWorldLore(BIBLE_BOOK, BIBLE_CHAPTER), { wrapper });

    const link = await result.current.authorLore({ kindId: 'k1' });

    // Step 1: entity created in the bible BOOK with the chosen kind.
    expect(createSpy).toHaveBeenCalledWith('tok', BIBLE_BOOK, 'k1');
    // Step 2: anchored to the bible CHAPTER (NOT NULL chapter_id == bible chapter).
    expect(linkSpy).toHaveBeenCalledWith('tok', BIBLE_BOOK, 'ent-99', BIBLE_CHAPTER);
    // The returned link carries the bible chapter id.
    expect(link.chapter_id).toBe(BIBLE_CHAPTER);

    // Ordering: create resolves before link is invoked.
    expect(createSpy.mock.invocationCallOrder[0]).toBeLessThan(
      linkSpy.mock.invocationCallOrder[0],
    );
  });

  it('refuses to author (no chapter-link call) when the bible anchor is missing', async () => {
    const linkSpy = vi.spyOn(worldsApi, 'linkEntityToBibleChapter');
    const { result } = renderHook(() => useWorldLore(null, null), { wrapper });

    await expect(result.current.authorLore({ kindId: 'k1' })).rejects.toThrow();
    // Never anchors to a wrong/absent chapter.
    expect(linkSpy).not.toHaveBeenCalled();
  });

  it('exposes glossary kinds for the lore form', async () => {
    const { result } = renderHook(() => useWorldLore(BIBLE_BOOK, BIBLE_CHAPTER), { wrapper });
    await waitFor(() => expect(result.current.kinds.length).toBe(1));
    expect(result.current.kinds[0].name).toBe('Character');
  });
});

describe('worldsApi — endpoints target the right services', () => {
  it('createBibleEntity posts the kind to the glossary bible book', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(
        new Response(JSON.stringify({ entity_id: 'e1' }), { status: 201 }),
      );
    await worldsApi.createBibleEntity('tok', BIBLE_BOOK, 'k1');
    const url = fetchSpy.mock.calls[0][0] as string;
    expect(url).toContain(`/v1/glossary/books/${BIBLE_BOOK}/entities`);
  });

  it('linkEntityToBibleChapter posts the chapter id to the chapter-links endpoint', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(
        new Response(
          JSON.stringify({ link_id: 'l1', entity_id: 'e1', chapter_id: BIBLE_CHAPTER, relevance: 'major' }),
          { status: 201 },
        ),
      );
    await worldsApi.linkEntityToBibleChapter('tok', BIBLE_BOOK, 'e1', BIBLE_CHAPTER);
    const url = fetchSpy.mock.calls[0][0] as string;
    const body = JSON.parse((fetchSpy.mock.calls[0][1] as RequestInit).body as string);
    expect(url).toContain(`/v1/glossary/books/${BIBLE_BOOK}/entities/e1/chapter-links`);
    expect(body.chapter_id).toBe(BIBLE_CHAPTER);
  });

  it('createWorld hits the /v1/worlds passthrough', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(
        new Response(JSON.stringify({ world_id: 'w1' }), { status: 201 }),
      );
    await worldsApi.createWorld('tok', { name: 'X' });
    const url = fetchSpy.mock.calls[0][0] as string;
    expect(url).toContain('/v1/worlds');
  });
});
