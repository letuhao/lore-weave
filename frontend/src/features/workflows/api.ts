// API layer for the workflow rack (M5). Same gateway path the extensions feature uses.
import { apiJson } from '@/api';
import type { WorkflowList } from './types';

const BASE = '/v1/agent-registry';

export const workflowsApi = {
  /** The workflows this user can see: System + their own + (if book_id given & granted) that book's. */
  list(token: string, params: { book_id?: string; surface?: string } = {}): Promise<WorkflowList> {
    const qs = new URLSearchParams();
    if (params.book_id) qs.set('book_id', params.book_id);
    if (params.surface) qs.set('surface', params.surface);
    const q = qs.toString();
    return apiJson<WorkflowList>(`${BASE}/workflows${q ? `?${q}` : ''}`, { token });
  },
};
