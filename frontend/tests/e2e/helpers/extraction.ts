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
