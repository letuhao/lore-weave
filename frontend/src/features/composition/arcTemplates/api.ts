// 34/34a arc-templates — S2-owned API shim for the tier surfaces the motif arcApi doesn't cover
// (D-S2-ARC-SEAM: reach the shared REST routes WITHOUT editing S4's motif/arcApi.ts). The book-shared
// tier (34a) + the public catalog. Types stay loose (the panel reads a subset).
import { apiJson } from '../../../api';
import type { ArcTemplate } from '../motif/arcTypes';

const BASE = '/v1/composition';

/** 34a — the book's SHARED tier: list arc templates the caller can co-edit for `bookId` (the route
 *  VIEW-gates the book; a non-grantee's bookId is rejected server-side). */
export async function listBookSharedTemplates(bookId: string, token: string): Promise<ArcTemplate[]> {
  const r = await apiJson<{ arc_templates: ArcTemplate[] }>(
    `${BASE}/arc-templates?scope=all&book_id=${encodeURIComponent(bookId)}`, { token },
  );
  // keep only the book-shared rows (the 'all' scope also returns owned+system).
  return (r.arc_templates ?? []).filter((a: ArcTemplate) => (a as { book_shared?: boolean }).book_shared);
}

/** 34a — create into the book's SHARED tier (EDIT-gated server-side). */
export function createSharedTemplate(
  body: { code: string; name: string; language?: string }, bookId: string, token: string,
): Promise<ArcTemplate> {
  return apiJson<ArcTemplate>(
    `${BASE}/arc-templates?target=book_shared&book_id=${encodeURIComponent(bookId)}`,
    { method: 'POST', token, body: JSON.stringify({ language: 'en', ...body }) },
  );
}

export interface CatalogItem {
  id: string; code: string; name: string; chapter_span: number | null; genre_tags: string[];
}
/** 34 — the PUBLIC catalog (others' public templates; a paged allow-list projection). */
export async function listCatalog(
  params: { genre?: string; q?: string; limit?: number; offset?: number }, token: string,
): Promise<{ items: CatalogItem[]; total: number }> {
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v != null && v !== '') usp.set(k, String(v));
  const s = usp.toString();
  return apiJson(`${BASE}/arc-templates/catalog${s ? `?${s}` : ''}`, { token });
}
