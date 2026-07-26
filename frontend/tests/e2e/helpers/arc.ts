// S2 (Plan & Structure) E2E fixtures — seed a deterministic arc surface via the REAL gateway so the
// specs assert BEHAVIOUR, not ambient data. Mirrors helpers/motif.ts (own auth headers; small typed
// wrappers over the composition arc routes S2 owns).
import type { APIRequestContext, APIResponse } from '@playwright/test';

function authHeaders(token: string): { Authorization: string; 'Content-Type': string } {
  return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
}

async function ok<T>(p: Promise<APIResponse>): Promise<T> {
  const r = await p;
  if (!r.ok()) throw new Error(`${r.status()} ${r.url()} — ${await r.text()}`);
  return (await r.json()) as T;
}

export interface SeededArc { id: string; version: number }

/** Create a top-level arc (structure_node, kind='arc') on a book. EDIT on the book required —
 *  the JWT owner has it. Returns the node id + version (for OCC edits). */
export async function seedArc(
  request: APIRequestContext, token: string, bookId: string, title: string,
  extra: Record<string, unknown> = {},
): Promise<SeededArc> {
  const a = await ok<{ id: string; version: number }>(
    request.post(`/v1/composition/books/${bookId}/arcs`, {
      headers: authHeaders(token), data: { kind: 'arc', title, ...extra },
    }),
  );
  return { id: a.id, version: a.version };
}

/** Create a USER-tier arc template in the caller's library. Returns the template id. */
export async function seedArcTemplate(
  request: APIRequestContext, token: string, code: string, name: string,
): Promise<string> {
  const t = await ok<{ id: string }>(
    request.post('/v1/composition/arc-templates', {
      headers: authHeaders(token), data: { code, name, language: 'en' },
    }),
  );
  return t.id;
}

/** Create a BOOK-SHARED arc template (34a collaboration tier) — EDIT on the book required. */
export async function seedBookSharedTemplate(
  request: APIRequestContext, token: string, bookId: string, code: string, name: string,
): Promise<{ id: string; book_shared: boolean }> {
  return ok<{ id: string; book_shared: boolean }>(
    request.post(`/v1/composition/arc-templates?target=book_shared&book_id=${bookId}`, {
      headers: authHeaders(token), data: { code, name, language: 'en' },
    }),
  );
}
