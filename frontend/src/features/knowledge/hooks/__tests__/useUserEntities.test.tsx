import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

const useAuthMock = vi.fn();
vi.mock('@/auth', () => ({
  useAuth: () => useAuthMock(),
}));

const listMyEntitiesMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    knowledgeApi: { listMyEntities: (...args: unknown[]) => listMyEntitiesMock(...args) },
  };
});

import { useUserEntities } from '../useUserEntities';

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe('useUserEntities', () => {
  beforeEach(() => {
    listMyEntitiesMock.mockReset();
    useAuthMock.mockReset();
    useAuthMock.mockReturnValue({
      accessToken: 'tok-test',
      user: { user_id: 'u1', email: 'a@b', display_name: null, avatar_url: null },
    });
  });

  it('returns entities from the API with default scope=global limit=50', async () => {
    listMyEntitiesMock.mockResolvedValue({
      entities: [
        {
          id: 'e1',
          user_id: 'u1',
          project_id: null,
          name: 'Coffee drinker',
          canonical_name: 'coffee drinker',
          kind: 'preference',
          aliases: ['Coffee drinker'],
          canonical_version: 1,
          source_types: ['chat_turn'],
          confidence: 0.9,
          glossary_entity_id: null,
          anchor_score: 0,
          archived_at: null,
          archive_reason: null,
          evidence_count: 1,
          mention_count: 1,
          created_at: null,
          updated_at: null,
        },
      ],
    });
    const { result } = renderHook(() => useUserEntities(), { wrapper: wrapper() });
    await waitFor(() => {
      expect(result.current.entities).toHaveLength(1);
    });
    expect(result.current.entities[0].name).toBe('Coffee drinker');
    expect(listMyEntitiesMock).toHaveBeenCalledWith(
      { scope: 'global', limit: 50 },
      'tok-test',
    );
  });

  it('returns an empty array initially (not null) so consumers can .map', async () => {
    listMyEntitiesMock.mockResolvedValue({ entities: [] });
    const { result } = renderHook(() => useUserEntities(), { wrapper: wrapper() });
    expect(result.current.entities).toEqual([]);
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });
    expect(result.current.entities).toEqual([]);
  });

  it('surfaces API errors via the error field', async () => {
    const boom = new Error('listing failed');
    listMyEntitiesMock.mockRejectedValue(boom);
    const { result } = renderHook(() => useUserEntities(), { wrapper: wrapper() });
    await waitFor(() => {
      expect(result.current.error).toBe(boom);
    });
  });
});
