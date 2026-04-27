import type { APIRequestContext } from '@playwright/test';

interface EntitySummary {
  entity_id: string;
  display_name?: string | null;
  status: string;
}

interface ListResponse {
  items: EntitySummary[];
  total: number;
}

function authHeaders(token: string): { Authorization: string; 'Content-Type': string } {
  return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
}

/**
 * Activate all draft entities for a book so wiki stub generation will pick them up.
 * Wiki generate filters by status='active' (per glossary-service wiki_handler.go:829).
 */
export async function activateAllDraftEntities(
  request: APIRequestContext,
  token: string,
  bookId: string,
): Promise<number> {
  const listResp = await request.get(`/v1/glossary/books/${bookId}/entities?status=draft&limit=200`, {
    headers: authHeaders(token),
  });
  if (!listResp.ok()) {
    throw new Error(`list draft entities failed: ${listResp.status()} ${await listResp.text()}`);
  }
  const data = (await listResp.json()) as ListResponse;

  let activated = 0;
  for (const entity of data.items) {
    // Only activate entities with a non-empty display_name; nameless ones won't make useful wiki stubs
    if (!entity.display_name || entity.display_name.trim() === '') continue;
    const patchResp = await request.patch(
      `/v1/glossary/books/${bookId}/entities/${entity.entity_id}`,
      {
        headers: authHeaders(token),
        data: { status: 'active' },
      },
    );
    if (!patchResp.ok()) {
      throw new Error(
        `activate entity ${entity.entity_id} failed: ${patchResp.status()} ${await patchResp.text()}`,
      );
    }
    activated++;
  }
  return activated;
}
