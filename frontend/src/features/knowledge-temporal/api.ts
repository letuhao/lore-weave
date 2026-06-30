// KAL (knowledge-gateway) read API for the FE temporal surfaces. All calls go through the BFF
// at the relative `/v1/kal/*` path (rides the proxy→gateway path in dev + prod, like every
// other FE api). The BFF passes the user's Bearer JWT through; the KAL dual-auths it (validate
// + book grant-check) and pins X-User-Id — so the FE just attaches `token`, nothing else.
import { apiJson } from '../../api';
import type {
  CanonicalSnapshot,
  CanonicalTranslation,
  FactsResponse,
  TimelineResponse,
  AttrValuesResponse,
  RosterResponse,
  RetrieveResponse,
  NeighborhoodResponse,
} from './types';

const BASE = '/v1/kal/books';

function qs(params: Record<string, string | number | undefined | null>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : '';
}

export const kalApi = {
  getCanonical(bookId: string, entityId: string, token: string, asOf?: number) {
    return apiJson<CanonicalSnapshot>(
      `${BASE}/${bookId}/entities/${entityId}/canonical${qs({ as_of: asOf })}`,
      { token },
    );
  },

  getCanonicalTranslation(bookId: string, entityId: string, lang: string, token: string, asOf?: number) {
    return apiJson<CanonicalTranslation>(
      `${BASE}/${bookId}/entities/${entityId}/canonical-translation${qs({ lang, as_of: asOf })}`,
      { token },
    );
  },

  getFacts(bookId: string, entityId: string, token: string, opts?: { asOf?: number; attrs?: string }) {
    return apiJson<FactsResponse>(
      `${BASE}/${bookId}/entities/${entityId}/facts${qs({ as_of: opts?.asOf, attrs: opts?.attrs })}`,
      { token },
    );
  },

  getTimeline(
    bookId: string,
    entityId: string,
    token: string,
    opts?: { cursor?: string; limit?: number; beforeOrder?: number; afterOrder?: number },
  ) {
    return apiJson<TimelineResponse>(
      `${BASE}/${bookId}/entities/${entityId}/timeline${qs({
        cursor: opts?.cursor,
        limit: opts?.limit,
        before_order: opts?.beforeOrder,
        after_order: opts?.afterOrder,
      })}`,
      { token },
    );
  },

  getAttrValues(
    bookId: string,
    entityId: string,
    attr: string,
    token: string,
    opts?: { cursor?: string; asOf?: number },
  ) {
    return apiJson<AttrValuesResponse>(
      `${BASE}/${bookId}/entities/${entityId}/attr-values${qs({ attr, cursor: opts?.cursor, as_of: opts?.asOf })}`,
      { token },
    );
  },

  roster(bookId: string, token: string, opts?: { cursor?: string; limit?: number }) {
    return apiJson<RosterResponse>(
      `${BASE}/${bookId}/roster${qs({ cursor: opts?.cursor, limit: opts?.limit })}`,
      { token },
    );
  },

  search(bookId: string, query: string, token: string, opts?: { k?: number }) {
    return apiJson<RosterResponse>(
      `${BASE}/${bookId}/search${qs({ query, k: opts?.k })}`,
      { token },
    );
  },

  neighborhood(
    bookId: string,
    entityId: string,
    token: string,
    opts?: { hops?: number; cap?: number; asOf?: number },
  ) {
    return apiJson<NeighborhoodResponse>(
      `${BASE}/${bookId}/entities/${entityId}/neighborhood${qs({
        hops: opts?.hops,
        cap: opts?.cap,
        as_of: opts?.asOf,
      })}`,
      { token },
    );
  },

  retrieve(bookId: string, body: { query: string; scope?: string; k?: number; as_of?: number }, token: string) {
    return apiJson<RetrieveResponse>(`${BASE}/${bookId}/retrieve`, {
      token,
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  },
};
