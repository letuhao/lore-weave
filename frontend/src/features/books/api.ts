import { apiJson, apiBase } from '@/api';
import type { RevisionCompare } from './types';

export type Visibility = 'private' | 'unlisted' | 'public';

/** The caller's effective grant on a book, computed server-side on the book read
 *  (book-service getBookByID: owner if books.owner_user_id matches, else the
 *  book_collaborators.role, else 'none'). Spec 29 T9/D10-C: the frontend gates
 *  edit-only affordances on this instead of guessing from owner_user_id. */
export type BookAccessLevel = 'owner' | 'manage' | 'edit' | 'view' | 'none';

export type Book = {
  book_id: string;
  owner_user_id: string;
  /** Caller's effective grant (see {@link BookAccessLevel}). Present on the single-book read. */
  access_level?: BookAccessLevel;
  title: string;
  description?: string | null;
  original_language?: string | null;
  summary?: string | null;
  chapter_count: number;
  has_cover?: boolean;
  visibility?: Visibility;
  genre_tags: string[];
  lifecycle_state: 'active' | 'trashed' | 'purge_pending';
  /** W6 (G3) — the world this book is grouped into, or null/undefined when
   *  standalone. Set on the single-book read; drives the "open in world"
   *  backlink + the SettingsTab world picker's current value. */
  world_id?: string | null;
  created_at?: string;
  updated_at?: string;
};

export type Chapter = {
  chapter_id: string;
  book_id: string;
  title?: string | null;
  original_filename: string;
  original_language: string;
  content_type: string;
  byte_size: number;
  sort_order: number;
  draft_updated_at?: string | null;
  draft_revision_count?: number;
  lifecycle_state: 'active' | 'trashed' | 'purge_pending';
  trashed_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  // Canon Model (CM1): editorial lifecycle. New chapters start 'draft'; existing
  // chapters were migrated to 'published'. NOTE: publish no longer decides knowledge-
  // graph membership — see kg_indexed_revision_id below (WS-0.2+).
  editorial_status?: 'draft' | 'published';
  published_revision_id?: string | null;
  // Publish-independent KG indexing (spec 2026-07-11). "Is this chapter in my knowledge
  // graph?" is now a SEPARATE question from "is it published":
  //   kg_indexed_revision_id — the revision the knowledge layer reflects. Non-null ⇒ the
  //                            chapter is in the KG (possibly as a DRAFT the user
  //                            explicitly indexed).
  //   kg_exclude             — the user's explicit "keep this out of my knowledge graph"
  //                            (also retracts what was already extracted).
  // Both are optional: an older book-service may not return them, so every consumer must
  // tolerate `undefined` rather than assume the field exists.
  kg_indexed_revision_id?: string | null;
  kg_exclude?: boolean;
  // 15_chapter_browser.md CB3 — multilingual char/word count. Additive + optional:
  // the BE column/backfill (Phase A) may not have landed yet on a given deploy, so
  // every consumer must tolerate `undefined` rather than assume the field exists.
  word_count?: number;
  // S-02 — the manuscript part (act/volume) this chapter is homed in, or null when it
  // lives in the flat manuscript. Additive + optional: an older book-service may not
  // return it, so the navigator must tolerate `undefined` (treated as unassigned).
  part_id?: string | null;
};

// Shared base from @/api (relative '' default → proxy→gateway). For multipart
// upload / media URLs that bypass apiJson.
const base = apiBase;

export type ChapterListResponse = {
  items: Chapter[];
  total: number;
  limit?: number;
  offset?: number;
};

// Keyset/cursor page (GET /chapters/page). `next_cursor` null on the last page;
// `total` present only on the first page (no cursor) — see #02 navigator.
export type ChapterPage = {
  items: Chapter[];
  next_cursor: string | null;
  total: number | null;
};

// 22-C1 — a parse-leaf scene from book-service (`scenes`), the INDEX/identity side of a
// scene (SC1/SC2). This is book-service's TRUTH (per-book, E0-shared), distinct from the
// composition `OutlineNode` spec/intent side. `source_scene_id` is the join key back onto
// composition's spec (`source_scene_id → outline_node.id`); NULL ⇒ "written, not decompiled"
// (or anchor lost) — the union row shape the scene-browser renders (spec 22 §GUI, BPS-13).
export type Scene = {
  // book-service's public scene list names the identity `scene_id` (NOT `id`) — the row's PK is
  // exposed under that key so it never collides with `source_scene_id` (the spec node it links to).
  // Matching the wire name here is load-bearing: a mismatch renders every row with a `undefined` key.
  scene_id: string;
  book_id: string;
  chapter_id: string;
  sort_order: number;
  title: string | null;      // a parsed heading (SC1) — NEVER the authored intent title
  path: string;
  leaf_text: string;         // read-only projection of chapter.body (D17) — never editable
  content_hash: string;
  source_scene_id: string | null; // → outline_node.id; null = not-yet-decompiled / anchor lost
  parse_version: number;
  lifecycle_state: string;
  created_at?: string;
  updated_at?: string;
};

