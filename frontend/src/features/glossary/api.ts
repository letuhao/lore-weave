import { apiJson } from '../../api';
import type {
  EntityKind,
  EntityNameEntry,
  GlossaryEntity,
  GlossaryEntityListResponse,
  FilterState,
  EvidenceListResponse,
  EvidenceListParams,
  CreateEvidencePayload,
  PatchEvidencePayload,
  Evidence,
  Translation,
  Confidence,
  EntityRevisionSummary,
  EntityRevisionDetail,
  ActionPreview,
  TranslationCandidatesResponse,
  ApplyTranslationsResponse,
  ApplyTranslationItem,
} from './types';

const BASE = '/v1/glossary';

export type BookIntegrityCheck = {
  code: string;
  status: 'ok' | 'warning' | 'error' | 'unavailable';
  severity: 'warning' | 'error';
  count: number;
  message: string;
};

export type BookIntegrityResponse = {
  book_id: string;
  status: 'ok' | 'warning' | 'error';
  checked_at: string;
  checks: BookIntegrityCheck[];
};

export type BookIntegrityRepairResponse = {
  book_id: string;
  fixed_codes: string[];
  fixed_count: number;
  checked_at: string;
};


/** One keyset page of the widened entity-names endpoint (F-H9/PH26). */
type EntityNamesPage = {
  items: EntityNameEntry[];
  truncated: boolean;
  next_cursor: string | null;
};

// API responses from older glossary-service deployments (and rows created before
// the tiered glossary migration) may omit array fields or encode them as null.
// Keep that wire drift at the client boundary so every glossary surface can rely
// on the typed contract and never render `undefined.length`.
function normalizeEntityListResponse(response: GlossaryEntityListResponse): GlossaryEntityListResponse {
  return {
    ...response,
    items: (Array.isArray(response?.items) ? response.items : []).map((item) => ({
      ...item,
      tags: Array.isArray(item.tags) ? item.tags : [],
      kind_labels: Array.isArray(item.kind_labels) ? item.kind_labels : [],
    })),
  };
}

// Legacy entity rows can omit collection fields. Normalize them once at the API
// boundary so the editor and evidence tabs never render `undefined.length`.
function normalizeEntityResponse(entity: GlossaryEntity): GlossaryEntity {
  return {
    ...entity,
    tags: Array.isArray(entity?.tags) ? entity.tags : [],
    attribute_values: (Array.isArray(entity?.attribute_values) ? entity.attribute_values : []).map((value) => ({
      ...value,
      translations: Array.isArray(value.translations) ? value.translations : [],
      evidences: Array.isArray(value.evidences) ? value.evidences : [],
      attribute_def: {
        ...value.attribute_def,
        options: Array.isArray(value.attribute_def?.options) ? value.attribute_def.options : [],
        genre_tags: Array.isArray(value.attribute_def?.genre_tags) ? value.attribute_def.genre_tags : [],
      },
    })),
  };
}

function normalizeEvidenceListResponse(response: EvidenceListResponse): EvidenceListResponse {
  return {
    ...response,
    items: Array.isArray(response?.items) ? response.items : [],
    available_attributes: Array.isArray(response?.available_attributes) ? response.available_attributes : [],
    available_chapters: Array.isArray(response?.available_chapters) ? response.available_chapters : [],
    available_languages: Array.isArray(response?.available_languages) ? response.available_languages : [],
  };
}

