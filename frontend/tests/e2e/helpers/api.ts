import type { APIRequestContext } from '@playwright/test';
import { TEST_USER, TEST_USER_B } from './auth';

/** Login via API and return the access token. */
export async function getAccessToken(request: APIRequestContext): Promise<string> {
  return loginAs(request, TEST_USER.email, TEST_USER.password);
}

async function loginAs(request: APIRequestContext, email: string, password: string): Promise<string> {
  const resp = await request.post('/v1/auth/login', { data: { email, password } });
  if (!resp.ok()) throw new Error(`API login ${email} failed: ${resp.status()} ${await resp.text()}`);
  return ((await resp.json()) as { access_token: string }).access_token;
}

/** Ensure the 2nd isolation account exists (register is idempotent — 409 = already
 * there) and return its access token. Dev login has no email-verification gate. */
export async function ensureUserB(request: APIRequestContext): Promise<string> {
  const reg = await request.post('/v1/auth/register', {
    data: { email: TEST_USER_B.email, password: TEST_USER_B.password, display_name: 'Claude Test 2' },
  });
  if (!reg.ok() && reg.status() !== 409) {
    throw new Error(`register user B failed: ${reg.status()} ${await reg.text()}`);
  }
  return loginAs(request, TEST_USER_B.email, TEST_USER_B.password);
}

const auth = (token: string) => ({ headers: { Authorization: `Bearer ${token}` } });

async function ok<T>(p: Promise<import('@playwright/test').APIResponse>): Promise<T> {
  const r = await p;
  if (!r.ok()) throw new Error(`API ${r.url()} → ${r.status()} ${await r.text()}`);
  return (await r.json()) as T;
}

/** #19 Wave 2 — `studioRole` is a server-synced ACCOUNT-level pref (not per-book, not
 *  per-test-run), so a role picked by one E2E test sticks for every later test on this shared
 *  account. Tests that need a deterministic tour (e.g. "the core tour specifically") reset it
 *  to null directly via the API first — there is no UI affordance to clear a role once picked
 *  (Skip only sets the seen-flag, it never touches studioRole, by design — see
 *  useStudioOnboarding.ts). */
export async function resetStudioRolePref(request: APIRequestContext, token: string): Promise<void> {
  const r = await request.patch('/v1/me/preferences', { ...auth(token), data: { prefs: { studioRole: null } } });
  if (!r.ok()) throw new Error(`resetStudioRolePref failed: ${r.status()} ${await r.text()}`);
}

export async function createBook(request: APIRequestContext, token: string, title: string): Promise<string> {
  const b = await ok<{ book_id: string }>(
    request.post('/v1/books', { ...auth(token), data: { title, original_language: 'en' } }),
  );
  return b.book_id;
}

export async function createChapter(request: APIRequestContext, token: string, bookId: string, title: string): Promise<string> {
  const c = await ok<{ chapter_id: string }>(
    request.post(`/v1/books/${bookId}/chapters`, { ...auth(token), data: { original_language: 'en', title } }),
  );
  return c.chapter_id;
}

async function draftVersion(request: APIRequestContext, token: string, bookId: string, chapterId: string): Promise<number> {
  const d = await ok<{ draft_version: number }>(
    request.get(`/v1/books/${bookId}/chapters/${chapterId}/draft`, auth(token)),
  );
  return d.draft_version;
}

/** Save the draft (creates a revision). `text` may contain `\n` — it becomes the
 * block's `_text` projection, which is what the compare diffs. Returns the new
 * draft_version. */
export async function saveDraft(
  request: APIRequestContext, token: string, bookId: string, chapterId: string,
  text: string, expectedDraftVersion: number, message: string,
): Promise<number> {
  const body = { type: 'doc', content: [{ type: 'paragraph', _text: text, content: [{ type: 'text', text }] }] };
  const d = await ok<{ draft_version: number }>(
    request.patch(`/v1/books/${bookId}/chapters/${chapterId}/draft`, {
      ...auth(token),
      data: { body, body_format: 'json', commit_message: message, expected_draft_version: expectedDraftVersion },
    }),
  );
  return d.draft_version;
}

export async function trashBook(request: APIRequestContext, token: string, bookId: string): Promise<void> {
  await request.delete(`/v1/books/${bookId}`, auth(token));
}

// ── translation (#16 Phase 3 — real job, not a mock, per this repo's E2E convention) ──────────

/** Submit a real translate job against a chat-capable model. Resolves the model dynamically
 *  (via listChatModels) rather than a hardcoded id, so a deactivated/renamed test model doesn't
 *  silently break this helper. */