// Keyset/cursor page of book-wide scenes (GET /v1/books/{id}/scenes). Same envelope as
// ChapterPage: `next_cursor` null on the last page; `total` on the first page only.
export type ScenePage = {
  items: Scene[];
  next_cursor: string | null;
  total: number | null;
};

async function apiForm<T>(path: string, form: FormData, token: string): Promise<T> {
  const res = await fetch(`${base()}${path}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const body = text ? JSON.parse(text) : null;
  if (!res.ok) {
    throw Object.assign(new Error(body?.message || res.statusText), {
      status: res.status,
      code: body?.code,
    });
  }
  return body as T;
}

async function apiAuthedFetch(path: string, token: string): Promise<Response> {
  return fetch(`${base()}${path}`, {
    method: 'GET',
    headers: { Authorization: `Bearer ${token}` },
  });
}

export const booksApi = {
  listBooks(token: string, params?: { limit?: number; offset?: number }) {
    const qs = new URLSearchParams();
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.offset) qs.set('offset', String(params.offset));
    const query = qs.toString();
    return apiJson<{ items: Book[]; total: number }>(`/v1/books${query ? `?${query}` : ''}`, { token });
  },
  listTrash(token: string) {
    return apiJson<{ items: Book[]; total: number }>('/v1/books/trash', { token });
  },
  createBook(
    token: string,
    payload: { title: string; description?: string; original_language?: string; summary?: string; genre_tags?: string[] },
  ) {
    return apiJson<Book>('/v1/books', { method: 'POST', token, body: JSON.stringify(payload) });
  },
  getBook(token: string, bookId: string) {
    return apiJson<Book>(`/v1/books/${bookId}`, { token });
  },
  patchBook(token: string, bookId: string, payload: Record<string, unknown>) {
    return apiJson<Book>(`/v1/books/${bookId}`, { method: 'PATCH', token, body: JSON.stringify(payload) });
  },
  trashBook(token: string, bookId: string) {
    return apiJson<void>(`/v1/books/${bookId}`, { method: 'DELETE', token });
  },
  restoreBook(token: string, bookId: string) {
    return apiJson<Book>(`/v1/books/${bookId}/restore`, { method: 'POST', token });
  },
  purgeBook(token: string, bookId: string) {
    return apiJson<void>(`/v1/books/${bookId}/purge`, { method: 'DELETE', token });
  },
  uploadCover(token: string, bookId: string, file: File) {
    const form = new FormData();
    form.append('file', file);
    return apiForm<Book>(`/v1/books/${bookId}/cover`, form, token);
  },
  listChapters(
    token: string,
    bookId: string,
    params?: {
      lifecycle_state?: string;
      original_language?: string;
      editorial_status?: string;
      q?: string;
      sort_order?: number;
      // 15_chapter_browser.md CB7 — sort key for the chapter-browser's sort dropdown
      // ('sort_order' | 'updated_at' | 'word_count' | 'lifecycle_state'). Forward-
      // compatible: the BE (Phase A, landing in parallel) may not read this param
      // yet — an unrecognized query param is a harmless no-op there, never a 400.
      sort?: string;
      limit?: number;
      offset?: number;
    },
  ) {
    const qs = new URLSearchParams();
    if (params?.lifecycle_state) qs.set('lifecycle_state', params.lifecycle_state);
    if (params?.original_language) qs.set('original_language', params.original_language);
    if (params?.editorial_status) qs.set('editorial_status', params.editorial_status);
    if (params?.q) qs.set('q', params.q);
    if (params?.sort_order !== undefined) qs.set('sort_order', String(params.sort_order));
    if (params?.sort) qs.set('sort', params.sort);
    if (params?.limit !== undefined) qs.set('limit', String(params.limit));
    if (params?.offset !== undefined) qs.set('offset', String(params.offset));
    const query = qs.toString();
    return apiJson<ChapterListResponse>(`/v1/books/${bookId}/chapters${query ? `?${query}` : ''}`, { token });
  },

  // #02 manuscript navigator — keyset/cursor page of chapters (scales to 10k+).
  // First page (no cursor) also returns `total` so the virtual scrollbar can size itself.
  //
  // 15_chapter_browser.md CB7 — `sort` here is intentionally NARROWER than
  // listChapters' (only 'sort_order' | 'updated_at'): true cursor-stable paging
  // needs a monotonic key, which word_count/lifecycle_state don't have. Passing
  // either of those 400s server-side — callers wanting those sorts should use
  // listChapters (offset-paginated) instead.
  listChaptersPage(
    token: string,
    bookId: string,
    opts: { cursor?: string | null; limit?: number; q?: string; original_language?: string; sort?: 'sort_order' | 'updated_at' } = {},
  ) {
    const qs = new URLSearchParams();
    if (opts.cursor) qs.set('cursor', opts.cursor);
    if (opts.limit !== undefined) qs.set('limit', String(opts.limit));
    if (opts.q) qs.set('q', opts.q);
    if (opts.original_language) qs.set('original_language', opts.original_language);
    if (opts.sort) qs.set('sort', opts.sort);
    const query = qs.toString();
    return apiJson<ChapterPage>(`/v1/books/${bookId}/chapters/page${query ? `?${query}` : ''}`, { token });
  },

  // 22-C1 — the book-wide scene list (VIEW-gated), keyset-paged by (chapter_id, sort_order).
  // This is the scene-browser's IDENTITY source; the panel joins each row onto composition's
  // spec via `source_scene_id`. Server-side filters: `chapter_id`, `source_scene_id` (the
  // go-to-prose join key, 28 AN-5b), and `q` (a bounded ILIKE over title + leaf_text). Status/
  // POV/beat filters are CLIENT-side — they live in composition, not here (spec 22 §GUI).
  listScenes(
    token: string,
    bookId: string,
    opts: { cursor?: string | null; limit?: number; chapter_id?: string; source_scene_id?: string; q?: string } = {},
  ) {
    const qs = new URLSearchParams();
    if (opts.cursor) qs.set('cursor', opts.cursor);
    if (opts.limit !== undefined) qs.set('limit', String(opts.limit));
    if (opts.chapter_id) qs.set('chapter_id', opts.chapter_id);
    if (opts.source_scene_id) qs.set('source_scene_id', opts.source_scene_id);
    if (opts.q) qs.set('q', opts.q);
    const query = qs.toString();
    return apiJson<ScenePage>(`/v1/books/${bookId}/scenes${query ? `?${query}` : ''}`, { token });
  },
  /** Chapter Browser A3 — bulk lifecycle change (trash/restore/purge many chapters
   *  in one call). Response is a PER-ID outcome array (CB5) — a partial failure
   *  across N chapters is never a single all-or-nothing result; callers must
   *  check each `results[i].ok` rather than assume the whole batch succeeded. */
  bulkUpdateChapterStatus(
    token: string,
    bookId: string,
    chapterIds: string[],
    lifecycleState: 'active' | 'trashed' | 'purge_pending',
  ): Promise<{ results: Array<{ chapter_id: string; ok: boolean; error?: string }> }> {
    return apiJson<{ results: Array<{ chapter_id: string; ok: boolean; error?: string }> }>(
      `/v1/books/${bookId}/chapters/bulk-status`,
      { method: 'PATCH', token, body: JSON.stringify({ chapter_ids: chapterIds, lifecycle_state: lifecycleState }) },
    );
  },
  /** Chapter Browser A4 — bulk zip export. POST (not GET+query) because a large
   *  multi-select can carry hundreds of UUIDs past typical URL-length limits.
   *  Returns a Blob (mirrors downloadRaw's fetch→blob handling) — the caller
   *  creates an object URL and triggers the browser download, same pattern as
   *  any other binary-response endpoint in this file. Any requested id that
   *  couldn't be exported is listed in a `_errors.txt` entry INSIDE the zip
   *  (the binary response can't carry a JSON per-id outcome alongside it). */
  async bulkExportChaptersZip(token: string, bookId: string, chapterIds: string[]): Promise<Blob> {
    const res = await fetch(`${base()}/v1/books/${bookId}/chapters/export-zip`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ chapter_ids: chapterIds }),
    });
    if (!res.ok) {
      const text = await res.text();
      let message = res.statusText;
      try {
        const body = JSON.parse(text) as { message?: string };
        message = body.message || message;
      } catch {
        // keep status text fallback
      }
      throw Object.assign(new Error(message), { status: res.status });
    }
    return res.blob();
  },
  createChapterUpload(
    token: string,
    bookId: string,
    payload: { file: File; original_language: string; title?: string; sort_order?: number },
  ) {
    const form = new FormData();
    form.append('file', payload.file);
    form.append('original_language', payload.original_language);
    if (payload.title) form.append('title', payload.title);
    if (payload.sort_order !== undefined) form.append('sort_order', String(payload.sort_order));
    return apiForm<Chapter>(`/v1/books/${bookId}/chapters`, form, token);
  },
  createChapter(token: string, bookId: string, payload: { file: File; original_language: string; title?: string; sort_order?: number }) {
    return this.createChapterUpload(token, bookId, payload);
  },
  /** Bulk-create plain-text chapters in one request (folder/large import). The
   *  caller sends naturally-sorted, exclude-filtered batches SEQUENTIALLY so the
   *  server's monotonic sort_order preserves order. Returns the created count. */
  bulkCreateChapters(
    token: string,
    bookId: string,
    chapters: { original_filename: string; content: string; title?: string }[],
    originalLanguage = 'auto',
  ): Promise<{ chapters_created: number; skipped_existing: number; book_id: string }> {
    return apiJson<{ chapters_created: number; skipped_existing: number; book_id: string }>(
      `/v1/books/${bookId}/chapters/bulk`,
      { method: 'POST', token, body: JSON.stringify({ chapters, original_language: originalLanguage }) },
    );
  },
  createChapterEditor(
    token: string,
    bookId: string,
    payload: { original_language: string; title?: string; sort_order?: number; body?: string },
  ) {
    return apiJson<Chapter>(`/v1/books/${bookId}/chapters`, {
      method: 'POST',
      token,
      body: JSON.stringify(payload),
    });
  },
  async downloadRaw(token: string, bookId: string, chapterId: string) {
    const res = await apiAuthedFetch(`/v1/books/${bookId}/chapters/${chapterId}/export`, token);
    if (!res.ok) {
      const text = await res.text();
      let message = res.statusText;
      try {
        const body = JSON.parse(text) as { message?: string };
        message = body.message || message;
      } catch {
        // keep status text fallback
      }
      throw new Error(message);
    }
    return res.blob();
  },
  getChapter(token: string, bookId: string, chapterId: string) {
    return apiJson<Chapter>(`/v1/books/${bookId}/chapters/${chapterId}`, { token });
  },
  async getOriginalContent(token: string, bookId: string, chapterId: string): Promise<string> {
    const res = await apiAuthedFetch(`/v1/books/${bookId}/chapters/${chapterId}/content`, token);
    if (!res.ok) throw new Error('Failed to load original content');
    return res.text();
  },
  patchChapter(token: string, bookId: string, chapterId: string, payload: Record<string, unknown>) {
    return apiJson<Chapter>(`/v1/books/${bookId}/chapters/${chapterId}`, {
      method: 'PATCH',
      token,
      body: JSON.stringify(payload),
    });
  },
  trashChapter(token: string, bookId: string, chapterId: string) {
    return apiJson<void>(`/v1/books/${bookId}/chapters/${chapterId}`, { method: 'DELETE', token });
  },
  // Canon Model CM-FE: publish snapshots the current server draft as the
  // pinned canon revision (canon = published) and emits chapter.published →
  // KG + L3 passages extract at that revision. `expectedDraftVersion` echoes
  // the editor's draft_version so a concurrent edit elsewhere → 409
  // CHAPTER_DRAFT_CONFLICT instead of silently publishing stale content.
  publishChapter(token: string, bookId: string, chapterId: string, expectedDraftVersion?: number) {
    return apiJson<Chapter>(`/v1/books/${bookId}/chapters/${chapterId}/publish`, {
      method: 'POST',
      token,
      body: JSON.stringify(
        expectedDraftVersion !== undefined ? { expected_draft_version: expectedDraftVersion } : {},
      ),
    });
  },
  // Unpublish flips the chapter back to draft. It is an EDITORIAL act only.
  //
  // ⚠️ It NO LONGER retracts the knowledge graph (WS-0.8, spec §3.8 / acceptance #9).
  // Publishing and indexing are independent now, so a user who added a chapter to their
  // knowledge graph and later unpublished it for editorial reasons keeps their KG. The
  // chapter's passages are demoted to non-canon, but its facts and its index request
  // survive. To actually remove a chapter from the graph, use setChapterKgExclude(true).
  unpublishChapter(token: string, bookId: string, chapterId: string) {
    return apiJson<Chapter>(`/v1/books/${bookId}/chapters/${chapterId}/unpublish`, {
      method: 'POST',
      token,
    });
  },
  // "Add to knowledge" — index this chapter into the knowledge graph. Works on a DRAFT;
  // publishing is neither required nor implied. Emits chapter.kg_indexed → the graph
  // extracts + L3 passages ingest at the pinned revision. Re-indexing an unchanged draft
  // reuses the existing revision and costs nothing (`reused_revision: true`).
  indexChapter(token: string, bookId: string, chapterId: string) {
    return apiJson<{
      chapter_id: string;
      revision_id: string;
      reused_revision: boolean;
      reparse?: { unchanged: number; updated: number; inserted: number; deleted: number };
    }>(`/v1/books/${bookId}/chapters/${chapterId}/index`, { method: 'POST', token });
  },
  // Include/exclude a chapter from the knowledge graph.
  // `true` KEEPS IT OUT and RETRACTS anything already extracted from it (facts +
  // passages) — this is the real "forget this chapter". `false` merely re-allows
  // indexing; it does NOT re-index by itself (call indexChapter for that), because a
  // toggle that silently re-ingests the user's prose is a privacy surprise.
  setChapterKgExclude(token: string, bookId: string, chapterId: string, kgExclude: boolean) {
    return apiJson<{ chapter_id: string; kg_exclude: boolean }>(
      `/v1/books/${bookId}/chapters/${chapterId}/kg-exclude`,
      { method: 'PUT', token, body: JSON.stringify({ kg_exclude: kgExclude }) },
    );
  },
  restoreChapter(token: string, bookId: string, chapterId: string) {
    return apiJson<Chapter>(`/v1/books/${bookId}/chapters/${chapterId}/restore`, { method: 'POST', token });
  },
  purgeChapter(token: string, bookId: string, chapterId: string) {
    return apiJson<void>(`/v1/books/${bookId}/chapters/${chapterId}/purge`, { method: 'DELETE', token });
  },
  getDraft(token: string, bookId: string, chapterId: string) {
    return apiJson<{
      chapter_id: string;
      body: any;
      draft_format: string;
      draft_updated_at: string;
      draft_version: number;
      text_content: string | null;
    }>(`/v1/books/${bookId}/chapters/${chapterId}/draft`, { token });
  },
  patchDraft(
    token: string,
    bookId: string,
    chapterId: string,
    payload: { body: any; body_format?: string; commit_message?: string; expected_draft_version?: number },
  ) {
    return apiJson(`/v1/books/${bookId}/chapters/${chapterId}/draft`, {
      method: 'PATCH',
      token,
      body: JSON.stringify(payload),
    });
  },
  listRevisions(token: string, bookId: string, chapterId: string, params?: { limit?: number; offset?: number }) {
    const qs = new URLSearchParams();
    if (params?.limit !== undefined) qs.set('limit', String(params.limit));
    if (params?.offset !== undefined) qs.set('offset', String(params.offset));
    const query = qs.toString();
    return apiJson<{ items: Array<{ revision_id: string; created_at: string; message?: string }>; total: number }>(
      `/v1/books/${bookId}/chapters/${chapterId}/revisions${query ? `?${query}` : ''}`,
      { token },
    );
  },
  getRevision(token: string, bookId: string, chapterId: string, revisionId: string) {
    return apiJson<{ revision_id: string; created_at: string; message?: string; body: any; body_format: string; text_content: string | null }>(
      `/v1/books/${bookId}/chapters/${chapterId}/revisions/${revisionId}`,
      { token },
    );
  },
  restoreRevision(token: string, bookId: string, chapterId: string, revisionId: string) {
    return apiJson(`/v1/books/${bookId}/chapters/${chapterId}/revisions/${revisionId}/restore`, {
      method: 'POST',
      token,
    });
  },
  // Compare two revisions of the same chapter (server-computed line diff).
  compareRevisions(token: string, bookId: string, chapterId: string, left: string, right: string) {
    const qs = new URLSearchParams({ left, right }).toString();
    return apiJson<RevisionCompare>(
      `/v1/books/${bookId}/chapters/${chapterId}/revisions/compare?${qs}`,
      { token },
    );
  },
  getCover(token: string, bookId: string): Promise<Blob> {
    return fetch(`${base()}/v1/books/${bookId}/cover`, {
      headers: { Authorization: `Bearer ${token}` },
    }).then((r) => {
      if (!r.ok) throw new Error('cover not found');
      return r.blob();
    });
  },
  deleteCover(token: string, bookId: string) {
    return apiJson<void>(`/v1/books/${bookId}/cover`, { method: 'DELETE', token });
  },
  getSharing(token: string, bookId: string) {
    return apiJson<{ book_id: string; visibility: 'private' | 'unlisted' | 'public'; unlisted_access_token?: string }>(
      `/v1/sharing/books/${bookId}`,
      { token },
    );
  },
  patchSharing(
    token: string,
    bookId: string,
    payload: { visibility?: 'private' | 'unlisted' | 'public'; rotate_unlisted_token?: boolean },
  ) {
    return apiJson(`/v1/sharing/books/${bookId}`, { method: 'PATCH', token, body: JSON.stringify(payload) });
  },

  // ── E0-5 collaborators (owner-only; book-service orchestrates email-invite) ──
  listCollaborators(token: string, bookId: string) {
    return apiJson<{ collaborators: Collaborator[] }>(`/v1/books/${bookId}/collaborators`, { token });
  },
  // Invite by EMAIL — book-service resolves it to a user via auth-service (404 if
  // no such active user). Returns the resolved {user_id, role, display_name}.
  inviteCollaborator(token: string, bookId: string, payload: { email: string; role: CollaboratorRole }) {
    return apiJson<{ user_id: string; role: CollaboratorRole; display_name: string }>(
      `/v1/books/${bookId}/collaborators`,
      { method: 'POST', token, body: JSON.stringify(payload) },
    );
  },
  changeCollaboratorRole(token: string, bookId: string, userId: string, role: CollaboratorRole) {
    return apiJson<{ user_id: string; role: CollaboratorRole }>(
      `/v1/books/${bookId}/collaborators/${userId}`,
      { method: 'PUT', token, body: JSON.stringify({ role }) },
    );
  },
  removeCollaborator(token: string, bookId: string, userId: string) {
    return apiJson<{ status: string }>(`/v1/books/${bookId}/collaborators/${userId}`, {
      method: 'DELETE',
      token,
    });
  },
  listCatalog(params?: { limit?: number; offset?: number; q?: string }) {
    const qs = new URLSearchParams();
    if (params?.limit !== undefined) qs.set('limit', String(params.limit));
    if (params?.offset !== undefined) qs.set('offset', String(params.offset));
    if (params?.q) qs.set('q', params.q);
    const query = qs.toString();
    return apiJson<{
      items: Array<{ book_id: string; title: string; summary_excerpt?: string; original_language?: string; chapter_count?: number }>;
      total: number;
    }>(
      `/v1/catalog/books${query ? `?${query}` : ''}`,
    );
  },
  getCatalogBook(bookId: string) {
    return apiJson<{ book_id: string; title: string; summary_excerpt?: string; original_language?: string; chapter_count?: number }>(
      `/v1/catalog/books/${bookId}`,
    );
  },
  listCatalogChapters(bookId: string, params?: { limit?: number; offset?: number }) {
    const qs = new URLSearchParams();
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.offset) qs.set('offset', String(params.offset));
    const query = qs.toString();
    return apiJson<{ items: Array<{ chapter_id: string; title?: string | null; sort_order: number; original_language: string }>; total: number; limit?: number; offset?: number }>(
      `/v1/catalog/books/${bookId}/chapters${query ? `?${query}` : ''}`,
    );
  },
  getCatalogChapter(bookId: string, chapterId: string) {
    return apiJson<{ chapter_id: string; title?: string | null; sort_order: number; original_language: string; body: string }>(
      `/v1/catalog/books/${bookId}/chapters/${chapterId}`,
    );
  },
  getUnlisted(accessToken: string) {
    return apiJson<{
      book_id: string; title: string; description?: string | null;
      summary_excerpt?: string | null; original_language?: string | null;
      has_cover?: boolean; cover_url?: string | null;
      chapter_count?: number; visibility?: string;
    }>(
      `/v1/sharing/unlisted/${accessToken}`,
    );
  },
  listUnlistedChapters(accessToken: string, params?: { limit?: number; offset?: number }) {
    const qs = new URLSearchParams();
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.offset) qs.set('offset', String(params.offset));
    const query = qs.toString();
    return apiJson<{
      items: Array<{
        chapter_id: string; title?: string | null; sort_order: number;
        original_language: string; word_count_estimate?: number;
      }>;
      total: number; limit?: number; offset?: number;
    }>(
      `/v1/sharing/unlisted/${accessToken}/chapters${query ? `?${query}` : ''}`,
    );
  },
  getUnlistedChapter(accessToken: string, chapterId: string) {
    return apiJson<{
      chapter_id: string; title?: string | null; sort_order: number;
      original_language: string; body: any; text_content?: string;
    }>(
      `/v1/sharing/unlisted/${accessToken}/chapters/${chapterId}`,
    );
  },

  /** Upload chapter media (image) to MinIO. Uses XHR for progress tracking. */
  uploadChapterMedia(
    token: string,
    bookId: string,
    chapterId: string,
    file: File,
    onProgress?: (pct: number) => void,
    blockId?: string,
  ): Promise<{ url: string; object_key: string; filename: string; size: number; content_type: string; version?: number; version_id?: string }> {
    return new Promise((resolve, reject) => {
      const form = new FormData();
      form.append('file', file);
      if (blockId) form.append('block_id', blockId);

      const xhr = new XMLHttpRequest();
      xhr.open('POST', `${base()}/v1/books/${bookId}/chapters/${chapterId}/media`);
      xhr.setRequestHeader('Authorization', `Bearer ${token}`);

      if (onProgress) {
        xhr.upload.addEventListener('progress', (e) => {
          if (e.lengthComputable) {
            onProgress(Math.round((e.loaded / e.total) * 100));
          }
        });
      }

      xhr.addEventListener('load', () => {
        try {
          const body = JSON.parse(xhr.responseText);
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve(body);
          } else {
            reject(Object.assign(new Error(body?.message || xhr.statusText), {
              status: xhr.status,
              code: body?.code,
            }));
          }
        } catch {
          reject(new Error('Invalid response'));
        }
      });

      xhr.addEventListener('error', () => reject(new Error('Network error')));
      xhr.addEventListener('abort', () => reject(new Error('Upload cancelled')));

      xhr.send(form);
    });
  },

  /** Generate AI TTS audio for chapter blocks via AU-03 endpoint. */
  async generateAudio(
    token: string,
    bookId: string,
    chapterId: string,
    body: {
      language: string;
      voice: string;
      model_ref: string;
      model_source?: string;
      provider?: string;
      blocks: Array<{ index: number; text: string }>;
    },
  ): Promise<{ segments: Array<{ block_index: number; media_url: string; media_key: string; duration_ms: number }>; errors: Array<{ block_index: number; error: string }> }> {
    const res = await fetch(`${base()}/v1/books/${bookId}/chapters/${chapterId}/audio/generate`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw Object.assign(new Error(data?.message || res.statusText), { status: res.status, code: data?.code });
    return data;
  },

  /** Upload block audio (mp3/wav/ogg/webm/m4a) to MinIO via AU-02 endpoint. */
  uploadBlockAudio(
    token: string,
    bookId: string,
    chapterId: string,
    file: File,
    blockIndex: number,
    subtitle?: string,
    onProgress?: (pct: number) => void,
  ): Promise<{ audio_url: string; media_key: string; duration_ms: number; size_bytes: number; content_type: string; subtitle: string }> {
    return new Promise((resolve, reject) => {
      const form = new FormData();
      form.append('file', file);
      form.append('block_index', String(blockIndex));
      if (subtitle) form.append('subtitle', subtitle);

      const xhr = new XMLHttpRequest();
      xhr.open('POST', `${base()}/v1/books/${bookId}/chapters/${chapterId}/block-audio`);
      xhr.setRequestHeader('Authorization', `Bearer ${token}`);

      if (onProgress) {
        xhr.upload.addEventListener('progress', (e) => {
          if (e.lengthComputable) {
            onProgress(Math.round((e.loaded / e.total) * 100));
          }
        });
      }

      xhr.addEventListener('load', () => {
        try {
          const body = JSON.parse(xhr.responseText);
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve(body);
          } else {
            reject(Object.assign(new Error(body?.message || xhr.statusText), {
              status: xhr.status,
              code: body?.code,
            }));
          }
        } catch {
          reject(new Error('Invalid response'));
        }
      });

      xhr.addEventListener('error', () => reject(new Error('Network error')));
      xhr.addEventListener('abort', () => reject(new Error('Upload cancelled')));

      xhr.send(form);
    });
  },

  // ── Media Versions ──────────────────────────────────────────────────

  async listMediaVersions(token: string, bookId: string, chapterId: string, blockId: string) {
    const res = await apiAuthedFetch(
      `/v1/books/${bookId}/chapters/${chapterId}/media-versions?block_id=${encodeURIComponent(blockId)}`,
      token,
    );
    const body = await res.json();
    if (!res.ok) throw Object.assign(new Error(body?.message || res.statusText), { status: res.status });
    return body as { items: MediaVersion[] };
  },

  async createMediaVersion(
    token: string, bookId: string, chapterId: string,
    body: { block_id: string; action: string; changes: string[]; prompt_snapshot?: string; caption_snapshot?: string; media_ref?: string },
  ) {
    const res = await fetch(`${base()}/v1/books/${bookId}/chapters/${chapterId}/media-versions`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw Object.assign(new Error(data?.message || res.statusText), { status: res.status });
    return data as MediaVersion;
  },

  async generateImage(
    token: string, bookId: string, chapterId: string,
    body: { block_id: string; prompt: string; model_source: string; model_ref: string; size?: string },
  ): Promise<{ url: string; object_key: string; version: number; version_id: string; ai_model: string; size: number; content_type: string }> {
    const res = await fetch(`${base()}/v1/books/${bookId}/chapters/${chapterId}/media-generate`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw Object.assign(new Error(data?.message || res.statusText), { status: res.status, code: data?.code });
    return data;
  },

  async deleteMediaVersion(token: string, bookId: string, chapterId: string, versionId: string) {
    const res = await fetch(`${base()}/v1/books/${bookId}/chapters/${chapterId}/media-versions/${versionId}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok && res.status !== 204) {
      const data = await res.json().catch(() => null);
      throw Object.assign(new Error(data?.message || res.statusText), { status: res.status });
    }
  },

  // ── Reading Analytics ──────────────────────────────────────────────────

  async getReadingProgress(token: string, bookId: string): Promise<{ items: ReadingProgress[] }> {
    const res = await fetch(`${base()}/v1/books/${bookId}/progress`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return { items: [] };
    return res.json();
  },

  async getReadingHistory(token: string): Promise<{ items: ReadingHistoryEntry[] }> {
    const res = await fetch(`${base()}/v1/books/reading-history`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return { items: [] };
    return res.json();
  },

  async getBookStats(token: string, bookId: string): Promise<BookStats> {
    const res = await fetch(`${base()}/v1/books/${bookId}/stats`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return { total_readers: 0, avg_time_ms: 0, avg_scroll_depth: 0 };
    return res.json();
  },

  // ── Import (.docx/.epub/.pdf) ─────────────────────────────────────────

  startImport(
    token: string,
    bookId: string,
    file: File,
    originalLanguage?: string,
    onProgress?: (pct: number) => void,
    // docs/specs/2026-07-06-pdf-book-import.md — only meaningful for a
    // .pdf file; every existing docx/epub/txt/md call site omits this.
    pdfOptions?: {
      pagesPerChunk: number;
      captionImages: boolean;
      modelSource?: string;
      modelRef?: string;
    },
  ): Promise<ImportJob> {
    return new Promise((resolve, reject) => {
      const form = new FormData();
      form.append('file', file);
      if (originalLanguage) form.append('original_language', originalLanguage);
      if (pdfOptions) {
        form.append('pages_per_chunk', String(pdfOptions.pagesPerChunk));
        form.append('caption_images', String(pdfOptions.captionImages));
        if (pdfOptions.captionImages) {
          if (pdfOptions.modelSource) form.append('model_source', pdfOptions.modelSource);
          if (pdfOptions.modelRef) form.append('model_ref', pdfOptions.modelRef);
        }
      }

      const xhr = new XMLHttpRequest();
      xhr.open('POST', `${base()}/v1/books/${bookId}/import`);
      xhr.setRequestHeader('Authorization', `Bearer ${token}`);

      if (onProgress) {
        xhr.upload.addEventListener('progress', (e) => {
          if (e.lengthComputable) {
            onProgress(Math.round((e.loaded / e.total) * 100));
          }
        });
      }

      xhr.addEventListener('load', () => {
        try {
          const body = JSON.parse(xhr.responseText);
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve(body);
          } else {
            reject(Object.assign(new Error(body?.message || xhr.statusText), {
              status: xhr.status,
              code: body?.code,
            }));
          }
        } catch {
          reject(new Error('Invalid response'));
        }
      });

      xhr.addEventListener('error', () => reject(new Error('Network error')));
      xhr.addEventListener('abort', () => reject(new Error('Upload cancelled')));

      xhr.send(form);
    });
  },

  getImportJob(token: string, bookId: string, importId: string) {
    return apiJson<ImportJob>(`/v1/books/${bookId}/imports/${importId}`, { token });
  },

  listImportJobs(token: string, bookId: string) {
    return apiJson<{ imports: ImportJob[] }>(`/v1/books/${bookId}/imports`, { token });
  },

  /** Cheap page-count check for a PDF, called right after file select —
   * before the user configures pages_per_chunk (docs/specs/2026-07-06-pdf-book-import.md).
   * Rejects encrypted/corrupted PDFs with a 422 (surfaced as a thrown Error). */
  pdfPeek(token: string, bookId: string, file: File): Promise<{ page_count: number }> {
    return new Promise((resolve, reject) => {
      const form = new FormData();
      form.append('file', file);
      const xhr = new XMLHttpRequest();
      xhr.open('POST', `${base()}/v1/books/${bookId}/import/pdf-peek`);
      xhr.setRequestHeader('Authorization', `Bearer ${token}`);
      xhr.addEventListener('load', () => {
        try {
          const body = JSON.parse(xhr.responseText);
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve(body);
          } else {
            reject(Object.assign(new Error(body?.message || xhr.statusText), {
              status: xhr.status,
              code: body?.code,
            }));
          }
        } catch {
          reject(new Error('Invalid response'));
        }
      });
      xhr.addEventListener('error', () => reject(new Error('Network error')));
      xhr.send(form);
    });
  },
};

