// API layer for mode→capability bindings (M6). Same gateway path the extensions feature uses.
import { apiJson } from '@/api';
import type { Mode, ModeBinding } from './types';

const BASE = '/v1/agent-registry';

export interface ModeBindingWrite {
  inject_skills?: string[];
  inject_workflows?: string[];
  seed_tool_categories?: string[];
  disable_workflows?: string[];
}

export const modeBindingsApi = {
  get(token: string, mode: Mode, bookId?: string): Promise<ModeBinding> {
    const q = bookId ? `?book_id=${encodeURIComponent(bookId)}` : '';
    return apiJson<ModeBinding>(`${BASE}/mode-bindings/${mode}${q}`, { token });
  },

  /** Upsert the CALLER'S OWN tier (or a book they hold EDIT on). System is never writable here. */
  put(token: string, mode: Mode, body: ModeBindingWrite, bookId?: string): Promise<ModeBinding> {
    const q = bookId ? `?book_id=${encodeURIComponent(bookId)}` : '';
    return apiJson<ModeBinding>(`${BASE}/mode-bindings/${mode}${q}`, {
      method: 'PUT',
      token,
      body: JSON.stringify(body),
    });
  },
};
