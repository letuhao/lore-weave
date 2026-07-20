// P1.2 (book-structure-pipeline spec §4.2) — the FE client for the unified manuscript-structure read.
// One book-service-owned call replaces the old juggle of useWorkResolution + partsApi.list + a mode
// guess. Parts are ALWAYS present in the response (they can't be hidden by Work-mode) → Bug 4 fixed.

import { apiJson } from '@/api';

export interface StructurePartHeader {
  part_id: string;
  title: string | null;
  sort_order: number;
  chapter_count: number;
}

export interface BookStructure {
  book_id: string;
  kinds_present: { parts: boolean; outline: boolean };
  /** Active parts (acts) in sort order, headers + counts — chapters are lazy-loaded per group. */
  parts: StructurePartHeader[];
  unassigned_count: number;
  active_work: { project_id: string | null };
  /** "ok" | "unavailable" — surfaces a composition outage rather than silently flattening. */
  sources: { parts: string; work: string };
}

export const structureApi = {
  /** GET the manuscript structure skeleton (book-service resolver). VIEW-gated server-side. */
  get(token: string, bookId: string): Promise<BookStructure> {
    return apiJson<BookStructure>(`/v1/books/${bookId}/structure`, { token });
  },
};
