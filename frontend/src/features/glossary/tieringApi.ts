// G6 — typed client for the genre·kind·attribute TIERED surface (G1–G5 backend).
// Standards (System read-only + User CRUD) · Book (adopt + ontology + book-tier CRUD)
// · Sync (diff/apply). All calls go through the shared apiJson (JWT in `token`,
// relative `/v1` proxied to the gateway). Kept separate from the legacy `glossaryApi`.

import { apiJson } from '../../api';
import type {
  Genre,
  UserGenreCreate,
  Attribute,
  UserAttributeCreate,
  UserKind,
  UserKindCreate,
  KindGenreLink,
  BookOntology,
  AdoptRequest,
  BookGenreCreate,
  BookKindCreate,
  BookAttributeCreate,
  SyncAvailable,
  SyncApplyItem,
  SyncApplyResult,
  EntityGenres,
  ItemsResponse,
} from './tieringTypes';

const BASE = '/v1/glossary';

export const tieringApi = {
  // ── Standards: genres (System read-only merged + User CRUD) ────────────────

  /** Merged System + caller's User genres (tier-tagged). */
  listGenres(token: string): Promise<Genre[]> {
    return apiJson<ItemsResponse<Genre>>(`${BASE}/genres`, { token }).then((r) => r.items);
  },

  createUserGenre(payload: UserGenreCreate, token: string): Promise<Genre> {
    return apiJson<Genre>(`${BASE}/user-genres`, {
      method: 'POST',
      body: JSON.stringify(payload),
      token,
    });
  },

  patchUserGenre(genreId: string, changes: Partial<UserGenreCreate>, token: string): Promise<Genre> {
    return apiJson<Genre>(`${BASE}/user-genres/${genreId}`, {
      method: 'PATCH',
      body: JSON.stringify(changes),
      token,
    });
  },

  deleteUserGenre(genreId: string, token: string): Promise<void> {
    return apiJson<void>(`${BASE}/user-genres/${genreId}`, { method: 'DELETE', token });
  },

  // ── Standards: attributes (System read-only + User CRUD, attach-by-code) ───

  /** System attributes for a (kind × genre) pair. */
  listSystemAttributes(kindId: string, genreId: string, token: string): Promise<Attribute[]> {
    const qs = new URLSearchParams({ kind_id: kindId, genre_id: genreId });
    return apiJson<ItemsResponse<Attribute>>(`${BASE}/system-attributes?${qs}`, { token }).then(
      (r) => r.items,
    );
  },

  /** Caller's user attributes (optionally filtered by kind/genre). */
  listUserAttributes(
    token: string,
    filter?: { kindId?: string; genreId?: string },
  ): Promise<Attribute[]> {
    const qs = new URLSearchParams();
    if (filter?.kindId) qs.set('kind_id', filter.kindId);
    if (filter?.genreId) qs.set('genre_id', filter.genreId);
    const q = qs.toString();
    return apiJson<ItemsResponse<Attribute>>(`${BASE}/user-attributes${q ? '?' + q : ''}`, {
      token,
    }).then((r) => r.items);
  },

  createUserAttribute(payload: UserAttributeCreate, token: string): Promise<Attribute> {
    return apiJson<Attribute>(`${BASE}/user-attributes`, {
      method: 'POST',
      body: JSON.stringify(payload),
      token,
    });
  },

  patchUserAttribute(
    attrId: string,
    changes: Partial<UserAttributeCreate>,
    token: string,
  ): Promise<Attribute> {
    return apiJson<Attribute>(`${BASE}/user-attributes/${attrId}`, {
      method: 'PATCH',
      body: JSON.stringify(changes),
      token,
    });
  },

  deleteUserAttribute(attrId: string, token: string): Promise<void> {
    return apiJson<void>(`${BASE}/user-attributes/${attrId}`, { method: 'DELETE', token });
  },

  // ── Standards: user kinds + kind↔genre links ───────────────────────────────

  listUserKinds(token: string): Promise<UserKind[]> {
    return apiJson<{ items: UserKind[] }>(`${BASE}/user-kinds`, { token }).then((r) => r.items);
  },

  /** Create a user kind — or clone a System kind into the User tier (same code). */
  createUserKind(payload: UserKindCreate, token: string): Promise<UserKind> {
    return apiJson<UserKind>(`${BASE}/user-kinds`, {
      method: 'POST',
      body: JSON.stringify(payload),
      token,
    });
  },

  patchUserKind(userKindId: string, changes: Partial<UserKindCreate>, token: string): Promise<UserKind> {
    return apiJson<UserKind>(`${BASE}/user-kinds/${userKindId}`, {
      method: 'PATCH',
      body: JSON.stringify(changes),
      token,
    });
  },

  deleteUserKind(userKindId: string, token: string): Promise<void> {
    return apiJson<void>(`${BASE}/user-kinds/${userKindId}`, { method: 'DELETE', token });
  },

  // ── Standards recycle bins (soft-delete restore / purge) ───────────────────

  listUserGenreTrash(token: string): Promise<Genre[]> {
    return apiJson<ItemsResponse<Genre>>(`${BASE}/user-genres-trash`, { token }).then((r) => r.items);
  },
  restoreUserGenre(genreId: string, token: string): Promise<Genre> {
    return apiJson<Genre>(`${BASE}/user-genres-trash/${genreId}/restore`, { method: 'POST', token });
  },
  purgeUserGenre(genreId: string, token: string): Promise<void> {
    return apiJson<void>(`${BASE}/user-genres-trash/${genreId}`, { method: 'DELETE', token });
  },

  listUserKindTrash(token: string): Promise<UserKind[]> {
    return apiJson<ItemsResponse<UserKind>>(`${BASE}/user-kinds-trash`, { token }).then((r) => r.items);
  },
  restoreUserKind(userKindId: string, token: string): Promise<UserKind> {
    return apiJson<UserKind>(`${BASE}/user-kinds-trash/${userKindId}/restore`, { method: 'POST', token });
  },
  purgeUserKind(userKindId: string, token: string): Promise<void> {
    return apiJson<void>(`${BASE}/user-kinds-trash/${userKindId}`, { method: 'DELETE', token });
  },

  listUserKindGenres(userKindId: string, token: string): Promise<KindGenreLink[]> {
    return apiJson<ItemsResponse<KindGenreLink>>(`${BASE}/user-kinds/${userKindId}/genres`, {
      token,
    }).then((r) => r.items);
  },

  /** Replace the full genre set of a user kind. */
  setUserKindGenres(userKindId: string, genreIds: string[], token: string): Promise<KindGenreLink[]> {
    return apiJson<ItemsResponse<KindGenreLink>>(`${BASE}/user-kinds/${userKindId}/genres`, {
      method: 'PUT',
      body: JSON.stringify({ genre_ids: genreIds }),
      token,
    }).then((r) => r.items);
  },

  // ── Book tier: adopt (copy-down) + book-local ontology read ────────────────

  /** R1 pick-list copy-down (Manage). Returns the book ontology after adopt. */
  adoptOntology(bookId: string, req: AdoptRequest, token: string): Promise<BookOntology> {
    return apiJson<BookOntology>(`${BASE}/books/${bookId}/adopt`, {
      method: 'POST',
      body: JSON.stringify(req),
      token,
    });
  },

  /** The book-local, single-tier ontology read (View). */
  getOntology(bookId: string, token: string): Promise<BookOntology> {
    return apiJson<BookOntology>(`${BASE}/books/${bookId}/ontology`, { token });
  },

  // ── Book tier: CRUD (all Manage-gated) ─────────────────────────────────────

  createBookGenre(bookId: string, payload: BookGenreCreate, token: string) {
    return apiJson(`${BASE}/books/${bookId}/ontology/genres`, {
      method: 'POST',
      body: JSON.stringify(payload),
      token,
    });
  },
  patchBookGenre(bookId: string, genreId: string, changes: Record<string, unknown>, token: string) {
    return apiJson(`${BASE}/books/${bookId}/ontology/genres/${genreId}`, {
      method: 'PATCH',
      body: JSON.stringify(changes),
      token,
    });
  },
  deleteBookGenre(bookId: string, genreId: string, token: string): Promise<void> {
    return apiJson<void>(`${BASE}/books/${bookId}/ontology/genres/${genreId}`, {
      method: 'DELETE',
      token,
    });
  },
  /** G-U1: revert an adopted book genre back to its parent (System/User) standard. */
  revertBookGenre(bookId: string, genreId: string, token: string) {
    return apiJson(`${BASE}/books/${bookId}/ontology/genres/${genreId}/revert`, {
      method: 'POST',
      token,
    });
  },

  createBookKind(bookId: string, payload: BookKindCreate, token: string) {
    return apiJson(`${BASE}/books/${bookId}/ontology/kinds`, {
      method: 'POST',
      body: JSON.stringify(payload),
      token,
    });
  },
  patchBookKind(bookId: string, kindId: string, changes: Record<string, unknown>, token: string) {
    return apiJson(`${BASE}/books/${bookId}/ontology/kinds/${kindId}`, {
      method: 'PATCH',
      body: JSON.stringify(changes),
      token,
    });
  },
  deleteBookKind(bookId: string, kindId: string, token: string): Promise<void> {
    return apiJson<void>(`${BASE}/books/${bookId}/ontology/kinds/${kindId}`, {
      method: 'DELETE',
      token,
    });
  },
  /** G-U1: revert an adopted book kind back to its parent (System/User) standard. */
  revertBookKind(bookId: string, kindId: string, token: string) {
    return apiJson(`${BASE}/books/${bookId}/ontology/kinds/${kindId}/revert`, {
      method: 'POST',
      token,
    });
  },
  /** Replace a book kind's active genre links (matrix row). */
  setBookKindGenres(bookId: string, kindId: string, genreIds: string[], token: string) {
    return apiJson(`${BASE}/books/${bookId}/ontology/kinds/${kindId}/genres`, {
      method: 'PUT',
      body: JSON.stringify({ genre_ids: genreIds }),
      token,
    });
  },

  createBookAttribute(bookId: string, payload: BookAttributeCreate, token: string) {
    return apiJson(`${BASE}/books/${bookId}/ontology/attributes`, {
      method: 'POST',
      body: JSON.stringify(payload),
      token,
    });
  },
  patchBookAttribute(bookId: string, attrId: string, changes: Record<string, unknown>, token: string) {
    return apiJson(`${BASE}/books/${bookId}/ontology/attributes/${attrId}`, {
      method: 'PATCH',
      body: JSON.stringify(changes),
      token,
    });
  },
  deleteBookAttribute(bookId: string, attrId: string, token: string): Promise<void> {
    return apiJson<void>(`${BASE}/books/${bookId}/ontology/attributes/${attrId}`, {
      method: 'DELETE',
      token,
    });
  },
  /** G-U1: revert an adopted book attribute back to its parent (System/User) standard. */
  revertBookAttribute(bookId: string, attrId: string, token: string) {
    return apiJson(`${BASE}/books/${bookId}/ontology/attributes/${attrId}/revert`, {
      method: 'POST',
      token,
    });
  },

  /** Replace the book's active-genre set (matrix columns). */
  setActiveGenres(bookId: string, genreIds: string[], token: string) {
    return apiJson(`${BASE}/books/${bookId}/ontology/active-genres`, {
      method: 'PUT',
      body: JSON.stringify({ genre_ids: genreIds }),
      token,
    });
  },

  // ── Sync (G5) ──────────────────────────────────────────────────────────────

  /** Diff the book's adopted standards vs upstream (View). */
  getSyncAvailable(bookId: string, token: string): Promise<SyncAvailable> {
    return apiJson<SyncAvailable>(`${BASE}/books/${bookId}/sync/available`, { token });
  },

  /** Apply per-row sync choices (Manage). */
  applySync(bookId: string, items: SyncApplyItem[], token: string): Promise<SyncApplyResult> {
    return apiJson<SyncApplyResult>(`${BASE}/books/${bookId}/sync/apply`, {
      method: 'POST',
      body: JSON.stringify({ items }),
      token,
    });
  },

  // ── Per-entity genre override (D2) ─────────────────────────────────────────

  getEntityGenres(bookId: string, entityId: string, token: string): Promise<EntityGenres> {
    return apiJson<EntityGenres>(`${BASE}/books/${bookId}/entities/${entityId}/genres`, { token });
  },

  /** Replace an entity's genre override (universal auto-included server-side). */
  setEntityGenres(bookId: string, entityId: string, genreIds: string[], token: string): Promise<EntityGenres> {
    return apiJson<EntityGenres>(`${BASE}/books/${bookId}/entities/${entityId}/genres`, {
      method: 'PUT',
      body: JSON.stringify({ genre_ids: genreIds }),
      token,
    });
  },
};