export const glossaryApi = {
  getKinds(token: string): Promise<EntityKind[]> {
    return apiJson<unknown>(BASE + '/kinds', { token }).then((response) => {
      if (Array.isArray(response)) return response as EntityKind[];
      if (response && typeof response === 'object' && Array.isArray((response as { items?: unknown }).items)) {
        return (response as { items: EntityKind[] }).items;
      }
      return [];
    });
  },

  checkBookIntegrity(bookId: string, token: string): Promise<BookIntegrityResponse> {
    return apiJson<BookIntegrityResponse>(BASE + '/books/' + bookId + '/integrity', { token });
  },

  repairBookIntegrity(bookId: string, token: string): Promise<BookIntegrityRepairResponse> {
    return apiJson<BookIntegrityRepairResponse>(BASE + '/books/' + bookId + '/integrity/repair', { method: 'POST', token });
  },

  listTranslationLanguages(bookId: string, token: string): Promise<{ languages: string[] }> {
    return apiJson<{ languages: string[] }>(
      `${BASE}/books/${bookId}/translation-languages`,
      { token },
    );
  },

  // S4 — batch translate: list entities with untranslated attrs for a target language.
  listTranslationCandidates(
    bookId: string,
    targetLanguage: string,
    opts: { overwriteMode?: 'missing_only' | 'refresh_machine'; limit?: number; offset?: number },
    token: string,
  ): Promise<TranslationCandidatesResponse> {
    const qs = new URLSearchParams({ target_language: targetLanguage });
    if (opts.overwriteMode) qs.set('overwrite_mode', opts.overwriteMode);
    if (opts.limit) qs.set('limit', String(opts.limit));
    if (opts.offset) qs.set('offset', String(opts.offset));
    return apiJson<TranslationCandidatesResponse>(
      `${BASE}/books/${bookId}/translation-candidates?${qs.toString()}`,
      { token },
    );
  },

  // S4 — batch translate: write draft translations (never overwrites verified; per-item
  // partial-failure report).
  applyTranslations(
    bookId: string,
    req: { target_language: string; items: ApplyTranslationItem[] },
    token: string,
  ): Promise<ApplyTranslationsResponse> {
    return apiJson<ApplyTranslationsResponse>(
      `${BASE}/books/${bookId}/apply-translations`,
      { method: 'POST', body: JSON.stringify(req), token },
    );
  },

  listEntities(
    bookId: string,
    filters: FilterState & {
      limit?: number;
      offset?: number;
      sort?: string;
      displayLanguage?: string;
      searchMode?: 'simple' | 'raw';
    },
    token: string,
  ): Promise<GlossaryEntityListResponse> {
    const params = new URLSearchParams();
    const kindCodes = Array.isArray(filters.kindCodes) ? filters.kindCodes : [];
    if (kindCodes.length > 0) params.set('kind_codes', kindCodes.join(','));
    if (filters.status !== 'all') params.set('status', filters.status);
    if (filters.searchQuery) params.set('search', filters.searchQuery);
    if (filters.searchMode === 'raw') params.set('search_mode', 'raw');
    if (filters.displayLanguage) params.set('display_language', filters.displayLanguage);
    if (filters.limit) params.set('limit', String(filters.limit));
    if (filters.offset) params.set('offset', String(filters.offset));
    if (filters.sort) params.set('sort', filters.sort);
    const qs = params.toString();
    return apiJson<GlossaryEntityListResponse>(
      `${BASE}/books/${bookId}/entities${qs ? '?' + qs : ''}`,
      { token },
    ).then(normalizeEntityListResponse);
  },

  // genreIds (optional) is the per-entity genre override applied atomically at create:
  // the backend seeds value rows for exactly those genres' attributes (keep-both
  // conflicts included). Omit ⇒ the entity follows the book's active genres.
  createEntity(bookId: string, kindId: string, token: string, genreIds?: string[]): Promise<GlossaryEntity> {
    return apiJson<GlossaryEntity>(`${BASE}/books/${bookId}/entities`, {
      method: 'POST',
      body: JSON.stringify(genreIds ? { kind_id: kindId, genre_ids: genreIds } : { kind_id: kindId }),
      token,
    });
  },

  getEntity(bookId: string, entityId: string, token: string): Promise<GlossaryEntity> {
    return apiJson<GlossaryEntity>(`${BASE}/books/${bookId}/entities/${entityId}`, { token }).then(normalizeEntityResponse);
  },

  // Generalized class-C confirm (spec §13). The assistant proposed a high-impact
  // action (schema create, book_delete, …) minting `confirmToken`; this confirms it
  // after the human clicks Confirm. JWT-only — no gateway/MCP route reaches it.
  // Single-use: a replay or a stale/expired token 422s.
  confirmAction(confirmToken: string, token: string): Promise<unknown> {
    return apiJson<unknown>(`${BASE}/actions/confirm`, {
      method: 'POST',
      body: JSON.stringify({ confirm_token: confirmToken }),
      token,
    });
  },

  // Non-consuming current-state render of a pending action's confirm card (§13.5).
  // Called when the card mounts so the human confirms against what is true NOW.
  previewAction(confirmToken: string, token: string): Promise<ActionPreview> {
    return apiJson<ActionPreview>(`${BASE}/actions/preview`, {
      method: 'POST',
      body: JSON.stringify({ confirm_token: confirmToken }),
      token,
    });
  },

  // EDIT-ATOMIC: the assistant diff-card Apply — multiple field changes applied
  // in ONE transaction with ONE version check (base_version → 412 on drift).
  applyEntityEdit(
    bookId: string,
    entityId: string,
    body: {
      base_version: string;
      short_description?: string | null;
      attributes?: { attr_value_id: string; original_value: string }[];
    },
    token: string,
  ): Promise<unknown> {
    return apiJson<unknown>(`${BASE}/books/${bookId}/entities/${entityId}/apply-edit`, {
      method: 'POST',
      body: JSON.stringify(body),
      token,
    });
  },

  patchEntity(
    bookId: string,
    entityId: string,
    changes: {
      status?: string;
      tags?: string[];
      alive?: boolean;
      short_description?: string | null;
      scope_label?: string;
    },
    token: string,
    // Glossary-assistant P3 (H5): when set, sent as `If-Match` so the PATCH is
    // optimistic-concurrency checked — 412 if the entity changed since read.
    opts?: { ifMatch?: string },
  ): Promise<GlossaryEntity> {
    return apiJson<GlossaryEntity>(`${BASE}/books/${bookId}/entities/${entityId}`, {
      method: 'PATCH',
      body: JSON.stringify(changes),
      token,
      ...(opts?.ifMatch ? { headers: { 'If-Match': opts.ifMatch } } : {}),
    });
  },

  /** Bulk-flip status for many entities in one request (e.g. activate freshly
   *  extracted drafts so they feed the translation glossary). Returns the count
   *  actually updated (book-scoped; absent/foreign ids are ignored). */
  bulkSetStatus(
    bookId: string,
    status: 'active' | 'inactive' | 'draft' | 'rejected',
    entityIds: string[],
    token: string,
  ): Promise<{ updated: number }> {
    return apiJson<{ updated: number }>(`${BASE}/books/${bookId}/entities/bulk-status`, {
      method: 'POST',
      body: JSON.stringify({ status, entity_ids: entityIds }),
      token,
    });
  },

  /** Bulk soft-delete many entities in one request (clean up duplicate/unwanted
   *  entities). Returns the count actually deleted (book-scoped; absent/foreign/
   *  already-deleted ids are ignored — the partial-success report). */
  bulkDeleteEntities(
    bookId: string,
    entityIds: string[],
    token: string,
  ): Promise<{ deleted: number }> {
    return apiJson<{ deleted: number }>(`${BASE}/books/${bookId}/entities/bulk-delete`, {
      method: 'POST',
      body: JSON.stringify({ entity_ids: entityIds }),
      token,
    });
  },

  // ── VG-3: entity revision history + restore (D-GLOSSARY-VERSIONING) ─────────

  listEntityRevisions(
    bookId: string,
    entityId: string,
    token: string,
  ): Promise<{ revisions: EntityRevisionSummary[] }> {
    return apiJson<{ revisions: EntityRevisionSummary[] }>(
      `${BASE}/books/${bookId}/entities/${entityId}/revisions`,
      { token },
    );
  },

  getEntityRevision(
    bookId: string,
    entityId: string,
    revId: string,
    token: string,
  ): Promise<EntityRevisionDetail> {
    return apiJson<EntityRevisionDetail>(
      `${BASE}/books/${bookId}/entities/${entityId}/revisions/${revId}`,
      { token },
    );
  },

  restoreEntityRevision(
    bookId: string,
    entityId: string,
    revId: string,
    token: string,
  ): Promise<{ restored: boolean; from_revision_num: number }> {
    return apiJson<{ restored: boolean; from_revision_num: number }>(
      `${BASE}/books/${bookId}/entities/${entityId}/revisions/${revId}/restore`,
      { method: 'POST', token },
    );
  },

  /** Lightweight names-only list for editor decoration scanning + the Plan Hub
   *  badge name map. The backend endpoint is now KEYSET-paginated (F-H9/PH26) and
   *  returns ALL non-deleted entities (draft/inactive/active), not just active —
   *  so we follow next_cursor until truncated=false and accumulate every page.
   *
   *  `complete` is the load-bearing half for PH26. The safety cap below can, in
   *  principle, stop paging with entities still unread — and then an id that is
   *  ABSENT from the map means "we didn't fetch it", not "it doesn't exist". The
   *  Hub renders those two completely differently (a MISSING-entity warning chip vs
   *  a neutral unresolved one), so collapsing them would make it accuse the user's
   *  glossary of losing an entity it merely hadn't loaded — the
   *  `paged-join-against-complete-set-mislabels-not-yet-loaded-as-absent` bug class. */
  async listEntityNamesWithMeta(
    bookId: string,
    token: string,
  ): Promise<{ items: EntityNameEntry[]; complete: boolean }> {
    const acc: EntityNameEntry[] = [];
    let cursor: string | null = null;
    // Safety cap: 500/page × 500 pages = 250k entities before we bail (never hit
    // in practice; guards against a misbehaving server looping forever).
    for (let page = 0; page < 500; page++) {
      const params = new URLSearchParams({ limit: '500' });
      if (cursor) params.set('cursor', cursor);
      const res = await apiJson<EntityNamesPage>(
        `${BASE}/books/${bookId}/entity-names?${params.toString()}`,
        { token },
      );
      if (res.items?.length) acc.push(...res.items);
      // Exhausted ⇒ the map is the WHOLE book's entity set.
      if (!res.truncated || !res.next_cursor) return { items: acc, complete: true };
      cursor = res.next_cursor;
    }
    // Fell out of the loop ⇒ the cap tripped ⇒ there is more we never read.
    return { items: acc, complete: false };
  },

  /** The names alone — for consumers (editor decoration, the compose picker) that only ever look ids
   *  UP and never reason about an ABSENT one. ONE implementation: it delegates. */
  async listEntityNames(bookId: string, token: string): Promise<EntityNameEntry[]> {
    const { items } = await glossaryApi.listEntityNamesWithMeta(bookId, token);
    return items;
  },

  deleteEntity(bookId: string, entityId: string, token: string): Promise<void> {
    return apiJson<void>(`${BASE}/books/${bookId}/entities/${entityId}`, {
      method: 'DELETE',
      token,
    });
  },

  // ── Kind-resolution review (unknown bucket + aliases) ──────────────────────

  /** Review queue: entities parked under the 'unknown' kind for this book. */
  listUnknownEntities(
    bookId: string,
    token: string,
  ): Promise<{ items: import('./types').UnknownEntity[]; total: number }> {
    return apiJson(`${BASE}/books/${bookId}/unknown-entities`, { token });
  },

  /**
   * Review queue: AI-suggested draft entities knowledge-service wrote back
   * (glossary AI-pipeline v2, mui #1). Reuses the entities list filtered to
   * status=draft + tag ai-suggested — no dedicated endpoint needed.
   */
  listAiSuggestions(
    bookId: string,
    token: string,
  ): Promise<GlossaryEntityListResponse> {
    return apiJson<GlossaryEntityListResponse>(
      `${BASE}/books/${bookId}/entities?status=draft&tags=ai-suggested&limit=200`,
      { token },
    );
  },

  // ── Merge candidates (mui #1c — coreference merge inbox) ───────────────────

  /** Proposed merge clusters for review (knowledge's coref detector wrote them). */
  listMergeCandidates(
    bookId: string,
    token: string,
  ): Promise<import('./types').MergeCandidateListResponse> {
    return apiJson(`${BASE}/books/${bookId}/merge-candidates?status=proposed`, { token });
  },

  /** Confirm a merge: fold `loserIds` into `winnerId` (R5 destructive merge). */
  confirmMerge(
    bookId: string,
    winnerId: string,
    loserIds: string[],
    token: string,
  ): Promise<import('./types').MergeResult> {
    return apiJson(`${BASE}/books/${bookId}/entities/${winnerId}/merge`, {
      method: 'POST',
      body: JSON.stringify({ loser_ids: loserIds }),
      token,
    });
  },

  /** Dismiss a proposed cluster (re-propose then suppressed). */
  dismissMergeCandidate(
    bookId: string,
    candidateId: string,
    token: string,
  ): Promise<{ candidate_id: string; status: string }> {
    return apiJson(`${BASE}/books/${bookId}/merge-candidates/${candidateId}/dismiss`, {
      method: 'POST',
      token,
    });
  },

  /** Undo a merge by replaying its journal. */
  revertMerge(
    bookId: string,
    journalId: string,
    token: string,
  ): Promise<{ journal_id: string; status: string }> {
    return apiJson(`${BASE}/books/${bookId}/merge-journal/${journalId}/revert`, {
      method: 'POST',
      token,
    });
  },

  /**
   * Create an alias `alias_code → kind_id`. When `reassign` is true, also moves every
   * unknown entity whose source_kind_code == alias_code (scoped to book_id if given)
   * onto that kind — the "merge" action.
   */
  // createKindAlias — RETIRED (2026-07-28). `POST /kind-aliases` was removed by SS-4 Milestone C
  // and live-probes at 405; only the GET survives. Its one caller was the unknown-review's
  // "apply to all", which is why that option is no longer offered (see useUnknownReview). The
  // alias write returns in SS-7 retargeted at the tiered model — re-add the binding then, against
  // whatever shape that route lands with, rather than resurrecting this one.

  /** Move ONE entity onto a kind (ad-hoc triage; re-keys attributes by code). */
  reassignEntityKind(
    bookId: string,
    entityId: string,
    kindId: string,
    token: string,
  ): Promise<{ entity_id: string; kind_id: string }> {
    return apiJson(`${BASE}/books/${bookId}/entities/${entityId}/reassign-kind`, {
      method: 'POST',
      body: JSON.stringify({ kind_id: kindId }),
      token,
    });
  },

  // ── Kind CRUD ──────────────────────────────────────────────────────────────

  // createKind — RETIRED (2026-07-28). `POST /kinds` went the same way as the write family below
  // (SS-4 → tiered kinds); live-probed at 405 while GET /kinds still works, which is exactly how
  // it survived unnoticed. Minting a kind is `tieringApi.createBookKind` / `createUserKind`. There
  // is no judgement call about which: `reassign-kind` validates its target against
  // `book_kinds WHERE book_kind_id = $1 AND book_id = $2`, so the book tier is the only id space
  // the very next call accepts.

  // ── RETIRED (2026-07-28): the flat `/kinds/{id}/…` write family ───────────
  //
  // patchKind · deleteKind · reorderKinds · reorderAttrDefs · createAttrDef · patchAttrDef ·
  // deleteAttrDef all lived here with ZERO callers, aimed at routes the glossary service no
  // longer serves: SS-4 moved kinds to the tiered model, so the writes are now
  // `/system-kinds/…` (admin), `/user-kinds/{id}/attributes/…` (per-user) and
  // `/books/{book_id}/kinds/…` (per-book) — the paths `tieringApi` already uses and the live
  // UI already calls through `useBookOntology`. Only `GET /kinds` survives (see getKinds above).
  //
  // Kept as a comment rather than silently deleted because "an api function whose route 404s"
  // is exactly the dead affordance this codebase forbids: the next person to need a kind write
  // would otherwise find these, wire them, and ship a button that fails at runtime. Use
  // `tieringApi`.
  //
  // ⚠ NOT yet fixed: `createKind` (above) and `createKindAlias` still point at removed routes
  // and DO have a live caller — `useUnknownReview.resolve`, behind UnknownEntitiesPanel's
  // "new kind" / "apply to all". Both were probed live and return **405**. Tracked as
  // D-GLOSSARY-UNKNOWN-REVIEW-405; the fix needs a glossary-track decision about which tier a
  // newly-minted kind belongs to, so it is not a rename.

  // ── Attribute Values ──────────────────────────────────────────────────────

  patchAttributeValue(
    bookId: string,
    entityId: string,
    attrValueId: string,
    changes: { original_language?: string; original_value?: string },
    token: string,
    // Glossary-assistant P3 (H5): `If-Match` version guard (412 on drift).
    opts?: { ifMatch?: string },
  ) {
    return apiJson(
      `${BASE}/books/${bookId}/entities/${entityId}/attributes/${attrValueId}`,
      {
        method: 'PATCH',
        body: JSON.stringify(changes),
        token,
        ...(opts?.ifMatch ? { headers: { 'If-Match': opts.ifMatch } } : {}),
      },
    );
  },

  // S-06 — add a value for an attr-def added to the ontology AFTER this entity existed (the
  // "add-later" path that was MCP-only). 409 if a value row already exists (edit it via PATCH).
  addAttributeValue(
    bookId: string,
    entityId: string,
    payload: { attribute_def_id: string; value: string },
    token: string,
  ) {
    return apiJson(
      `${BASE}/books/${bookId}/entities/${entityId}/attributes`,
      { method: 'POST', body: JSON.stringify(payload), token },
    );
  },

  // S-06 — remove a value ROW entirely (distinct from PATCH-to-empty which keeps a blank row).
  deleteAttributeValue(
    bookId: string,
    entityId: string,
    attrValueId: string,
    token: string,
  ) {
    return apiJson<void>(
      `${BASE}/books/${bookId}/entities/${entityId}/attributes/${attrValueId}`,
      { method: 'DELETE', token },
    );
  },

  // ── Attribute Translations ────────────────────────────────────────────────

  createTranslation(
    bookId: string,
    entityId: string,
    attrValueId: string,
    payload: { language_code: string; value: string; confidence?: Confidence; translator?: string },
    token: string,
  ): Promise<Translation> {
    return apiJson<Translation>(
      `${BASE}/books/${bookId}/entities/${entityId}/attributes/${attrValueId}/translations`,
      { method: 'POST', body: JSON.stringify(payload), token },
    );
  },

  patchTranslation(
    bookId: string,
    entityId: string,
    attrValueId: string,
    translationId: string,
    changes: { value?: string; confidence?: Confidence; translator?: string | null },
    token: string,
  ): Promise<Translation> {
    return apiJson<Translation>(
      `${BASE}/books/${bookId}/entities/${entityId}/attributes/${attrValueId}/translations/${translationId}`,
      { method: 'PATCH', body: JSON.stringify(changes), token },
    );
  },

  deleteTranslation(
    bookId: string,
    entityId: string,
    attrValueId: string,
    translationId: string,
    token: string,
  ): Promise<void> {
    return apiJson<void>(
      `${BASE}/books/${bookId}/entities/${entityId}/attributes/${attrValueId}/translations/${translationId}`,
      { method: 'DELETE', token },
    );
  },

  // ── Evidence (entity-level list + per-attribute CRUD) ────────────────────

  listEntityEvidences(
    bookId: string,
    entityId: string,
    params: EvidenceListParams,
    token: string,
  ): Promise<EvidenceListResponse> {
    const qs = new URLSearchParams();
    if (params.limit) qs.set('limit', String(params.limit));
    if (params.offset) qs.set('offset', String(params.offset));
    if (params.evidence_type) qs.set('evidence_type', params.evidence_type);
    if (params.attr_value_id) qs.set('attr_value_id', params.attr_value_id);
    if (params.chapter_id) qs.set('chapter_id', params.chapter_id);
    if (params.language) qs.set('language', params.language);
    if (params.sort_by) qs.set('sort_by', params.sort_by);
    if (params.sort_dir) qs.set('sort_dir', params.sort_dir);
    const q = qs.toString();
    return apiJson<EvidenceListResponse>(
      `${BASE}/books/${bookId}/entities/${entityId}/evidences${q ? '?' + q : ''}`,
      { token },
    ).then(normalizeEvidenceListResponse);
  },

  createEvidence(
    bookId: string,
    entityId: string,
    attrValueId: string,
    payload: CreateEvidencePayload,
    token: string,
  ): Promise<Evidence> {
    return apiJson<Evidence>(
      `${BASE}/books/${bookId}/entities/${entityId}/attributes/${attrValueId}/evidences`,
      { method: 'POST', body: JSON.stringify(payload), token },
    );
  },

  patchEvidence(
    bookId: string,
    entityId: string,
    attrValueId: string,
    evidenceId: string,
    changes: PatchEvidencePayload,
    token: string,
  ): Promise<Evidence> {
    return apiJson<Evidence>(
      `${BASE}/books/${bookId}/entities/${entityId}/attributes/${attrValueId}/evidences/${evidenceId}`,
      { method: 'PATCH', body: JSON.stringify(changes), token },
    );
  },

  deleteEvidence(
    bookId: string,
    entityId: string,
    attrValueId: string,
    evidenceId: string,
    token: string,
  ): Promise<void> {
    return apiJson<void>(
      `${BASE}/books/${bookId}/entities/${entityId}/attributes/${attrValueId}/evidences/${evidenceId}`,
      { method: 'DELETE', token },
    );
  },

  // ── M6 (canon-at-chapter inspector) — public, View-grant gated read routes ──

  /** Entities canon has ESTABLISHED by chapter N (windowed by `before_chapter_index`),
   *  with first/last appearance + coverage. Bare array. */
  knownEntitiesAsOf(
    bookId: string,
    params: { beforeChapterIndex?: number; minFrequency?: number; limit?: number },
    token: string,
  ): Promise<KnownEntityAsOf[]> {
    const qs = new URLSearchParams();
    if (params.beforeChapterIndex != null) qs.set('before_chapter_index', String(params.beforeChapterIndex));
    if (params.minFrequency != null) qs.set('min_frequency', String(params.minFrequency));
    if (params.limit != null) qs.set('limit', String(params.limit));
    const q = qs.toString();
    return apiJson<KnownEntityAsOf[]>(`${BASE}/books/${bookId}/known-entities${q ? `?${q}` : ''}`, { token });
  },

  /** Entities PRESENT IN a specific chapter (chapter→entities), with relevance +
   *  per-chapter mention_count (0 until M7 backfill). Bare array. */
  chapterEntities(
    bookId: string,
    chapterId: string,
    token: string,
  ): Promise<ChapterEntity[]> {
    return apiJson<ChapterEntity[]>(
      `${BASE}/books/${bookId}/chapter-entities?chapter_id=${encodeURIComponent(chapterId)}`,
      { token },
    );
  },
};

/** M6 — `known-entities` row (entities established by chapter N). */
export type KnownEntityAsOf = {
  entity_id: string;
  name: string;
  kind_code: string;
  aliases: string[];
  frequency: number;
  first_chapter_index: number | null;
  last_chapter_index: number | null;
  coverage_pct: number;
};

/** M6 — `chapter-entities` row (entities present in chapter N). */
export type ChapterEntity = {
  entity_id: string;
  name: string;
  kind_code: string;
  relevance: 'major' | 'appears' | 'mentioned';
  chapter_index: number | null;
  mention_count: number;
};
