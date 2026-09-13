import type { APIRequestContext } from '@playwright/test';

interface ExtractionProfileAttribute {
  code: string;
  auto_selected: boolean;
  is_required: boolean;
}

interface ExtractionProfileKind {
  code: string;
  auto_selected: boolean;
  attributes: ExtractionProfileAttribute[];
}

interface ExtractionProfileResponse {
  kinds: ExtractionProfileKind[];
}

export type ExtractionProfile = Record<string, Record<string, 'fill' | 'overwrite' | 'skip'>>;

export interface JobStatus {
  job_id: string;
  status: string;
  [key: string]: unknown;
}

const TERMINAL_STATUSES = new Set([
  'completed',
  'failed',
  'cancelled',
  'completed_with_errors',
]);

function authHeaders(token: string): { Authorization: string } {
  return { Authorization: `Bearer ${token}` };
}

/** Build the same auto-selected profile that StepProfile constructs from book.extraction-profile. */
/** Adopt the book's ontology — copy the System standards down into book-local kinds.
 *
 * REQUIRED BEFORE EXTRACTION. glossary-service states the invariant itself: "A book MUST be
 * adopted (book_kinds populated) before extraction can run — an un-adopted book yields zero
 * kinds, which the worker treats as 'book not scaffolded'"
 * (internal/api/extraction_handler.go, writeExtractionProfile).
 *
 * A person does this through the extraction wizard. Specs that say they "skip wizard UI for
 * determinism" still have to do the equivalent setup, or they are asking a book that was never
 * scaffolded to extract. An empty body adopts the mandatory `universal` genre, which is what the
 * wizard lands on by default.
 */
export async function adoptBookOntology(
  request: APIRequestContext,
  token: string,
  bookId: string,
): Promise<void> {
  const resp = await request.post(`/v1/glossary/books/${bookId}/adopt`, {
    headers: authHeaders(token),
    data: {},
  });
  if (!resp.ok()) {
    throw new Error(`adopt book ontology failed: ${resp.status()} ${await resp.text()}`);
  }
}

export async function buildAutoExtractionProfile(
  request: APIRequestContext,
  token: string,
  bookId: string,
): Promise<ExtractionProfile> {
  const resp = await request.get(`/v1/glossary/books/${bookId}/extraction-profile`, {
    headers: authHeaders(token),
  });
  if (!resp.ok()) {
    throw new Error(`get extraction profile failed: ${resp.status()} ${await resp.text()}`);
  }
  const data = (await resp.json()) as ExtractionProfileResponse;

  const profile: ExtractionProfile = {};
  for (const kind of data.kinds) {
    if (!kind.auto_selected) continue;
    const attrs: Record<string, 'fill' | 'overwrite' | 'skip'> = {};
    for (const attr of kind.attributes) {
      attrs[attr.code] = attr.auto_selected ? 'fill' : 'skip';
    }
    profile[kind.code] = attrs;
  }
  return profile;
}

export async function createExtractionJob(
  request: APIRequestContext,
  token: string,
  bookId: string,
  chapterId: string,
  modelRef: string,
  profile: ExtractionProfile,
): Promise<string> {
  const resp = await request.post(`/v1/extraction/books/${bookId}/extract-glossary`, {
    headers: authHeaders(token),
    data: {
      chapter_ids: [chapterId],
      extraction_profile: profile,
      model_source: 'user_model',
      model_ref: modelRef,
    },
  });
  if (!resp.ok()) {
    throw new Error(`create extraction job failed: ${resp.status()} ${await resp.text()}`);
  }
  const created = (await resp.json()) as { job_id: string };
  return created.job_id;
}

export async function pollUntilComplete(
  request: APIRequestContext,
  token: string,
  jobId: string,
  options: { timeoutMs?: number; intervalMs?: number } = {},
): Promise<JobStatus> {
  const timeoutMs = options.timeoutMs ?? 240_000;
  const intervalMs = options.intervalMs ?? 3000;
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    const resp = await request.get(`/v1/extraction/jobs/${jobId}`, {
      headers: authHeaders(token),
    });
    if (!resp.ok()) {
      throw new Error(`poll job failed: ${resp.status()} ${await resp.text()}`);
    }
    const status = (await resp.json()) as JobStatus;
    if (TERMINAL_STATUSES.has(status.status)) return status;
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }

  throw new Error(`extraction job ${jobId} did not complete within ${timeoutMs}ms`);
}

/** Seed a book that has BOTH a profile and an extraction history, and return its id.
 *
 * 🔴 #268-adjacent / J1 — `enrichment-profile` asserts a NON-EMPTY worldview and that the Gaps
 * panel never shows the C2 "extract first" notice. Both are true only of a book that has been
 * profiled AND extracted. It used to point at a hard-coded "seeded demo Fengshen book" that
 * exists on one stack and one account; everywhere else the page rendered `book not found`.
 *
 * Pointing it at a FRESH book instead would be worse than the bug: the worldview would be empty
 * and "extract first" would be correct, so both assertions would pass vacuously while proving
 * nothing. The fixture is therefore assembled for real -- adopt, extract, profile -- which is
 * slow (a live model run) and is the price of the claims being worth anything.
 */
export async function seedProfiledExtractedBook(
  request: APIRequestContext,
  token: string,
  opts: { title: string; chapterTitle: string; body: string; worldview: string; modelRef: string },
): Promise<string> {
  const post = async <T>(url: string, data: unknown): Promise<T> => {
    const r = await request.post(url, { headers: authHeaders(token), data });
    if (!r.ok()) throw new Error(`seedProfiledExtractedBook: POST ${url} -> ${r.status()} ${await r.text()}`);
    return (await r.json()) as T;
  };

  const book = await post<{ book_id: string }>('/v1/books', { title: opts.title, original_language: 'en' });
  const bookId = book.book_id;
  await post(`/v1/books/${bookId}/chapters`, {
    original_language: 'en', title: opts.chapterTitle, body: opts.body,
  });
  await adoptBookOntology(request, token, bookId);

  const chRes = await request.get(`/v1/books/${bookId}/chapters`, { headers: authHeaders(token) });
  if (!chRes.ok()) throw new Error(`seedProfiledExtractedBook: list chapters -> ${chRes.status()}`);
  const chapters = (await chRes.json()) as { items?: Array<{ chapter_id?: string; id?: string }> };
  const chapterId = chapters.items?.[0]?.chapter_id ?? chapters.items?.[0]?.id ?? '';
  if (!chapterId) throw new Error('seedProfiledExtractedBook: the chapter did not come back');

  const profile = await buildAutoExtractionProfile(request, token, bookId);
  if (Object.keys(profile).length === 0) {
    throw new Error('seedProfiledExtractedBook: no auto-selected kinds after adopt — the fixture would be vacuous');
  }
  const jobId = await createExtractionJob(request, token, bookId, chapterId, opts.modelRef, profile);
  const final = await pollUntilComplete(request, token, jobId, { timeoutMs: 300_000 });
  if (!/^completed$/.test(final.status)) {
    throw new Error(`seedProfiledExtractedBook: extraction did not complete cleanly (status=${final.status})`);
  }

  const put = await request.put(`/v1/lore-enrichment/books/${bookId}/profile`, {
    headers: authHeaders(token), data: { worldview: opts.worldview },
  });
  if (!put.ok()) throw new Error(`seedProfiledExtractedBook: profile PUT -> ${put.status()}`);
  return bookId;
}
