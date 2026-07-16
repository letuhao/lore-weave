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

export interface ArcDriftReport {
  thread_coverage?: { thread: string; realized: number; planned: number }[];
  pacing?: unknown;
  unmaterialized?: { motif_code: string; thread: string; reason: string }[];
  [k: string]: unknown;
}

/** 34 §4.2 §Drift — "how far has my materialized arc drifted from its template" (AT-6's stamp is
 *  written by materialize server-side, so a materialized arc carries arc_template_id and IS a drift
 *  subject). `arcId` is the structure_node id. Distinct honest failures: 422 NO_TEMPLATE_PROVENANCE
 *  (the arc was authored directly), 404 (the template is gone) — the caller renders each distinctly. */
export async function getArcTemplateDrift(
  projectId: string, arcId: string, token: string,
): Promise<{ report: ArcDriftReport | null; state: 'ok' | 'no_provenance' | 'gone' }> {
  try {
    const report = await apiJson<ArcDriftReport>(
      `${BASE}/works/${projectId}/conformance?scope=arc_template_drift&arc_id=${encodeURIComponent(arcId)}`,
      { token },
    );
    return { report, state: 'ok' };
  } catch (e) {
    const status = (e as { status?: number }).status;
    const code = ((e as { body?: { detail?: { code?: string } } }).body?.detail?.code) ?? '';
    if (status === 422 || code === 'NO_TEMPLATE_PROVENANCE') return { report: null, state: 'no_provenance' };
    if (status === 404) return { report: null, state: 'gone' };
    throw e;
  }
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
