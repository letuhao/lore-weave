// Typed client for the book-service steering routes (all under the gateway /v1).
// Errors bubble as the standard apiJson Error carrying `.status`/`.code` so the hook
// can surface 409 (duplicate name within the book) and 422 (cap/enum violation).
import { apiJson } from '@/api';
import type { SteeringEntry, SteeringInput } from './types';

export const steeringApi = {
  list(token: string, bookId: string) {
    return apiJson<SteeringEntry[]>(`/v1/books/${bookId}/steering`, { token });
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
