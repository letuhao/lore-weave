// Typed client for the book-service steering routes (all under the gateway /v1).
// Errors bubble as the standard apiJson Error carrying `.status`/`.code` so the hook
// can surface 409 (duplicate name within the book) and 422 (cap/enum violation).
import { apiJson } from '@/api';
import type { SteeringEntry, SteeringInput } from './types';

/** T12 — what this book's steering COSTS against the cap that will actually apply.
 *
 * Served by chat-service (under /v1/chat so the existing gateway proxy reaches it) because the cap
 * and the token estimator live there. Deliberately NOT re-implemented in the browser: a second
 * estimate that disagreed with the one applied at generation time would be worse than no
 * indicator, because it would be believed. */
export interface SteeringBudget {
  total_entries: number;
  total_tokens: number;
  cap_tokens: number;
  over_budget: boolean;
  would_drop: number;
  would_drop_names: string[];
}

export const steeringApi = {
  budget(token: string, bookId: string) {
    return apiJson<SteeringBudget>(`/v1/chat/books/${bookId}/steering-budget`, { token });
  },
  list(token: string, bookId: string) {
    // book-service returns the {items,total} envelope (review-impl HIGH: the FE
    // consumed it as a bare array → .map crashed the panel on every load).
    return apiJson<{ items: SteeringEntry[]; total: number }>(
      `/v1/books/${bookId}/steering`,
      { token },
    ).then((r) => r.items);
  },
  create(token: string, bookId: string, payload: SteeringInput) {
    return apiJson<SteeringEntry>(`/v1/books/${bookId}/steering`, {
      method: 'POST',
      token,
      body: JSON.stringify(payload),
    });
  },
  update(token: string, bookId: string, id: string, payload: SteeringInput) {
    return apiJson<SteeringEntry>(`/v1/books/${bookId}/steering/${id}`, {
      method: 'PUT',
      token,
      body: JSON.stringify(payload),
    });
  },
  remove(token: string, bookId: string, id: string) {
    return apiJson<void>(`/v1/books/${bookId}/steering/${id}`, { method: 'DELETE', token });
  },
};
