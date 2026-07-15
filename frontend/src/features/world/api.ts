import { apiJson } from '../../api';
import type {
  AuthoredEntity,
  ChapterLink,
  CreateWorldPayload,
  World,
  WorldBookListResponse,
  WorldKind,
  WorldListResponse,
  WorldMapDetail,
  WorldMapListResponse,
} from './types';

// C21 — world container FE. World CRUD rides C20's `/v1/worlds` (book-service,
// reached via the thin gateway passthrough added this cycle). Lore authoring
// rides the EXISTING glossary endpoints: create an entity in the bible BOOK,
// then chapter-link it to the bible CHAPTER (the NOT-NULL anchor). No new BE.
const WORLDS = '/v1/worlds';
const GLOSSARY = '/v1/glossary';

export const worldsApi = {
  listWorlds(token: string, params?: { limit?: number; offset?: number }): Promise<WorldListResponse> {
    const qs = new URLSearchParams();
    if (params?.limit != null) qs.set('limit', String(params.limit));
    if (params?.offset != null) qs.set('offset', String(params.offset));
    const q = qs.toString();
    return apiJson<WorldListResponse>(`${WORLDS}${q ? `?${q}` : ''}`, { token });
  },

  getWorld(token: string, worldId: string): Promise<World> {
    return apiJson<World>(`${WORLDS}/${encodeURIComponent(worldId)}`, { token });
  },

  /** C28 — the world's member books (C20 `GET /v1/worlds/{id}/books`). The
   *  living-world tree enumerates these to collect their canon + dị bản Works.
   *  Bible books are excluded by the endpoint. No new BE. */
  listWorldBooks(
    token: string,
    worldId: string,
    params?: { limit?: number; offset?: number },
  ): Promise<WorldBookListResponse> {
    const qs = new URLSearchParams();
    if (params?.limit != null) qs.set('limit', String(params.limit));
    if (params?.offset != null) qs.set('offset', String(params.offset));
    const q = qs.toString();
    return apiJson<WorldBookListResponse>(
      `${WORLDS}/${encodeURIComponent(worldId)}/books${q ? `?${q}` : ''}`,
      { token },
    );
  },

  createWorld(token: string, payload: CreateWorldPayload): Promise<World> {
    return apiJson<World>(WORLDS, {
      method: 'POST',
      body: JSON.stringify(payload),
      token,
    });
  },

  /** W5 (G1) — attach an existing book to a world (C20 `POST /v1/worlds/{id}/
   *  books` — sets `books.world_id`). Requires world ownership AND edit grant on
   *  the book (BE-enforced). Idempotent: re-adding a book already in the world
   *  is a no-op. Bible books can't be moved (BE filters `is_bible=false`). */
  moveBookIntoWorld(token: string, worldId: string, bookId: string): Promise<{ book_id: string; world_id: string }> {
    return apiJson<{ book_id: string; world_id: string }>(
      `${WORLDS}/${encodeURIComponent(worldId)}/books`,
      { method: 'POST', body: JSON.stringify({ book_id: bookId }), token },
    );
  },

  /** W6 (G3) — detach a book from a world (C20 `DELETE /v1/worlds/{id}/books/
   *  {bookId}` — clears `books.world_id` back to standalone). Only clears when
   *  the book is actually in THIS world. */
  removeBookFromWorld(token: string, worldId: string, bookId: string): Promise<void> {
    return apiJson<void>(
      `${WORLDS}/${encodeURIComponent(worldId)}/books/${encodeURIComponent(bookId)}`,
      { method: 'DELETE', token },
    );
  },

  // ── lore authoring (anchors to the bible chapter) ───────────────────────

  /** Glossary entity kinds — the world lore form's kind picker. Reuses the
   *  shared glossary kinds endpoint (no world-specific kinds). */
  listKinds(token: string): Promise<WorldKind[]> {
    return apiJson<WorldKind[]>(`${GLOSSARY}/kinds`, { token });
  },

  /** Step 1 of authoring lore against the world: create a glossary entity in
   *  the world's bible BOOK. The body is `{kind_id}` only (the glossary
   *  contract); the entity starts as a `draft`. */
  createBibleEntity(token: string, bibleBookId: string, kindId: string): Promise<AuthoredEntity> {
    return apiJson<AuthoredEntity>(
      `${GLOSSARY}/books/${encodeURIComponent(bibleBookId)}/entities`,
      { method: 'POST', body: JSON.stringify({ kind_id: kindId }), token },
    );
  },

  /** Step 2: anchor the entity to the world's bible CHAPTER. This is the call
   *  that writes the NOT-NULL `chapter_entity_links.chapter_id` — the whole
   *  prose-less worldbuilding story hinges on `chapterId === bible_chapter_id`. */
  linkEntityToBibleChapter(
    token: string,
    bibleBookId: string,
    entityId: string,
    chapterId: string,
  ): Promise<ChapterLink> {
    return apiJson<ChapterLink>(
      `${GLOSSARY}/books/${encodeURIComponent(bibleBookId)}/entities/${encodeURIComponent(
        entityId,
      )}/chapter-links`,
      {
        method: 'POST',
        body: JSON.stringify({ chapter_id: chapterId, relevance: 'major' }),
        token,
      },
    );
  },

  /** W10 — list a world's maps (GET /v1/worlds/{id}/maps, book-service). Read-only;
   *  map mutations stay on the Tier-W world_map_* agent tools. */
  listWorldMaps(token: string, worldId: string): Promise<WorldMapListResponse> {
    return apiJson<WorldMapListResponse>(
      `${WORLDS}/${encodeURIComponent(worldId)}/maps`,
      { token },
    );
  },

  /** W10 — one map with all its markers + regions + a render-ready image URL. */
  getWorldMap(token: string, worldId: string, mapId: string): Promise<WorldMapDetail> {
    return apiJson<WorldMapDetail>(
      `${WORLDS}/${encodeURIComponent(worldId)}/maps/${encodeURIComponent(mapId)}`,
      { token },
    );
  },
};