export async function createTranslationJob(
  request: APIRequestContext, token: string, bookId: string, chapterId: string, targetLanguage: string,
): Promise<string> {
  const models = await listChatModels(request, token);
  if (models.length === 0) throw new Error('no active chat-capable model for translation E2E — check test account BYOK models');
  const j = await ok<{ job_id: string }>(request.post(`/v1/translation/books/${bookId}/jobs`, {
    ...auth(token),
    data: { chapter_ids: [chapterId], target_language: targetLanguage, model_source: 'user_model', model_ref: models[0].user_model_id },
  }));
  return j.job_id;
}

/** Poll a translation job to completion (or throw on failure/timeout). Local models translating
 *  a 1-paragraph seed chapter typically finish in 5-15s. */
export async function waitForTranslationJob(
  request: APIRequestContext, token: string, jobId: string, timeoutMs = 60_000,
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const job = await ok<{ status: string; error_message?: string | null }>(
      request.get(`/v1/translation/jobs/${jobId}`, auth(token)),
    );
    if (job.status === 'completed') return;
    if (job.status === 'failed') throw new Error(`translation job ${jobId} failed: ${job.error_message}`);
    await new Promise((r) => setTimeout(r, 2000));
  }
  throw new Error(`translation job ${jobId} did not complete within ${timeoutMs}ms`);
}

export async function getBookApi(
  request: APIRequestContext, token: string, bookId: string,
): Promise<{ book_id: string; title: string; world_id?: string | null }> {
  return ok(request.get(`/v1/books/${bookId}`, auth(token)));
}

// ── worlds (creation-unblock RAID) ──────────────────────────────────────────

/** Create a world (C20). Returns its id + the auto-provisioned bible anchors. */
export async function createWorld(
  request: APIRequestContext, token: string, name: string,
): Promise<{ world_id: string; bible_book_id: string | null; bible_chapter_id: string | null }> {
  return ok(request.post('/v1/worlds', { ...auth(token), data: { name } }));
}

/** Delete a world (owner-scoped; FK SET NULL returns member books to standalone). */
export async function deleteWorld(request: APIRequestContext, token: string, worldId: string): Promise<void> {
  await request.delete(`/v1/worlds/${worldId}`, auth(token));
}

/** List the caller's worlds — used to resolve a UI-created world's id for cleanup. */
export async function listWorlds(
  request: APIRequestContext, token: string,
): Promise<{ items: Array<{ world_id: string; name: string }>; total: number }> {
  return ok(request.get('/v1/worlds?limit=200', auth(token)));
}

/** The world's member books (bible excluded) — used to assert an attach landed. */
export async function listWorldBooks(
  request: APIRequestContext, token: string, worldId: string,
): Promise<{ items: Array<{ book_id: string; title: string }>; total: number }> {
  return ok(request.get(`/v1/worlds/${worldId}/books`, auth(token)));
}

/** Attach an existing book to a world (C20 move-book) — pre-seed membership. */
export async function moveBookIntoWorld(
  request: APIRequestContext, token: string, worldId: string, bookId: string,
): Promise<void> {
  await ok(request.post(`/v1/worlds/${worldId}/books`, { ...auth(token), data: { book_id: bookId } }));
}

// ── knowledge projects (creation-unblock RAID) ──────────────────────────────

/** Create a knowledge project bound to a book — drives the project→book+world
 *  Overview backlink (D-WORLD-PROJECT-BACKLINK). */
export async function createKnowledgeProject(
  request: APIRequestContext, token: string, name: string, bookId: string,
): Promise<{ project_id: string }> {
  return ok(request.post('/v1/knowledge/projects', {
    ...auth(token), data: { name, book_id: bookId, project_type: 'book' },
  }));
}

export async function deleteKnowledgeProject(
  request: APIRequestContext, token: string, projectId: string,
): Promise<void> {
  await request.delete(`/v1/knowledge/projects/${projectId}`, auth(token));
}

/** Create a user-authored (DISCOVERED / unanchored) knowledge entity — the input
 *  to the D-079 anchor-and-override flow (a discovered entity the wizard offers to
 *  anchor inline). Idempotent on (name, kind) within the project. */
export async function createKnowledgeEntity(
  request: APIRequestContext, token: string, projectId: string, name: string, kind: string,
): Promise<{ id: string; glossary_entity_id: string | null }> {
  return ok(request.post('/v1/knowledge/entities', {
    ...auth(token), data: { project_id: projectId, name, kind },
  }));
}

// ── chat (creation-unblock — ProjectPicker lives in the session settings) ────

/** Create a chat session (needs a model). Returns its id so the test can open the
 *  session settings panel where the ProjectPicker replaced the raw <select>. */
