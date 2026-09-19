// S4 (Motif & craft) E2E fixtures — seed a deterministic motif surface via the REAL API so the
// specs assert BEHAVIOUR, not ambient data. Mirrors the helpers/glossary.ts pattern (own auth
// headers; small typed wrappers over the gateway).
import type { APIRequestContext } from '@playwright/test';

function authHeaders(token: string): { Authorization: string; 'Content-Type': string } {
  return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
}

async function ok<T>(p: Promise<import('@playwright/test').APIResponse>): Promise<T> {
  const r = await p;
  if (!r.ok()) throw new Error(`${r.status()} ${r.url()} — ${await r.text()}`);
  return (await r.json()) as T;
}

/** Create the co-writer Work for a book (so binding/conformance are live). Returns project_id. */
export async function createWork(request: APIRequestContext, token: string, bookId: string): Promise<string> {
  const w = await ok<{ project_id: string }>(
    request.post(`/v1/composition/books/${bookId}/work`, { headers: authHeaders(token) }),
  );
  return w.project_id;
}

export interface SeedMotifArgs {
  code: string;
  name: string;
  kind?: 'trope' | 'scheme' | 'sequence' | 'pattern';
  summary?: string;
  visibility?: 'private' | 'public' | 'unlisted';
}

/** Create a user-tier motif (owner-stamped from the JWT). Returns motif_id. */
export async function seedMotif(request: APIRequestContext, token: string, args: SeedMotifArgs): Promise<string> {
  const m = await ok<{ id: string }>(
    request.post('/v1/composition/motifs', {
      headers: authHeaders(token),
      data: { kind: 'scheme', visibility: 'private', ...args },
    }),
  );
  return m.id;
}

/** Create a graph edge FROM one motif TO another (BE-M3). Returns link id. */
export async function createMotifLink(
  request: APIRequestContext, token: string, fromId: string, toId: string,
  kind: 'composed_of' | 'precedes' | 'variant_of' = 'precedes',
): Promise<string> {
  const l = await ok<{ id: string }>(
    request.post(`/v1/composition/motifs/${fromId}/links`, {
      headers: authHeaders(token), data: { to_motif_id: toId, kind },
    }),
  );
  return l.id;
}

/** Create a scene outline node in a Work (so the scene-inspector has a scene to bind motifs to).
 *  Returns the outline node id. */
export async function createSceneNode(
  request: APIRequestContext, token: string, projectId: string, chapterId: string, title: string,
): Promise<string> {
  const n = await ok<{ id: string }>(
    request.post(`/v1/composition/works/${projectId}/outline/nodes`, {
      headers: authHeaders(token),
      data: { kind: 'scene', chapter_id: chapterId, title, status: 'drafting', tension: 3, beat_role: 'reversal' },
    }),
  );
  return n.id;
}

/** Soft-archive a motif (cleanup). Best-effort. */
export async function archiveMotif(request: APIRequestContext, token: string, motifId: string): Promise<void> {
  await request.delete(`/v1/composition/motifs/${motifId}`, { headers: authHeaders(token) }).catch(() => { /* best effort */ });
}

/** Archive the caller's motifs with exactly these codes: for a motif a test created through the UI,
 *  whose id it never saw. A spec that creates a motif and does not archive it leaks it into the
 *  shared account for good; 47 had leaked by 2026-09-19, enough to push a freshly seeded motif off
 *  the library's first page (84 system rows + user rows by name) and turn three tests red. */
export async function archiveMotifsByCode(request: APIRequestContext, token: string, codes: string[]): Promise<void> {
  for (const code of codes) {
    const r = await request.get(`/v1/composition/motifs?scope=mine&q=${encodeURIComponent(code)}&limit=100`,
      { headers: authHeaders(token) }).catch(() => null);
    if (!r || !r.ok()) continue;
    const body = await r.json() as { motifs?: Array<{ id: string; code: string }> };
    for (const m of body.motifs ?? []) if (m.code === code) await archiveMotif(request, token, m.id);
  }
}

/** Resolve a chat-capable BYOK model_ref for the LLM-spend steps (mine / re-run / regenerate).
 *  Prefers a LOCAL model ($0). Returns the user_model_id UUID, or null if none is registered. */
export async function resolveChatModel(request: APIRequestContext, token: string): Promise<string | null> {
  const r = await request.get('/v1/settings/models', { headers: authHeaders(token) });
  if (!r.ok()) return null;
  const body = await r.json() as { models?: Array<{ user_model_id: string; alias?: string; capability_flags?: Record<string, unknown> }> };
  const models = body.models ?? [];
  const chat = models.filter((m) => m.capability_flags && (m.capability_flags.chat === true || m.capability_flags._capability === 'chat'));
  // prefer a Gemma/local model (cheapest); else any chat model.
  const gemma = chat.find((m) => /gemma/i.test(m.alias ?? ''));
  return (gemma ?? chat[0])?.user_model_id ?? null;
}
