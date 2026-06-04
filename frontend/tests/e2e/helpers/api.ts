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