export async function createChatSession(
  request: APIRequestContext, token: string, modelRef: string, title: string,
): Promise<{ session_id: string }> {
  return ok(request.post('/v1/chat/sessions', {
    ...auth(token), data: { model_source: 'user_model', model_ref: modelRef, title },
  }));
}

export async function deleteChatSession(
  request: APIRequestContext, token: string, sessionId: string,
): Promise<void> {
  await request.delete(`/v1/chat/sessions/${sessionId}`, auth(token));
}

export async function patchChatSession(
  request: APIRequestContext,
  token: string,
  sessionId: string,
  body: { enabled_tools?: string[]; enabled_skills?: string[]; activated_tools?: string[]; title?: string },
): Promise<Record<string, unknown>> {
  return ok(
    request.patch(`/v1/chat/sessions/${sessionId}`, { ...auth(token), data: body }),
  );
}

export async function getChatSession(
  request: APIRequestContext, token: string, sessionId: string,
): Promise<Record<string, unknown>> {
  return ok(request.get(`/v1/chat/sessions/${sessionId}`, auth(token)));
}

export async function getToolsCatalog(
  request: APIRequestContext, token: string,
): Promise<{ items: Array<{ name: string }> }> {
  return ok(request.get('/v1/chat/tools/catalog', auth(token)));
}

export async function getSkillsCatalog(
  request: APIRequestContext, token: string,
): Promise<{ items: Array<{ id: string }> }> {
  return ok(request.get('/v1/chat/skills/catalog', auth(token)));
}

/** Create a chapter and save `text` as its draft body (one revision) — a content-
 * rich chapter the extractor can pull entities from. Returns the chapter id. */
export async function seedRichChapter(
  request: APIRequestContext, token: string, bookId: string, title: string, text: string,
): Promise<string> {
  const chapterId = await createChapter(request, token, bookId, title);
  const dv = await draftVersion(request, token, bookId, chapterId);
  await saveDraft(request, token, bookId, chapterId, text, dv, `seed ${title}`);
  return chapterId;
}

/** A chapter's revision ids (newest first) — used to drive the compare endpoint. */
export async function listRevisionIds(
  request: APIRequestContext, token: string, bookId: string, chapterId: string,
): Promise<string[]> {
  const d = await ok<{ items: Array<{ revision_id: string }> }>(
    request.get(`/v1/books/${bookId}/chapters/${chapterId}/revisions`, auth(token)),
  );
  return (d.items ?? []).map((r) => r.revision_id);
}

/** Read a chapter's canon-side editorial fields (server source of truth). Used to
 * assert publish lifecycle outcomes without trusting the UI badge alone. */
export async function getChapterEditorial(
  request: APIRequestContext, token: string, bookId: string, chapterId: string,
): Promise<{ editorial_status?: 'draft' | 'published'; published_revision_id?: string | null }> {
  return ok(request.get(`/v1/books/${bookId}/chapters/${chapterId}`, auth(token)));
}

/** Save the draft once to advance the server `draft_version` — simulates "another
 * tab/device saved" so the editor's loaded version goes stale (OI-2 / B1.4). */
export async function bumpServerDraft(
  request: APIRequestContext, token: string, bookId: string, chapterId: string, text: string,
): Promise<number> {
  const dv = await draftVersion(request, token, bookId, chapterId);
  return saveDraft(request, token, bookId, chapterId, text, dv, 'external bump');
}

/** Publish a chapter via the API (canon = published; triggers CM3b extraction). */
export async function publishChapterApi(
  request: APIRequestContext, token: string, bookId: string, chapterId: string,
): Promise<void> {
  await ok(request.post(`/v1/books/${bookId}/chapters/${chapterId}/publish`, { ...auth(token), data: {} }));
}

// ── composition (co-write) seeding ──

export type ChatModel = { user_model_id: string; provider_model_name: string; is_active: boolean };

// Chat-tagged models — the set the UI model picker shows (drafter source).
export async function listChatModels(request: APIRequestContext, token: string): Promise<ChatModel[]> {
  const d = await ok<{ items: ChatModel[] }>(
    request.get('/v1/model-registry/user-models?capability=chat', auth(token)),
  );
  return (d.items ?? []).filter((m) => m.is_active);
}

// All active models — the critic is set via API (not the UI picker), so it only
// needs to be a valid active model, distinct from the drafter.
export async function listActiveModels(request: APIRequestContext, token: string): Promise<ChatModel[]> {
  const d = await ok<{ items: ChatModel[] }>(
    request.get('/v1/model-registry/user-models?include_inactive=true', auth(token)),
  );
  return (d.items ?? []).filter((m) => m.is_active);
}