// E0-5 — a book collaborator (owner grants view|edit|manage). display_name is
// best-effort from auth-service ("" when unknown).
export type CollaboratorRole = 'view' | 'edit' | 'manage';
export type Collaborator = {
  user_id: string;
  role: CollaboratorRole;
  granted_by: string;
  created_at: string;
  updated_at: string;
  display_name: string;
};

export type ReadingProgress = {
  chapter_id: string;
  read_at: string;
  time_spent_ms: number;
  scroll_depth: number;
  read_count: number;
};

export type BookStats = {
  total_readers: number;
  avg_time_ms: number;
  avg_scroll_depth: number;
};

export type ReadingHistoryEntry = {
  book_id: string;
  chapter_id: string;
  read_at: string;
  time_spent_ms: number;
  scroll_depth: number;
  read_count: number;
  book_title: string;
  chapter_title: string | null;
  sort_order: number | null;
};

export type ImportJob = {
  id: string;
  book_id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  filename: string;
  file_format: string;
  file_size: number;
  chapters_created: number;
  error: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
};

// ── Types ───────────────────────────────────────────────────────────────

export type MediaVersion = {
  id: string;
  block_id: string;
  version: number;
  action: string;
  changes: string[];
  media_ref: string | null;
  media_url?: string | null;
  prompt_snapshot: string;
  caption_snapshot: string;
  ai_model: string | null;
  content_type: string | null;
  size_bytes: number | null;
  created_at: string;
};
