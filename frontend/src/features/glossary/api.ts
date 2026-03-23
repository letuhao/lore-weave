import { apiJson } from '@/api';
import type { EntityKind } from './types';

const BASE = '/v1/glossary';

export const glossaryApi = {
  /** GET /v1/glossary/kinds — returns all 12 default entity kinds with attribute definitions. */
  getKinds(token: string): Promise<EntityKind[]> {
    return apiJson<EntityKind[]>(`${BASE}/kinds`, { token });
  },
};
