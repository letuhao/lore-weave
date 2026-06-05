import type { APIRequestContext } from '@playwright/test';
import { TEST_USER } from './auth';

/** Login via API and return the access token. */
export async function getAccessToken(request: APIRequestContext): Promise<string> {
  const resp = await request.post('/v1/auth/login', {
    data: { email: TEST_USER.email, password: TEST_USER.password },
  });
  if (!resp.ok()) {
    throw new Error(`API login failed: ${resp.status()} ${await resp.text()}`);
  }
  const body = (await resp.json()) as { access_token: string };
  return body.access_token;
}

const auth = (token: string) => ({ headers: { Authorization: `Bearer ${token}` } });

async function ok<T>(p: Promise<import('@playwright/test').APIResponse>): Promise<T> {
  const r = await p;
  if (!r.ok()) throw new Error(`API ${r.url()} → ${r.status()} ${await r.text()}`);
  return (await r.json()) as T;
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
