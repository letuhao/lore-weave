import { apiBase, apiJson } from '../../api';
import type {
  AuthoredEntity,
  ChapterLink,
  CreateWorldPayload,
  World,
  WorldBookListResponse,
  WorldKind,
  WorldListResponse,
  WorldMapCreateResponse,
  WorldMapDetail,
  WorldMapImageResponse,
  WorldMapListResponse,
  WorldMapMarkerResponse,
  WorldMapRegionResponse,
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

  // ── S7·2 — the world-map editor's write layer (R1..R10, book-service). Every write is
  //    deterministic CRUD ($0, no LLM). A pin DRAG is patchMarker({x,y}) on a STABLE marker_id —
  //    NEVER deleteMarker+addMarker (which churns the id + strands the entity tie).

  /** R1 — create a map in a world. Optionally attach an already-uploaded base image key. */
  createMap(token: string, worldId: string, payload: { name: string; image_ref?: string }): Promise<WorldMapCreateResponse> {
    return apiJson<WorldMapCreateResponse>(`${WORLDS}/${encodeURIComponent(worldId)}/maps`, {
      method: 'POST',
      body: JSON.stringify(payload),
      token,
    });
  },

  /** R2 — rename a map / repoint its image. OCC: If-Match on the map version (428 absent, 412
   *  stale — the caller reads the current row off the thrown error's `body.current`). */
  patchMap(
    token: string,
    worldId: string,
    mapId: string,
    version: number,
    payload: { name?: string; image_object_key?: string | null },
  ): Promise<WorldMapCreateResponse> {
    return apiJson<WorldMapCreateResponse>(
      `${WORLDS}/${encodeURIComponent(worldId)}/maps/${encodeURIComponent(mapId)}`,
      { method: 'PATCH', body: JSON.stringify(payload), token, headers: { 'If-Match': String(version) } },
    );
  },

  /** R3 — delete a map (CASCADE-removes its markers + regions + base image). */
  deleteMap(token: string, worldId: string, mapId: string): Promise<{ deleted: boolean }> {
    return apiJson<{ deleted: boolean }>(
      `${WORLDS}/${encodeURIComponent(worldId)}/maps/${encodeURIComponent(mapId)}`,
      { method: 'DELETE', token },
    );
  },

  /** R4 — upload a base image (multipart). Public JWT-resolved wrapper; the browser CANNOT hit
   *  the internal ?user_id route. Bypasses apiJson (which forces JSON) so the browser sets the
   *  multipart boundary itself. */
  async uploadMapImage(token: string, worldId: string, mapId: string, file: File): Promise<WorldMapImageResponse> {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(
      `${apiBase()}${WORLDS}/${encodeURIComponent(worldId)}/maps/${encodeURIComponent(mapId)}/image`,
      { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: form },
    );
    const text = await res.text();
    const body = text ? JSON.parse(text) : null;
    if (!res.ok) {
      throw Object.assign(new Error(body?.message || res.statusText), { status: res.status, code: body?.code, body });
    }
    return body as WorldMapImageResponse;
  },

  /** R5 — drop a pin at a normalized (x,y). */
  addMarker(
    token: string,
    worldId: string,
    mapId: string,
    payload: { label: string; x: number; y: number; entity_id?: string; marker_type?: string },
  ): Promise<WorldMapMarkerResponse> {
    return apiJson<WorldMapMarkerResponse>(
      `${WORLDS}/${encodeURIComponent(worldId)}/maps/${encodeURIComponent(mapId)}/markers`,
      { method: 'POST', body: JSON.stringify(payload), token },
    );
  },

  /** R6 🔴 — move/relabel/rebind a pin. A drag sends `{x,y}` ABSOLUTE on the stable marker_id.
   *  `entity_id:null` unbinds; a partial body leaves omitted fields unchanged (the pointer rule). */
  patchMarker(
    token: string,
    worldId: string,
    mapId: string,
    markerId: string,
    payload: { x?: number; y?: number; label?: string; entity_id?: string | null; marker_type?: string | null },
  ): Promise<WorldMapMarkerResponse> {
    return apiJson<WorldMapMarkerResponse>(
      `${WORLDS}/${encodeURIComponent(worldId)}/maps/${encodeURIComponent(mapId)}/markers/${encodeURIComponent(markerId)}`,
      { method: 'PATCH', body: JSON.stringify(payload), token },
    );
  },

  /** R7 — delete a pin. */
  deleteMarker(token: string, worldId: string, mapId: string, markerId: string): Promise<{ removed: boolean }> {
    return apiJson<{ removed: boolean }>(
      `${WORLDS}/${encodeURIComponent(worldId)}/maps/${encodeURIComponent(mapId)}/markers/${encodeURIComponent(markerId)}`,
      { method: 'DELETE', token },
    );
  },

  /** R8 — draw a region (polygon of ≥3 normalized points). */
  addRegion(
    token: string,
    worldId: string,
    mapId: string,
    payload: { name: string; polygon: number[][]; entity_id?: string },
  ): Promise<WorldMapRegionResponse> {
    return apiJson<WorldMapRegionResponse>(
      `${WORLDS}/${encodeURIComponent(worldId)}/maps/${encodeURIComponent(mapId)}/regions`,
      { method: 'POST', body: JSON.stringify(payload), token },
    );
  },

  /** R9 — reshape/rename/rebind a region. A reshape sends the whole `{polygon}`. */
  patchRegion(
    token: string,
    worldId: string,
    mapId: string,
    regionId: string,
    payload: { polygon?: number[][]; name?: string; entity_id?: string | null },
  ): Promise<WorldMapRegionResponse> {
    return apiJson<WorldMapRegionResponse>(
      `${WORLDS}/${encodeURIComponent(worldId)}/maps/${encodeURIComponent(mapId)}/regions/${encodeURIComponent(regionId)}`,
      { method: 'PATCH', body: JSON.stringify(payload), token },
    );
  },

  /** R10 — delete a region. */
  deleteRegion(token: string, worldId: string, mapId: string, regionId: string): Promise<{ removed: boolean }> {
    return apiJson<{ removed: boolean }>(
      `${WORLDS}/${encodeURIComponent(worldId)}/maps/${encodeURIComponent(mapId)}/regions/${encodeURIComponent(regionId)}`,
      { method: 'DELETE', token },
    );
  },
};
