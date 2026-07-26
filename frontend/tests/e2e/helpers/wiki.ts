import type { APIRequestContext } from '@playwright/test';

// 15_wiki_panels.md — seed a real wiki article for the E2E wiki-panels spec. Verified live
// against the dev stack (2026-07-04) before writing this file, since none of the endpoints
// below have an existing TS client abstraction in tests/e2e/helpers/ — this mirrors the exact
// request/response shapes glossaryApi.ts / wiki/api.ts use in the app itself.
//
// Flow: adopt the 'character' system kind into the book (a fresh book has NO kinds until
// adopted — 'universal' genre + 'unknown' kind are auto-included even with an empty request,
// but 'unknown' is is_hidden:true and unsuitable for a visible test article) → create a draft
// entity of that kind → set its required 'name' attribute (entity display_name derives from
// this, NOT a direct field) → activate it → generate a wiki article from it.

const auth = (token: string) => ({ headers: { Authorization: `Bearer ${token}` } });

async function ok<T>(p: Promise<import('@playwright/test').APIResponse>): Promise<T> {
  const r = await p;
  if (!r.ok()) throw new Error(`API ${r.url()} → ${r.status()} ${await r.text()}`);
  return (await r.json()) as T;
}

interface AttributeValue {
  attr_value_id: string;
  attribute_def: { code: string };
}

interface EntityResp {
  entity_id: string;
  attribute_values: AttributeValue[];
}

export interface SeededWikiArticle {
  articleId: string;
  entityId: string;
  displayName: string;
}

/** Adopts the 'character' system kind into `bookId` (a fresh book has none) and returns its
 *  book-scoped `book_kind_id`. Idempotent — a re-adopt of an already-adopted kind is a no-op
 *  server-side, so this is safe to call once per test book. */
export async function adoptCharacterKind(request: APIRequestContext, token: string, bookId: string): Promise<string> {
  const ont = await ok<{ kinds: { code: string; book_kind_id: string }[] }>(
    request.post(`/v1/glossary/books/${bookId}/adopt`, { ...auth(token), data: { genres: [], kinds: ['character'] } }),
  );
  const kind = ont.kinds.find((k) => k.code === 'character');
  if (!kind) throw new Error(`adopt did not return a 'character' kind for book ${bookId}`);
  return kind.book_kind_id;
}

/** Creates an active, named glossary entity of the given book-kind, then generates a wiki
 *  article (deterministic stub, no LLM cost) from it. Returns the ids the spec needs to open
 *  the `wiki` panel and drive the `wiki-editor` panel directly. */
export async function seedWikiArticle(
  request: APIRequestContext,
  token: string,
  bookId: string,
  bookKindId: string,
  displayName: string,
): Promise<SeededWikiArticle> {
  const entity = await ok<EntityResp>(
    request.post(`/v1/glossary/books/${bookId}/entities`, { ...auth(token), data: { kind_id: bookKindId } }),
  );
  const nameAttr = entity.attribute_values.find((a) => a.attribute_def.code === 'name');
  if (!nameAttr) throw new Error(`entity ${entity.entity_id} has no 'name' attribute value`);

  await ok(request.patch(
    `/v1/glossary/books/${bookId}/entities/${entity.entity_id}/attributes/${nameAttr.attr_value_id}`,
    { ...auth(token), data: { original_value: displayName } },
  ));
  await ok(request.patch(
    `/v1/glossary/books/${bookId}/entities/${entity.entity_id}`,
    { ...auth(token), data: { status: 'active' } },
  ));
  const article = await ok<{ article_id: string }>(
    request.post(`/v1/glossary/books/${bookId}/wiki`, {
      ...auth(token),
      data: { entity_id: entity.entity_id, template_code: 'character' },
    }),
  );
  return { articleId: article.article_id, entityId: entity.entity_id, displayName };
}
