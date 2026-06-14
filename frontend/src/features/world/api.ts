import { apiJson } from '../../api';
import type {
  AuthoredEntity,
  ChapterLink,
  CreateWorldPayload,
  World,
  WorldKind,
  WorldListResponse,
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

  createWorld(token: string, payload: CreateWorldPayload): Promise<World> {
    return apiJson<World>(WORLDS, {
      method: 'POST',
      body: JSON.stringify(payload),
      token,
    });
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
};