export async function createCompositionWork(request: APIRequestContext, token: string, bookId: string): Promise<string> {
  const w = await ok<{ project_id: string }>(
    request.post(`/v1/composition/books/${bookId}/work`, auth(token)),
  );
  return w.project_id;
}

/** S5 — derive a dị bản (derivative Work) from a canon Work via the real route the wizard
 *  calls. Returns the new derivative's project_id + version (for If-Match archive). Throws on
 *  the 503 PROJECT_CREATE_UNAVAILABLE (knowledge-service can't mint the delta partition) so a
 *  seeding test can `test.skip()` on a genuine infra outage instead of failing spuriously. */
export async function createDerivative(
  request: APIRequestContext, token: string, sourceProjectId: string,
  opts: { name: string; branchPoint?: number; taxonomy?: 'au' | 'pov_shift' | 'character_transform'; canonRules?: string[] },
): Promise<{ project_id: string; version: number }> {
  const r = await request.post(`/v1/composition/works/${sourceProjectId}/derive`, {
    ...auth(token),
    data: {
      name: opts.name,
      branch_point: opts.branchPoint ?? 0,
      divergence: { taxonomy: opts.taxonomy ?? 'au', canon_rule: opts.canonRules ?? [] },
    },
  });
  if (!r.ok()) throw new Error(`createDerivative ${r.url()} → ${r.status()} ${await r.text()}`);
  const w = (await r.json()) as { project_id: string; version: number };
  return { project_id: w.project_id, version: w.version };
}

export async function createCompositionScene(
  request: APIRequestContext, token: string, projectId: string, chapterId: string, title: string,
): Promise<string> {
  const n = await ok<{ id: string }>(
    request.post(`/v1/composition/works/${projectId}/outline/nodes`, {
      ...auth(token), data: { kind: 'scene', chapter_id: chapterId, title },
    }),
  );
  return n.id;
}

/** Create a non-scene outline node (e.g. a structural 'beat') — used to prove the
 * scene_committed telemetry fires ONLY for scenes (B3.3). */
export async function createOutlineNode(
  request: APIRequestContext, token: string, projectId: string, kind: string, title: string,
): Promise<string> {
  const n = await ok<{ id: string }>(
    request.post(`/v1/composition/works/${projectId}/outline/nodes`, {
      ...auth(token), data: { kind, title },
    }),
  );
  return n.id;
}

/** Patch an outline node's status (M9 mark-done path → emits scene_committed for
 * scenes). Mirrors the FE patchNode (PATCH /v1/composition/outline/nodes/{id}). */
export async function setSceneStatus(
  request: APIRequestContext, token: string, nodeId: string, status: string,
): Promise<void> {
  await ok(
    request.patch(`/v1/composition/outline/nodes/${nodeId}`, { ...auth(token), data: { status } }),
  );
}

/** Point the Work's critic at a DISTINCT model (anti-self-reinforcement §4) so
 * the advisory critique actually runs after accept. */
export async function setWorkCriticModel(
  request: APIRequestContext, token: string, projectId: string, criticModelRef: string,
): Promise<void> {
  await ok(
    request.patch(`/v1/composition/works/${projectId}`, {
      ...auth(token),
      data: { settings: { critic_model_source: 'user_model', critic_model_ref: criticModelRef } },
    }),
  );
}

/** Persist the Work's default drafter model (settings.default_model_ref). The studio editor's inline
 *  "Continue from cursor" is gated on a RESOLVED default (composeDefaultModel = persisted ?? sole-model);
 *  the test account has no `user_default_models`, so a spec that drives the inline ghost must set this. */
export async function setWorkDefaultModel(
  request: APIRequestContext, token: string, projectId: string, modelRef: string,
): Promise<void> {
  await ok(
    request.patch(`/v1/composition/works/${projectId}`, {
      ...auth(token),
      data: { settings: { default_model_ref: modelRef } },
    }),
  );
}

/** Seed a fresh book+chapter with `texts.length` saved revisions (newest last).
 * Returns ids for navigation + cleanup. */
export async function seedChapterWithRevisions(
  request: APIRequestContext, token: string, texts: string[],
): Promise<{ bookId: string; chapterId: string }> {
  const bookId = await createBook(request, token, `E2E compare ${Date.now()}`);
  const chapterId = await createChapter(request, token, bookId, 'Ch1');
  let dv = await draftVersion(request, token, bookId, chapterId);
  for (let i = 0; i < texts.length; i++) {
    dv = await saveDraft(request, token, bookId, chapterId, texts[i], dv, `rev ${i + 1}`);
  }
  return { bookId, chapterId };
}
